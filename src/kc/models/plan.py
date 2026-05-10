from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PlanOperation(BaseModel):
    op_id: str
    kind: str
    path: str
    before_fingerprint: str | None = None
    after_fingerprint: str | None = None
    risk: Literal["low", "medium", "high"] = "medium"
    diff_path: str | None = None
    requires_yes: bool = True
    details: dict[str, Any] = Field(default_factory=dict)


class PlanCondition(BaseModel):
    kind: str
    path: str | None = None
    expected: str | None = None


class PlanRecord(BaseModel):
    schema_version: Literal["kc.plan.v1"] = "kc.plan.v1"
    plan_id: str
    created_at: str
    command: str
    mode: Literal["dry_run", "apply"] = "dry_run"
    idempotency_key: str | None = None
    operations: list[PlanOperation] = Field(default_factory=list)
    preconditions: list[PlanCondition] = Field(default_factory=list)
    postconditions: list[PlanCondition] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
