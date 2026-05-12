---
name: kc
description: Use kc to maintain repo-local knowledge workspaces, ingest local or snapshotted remote sources, register and refresh revisioned source ranges, answer natural-language queries with grounded citations to original sources, prepare durable context packs, write cited artifacts, validate exact kc citation tokens, rewrite or repair legacy citations, diff and apply artifacts safely, lint knowledge state, run retrieval evals, and manage durable task workflows.
---

<!-- kc-managed-agent-skill:v1 -->

# kc

## Operating Rule

Use `kc` as the deterministic harness around knowledge work. Write semantic content yourself, and use `kc` for source registration, retrieval, query answering, context preparation, citation validation, safe apply, task state, linting, and exports.

Run commands from the repository root, a subdirectory inside it, or with `kc --root <repo> ...`. Prefer `kc guide --section bootstrap` or `kc guide --section workflows` when you need the current command contract.

Important boundaries:

- `kc source add` registers local files. For web or API documentation, first save a local source snapshot under `knowledge/raw/<domain>/`.
- Do not ask `kc` to summarize, classify, judge truth, or generate prose. The agent writes the semantic content.
- Do not hand-author citation line ranges. Use citation tokens returned by `kc source search`, `kc context prepare`, or `kc artifact validate`.

## Workspace Bootstrap And Diagnostics

Start by discovering the workspace and current state:

```bash
kc status
kc guide --section quickstart
kc guide --section agent_contract
```

Use `kc --root <repo> ...` when you are outside the workspace, and respect `KC_ROOT` when it is already set. `kc` resolves the root from `--root`, `KC_ROOT`, `kc.toml`, `.git`, then the current directory.

Initialize or update the managed layout when needed:

```bash
kc init --dry-run
kc init --yes
```

Run diagnostics before changing state if paths, indexes, locks, or semantic search behavior look wrong:

```bash
kc doctor
kc lint
```

If a command reports a `repo-write` lock or an operation under `.kc/operations/`, inspect status and doctor output before retrying. Do not delete locks, operation records, plans, snapshots, task files, or SQLite state unless the user explicitly asks.

## Common Workflow

1. Check or initialize the workspace:

```bash
kc status
kc init --yes
```

2. Register local source files before relying on them:

```bash
kc source add docs/policy.md --domain policy --dry-run
kc source add docs/policy.md --domain policy --yes
kc source inspect docs/policy.md --ranges
```

3. Gather evidence for the writing task. Prefer search queries that match the exact claim you need to make, and write a durable context pack for longer work:

```bash
kc source search "ownership responsibilities" --domain policy
kc context prepare --ask "Create an ownership page" --shape knowledge_page --grounding required --target knowledge/wiki/ownership.md --out .kc/context/ownership.json
```

4. Write or edit the artifact yourself. Do not ask `kc` to summarize, classify, judge truth, or generate prose.

5. Keep material claims grounded with returned v2 `[kc:src_...:rng_...]` citation tokens. Mark synthesis with `[kc:inference]` and unresolved draft work with `[kc:todo]`. If validation says a citation range is missing, search again for that exact claim and use the returned token; a visible source line is not necessarily an extracted kc range.

6. Validate, preview, and apply:

```bash
kc artifact validate --file knowledge/wiki/ownership.md
kc artifact diff --file knowledge/wiki/ownership.md
kc artifact apply --file knowledge/wiki/ownership.md --dry-run
kc artifact apply --file knowledge/wiki/ownership.md --yes
kc lint
```

7. For multi-step work, keep task state current:

```bash
kc task start --goal "Create ownership page" --target knowledge/wiki/ownership.md
kc task next --task-id task_01HX
```

## Search And Context Packs

Use `kc source search` for quick evidence and `kc context prepare` when an external agent needs a complete work packet:

```bash
kc source search "approval owner responsibility" --domain policy --limit 8
kc context prepare --ask "Document approval ownership" --shape knowledge_page --grounding required --target knowledge/wiki/approval-ownership.md --out .kc/context/approval-ownership.json
```

