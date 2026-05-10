from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from kc.errors import KcError
from kc.models.artifact import ArtifactRecord
from kc.models.citation import CitationEdgeRecord
from kc.models.source import SourceRecord
from kc.models.source_range import SourceRangeRecord
from kc.output import emit_error, emit_unexpected, state
from kc.paths import current_paths, repo_relative
from kc.store.jsonl import read_jsonl, write_jsonl


def now() -> str:
    return datetime.now(UTC).isoformat()


def run[T](command: str, func: Callable[[], T]) -> T:
    try:
        return func()
    except SystemExit:
        raise
    except KcError as exc:
        emit_error(command, exc)
    except Exception as exc:
        emit_unexpected(command, exc)
    raise AssertionError("unreachable")


def require_json_format(command: str) -> None:
    if state.format != "json":
        raise KcError(
            code="KC_UNSUPPORTED_FEATURE",
            message=f"Output format '{state.format}' is not supported for {command}.",
            details={"requested": state.format, "supported": ["json"]},
        )


def load_sources() -> list[SourceRecord]:
    return read_jsonl(current_paths().sources_jsonl, SourceRecord)


def save_sources(records: list[SourceRecord]) -> None:
    write_jsonl(current_paths().sources_jsonl, records)


def load_ranges() -> list[SourceRangeRecord]:
    return read_jsonl(current_paths().ranges_jsonl, SourceRangeRecord)


def save_ranges(records: list[SourceRangeRecord]) -> None:
    write_jsonl(current_paths().ranges_jsonl, records)


def load_artifacts() -> list[ArtifactRecord]:
    return read_jsonl(current_paths().artifacts_jsonl, ArtifactRecord)


def save_artifacts(records: list[ArtifactRecord]) -> None:
    write_jsonl(current_paths().artifacts_jsonl, records)


def load_citation_edges() -> list[CitationEdgeRecord]:
    return read_jsonl(current_paths().citation_edges_jsonl, CitationEdgeRecord)


def save_citation_edges(records: list[CitationEdgeRecord]) -> None:
    write_jsonl(current_paths().citation_edges_jsonl, records)


def artifact_by_path(path: Path) -> ArtifactRecord | None:
    rel = repo_relative(path)
    for artifact in load_artifacts():
        if artifact.path == rel or Path(artifact.path).as_posix() == path.as_posix():
            return artifact
    return None


def path_lock_name(path: Path) -> str:
    digest = hashlib.sha256(path.as_posix().encode("utf-8")).hexdigest()[:16]
    return f"artifact-{digest}"


def json_dumps(data: Any) -> str:
    return orjson.dumps(data, option=orjson.OPT_INDENT_2).decode()


def parse_input_json(raw: str) -> dict[str, Any]:
    text = Path(raw[1:]).read_text(encoding="utf-8") if raw.startswith("@") else raw
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise KcError(
            code="KC_JSON_INVALID",
            message=f"Invalid JSON input: {exc}",
            details={"input": raw[:120]},
        ) from exc
    if not isinstance(value, dict):
        raise KcError(
            code="KC_EVENT_INVALID",
            message="Expected JSON object input.",
            details={"input_type": type(value).__name__},
        )
    return value
