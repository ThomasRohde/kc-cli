from __future__ import annotations

import json
from typing import Annotated

import typer

from kc.commands.common import load_ranges, run
from kc.output import emit_success
from kc.paths import current_paths
from kc.search.semantic import semantic_index_status

app = typer.Typer(help="Inspect repository health, locks, and semantic index state.")


@app.callback(invoke_without_command=True)
def doctor(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return

    def _run() -> None:
        paths = current_paths()
        ranges = load_ranges() if paths.ranges_jsonl.exists() else []
        emit_success(
            "doctor",
            {
                "config_exists": paths.config_path.exists(),
                "data_dir_exists": paths.data_dir.exists(),
                "state_dir_exists": paths.state_dir.exists(),
                "sqlite_exists": paths.sqlite_path.exists(),
                "locks": len(list(paths.locks_dir.glob("*.lock")))
                if paths.locks_dir.exists()
                else 0,
                "semantic": semantic_index_status(paths.sqlite_path, ranges),
            },
        )

    run("doctor", _run)


@app.command("locks", help="List lock files and optionally clear them after confirmation.")
def locks(
    clear_stale: Annotated[bool, typer.Option("--clear-stale", help="Clear lock files.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm clearing lock files.")] = False,
) -> None:
    def _run() -> None:
        paths = current_paths()
        paths.locks_dir.mkdir(parents=True, exist_ok=True)
        lock_infos = []
        cleared = []
        for path in sorted(paths.locks_dir.glob("*.lock")):
            try:
                metadata = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                metadata = {"lock_file": str(path)}
            lock_infos.append({"path": str(path), "metadata": metadata})
            if clear_stale and yes:
                path.unlink(missing_ok=True)
                cleared.append(str(path))
        emit_success(
            "doctor.locks",
            {
                "locks": lock_infos,
                "clear_stale": clear_stale,
                "cleared": cleared,
                "dry_run": clear_stale and not yes,
            },
        )

    run("doctor.locks", _run)
