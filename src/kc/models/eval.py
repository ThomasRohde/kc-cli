from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvalCase(BaseModel):
    id: str
    query: str
    domain: str | None = None
    limit: int = 10
    expected_source_ids: list[str] = Field(default_factory=list)
    expected_range_ids: list[str] = Field(default_factory=list)
    must_include_citation_tokens: list[str] = Field(default_factory=list)
    min_recall_at_k: float = 1.0


class EvalPack(BaseModel):
    schema_version: Literal["kc.eval_pack.v1"] = "kc.eval_pack.v1"
    cases: list[EvalCase] = Field(default_factory=list)
