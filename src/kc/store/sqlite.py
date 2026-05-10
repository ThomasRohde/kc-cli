"""SQLite cache/state store."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from kc.models.artifact import ArtifactRecord
from kc.models.citation import CitationEdgeRecord
from kc.models.plan import PlanRecord
from kc.models.source import SourceRecord
from kc.models.source_range import SourceRangeRecord
from kc.models.task import TaskRecord

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY,
  uri TEXT NOT NULL,
  display_name TEXT,
  media_type TEXT,
  fingerprint TEXT NOT NULL,
  status TEXT NOT NULL,
  domain_json TEXT NOT NULL,
  authority_json TEXT NOT NULL,
  record_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_ranges (
  range_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  source_fingerprint TEXT NOT NULL,
  locator_json TEXT NOT NULL,
  text_hash TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  heading_path_json TEXT,
  record_json TEXT NOT NULL,
  FOREIGN KEY(source_id) REFERENCES sources(source_id)
);

CREATE TABLE IF NOT EXISTS source_range_embeddings (
  range_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  source_fingerprint TEXT NOT NULL,
  text_hash TEXT NOT NULL,
  model_name TEXT NOT NULL,
  model_checksum TEXT NOT NULL,
  dimension INTEGER NOT NULL,
  embedding BLOB NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(range_id) REFERENCES source_ranges(range_id),
  FOREIGN KEY(source_id) REFERENCES sources(source_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS source_ranges_fts USING fts5(
  range_id UNINDEXED,
  source_id UNINDEXED,
  domain,
  heading_path,
  excerpt
);

CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id TEXT PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  artifact_type TEXT NOT NULL,
  status TEXT NOT NULL,
  fingerprint TEXT,
  record_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS citation_edges (
  edge_id TEXT PRIMARY KEY,
  artifact_id TEXT,
  artifact_path TEXT NOT NULL,
  source_id TEXT NOT NULL,
  range_id TEXT,
  citation_token TEXT NOT NULL,
  status TEXT NOT NULL,
  record_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  goal TEXT NOT NULL,
  record_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
  plan_id TEXT PRIMARY KEY,
  command TEXT NOT NULL,
  mode TEXT NOT NULL,
  record_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  key TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS index_metadata (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(UTC).isoformat()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def rebuild_index(
    db_path: Path,
    sources: list[SourceRecord],
    ranges: list[SourceRangeRecord],
    artifacts: list[ArtifactRecord] | None = None,
    citation_edges: list[CitationEdgeRecord] | None = None,
) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        conn.executescript(
            """
            DROP TABLE IF EXISTS citation_edges;
            DROP TABLE IF EXISTS artifacts;
            DROP TABLE IF EXISTS source_ranges_fts;
            DROP TABLE IF EXISTS source_range_embeddings;
            DROP TABLE IF EXISTS source_ranges;
            DROP TABLE IF EXISTS sources;
            """
        )
        conn.executescript(SCHEMA_SQL)
        timestamp = now()
        conn.executemany(
            """
            INSERT INTO sources (
              source_id, uri, display_name, media_type, fingerprint, status,
              domain_json, authority_json, record_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    s.source_id,
                    s.uri,
                    s.display_name,
                    s.media_type,
                    s.fingerprint,
                    s.status,
                    orjson.dumps(s.domain).decode(),
                    orjson.dumps(s.authority.model_dump(mode="json")).decode(),
                    orjson.dumps(s.model_dump(mode="json")).decode(),
                    timestamp,
                )
                for s in sources
            ],
        )
        source_by_id = {s.source_id: s for s in sources}
        conn.executemany(
            """
            INSERT INTO source_ranges (
              range_id, source_id, source_fingerprint, locator_json, text_hash,
              excerpt, heading_path_json, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    r.range_id,
                    r.source_id,
                    r.source_fingerprint,
                    orjson.dumps(r.locator.model_dump(mode="json")).decode(),
                    r.text_hash,
                    r.excerpt,
                    orjson.dumps(r.metadata.get("heading_path", [])).decode(),
                    orjson.dumps(r.model_dump(mode="json")).decode(),
                )
                for r in ranges
            ],
        )
        conn.executemany(
            """
            INSERT INTO source_ranges_fts(range_id, source_id, domain, heading_path, excerpt)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    r.range_id,
                    r.source_id,
                    " ".join(
                        source_by_id.get(
                            r.source_id,
                            SourceRecord(
                                source_id=r.source_id,
                                uri="",
                                display_name="",
                                fingerprint=r.source_fingerprint,
                                registered_at=timestamp,
                            ),
                        ).domain
                    ),
                    " ".join(str(x) for x in r.metadata.get("heading_path", [])),
                    r.excerpt,
                )
                for r in ranges
            ],
        )
        if artifacts:
            upsert_artifacts(conn, artifacts)
        if citation_edges:
            replace_citation_edges(conn, citation_edges)
        conn.execute(
            "INSERT OR REPLACE INTO index_metadata(key, value_json, updated_at) VALUES (?, ?, ?)",
            ("last_build", json.dumps({"built_at": timestamp, "ranges": len(ranges)}), timestamp),
        )
        conn.commit()
        return {"sources": len(sources), "ranges": len(ranges), "built_at": timestamp}
    finally:
        conn.close()


