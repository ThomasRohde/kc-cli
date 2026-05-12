# kc-cli

[![PyPI](https://img.shields.io/pypi/v/kc-cli.svg)](https://pypi.org/project/kc-cli/)
[![Python](https://img.shields.io/pypi/pyversions/kc-cli.svg)](https://pypi.org/project/kc-cli/)
[![License](https://img.shields.io/pypi/l/kc-cli.svg)](https://pypi.org/project/kc-cli/)

`kc-cli` installs `kc`, a local-first knowledge compiler for people and agents
who need grounded project knowledge instead of another pile of loose notes.

Register the source material you trust. Ask `kc` for the relevant evidence.
Let a human or external agent write the semantic content. Then use `kc` to
validate citations, preview the change, apply it safely, and keep the knowledge
workspace searchable.

`kc` does not call an LLM, does not answer questions for you, and does not add a
model provider dependency to your project. It is the deterministic harness
around that work: source registration, search, context preparation, citation
validation, safe apply, task state, and exports.

## Why use kc?

- **Give agents better inputs.** Prepare compact, cited evidence packs before an
  agent writes a page, policy, ADR, runbook, or implementation note.
- **Keep knowledge auditable.** Material claims can point back to registered
  source ranges such as Markdown lines, JSON pointers, or CSV rows.
- **Reduce drift.** `kc lint` can find stale sources, broken citations, orphaned
  artifacts, duplicate records, and stale indexes.
- **Make changes safely.** Mutation commands are dry-run or explicit-apply by
  default, with locks and snapshots around artifact application.
- **Stay local and provider-neutral.** Source data, indexes, artifacts, and task
  state live in the repository. Agents remain external and interchangeable.
- **Automate without scraping text output.** Commands emit stable structured
  envelopes by default and expose deterministic next steps.

## Good fits

| Use case | What kc gives you |
| --- | --- |
| Project implementation wiki | Pages grounded in code, ADRs, design notes, and existing docs. |
| Agent handoff packs | Search results and context bundles an external agent can use without guessing. |
| Compliance or policy knowledge | Traceable claims with citations back to local source material. |
| Onboarding material | Curated knowledge pages that can be refreshed as source files change. |
| Repository self-knowledge | A durable `knowledge/` workspace that future contributors and agents can query. |
| Retrieval evaluation | Deterministic eval packs for checking whether the right evidence is found. |
| Knowledge export | JSONL, Markdown bundle, or `llms.txt` exports from registered knowledge. |

## Install

`kc-cli` requires Python 3.12 or newer. The recommended install path is
[uv](https://docs.astral.sh/uv/):

```bash
uv tool install kc-cli
kc --help
kc --version
```

Try it without installing a persistent tool:

```bash
uvx --from kc-cli kc --help
```

The Python package name is `kc-cli`; the console command is `kc`.

`pip` works too:

```bash
python -m pip install kc-cli
```

## First workspace

A typical `kc` workflow has five steps:

1. Initialize a repository-local knowledge workspace.
2. Register source files that should ground future knowledge.
3. Search or prepare context for the question at hand.
4. Write the artifact yourself or ask an external agent to write it.
5. Validate, diff, and apply the artifact.

```bash
kc init --yes
kc source add docs/policy.md --domain policy --yes
kc --format markdown source search "ownership responsibilities" --domain policy
kc context prepare --ask "Create an ownership page" --shape knowledge_page --grounding required --target knowledge/wiki/ownership.md
kc artifact new --type knowledge_page --path knowledge/wiki/ownership.md --title "Ownership" --yes
```

Edit `knowledge/wiki/ownership.md` with citations from `kc source search` or
`kc context prepare`:

```markdown
The policy owner reviews the document every quarter. [kc:src_01HX...:L12-L18]
```

Then check and apply the result:

```bash
kc artifact validate --file knowledge/wiki/ownership.md
kc artifact diff --file knowledge/wiki/ownership.md
kc artifact apply --file knowledge/wiki/ownership.md --dry-run
kc artifact apply --file knowledge/wiki/ownership.md --yes
kc lint
```

## How kc works with agents

`kc` is intentionally not the agent. It is the compiler harness around agentic
knowledge work.

```text
trusted local sources
        |
        v
source registration and range extraction
        |
        v
search and context preparation
        |
        v
human or external agent writes semantic content
        |
        v
citation validation, diff, apply, lint, export
```

That split keeps responsibilities clear: the agent writes and synthesizes;
`kc` tracks evidence, validates provenance, and mutates repository state in a
predictable way.

## Core ideas

**Sources** are local files that ground future knowledge. Adding a source records
metadata, fingerprints, and extracted citation ranges in `knowledge/`.

```bash
kc source add docs/policy.md --domain policy --dry-run
kc source add docs/policy.md --domain policy --yes
kc source inspect docs/policy.md --ranges
```

**Ranges** are stable citation targets extracted from sources. Search commands
return ready-to-use citation tokens.

```bash
kc source search "retention period" --domain policy --limit 5
```

**Context** is the evidence package for a writing task. `kc context prepare`
gathers relevant ranges, policies, artifact matches, and next commands without
answering the question.

```bash
kc context prepare --ask "Summarize retention obligations" --shape knowledge_page --grounding required
```

**Artifacts** are durable outputs such as Markdown knowledge pages or typed
JSON/YAML documents. `kc` can create skeletons, validate citations, build a
diff plan, and apply registry updates.

```bash
kc artifact new --type knowledge_page --path knowledge/wiki/retention.md --title "Retention" --yes
kc artifact validate --file knowledge/wiki/retention.md
kc artifact apply --file knowledge/wiki/retention.md --yes
```

**Tasks** store durable state for longer external-agent workflows.

```bash
kc task start --goal "Create retention page" --target knowledge/wiki/retention.md
kc task status --task-id task_01HX
kc task resume --task-id task_01HX --event artifact_created --input @event.json
```

## Workspace layout

`kc init --yes` creates a Git-friendly durable knowledge directory and local
runtime state:

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
  .agents/
    skills/
      kc/
        SKILL.md
        agents/
          openai.yaml
        scripts/
          resolve_query_citations.py
  .kc/
    state.sqlite
    locks/
    snapshots/
    plans/
    tasks/
    cache/
```

Commit `knowledge/` and `.agents/` when they are part of the project record.
The `.agents/skills/kc/` skill gives external agents the local `kc` workflow.
Keep `.kc/` local unless you have a specific reason to share runtime state.

## Common commands

`kc guide` is the authoritative command catalog. It is designed for humans,
agents, and tool integrations.

```bash
kc guide
kc guide --section commands
kc guide --section workflows
kc guide --section errors
kc --format json guide --section commands
```

| Command | Purpose |
| --- | --- |
| `kc init` | Create the workspace layout, config, stores, and local state. |
| `kc source add` | Register a source, fingerprint it, extract ranges, and update indexes. |
| `kc source inspect` | Show source metadata, fingerprint state, and optional ranges. |
| `kc source refresh` | Refresh a changed registered source. |
| `kc source search` | Search registered source ranges and return citation tokens. |
| `kc index build` | Rebuild BM25 and semantic search indexes. |
| `kc context prepare` | Gather evidence and instructions for a writing task. |
| `kc artifact new` | Create a deterministic artifact skeleton. |
| `kc artifact validate` | Validate schema, required sections, citations, and provenance. |
| `kc artifact diff` | Build a structured apply plan before mutation. |
| `kc artifact apply` | Validate, lock, snapshot, register, and apply an artifact. |
| `kc citation check` | Check citation tokens and provenance for one or all artifacts. |
| `kc lint` | Run repository integrity checks. |
| `kc task start/status/inspect/resume` | Track longer-running agent workflows. |
| `kc eval run` | Run deterministic retrieval eval packs. |
| `kc export` | Export registered knowledge as JSONL, Markdown bundle, or `llms.txt`. |
| `kc doctor` | Inspect config, state, locks, and semantic index health. |
| `kc conformance` | Run read-only CLI contract checks. |

## Citations

Markdown artifacts use parseable citation tokens:

| Token | Meaning |
| --- | --- |
| `[kc:src_<id>:L<start>-L<end>]` | Cite a source line range. |
| `[kc:src_<id>:JP:<percent-encoded-json-pointer>]` | Cite a JSON/YAML/TOML pointer range. |
| `[kc:src_<id>:CSV:R<start>-R<end>]` | Cite CSV rows. |

Special markers make intent explicit:

| Marker | Meaning |
| --- | --- |
| `[kc:inference]` | Synthesis or interpretation based on cited facts. |
| `[kc:todo]` | Unresolved work. Valid drafts warn so agents can detect placeholders. |
| `[kc:uncited]` | Uncited content. Validation fails unless explicitly allowed. |

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

## Output and automation

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

Use `--format table` or `--format markdown` for human views when available.
Use JSON for integrations.

```bash
kc --format markdown source search "retention period"
kc --format json guide --section commands
```

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
rrf_k = 60

[index.semantic]
provider = "model2vec"
model = "potion-base-8M"
dimension = 256
purpose = "ranking_only"

[mutation]
default_dry_run = true
require_yes_for_apply = true
atomic_writes = true
create_snapshots = true
```

Built-in hybrid retrieval uses SQLite FTS5/BM25 and the bundled `model2vec`
`potion-base-8M` model for ranking only.

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

Refresh a changed source:

```bash
kc source inspect docs/policy.md --ranges
kc source refresh docs/policy.md --dry-run
kc source refresh docs/policy.md --yes
kc lint
```

Rebuild indexes:

```bash
kc index build
kc lint
```

Inspect or clear stale locks:

```bash
kc doctor locks
kc doctor locks --clear-stale --yes
```

See the complete error taxonomy:

```bash
kc guide --section errors
```

## Development

This repository uses a `src/` layout and targets Python 3.12+. Use uv for local
development:

```bash
git clone <repo-url> kc-cli
cd kc-cli
uv sync --extra dev
uv run kc --help
```

Run focused and broad checks:

```bash
uv run pytest tests/test_cli_contract.py -q
uv run pytest
uv run ruff check .
uv run pyright
uv run kc lint
```

When the package is not installed, run the CLI from the repository root:

```powershell
$env:PYTHONPATH='src'; uv run python -m kc --help
$env:PYTHONPATH='src'; uv run python -m kc lint
```

## Publishing

The PyPI package name is `kc-cli`; the installed command remains `kc`.

Versioning follows a single-source package pattern:

- The release version lives in `src/kc/__init__.py` as `__version__`.
- `pyproject.toml` uses Hatch dynamic versioning from that file.
- `kc --version` and `kc guide` must report the same version.
- `CHANGELOG.md` keeps an `[Unreleased]` section and a section for the current
  version.

Use Semantic Versioning:

- Patch: compatible fixes and documentation changes.
- Minor: backward-compatible commands, fields, options, schemas, or behavior.
- Major: breaking changes to command semantics, required envelope fields,
  stable error codes, JSONL schemas, or stored artifact contracts.

Before publishing, update `CHANGELOG.md`, bump `src/kc/__init__.py`, and tag the
release as `vX.Y.Z`.

Build and check distributions:

```bash
uv build
uvx twine check dist/*
```

Upload when ready:

```bash
uvx twine upload dist/*
```

Before publishing, verify:

```bash
uv run pytest
uv run ruff check .
uv run pyright
uv run kc --version
uv run kc guide --section compatibility
uv run kc conformance
uv run kc lint
```
