"""Deterministic local source extraction."""

from __future__ import annotations

import json
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kc.fingerprints import normalize_text, text_hash
from kc.ids import new_id
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
            return _extract_json_ranges(path, source_id, source_fingerprint)
        except Exception:
            return _extract_text_ranges(path, source_id, source_fingerprint)
    if not is_text_like(path, media_type):
        return []
    return _extract_text_ranges(path, source_id, source_fingerprint)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


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
        records.append(
            SourceRangeRecord(
                range_id=new_id("rng"),
                source_id=source_id,
                source_fingerprint=source_fingerprint,
                locator=Locator(kind="line_range", start_line=start_line, end_line=end_line),
                text_hash=text_hash(excerpt),
                excerpt=excerpt,
                tokens_estimate=_estimate_tokens(excerpt),
                extracted_at=extracted_at,
                metadata={"heading_path": headings},
            )
        )
    return records


def _extract_json_ranges(
    path: Path, source_id: str, source_fingerprint: str
) -> list[SourceRangeRecord]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
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
            excerpt = str(value).strip()
            if not excerpt:
                return
            records.append(
                SourceRangeRecord(
                    range_id=new_id("rng"),
                    source_id=source_id,
                    source_fingerprint=source_fingerprint,
                    locator=Locator(kind="json_pointer", pointer=pointer or "/"),
                    text_hash=text_hash(excerpt),
                    excerpt=excerpt,
                    tokens_estimate=_estimate_tokens(excerpt),
                    extracted_at=extracted_at,
                    metadata={"heading_path": [pointer or "/"]},
                )
            )

    visit(data, "")
    return records
