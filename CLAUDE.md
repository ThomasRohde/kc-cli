# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

The bulk of project conventions live in `AGENTS.md` — imported below. Read it. This file only adds Claude-specific essentials.

@AGENTS.md

## Environment

- **Python 3.12+ required.** Packaging is Hatchling with dynamic versioning from `src/kc/__init__.py::__version__`.
- **Shell is PowerShell on Windows.** Use `$env:VAR='...'` for environment variables (not `VAR=...`); use `;` to chain.
- Editable dev install: `python -m pip install -e ".[dev]"`. Without installing, run the CLI as `$env:PYTHONPATH='src'; python -m kc <args>`.

## Verification loop

After any non-trivial change, run all four:

```powershell
pytest
ruff check .
pyright
$env:PYTHONPATH='src'; python -m kc lint
```

For focused iteration: `pytest tests/<file>.py -q` or `pytest -k <pattern>`. Pytest config (`testpaths`, `pythonpath=["src"]`, `addopts="-ra -q"`) is in `pyproject.toml` — don't pass these flags manually.

## CLI contract — do not break silently

- Default output is `--format json` with envelope shape `kc.result.v1`. Setting `$env:LLM='true'` forces JSON, quiet, no-prompt mode.
- Mutating commands are **dry-run by default**; they require `--yes` to apply. Preserve this in any new command.
- Exit codes are stable: `2` usage, `10` validation, `11` not found, `20` provenance, `30` index, `60` lock (and others). Don't reassign.
- `kc guide` is the authoritative machine-readable command manifest. `kc --version`, `kc guide`, and `src/kc/__init__.py::__version__` must stay in sync.
- The CLI contract is locked down by golden tests in `tests/goldens/v1/` (`conformance.json`, `conformance_table.txt`, `guide_commands.json`) plus `kc conformance` and `tests/test_v1_conformance.py`. If a contract change is intentional, regenerate the golden and call it out.

## No LLM inside the CLI

`kc` is a deterministic harness for external agents. **Do not add LLM or provider dependencies** to the `kc` package. The bundled `model2vec` `potion-base-8M` in `src/kc/embedding_models/` is for ranking only and is force-included into the wheel via `[tool.hatch.build.targets.wheel.force-include]` — keep it that way.

## Knowledge workspace

This repo is itself a `kc` workspace: `kc.toml` is real config, `knowledge/*.jsonl` are tracked source-of-truth artifacts. Follow the knowledge-maintenance workflow in `AGENTS.md` (`kc context prepare`, `kc source add`, citation tokens, `kc artifact validate`, `kc lint`) for any change that creates durable project knowledge. Never commit `.kc/`, `__pycache__/`, `.pytest_cache/`, or `.ruff_cache/`.
