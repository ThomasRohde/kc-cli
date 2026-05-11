from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from kc.models.source_range import Locator


class ArtifactLocator(BaseModel):
    kind: Literal["line_range"] = "line_range"
    start_line: int
    end_line: int


class CitationEdgeRecord(BaseModel):
    schema_version: Literal["kc.citation_edge.v1"] = "kc.citation_edge.v1"
    edge_id: str
    artifact_id: str | None = None
    artifact_path: str
    artifact_locator: ArtifactLocator
    citation_token: str
    source_id: str
    range_id: str | None = None
    source_fingerprint_at_validation: str | None = None
    validated_at: str
    status: Literal[
        "valid",
        "missing_source",
        "missing_range",
        "stale_source",
        "locator_mismatch",
        "invalid_token",
    ] = "valid"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedCitation(BaseModel):
    token: str
    source_id: str
    kind: Literal["line_range", "json_pointer", "csv_row_range"]
    line: int
    start_line: int | None = None
    end_line: int | None = None
    pointer: str | None = None
    start_row: int | None = None
    end_row: int | None = None

    @property
    def locator(self) -> Locator:
        return Locator(
            kind=self.kind,
            start_line=self.start_line,
            end_line=self.end_line,
            pointer=self.pointer,
            start_row=self.start_row,
            end_row=self.end_row,
        )
