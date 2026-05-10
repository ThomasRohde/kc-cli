from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from kc.commands.common import run
from kc.output import emit_success
from kc.paths import current_paths
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
        if pack and pack.exists():
            data = yaml.safe_load(pack.read_text(encoding="utf-8")) or {}
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
        emit_success(
            "eval.run",
            {
                "pack": str(pack) if pack else None,
                "total": len(results),
                "passed": sum(1 for item in results if item["passed"]),
                "results": results,
            },
        )

    run("eval.run", _run)
