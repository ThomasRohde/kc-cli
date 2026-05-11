from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from kc.commands.common import run
from kc.errors import KcError
from kc.output import emit_success
from kc.paths import current_paths, ensure_under_root, repo_relative
from kc.search.fts import ensure_index, search_ranges

app = typer.Typer(help="Run deterministic retrieval evaluation packs.")


@app.command("run", help="Run retrieval eval cases from a YAML pack.")
def run_eval(
    pack: Annotated[Path | None, typer.Option("--pack", help="Eval pack YAML.")] = None,
) -> None:
    def _run() -> None:
        paths = current_paths()
        ensure_index(paths.sqlite_path, paths.sources_jsonl, paths.ranges_jsonl)
        cases: list[dict[str, Any]] = []
        pack_path = ensure_under_root((Path.cwd() / pack).resolve()) if pack else None
        if pack_path:
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
            cases = list(data.get("cases", []))
        results = []
        for case in cases:
            query = str(case.get("ask") or case.get("query") or "")
            found = search_ranges(paths.sqlite_path, query, limit=int(case.get("limit", 10)))
            expected_sources = set(case.get("expected_source_ids", []))
            found_sources = {item["source_id"] for item in found}
            results.append(
                {
                    "id": case.get("id"),
                    "query": query,
                    "passed": expected_sources.issubset(found_sources)
                    if expected_sources
                    else True,
                    "expected_source_ids": sorted(expected_sources),
                    "found_source_ids": sorted(found_sources),
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
        emit_success(
            "eval.run",
            {
                "pack": repo_relative(pack_path) if pack_path else None,
                "total": len(results),
                "passed": sum(1 for item in results if item["passed"]),
                "results": results,
            },
        )

    run("eval.run", _run)
