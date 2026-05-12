from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from kc.cli import app
from kc.search import semantic
from kc.search.fts import rrf_score

runner = CliRunner()


def parse(output: str) -> dict:
    return json.loads(output)


def init_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 0


def add_policy_source(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    source.write_text(
        "# Ownership\n\n"
        "Capability owners maintain accountability, definitions, and lifecycle reviews.\n\n"
        "# Encryption\n\n"
        "Sensitive customer records require cryptographic controls and key management.\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["source", "add", "policy.md", "--domain", "bcm", "--yes"])
    assert result.exit_code == 0


def test_embedding_blob_round_trip_and_cosine() -> None:
    original = np.array([1.0, 0.0, 0.5], dtype=np.float32)
    recovered = semantic.blob_to_embedding(semantic.embedding_to_blob(original))
    np.testing.assert_allclose(recovered, original)
    assert semantic.cosine_similarity(original, original) == 1.0
    assert semantic.cosine_similarity(original, np.zeros(3, dtype=np.float32)) == 0.0


def test_model_directory_checksum_is_deterministic() -> None:
    assert semantic.model_directory_checksum(semantic.bundled_model_dir()) == semantic.EXPECTED_CHECKSUM


def test_rrf_score_is_deterministic() -> None:
    assert rrf_score([1], k=60) == 1 / 61
    assert rrf_score([1, 3], k=60) == (1 / 61) + (1 / 63)


def test_hybrid_index_and_search_are_default(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path, monkeypatch)
    add_policy_source(tmp_path)

    search = runner.invoke(
        app,
        ["source", "search", "owners lifecycle", "--domain", "bcm", "--limit", "3"],
    )
    assert search.exit_code == 0
    search_payload = parse(search.output)
    assert search_payload["result"]["mode"] == "hybrid"
    first = search_payload["result"]["results"][0]
    assert first["citation_token"].startswith("[kc:src_")
    assert first["scores"]["hybrid_rank"] == 1
    assert first["scores"]["rrf_score"] is not None
    assert first["scores"]["bm25_rank"] is not None
    assert first["scores"]["semantic_rank"] is not None
    assert first["scores"]["semantic_score"] is not None

    build = runner.invoke(app, ["index", "build"])
    assert build.exit_code == 0
    build_payload = parse(build.output)
    assert build_payload["result"]["semantic"]["enabled"] is True
    assert build_payload["result"]["semantic"]["model"]["checksum"] == semantic.EXPECTED_CHECKSUM
    assert build_payload["result"]["semantic"]["embeddings"] >= 2


def test_context_prepare_uses_hybrid_mode(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path, monkeypatch)
    add_policy_source(tmp_path)

    result = runner.invoke(
        app,
        [
            "context",
            "prepare",
            "--ask",
            "Create ownership lifecycle notes",
            "--domain",
            "bcm",
        ],
    )
    assert result.exit_code == 0
    payload = parse(result.output)
    assert payload["result"]["mode"] == "hybrid"
    assert payload["result"]["candidate_ranges"]
    assert payload["result"]["candidate_ranges"][0]["scores"]["rrf_score"] is not None


def test_semantic_model_checksum_mismatch_fails(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path, monkeypatch)
    add_policy_source(tmp_path)
    semantic.load_semantic_model.cache_clear()
    monkeypatch.setattr(semantic, "EXPECTED_CHECKSUM", "sha256:not-the-bundled-model")
    result = runner.invoke(app, ["index", "build"])
    assert result.exit_code == 31
    payload = parse(result.output)
    assert payload["errors"][0]["code"] == "KC_RETRIEVAL_MODEL_UNAVAILABLE"
    assert "checksum" in payload["errors"][0]["message"]
    semantic.load_semantic_model.cache_clear()


def test_source_search_falls_back_to_fts_when_semantic_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    init_repo(tmp_path, monkeypatch)
    add_policy_source(tmp_path)
    semantic.load_semantic_model.cache_clear()
    monkeypatch.setattr(semantic, "EXPECTED_CHECKSUM", "sha256:not-the-bundled-model")

    result = runner.invoke(app, ["source", "search", "owners lifecycle", "--domain", "bcm"])

    assert result.exit_code == 0
    payload = parse(result.output)
    assert payload["result"]["mode"] == "fts_fallback"
    assert payload["result"]["results"]
    assert payload["result"]["results"][0]["scores"]["semantic_rank"] is None
    assert "KC_RETRIEVAL_SEMANTIC_UNAVAILABLE" in {item["code"] for item in payload["warnings"]}
    semantic.load_semantic_model.cache_clear()


def test_removed_retrieval_options_are_usage_errors(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path, monkeypatch)
    add_policy_source(tmp_path)

    cases = [
        ["source", "search", "owners", "--mode", "hybrid"],
        ["context", "prepare", "--ask", "owners", "--mode", "hybrid"],
        ["index", "build", "--semantic"],
    ]
    for args in cases:
        result = runner.invoke(app, args)
        assert result.exit_code == 2
        payload = parse(result.output)
        assert payload["errors"][0]["code"] == "KC_USAGE_ERROR"
