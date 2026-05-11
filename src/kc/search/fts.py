"""Range retrieval over SQLite FTS5 plus optional semantic vectors."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import orjson

from kc.errors import KcError
from kc.models.source import SourceRecord
from kc.models.source_range import SourceRangeRecord
from kc.paths import ensure_data_dir_exists
from kc.search.semantic import assert_semantic_index_ready, semantic_rankings
from kc.store.jsonl import read_jsonl
from kc.store.sqlite import index_status, init_db, rebuild_index


@dataclass(frozen=True)
class Bm25Rank:
    range_id: str
    rank: int
    score: float


@dataclass(frozen=True)
class CombinedRank:
    range_id: str
    bm25_rank: int | None = None
    bm25_score: float | None = None
    semantic_rank: int | None = None
    semantic_score: float | None = None
    rrf_score: float | None = None


def ensure_index(db_path: Path, sources_path: Path, ranges_path: Path) -> None:
    ensure_data_dir_exists()
    sources = read_jsonl(sources_path, SourceRecord)
    ranges = read_jsonl(ranges_path, SourceRangeRecord)
    status = index_status(db_path, sources, ranges)
    if status["sqlite_exists"] and not status["stale"]:
        return
    rebuild_index(db_path, sources, ranges)


def _build_fts_query(query: str) -> str:
    terms = [t.replace('"', "").strip() for t in query.split() if t.strip()]
    return " OR ".join(f'"{term}"' for term in terms)


def citation_token(source_id: str, locator: dict[str, Any]) -> str:
    if locator.get("kind") == "line_range":
        return f"[kc:{source_id}:L{locator.get('start_line')}-L{locator.get('end_line')}]"
    if locator.get("kind") == "json_pointer":
        pointer = quote(str(locator.get("pointer", "/")), safe="/~")
        return f"[kc:{source_id}:JP:{pointer}]"
    if locator.get("kind") == "csv_row_range":
        return f"[kc:{source_id}:CSV:R{locator.get('start_row')}-R{locator.get('end_row')}]"
    return f"[kc:{source_id}]"


def rrf_score(ranks: list[int], *, k: int = 60) -> float:
    return sum(1.0 / (k + rank) for rank in ranks)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _bm25_rankings(
    conn: sqlite3.Connection,
    query: str,
    *,
    domain: str | None = None,
    limit: int = 100,
) -> list[Bm25Rank]:
    fts_query = _build_fts_query(query)
    if not fts_query:
        return []
    sql = """
        SELECT
          f.range_id,
          bm25(source_ranges_fts) AS bm25_score
        FROM source_ranges_fts f
        JOIN source_ranges r ON r.range_id = f.range_id
        JOIN sources s ON s.source_id = f.source_id
        WHERE source_ranges_fts MATCH ?
    """
    params: list[Any] = [fts_query]
    if domain:
        sql += " AND f.domain LIKE ?"
        params.append(f"%{domain}%")
    sql += " ORDER BY bm25_score, f.range_id LIMIT ?"
    params.append(limit)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        raise KcError(
            code="KC_INDEX_BUILD_FAILED",
            message=f"Search failed: {exc}",
            details={"query": query},
        ) from exc
    return [
        Bm25Rank(range_id=row["range_id"], rank=rank, score=float(row["bm25_score"]))
        for rank, row in enumerate(rows, start=1)
    ]


def _rows_for_ranges(conn: sqlite3.Connection, range_ids: list[str]) -> dict[str, sqlite3.Row]:
    if not range_ids:
        return {}
    placeholders = ", ".join("?" for _ in range_ids)
    rows = conn.execute(
        f"""
        SELECT
          r.range_id,
          r.source_id,
          r.locator_json,
          r.source_fingerprint,
          r.record_json AS range_record_json,
          r.excerpt,
          s.display_name,
          s.status AS source_status,
          s.authority_json,
          s.fingerprint AS current_source_fingerprint
        FROM source_ranges r
        JOIN sources s ON s.source_id = r.source_id
        WHERE r.range_id IN ({placeholders})
        """,
        range_ids,
    ).fetchall()
    return {row["range_id"]: row for row in rows}


def _format_result(
    row: sqlite3.Row,
    rank: CombinedRank,
    *,
    hybrid_rank: int,
) -> dict[str, Any]:
    locator = orjson.loads(row["locator_json"])
    authority = orjson.loads(row["authority_json"])
    return {
        "range_id": row["range_id"],
        "source_id": row["source_id"],
        "display_name": row["display_name"],
        "locator": locator,
        "excerpt": row["excerpt"],
        "scores": {
            "bm25_rank": rank.bm25_rank,
            "bm25_score": rank.bm25_score,
            "semantic_rank": rank.semantic_rank,
            "semantic_score": rank.semantic_score,
            "hybrid_rank": hybrid_rank,
            "rrf_score": rank.rrf_score,
        },
        "citation_token": citation_token(row["source_id"], locator),
        "source_authority": authority,
        "source_status": row["source_status"],
        "source_fingerprint": row["source_fingerprint"],
        "current_source_fingerprint": row["current_source_fingerprint"],
    }


def _combine_bm25_only(rankings: list[Bm25Rank]) -> list[CombinedRank]:
    return [
        CombinedRank(range_id=item.range_id, bm25_rank=item.rank, bm25_score=item.score)
        for item in rankings
    ]


def _combine_semantic_only(rankings: list[Any]) -> list[CombinedRank]:
    return [
        CombinedRank(
            range_id=item.range_id,
            semantic_rank=item.rank,
            semantic_score=item.score,
        )
        for item in rankings
    ]


def _combine_hybrid(
    bm25: list[Bm25Rank],
    semantic: list[Any],
    *,
    rrf_k: int,
    limit: int,
) -> list[CombinedRank]:
    by_range: dict[str, CombinedRank] = {}
    for item in bm25:
        by_range[item.range_id] = CombinedRank(
            range_id=item.range_id,
            bm25_rank=item.rank,
            bm25_score=item.score,
        )
    for item in semantic:
        existing = by_range.get(item.range_id)
        by_range[item.range_id] = CombinedRank(
            range_id=item.range_id,
            bm25_rank=existing.bm25_rank if existing else None,
            bm25_score=existing.bm25_score if existing else None,
            semantic_rank=item.rank,
            semantic_score=item.score,
        )

    merged = []
    for item in by_range.values():
        ranks = [rank for rank in [item.bm25_rank, item.semantic_rank] if rank is not None]
        merged.append(
            CombinedRank(
                range_id=item.range_id,
                bm25_rank=item.bm25_rank,
                bm25_score=item.bm25_score,
                semantic_rank=item.semantic_rank,
                semantic_score=item.semantic_score,
                rrf_score=rrf_score(ranks, k=rrf_k),
            )
        )
    sentinel = 1_000_000
    merged.sort(
        key=lambda item: (
            -(item.rrf_score or 0.0),
            item.bm25_rank if item.bm25_rank is not None else sentinel,
            item.semantic_rank if item.semantic_rank is not None else sentinel,
            item.range_id,
        )
    )
    return merged[:limit]


def search_ranges(
    db_path: Path,
    query: str,
    *,
    domain: str | None = None,
    limit: int = 10,
    mode: str = "bm25",
    rrf_k: int = 60,
    ranges: list[SourceRangeRecord] | None = None,
) -> list[dict[str, Any]]:
    if mode not in {"bm25", "semantic", "hybrid"}:
        raise KcError(
            code="KC_RETRIEVAL_MODEL_UNAVAILABLE",
            message=f"Unsupported retrieval mode: {mode}",
            details={"mode": mode, "supported": ["bm25", "semantic", "hybrid"]},
        )
    init_db(db_path)
    conn = _connect(db_path)
    try:
        candidate_limit = max(limit * 5, 100)
        if mode == "bm25":
            combined = _combine_bm25_only(_bm25_rankings(conn, query, domain=domain, limit=limit))
        else:
            source_ranges = ranges if ranges is not None else []
            model = assert_semantic_index_ready(db_path, source_ranges)
            semantic = semantic_rankings(conn, query, model, domain=domain, limit=candidate_limit)
            if mode == "semantic":
                combined = _combine_semantic_only(semantic[:limit])
            else:
                bm25 = _bm25_rankings(conn, query, domain=domain, limit=candidate_limit)
                combined = _combine_hybrid(bm25, semantic, rrf_k=rrf_k, limit=limit)
        rows = _rows_for_ranges(conn, [item.range_id for item in combined])
        results = []
        for hybrid_rank, item in enumerate(combined, start=1):
            row = rows.get(item.range_id)
            if row is not None:
                results.append(_format_result(row, item, hybrid_rank=hybrid_rank))
        return results
    finally:
        conn.close()
