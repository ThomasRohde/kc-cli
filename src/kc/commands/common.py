from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from kc.errors import KcError
from kc.fingerprints import raw_fingerprint
from kc.models.artifact import ArtifactRecord
from kc.models.citation import CitationEdgeRecord
from kc.models.source import SourceRecord
from kc.models.source_range import SourceRangeRecord
from kc.models.source_revision import SourceRevisionRecord
from kc.output import emit_error, emit_unexpected, state
from kc.paths import current_paths, ensure_data_dir_exists, repo_relative, resolve_repo_path
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


def validate_choice(
    value: str | None,
    *,
    option: str,
    supported: set[str],
    allow_none: bool = False,
    code: str = "KC_VALIDATION_INVALID_ARGUMENT",
) -> str | None:
    if value is None and allow_none:
        return None
    if value not in supported:
        raise KcError(
            code=code,
            message=f"Invalid {option}: {value}",
            details={"option": option, "value": value, "supported": sorted(supported)},
        )
    return value


def validate_positive_int(value: int, *, option: str) -> int:
    if value < 1:
        raise KcError(
            code="KC_VALIDATION_INVALID_ARGUMENT",
            message=f"{option} must be a positive integer.",
            details={"option": option, "value": value},
        )
    return value


def parse_named_ints(
    raw: str | None,
    *,
    option: str,
    defaults: dict[str, int],
) -> dict[str, int]:
    if raw is None:
        return dict(defaults)
    if not raw.strip():
        raise KcError(
            code="KC_CONFIG_INVALID",
            message=f"{option} must use key=value entries.",
            details={"option": option, "value": raw, "supported_keys": sorted(defaults)},
        )
    parsed = dict(defaults)
    seen: set[str] = set()
    for part in raw.split(","):
        item = part.strip()
        if not item or "=" not in item:
            raise KcError(
                code="KC_CONFIG_INVALID",
                message=f"Malformed {option} entry: {part}",
                details={"option": option, "value": raw, "supported_keys": sorted(defaults)},
            )
        key, value = item.split("=", 1)
        key = key.strip()
        if key not in parsed:
            raise KcError(
                code="KC_CONFIG_INVALID",
                message=f"Unknown {option} key: {key}",
                details={"option": option, "key": key, "supported_keys": sorted(defaults)},
            )
        if key in seen:
            raise KcError(
                code="KC_CONFIG_INVALID",
                message=f"Duplicate {option} key: {key}",
                details={"option": option, "key": key},
            )
        seen.add(key)
        try:
            parsed[key] = int(value.strip())
        except ValueError as exc:
            raise KcError(
                code="KC_CONFIG_INVALID",
                message=f"Invalid {option} value: {item}",
                details={"option": option, "value": raw, "key": key},
            ) from exc
    for key, value in parsed.items():
        if value < 1:
            raise KcError(
                code="KC_CONFIG_INVALID",
                message=f"{option} values must be positive: {key}={value}",
                details={"option": option, "value": raw, "key": key, "parsed_value": value},
            )
    return parsed


def parse_checks(raw: str, *, allowed: set[str], all_checks: set[str]) -> set[str]:
    parts = {part.strip() for part in raw.split(",") if part.strip()}
    if not parts:
        raise KcError(
            code="KC_VALIDATION_INVALID_ARGUMENT",
            message="--checks must include at least one check name.",
            details={"option": "--checks", "supported": sorted({*allowed, "all"})},
        )
    unknown = sorted(parts - allowed - {"all"})
    if unknown:
        raise KcError(
            code="KC_VALIDATION_INVALID_ARGUMENT",
            message=f"Unknown lint check: {unknown[0]}",
            details={"option": "--checks", "unknown": unknown, "supported": sorted({*allowed, "all"})},
        )
    if "all" in parts:
        return set(all_checks)
    return parts


def load_sources() -> list[SourceRecord]:
    ensure_data_dir_exists()
    return read_jsonl(current_paths().sources_jsonl, SourceRecord)


def save_sources(records: list[SourceRecord]) -> None:
    write_jsonl(current_paths().sources_jsonl, records)


def load_ranges() -> list[SourceRangeRecord]:
    ensure_data_dir_exists()
    return read_jsonl(current_paths().ranges_jsonl, SourceRangeRecord)


