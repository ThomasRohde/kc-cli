from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from kc.cli import app
from kc.commands.common import path_lock_name

runner = CliRunner()


def parse(output: str) -> dict:
    return json.loads(output)


def setup_repo_with_source(tmp_path: Path, monkeypatch) -> dict:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "--yes"]).exit_code == 0
    source = tmp_path / "policy.md"
    source.write_text(
        "# Ownership\n\nCapability owners maintain definitions and review lifecycle state.\n",
        encoding="utf-8",
    )
    assert (
        runner.invoke(app, ["source", "add", "policy.md", "--domain", "bcm", "--yes"]).exit_code
        == 0
    )
    search = runner.invoke(app, ["source", "search", "owners lifecycle", "--domain", "bcm"])
    return parse(search.output)["result"]["results"][0]


def write_valid_artifact(tmp_path: Path, citation: str) -> Path:
    artifact = tmp_path / "knowledge" / "wiki" / "ownership.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        f"""---
schema_version: kc.knowledge_page.v1
artifact_id: art_test
title: Ownership
status: draft
domain:
  - bcm
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


def test_artifact_validate_diff_and_apply(tmp_path: Path, monkeypatch) -> None:
    hit = setup_repo_with_source(tmp_path, monkeypatch)
    artifact = write_valid_artifact(tmp_path, hit["citation_token"])

    validate = runner.invoke(
        app, ["artifact", "validate", "--file", str(artifact.relative_to(tmp_path))]
    )
    assert validate.exit_code == 0
    payload = parse(validate.output)
    assert payload["result"]["valid"] is True
    assert payload["result"]["citation_edges"]

    diff = runner.invoke(app, ["artifact", "diff", "--file", str(artifact.relative_to(tmp_path))])
    assert diff.exit_code == 0
    assert parse(diff.output)["result"]["plan"]["plan_id"].startswith("plan_")

    dry = runner.invoke(
        app, ["artifact", "apply", "--file", str(artifact.relative_to(tmp_path)), "--dry-run"]
    )
    assert dry.exit_code == 0
    assert parse(dry.output)["result"]["applied"] is False

    apply = runner.invoke(
        app,
        [
            "artifact",
            "apply",
            "--file",
            str(artifact.relative_to(tmp_path)),
            "--yes",
            "--idempotency-key",
            "idem-test",
        ],
    )
    assert apply.exit_code == 0
    apply_payload = parse(apply.output)
    assert apply_payload["result"]["applied"] is True
    plan_id = apply_payload["result"]["plan"]["plan_id"]
    assert (tmp_path / ".kc" / "plans" / f"{plan_id}.json").exists()
    assert list((tmp_path / ".kc" / "snapshots").glob(f"*_{plan_id}/ownership.md"))
    assert (tmp_path / "knowledge" / "artifacts.jsonl").read_text(encoding="utf-8").strip()
    assert (tmp_path / "knowledge" / "citation_edges.jsonl").read_text(encoding="utf-8").strip()

    replay = runner.invoke(
        app,
        [
            "artifact",
            "apply",
            "--file",
            str(artifact.relative_to(tmp_path)),
            "--yes",
            "--idempotency-key",
            "idem-test",
        ],
    )
    assert replay.exit_code == 0
    replay_payload = parse(replay.output)
    assert replay_payload["result"]["noop"] is True
    assert replay_payload["result"]["idempotency"]["status"] == "replayed"


def test_artifact_diff_rejects_missing_file(tmp_path: Path, monkeypatch) -> None:
    setup_repo_with_source(tmp_path, monkeypatch)
    result = runner.invoke(app, ["artifact", "diff", "--file", "knowledge/wiki/missing.md"])
    assert result.exit_code == 11
    payload = parse(result.output)
    assert payload["errors"][0]["code"] == "KC_ARTIFACT_NOT_FOUND"


def test_artifact_apply_missing_plan_is_file_not_found(tmp_path: Path, monkeypatch) -> None:
    setup_repo_with_source(tmp_path, monkeypatch)
    result = runner.invoke(app, ["artifact", "apply", "--plan", "missing_plan.json", "--yes"])
    assert result.exit_code == 11
    payload = parse(result.output)
    assert payload["errors"][0]["code"] == "KC_FILE_NOT_FOUND"


def test_artifact_validate_fails_missing_citation(tmp_path: Path, monkeypatch) -> None:
    setup_repo_with_source(tmp_path, monkeypatch)
    artifact = tmp_path / "knowledge" / "wiki" / "bad.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        """---
schema_version: kc.knowledge_page.v1
artifact_id: art_bad
title: Bad
status: draft
domain: [bcm]
artifact_type: knowledge_page
requires_citations: true
---
# Bad

## Summary

This paragraph has no citation.

## Source-backed facts

- Still no citation.

## Open questions

