from __future__ import annotations

from typing import Annotated

import typer

from kc.commands.common import load_artifacts, load_citation_edges, load_ranges, load_sources, run
from kc.output import emit_success
from kc.paths import current_paths
from kc.search.semantic import build_semantic_index, load_semantic_model, semantic_model_metadata
from kc.store.sqlite import rebuild_index

app = typer.Typer(help="Build or rebuild derived SQLite search indexes.")


@app.command("build", help="Rebuild BM25 indexes and optionally build semantic embeddings.")
def build(
    semantic: Annotated[bool, typer.Option("--semantic", help="Build semantic index.")] = False,
    clean: Annotated[bool, typer.Option("--clean", help="Force a clean rebuild.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without writing.")] = False,
) -> None:
    def _run() -> None:
        sources = load_sources()
        ranges = load_ranges()
        paths = current_paths()
        if dry_run:
            semantic_model = None
            if semantic:
                semantic_model = semantic_model_metadata(load_semantic_model())
            result = {
                "dry_run": True,
                "clean": clean,
                "semantic": semantic,
                "semantic_model": semantic_model,
                "sources": len(sources),
                "ranges": len(ranges),
                "db_path": str(paths.sqlite_path),
            }
        else:
            result = rebuild_index(
                paths.sqlite_path,
                sources,
                ranges,
                load_artifacts(),
                load_citation_edges(),
            )
            if semantic:
                result["semantic"] = build_semantic_index(paths.sqlite_path, ranges)
            else:
                result["semantic"] = {"enabled": False}
            result["dry_run"] = False
            result["clean"] = clean
            result["db_path"] = str(paths.sqlite_path)
        emit_success("index.build", result)

    run("index.build", _run)