def save_ranges(records: list[SourceRangeRecord]) -> None:
    write_jsonl(current_paths().ranges_jsonl, records)


def load_source_revisions() -> list[SourceRevisionRecord]:
    ensure_data_dir_exists()
    return read_jsonl(current_paths().source_revisions_jsonl, SourceRevisionRecord)


def save_source_revisions(records: list[SourceRevisionRecord]) -> None:
    write_jsonl(current_paths().source_revisions_jsonl, records)


def load_artifacts() -> list[ArtifactRecord]:
    ensure_data_dir_exists()
    return read_jsonl(current_paths().artifacts_jsonl, ArtifactRecord)


def save_artifacts(records: list[ArtifactRecord]) -> None:
    write_jsonl(current_paths().artifacts_jsonl, records)


def load_citation_edges() -> list[CitationEdgeRecord]:
    ensure_data_dir_exists()
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
    if raw.startswith("@"):
        input_path = Path(raw[1:])
        if not input_path.exists():
            raise KcError(
                code="KC_FILE_NOT_FOUND",
                message=f"Input file not found: {raw[1:]}",
                details={"path": input_path.as_posix()},
            )
        text = input_path.read_text(encoding="utf-8")
    else:
        text = raw
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


def validate_payload_schema(payload: dict[str, Any], schema: dict[str, Any] | None) -> None:
    if not schema:
        return
    if schema.get("type") == "object" and not isinstance(payload, dict):
        raise KcError(
            code="KC_EVENT_INVALID",
            message="Event input must be a JSON object.",
            details={"expected": "object", "actual": type(payload).__name__},
        )
    required = schema.get("required", [])
    if isinstance(required, list):
        missing = [str(key) for key in required if key not in payload]
        if missing:
            raise KcError(
                code="KC_EVENT_INVALID",
                message="Event input is missing required properties.",
                details={"missing": missing, "schema": schema},
            )
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    for key, definition in properties.items():
        if key not in payload or not isinstance(definition, dict):
            continue
        raw_expected = definition.get("type")
        if not isinstance(raw_expected, str):
            continue
        expected = raw_expected
        expected_type = type_map.get(expected)
        if expected_type is None:
            continue
        if expected == "integer":
            valid = isinstance(payload[key], int) and not isinstance(payload[key], bool)
        elif expected == "number":
            valid = isinstance(payload[key], int | float) and not isinstance(payload[key], bool)
        elif expected == "boolean":
            valid = isinstance(payload[key], bool)
        else:
            valid = isinstance(payload[key], expected_type)
        if not valid:
            raise KcError(
                code="KC_EVENT_INVALID",
                message=f"Event input property has invalid type: {key}",
                details={
                    "property": key,
                    "expected": expected,
                    "actual": type(payload[key]).__name__,
                    "schema": schema,
                },
            )


def stale_source_warnings(
    results: list[dict[str, Any]],
    sources: list[SourceRecord] | None = None,
) -> list[dict[str, Any]]:
    if not results:
        return []
    sources_by_id = {source.source_id: source for source in (sources or load_sources())}
    stale: list[dict[str, Any]] = []
    current_by_source: dict[str, str | None] = {}
    for source_id in sorted({str(item.get("source_id", "")) for item in results if item.get("source_id")}):
        source = sources_by_id.get(source_id)
        if source is None:
            continue
        original = source.metadata.get("original_path")
        current_fingerprint = None
        if isinstance(original, str):
            path = resolve_repo_path(original)
            current_fingerprint = raw_fingerprint(path) if path.exists() else None
        current_by_source[source_id] = current_fingerprint
        if current_fingerprint != source.fingerprint:
            stale.append(
                {
                    "source_id": source_id,
                    "uri": source.uri,
                    "registered_fingerprint": source.fingerprint,
                    "current_fingerprint": current_fingerprint,
                }
            )
    for item in results:
        source_id = str(item.get("source_id", ""))
        if source_id in current_by_source:
            item["current_source_fingerprint"] = current_by_source[source_id]
    if not stale:
        return []
    return [
        {
            "code": "KC_SOURCE_STALE",
            "message": "One or more returned source ranges come from stale registered sources.",
            "details": {"sources": stale},
        }
    ]