- [kc:todo] Missing source.
""",
        encoding="utf-8",
    )
    missing_line = next(
        idx
        for idx, line in enumerate(artifact.read_text(encoding="utf-8").splitlines(), start=1)
        if line == "This paragraph has no citation."
    )
    result = runner.invoke(
        app, ["artifact", "validate", "--file", str(artifact.relative_to(tmp_path))]
    )
    assert result.exit_code == 10
    payload = parse(result.output)
    assert payload["ok"] is False
    assert {error["code"] for error in payload["errors"]} >= {
        "KC_ARTIFACT_SCHEMA_INVALID",
        "KC_VALIDATION_MISSING_CITATION",
    }
    assert any(
        error["code"] == "KC_VALIDATION_MISSING_CITATION"
        and error["details"].get("line") == missing_line
        for error in payload["errors"]
    )


def test_artifact_validate_accepts_source_ref_line_locators(
    tmp_path: Path, monkeypatch
) -> None:
    hit = setup_repo_with_source(tmp_path, monkeypatch)
    artifact = write_valid_artifact(tmp_path, hit["citation_token"])
    locator = hit["locator"]
    source_ref_locator = f"L{locator['start_line']}-L{locator['end_line']}"
    artifact.write_text(
        artifact.read_text(encoding="utf-8").replace(
            "source_refs: []",
            "\n".join(
                [
                    "source_refs:",
                    f"- source_id: {hit['source_id']}",
                    "  ranges:",
                    f"  - {source_ref_locator}",
                ]
            ),
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["artifact", "validate", "--file", str(artifact.relative_to(tmp_path))]
    )
    assert result.exit_code == 0
    assert parse(result.output)["result"]["valid"] is True


def test_llm_mode_blocks_skip_validate(tmp_path: Path, monkeypatch) -> None:
    setup_repo_with_source(tmp_path, monkeypatch)
    artifact = tmp_path / "knowledge" / "wiki" / "empty.md"
    artifact.write_text("no frontmatter\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "artifact",
            "apply",
            "--file",
            str(artifact.relative_to(tmp_path)),
            "--skip-validate",
            "--yes",
        ],
        env={"LLM": "true"},
    )
    assert result.exit_code == 10
    assert parse(result.output)["errors"][0]["code"] == "KC_APPLY_NOT_VALIDATED"


def test_artifact_validate_detects_malformed_and_stale_citations(
    tmp_path: Path, monkeypatch
) -> None:
    hit = setup_repo_with_source(tmp_path, monkeypatch)
    artifact = write_valid_artifact(tmp_path, hit["citation_token"])
    artifact.write_text(
        artifact.read_text(encoding="utf-8").replace(hit["citation_token"], "[kc:src_bad:L1]"),
        encoding="utf-8",
    )
    malformed = runner.invoke(
        app, ["artifact", "validate", "--file", str(artifact.relative_to(tmp_path))]
    )
    assert malformed.exit_code == 20
    assert "KC_CITATION_INVALID_TOKEN" in {
        error["code"] for error in parse(malformed.output)["errors"]
    }

    artifact = write_valid_artifact(tmp_path, hit["citation_token"])
    (tmp_path / "policy.md").write_text("changed source text\n", encoding="utf-8")
    stale = runner.invoke(
        app, ["artifact", "validate", "--file", str(artifact.relative_to(tmp_path))]
    )
    assert stale.exit_code == 20
    assert "KC_CITATION_STALE_SOURCE" in {
        error["code"] for error in parse(stale.output)["errors"]
    }


def test_active_artifact_rejects_todo_and_uncited_markers(
    tmp_path: Path, monkeypatch
) -> None:
    hit = setup_repo_with_source(tmp_path, monkeypatch)
    artifact = write_valid_artifact(tmp_path, hit["citation_token"])
    artifact.write_text(
        artifact.read_text(encoding="utf-8")
        .replace("status: draft", "status: active")
        .replace("[kc:todo] Confirm review cadence.", "[kc:uncited] Confirm review cadence."),
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["artifact", "validate", "--file", str(artifact.relative_to(tmp_path))]
    )
    assert result.exit_code == 10
    codes = {error["code"] for error in parse(result.output)["errors"]}
    assert "KC_VALIDATION_MISSING_CITATION" in codes


def test_draft_todo_markers_emit_warning(tmp_path: Path, monkeypatch) -> None:
    hit = setup_repo_with_source(tmp_path, monkeypatch)
    artifact = write_valid_artifact(tmp_path, hit["citation_token"])
    result = runner.invoke(
        app, ["artifact", "validate", "--file", str(artifact.relative_to(tmp_path))]
    )
    assert result.exit_code == 0
    payload = parse(result.output)
    assert "KC_ARTIFACT_TODO_MARKERS" in {item["code"] for item in payload["warnings"]}


def test_artifact_new_rejects_unknown_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "--yes"]).exit_code == 0
    result = runner.invoke(
        app,
        [
            "artifact",
            "new",
            "--path",
            "knowledge/artifacts/test.md",
            "--title",
            "T",
            "--status",
            "weird_status",
            "--yes",
        ],
    )
    assert result.exit_code == 10
    assert parse(result.output)["errors"][0]["code"] == "KC_VALIDATION_INVALID_ARGUMENT"


def test_json_artifact_schema_and_structured_citations(
    tmp_path: Path, monkeypatch
) -> None:
    hit = setup_repo_with_source(tmp_path, monkeypatch)
    artifact = tmp_path / "knowledge" / "artifacts" / "glossary.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {
                "schema_version": "kc.glossary.v1",
                "artifact_id": "art_json",
                "title": "Glossary",
                "artifact_type": "glossary",
                "status": "draft",
                "domain": ["bcm"],
                "terms": [
                    {
                        "term": "Owner",
                        "definition": "Maintains lifecycle state.",
                        "citations": [
                            {"source_id": hit["source_id"], "range_id": hit["range_id"]}
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "artifact",
            "validate",
            "--file",
            str(artifact.relative_to(tmp_path)),
            "--schema",
            "kc.glossary.v1",
        ],
    )
    assert result.exit_code == 0
    assert parse(result.output)["result"]["citation_edges"][0]["status"] == "valid"


def test_artifact_apply_rejects_idempotency_key_conflict(
    tmp_path: Path, monkeypatch
) -> None:
    hit = setup_repo_with_source(tmp_path, monkeypatch)
    artifact = write_valid_artifact(tmp_path, hit["citation_token"])
    rel = str(artifact.relative_to(tmp_path))
    first = runner.invoke(
        app, ["artifact", "apply", "--file", rel, "--yes", "--idempotency-key", "idem-conflict"]
    )
    assert first.exit_code == 0
    artifact.write_text(
        artifact.read_text(encoding="utf-8").replace("maintain definitions", "maintain definitions safely"),
        encoding="utf-8",
    )
    second = runner.invoke(
        app, ["artifact", "apply", "--file", rel, "--yes", "--idempotency-key", "idem-conflict"]
    )
    assert second.exit_code == 13
    assert parse(second.output)["errors"][0]["code"] == "KC_PLAN_PRECONDITION_FAILED"


def test_artifact_apply_reports_lock_held(tmp_path: Path, monkeypatch) -> None:
    hit = setup_repo_with_source(tmp_path, monkeypatch)
    artifact = write_valid_artifact(tmp_path, hit["citation_token"])
    rel = str(artifact.relative_to(tmp_path))
    lock_dir = tmp_path / ".kc" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_name = path_lock_name(artifact.resolve())
    (lock_dir / f"{lock_name}.lock").write_text('{"command":"test"}\n', encoding="utf-8")

    result = runner.invoke(app, ["artifact", "apply", "--file", rel, "--yes"])
    assert result.exit_code == 60
    assert parse(result.output)["errors"][0]["code"] == "KC_LOCK_HELD"


def test_artifact_apply_plan_rejects_changed_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    hit = setup_repo_with_source(tmp_path, monkeypatch)
    artifact = write_valid_artifact(tmp_path, hit["citation_token"])
    rel = str(artifact.relative_to(tmp_path))
    dry = runner.invoke(app, ["artifact", "apply", "--file", rel, "--dry-run"])
    assert dry.exit_code == 0
    plan = parse(dry.output)["result"]["plan"]
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")

    artifact.write_text(
        artifact.read_text(encoding="utf-8").replace(
            "Capability owners maintain definitions.",
            "Capability owners maintain definitions and stewardship.",
        ),
        encoding="utf-8",
    )
    apply = runner.invoke(app, ["artifact", "apply", "--plan", "plan.json", "--yes"])
    assert apply.exit_code == 13
    assert parse(apply.output)["errors"][0]["code"] == "KC_PLAN_PRECONDITION_FAILED"


def test_source_refresh_impacts_old_citation_tokens(
    tmp_path: Path, monkeypatch
) -> None:
    hit = setup_repo_with_source(tmp_path, monkeypatch)
    artifact = write_valid_artifact(tmp_path, hit["citation_token"])
    rel = str(artifact.relative_to(tmp_path))
    assert runner.invoke(app, ["artifact", "apply", "--file", rel, "--yes"]).exit_code == 0

    (tmp_path / "policy.md").write_text("# Ownership\n", encoding="utf-8")
    refresh = runner.invoke(app, ["source", "refresh", "policy.md", "--yes"])
    assert refresh.exit_code == 0
    impacts = parse(refresh.output)["result"]["impacted_artifacts"]
    assert impacts
    assert impacts[0]["artifact_path"] == "knowledge/wiki/ownership.md"
    assert impacts[0]["reason"] == "line_range_no_longer_resolves"

    validate = runner.invoke(app, ["artifact", "validate", "--file", rel])
    assert validate.exit_code == 20
    assert parse(validate.output)["errors"][0]["code"] == "KC_CITATION_RANGE_MISSING"
