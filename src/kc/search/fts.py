"""FTS5/BM25 range search."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import orjson

from kc.errors import KcError
from kc.models.source import SourceRecord
from kc.models.source_range import SourceRangeRecord
from kc.store.jsonl import read_jsonl
from kc.store.sqlite import init_db, rebuild_index


def ensure_index(db_path: Path, sources_path: Path, ranges_path: Path) -> None:
    if db_path.exists():
        return
    sources = read_jsonl(sources_path, SourceRecord)
    ranges = read_jsonl(ranges_path, SourceRangeRecord)
    rebuild_index(db_path, sources, ranges)


def _build_fts_query(query: str) -> str:
    terms = [t.replace('"', "").strip() for t in query.split() if t.strip()]
    return " OR ".join(f'"{term}"' for term in terms)


def citation_token(source_id: str, locator: dict[str, Any]) -> str:
    if locator.get("kind") == "line_range":
        return f"[kc:{source_id}:L{locator.get('start_line')}-L{locator.get('end_line')}]"
    if locator.get("kind") == "json_pointer":
        pointer = str(locator.get("pointer", "/")).replace("]", "%5D").replace("[", "%5B")
        return f"[kc:{source_id}:JP:{pointer}]"
    return f"[kc:{source_id}]"


def search_ranges(
    db_path: Path,
    query: str,
    *,
    domain: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        fts_query = _build_fts_query(query)
        if not fts_query:
            return []
        sql = """
            SELECT
              f.range_id,
              f.source_id,
              f.domain,
              f.heading_path,
              f.excerpt,
              bm25(source_ranges_fts) AS bm25_score,
              r.locator_json,
              r.source_fingerprint,
              r.record_json AS range_record_json,
              s.display_name,
              s.status AS source_status,
              s.authority_json,
              s.fingerprint AS current_source_fingerprint
            FROM source_ranges_fts f
            JOIN source_ranges r ON r.range_id = f.range_id
            JOIN sources s ON s.source_id = f.source_id
            WHERE source_ranges_fts MATCH ?
        """
        params: list[Any] = [fts_query]
        if domain:
            sql += " AND f.domain LIKE ?"
            params.append(f"%{domain}%")
        sql += " ORDER BY bm25_score LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        raise KcError(
            code="KC_INDEX_BUILD_FAILED",
            message=f"Search failed: {exc}",
            details={"query": query},
        ) from exc
    finally:
        conn.close()

    results: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        locator = orjson.loads(row["locator_json"])
        authority = orjson.loads(row["authority_json"])
        results.append(
            {
                "range_id": row["range_id"],
                "source_id": row["source_id"],
                "display_name": row["display_name"],
                "locator": locator,
                "excerpt": row["excerpt"],
                "scores": {
                    "bm25_rank": idx,
                    "bm25_score": row["bm25_score"],
                    "semantic_rank": None,
                    "hybrid_rank": idx,
                },
                "citation_token": citation_token(row["source_id"], locator),
                "source_authority": authority,
                "source_status": row["source_status"],
                "source_fingerprint": row["source_fingerprint"],
                "current_source_fingerprint": row["current_source_fingerprint"],
            }
        )
    return results
