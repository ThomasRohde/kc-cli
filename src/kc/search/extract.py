"""Deterministic local source extraction."""

from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from kc.fingerprints import normalize_text, text_hash
from kc.models.source_range import Locator, SourceRangeRecord

TEXT_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".rst",
    ".py",
    ".js",
    ".ts",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
}


def guess_media_type(path: Path) -> str:
    guessed, _encoding = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return "text/plain"
    return "application/octet-stream"


def is_text_like(path: Path, media_type: str) -> bool:
    return media_type.startswith("text/") or path.suffix.lower() in TEXT_EXTENSIONS


def extract_ranges(path: Path, source_id: str, source_fingerprint: str) -> list[SourceRangeRecord]:
    media_type = guess_media_type(path)
    if path.suffix.lower() == ".json":
        try:
            return _extract_structured_ranges(
                json.loads(path.read_text(encoding="utf-8-sig")),
                source_id,
                source_fingerprint,
            )
        except Exception:
            return _extract_text_ranges(path, source_id, source_fingerprint)
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            return _extract_structured_ranges(
                yaml.safe_load(path.read_text(encoding="utf-8-sig")),
                source_id,
                source_fingerprint,
            )
        except Exception:
            return _extract_text_ranges(path, source_id, source_fingerprint)
    if path.suffix.lower() == ".toml":
        try:
            return _extract_structured_ranges(
                tomllib.loads(path.read_text(encoding="utf-8-sig")),
                source_id,
                source_fingerprint,
            )
        except Exception:
            return _extract_text_ranges(path, source_id, source_fingerprint)
    if path.suffix.lower() == ".csv":
        try:
            return _extract_csv_ranges(path, source_id, source_fingerprint)
        except Exception:
            return _extract_text_ranges(path, source_id, source_fingerprint)
    if not is_text_like(path, media_type):
        return []
    return _extract_text_ranges(path, source_id, source_fingerprint)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def _range_id(source_id: str, locator: Locator) -> str:
    digest = hashlib.sha256(
        f"{source_id}:{locator.model_dump_json(exclude_none=True)}".encode()
    ).hexdigest()
    return f"rng_{digest[:26].upper()}"


def _extract_text_ranges(
    path: Path, source_id: str, source_fingerprint: str
) -> list[SourceRangeRecord]:
    text = normalize_text(path.read_text(encoding="utf-8-sig"))
    lines = text.split("\n")
    chunks: list[tuple[int, int, list[str]]] = []
    current_start: int | None = None
    current_lines: list[str] = []
    heading_path: list[str] = []
    current_heading: list[str] = []

    def flush(end_line: int) -> None:
        nonlocal current_start, current_lines, current_heading
        if current_start is None:
            return
        content = "\n".join(current_lines).strip()
        if content:
            chunks.append((current_start, end_line, list(current_heading)))
        current_start = None
        current_lines = []

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip()
        if path.suffix.lower() in {".md", ".markdown"} and line.startswith("#"):
            flush(idx - 1)
            depth = len(line) - len(line.lstrip("#"))
            title = line.lstrip("#").strip()
            if title:
                heading_path = [*heading_path[: max(depth - 1, 0)], title]
            current_heading = list(heading_path)
            current_start = idx
            current_lines = [raw_line]
            continue

        if not line.strip():
            flush(idx - 1)
            continue

        if current_start is None:
            current_start = idx
            current_heading = list(heading_path)
            current_lines = []
        current_lines.append(raw_line)

        if len(current_lines) >= 24:
            flush(idx)

    flush(len(lines))

    if not chunks and text.strip():
        chunks = [(1, len(lines), [])]

    extracted_at = _now()
    records: list[SourceRangeRecord] = []
    for start_line, end_line, headings in chunks:
        excerpt = "\n".join(lines[start_line - 1 : end_line]).strip()
        if not excerpt:
            continue
        locator = Locator(kind="line_range", start_line=start_line, end_line=end_line)
        records.append(
            SourceRangeRecord(
                range_id=_range_id(source_id, locator),
                source_id=source_id,
                source_fingerprint=source_fingerprint,
                locator=locator,
                text_hash=text_hash(excerpt),
                excerpt=excerpt,
                tokens_estimate=_estimate_tokens(excerpt),
                extracted_at=extracted_at,
                metadata={"heading_path": headings},
            )
        )
    return records


def _extract_structured_ranges(
    data: Any, source_id: str, source_fingerprint: str
) -> list[SourceRangeRecord]:
    records: list[SourceRangeRecord] = []
    extracted_at = _now()

    def visit(value: Any, pointer: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                visit(child, f"{pointer}/{escaped}")
        elif isinstance(value, list):
            for idx, child in enumerate(value):
                visit(child, f"{pointer}/{idx}")
        else:
            excerpt = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
            excerpt = excerpt.strip()
            if not excerpt:
                return
            locator = Locator(kind="json_pointer", pointer=pointer or "/")
            records.append(
                SourceRangeRecord(
                    range_id=_range_id(source_id, locator),
                    source_id=source_id,
                    source_fingerprint=source_fingerprint,
                    locator=locator,
                    text_hash=text_hash(excerpt),
                    excerpt=excerpt,
                    tokens_estimate=_estimate_tokens(excerpt),
                    extracted_at=extracted_at,
                    metadata={"heading_path": [pointer or "/"]},
                )
            )

    visit(data, "")
    return records


def _extract_csv_ranges(
    path: Path, source_id: str, source_fingerprint: str
) -> list[SourceRangeRecord]:
    text = path.read_text(encoding="utf-8-sig")
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        return []
    header = [cell.strip() for cell in rows[0]]
    records: list[SourceRangeRecord] = []
    extracted_at = _now()
    for row_index, row in enumerate(rows[1:], start=2):
        values = {
            header[index] if index < len(header) and header[index] else f"column_{index + 1}": value
            for index, value in enumerate(row)
        }
        excerpt = json.dumps(values, ensure_ascii=False, sort_keys=True)
        locator = Locator(kind="csv_row_range", start_row=row_index, end_row=row_index)
        records.append(
            SourceRangeRecord(
                range_id=_range_id(source_id, locator),
                source_id=source_id,
                source_fingerprint=source_fingerprint,
                locator=locator,
                text_hash=text_hash(excerpt),
                excerpt=excerpt,
                tokens_estimate=_estimate_tokens(excerpt),
                extracted_at=extracted_at,
                metadata={"heading_path": ["csv", f"row {row_index}"]},
            )
        )
    return records
