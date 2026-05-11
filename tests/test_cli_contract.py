from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from kc.cli import app
from kc.commands.guide import build_guide
from kc.output import HUMAN_RENDERERS

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
    assert "source.refresh" in guide["commands"]
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
    assert payload["result"] is None
    assert payload["errors"][0]["code"] == "KC_UNSUPPORTED_FEATURE"


def test_json_failure_result_is_null(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "--yes"]).exit_code == 0
    result = runner.invoke(app, ["source", "inspect", "missing.md"])
    assert result.exit_code == 11
    payload = parse(result.output)
    assert_envelope(payload, ok=False, command="source.inspect")
    assert payload["result"] is None
    assert payload["errors"][0]["code"] == "KC_SOURCE_NOT_FOUND"


def test_guide_manifest_has_contract_fields_and_renderer_coverage() -> None:
    guide = build_guide()
    required = {
        "command_id",
        "mutates",
        "confirmation",
        "syntax",
        "important_options",
        "result_summary",
        "examples",
        "common_errors",
        "exit_codes",
    }
    commands = guide["commands"]
    assert set(commands) == set(HUMAN_RENDERERS)
    for command_id, contract in commands.items():
        assert required.issubset(contract)
        assert contract["command_id"] == command_id
        assert isinstance(contract["examples"], list) and contract["examples"]
        assert isinstance(contract["common_errors"], list)
        assert isinstance(contract["exit_codes"], list) and contract["exit_codes"]


def _init_repo_with_source(tmp_path: Path, monkeypatch) -> dict:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "--yes"]).exit_code == 0
    source = tmp_path / "policy.md"
    source.write_text(
        "# Ownership\n\nCapability owners maintain definitions and review lifecycle state.\n",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["source", "add", "policy.md", "--domain", "bcm", "--yes"]).exit_code == 0
    search = runner.invoke(app, ["source", "search", "owners lifecycle", "--domain", "bcm"])
    assert search.exit_code == 0
    return parse(search.output)["result"]["results"][0]


def _write_valid_artifact(tmp_path: Path, citation: str) -> Path:
    artifact = tmp_path / "knowledge" / "wiki" / "ownership.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        f"""---
schema_version: kc.knowledge_page.v1
artifact_id: art_contract
title: Ownership
status: draft
domain: [bcm]
artifact_type: knowledge_page
requires_citations: true
source_refs: []
last_validated_at: null
---
# Ownership

## Summary

Capability owners maintain definitions. {citation}

## Source-backed facts

- Owners review lifecycle state. {citation}

## Open questions

- [kc:todo] Confirm review cadence.
""",
        encoding="utf-8",
    )
    return artifact


def test_table_and_markdown_formats_cover_representative_commands(
    tmp_path: Path, monkeypatch
) -> None:
    hit = _init_repo_with_source(tmp_path, monkeypatch)
    artifact = _write_valid_artifact(tmp_path, hit["citation_token"])
    rel = str(artifact.relative_to(tmp_path))

    checks = [
        (["--format", "table", "guide"], "guide"),
        (["--format", "markdown", "lint"], "# lint"),
        (["--format", "table", "source", "search", "owners lifecycle"], "source.search"),
        (["--format", "table", "artifact", "validate", "--file", rel], "artifact.validate"),
        (["--format", "markdown", "artifact", "apply", "--file", rel, "--dry-run"], "# artifact.apply"),
        (["--format", "markdown", "doctor"], "# doctor"),
    ]
    for args, expected in checks:
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert expected in result.output
        assert not result.output.lstrip().startswith("{")


def test_task_status_has_table_format(tmp_path: Path, monkeypatch) -> None:
    _init_repo_with_source(tmp_path, monkeypatch)
    start = runner.invoke(app, ["task", "start", "--goal", "Create ownership page"])
    assert start.exit_code == 0
    task_id = parse(start.output)["result"]["task"]["task_id"]
    status = runner.invoke(app, ["--format", "table", "task", "status", "--task-id", task_id])
    assert status.exit_code == 0
    assert "task.status" in status.output
    assert task_id in status.output
    assert not status.output.lstrip().startswith("{")


def test_doctor_table_includes_full_health_fields(tmp_path: Path, monkeypatch) -> None:
    _init_repo_with_source(tmp_path, monkeypatch)
    result = runner.invoke(app, ["--format", "table", "doctor"])
    assert result.exit_code == 0
    assert "index_stale" in result.output
    assert "index_ranges" in result.output
    assert "sqlite_exists" in result.output
    assert "semantic_metadata_match" in result.output
    assert "semantic_index_ranges" in result.output
    assert "semantic_missing_vectors" in result.output
    assert "semantic_stale_vectors" in result.output


def test_human_format_errors_are_readable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "--yes"]).exit_code == 0
    result = runner.invoke(app, ["--format", "markdown", "source", "inspect", "missing.md"])
    assert result.exit_code == 11
    assert result.output.startswith("# Error: source.inspect")
    assert "KC_SOURCE_NOT_FOUND" in result.output
    assert not result.output.lstrip().startswith("{")


def test_llm_mode_forces_json_when_human_format_requested() -> None:
    result = runner.invoke(app, ["--format", "table", "guide"], env={"LLM": "true"})
    assert result.exit_code == 0
    payload = parse(result.output)
    assert_envelope(payload, ok=True, command="guide")


def test_help_outputs_include_command_explanations() -> None:
    root = runner.invoke(app, ["--help"])
    assert root.exit_code == 0
    assert "Emit the machine-readable kc playbook" in root.output
    assert "Run read-only CLI contract conformance checks" in root.output
    assert "Create the repo-local kc layout" in root.output
    assert "Run repository integrity checks" in root.output
    assert "Export registered knowledge" in root.output

    source = runner.invoke(app, ["source", "--help"])
    assert source.exit_code == 0
    assert "Register a local text/Markdown source" in source.output
    assert "Show source metadata" in source.output
    assert "Refresh a registered local source" in source.output
    assert "Search source ranges with BM25" in source.output

    artifact = runner.invoke(app, ["artifact", "--help"])
    assert artifact.exit_code == 0
    assert "Create a deterministic artifact skeleton" in artifact.output
    assert "Validate artifact schema" in artifact.output
    assert "Validate, lock, snapshot" in artifact.output


def test_context_budget_and_export_out_are_validated(tmp_path: Path, monkeypatch) -> None:
    _init_repo_with_source(tmp_path, monkeypatch)
    bad_budget = runner.invoke(
        app,
        [
            "context",
            "prepare",
            "--ask",
            "ownership",
            "--budget",
            "max_ranges=0",
        ],
    )
    assert bad_budget.exit_code == 10
    assert parse(bad_budget.output)["errors"][0]["code"] == "KC_CONFIG_INVALID"

    export = runner.invoke(app, ["export", "--format", "jsonl", "--out", "../outside.json"])
    assert export.exit_code == 10
    assert parse(export.output)["errors"][0]["code"] == "KC_PATH_OUTSIDE_REPO"
