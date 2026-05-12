from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ContextPackRecord(BaseModel):
    schema_version: Literal["kc.context_pack.v1"] = "kc.context_pack.v1"
    context_id: str
    created_at: str
    ask: str
    shape: str = "knowledge_page"
    target: str | None = None
    grounding_policy: str = "required"
    workspace: dict[str, Any] = Field(default_factory=dict)
    candidate_ranges: list[dict[str, Any]] = Field(default_factory=list)
    existing_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    citation_policy: dict[str, Any] = Field(default_factory=dict)
    artifact_policy: dict[str, Any] = Field(default_factory=dict)
    agent_instructions: list[str] = Field(default_factory=list)
    next_commands: list[str] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
