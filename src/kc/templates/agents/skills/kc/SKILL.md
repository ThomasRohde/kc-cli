---
name: kc
description: Use kc to maintain repo-local knowledge workspaces, ingest local or snapshotted remote sources, register and refresh source ranges, answer natural-language queries with grounded citations to original sources, prepare context, write cited artifacts, validate exact kc citation tokens, diff and apply artifacts safely, lint knowledge state, and manage task workflows.
---

<!-- kc-managed-agent-skill:v1 -->

# kc

## Operating Rule

Use `kc` as the deterministic harness around knowledge work. Write semantic content yourself, and use `kc` for source registration, retrieval, query answering, context preparation, citation validation, safe apply, task state, linting, and exports.

Run commands from the repository root. Prefer `kc guide --section bootstrap` or `kc guide --section workflows` when you need the current command contract.

Important boundaries:

- `kc source add` registers local files. For web or API documentation, first save a local source snapshot under `knowledge/raw/<domain>/`.
- Do not ask `kc` to summarize, classify, judge truth, or generate prose. The agent writes the semantic content.
- Do not hand-author citation line ranges. Use citation tokens returned by `kc source search`, `kc context prepare`, or `kc artifact validate`.

## Common Workflow

1. Initialize the workspace when needed:

```bash
kc init --yes
```

2. Register local source files before relying on them:

```bash
kc source add docs/policy.md --domain policy --dry-run
kc source add docs/policy.md --domain policy --yes
```

3. Gather evidence for the writing task. Prefer search queries that match the exact claim you need to make:

```bash
kc source search "ownership responsibilities" --domain policy
kc context prepare --ask "Create an ownership page" --shape knowledge_page --grounding required --target knowledge/wiki/ownership.md
```

4. Write or edit the artifact yourself. Do not ask `kc` to summarize, classify, judge truth, or generate prose.

5. Keep material claims grounded with returned `[kc:src_...]` citation tokens. Mark synthesis with `[kc:inference]` and unresolved draft work with `[kc:todo]`. If validation says a citation range is missing, search again for that exact claim and use the returned token; a visible source line is not necessarily an extracted kc range.

6. Validate, preview, and apply:

```bash
kc artifact validate --file knowledge/wiki/ownership.md
kc artifact diff --file knowledge/wiki/ownership.md
kc artifact apply --file knowledge/wiki/ownership.md --dry-run
kc artifact apply --file knowledge/wiki/ownership.md --yes
kc lint
```

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

## Citation and Artifact Rules

- Use only exact citation tokens returned by kc. Do not combine adjacent returned tokens into a wider line range.
- If one sentence needs multiple facts, cite each supporting range.
- If a material claim has no returned source range, omit it, mark it `[kc:todo]` while draft, or mark it `[kc:inference]` if it is explicit synthesis.
- Leave `source_refs: []` in frontmatter unless you know kc's structured object schema. `kc artifact apply` derives structured source refs from citation edges.
- Run both `kc artifact validate --file <path>` and `kc citation check --file <path>` before apply when editing cited artifacts.
- Treat `kc artifact diff` and `kc artifact apply --dry-run` output as the review surface before `--yes`.

## Task State

Use task commands for longer external-agent workflows or when the user asks for a durable knowledge update:

```bash
kc task start --goal "Create ownership page" --target knowledge/wiki/ownership.md
kc task status --task-id task_01HX
kc task resume --task-id task_01HX --event artifact_created --input @event.json
```

Start the task before source gathering when the work is multi-step. After the artifact validates and is applied, resume the task with the expected event payload so the task reaches `completed`.

## Parallel Work

Use subagents only for sidecar work that does not mutate the shared kc registry, such as:

- checking coverage against a source list
- inspecting noisy converted snapshots
- reviewing whether a draft artifact misses obvious topics

Keep source registration, source refresh, index builds, artifact apply, and task resume in the main thread so `.kc/state.sqlite` and JSONL stores are updated predictably.

## Guardrails

- Keep `kc` provider-neutral and local-first; do not add LLM or model-provider behavior to CLI workflows.
- Use JSON output for automation and integrations.
- Treat stale-source warnings as blocking for durable knowledge updates unless the user explicitly chooses otherwise.
- Prefer dry-run before mutation, especially for source refresh and artifact apply.
- Do not revert or delete existing kc state, snapshots, or logs unless the user explicitly asks.
- Expect `kc` to update `knowledge/*.jsonl`, `.kc/state.sqlite`, `.kc/plans/`, `.kc/snapshots/`, and task files when artifacts are applied.
