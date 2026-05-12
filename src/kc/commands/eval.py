from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from kc.atomic_write import atomic_write_text
from kc.commands.common import run
from kc.errors import KcError
from kc.models.eval import EvalPack
from kc.output import emit_success
from kc.paths import current_paths, repo_relative, resolve_repo_path
from kc.search.fts import ensure_index, search_ranges
from kc.store.transaction import mutation_transaction

app = typer.Typer(help="Run deterministic retrieval evaluation packs.")


@app.command("run", help="Run retrieval eval cases from a YAML pack.")
def run_eval(
    pack: Annotated[Path | None, typer.Option("--pack", help="Eval pack YAML.")] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Write eval result JSON.")] = None,
) -> None:
    def _run() -> None:
        paths = current_paths()
        cases: list[dict[str, Any]] = []
        pack_path = resolve_repo_path(pack, paths.root) if pack else None
        if pack_path is None:
            raise KcError(
                code="KC_USAGE_ERROR",
                message="Provide --pack.",
                details={"option": "--pack"},
            )
        ensure_index(paths.sqlite_path, paths.sources_jsonl, paths.ranges_jsonl)
        if not pack_path.exists():
            raise KcError(
                code="KC_FILE_NOT_FOUND",
                message=f"Eval pack not found: {repo_relative(pack_path)}",
                details={"path": repo_relative(pack_path)},
            )
        data = yaml.safe_load(pack_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise KcError(
                code="KC_CONFIG_INVALID",
                message="Eval pack must be a YAML object.",
                details={"path": repo_relative(pack_path)},
            )
        try:
            eval_pack = EvalPack.model_validate(data)
        except Exception as exc:
            raise KcError(
                code="KC_ARTIFACT_SCHEMA_INVALID",
                message=f"Invalid eval pack: {exc}",
                details={"path": repo_relative(pack_path)},
            ) from exc
        cases = [case.model_dump(mode="json") for case in eval_pack.cases]
        results = []
        for case in cases:
            query = str(case.get("ask") or case.get("query") or "")
            found = search_ranges(
                paths.sqlite_path,
                query,
                domain=case.get("domain"),
                limit=int(case.get("limit", 10)),
            )
            expected_sources = set(case.get("expected_source_ids", []))
            expected_ranges = set(case.get("expected_range_ids", []))
            expected_citations = set(case.get("must_include_citation_tokens", []))
            found_sources = {item["source_id"] for item in found}
            found_ranges = [item["range_id"] for item in found]
            found_range_set = set(found_ranges)
            found_citations = {item["citation_token"] for item in found}
            expected_total = len(expected_sources) + len(expected_ranges) + len(expected_citations)
            matched_total = (
                len(expected_sources & found_sources)
                + len(expected_ranges & found_range_set)
                + len(expected_citations & found_citations)
            )
            recall = 1.0 if expected_total == 0 else matched_total / expected_total
            reciprocal_rank = 0.0
            for index, range_id in enumerate(found_ranges, start=1):
                if range_id in expected_ranges:
                    reciprocal_rank = 1.0 / index
                    break
            min_recall = float(case.get("min_recall_at_k", 1.0))
            results.append(
                {
                    "id": case.get("id"),
                    "query": query,
                    "passed": recall >= min_recall,
                    "expected_source_ids": sorted(expected_sources),
                    "expected_range_ids": sorted(expected_ranges),
                    "found_source_ids": sorted(found_sources),
                    "found_range_ids": found_ranges,
                    "recall_at_k": recall,
                    "reciprocal_rank": reciprocal_rank,
                    "results": found,
                }
            )
        failed = [item for item in results if not item["passed"]]
        if failed:
            raise KcError(
                code="KC_ARTIFACT_SCHEMA_INVALID",
                message="Retrieval eval failed.",
                details={"failed": failed, "total": len(results)},
            )
        result = {
            "pack": repo_relative(pack_path),
            "total": len(results),
            "passed": sum(1 for item in results if item["passed"]),
            "metrics": {
                "recall_at_k": sum(float(item["recall_at_k"]) for item in results) / len(results)
                if results
                else 1.0,
                "mrr": sum(float(item["reciprocal_rank"]) for item in results) / len(results)
                if results
                else 0.0,
            },
            "results": results,
        }
        if out is not None:
            out_path = resolve_repo_path(out, paths.root)
            with mutation_transaction(paths, "eval.run", [out_path]) as tx:
                import orjson

                atomic_write_text(out_path, orjson.dumps(result, option=orjson.OPT_INDENT_2).decode() + "\n")
                tx.commit({"out": repo_relative(out_path)})
            result["out"] = repo_relative(out_path)
        emit_success("eval.run", result)

    run("eval.run", _run)
