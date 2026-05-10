from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from kc.cli import app

runner = CliRunner()


def parse(output: str) -> dict:
    return json.loads(output)


def assert_envelope(payload: dict, *, ok: bool, command: str) -> None:
    assert payload["schema_version"] == "kc.result.v1"
    assert payload["ok"] is ok
    assert payload["command"] == command
    assert "request_id" in payload
    assert "target" in payload
    assert "result" in payload
    assert isinstance(payload["warnings"], list)
    assert isinstance(payload["errors"], list)
    assert "duration_ms" in payload["metrics"]


def test_guide_returns_machine_readable_contract() -> None:
    result = runner.invoke(app, ["guide"])
    assert result.exit_code == 0
    payload = parse(result.output)
    assert_envelope(payload, ok=True, command="guide")
    guide = payload["result"]
    assert guide["capabilities"]["calls_llm"] is False
    assert "source.add" in guide["commands"]
    assert "KC_LOCK_HELD" in guide["error_codes"]


def test_init_dry_run_creates_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "--dry-run"])
    assert result.exit_code == 0
    payload = parse(result.output)
    assert_envelope(payload, ok=True, command="init")
    assert payload["result"]["dry_run"] is True
    assert not (tmp_path / "kc.toml").exists()
    assert not (tmp_path / "knowledge").exists()


def test_init_yes_creates_repo_layout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 0
    payload = parse(result.output)
    assert payload["result"]["dry_run"] is False
    assert (tmp_path / "kc.toml").exists()
    assert (tmp_path / "knowledge" / "sources.jsonl").exists()
    assert (tmp_path / ".kc" / "state.sqlite").exists()


def test_invalid_format_returns_structured_error() -> None:
    result = runner.invoke(app, ["--format", "xml", "guide"])
    assert result.exit_code == 80
    payload = parse(result.output)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "KC_UNSUPPORTED_FEATURE"


def test_help_outputs_include_command_explanations() -> None:
    root = runner.invoke(app, ["--help"])
    assert root.exit_code == 0
    assert "Emit the machine-readable kc playbook" in root.output
    assert "Create the repo-local kc layout" in root.output
    assert "Run repository integrity checks" in root.output
    assert "Export registered knowledge" in root.output

    source = runner.invoke(app, ["source", "--help"])
    assert source.exit_code == 0
    assert "Register a local text/Markdown source" in source.output
    assert "Show source metadata" in source.output
    assert "Search source ranges with BM25" in source.output

    artifact = runner.invoke(app, ["artifact", "--help"])
    assert artifact.exit_code == 0
    assert "Create a deterministic artifact skeleton" in artifact.output
    assert "Validate artifact schema" in artifact.output
    assert "Validate, lock, snapshot" in artifact.output
