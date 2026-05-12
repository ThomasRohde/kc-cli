from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Locator(BaseModel):
    kind: Literal["line_range", "json_pointer", "csv_row_range", "page_text_range"] = "line_range"
    start_line: int | None = None
    end_line: int | None = None
    pointer: str | None = None
    start_row: int | None = None
    end_row: int | None = None


class SourceRangeRecord(BaseModel):
    schema_version: Literal["kc.source_range.v1"] = "kc.source_range.v1"
    range_id: str
    source_id: str
    revision_id: str | None = None
    source_fingerprint: str
    locator: Locator
    text_hash: str
    excerpt: str
    tokens_estimate: int = 0
    extracted_at: str
    status: Literal["active", "superseded"] = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
