from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any

import typer

from kc.atomic_write import atomic_write_text
from kc.commands.common import run, validate_choice
from kc.config import DEFAULT_CONFIG
from kc.output import emit_success, warning
from kc.paths import current_paths, repo_relative
from kc.store.sqlite import init_db

ALLOWED_PROFILES = {"generic"}
MANAGED_AGENT_SKILL_MARKER = "kc-managed-agent-skill:v1"
AGENT_SKILL_DIRS = [
    Path(".agents"),
    Path(".agents") / "skills",
    Path(".agents") / "skills" / "kc",
    Path(".agents") / "skills" / "kc" / "agents",
    Path(".agents") / "skills" / "kc" / "scripts",
]
AGENT_SKILL_TEMPLATE_FILES = [
    (("SKILL.md",), Path(".agents") / "skills" / "kc" / "SKILL.md"),
    (("agents", "openai.yaml"), Path(".agents") / "skills" / "kc" / "agents" / "openai.yaml"),
    (
        ("scripts", "resolve_query_citations.py"),
        Path(".agents") / "skills" / "kc" / "scripts" / "resolve_query_citations.py",
    ),
]


def _agent_skill_templates() -> dict[Path, str]:
    template_root = files("kc").joinpath("templates", "agents", "skills", "kc")
    return {
        target: template_root.joinpath(*template_path).read_text(encoding="utf-8")
        for template_path, target in AGENT_SKILL_TEMPLATE_FILES
    }


def _handle_managed_file(
    path: Path,
    content: str,
    *,
    effective_dry_run: bool,
    created: list[str],
    updated: list[str],
    noop: list[str],
    planned: list[str],
    warnings: list[dict[str, Any]],
) -> None:
    rel = repo_relative(path)
    if not path.exists():
        if effective_dry_run:
            planned.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, content)
            created.append(rel)
        return

    if not path.is_file():
        noop.append(rel)
        warnings.append(
            warning(
                "KC_INIT_AGENT_SKILL_CUSTOM",
                "Existing agent skill path is not a managed file; preserved without overwrite.",
                {"path": rel},
            )
        )
        return

    current = path.read_text(encoding="utf-8")
    if current == content:
        noop.append(rel)
        return
    if MANAGED_AGENT_SKILL_MARKER in current:
        if effective_dry_run:
            planned.append(rel)
        else:
            atomic_write_text(path, content)
            updated.append(rel)
        return

    noop.append(rel)
    warnings.append(
        warning(
            "KC_INIT_AGENT_SKILL_CUSTOM",
            "Existing agent skill file is not kc-managed; preserved without overwrite.",
            {"path": rel},
        )
    )


def register(app: typer.Typer) -> None:
    @app.command("init", help="Create the repo-local kc layout, config, JSONL stores, and SQLite state.")
    def init_command(
        profile: Annotated[
            str, typer.Option("--profile", help="Initialization profile: generic.")
        ] = "generic",
        dry_run: Annotated[
            bool, typer.Option("--dry-run", help="Preview without writing.")
        ] = False,
        yes: Annotated[bool, typer.Option("--yes", help="Create files.")] = False,
    ) -> None:
        def _run() -> None:
            validate_choice(profile, option="--profile", supported=ALLOWED_PROFILES)
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
                *[paths.root / path for path in AGENT_SKILL_DIRS],
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
            updated: list[str] = []
            warnings: list[dict[str, Any]] = []
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
            for rel_path, content in _agent_skill_templates().items():
                _handle_managed_file(
                    paths.root / rel_path,
                    content,
                    effective_dry_run=effective_dry_run,
                    created=created,
                    updated=updated,
                    noop=noop,
                    planned=planned,
                    warnings=warnings,
                )
            sqlite_rel = repo_relative(paths.sqlite_path)
            if paths.sqlite_path.exists():
                noop.append(sqlite_rel)
            elif effective_dry_run:
                planned.append(sqlite_rel)
            else:
                init_db(paths.sqlite_path)
                created.append(sqlite_rel)
            emit_success(
                "init",
                {
                    "dry_run": effective_dry_run,
                    "profile": profile,
                    "created": created,
                    "updated": updated,
                    "planned": planned,
                    "noop": sorted(set(noop)),
                },
                warnings=warnings,
            )

        run("init", _run)
