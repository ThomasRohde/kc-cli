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


def test_source_search_rejects_non_positive_limit(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path, monkeypatch)
    result = runner.invoke(app, ["source", "search", "owners", "--limit", "0"])
    assert result.exit_code == 10
    assert parse(result.output)["errors"][0]["code"] == "KC_VALIDATION_INVALID_ARGUMENT"

    negative = runner.invoke(app, ["source", "search", "owners", "--limit", "-5"])
    assert negative.exit_code == 10
    assert parse(negative.output)["errors"][0]["code"] == "KC_VALIDATION_INVALID_ARGUMENT"


def test_source_add_empty_file_warns_no_ranges(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path, monkeypatch)
    source = tmp_path / "empty.md"
    source.write_text("", encoding="utf-8")
    result = runner.invoke(app, ["source", "add", "empty.md", "--yes"])
    assert result.exit_code == 0
    payload = parse(result.output)
    assert payload["result"]["ranges_extracted"] == 0
    assert "KC_SOURCE_NO_RANGES" in {item["code"] for item in payload["warnings"]}


def test_source_add_dry_run_previews_stable_source_id(
    tmp_path: Path, monkeypatch
) -> None:
    init_repo(tmp_path, monkeypatch)
    source = tmp_path / "policy.md"
    source.write_text(
        "# Ownership\n\nCapability owners maintain definitions.\n",
        encoding="utf-8",
    )

    dry_run = runner.invoke(app, ["source", "add", "policy.md", "--domain", "bcm", "--dry-run"])
    assert dry_run.exit_code == 0
    assert not (tmp_path / "knowledge" / "sources.jsonl").read_text(encoding="utf-8").strip()

    apply = runner.invoke(app, ["source", "add", "policy.md", "--domain", "bcm", "--yes"])
    assert apply.exit_code == 0
    assert parse(dry_run.output)["result"]["source_id"] == parse(apply.output)["result"]["source_id"]


def test_structured_sources_emit_json_pointer_and_csv_citations(
    tmp_path: Path, monkeypatch
) -> None:
    init_repo(tmp_path, monkeypatch)
    json_source = tmp_path / "policy.json"
    json_source.write_text(
        '{"policy": {"owner": "platform team", "review": "quarterly"}}',
        encoding="utf-8",
    )
    csv_source = tmp_path / "controls.csv"
    csv_source.write_text("control,owner\nlogging,security team\n", encoding="utf-8")

    assert runner.invoke(app, ["source", "add", "policy.json", "--domain", "ops", "--yes"]).exit_code == 0
    assert runner.invoke(app, ["source", "add", "controls.csv", "--domain", "ops", "--yes"]).exit_code == 0

    json_search = runner.invoke(app, ["source", "search", "platform", "--domain", "ops"])
    assert json_search.exit_code == 0
    json_hit = parse(json_search.output)["result"]["results"][0]
    assert json_hit["locator"]["kind"] == "json_pointer"
    assert json_hit["citation_token"].startswith("[kc:src_")
    assert ":JP:/policy/owner]" in json_hit["citation_token"]

    csv_search = runner.invoke(app, ["source", "search", "security", "--domain", "ops"])
    assert csv_search.exit_code == 0
    csv_hit = parse(csv_search.output)["result"]["results"][0]
    assert csv_hit["locator"]["kind"] == "csv_row_range"
    assert ":CSV:R2-R2]" in csv_hit["citation_token"]

    artifact = tmp_path / "knowledge" / "wiki" / "structured.md"
    artifact.write_text(
        f"""---
schema_version: kc.knowledge_page.v1
artifact_id: art_structured
title: Structured
status: draft
domain: [ops]
artifact_type: knowledge_page
requires_citations: true
source_refs: []
---
# Structured

## Summary

The owner is represented in structured source data. {json_hit["citation_token"]}

## Source-backed facts

- The control owner is represented in CSV data. {csv_hit["citation_token"]}

## Open questions

- [kc:todo] Confirm ownership cadence.
""",
        encoding="utf-8",
    )
    validate = runner.invoke(
        app, ["artifact", "validate", "--file", str(artifact.relative_to(tmp_path))]
    )
    assert validate.exit_code == 0
    citation_check = runner.invoke(
        app, ["citation", "check", "--file", str(artifact.relative_to(tmp_path))]
    )
    assert citation_check.exit_code == 0
    assert parse(citation_check.output)["result"]["files"][0]["citations"] == 2


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


def test_search_and_context_warn_on_stale_sources(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path, monkeypatch)
    source = tmp_path / "policy.md"
    source.write_text("ownership lifecycle text\n", encoding="utf-8")
    assert runner.invoke(app, ["source", "add", "policy.md", "--yes"]).exit_code == 0
    source.write_text("changed ownership lifecycle text\n", encoding="utf-8")

    search = runner.invoke(app, ["source", "search", "ownership"])
    assert search.exit_code == 0
    assert "KC_SOURCE_STALE" in {item["code"] for item in parse(search.output)["warnings"]}

    context = runner.invoke(app, ["context", "prepare", "--ask", "ownership"])
    assert context.exit_code == 0
    assert "KC_SOURCE_STALE" in {item["code"] for item in parse(context.output)["warnings"]}


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


def test_lint_detects_duplicate_ids(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path, monkeypatch)
    source = tmp_path / "policy.md"
    source.write_text("ownership text\n", encoding="utf-8")
    assert runner.invoke(app, ["source", "add", "policy.md", "--yes"]).exit_code == 0
    sources_jsonl = tmp_path / "knowledge" / "sources.jsonl"
    first_line = sources_jsonl.read_text(encoding="utf-8").splitlines()[0]
    sources_jsonl.write_text(first_line + "\n" + first_line + "\n", encoding="utf-8")

    lint = runner.invoke(app, ["lint", "--checks", "duplicates"])
    assert lint.exit_code == 10
    payload = parse(lint.output)
    assert payload["errors"][0]["code"] == "KC_CONFIG_INVALID"
    assert "Duplicate source_id" in payload["errors"][0]["message"]


def test_lint_rejects_unknown_or_empty_checks(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path, monkeypatch)
    invalid = runner.invoke(app, ["lint", "--checks", "invalid_check"])
    assert invalid.exit_code == 10
    assert parse(invalid.output)["errors"][0]["code"] == "KC_VALIDATION_INVALID_ARGUMENT"

    empty = runner.invoke(app, ["lint", "--checks", ""])
    assert empty.exit_code == 10
    assert parse(empty.output)["errors"][0]["code"] == "KC_VALIDATION_INVALID_ARGUMENT"
