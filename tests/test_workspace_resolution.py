from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from kc.cli import app
from kc.config import DEFAULT_CONFIG

runner = CliRunner()


def parse(output: str) -> dict:
    return json.loads(output)


def test_commands_resolve_workspace_from_subdirectory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "--yes"]).exit_code == 0
    source = tmp_path / "docs" / "policy.md"
    source.parent.mkdir()
    source.write_text("Ownership rules define lifecycle responsibilities.\n", encoding="utf-8")
    add = runner.invoke(app, ["source", "add", "docs/policy.md", "--yes"])
    assert add.exit_code == 0
    source_id = parse(add.output)["result"]["source_id"]

    nested = tmp_path / "nested" / "work"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    search = runner.invoke(app, ["source", "search", "ownership"])
    assert search.exit_code == 0
    payload = parse(search.output)
    assert payload["result"]["results"][0]["source_id"] == source_id
    assert payload["target"]["workspace_root"] == tmp_path.as_posix()

    inspect_result = runner.invoke(app, ["source", "inspect", source_id])
    assert inspect_result.exit_code == 0
    assert parse(inspect_result.output)["result"]["stale"] is False


def test_kc_toml_data_and_state_dirs_are_honored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "kc.toml").write_text(
        DEFAULT_CONFIG.replace('data_dir = "knowledge"', 'data_dir = "kcdata"').replace(
            'state_dir = ".kc"', 'state_dir = "kcstate"'
        ),
        encoding="utf-8",
    )

    init_result = runner.invoke(app, ["init", "--yes"])
    assert init_result.exit_code == 0
    assert (tmp_path / "kcdata" / "sources.jsonl").exists()
    assert (tmp_path / "kcstate" / "state.sqlite").exists()
    assert not (tmp_path / "knowledge" / "sources.jsonl").exists()
    assert parse(init_result.output)["target"]["workspace_root"] == tmp_path.as_posix()

    source = tmp_path / "policy.md"
    source.write_text("Ownership rules define lifecycle responsibilities.\n", encoding="utf-8")
    add = runner.invoke(app, ["source", "add", "policy.md", "--yes"])
    assert add.exit_code == 0
    assert (tmp_path / "kcdata" / "sources.jsonl").read_text(encoding="utf-8").strip()


def test_root_global_option_overrides_current_directory(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.chdir(root)
    assert runner.invoke(app, ["init", "--yes"]).exit_code == 0
    source = root / "policy.md"
    source.write_text("Ownership rules define lifecycle responsibilities.\n", encoding="utf-8")
    assert runner.invoke(app, ["source", "add", "policy.md", "--yes"]).exit_code == 0

    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    result = runner.invoke(app, ["--root", str(root), "source", "search", "ownership"])

    assert result.exit_code == 0
    payload = parse(result.output)
    assert payload["target"]["workspace_root"] == root.as_posix()
    assert payload["result"]["total"] >= 1