Read `result.mode` and warnings. If `KC_RETRIEVAL_SEMANTIC_UNAVAILABLE` appears, results are still usable FTS fallback results, but you should run `kc doctor` or `kc index build --clean` if semantic ranking is expected.

When a context pack exists, treat it as the working contract: use its candidate ranges, citation policy, validation commands, and next commands. Do not scrape human text output when JSON fields are available.

## Query Answering

For user questions over a kc corpus, answer directly instead of creating an artifact unless the user asks for a durable page.

1. Identify the likely domain and run one broad search:

```bash
kc source search "How do approvals work?" --domain codex --limit 8
```

2. For compound questions, split the prompt into exact claim-style searches. Search for the support you need, not just the user's wording:

```bash
kc source search "approval modes sandbox modes Codex" --domain codex --limit 6
kc source search "managed configuration approval policy sandbox mode" --domain codex --limit 6
```

3. Open the local source snapshot when snippets are too thin or adjacent context matters. Use the returned `display_name`, `source_id`, and line range to find the registered file in `knowledge/sources.jsonl`, then read only the needed lines.

4. Resolve citations to original sources before responding. Prefer the `Source URL:` in the snapshot metadata header. If no original URL exists, cite the registered local source path.

Use the bundled helper when search output is saved or piped:

```bash
kc source search "Codex app worktrees automations" --domain codex --limit 8 | python .agents/skills/kc/scripts/resolve_query_citations.py -
kc context prepare --ask "How do Codex app worktrees work?" --domain codex | python .agents/skills/kc/scripts/resolve_query_citations.py -
```

5. Write the final answer as a documentation-style response:
   - Put the direct answer first.
   - Use short headings or bullets only when they improve scanability.
   - Cite material claims inline with Markdown links to original source URLs.
   - Do not show `[kc:src_...]` tokens to the user in transient query answers.
   - Add a short "Not found" or "Unclear" note for unsupported parts instead of guessing.

Use kc citation tokens only in working notes or durable artifacts. For durable artifacts, keep the exact `[kc:src_...]` tokens and run the artifact validation workflow.

## Remote or Bulk Source Ingestion

For remote documentation, API pages, or large source sets:

1. Discover the authoritative source list first, such as a sitemap, index page, repository tree, or user-provided list.
2. Snapshot each source to `knowledge/raw/<domain>/...` with a short metadata header:
   - source URL
   - fetched UTC timestamp
   - publisher or owner when known
   - conversion method, if any
3. Prefer official Markdown or structured exports when available.
4. Use HTML conversion only as a fallback. If `markitdown` is available, use it for HTML fallback conversion, then trim site chrome before registration when the converted page starts with navigation noise.
5. Record a manifest for bulk ingests, including total discovered, downloaded, fallbacks, failures, and post-processing.
6. Dry-run all source registrations before mutating state. Keep logs under `.kc/logs/` for large batches.
7. Register with `kc source add ... --yes`, then run `kc index build --clean` and `kc lint`.

If you clean or post-process a file after registering it, refresh the source rather than adding it again:

```bash
kc source refresh knowledge/raw/codex/app.md --dry-run
kc source refresh knowledge/raw/codex/app.md --yes
kc index build --clean
```

## Source Maintenance

Inspect before re-adding a path:

```bash
kc source inspect docs/policy.md --ranges
```

Refresh changed registered sources instead of adding duplicates:

```bash
kc source refresh docs/policy.md --dry-run
kc source refresh docs/policy.md --yes
kc index build
kc lint
```

Source IDs are path-stable and source revisions track content changes. If refresh changes same-locator text, old locator-only citations may become invalid or stale. Run citation checks and use rewrite or repair rather than preserving stale citations.

## Citation and Artifact Rules

