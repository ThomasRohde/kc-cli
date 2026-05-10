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


def test_source_refresh_dry_run_and_yes_preserves_source_id(
    tmp_path: Path, monkeypatch
) -> None:
    init_repo(tmp_path, monkeypatch)
    source = tmp_path / "policy.md"
    source.write_text("original ownership text\n", encoding="utf-8")
    add = runner.invoke(app, ["source", "add", "policy.md", "--domain", "bcm", "--yes"])
    source_id = parse(add.output)["result"]["source_id"]
    old_fingerprint = parse(add.output)["result"]["fingerprint"]
    old_ranges = parse(
        runner.invoke(app, ["source", "inspect", source_id, "--ranges"]).output
    )["result"]["ranges"]

    source.write_text("changed lifecycle text\n", encoding="utf-8")
    dry = runner.invoke(app, ["source", "refresh", "policy.md", "--dry-run"])
    assert dry.exit_code == 0
    dry_payload = parse(dry.output)
    assert dry_payload["result"]["dry_run"] is True
    assert dry_payload["result"]["source_id"] == source_id
    assert dry_payload["result"]["old_fingerprint"] == old_fingerprint
    assert dry_payload["result"]["new_fingerprint"] != old_fingerprint
    assert dry_payload["result"]["index_rebuilt"] is False

    inspect_after_dry_run = runner.invoke(app, ["source", "inspect", source_id])
    assert parse(inspect_after_dry_run.output)["result"]["stale"] is True

    refresh = runner.invoke(app, ["source", "refresh", source_id, "--yes"])
    assert refresh.exit_code == 0
    refresh_payload = parse(refresh.output)
    assert refresh_payload["result"]["source_id"] == source_id
    assert refresh_payload["result"]["ranges_removed"] == len(old_ranges)
    assert refresh_payload["result"]["ranges_extracted"] >= 1
    assert refresh_payload["result"]["index_rebuilt"] is True

    inspect = runner.invoke(app, ["source", "inspect", source_id, "--ranges"])
    inspect_payload = parse(inspect.output)
    assert inspect_payload["result"]["stale"] is False
    assert inspect_payload["result"]["source"]["source_id"] == source_id
    assert inspect_payload["result"]["ranges"][0]["source_id"] == source_id
    assert "changed lifecycle text" in inspect_payload["result"]["ranges"][0]["excerpt"]

    lint = runner.invoke(app, ["lint", "--checks", "stale"])
    assert lint.exit_code == 0
