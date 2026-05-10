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
    assert result.exit_code == 40
    payload = parse(result.output)
    assert payload["ok"] is True
    assert payload["command"] == "task.start"
    task_id = payload["result"]["task"]["task_id"]
    status = runner.invoke(app, ["task", "status", "--task-id", task_id])
    assert status.exit_code == 0
    assert parse(status.output)["result"]["status"] == "awaiting_agent"


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
