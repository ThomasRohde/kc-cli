from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    source_id: str
    range_ids: list[str] = Field(default_factory=list)


class ArtifactRecord(BaseModel):
    schema_version: Literal["kc.artifact.v1"] = "kc.artifact.v1"
    artifact_id: str
    path: str
    artifact_type: Literal[
        "knowledge_page",
        "glossary",
        "decision_note",
        "source_index",
        "log_entry",
        "eval_pack",
    ] = "knowledge_page"
    title: str
    status: Literal["draft", "active", "deprecated", "superseded"] = "draft"
    domain: list[str] = Field(default_factory=list)
    fingerprint: str
    created_at: str
    updated_at: str
    last_validated_at: str | None = None
    validation_status: Literal["passed", "failed", "unknown"] = "unknown"
    source_refs: list[SourceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
