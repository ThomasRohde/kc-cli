from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Authority(BaseModel):
    level: Literal["unknown", "informal", "team-approved", "enterprise-approved", "regulatory"] = (
        "unknown"
    )
    owner: str | None = None
    review_date: str | None = None
    notes: str = "Do not infer authority from file location."


class SourceRecord(BaseModel):
    schema_version: Literal["kc.source.v1"] = "kc.source.v1"
    source_id: str
    uri: str
    display_name: str
    media_type: str = "text/plain"
    fingerprint: str
    raw_fingerprint: str | None = None
    normalized_fingerprint: str | None = None
    fingerprint_algorithm: str = "sha256-normalized-v1"
    registered_at: str
    registered_by: str = "agent-or-human"
    status: Literal["active", "stale", "superseded", "missing", "excluded"] = "active"
    immutability: Literal["fingerprinted", "external", "copied"] = "fingerprinted"
    domain: list[str] = Field(default_factory=list)
    authority: Authority = Field(default_factory=Authority)
    metadata: dict[str, Any] = Field(default_factory=dict)
