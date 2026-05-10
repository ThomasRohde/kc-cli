from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from kc.cli import app

runner = CliRunner()


def parse(output: str) -> dict:
    return json.loads(output)


def init_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 0


def test_source_add_extracts_ranges_and_search_returns_citation(
    tmp_path: Path, monkeypatch
) -> None:
    init_repo(tmp_path, monkeypatch)
    source = tmp_path / "policy.md"
    source.write_text(
        "# Ownership\n\nCapability owners maintain definitions and review lifecycle state.\n",
        encoding="utf-8",
    )
    add = runner.invoke(app, ["source", "add", "policy.md", "--domain", "bcm", "--yes"])
    assert add.exit_code == 0
    add_payload = parse(add.output)
    assert add_payload["result"]["ranges_extracted"] >= 1
    assert add_payload["result"]["fingerprint"].startswith("sha256:")

    search = runner.invoke(app, ["source", "search", "owners lifecycle", "--domain", "bcm"])
    assert search.exit_code == 0
    payload = parse(search.output)
    assert payload["command"] == "source.search"
    assert payload["result"]["total"] >= 1
    first = payload["result"]["results"][0]
    assert first["range_id"].startswith("rng_")
    assert first["source_id"].startswith("src_")
    assert first["citation_token"].startswith("[kc:src_")


def test_source_inspect_reports_staleness(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path, monkeypatch)
    source = tmp_path / "policy.md"
    source.write_text("original text\n", encoding="utf-8")
    add = runner.invoke(app, ["source", "add", "policy.md", "--yes"])
    source_id = parse(add.output)["result"]["source_id"]
    source.write_text("changed text\n", encoding="utf-8")
    inspect = runner.invoke(app, ["source", "inspect", source_id, "--ranges"])
    assert inspect.exit_code == 0
    payload = parse(inspect.output)
    assert payload["result"]["stale"] is True
    assert payload["result"]["ranges"]
