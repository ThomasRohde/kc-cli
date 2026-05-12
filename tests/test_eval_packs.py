from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from kc.cli import app

runner = CliRunner()


def parse(output: str) -> dict:
    return json.loads(output)


def test_eval_pack_checks_expected_range_ids_and_writes_output(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "--yes"]).exit_code == 0
    source = tmp_path / "policy.md"
    source.write_text("Ownership rules define lifecycle responsibilities.\n", encoding="utf-8")
    assert runner.invoke(app, ["source", "add", "policy.md", "--domain", "bcm", "--yes"]).exit_code == 0
    hit = parse(runner.invoke(app, ["source", "search", "ownership"]).output)["result"]["results"][0]
    pack = tmp_path / "knowledge" / "evals" / "ranges.yaml"
    pack.write_text(
        "\n".join(
            [
                'schema_version: "kc.eval_pack.v1"',
                "cases:",
                "  - id: ownership",
                "    query: ownership lifecycle",
                "    expected_range_ids:",
                f"      - {hit['range_id']}",
                "    min_recall_at_k: 1.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            "--pack",
            str(pack.relative_to(tmp_path)),
            "--out",
            "knowledge/evals/result.json",
        ],
    )

    assert result.exit_code == 0
    payload = parse(result.output)
    assert payload["result"]["metrics"]["recall_at_k"] == 1.0
    assert payload["result"]["metrics"]["mrr"] == 1.0
    assert (tmp_path / "knowledge" / "evals" / "result.json").exists()
