from __future__ import annotations

import copy
import json
from pathlib import Path

from typer.testing import CliRunner

from kc.cli import app
from kc.commands import conformance as conformance_command
from kc.commands.guide import build_guide
from kc.output import HUMAN_RENDERERS

runner = CliRunner()
GOLDENS = Path(__file__).parent / "goldens" / "v1"


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


def normalize_envelope(payload: dict) -> dict:
    normalized = copy.deepcopy(payload)
    normalized["request_id"] = "<request_id>"
    normalized["metrics"]["duration_ms"] = "<duration_ms>"
    return normalized


def read_text_golden(name: str) -> str:
    return (GOLDENS / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def normalize_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").splitlines()) + "\n"


def read_json_golden(name: str) -> dict:
    return json.loads(read_text_golden(name))


def test_conformance_report_detects_missing_renderer() -> None:
    renderers = {key: renderer for key, renderer in HUMAN_RENDERERS.items() if key != "guide"}
    report = conformance_command.build_conformance_report(human_renderers=renderers)

    assert report["valid"] is False
    failed = {check["check_id"]: check for check in report["checks"] if not check["passed"]}
    assert failed["renderers.coverage"]["details"]["missing"] == ["guide"]


def test_conformance_report_detects_missing_guide_field() -> None:
    guide = build_guide()
    guide = copy.deepcopy(guide)
    del guide["commands"]["guide"]["syntax"]

    report = conformance_command.build_conformance_report(guide=guide)

    assert report["valid"] is False
    failed = {check["check_id"]: check for check in report["checks"] if not check["passed"]}
    assert failed["guide.command_fields"]["details"]["failures"] == [
        {"command_id": "guide", "missing": ["syntax"], "command_id_mismatch": False}
    ]


def test_conformance_json_success_envelope() -> None:
    result = runner.invoke(app, ["conformance"])

    assert result.exit_code == 0
    payload = parse(result.output)
    assert_envelope(payload, ok=True, command="conformance")
    assert payload["result"]["profile"] == "v1"
    assert payload["result"]["valid"] is True
    assert payload["result"]["summary"] == {"total": 6, "passed": 6, "failed": 0}
    assert all(check["passed"] is True for check in payload["result"]["checks"])


def test_conformance_table_and_markdown_formats() -> None:
    table = runner.invoke(app, ["--format", "table", "conformance"])
    assert table.exit_code == 0
    assert table.output.startswith("conformance\n")
    assert "guide.required_sections" in table.output
    assert not table.output.lstrip().startswith("{")

    markdown = runner.invoke(app, ["--format", "markdown", "conformance"])
    assert markdown.exit_code == 0
    assert markdown.output.startswith("# conformance\n")
    assert "| guide.required_sections | true |" in markdown.output
    assert not markdown.output.lstrip().startswith("{")


def test_conformance_llm_mode_forces_json_when_human_format_requested() -> None:
    result = runner.invoke(app, ["--format", "table", "conformance"], env={"LLM": "true"})

    assert result.exit_code == 0
    payload = parse(result.output)
    assert_envelope(payload, ok=True, command="conformance")


def test_conformance_failure_emits_contract_error(monkeypatch) -> None:
    renderers = {key: renderer for key, renderer in HUMAN_RENDERERS.items() if key != "conformance"}
    monkeypatch.setattr(conformance_command, "HUMAN_RENDERERS", renderers)

    result = runner.invoke(app, ["conformance"])

    assert result.exit_code == 10
    payload = parse(result.output)
    assert_envelope(payload, ok=False, command="conformance")
    assert payload["result"] is None
    error = payload["errors"][0]
    assert error["code"] == "KC_CONFORMANCE_FAILED"
    assert error["exit_code"] == 10
    failed_checks = error["details"]["failed_checks"]
    assert failed_checks[0]["check_id"] == "renderers.coverage"
    assert failed_checks[0]["details"]["missing"] == ["conformance"]


def test_v1_golden_guide_commands() -> None:
    result = runner.invoke(app, ["guide", "--section", "commands"])

    assert result.exit_code == 0
    actual = normalize_envelope(parse(result.output))
    assert actual == read_json_golden("guide_commands.json")


def test_v1_golden_conformance_json() -> None:
    result = runner.invoke(app, ["conformance"])

    assert result.exit_code == 0
    actual = normalize_envelope(parse(result.output))
    assert actual == read_json_golden("conformance.json")


def test_v1_golden_conformance_table() -> None:
    result = runner.invoke(app, ["--format", "table", "conformance"])

    assert result.exit_code == 0
    assert normalize_text(result.output) == read_text_golden("conformance_table.txt")
