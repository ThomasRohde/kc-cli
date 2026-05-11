from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from kc.cli import app

runner = CliRunner()


def parse(output: str) -> dict:
    return json.loads(output)


def test_task_start_returns_waiting_envelope(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "--yes"]).exit_code == 0
    source = tmp_path / "policy.md"
    source.write_text("Ownership rules mention owners and lifecycle.\n", encoding="utf-8")
    assert runner.invoke(app, ["source", "add", "policy.md", "--yes"]).exit_code == 0
    result = runner.invoke(
        app,
        [
            "task",
            "start",
            "--goal",
            "Create ownership page",
            "--target",
            "knowledge/wiki/ownership.md",
        ],
    )
    assert result.exit_code == 0
    payload = parse(result.output)
    assert payload["ok"] is True
    assert payload["command"] == "task.start"
    task_id = payload["result"]["task"]["task_id"]
    status = runner.invoke(app, ["task", "status", "--task-id", task_id])
    assert status.exit_code == 0
    assert parse(status.output)["result"]["status"] == "awaiting_agent"


def test_task_resume_enforces_expected_event_schema(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "--yes"]).exit_code == 0
    start = runner.invoke(app, ["task", "start", "--goal", "Create ownership page"])
    assert start.exit_code == 0
    task_id = parse(start.output)["result"]["task"]["task_id"]

    result = runner.invoke(
        app,
        [
            "task",
            "resume",
            "--task-id",
            task_id,
            "--event",
            "artifact_created",
            "--input",
            "{}",
        ],
    )
    assert result.exit_code == 10
    payload = parse(result.output)
    assert payload["errors"][0]["code"] == "KC_EVENT_INVALID"
    assert payload["errors"][0]["details"]["missing"] == ["path"]


def test_task_start_wait_exit_code_is_opt_in(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "--yes"]).exit_code == 0
    config = tmp_path / "kc.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "enable_wait_exit_code = false",
            "enable_wait_exit_code = true",
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["task", "start", "--goal", "Create ownership page"])
    assert result.exit_code == 40
    assert parse(result.output)["ok"] is True


def test_core_has_no_llm_provider_dependencies() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").lower()
    banned = [
        "openai",
        "anthropic",
        "langchain",
        "llamaindex",
        "llama-index",
        "google-generativeai",
    ]
    assert not any(dep in pyproject for dep in banned)