def upsert_artifacts(conn: sqlite3.Connection, artifacts: list[ArtifactRecord]) -> None:
    timestamp = now()
    conn.executemany(
        """
        INSERT OR REPLACE INTO artifacts (
          artifact_id, path, artifact_type, status, fingerprint, record_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                a.artifact_id,
                a.path,
                a.artifact_type,
                a.status,
                a.fingerprint,
                orjson.dumps(a.model_dump(mode="json")).decode(),
                timestamp,
            )
            for a in artifacts
        ],
    )


def replace_citation_edges(
    conn: sqlite3.Connection, citation_edges: list[CitationEdgeRecord]
) -> None:
    for edge in citation_edges:
        conn.execute("DELETE FROM citation_edges WHERE edge_id = ?", (edge.edge_id,))
    conn.executemany(
        """
        INSERT OR REPLACE INTO citation_edges (
          edge_id, artifact_id, artifact_path, source_id, range_id,
          citation_token, status, record_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                e.edge_id,
                e.artifact_id,
                e.artifact_path,
                e.source_id,
                e.range_id,
                e.citation_token,
                e.status,
                orjson.dumps(e.model_dump(mode="json")).decode(),
            )
            for e in citation_edges
        ],
    )


def save_task(db_path: Path, task: TaskRecord) -> None:
    init_db(db_path)
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO tasks(task_id, status, goal, record_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                task.task_id,
                task.status,
                task.goal,
                orjson.dumps(task.model_dump(mode="json")).decode(),
                task.updated_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_task(db_path: Path, task_id: str) -> TaskRecord | None:
    init_db(db_path)
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT record_json FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return TaskRecord.model_validate(orjson.loads(row["record_json"]))
    finally:
        conn.close()


def save_plan(db_path: Path, plan: PlanRecord) -> None:
    init_db(db_path)
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO plans(plan_id, command, mode, record_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                plan.plan_id,
                plan.command,
                plan.mode,
                orjson.dumps(plan.model_dump(mode="json")).decode(),
                plan.created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_idempotency(db_path: Path, key: str) -> dict[str, Any] | None:
    init_db(db_path)
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT result_json FROM idempotency_keys WHERE key = ?", (key,)
        ).fetchone()
        return None if row is None else orjson.loads(row["result_json"])
    finally:
        conn.close()


def save_idempotency(db_path: Path, key: str, plan_id: str, result: dict[str, Any]) -> None:
    init_db(db_path)
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO idempotency_keys(key, plan_id, result_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (key, plan_id, orjson.dumps(result).decode(), now()),
        )
        conn.commit()
    finally:
        conn.close()
