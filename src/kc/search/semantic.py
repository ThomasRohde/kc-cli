"""Local semantic retrieval support for source ranges."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import orjson

from kc.errors import KcError
from kc.models.source_range import SourceRangeRecord
from kc.store.sqlite import init_db

MODEL_PROVIDER = "model2vec"
BUNDLED_MODEL_NAME = "potion-base-8M"
EXPECTED_DIMENSION = 256
EXPECTED_CHECKSUM = "sha256:aef1c5e1fd70060804f5295ec8e9ab3ed62e50e79b208435fb77e15c5bf94bb8"
SEMANTIC_METADATA_KEY = "semantic_model"


@dataclass(frozen=True)
class SemanticRank:
    range_id: str
    rank: int
    score: float


def bundled_model_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "embedding_models" / BUNDLED_MODEL_NAME


def model_directory_checksum(model_dir: Path) -> str:
    root = Path(model_dir)
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(rel)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _model_unavailable(message: str, **details: Any) -> KcError:
    return KcError(
        code="KC_RETRIEVAL_MODEL_UNAVAILABLE",
        message=message,
        details=details,
        suggested_action="run kc index build --semantic after fixing the local model",
    )


def semantic_model_metadata(model: Any | None = None) -> dict[str, Any]:
    dimension = int(getattr(model, "dim", EXPECTED_DIMENSION) or EXPECTED_DIMENSION)
    return {
        "provider": MODEL_PROVIDER,
        "model": BUNDLED_MODEL_NAME,
        "dimension": dimension,
        "checksum": model_directory_checksum(bundled_model_dir()),
        "purpose": "ranking_only",
    }


@lru_cache(maxsize=1)
def load_semantic_model() -> Any:
    model_dir = bundled_model_dir()
    if not model_dir.exists():
        raise _model_unavailable("Bundled semantic model directory is missing.", model_dir=str(model_dir))
    checksum = model_directory_checksum(model_dir)
    if checksum != EXPECTED_CHECKSUM:
        raise _model_unavailable(
            "Bundled semantic model checksum does not match the configured checksum.",
            model_dir=str(model_dir),
            expected_checksum=EXPECTED_CHECKSUM,
            actual_checksum=checksum,
        )
    try:
        from model2vec import StaticModel
    except ImportError as exc:
        raise _model_unavailable("model2vec is not installed.", dependency="model2vec") from exc
    try:
        model = StaticModel.from_pretrained(str(model_dir))
    except Exception as exc:
        raise _model_unavailable("Failed to load bundled semantic model.", model_dir=str(model_dir)) from exc
    dimension = int(getattr(model, "dim", 0) or 0)
    if dimension and dimension != EXPECTED_DIMENSION:
        raise _model_unavailable(
            "Bundled semantic model dimension does not match the configured dimension.",
            expected_dimension=EXPECTED_DIMENSION,
            actual_dimension=dimension,
        )
    return model


def is_model_available() -> tuple[bool, dict[str, Any] | None, str | None]:
    try:
        model = load_semantic_model()
        return True, semantic_model_metadata(model), None
    except KcError as exc:
        return False, None, exc.message


def _encode(model: Any, texts: str | list[str]) -> npt.NDArray[np.float32]:
    try:
        encoded = model.encode(texts, show_progress_bar=False, use_multiprocessing=False)
    except TypeError:
        encoded = model.encode(texts)
    return np.asarray(encoded, dtype=np.float32)


def embed_text(model: Any, text: str) -> npt.NDArray[np.float32]:
    return _encode(model, text).reshape(-1).astype(np.float32)


def embed_texts(model: Any, texts: list[str]) -> npt.NDArray[np.float32]:
    if not texts:
        return np.empty((0, EXPECTED_DIMENSION), dtype=np.float32)
    encoded = _encode(model, texts)
    if encoded.ndim == 1:
        encoded = encoded.reshape(1, -1)
    return encoded.astype(np.float32)


def embedding_to_blob(embedding: npt.NDArray[np.float32]) -> bytes:
    return np.asarray(embedding, dtype=np.float32).reshape(-1).tobytes()


def blob_to_embedding(blob: bytes) -> npt.NDArray[np.float32]:
    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(a: npt.NDArray[np.float32], b: npt.NDArray[np.float32]) -> float:
    left = np.asarray(a, dtype=np.float32).reshape(-1)
    right = np.asarray(b, dtype=np.float32).reshape(-1)
    norm = np.linalg.norm(left) * np.linalg.norm(right)
    if norm == 0:
        return 0.0
    return float(np.dot(left, right) / norm)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _metadata_from_db(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute("SELECT value_json FROM index_metadata WHERE key = ?", (SEMANTIC_METADATA_KEY,)).fetchone()
    if row is None:
        return None
    return orjson.loads(row["value_json"])


def build_semantic_index(db_path: Path, ranges: list[SourceRangeRecord]) -> dict[str, Any]:
    init_db(db_path)
    model = load_semantic_model()
    metadata = semantic_model_metadata(model)
    vectors = embed_texts(model, [r.excerpt for r in ranges])
    if len(vectors) != len(ranges):
        raise _model_unavailable(
            "Semantic model returned an unexpected number of embeddings.",
            expected=len(ranges),
            actual=len(vectors),
        )
    dimension = int(vectors.shape[1]) if vectors.ndim == 2 and len(ranges) > 0 else int(metadata["dimension"])
    if dimension != int(metadata["dimension"]):
        raise _model_unavailable(
            "Semantic model returned embeddings with an unexpected dimension.",
            expected_dimension=metadata["dimension"],
            actual_dimension=dimension,
        )

    conn = _connect(db_path)
    try:
        timestamp = _now()
        conn.execute("DELETE FROM source_range_embeddings")
        conn.executemany(
            """
            INSERT INTO source_range_embeddings(
              range_id, source_id, source_fingerprint, text_hash, model_name,
              model_checksum, dimension, embedding, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    source_range.range_id,
                    source_range.source_id,
                    source_range.source_fingerprint,
                    source_range.text_hash,
                    metadata["model"],
                    metadata["checksum"],
                    metadata["dimension"],
                    embedding_to_blob(vectors[index]),
                    timestamp,
                )
                for index, source_range in enumerate(ranges)
            ],
        )
        stored_metadata = {**metadata, "built_at": timestamp, "ranges": len(ranges)}
        conn.execute(
            "INSERT OR REPLACE INTO index_metadata(key, value_json, updated_at) VALUES (?, ?, ?)",
            (SEMANTIC_METADATA_KEY, orjson.dumps(stored_metadata).decode(), timestamp),
        )
        conn.commit()
        return {"enabled": True, "model": stored_metadata, "embeddings": len(ranges)}
    finally:
        conn.close()


