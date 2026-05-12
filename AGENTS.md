# Codex Project Instructions

## Scope

These instructions apply to the whole repository.

## Project Shape

`kc-cli` is a Python 3.12+ Typer CLI using a `src/` layout. The package implements `kc`, a deterministic, local-first knowledge compiler harness for external agents. The agent writes semantic content; `kc` handles source registration, search, context preparation, citation validation, safe apply, and task state. Keep `kc` free of LLM/provider dependencies and do not add generative reasoning inside the CLI.

Use the existing command/module organization:

- CLI wiring: `src/kc/cli.py` and `src/kc/commands/`
- Data models: `src/kc/models/`
- JSONL and SQLite storage: `src/kc/store/`
- Retrieval and extraction: `src/kc/search/`
- Citation/provenance logic: `src/kc/provenance/`
- Artifact helpers: `src/kc/artifacts/`
- Tests: `tests/`

## Local Commands

When the package is not installed, run the CLI from the repo root with:

```powershell
$env:PYTHONPATH='src'; python -m kc --help
```

Useful checks:

```powershell
uv run pytest
uv run ruff check .
uv run pyright
$env:PYTHONPATH='src'; python -m kc lint
```

Use `pytest tests/<file>.py -q` for focused checks while iterating, then broaden as risk increases.

## Versioning and Releases

Follow the `archguard`-style single-source version regime:

- Keep the package version in `src/kc/__init__.py` as `__version__`.
- Keep `pyproject.toml` configured for Hatch dynamic versioning from that file.
- Keep `kc --version`, `kc guide`, and the package version in sync.
- Keep `CHANGELOG.md` with an `[Unreleased]` section and a section for the current version.
- Use Semantic Versioning: patch for compatible fixes, minor for backward-compatible additions, and major for breaking command, envelope, error-code, JSONL schema, or artifact-contract changes.
- Before publishing, update `CHANGELOG.md`, bump `__version__`, run the documented checks, and tag the release as `vX.Y.Z`.

## Knowledge Maintenance With kc

This repository is also a `kc` knowledge workspace. `kc.toml` points at `knowledge/` for durable artifacts and `.kc/` for local state.

Use `kc` to keep knowledge about the project itself current:

- Before substantial architecture, workflow, command-contract, schema, retrieval, storage, or policy changes, query existing project knowledge with `kc context prepare` or `kc source search`.
- Prefer `kc context prepare --ask "<task>" --shape knowledge_page --grounding required --target knowledge/wiki/kc-implementation.md` when planning updates to the implementation knowledge page.
- Update `knowledge/wiki/kc-implementation.md` when a change creates durable project knowledge future agents should know.
- Register new source files that should ground future knowledge with `kc source add <path> --domain kc --yes`.
- Do not re-add a source path that is already registered; use `kc source inspect <path>` and `kc lint` to detect stale registered sources.
- Knowledge pages must keep material claims cited with `[kc:src_...]` tokens, mark synthesis with `[kc:inference]`, and leave unresolved work as `[kc:todo]`.
- After editing knowledge artifacts, run `kc artifact validate --file <path>` and `kc lint`. Use `kc artifact diff --file <path>` before applying artifact changes when the workflow calls for it.
- Keep `docs/contracts.md` aligned when changing workspace resolution, source/range identity, citation grammar, mutation transactions, context packs, task states, or eval pack schemas.

If `kc lint` reports stale sources from unrelated user changes, do not overwrite those changes. Report the stale source IDs and continue with the requested work unless refreshing them is part of the task.

## Editing Rules

Preserve the deterministic CLI contract: commands should emit structured envelopes, stable errors, and machine-readable next steps. Keep mutation commands dry-run or explicit-apply by default, consistent with `kc.toml`.

Avoid committing generated or runtime files such as `.kc/` state, `__pycache__/`, `.pytest_cache/`, and `.ruff_cache/` unless the user explicitly asks for repository hygiene changes involving tracked generated files.
