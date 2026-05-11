# kc-cli

[![PyPI](https://img.shields.io/pypi/v/kc-cli.svg)](https://pypi.org/project/kc-cli/)
[![Python](https://img.shields.io/pypi/pyversions/kc-cli.svg)](https://pypi.org/project/kc-cli/)
[![License](https://img.shields.io/pypi/l/kc-cli.svg)](https://pypi.org/project/kc-cli/)

`kc-cli` installs the `kc` command: a deterministic, local-first knowledge
compiler harness for external agents.

Agents write the semantic content. `kc` handles the local mechanics around that
work: source registration, range extraction, search, context preparation,
citation validation, safe artifact apply, task state, and exports.

`kc` does not call an LLM, does not answer questions for you, and does not add a
provider dependency to your project. Optional semantic retrieval uses the
bundled `model2vec` `potion-base-8M` model for ranking only.

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [Core concepts](#core-concepts)
- [Workspace layout](#workspace-layout)
- [Command reference](#command-reference)
- [Common workflows](#common-workflows)
- [Citations](#citations)
- [Output contract](#output-contract)
- [Configuration](#configuration)
- [Safety model](#safety-model)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Publishing](#publishing)

## Install

`kc-cli` requires Python 3.12 or newer.

```bash
python -m pip install kc-cli
```

After installation, run:

```bash
kc --help
kc --version
```

The Python package name is `kc-cli`; the console command is `kc`.

### Install from source

```bash
git clone <repo-url> kc-cli
cd kc-cli
python -m pip install -e ".[dev]"
kc --help
```

When the package is not installed, run the CLI from the repository root:

```powershell
$env:PYTHONPATH='src'; python -m kc --help
```

## Quick start

Create a workspace, register source material, prepare grounded context, write an
artifact yourself or with an external agent, then validate and apply it.

```bash
kc init --yes
kc source add docs/policy.md --domain policy --yes
kc index build
kc context prepare --ask "Create an ownership page" --shape knowledge_page --target knowledge/wiki/ownership.md
kc artifact new --type knowledge_page --path knowledge/wiki/ownership.md --title "Ownership" --yes
```

Edit `knowledge/wiki/ownership.md` with material claims cited using the source
tokens returned by `kc context prepare` or `kc source search`.

```bash
kc artifact validate --file knowledge/wiki/ownership.md
kc artifact diff --file knowledge/wiki/ownership.md
kc artifact apply --file knowledge/wiki/ownership.md --dry-run
kc artifact apply --file knowledge/wiki/ownership.md --yes
kc lint
```

Use `--dry-run` before mutating commands when you want the planned change
without writing files.

## Core concepts

### Sources

Sources are local files that ground future knowledge. `kc source add` records
metadata, fingerprints, and extracted citation ranges in `knowledge/`.

```bash
kc source add docs/policy.md --domain policy --dry-run
kc source add docs/policy.md --domain policy --yes
kc source inspect docs/policy.md --ranges
```

### Source ranges

Ranges are stable citation targets extracted from registered sources. They can
refer to line ranges, JSON pointers, or CSV row ranges. Search commands return
range records with ready-to-use citation tokens.

```bash
kc source search "ownership responsibilities" --domain policy
kc source search "retention period" --mode bm25 --limit 5
```

### Context

`kc context prepare` gathers evidence and instructions for an external agent. It
does not answer the question or write the artifact.

```bash
kc context prepare --ask "Summarize retention obligations" --shape knowledge_page --grounding required
```

### Artifacts

Artifacts are durable knowledge outputs, usually Markdown knowledge pages or
typed JSON/YAML documents. `kc` can create skeletons, validate citations, build a
diff plan, and safely apply registry updates.

```bash
kc artifact new --type knowledge_page --path knowledge/wiki/retention.md --title "Retention" --yes
kc artifact validate --file knowledge/wiki/retention.md
kc artifact diff --file knowledge/wiki/retention.md
kc artifact apply --file knowledge/wiki/retention.md --yes
```

### Tasks

Tasks store durable workflow state for external-agent work.

```bash
kc task start --goal "Create retention page" --target knowledge/wiki/retention.md
kc task status --task-id task_01HX
kc task inspect --task-id task_01HX
kc task resume --task-id task_01HX --event artifact_created --input @event.json
```

## Workspace layout

`kc init --yes` creates the local project layout:

```text
repo-root/
  kc.toml
  knowledge/
    sources.jsonl
    source_ranges.jsonl
    artifacts.jsonl
    citation_edges.jsonl
    wiki/
    artifacts/
    schemas/
    evals/
    exports/
  .kc/
    state.sqlite
    locks/
    snapshots/
    plans/
    tasks/
    cache/
```

The `knowledge/` directory is durable and Git-friendly. The `.kc/` directory is
local runtime state and is normally ignored by Git.

## Command reference

All commands support the global options documented in [Output contract](#output-contract).
Use `kc guide` for a machine-readable command manifest.

| Command | Mutates | Confirmation | Purpose |
| --- | --- | --- | --- |
| `kc guide [--section SECTION]` | No | None | Emit the CLI manifest, schemas, workflows, examples, and error taxonomy. |
| `kc conformance` | No | None | Run read-only CLI contract checks. |
| `kc init --dry-run\|--yes` | Yes | Dry-run unless `--yes` | Create the repo-local layout, config, JSONL stores, and SQLite state. |
| `kc source add FILE --domain DOMAIN --dry-run\|--yes` | Yes | Dry-run unless `--yes` | Register a source, fingerprint it, extract ranges, and update indexes. |
| `kc source inspect SOURCE_OR_PATH [--ranges]` | No | None | Show source metadata, fingerprint state, and optional ranges. |
| `kc source refresh SOURCE_OR_PATH --dry-run\|--yes` | Yes | Dry-run unless `--yes` | Refresh a registered source and replace extracted ranges. |
| `kc source search QUERY [--domain DOMAIN] [--limit N] [--mode bm25\|semantic\|hybrid]` | No | None | Search source ranges and return citation tokens. |
| `kc index build [--semantic] [--clean] [--dry-run]` | Yes | Cache rebuild; `--dry-run` previews | Rebuild BM25 indexes and optionally semantic embeddings. |
| `kc context prepare --ask ASK --shape SHAPE [--domain DOMAIN] [--target PATH] [--grounding required\|optional] [--budget max_sources=N,max_ranges=N] [--mode bm25\|semantic\|hybrid]` | No | None | Emit evidence, policies, artifact matches, and next commands. |
| `kc artifact new --type TYPE --path PATH --title TITLE --dry-run\|--yes` | Yes | Dry-run unless `--yes` | Create a deterministic artifact skeleton. |
| `kc artifact validate --file PATH [--schema SCHEMA] [--allow-uncited]` | No | None | Validate artifact schema, sections, citations, and provenance. |
| `kc artifact diff --file PATH [--against BASELINE]` | No | None | Build a structured apply plan and show artifact changes. |
| `kc artifact apply --file PATH\|--plan PLAN --dry-run\|--yes [--skip-validate] [--idempotency-key KEY]` | Yes | Dry-run unless `--yes` | Validate, lock, snapshot, register, and apply an artifact safely. |
| `kc citation check --file PATH\|--all [--fail-on-warning]` | No | None | Check citation tokens and provenance for one or all artifacts. |
| `kc lint [--checks CHECKS]` | No | None | Run repository integrity checks for citations, stale sources, orphans, duplicates, index state, and log references. |
| `kc task start --goal GOAL [--shape SHAPE] [--domain DOMAIN] [--target PATH] [--await-agent/--no-await-agent]` | Yes | Task state write | Create a task and gather candidate ranges. |
| `kc task status --task-id TASK_ID` | No | None | Show compact task state and next commands. |
| `kc task inspect --task-id TASK_ID` | No | None | Show the full stored task record. |
| `kc task resume --task-id TASK_ID --event EVENT --input JSON_OR_FILE` | Yes | Task state write | Resume an awaiting task with a structured event. |
| `kc eval run --pack FILE` | No | None | Run deterministic retrieval evaluation packs. |
| `kc export --format jsonl\|markdown-bundle\|llms-txt [--out FILE]` | Yes when `--out` is provided | Writes `--out` without `--yes` | Export registered knowledge. |
| `kc doctor` | No | None | Inspect config, state, locks, and semantic index health. |
| `kc doctor locks [--clear-stale --yes]` | Yes when clearing | Dry-run unless `--clear-stale --yes` | List or clear lock files. |

### Built-in guide

`kc guide` is the authoritative command catalog.

```bash
kc guide
kc guide --section commands
kc guide --section workflows
kc guide --section errors
```

For agent/tool integrations, prefer JSON:

```bash
kc --format json guide --section commands
```

## Common workflows

### Add and search a source

```bash
kc source add docs/policy.md --domain policy --dry-run
kc source add docs/policy.md --domain policy --yes
kc source search "ownership responsibilities" --domain policy
```

### Refresh a changed source

```bash
kc source inspect docs/policy.md --ranges
kc source refresh docs/policy.md --dry-run
kc source refresh docs/policy.md --yes
kc lint
```

### Create a cited knowledge page

```bash
kc context prepare --ask "Create an ownership page" --shape knowledge_page --target knowledge/wiki/ownership.md
kc artifact new --type knowledge_page --path knowledge/wiki/ownership.md --title "Ownership" --yes
```

Write the page with citations such as:

```markdown
The policy owner reviews the document every quarter. [kc:src_01HX...:L12-L18]
```

Then validate and apply it:

```bash
kc artifact validate --file knowledge/wiki/ownership.md
kc artifact diff --file knowledge/wiki/ownership.md
kc artifact apply --file knowledge/wiki/ownership.md --dry-run
kc artifact apply --file knowledge/wiki/ownership.md --yes
```

### Check citations

```bash
kc citation check --file knowledge/wiki/ownership.md
kc citation check --all --fail-on-warning
```

### Export knowledge

```bash
kc export --format jsonl
kc export --format llms-txt
kc export --format markdown-bundle --out knowledge/exports/bundle.md
```

### Run retrieval evals

```bash
kc eval run --pack knowledge/evals/basic.yaml
```

### Inspect health

```bash
kc doctor
kc doctor locks
kc lint
```

## Citations

Markdown artifacts use parseable citation tokens:

| Token | Meaning |
| --- | --- |
| `[kc:src_<id>:L<start>-L<end>]` | Cite a source line range. |
| `[kc:src_<id>:JP:<percent-encoded-json-pointer>]` | Cite a JSON/YAML/TOML pointer range. |
| `[kc:src_<id>:CSV:R<start>-R<end>]` | Cite CSV rows. |

Special markers:

| Marker | Meaning |
| --- | --- |
| `[kc:inference]` | Marks synthesis or interpretation based on cited facts. |
| `[kc:todo]` | Marks unresolved work. Draft-only; valid draft artifacts emit a warning so agents can detect placeholders. |
| `[kc:uncited]` | Marks uncited content. Fails validation unless explicitly allowed. |

JSON artifacts should use structured citation references:

```json
{
  "citations": [
    {
      "source_id": "src_01HX...",
      "range_id": "rng_01HX..."
    }
  ]
}
```

## Output contract

The default output format is JSON. Every successful or failed JSON response uses
the `kc.result.v1` envelope:

```json
{
  "schema_version": "kc.result.v1",
  "request_id": "req_01HX...",
  "ok": true,
  "command": "source.search",
  "target": {},
  "result": {},
  "warnings": [],
  "errors": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

Command-line usage failures, such as a missing argument, are also reported in
this envelope with `KC_USAGE_ERROR` and process exit code `2`. When multiple
errors are present, the process exits with the maximum `exit_code` in the
envelope.

Global options:

| Option | Values | Default | Notes |
| --- | --- | --- | --- |
| `--format`, `-f` | `json`, `table`, `markdown` | `json` | JSON is the machine contract; table and markdown are deterministic human views. |
| `--data-dir` | Path | `knowledge` | Durable knowledge directory; workspace commands fail clearly if it does not exist. |
| `--state-dir` | Path | `.kc` | Local state directory. |
| `--quiet`, `-q` | Flag | Off | Suppress stderr diagnostics. |
| `--request-id` | String | Generated | Use a caller-provided trace ID. |
| `--no-input` | Flag | Off | Fail instead of prompting. |
| `--version`, `-V` | Flag | Off | Print version and exit. |

`LLM=true` forces JSON output, quiet mode, no ANSI, and no prompts:

```bash
LLM=true kc guide
```

PowerShell:

```powershell
$env:LLM='true'; kc guide
```

## Configuration

`kc.toml` controls local policy:

```toml
schema_version = "kc.config.v1"
project_id = "my-project"
data_dir = "knowledge"
state_dir = ".kc"

[index]
fts_enabled = true
semantic_enabled = false
hybrid_enabled = false

[mutation]
default_dry_run = true
require_yes_for_apply = true
atomic_writes = true
create_snapshots = true
```

Use command-line `--data-dir` and `--state-dir` when a workspace uses
non-default paths.

BM25 search uses SQLite FTS5 scoring. Lower scores rank better, and scores can
be negative on small or term-heavy corpora.

## Safety model

- Read commands can run in parallel.
- Write commands use `.kc/locks`.
- Most mutation commands preview changes unless `--yes` is provided.
- `artifact apply` validates, locks, rechecks preconditions, snapshots relevant
  state, then updates registries.
- Citation validation fails on missing ranges, stale sources, invalid tokens,
  and uncited material unless explicitly allowed.
- `kc` never writes semantic content for you; it validates and applies content
  written by a human or external agent.

## Troubleshooting

### Stale source

If `kc lint` reports `KC_SOURCE_STALE`, inspect and refresh the source:

```bash
kc source inspect docs/policy.md --ranges
kc source refresh docs/policy.md --dry-run
kc source refresh docs/policy.md --yes
```

### Stale or missing index

If search, context preparation, or lint reports index problems:

```bash
kc index build
kc lint
```

For semantic search:

```bash
kc index build --semantic
kc source search "ownership lifecycle" --mode semantic
```

### Lock held

If a previous write was interrupted:

```bash
kc doctor locks
kc doctor locks --clear-stale --yes
```

### Common exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `2` | Usage error |
| `10` | Validation error |
| `11` | Not found |
| `12` | Already exists |
| `13` | Conflict or invalid transition |
| `20` | Provenance or citation error |
| `30` | Index or build error |
| `31` | Retrieval model error |
| `40` | Optional waiting-state code when configured |
| `50` | I/O error |
| `60` | Lock or concurrency error |
| `70` | Persistence or state error |
| `80` | Unsupported feature or configuration |
| `90` | Internal error |

For the complete error taxonomy:

```bash
kc guide --section errors
```

## Development

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run focused and broad checks:

```bash
pytest tests/test_cli_contract.py -q
pytest
ruff check .
pyright
kc lint
```

When working without installing the package:

```powershell
$env:PYTHONPATH='src'; python -m kc --help
$env:PYTHONPATH='src'; python -m kc lint
```

## Publishing

The PyPI package name is `kc-cli`; the installed command remains `kc`.

Build and check distributions:

```bash
python -m pip install build twine
python -m build
twine check dist/*
```

Upload when ready:

```bash
twine upload dist/*
```

Before publishing, verify:

```bash
pytest
ruff check .
pyright
kc conformance
kc lint
```
