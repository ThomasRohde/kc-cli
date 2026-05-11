"""Citation token parsing and validation."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from kc.fingerprints import raw_fingerprint
from kc.ids import new_id
from kc.models.citation import ArtifactLocator, CitationEdgeRecord, ParsedCitation
from kc.models.source import SourceRecord
from kc.models.source_range import SourceRangeRecord
from kc.store.jsonl import read_jsonl

CITATION_RE = re.compile(
    r"\[kc:(?P<source>src_[A-Za-z0-9_]+):"
    r"(?:(?:L(?P<line_start>\d+)-L(?P<line_end>\d+))|"
    r"(?:JP:(?P<pointer>[^\]]+))|"
    r"(?:CSV:R(?P<row_start>\d+)-R(?P<row_end>\d+)))\]"
)
KC_TOKEN_RE = re.compile(r"\[kc:[^\]]+\]")
MARKER_RE = re.compile(r"\[kc:(inference|todo|uncited)\]")


def parse_markdown_citations(text: str) -> list[ParsedCitation]:
    parsed: list[ParsedCitation] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in CITATION_RE.finditer(line):
            if match.group("line_start") is not None:
                parsed.append(
                    ParsedCitation(
                        token=match.group(0),
                        source_id=match.group("source"),
                        kind="line_range",
                        start_line=int(match.group("line_start")),
                        end_line=int(match.group("line_end")),
                        line=line_no,
                    )
                )
                continue
            if match.group("pointer") is not None:
                parsed.append(
                    ParsedCitation(
                        token=match.group(0),
                        source_id=match.group("source"),
                        kind="json_pointer",
                        pointer=unquote(match.group("pointer")),
                        line=line_no,
                    )
                )
                continue
            parsed.append(
                ParsedCitation(
                    token=match.group(0),
                    source_id=match.group("source"),
                    kind="csv_row_range",
                    start_row=int(match.group("row_start")),
                    end_row=int(match.group("row_end")),
                    line=line_no,
                )
            )
    return parsed


def invalid_markdown_citation_tokens(text: str) -> list[dict[str, Any]]:
    invalid: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in KC_TOKEN_RE.finditer(line):
            token = match.group(0)
            if MARKER_RE.fullmatch(token) or CITATION_RE.fullmatch(token):
                continue
            invalid.append(
                {
                    "code": "KC_CITATION_INVALID_TOKEN",
                    "message": f"Invalid kc citation token: {token}",
                    "line": line_no,
                    "token": token,
                }
            )
    return invalid


def has_citation_or_marker(text: str) -> bool:
    return bool(CITATION_RE.search(text) or MARKER_RE.search(text))


def find_range_for_token(
    citation: ParsedCitation,
    ranges: list[SourceRangeRecord],
) -> SourceRangeRecord | None:
    for candidate in ranges:
        loc = candidate.locator
        if candidate.source_id != citation.source_id or loc.kind != citation.kind:
            continue
        if citation.kind == "line_range" and loc.start_line == citation.start_line and loc.end_line == citation.end_line:
            return candidate
        if citation.kind == "json_pointer" and loc.pointer == citation.pointer:
            return candidate
        if citation.kind == "csv_row_range" and loc.start_row == citation.start_row and loc.end_row == citation.end_row:
            return candidate
    return None


def _current_source_fingerprint(source: SourceRecord) -> str | None:
    original = source.metadata.get("original_path")
    if not isinstance(original, str):
        return None
    path = Path.cwd() / original
    if not path.exists():
        return None
    return raw_fingerprint(path)


def validate_citations(
    artifact_path: str,
    artifact_text: str,
    *,
    sources_path: Path,
    ranges_path: Path,
    artifact_id: str | None = None,
) -> tuple[list[CitationEdgeRecord], list[dict[str, Any]]]:
    sources = read_jsonl(sources_path, SourceRecord)
    ranges = read_jsonl(ranges_path, SourceRangeRecord)
    source_by_id = {s.source_id: s for s in sources}
    parsed = parse_markdown_citations(artifact_text)
    edges: list[CitationEdgeRecord] = []
    problems: list[dict[str, Any]] = invalid_markdown_citation_tokens(artifact_text)
    timestamp = datetime.now(UTC).isoformat()
    for problem in problems:
        token = str(problem.get("token", ""))
        source_match = re.search(r"\[kc:(src_[A-Za-z0-9_]+)", token)
        edges.append(
            CitationEdgeRecord(
                edge_id=new_id("cite"),
                artifact_id=artifact_id,
                artifact_path=artifact_path,
                artifact_locator=ArtifactLocator(
                    start_line=int(problem.get("line", 1)),
                    end_line=int(problem.get("line", 1)),
                ),
                citation_token=token,
                source_id=source_match.group(1) if source_match else "",
                range_id=None,
                source_fingerprint_at_validation=None,
                validated_at=timestamp,
                status="invalid_token",
            )
        )
    for citation in parsed:
        source = source_by_id.get(citation.source_id)
        range_record = find_range_for_token(citation, ranges)
        status = "valid"
        if source is None:
            status = "missing_source"
            problems.append(
                {
                    "code": "KC_CITATION_SOURCE_MISSING",
                    "message": f"Citation source does not exist: {citation.source_id}",
                    "line": citation.line,
                    "token": citation.token,
                }
            )
        elif range_record is None:
            status = "missing_range"
            problems.append(
                {
                    "code": "KC_CITATION_RANGE_MISSING",
                    "message": f"Citation range does not exist: {citation.token}",
                    "line": citation.line,
                    "token": citation.token,
                }
            )
        elif range_record.source_fingerprint != source.fingerprint:
            status = "stale_source"
            problems.append(
                {
                    "code": "KC_CITATION_STALE_SOURCE",
                    "message": f"Citation points to stale source fingerprint: {citation.token}",
                    "line": citation.line,
                    "token": citation.token,
                }
            )
        else:
            current_fingerprint = _current_source_fingerprint(source)
            if current_fingerprint is not None and current_fingerprint != source.fingerprint:
                status = "stale_source"
                problems.append(
                    {
                        "code": "KC_CITATION_STALE_SOURCE",
                        "message": f"Citation source file fingerprint has changed: {citation.token}",
                        "line": citation.line,
                        "token": citation.token,
                        "source_id": source.source_id,
                        "registered_fingerprint": source.fingerprint,
                        "current_fingerprint": current_fingerprint,
                    }
                )
        edges.append(
            CitationEdgeRecord(
                edge_id=new_id("cite"),
                artifact_id=artifact_id,
                artifact_path=artifact_path,
                artifact_locator=ArtifactLocator(start_line=citation.line, end_line=citation.line),
                citation_token=citation.token,
                source_id=citation.source_id,
                range_id=range_record.range_id if range_record else None,
                source_fingerprint_at_validation=source.fingerprint if source else None,
                validated_at=timestamp,
                status=status,  # type: ignore[arg-type]
            )
        )
    return edges, problems
