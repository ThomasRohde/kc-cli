from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceRevisionRecord(BaseModel):
    schema_version: Literal["kc.source_revision.v1"] = "kc.source_revision.v1"
    revision_id: str
    source_id: str
    uri: str
    raw_fingerprint: str
    normalized_fingerprint: str
    media_type: str
    extracted_at: str
    status: Literal["active", "superseded"] = "active"
    previous_revision_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