- Use only exact citation tokens returned by kc. Do not combine adjacent returned tokens into a wider line range.
- Prefer v2 range-aware tokens such as `[kc:src_...:rng_...:L12-L18]`.
- If one sentence needs multiple facts, cite each supporting range.
- If a material claim has no returned source range, omit it, mark it `[kc:todo]` while draft, or mark it `[kc:inference]` if it is explicit synthesis.
- Leave `source_refs: []` in frontmatter unless you know kc's structured object schema. `kc artifact apply` derives structured source refs from citation edges.
- Run both `kc artifact validate --file <path>` and `kc citation check --file <path>` before apply when editing cited artifacts.
- Treat `kc artifact diff` and `kc artifact apply --dry-run` output as the review surface before `--yes`.

Use citation maintenance commands for legacy or stale citations:

```bash
kc citation check --file knowledge/wiki/ownership.md
kc citation rewrite --file knowledge/wiki/ownership.md --dry-run
kc citation rewrite --file knowledge/wiki/ownership.md --yes
kc citation repair --file knowledge/wiki/ownership.md --dry-run
```

`kc citation rewrite` is for exact legacy-to-v2 rewrites. `kc citation repair` reports deterministic candidates and only applies exact mechanical repairs.

## Artifact Workflow

Create skeletons and apply only after validation:

```bash
kc artifact new --file knowledge/wiki/ownership.md --title "Ownership" --type knowledge_page
kc artifact validate --file knowledge/wiki/ownership.md
kc citation check --file knowledge/wiki/ownership.md
kc artifact diff --file knowledge/wiki/ownership.md
kc artifact apply --file knowledge/wiki/ownership.md --dry-run
kc artifact apply --file knowledge/wiki/ownership.md --yes
```

`kc artifact diff` compares against the last applied snapshot when one exists. If the baseline is unavailable, the result declares that instead of pretending there is a stable previous version.

## Task State

Use task commands for longer external-agent workflows or when the user asks for a durable knowledge update:

```bash
kc task start --goal "Create ownership page" --target knowledge/wiki/ownership.md
kc task status --task-id task_01HX
kc task next --task-id task_01HX
kc task resume --task-id task_01HX --event artifact_created --input @event.json
```

Start the task before source gathering when the work is multi-step. Use `kc task next` after each event; after the artifact validates and is applied, resume the task with the expected event payload so the task reaches `completed`.

Typical event payload files are small JSON objects:

```json
{"path": "knowledge/wiki/ownership.md", "valid": true}
```

Use `blocked_missing_source` or `blocked_validation_failed` with a `reason` field when the task cannot move forward without user input.

## Eval, Export, And Contract Checks

Run retrieval eval packs when changing source extraction, ranking, or command contracts:

```bash
kc eval run --pack knowledge/evals/basic.yaml --out .kc/evals/basic-result.json
kc conformance
```

Use exports only after lint and citation checks are clean:

```bash
kc export --format jsonl --out knowledge/exports/kc.jsonl
kc export --format llms_txt --out knowledge/exports/llms.txt
```

## Parallel Work

Use subagents only for sidecar work that does not mutate the shared kc registry, such as:

- checking coverage against a source list
- inspecting noisy converted snapshots
- reviewing whether a draft artifact misses obvious topics

Keep source registration, source refresh, index builds, artifact apply, citation rewrite, and task resume in the main thread so `.kc/state.sqlite`, `.kc/operations/`, and JSONL stores are updated predictably.

## Guardrails

- Keep `kc` provider-neutral and local-first; do not add LLM or model-provider behavior to CLI workflows.
- Use JSON output for automation and integrations.
- Treat stale-source warnings as blocking for durable knowledge updates unless the user explicitly chooses otherwise.
- Prefer dry-run before mutation, especially for source refresh and artifact apply.
- Do not revert or delete existing kc state, snapshots, or logs unless the user explicitly asks.
- Expect mutating commands to update `knowledge/*.jsonl`, `.kc/state.sqlite`, `.kc/operations/`, `.kc/plans/`, `.kc/snapshots/`, `.kc/context/`, and task files.
