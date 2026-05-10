from __future__ import annotations

from typing import Annotated

import typer

from kc.commands.common import load_artifacts, load_citation_edges, load_ranges, load_sources, run
from kc.errors import KcError
from kc.output import emit_success
from kc.paths import current_paths
from kc.store.sqlite import rebuild_index

app = typer.Typer(help="Index commands.")


@app.command("build")
def build(
    semantic: Annotated[bool, typer.Option("--semantic", help="Build semantic index.")] = False,
    clean: Annotated[bool, typer.Option("--clean", help="Force a clean rebuild.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without writing.")] = False,
) -> None:
    def _run() -> None:
        if semantic:
            raise KcError(
                code="KC_RETRIEVAL_MODEL_UNAVAILABLE",
                message="Semantic retrieval is deferred in v1; use BM25 index build.",
            )
        sources = load_sources()
        ranges = load_ranges()
        paths = current_paths()
        if dry_run:
            result = {
                "dry_run": True,
                "clean": clean,
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
            result["dry_run"] = False
            result["clean"] = clean
            result["db_path"] = str(paths.sqlite_path)
        emit_success("index.build", result)

    run("index.build", _run)