def semantic_index_status(db_path: Path, ranges: list[SourceRangeRecord] | None = None) -> dict[str, Any]:
    available, model_metadata, unavailable_reason = is_model_available()
    status: dict[str, Any] = {
        "model_available": available,
        "model": model_metadata,
        "unavailable_reason": unavailable_reason,
        "index_metadata": None,
        "metadata_match": False,
        "vector_count": 0,
        "missing_vectors": None,
        "stale_vectors": None,
    }
    if not db_path.exists():
        return status
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, "source_range_embeddings"):
            return status
        status["vector_count"] = int(conn.execute("SELECT COUNT(*) FROM source_range_embeddings").fetchone()[0])
        index_metadata = _metadata_from_db(conn)
        status["index_metadata"] = index_metadata
        if model_metadata and index_metadata:
            status["metadata_match"] = all(
                index_metadata.get(key) == model_metadata.get(key)
                for key in ("provider", "model", "dimension", "checksum", "purpose")
            )
        if ranges is not None:
            rows = {
                row["range_id"]: row
                for row in conn.execute(
                    """
                    SELECT range_id, source_fingerprint, text_hash, model_checksum, dimension
                    FROM source_range_embeddings
                    """
                ).fetchall()
            }
            missing = 0
            stale = 0
            checksum = model_metadata.get("checksum") if model_metadata else None
            dimension = int(model_metadata.get("dimension")) if model_metadata else None
            for source_range in ranges:
                row = rows.get(source_range.range_id)
                if row is None:
                    missing += 1
                    continue
                if (
                    row["source_fingerprint"] != source_range.source_fingerprint
                    or row["text_hash"] != source_range.text_hash
                    or row["model_checksum"] != checksum
                    or int(row["dimension"]) != dimension
                ):
                    stale += 1
            status["missing_vectors"] = missing
            status["stale_vectors"] = stale
        return status
    finally:
        conn.close()


def assert_semantic_index_ready(
    db_path: Path,
    ranges: list[SourceRangeRecord],
) -> Any:
    model = load_semantic_model()
    status = semantic_index_status(db_path, ranges)
    if not status["index_metadata"] or not status["metadata_match"]:
        raise _model_unavailable(
            "Semantic index metadata is missing or stale. Run kc index build --semantic.",
            status=status,
        )
    if status["missing_vectors"] or status["stale_vectors"]:
        raise _model_unavailable(
            "Semantic index vectors are missing or stale. Run kc index build --semantic.",
            missing_vectors=status["missing_vectors"],
            stale_vectors=status["stale_vectors"],
        )
    return model


def semantic_rankings(
    conn: sqlite3.Connection,
    query: str,
    model: Any,
    *,
    domain: str | None = None,
    limit: int = 100,
) -> list[SemanticRank]:
    query_embedding = embed_text(model, query)
    sql = """
        SELECT e.range_id, e.embedding
        FROM source_range_embeddings e
        JOIN sources s ON s.source_id = e.source_id
    """
    params: list[Any] = []
    if domain:
        sql += " WHERE s.domain_json LIKE ?"
        params.append(f"%{domain}%")
    rows = conn.execute(sql, params).fetchall()
    scored: list[tuple[str, float]] = []
    for row in rows:
        score = cosine_similarity(query_embedding, blob_to_embedding(row["embedding"]))
        scored.append((row["range_id"], score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [
        SemanticRank(range_id=range_id, rank=rank, score=score)
        for rank, (range_id, score) in enumerate(scored[:limit], start=1)
    ]
