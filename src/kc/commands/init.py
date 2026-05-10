from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from kc.atomic_write import atomic_write_text
from kc.commands.common import run
from kc.config import DEFAULT_CONFIG
from kc.output import emit_success
from kc.paths import current_paths, repo_relative
from kc.store.sqlite import init_db


def register(app: typer.Typer) -> None:
    @app.command("init")
    def init_command(
        profile: Annotated[
            str, typer.Option("--profile", help="Initialization profile.")
        ] = "generic",
        dry_run: Annotated[
            bool, typer.Option("--dry-run", help="Preview without writing.")
        ] = False,
        yes: Annotated[bool, typer.Option("--yes", help="Create files.")] = False,
    ) -> None:
        def _run() -> None:
            paths = current_paths()
            effective_dry_run = dry_run or not yes
            dirs = [
                paths.data_dir,
                paths.data_dir / "raw",
                paths.wiki_dir,
                paths.data_dir / "artifacts",
                paths.data_dir / "schemas",
                paths.data_dir / "evals",
                paths.data_dir / "exports",
                paths.state_dir,
                paths.locks_dir,
                paths.snapshots_dir,
                paths.plans_dir,
                paths.tasks_dir,
                paths.state_dir / "cache",
                paths.state_dir / "logs",
            ]
            files: dict[Path, str] = {
                paths.config_path: DEFAULT_CONFIG,
                paths.sources_jsonl: "",
                paths.ranges_jsonl: "",
                paths.artifacts_jsonl: "",
                paths.citation_edges_jsonl: "",
                paths.wiki_dir / "index.md": "# Knowledge Index\n\n",
                paths.log_path: "# Knowledge Log\n\n",
            }
            created: list[str] = []
            noop: list[str] = []
            planned: list[str] = []
            for d in dirs:
                rel = repo_relative(d)
                if d.exists():
                    noop.append(rel)
                elif effective_dry_run:
                    planned.append(rel)
                else:
                    d.mkdir(parents=True, exist_ok=True)
                    created.append(rel)
            for path, content in files.items():
                rel = repo_relative(path)
                if path.exists():
                    noop.append(rel)
                elif effective_dry_run:
                    planned.append(rel)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_text(path, content)
                    created.append(rel)
            if effective_dry_run:
                planned.append(repo_relative(paths.sqlite_path))
            else:
                init_db(paths.sqlite_path)
                created.append(repo_relative(paths.sqlite_path))
            emit_success(
                "init",
                {
                    "dry_run": effective_dry_run,
                    "profile": profile,
                    "created": created,
                    "planned": planned,
                    "noop": sorted(set(noop)),
                },
            )

        run("init", _run)
