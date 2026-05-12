from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from kc.cli import app

runner = CliRunner()


def parse(output: str) -> dict:
    return json.loads(output)


def setup_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "--yes"]).exit_code == 0
    source = tmp_path / "policy.md"
    source.write_text("Ownership rules define lifecycle responsibilities.\n", encoding="utf-8")
    assert runner.invoke(app, ["source", "add", "policy.md", "--domain", "bcm", "--yes"]).exit_code == 0


def test_context_prepare_out_writes_context_pack(tmp_path: Path, monkeypatch) -> None:
    setup_repo(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "context",
            "prepare",
            "--ask",
            "Create ownership notes",
            "--target",
            "knowledge/wiki/ownership.md",
            "--out",
            ".kc/context/ownership.json",
        ],
    )

    assert result.exit_code == 0
    payload = parse(result.output)
    pack_path = tmp_path / ".kc" / "context" / "ownership.json"
    assert pack_path.exists()
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    assert pack["schema_version"] == "kc.context_pack.v1"
    assert pack["context_id"] == payload["result"]["context_pack"]["context_id"]
    assert pack["target"] == "knowledge/wiki/ownership.md"
    assert pack["candidate_ranges"]


def test_task_next_and_resume_state_machine(tmp_path: Path, monkeypatch) -> None:
    setup_repo(tmp_path, monkeypatch)
    start = runner.invoke(
        app,
        ["task", "start", "--goal", "Create ownership notes", "--target", "knowledge/wiki/ownership.md"],
    )
    assert start.exit_code == 0
    task_id = parse(start.output)["result"]["task"]["task_id"]

    next_result = runner.invoke(app, ["task", "next", "--task-id", task_id])
    assert next_result.exit_code == 0
    assert parse(next_result.output)["result"]["status"] == "awaiting_agent"

    created = runner.invoke(
        app,
        [
            "task",
            "resume",
            "--task-id",
            task_id,
            "--event",
            "artifact_created",
            "--input",
            '{"path":"knowledge/wiki/ownership.md"}',
        ],
    )
    assert created.exit_code == 0
    assert parse(created.output)["result"]["task"]["status"] == "awaiting_validation"

    wrong = runner.invoke(
        app,
        [
            "task",
            "resume",
            "--task-id",
            task_id,
            "--event",
            "artifact_applied",
            "--input",
            '{"path":"knowledge/wiki/ownership.md"}',
        ],
    )
    assert wrong.exit_code == 10
    assert parse(wrong.output)["errors"][0]["code"] == "KC_EVENT_INVALID"
