"""Citation token parsing and validation."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kc.ids import new_id
from kc.models.citation import ArtifactLocator, CitationEdgeRecord, ParsedCitation
from kc.models.source import SourceRecord
from kc.models.source_range import SourceRangeRecord
from kc.store.jsonl import read_jsonl

CITATION_RE = re.compile(r"\[kc:(?P<source>src_[A-Za-z0-9_]+):L(?P<start>\d+)-L(?P<end>\d+)\]")
MARKER_RE = re.compile(r"\[kc:(inference|todo|uncited)\]")


def parse_markdown_citations(text: str) -> list[ParsedCitation]:
    parsed: list[ParsedCitation] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in CITATION_RE.finditer(line):
            parsed.append(
                ParsedCitation(
                    token=match.group(0),
                    source_id=match.group("source"),
                    start_line=int(match.group("start")),
                    end_line=int(match.group("end")),
                    line=line_no,
                )
            )
    return parsed


def has_citation_or_marker(text: str) -> bool:
    return bool(CITATION_RE.search(text) or MARKER_RE.search(text))


def find_range_for_token(
    citation: ParsedCitation,
    ranges: list[SourceRangeRecord],
) -> SourceRangeRecord | None:
    for candidate in ranges:
        loc = candidate.locator
        if (
            candidate.source_id == citation.source_id
            and loc.kind == "line_range"
            and loc.start_line == citation.start_line
            and loc.end_line == citation.end_line
        ):
            return candidate
    return None


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
    problems: list[dict[str, Any]] = []
    timestamp = datetime.now(UTC).isoformat()
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
