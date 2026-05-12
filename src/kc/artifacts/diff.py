"""Structured artifact diff planning."""

from __future__ import annotations

import difflib
from datetime import UTC, datetime
from pathlib import Path

from kc.fingerprints import raw_fingerprint
from kc.ids import new_id
from kc.models.plan import PlanCondition, PlanOperation, PlanRecord


def build_artifact_plan(
    path: Path,
    *,
    registered_fingerprint: str | None,
    baseline_path: Path | None = None,
    mode: str = "dry_run",
    idempotency_key: str | None = None,
) -> tuple[PlanRecord, str, dict[str, str | None]]:
    after = raw_fingerprint(path) if path.exists() else None
    before = registered_fingerprint
    baseline: dict[str, str | None] = {"kind": "unavailable", "path": None, "fingerprint": before}
    old_lines: list[str] = []
    if baseline_path is not None and baseline_path.exists():
        old_lines = baseline_path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
        baseline = {
            "kind": "last_applied_snapshot",
            "path": baseline_path.as_posix(),
            "fingerprint": raw_fingerprint(baseline_path),
        }
    new_lines = (
        path.read_text(encoding="utf-8-sig").splitlines(keepends=True) if path.exists() else []
    )
    if before is None:
        risk_flags = ["new_artifact"]
        old_label = "/dev/null"
    else:
        risk_flags = ["updates_existing_artifact"] if before != after else []
        old_label = baseline_path.as_posix() if baseline_path is not None and baseline_path.exists() else f"{path.as_posix()}@registry"
    diff_text = "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_label,
            tofile=path.as_posix(),
        )
    )
    risk = "medium" if risk_flags else "low"
    plan = PlanRecord(
        plan_id=new_id("plan"),
        created_at=datetime.now(UTC).isoformat(),
        command="artifact.apply",
        mode=mode,  # type: ignore[arg-type]
        idempotency_key=idempotency_key,
        operations=[
            PlanOperation(
                op_id="op_01",
                kind="register_artifact",
                path=path.as_posix(),
                before_fingerprint=before,
                after_fingerprint=after,
                risk=risk,  # type: ignore[arg-type]
                requires_yes=True,
            )
        ],
        preconditions=[
            PlanCondition(kind="file_exists", path=path.as_posix(), expected="true"),
        ],
        postconditions=[
            PlanCondition(kind="artifact_validates", path=path.as_posix()),
        ],
        risk_flags=risk_flags,
    )
    return plan, diff_text, baseline
