from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskRecord(BaseModel):
    schema_version: Literal["kc.task.v1"] = "kc.task.v1"
    task_id: str
    goal: str
    status: Literal[
        "created",
        "awaiting_agent",
        "awaiting_validation",
        "awaiting_apply",
        "completed",
        "blocked",
        "cancelled",
        "failed",
    ] = "awaiting_agent"
    context_pack_id: str | None = None
    context_pack_path: str | None = None
    created_at: str
    updated_at: str
    shape: str = "knowledge_page"
    domain: list[str] = Field(default_factory=list)
    candidate_sources: list[str] = Field(default_factory=list)
    candidate_ranges: list[str] = Field(default_factory=list)
    target_artifacts: list[str] = Field(default_factory=list)
    agent_instructions: list[str] = Field(default_factory=list)
    next_commands: list[str] = Field(default_factory=list)
    expected_event_name: str | None = None
    expected_event_schema: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
