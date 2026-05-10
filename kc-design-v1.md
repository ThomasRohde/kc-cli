# kc — Knowledge Compiler Harness

Detailed design document for v1

**Status:** Draft design  
**Date:** 2026-05-10  
**Primary audience:** Codex / Claude Code / Copilot CLI implementation agents, plus human maintainers  
**Primary goal:** Build a deterministic, local-first CLI that helps an external coding/knowledge agent compile, maintain, validate, and query a durable knowledge base without the CLI itself calling an LLM.

---

## 1. Executive summary

`kc` is an agent-first CLI for maintaining a repo-local knowledge base. It is not a chatbot, not a RAG application, and not an LLM wrapper.

The driving agent — for example Codex, Claude Code, or GitHub Copilot — provides the semantic intelligence. `kc` provides deterministic infrastructure: source registration, fingerprinting, indexing, search, context preparation, artifact validation, citation checking, dry-run/apply workflows, structured diffs, locks, task state, and machine-readable next-step instructions.

The core design principle is:

> The agent is the compiler. `kc` is the compiler harness.

In v1, `kc` should help an agent do five things reliably:

1. Register and fingerprint source material.
2. Search and prepare grounded context for a knowledge task.
3. Create or update Markdown/JSON artifacts outside the CLI.
4. Validate provenance, citations, schema, and safe-write rules.
5. Apply changes atomically with structured diffs and an audit trail.

`kc` must never perform generative reasoning, summarisation, synthesis, judgement, rewriting, classification, or question answering by calling an LLM. It may use deterministic algorithms and bounded local models for retrieval only, such as FTS5/BM25, vector embeddings, duplicate detection, and hybrid ranking, provided model/version/checksum are explicit and the generated content remains external to the CLI.

---

## 2. Prior art and design inheritance

### 2.1 `archguard`

`archguard` is the closest technical prior art for the retrieval and knowledge-store side. It provides an architecture guardrails management CLI backed by full-text search and vector similarity, with AI agents as a primary user class.

`kc` should reuse or adapt these ideas:

- JSONL-backed canonical records.
- SQLite-backed index.
- FTS5/BM25 search.
- Optional small local embedding model for semantic search.
- Hybrid ranking.
- `guide` command.
- Structured JSON envelopes.
- Validation and deduplication commands.
- Stable public IDs separate from internal IDs.
- Taxonomy that starts free-form and can later be locked down.
- Conservative authoring guidance: do not invent owners, review dates, source authority, or lifecycle status.

Important difference: `archguard` is domain-specific to architecture guardrails. `kc` is a generic knowledge compiler harness. `archguard` may become one specialized artifact type or downstream corpus managed through `kc`, but `kc` should not be limited to guardrails.

### 2.2 `checkpointflow`

`checkpointflow` is the closest prior art for the agent control-plane side. It makes workflows explicit, resumable, schema-validated, and durable. It models pauses with `await_event`, emits structured envelopes, persists state, and treats waiting as a first-class state rather than a failure.

`kc` should reuse or adapt these ideas:

- Explicit agent-facing instructions in CLI output.
- Durable task state.
- `status`, `inspect`, and `resume` style commands.
- Waiting state represented structurally.
- Exit code `40` for "waiting for external event".
- Schema-validated resume payloads.
- Agent-agnostic execution: Codex, Claude Code, Copilot, CI, shell, or human operator can continue the work.

Important difference: `kc` v1 is not a general workflow engine. It should not duplicate all of `checkpointflow`. It should expose enough task/checkpoint behavior to guide the driving agent through knowledge compilation. More complex orchestration can be delegated to `checkpointflow` later.

### 2.3 CLI-MANIFEST

`kc` must follow the agent-first CLI contract:

- One structured JSON envelope for every command.
- Stable error codes and exit codes.
- Built-in `guide` command as the machine-readable source of truth.
- Strict read/write separation.
- Terse or no human prose on stdout when JSON mode is active.
- Logs/progress on stderr only.
- `LLM=true` forces agent-optimized JSON output.
- Safe mutations through `plan`, `validate`, `apply`, and `verify` style flows.
- Dry-run by default for writes.
- Atomic writes, snapshots, idempotency keys, and concurrency locks.
- Rich structured metadata for reads so agents can plan without scraping prose.

---

## 3. Scope

### 3.1 In scope for v1

V1 should deliver a small but complete local-first harness:

- Repo-local initialization.
- Source registration and fingerprinting.
- Source inspection and extraction into stable ranges.
- FTS5/BM25 search.
- Optional local embedding/vector search, disabled or explicitly configured by default.
- Hybrid search using reciprocal rank fusion or another deterministic rank-combination strategy.
- Context preparation for the external agent.
- Markdown knowledge pages with parseable citation tokens.
- JSON artifacts with schema validation.
- Artifact validation, diff, and atomic apply.
- Citation and provenance checking.
- Index rebuild and validation.
- Minimal task state with agent instructions.
- `guide` command with machine-readable schemas, command catalog, playbooks, examples, anti-patterns, and error taxonomy.
- Git-friendly files: Markdown, JSON, JSONL, TOML/YAML configuration.
- SQLite for local indexes and state cache.
- JSON envelopes for every command.
- Tests and golden fixtures.

### 3.2 Out of scope for v1

Do not build these in v1:

- Internal LLM calls.
- Chat interface.
- Autonomous background daemon.
- SaaS backend.
- Web UI.
- General workflow engine.
- Multi-user server.
- Real-time collaboration.
- Enterprise ACL enforcement.
- Direct SharePoint, Confluence, Google Drive, Teams, Slack, or GitHub API ingestion.
- Full document OCR.
- Sophisticated semantic conflict resolution.
- Automatic truth arbitration across conflicting sources.
- MCP server, unless implemented as a thin experimental adapter after the CLI is stable.

### 3.3 Allowed local model usage

The CLI must not call an LLM. However, v1 may optionally use a small local model for retrieval-only functions:

Allowed:

- Embedding generation.
- Semantic nearest-neighbor search.
- Duplicate detection.
- Similarity scoring.
- Clustering support.

Not allowed:

- Summarisation.
- Rewriting.
- Classification that assigns semantic meaning not inspectably derived from metadata or rules.
- Question answering.
- Drafting wiki content.
- Resolving contradictions.
- Choosing which claim is true.

Every local model use must be visible in command output and persisted index metadata:

```json
{
  "retrieval_model": {
    "kind": "embedding",
    "provider": "local",
    "name": "model2vec-example",
    "version": "...",
    "checksum": "sha256:...",
    "purpose": "ranking_only"
  }
}
```

---

## 4. Product thesis

Most knowledge-agent tools fail because they put too much responsibility inside the model interaction and too little responsibility into durable artifacts.

`kc` inverts this:

- The knowledge base is durable and inspectable.
- The source material is immutable or fingerprinted.
- The agent can search, inspect, and prepare context.
- The agent writes content using its own intelligence.
- The CLI validates the resulting artifacts.
- The repository records what changed and why.

The aim is compounding knowledge. A well-maintained `kc` repository should get better over time, because the agent updates stable pages and artifacts rather than repeatedly answering from raw material.

---

## 5. Conceptual model

`kc` manages five primary object types:

1. **Source** — raw material registered with a fingerprint.
2. **Source range** — a stable addressable slice of a source.
3. **Knowledge artifact** — Markdown or JSON output maintained by an agent.
4. **Task** — a durable knowledge-work request with instructions and context.
5. **Plan** — a proposed mutation with before/after fingerprints and diffs.

The agent usually interacts with them in this order:

```text
source -> source ranges -> prepared context -> artifact edits -> validation -> plan -> apply -> verify
```

---

## 6. Repository layout

Default layout:

```text
repo-root/
  kc.toml
  AGENTS.md                         # optional repo-level agent instructions
  knowledge/
    raw/                            # optional copied source files, immutable by policy
    sources.jsonl                   # registered source metadata
    source_ranges.jsonl             # extracted stable ranges
    artifacts.jsonl                 # artifact registry
    citation_edges.jsonl            # artifact-to-source links discovered/validated
    wiki/                           # compiled Markdown knowledge pages
      index.md
      log.md
    artifacts/                      # typed JSON/YAML artifacts
    schemas/                        # artifact schemas and local extensions
    evals/                          # question packs and expected evidence patterns
    exports/                        # generated exports, ignored unless configured otherwise
  .kc/
    state.sqlite                    # indexes, caches, task state, plans
    locks/
    snapshots/
    plans/
    tasks/
    cache/
    logs/
```

### 6.1 Git policy

Recommended Git behavior:

Commit:

- `kc.toml`
- `knowledge/sources.jsonl`
- `knowledge/source_ranges.jsonl`, unless ranges are very large
- `knowledge/artifacts.jsonl`
- `knowledge/citation_edges.jsonl`
- `knowledge/wiki/**`
- `knowledge/artifacts/**`
- `knowledge/schemas/**`
- `knowledge/evals/**`

Usually ignore:

- `.kc/state.sqlite`
- `.kc/cache/**`
- `.kc/locks/**`
- `.kc/logs/**`
- `knowledge/exports/**`, unless export artifacts are release deliverables

Optional:

- `knowledge/raw/**` may be committed for small, non-sensitive source sets.
- For sensitive enterprise material, store only metadata and fingerprints, not raw documents.

### 6.2 `kc.toml`

Example:

```toml
schema_version = "kc.config.v1"
project_id = "example-knowledge-base"
data_dir = "knowledge"
state_dir = ".kc"

[output]
default_format = "json"
human_format = "table"
llm_env_var = "LLM"

[source_policy]
copy_sources = false
require_fingerprint = true
require_locator = true
allow_unregistered_citations = false

[citation_policy]
required_for_material_claims = true
citation_token_pattern = "kc_v1"
fail_on_stale_source_fingerprint = true

[index]
fts_enabled = true
semantic_enabled = false
hybrid_enabled = true
rrf_k = 60

[index.semantic]
provider = "local"
model = "model2vec-placeholder"
checksum = ""
purpose = "ranking_only"

[mutation]
default_dry_run = true
require_yes_for_apply = true
atomic_writes = true
create_snapshots = true
require_idempotency_key_for_apply = false

[task]
enable_wait_exit_code = true
waiting_exit_code = 40
```

---

## 7. Data model

All records should have a stable `schema_version`, an internal ULID/UUID-style ID, timestamps, and fingerprints where relevant.

Use UTC timestamps in ISO 8601 format.

### 7.1 Source record

Stored in `knowledge/sources.jsonl` and mirrored in SQLite.

```json
{
  "schema_version": "kc.source.v1",
  "source_id": "src_01HX...",
  "uri": "file:docs/bcm-governance.md",
  "display_name": "BCM Governance Notes",
  "media_type": "text/markdown",
  "fingerprint": "sha256:...",
  "fingerprint_algorithm": "sha256-normalized-v1",
  "registered_at": "2026-05-10T06:00:00Z",
  "registered_by": "agent-or-human",
  "status": "active",
  "immutability": "fingerprinted",
  "domain": ["bcm", "enterprise-architecture"],
  "authority": {
    "level": "unknown",
    "owner": null,
    "review_date": null,
    "notes": "Do not infer authority from file location."
  },
  "metadata": {
    "original_path": "docs/bcm-governance.md",
    "repo_relative": true
  }
}
```

Status values:

- `active`
- `stale`
- `superseded`
- `missing`
- `excluded`

Authority levels:

- `unknown`
- `informal`
- `team-approved`
- `enterprise-approved`
- `regulatory`

V1 rule: if authority is not explicitly provided, set `authority.level = "unknown"`. Do not infer it.

### 7.2 Source range record

Stored in `knowledge/source_ranges.jsonl`.

```json
{
  "schema_version": "kc.source_range.v1",
  "range_id": "rng_01HX...",
  "source_id": "src_01HX...",
  "source_fingerprint": "sha256:...",
  "locator": {
    "kind": "line_range",
    "start_line": 42,
    "end_line": 58
  },
  "text_hash": "sha256:...",
  "excerpt": "Capability owners are accountable for...",
  "tokens_estimate": 180,
  "extracted_at": "2026-05-10T06:02:00Z",
  "metadata": {
    "heading_path": ["Governance", "Ownership"]
  }
}
```

Supported locator kinds in v1:

- `line_range` for text-like sources.
- `json_pointer` for JSON/YAML sources.
- `csv_row_range` for CSV sources.
- `page_text_range` for PDFs if optional PDF extraction is implemented.

### 7.3 Knowledge artifact record

Stored in `knowledge/artifacts.jsonl`.

```json
{
  "schema_version": "kc.artifact.v1",
  "artifact_id": "art_01HX...",
  "path": "knowledge/wiki/bcm/ownership.md",
  "artifact_type": "knowledge_page",
  "title": "BCM Ownership",
  "status": "draft",
  "domain": ["bcm"],
  "fingerprint": "sha256:...",
  "created_at": "2026-05-10T06:10:00Z",
  "updated_at": "2026-05-10T06:20:00Z",
  "last_validated_at": "2026-05-10T06:20:00Z",
  "validation_status": "passed",
  "source_refs": [
    {
      "source_id": "src_01HX...",
      "range_ids": ["rng_01HX..."]
    }
  ],
  "metadata": {
    "compiled_by": "external_agent",
    "agent_tool": "codex",
    "notes": "No internal LLM call by kc."
  }
}
```

Artifact types in v1:

- `knowledge_page` — Markdown page with frontmatter.
- `glossary` — JSON/Markdown controlled vocabulary artifact.
- `decision_note` — Markdown/JSON artifact capturing a decision and evidence.
- `source_index` — generated index page.
- `log_entry` — append-only knowledge log item.
- `eval_pack` — test questions and expected grounding.

### 7.4 Citation edge record

Stored in `knowledge/citation_edges.jsonl`, generated by `kc citation check` or `kc artifact validate`.

```json
{
  "schema_version": "kc.citation_edge.v1",
  "edge_id": "cite_01HX...",
  "artifact_id": "art_01HX...",
  "artifact_path": "knowledge/wiki/bcm/ownership.md",
  "artifact_locator": {
    "kind": "line_range",
    "start_line": 23,
    "end_line": 23
  },
  "citation_token": "[kc:src_01HX:L42-L58]",
  "source_id": "src_01HX...",
  "range_id": "rng_01HX...",
  "source_fingerprint_at_validation": "sha256:...",
  "validated_at": "2026-05-10T06:21:00Z",
  "status": "valid"
}
```

Statuses:

- `valid`
- `missing_source`
- `missing_range`
- `stale_source`
- `locator_mismatch`
- `invalid_token`

### 7.5 Task record

Stored in SQLite and optionally exported under `.kc/tasks/<task_id>.json`.

```json
{
  "schema_version": "kc.task.v1",
  "task_id": "task_01HX...",
  "goal": "Create a BCM ownership knowledge page from registered governance sources.",
  "status": "awaiting_agent",
  "created_at": "2026-05-10T06:30:00Z",
  "updated_at": "2026-05-10T06:31:00Z",
  "shape": "knowledge_page",
  "domain": ["bcm"],
  "candidate_sources": ["src_01HX..."],
  "candidate_ranges": ["rng_01HX..."],
  "target_artifacts": ["knowledge/wiki/bcm/ownership.md"],
  "agent_instructions": [
    "Read the candidate source ranges.",
    "Create or update the target knowledge page.",
    "Do not add material claims without kc citation tokens.",
    "Run kc artifact validate before apply."
  ],
  "next_commands": [
    "kc artifact validate --file knowledge/wiki/bcm/ownership.md",
    "kc artifact diff --file knowledge/wiki/bcm/ownership.md",
    "kc artifact apply --file knowledge/wiki/bcm/ownership.md --dry-run"
  ]
}
```

### 7.6 Plan record

Stored under `.kc/plans/<plan_id>.json` and optionally mirrored in SQLite.

```json
{
  "schema_version": "kc.plan.v1",
  "plan_id": "plan_01HX...",
  "created_at": "2026-05-10T06:40:00Z",
  "command": "artifact.apply",
  "mode": "dry_run",
  "idempotency_key": "idem_...",
  "operations": [
    {
      "op_id": "op_01",
      "kind": "write_file",
      "path": "knowledge/wiki/bcm/ownership.md",
      "before_fingerprint": "sha256:old...",
      "after_fingerprint": "sha256:new...",
      "risk": "medium",
      "diff_path": ".kc/plans/plan_01HX/ownership.diff",
      "requires_yes": true
    }
  ],
  "preconditions": [
    {
      "kind": "fingerprint_match",
      "path": "knowledge/wiki/bcm/ownership.md",
      "expected": "sha256:old..."
    }
  ],
  "postconditions": [
    {
      "kind": "artifact_validates",
      "path": "knowledge/wiki/bcm/ownership.md"
    }
  ]
}
```

---

## 8. Citation model

V1 needs a citation format that is easy for agents to write and easy for `kc` to parse.

### 8.1 Markdown citation token

Use inline citation tokens:

```markdown
Capability owners are accountable for maintaining the capability definition and its lifecycle state. [kc:src_01HX:L42-L58]
```

Multiple citations:

```markdown
The ownership model separates accountability, stewardship, and review cadence. [kc:src_01HX:L42-L58] [kc:src_01HY:L12-L20]
```

JSON/YAML artifacts should use structured citation arrays instead:

```json
{
  "claim": "Capability owners are accountable for maintaining the capability definition.",
  "citations": [
    {
      "source_id": "src_01HX...",
      "range_id": "rng_01HX..."
    }
  ]
}
```

### 8.2 Citation validation

`kc citation check` validates:

- Token syntax.
- Source exists.
- Range exists.
- Range belongs to source.
- Source fingerprint matches fingerprint recorded at range extraction.
- Locator still resolves if source is available.
- Artifact registry contains or can create an artifact record.

It does not validate semantic relevance in v1. It can warn if a citation range has low lexical overlap with the sentence it supports, but this must not become a hidden semantic judgement.

### 8.3 Material claim policy

V1 cannot reliably detect all material claims without an LLM. Therefore, `kc` should enforce what is mechanically possible:

- If an artifact declares `requires_citations: true`, every non-heading paragraph in configured sections must contain at least one citation token or an explicit marker such as `[kc:inference]`, `[kc:todo]`, or `[kc:uncited]`.
- `[kc:uncited]` fails validation unless `--allow-uncited` is used.
- `[kc:inference]` passes only in sections where inference is allowed by artifact schema.
- `[kc:todo]` passes only for draft artifacts.

Example:

```markdown
This appears to imply that ownership and stewardship are separate responsibilities. [kc:inference] [kc:src_01HX:L42-L58]
```

---

## 9. Artifact format

### 9.1 Knowledge page frontmatter

Every Markdown knowledge page should use YAML frontmatter:

```yaml
---
schema_version: kc.knowledge_page.v1
artifact_id: art_01HX...
title: BCM Ownership
status: draft
domain:
  - bcm
artifact_type: knowledge_page
requires_citations: true
source_refs:
  - source_id: src_01HX...
    ranges:
      - rng_01HX...
last_validated_at: null
---
```

Recommended body structure:

```markdown
# BCM Ownership

## Summary

Short source-backed summary. [kc:src_01HX:L42-L58]

## Source-backed facts

- Fact one. [kc:src_01HX:L42-L58]
- Fact two. [kc:src_01HY:L12-L20]

## Inferences

- Inference clearly marked as inference. [kc:inference] [kc:src_01HX:L42-L58]

## Open questions

- [kc:todo] Missing explicit owner approval date.

## Source notes

- src_01HX — BCM Governance Notes, lines 42-58.
```

### 9.2 `index.md`

`knowledge/wiki/index.md` is a generated or semi-generated entry point for humans and agents.

It should include:

- Artifact catalog by domain.
- Last validation status.
- Stale or missing sources.
- High-priority open questions.
- Links to source index and eval packs.

`kc index page-build` can generate this page in a deterministic way.

### 9.3 `log.md`

`knowledge/wiki/log.md` is append-only by policy.

Each entry should contain:

```markdown
## 2026-05-10 — Updated BCM Ownership

- Task: task_01HX...
- Plan: plan_01HX...
- Artifacts changed:
  - knowledge/wiki/bcm/ownership.md
- Sources referenced:
  - src_01HX
- Validation:
  - artifact.validate: passed
  - citation.check: passed
- Notes:
  - Created as draft because authority level is unknown.
```

`kc artifact apply` should update `log.md` if configured. The content should be deterministic and based only on the plan, not generated prose.

---

## 10. Command design

All commands must support:

- `--format json|table|markdown` where relevant.
- `--data-dir <path>`.
- `--state-dir <path>`.
- `--quiet` to suppress stderr diagnostics.
- `--request-id <id>` for traceability.
- `--no-input` to fail instead of prompting.

When `LLM=true`, default to:

- JSON output.
- No ANSI.
- No interactive prompts.
- No progress on stdout.
- Structured stderr diagnostics only if not quiet.

### 10.1 Command groups

V1 command groups:

```text
kc guide
kc init
kc source ...
kc index ...
kc context ...
kc artifact ...
kc citation ...
kc lint
kc task ...
kc eval ...
kc export ...
kc doctor
```

### 10.2 `kc guide`

Purpose: machine-readable source of truth for agents.

Commands:

```text
kc guide
kc guide --section bootstrap
kc guide --section commands
kc guide --section schemas
kc guide --section workflows
kc guide --section errors
kc guide --section examples
kc guide --section anti-patterns
kc guide --section compatibility
```

Output sections:

- CLI identity and version.
- Capability flags.
- Command catalog.
- Input/output schemas.
- Error codes and exit codes.
- Supported citation syntax.
- Artifact schemas.
- Safety rules.
- Concurrency rules.
- Agent playbooks.
- Positive and negative examples.
- Compatibility policy.

Agent bootstrap example emitted by `guide`:

```json
{
  "bootstrap_sequence": [
    "kc guide --section bootstrap",
    "kc context prepare --ask '<task>' --shape knowledge_page --grounding required",
    "Edit or create the requested artifact yourself; kc will not generate it.",
    "kc artifact validate --file <path>",
    "kc artifact diff --file <path>",
    "kc artifact apply --file <path> --dry-run",
    "kc artifact apply --file <path> --yes",
    "kc lint"
  ]
}
```

### 10.3 `kc init`

Purpose: create the repository scaffold.

Examples:

```bash
kc init
kc init --data-dir knowledge --state-dir .kc
kc init --profile ea
kc init --dry-run
```

Behavior:

- Create `kc.toml` if missing.
- Create `knowledge/` directories.
- Create initial JSONL files if missing.
- Create `.kc/` state directories.
- Initialize SQLite schema.
- Create `knowledge/wiki/index.md` and `knowledge/wiki/log.md` if missing.
- Never overwrite existing files without an explicit plan and `--yes`.

### 10.4 `kc source add`

Purpose: register a source and fingerprint it.

Examples:

```bash
kc source add docs/bcm-governance.md --domain bcm
kc source add docs/bcm-governance.md --copy --domain bcm --dry-run
kc source add https://example.invalid/policy --metadata @source-meta.json
```

V1 should support file URIs. HTTP sources may be recorded as metadata but not fetched automatically unless an explicit adapter is implemented later.

Output includes:

- Source ID.
- Fingerprint.
- Media type.
- Extracted range count.
- Whether source was copied.
- Warnings about authority or missing metadata.

### 10.5 `kc source inspect`

Purpose: inspect source metadata and ranges.

Examples:

```bash
kc source inspect src_01HX...
kc source inspect docs/bcm-governance.md
kc source inspect src_01HX... --ranges
```

Output includes:

- Full metadata.
- Current fingerprint.
- Staleness status.
- Registered ranges.
- Extracted headings if available.

### 10.6 `kc source search`

Purpose: retrieve candidate source ranges.

Examples:

```bash
kc source search "BCM ownership responsibilities"
kc source search "BCM ownership responsibilities" --domain bcm --limit 10
kc source search "managed services" --mode bm25
kc source search "managed services" --mode hybrid
```

Search modes:

- `bm25`
- `semantic`
- `hybrid`

V1 default should be `bm25` unless semantic indexing is explicitly enabled.

Result item:

```json
{
  "range_id": "rng_01HX...",
  "source_id": "src_01HX...",
  "display_name": "BCM Governance Notes",
  "locator": { "kind": "line_range", "start_line": 42, "end_line": 58 },
  "excerpt": "...",
  "scores": {
    "bm25_rank": 1,
    "semantic_rank": null,
    "hybrid_rank": 1
  },
  "citation_token": "[kc:src_01HX:L42-L58]"
}
```

### 10.7 `kc context prepare`

Purpose: prepare grounded context and instructions for the external agent.

This is a central v1 command. It should not answer the user’s question. It prepares evidence, output contract, constraints, and next commands.

Examples:

```bash
kc context prepare \
  --ask "What are the BCM ownership rules?" \
  --shape answer_with_citations \
  --domain bcm \
  --grounding required

kc context prepare \
  --ask "Create a knowledge page about BCM ownership" \
  --shape knowledge_page \
  --target knowledge/wiki/bcm/ownership.md \
  --budget max_sources=12,max_ranges=40
```

Output includes:

- Search query used.
- Candidate source ranges.
- Existing related artifacts.
- Required output shape.
- Grounding policy.
- Citation policy.
- Agent instructions.
- Validation commands.

Example result:

```json
{
  "schema_version": "kc.result.v1",
  "request_id": "req_...",
  "ok": true,
  "command": "context.prepare",
  "target": {
    "ask": "What are the BCM ownership rules?",
    "shape": "answer_with_citations"
  },
  "result": {
    "candidate_ranges": [
      {
        "range_id": "rng_01HX...",
        "source_id": "src_01HX...",
        "locator": { "kind": "line_range", "start_line": 42, "end_line": 58 },
        "excerpt": "...",
        "citation_token": "[kc:src_01HX:L42-L58]"
      }
    ],
    "existing_artifacts": [
      {
        "path": "knowledge/wiki/bcm/ownership.md",
        "status": "draft",
        "validation_status": "passed"
      }
    ],
    "agent_instructions": [
      "Use the returned source ranges for factual claims.",
      "Do not invent owner, authority, review date, or lifecycle status.",
      "If sources conflict, report the conflict instead of silently resolving it.",
      "kc does not answer the question; you must write the answer or artifact."
    ],
    "validation_commands": [
      "kc citation check --file <artifact-or-answer>",
      "kc artifact validate --file <artifact>"
    ]
  },
  "warnings": [],
  "errors": [],
  "metrics": { "duration_ms": 42 }
}
```

### 10.8 `kc artifact new`

Purpose: create a skeleton artifact from a deterministic template.

Examples:

```bash
kc artifact new --type knowledge_page --path knowledge/wiki/bcm/ownership.md --title "BCM Ownership" --dry-run
kc artifact new --type decision_note --path knowledge/wiki/decisions/adr-001.md --title "Use GitHub for BCM versioning" --yes
```

This command may generate boilerplate but not substantive domain content.

Allowed generated content:

- Frontmatter.
- Section headings.
- Empty TODO markers.
- Deterministic source notes if source IDs are provided.

Forbidden generated content:

- Summary prose.
- Claims.
- Inferences.
- Recommendations.

### 10.9 `kc artifact validate`

Purpose: validate an artifact before apply.

Examples:

```bash
kc artifact validate --file knowledge/wiki/bcm/ownership.md
kc artifact validate --file knowledge/artifacts/bcm-ownership.json --schema kc.glossary.v1
```

Checks:

- File exists.
- Frontmatter/schema exists if required.
- Artifact type is known.
- Required fields are present.
- Status transition is valid.
- Citation tokens parse.
- Citation targets exist.
- Source fingerprints are not stale.
- `[kc:uncited]` is handled according to policy.
- TODO markers are allowed only for draft artifacts.
- Domain/taxonomy values are allowed if taxonomy is locked.
- Artifact registry can be updated consistently.

### 10.10 `kc artifact diff`

Purpose: produce a structured diff and mutation plan.

Examples:

```bash
kc artifact diff --file knowledge/wiki/bcm/ownership.md
kc artifact diff --file knowledge/wiki/bcm/ownership.md --against HEAD
```

Output includes:

- File diff path.
- Before/after fingerprints.
- Registry changes.
- Citation edge changes.
- Log entry preview.
- Risk flags.

Risk flags:

- `new_artifact`
- `updates_active_artifact`
- `removes_citations`
- `adds_uncited_claim_markers`
- `stale_source_reference`
- `authority_change`
- `status_transition`
- `deletes_artifact`

### 10.11 `kc artifact apply`

Purpose: safely apply a validated artifact change.

Examples:

```bash
kc artifact apply --file knowledge/wiki/bcm/ownership.md --dry-run
kc artifact apply --file knowledge/wiki/bcm/ownership.md --yes
kc artifact apply --plan .kc/plans/plan_01HX.json --yes
```

Behavior:

- Default to dry-run.
- Validate first unless `--skip-validate` is explicitly provided. `--skip-validate` should be blocked when `LLM=true` unless config allows it.
- Acquire lock.
- Check preconditions.
- Create snapshot.
- Write atomically.
- Update registry and citation edges.
- Update log if configured.
- Release lock.
- Return structured result with changed files and fingerprints.

### 10.12 `kc citation check`

Purpose: validate citations in one file or all artifacts.

Examples:

```bash
kc citation check --file knowledge/wiki/bcm/ownership.md
kc citation check --all
kc citation check --all --fail-on-warning
```

### 10.13 `kc index build`

Purpose: rebuild search indexes.

Examples:

```bash
kc index build
kc index build --semantic
kc index build --clean
```

Behavior:

- Re-read registered sources.
- Recompute current fingerprints.
- Mark stale sources.
- Extract source ranges.
- Build/update SQLite FTS index.
- Build/update vector index if enabled.
- Store index metadata and model metadata.

### 10.14 `kc lint`

Purpose: repo-level integrity check.

Examples:

```bash
kc lint
kc lint --checks citations,stale,orphans,taxonomy
kc lint --format markdown
```

Checks:

- Missing source files.
- Stale fingerprints.
- Broken citation tokens.
- Orphan source ranges.
- Orphan artifacts.
- Duplicate artifact IDs.
- Duplicate source IDs.
- Invalid status transitions.
- Unknown taxonomy values.
- Active artifacts with TODO markers.
- Active artifacts with uncited markers.
- Artifacts not listed in index.
- Log references to unknown plan/task IDs.

### 10.15 `kc task start`

Purpose: create a durable task packet for an external agent.

Examples:

```bash
kc task start \
  --goal "Create a BCM ownership page" \
  --shape knowledge_page \
  --domain bcm \
  --target knowledge/wiki/bcm/ownership.md
```

Output status should usually be `awaiting_agent`. If configured, process exit code may be `40` to make waiting explicit.

Result includes:

- Task ID.
- Candidate ranges.
- Target artifacts.
- Agent instructions.
- Next commands.
- Resume command, if relevant.

### 10.16 `kc task status`, `inspect`, `resume`

Purpose: durable task continuation.

Examples:

```bash
kc task status --task-id task_01HX...
kc task inspect --task-id task_01HX...
kc task resume --task-id task_01HX... --event artifact_created --input @event.json
```

V1 should keep this minimal. It is not a workflow runtime.

### 10.17 `kc eval run`

Purpose: verify whether the knowledge base can support expected questions with evidence.

Examples:

```bash
kc eval run
kc eval run --pack knowledge/evals/bcm.yaml
```

V1 evals should be deterministic and retrieval-focused, not answer-generation tests.

Example eval pack:

```yaml
schema_version: kc.eval_pack.v1
id: bcm-basic
questions:
  - id: bcm-ownership-001
    ask: What are the BCM ownership responsibilities?
    expected_sources:
      - src_01HX...
    expected_terms:
      - capability owner
      - steward
    min_candidate_ranges: 1
```

### 10.18 `kc export`

Purpose: produce deterministic exports.

Examples:

```bash
kc export --format llms-txt
kc export --format markdown-bundle
kc export --format jsonl
```

V1 export formats:

- `jsonl`
- `markdown-bundle`
- `llms-txt` or `llms-full-txt` if useful

---

## 11. JSON envelope

Every command must return the same top-level shape in JSON mode.

```json
{
  "schema_version": "kc.result.v1",
  "request_id": "req_20260510_063000_7f3a",
  "ok": true,
  "command": "source.search",
  "target": {},
  "result": {},
  "warnings": [],
  "errors": [],
  "metrics": {
    "duration_ms": 42
  }
}
```

### 11.1 Required fields

- `schema_version`
- `request_id`
- `ok`
- `command`
- `target`
- `result`
- `warnings`
- `errors`
- `metrics`

`warnings` and `errors` must always be arrays. `result` must always be present; use `null` on failure.

### 11.2 Error shape

```json
{
  "code": "KC_VALIDATION_MISSING_CITATION",
  "category": "validation",
  "message": "Paragraph requires at least one citation token or explicit inference marker.",
  "exit_code": 10,
  "retryable": false,
  "suggested_action": "Add a kc citation token or mark the paragraph as [kc:inference] if allowed by schema.",
  "details": {
    "path": "knowledge/wiki/bcm/ownership.md",
    "line": 23
  }
}
```

### 11.3 Warning shape

```json
{
  "code": "KC_AUTHORITY_UNKNOWN",
  "message": "Source authority was not provided; artifact should remain draft unless reviewed.",
  "details": {
    "source_id": "src_01HX..."
  }
}
```

---

## 12. Exit codes

Use stable exit code ranges.

```text
0   Success
10  Validation error
11  Not found
12  Already exists
13  Conflict or invalid transition
20  Provenance/citation error
30  Index/build error
31  Retrieval model error
40  Waiting for external agent/user event; not a failure
50  I/O error
60  Lock/concurrency error
70  Persistence/state error
80  Unsupported feature or configuration
90  Internal error
```

Special rule: exit code `40` may be returned with `ok: true` when the command successfully created a waiting state.

Example:

```json
{
  "schema_version": "kc.result.v1",
  "ok": true,
  "command": "task.start",
  "result": {
    "status": "awaiting_agent",
    "agent_instructions": ["Create the target artifact, then run kc artifact validate."],
    "next_commands": ["kc artifact validate --file knowledge/wiki/bcm/ownership.md"]
  },
  "errors": [],
  "warnings": [],
  "metrics": { "duration_ms": 31 }
}
```

---

## 13. Safe mutation model

V1 must treat writes as dangerous by default.

### 13.1 Read/write separation

Read commands:

- `guide`
- `source inspect`
- `source search`
- `context prepare`
- `artifact validate`
- `artifact diff`
- `citation check`
- `lint`
- `task status`
- `task inspect`
- `eval run`
- `doctor`

Write commands:

- `init`
- `source add`
- `index build`
- `artifact new`
- `artifact apply`
- `task start`
- `task resume`
- `export`

All write commands must support `--dry-run` where meaningful. Destructive operations require `--yes` and should not be present in v1 unless necessary.

### 13.2 Apply lifecycle

The standard lifecycle:

```text
prepare -> external agent edits -> validate -> diff -> apply --dry-run -> apply --yes -> verify/lint
```

### 13.3 Atomic writes

For each write:

1. Acquire lock.
2. Recompute current fingerprint.
3. Check preconditions.
4. Write temporary file in same directory.
5. fsync temporary file if practical.
6. Atomic rename.
7. Update registry/state.
8. Release lock.

### 13.4 Snapshots

Before modifying existing files, create a snapshot under:

```text
.kc/snapshots/<timestamp>_<plan_id>/
```

Snapshot metadata:

```json
{
  "schema_version": "kc.snapshot.v1",
  "snapshot_id": "snap_01HX...",
  "plan_id": "plan_01HX...",
  "created_at": "2026-05-10T06:50:00Z",
  "files": [
    {
      "path": "knowledge/wiki/bcm/ownership.md",
      "fingerprint": "sha256:old...",
      "snapshot_path": ".kc/snapshots/.../ownership.md"
    }
  ]
}
```

### 13.5 Idempotency

`artifact apply` should accept `--idempotency-key`. If the same key and same plan are applied twice, the second call should return `noop: true` rather than writing again.

---

## 14. Locking and concurrency

V1 should implement simple file locks.

Lock files:

```text
.kc/locks/data-dir.lock
.kc/locks/artifact-<hash>.lock
.kc/locks/index.lock
```

Lock metadata:

```json
{
  "schema_version": "kc.lock.v1",
  "lock_id": "lock_01HX...",
  "created_at": "2026-05-10T06:55:00Z",
  "pid": 12345,
  "hostname": "machine",
  "command": "artifact.apply",
  "request_id": "req_...",
  "target": "knowledge/wiki/bcm/ownership.md"
}
```

If a lock is held, fail with:

- error code `KC_LOCK_HELD`
- exit code `60`
- `retryable: true`
- `suggested_action` including inspect or stale-lock cleanup command

Potential cleanup command:

```bash
kc doctor locks
kc doctor locks --clear-stale --yes
```

---

## 15. Search and indexing design

### 15.1 FTS5/BM25 baseline

V1 baseline should be SQLite FTS5:

- One row per source range.
- Store source ID, range ID, domain, headings, excerpt.
- Use BM25 rank.
- Support filtering by domain, source status, artifact type, and authority level.

### 15.2 Optional semantic index

Optional semantic search may use a small local embedding model.

Requirements:

- Explicitly configured.
- No network calls during indexing.
- Store model metadata.
- Store embedding dimension and checksum.
- Rebuild if model metadata changes.
- Clear error if model unavailable.

### 15.3 Hybrid ranking

If both BM25 and semantic search are enabled, use deterministic rank fusion.

Suggested approach:

```text
rrf_score = 1 / (k + bm25_rank) + 1 / (k + semantic_rank)
```

Where `k` defaults to `60`.

If a result is absent from one ranking list, omit that component.

### 15.4 Search result constraints

Search results should include enough metadata for an agent to cite without additional calls:

- `source_id`
- `range_id`
- `locator`
- `excerpt`
- `citation_token`
- `scores`
- `source_authority`
- `source_status`
- `source_fingerprint`

---

## 16. SQLite schema sketch

The SQLite database is cache/state, not the canonical knowledge base. JSONL and Markdown/JSON artifacts remain canonical.

Tables:

```sql
CREATE TABLE sources (
  source_id TEXT PRIMARY KEY,
  uri TEXT NOT NULL,
  display_name TEXT,
  media_type TEXT,
  fingerprint TEXT NOT NULL,
  status TEXT NOT NULL,
  domain_json TEXT NOT NULL,
  authority_json TEXT NOT NULL,
  record_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE source_ranges (
  range_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  source_fingerprint TEXT NOT NULL,
  locator_json TEXT NOT NULL,
  text_hash TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  heading_path_json TEXT,
  record_json TEXT NOT NULL,
  FOREIGN KEY(source_id) REFERENCES sources(source_id)
);

CREATE VIRTUAL TABLE source_ranges_fts USING fts5(
  range_id UNINDEXED,
  source_id UNINDEXED,
  domain,
  heading_path,
  excerpt,
  content=''
);

CREATE TABLE artifacts (
  artifact_id TEXT PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  artifact_type TEXT NOT NULL,
  status TEXT NOT NULL,
  fingerprint TEXT,
  record_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE citation_edges (
  edge_id TEXT PRIMARY KEY,
  artifact_id TEXT,
  artifact_path TEXT NOT NULL,
  source_id TEXT NOT NULL,
  range_id TEXT,
  citation_token TEXT NOT NULL,
  status TEXT NOT NULL,
  record_json TEXT NOT NULL
);

CREATE TABLE tasks (
  task_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  goal TEXT NOT NULL,
  record_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE plans (
  plan_id TEXT PRIMARY KEY,
  command TEXT NOT NULL,
  mode TEXT NOT NULL,
  record_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE idempotency_keys (
  key TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE index_metadata (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

---

## 17. Guide content requirements

The `guide` command must be stronger than normal help. It is the agent playbook.

Required guide sections:

### 17.1 Bootstrap

- What `kc` is.
- What `kc` refuses to do.
- How to start a task.
- How to prepare context.
- How to validate artifacts.
- How to apply safely.

### 17.2 Command catalog

For every command:

- Canonical command ID.
- Human command syntax.
- Read/write classification.
- Input schema.
- Output schema.
- Exit codes.
- Examples.
- Common errors.

### 17.3 Artifact schemas

- Markdown frontmatter schema.
- JSON artifact schema.
- Citation syntax.
- Status lifecycle.
- Required sections.

### 17.4 Agent playbooks

At minimum:

- Create new knowledge page.
- Update existing knowledge page.
- Answer question with citations without persisting an artifact.
- Add new source.
- Resolve stale source warning.
- Handle conflicting sources.
- Promote draft artifact to active.

### 17.5 Anti-patterns

The guide must explicitly warn agents not to:

- Use uncited factual claims.
- Invent authority, owner, review date, lifecycle state, or approval status.
- Resolve conflicts silently.
- Treat search rank as truth.
- Overwrite active artifacts without diff and validation.
- Use stale source ranges.
- Store sensitive raw material by default.
- Call external APIs during supposedly deterministic operations.
- Put progress logs on stdout in JSON mode.

### 17.6 Quality rubric

Example checks:

- Every material claim has a citation token or permitted inference marker.
- Draft status used when authority is incomplete.
- Source status is not stale.
- Artifact title and domain are stable.
- No duplicate artifact ID.
- No unreviewed TODO in active artifacts.
- Conflicts are reported explicitly.

---

## 18. Workflows

### 18.1 Initialize a knowledge repo

```bash
kc init --profile generic
kc guide --section bootstrap
kc doctor
```

Expected result:

- Repository scaffold exists.
- Guide is readable by agent.
- Doctor passes.

### 18.2 Add source material

```bash
kc source add docs/bcm-governance.md --domain bcm --dry-run
kc source add docs/bcm-governance.md --domain bcm --yes
kc index build
kc source search "ownership responsibilities" --domain bcm
```

Agent responsibilities:

- Provide truthful metadata if known.
- Do not infer authority.
- Review warnings.

### 18.3 Create a knowledge page

```bash
kc context prepare \
  --ask "Create a knowledge page about BCM ownership" \
  --shape knowledge_page \
  --domain bcm \
  --target knowledge/wiki/bcm/ownership.md \
  --grounding required
```

The agent then writes `knowledge/wiki/bcm/ownership.md`.

Then:

```bash
kc artifact validate --file knowledge/wiki/bcm/ownership.md
kc artifact diff --file knowledge/wiki/bcm/ownership.md
kc artifact apply --file knowledge/wiki/bcm/ownership.md --dry-run
kc artifact apply --file knowledge/wiki/bcm/ownership.md --yes
kc lint
```

### 18.4 Update a stale artifact

```bash
kc lint --checks stale,citations
kc source inspect src_01HX... --ranges
kc context prepare \
  --ask "Refresh BCM ownership page after source update" \
  --shape knowledge_page \
  --target knowledge/wiki/bcm/ownership.md
```

Agent responsibilities:

- Compare old and new source ranges.
- Preserve valid claims.
- Remove or downgrade claims no longer supported.
- Mark unresolved questions.

### 18.5 Answer a question without persisting

```bash
kc context prepare \
  --ask "What are the BCM ownership rules?" \
  --shape answer_with_citations \
  --domain bcm \
  --grounding required
```

The agent writes the answer to the user, using returned citations or source IDs. `kc` does not generate the answer.

### 18.6 Handle conflicting sources

If `context prepare` returns sources with conflicting metadata or text, it should include a warning:

```json
{
  "code": "KC_POSSIBLE_SOURCE_CONFLICT",
  "message": "Candidate ranges appear to describe different ownership models. Report the conflict instead of resolving silently."
}
```

Agent behavior:

- State the conflict.
- Cite both sides.
- Avoid choosing unless source authority clearly resolves it.
- Create an open question if updating a persistent artifact.

---

## 19. Integration with `checkpointflow`

V1 should not depend on `checkpointflow`, but should be compatible with it.

### 19.1 Recommended division of responsibility

`checkpointflow` owns:

- Long-running workflow orchestration.
- Multi-step approval flows.
- Human and agent events.
- Branching and parallelism.

`kc` owns:

- Knowledge source registry.
- Search/context preparation.
- Artifact validation.
- Citation/provenance checks.
- Safe artifact writes.

### 19.2 Example `checkpointflow` step using `kc`

```yaml
- id: prepare_context
  kind: cli
  command: >
    kc context prepare
    --ask "Create a BCM ownership page"
    --shape knowledge_page
    --domain bcm
    --target knowledge/wiki/bcm/ownership.md
  outputs:
    type: object
    required: [candidate_ranges, agent_instructions]

- id: agent_write
  kind: await_event
  audience: agent
  event_name: artifact_written
  prompt: Use kc context output to write the artifact, then resume with the file path.
  input_schema:
    type: object
    required: [path]
    properties:
      path: { type: string }
```

### 19.3 TODO integration

Future integration could allow:

```bash
kc task export-cpf --task-id task_01HX... --out workflow.yaml
```

Not v1 unless trivial.

---

## 20. Integration with `archguard`

V1 should borrow from `archguard`, not necessarily depend on it.

### 20.1 Reusable concepts

- Search/index layer.
- JSONL records.
- Public IDs.
- Validation commands.
- Deduplication strategy.
- Guide command style.
- Agent authoring safety rules.

### 20.2 Potential code reuse

Possible approaches:

1. Copy selected patterns into `kc` and evolve independently.
2. Extract a shared `agentcli-core` package later.
3. Make `archguard` a plugin/artifact type later.

V1 recommendation: avoid premature shared library extraction. Build `kc` cleanly, then compare with `archguard` after v1 stabilizes.

### 20.3 Guardrail artifact type

TODO candidate:

```text
kc artifact new --type archguard_guardrail
kc artifact export --to-archguard
kc artifact import --from-archguard
```

Not v1.

---

## 21. Implementation architecture

Recommended stack:

- Python 3.12+
- Typer for CLI
- Pydantic v2 for schemas
- SQLite standard library for state/index
- Rich for human-readable table output only
- `platformdirs` for default user paths if needed
- Optional local embedding dependency behind an extra
- `pytest` for tests
- `ruff` for linting
- `mypy` or pyright if practical

### 21.1 Package structure

```text
src/kc/
  __init__.py
  cli.py
  output.py
  errors.py
  ids.py
  config.py
  paths.py
  locks.py
  fingerprints.py
  atomic_write.py
  commands/
    guide.py
    init.py
    source.py
    index.py
    context.py
    artifact.py
    citation.py
    lint.py
    task.py
    eval.py
    export.py
    doctor.py
  models/
    envelope.py
    source.py
    source_range.py
    artifact.py
    citation.py
    task.py
    plan.py
    errors.py
  store/
    jsonl.py
    sqlite.py
    registry.py
    migrations.py
  search/
    fts.py
    semantic.py
    hybrid.py
    extract.py
  artifacts/
    markdown.py
    frontmatter.py
    schemas.py
    templates.py
    diff.py
  provenance/
    citations.py
    stale.py
    authority.py
  tasks/
    state.py
    instructions.py
  guide/
    builder.py
    examples.py
    schemas.py
  testsupport/
    fixtures.py
```

### 21.2 CLI command registration

Keep `cli.py` thin. Each command module should expose an app or command functions. All command functions return domain results; `output.py` wraps them in envelopes and handles process exit.

### 21.3 Error handling

Use typed exceptions:

```python
class KcError(Exception):
    code: str
    category: str
    exit_code: int
    retryable: bool
    suggested_action: str | None
    details: dict[str, Any]
```

All top-level command handlers must catch `KcError` and unexpected exceptions, then emit the standard envelope.

### 21.4 Deterministic IDs

Use ULID or UUIDv7-style IDs for readability and ordering.

Prefixes:

- `src_`
- `rng_`
- `art_`
- `cite_`
- `task_`
- `plan_`
- `snap_`
- `lock_`
- `req_`

Public IDs may be added later for human-facing stable references.

### 21.5 Fingerprints

Use SHA-256. Define normalization per media type.

Text normalization v1:

- Decode UTF-8.
- Normalize line endings to `\n`.
- Preserve trailing whitespace for exact file fingerprint? Use two fingerprints if needed:
  - raw fingerprint
  - normalized fingerprint

Recommendation:

- `raw_fingerprint`: exact bytes.
- `normalized_fingerprint`: text-normalized.
- Source staleness uses raw fingerprint where file is available.
- Range text hash uses normalized text.

---

## 22. Non-functional requirements

### 22.1 Determinism

Given the same repository, config, command, source files, and index metadata, `kc` should produce the same structured result, excluding request IDs, timestamps, and duration metrics.

### 22.2 Local-first

V1 should not require network access.

### 22.3 Agent usability

An agent should be able to call `kc guide` and successfully use the CLI without external docs.

### 22.4 Human usability

Human-readable output is allowed, but it is secondary. JSON mode is the contract.

### 22.5 Performance

V1 target:

- 10,000 source ranges searchable under 1 second for BM25 on a normal laptop.
- 100,000 source ranges searchable in a few seconds, acceptable for v1.
- Index rebuild should be incremental where practical but may be full rebuild initially.

### 22.6 Security and privacy

- No network calls by default.
- Do not copy raw sources by default.
- Do not store raw sensitive material unless explicitly configured.
- Redaction is TODO, not v1.
- All source registration should make raw-copy behavior explicit.

### 22.7 Compatibility

V1 should promise compatibility for:

- Envelope shape within `kc.result.v1`.
- Command IDs.
- Error codes.
- Core JSONL schemas.

Breaking changes require schema version increments.

---

## 23. Validation rules

### 23.1 Source validation

- `source_id` unique.
- `uri` present.
- Fingerprint present.
- Media type known or `application/octet-stream`.
- Domain values are kebab-case if provided.
- Authority not inferred.

### 23.2 Range validation

- `range_id` unique.
- Source exists.
- Locator valid for source type.
- Excerpt non-empty.
- Text hash present.
- Source fingerprint matches source record at extraction time or range marked stale.

### 23.3 Artifact validation

- File exists.
- Artifact ID stable and unique.
- Frontmatter valid.
- Required sections present.
- Status valid.
- Citation tokens valid.
- Draft-only markers absent from active artifacts.
- Source references point to registered sources.
- No invalid status transition.

### 23.4 Plan validation

- Operations have before/after fingerprints.
- Preconditions resolvable.
- Paths are under allowed repository directories.
- Writes do not escape repo root.
- Risk flags present for sensitive changes.

---

## 24. Error code taxonomy

Examples:

```text
KC_CONFIG_NOT_FOUND
KC_CONFIG_INVALID
KC_SOURCE_NOT_FOUND
KC_SOURCE_ALREADY_REGISTERED
KC_SOURCE_STALE
KC_SOURCE_UNSUPPORTED_MEDIA_TYPE
KC_RANGE_NOT_FOUND
KC_ARTIFACT_NOT_FOUND
KC_ARTIFACT_SCHEMA_INVALID
KC_ARTIFACT_STATUS_INVALID
KC_CITATION_INVALID_TOKEN
KC_CITATION_SOURCE_MISSING
KC_CITATION_RANGE_MISSING
KC_CITATION_STALE_SOURCE
KC_VALIDATION_MISSING_CITATION
KC_VALIDATION_TODO_IN_ACTIVE_ARTIFACT
KC_PLAN_PRECONDITION_FAILED
KC_APPLY_REQUIRES_YES
KC_APPLY_NOT_VALIDATED
KC_LOCK_HELD
KC_INDEX_BUILD_FAILED
KC_RETRIEVAL_MODEL_UNAVAILABLE
KC_UNSUPPORTED_FEATURE
KC_INTERNAL_ERROR
```

Each error must include:

- code
- category
- message
- exit code
- retryable
- suggested action
- structured details

---

## 25. Testing strategy

### 25.1 Golden envelope tests

Every command should have at least one golden JSON output test verifying the envelope shape.

### 25.2 CLI behavior tests

- `kc guide` returns valid schema.
- `kc init --dry-run` creates no files.
- `kc init --yes` creates expected files.
- `kc source add` registers file and fingerprint.
- `kc source search` returns range IDs and citation tokens.
- `kc context prepare` returns candidate ranges and agent instructions.
- `kc artifact validate` fails on missing citations.
- `kc artifact validate` passes with valid citations.
- `kc artifact apply --dry-run` does not write.
- `kc artifact apply --yes` writes atomically.
- `kc lint` detects stale source.
- `kc task start` emits waiting status and next commands.

### 25.3 Safety tests

- Writes cannot escape repo root with `../`.
- Active artifact cannot contain `[kc:todo]`.
- Stale citations fail when policy requires.
- `--skip-validate` blocked under `LLM=true` unless explicitly configured.
- Lock held returns exit code `60`.
- Waiting task returns exit code `40` if configured.

### 25.4 No-LLM tests

Add guardrails:

- No dependencies on OpenAI, Anthropic, Google Generative AI, LangChain, LlamaIndex, or other LLM-call libraries in v1 core.
- No environment variables such as `OPENAI_API_KEY` consumed by core.
- No HTTP calls in core tests.
- Semantic model module has retrieval-only interface.

### 25.5 Fixture repository

Create `tests/fixtures/basic_repo/` with:

- Two source Markdown files.
- One source with changed fingerprint.
- One valid knowledge page.
- One invalid page with missing citations.
- One stale citation.
- One eval pack.

---

## 26. Milestones

### Milestone 0 — Skeleton

Deliver:

- Python package.
- Typer CLI.
- Envelope output.
- Error handling.
- `kc guide` minimal.
- `kc init` minimal.
- Tests for envelope and init.

### Milestone 1 — Source registry and FTS search

Deliver:

- `source add`
- `source inspect`
- range extraction for Markdown/text
- SQLite schema
- FTS5 index
- `source search`
- tests

### Milestone 2 — Context preparation

Deliver:

- `context prepare`
- candidate range output
- citation token generation
- agent instructions
- existing artifact discovery
- tests

### Milestone 3 — Artifact validation

Deliver:

- Markdown frontmatter parser
- citation token parser
- artifact schema validation
- `artifact validate`
- `citation check`
- tests

### Milestone 4 — Safe apply

Deliver:

- `artifact diff`
- `artifact apply --dry-run`
- `artifact apply --yes`
- atomic writes
- snapshots
- log update
- locks
- tests

### Milestone 5 — Lint, eval, export

Deliver:

- `lint`
- deterministic retrieval evals
- `export --format jsonl`
- `export --format markdown-bundle`
- improved `guide`
- tests

### Milestone 6 — Optional semantic retrieval

Deliver only after BM25 v1 is solid:

- local embedding abstraction
- model metadata
- semantic index
- hybrid ranking
- retrieval-only tests

---

## 27. Definition of Done for v1

V1 is done when:

- A fresh repo can be initialized.
- Markdown/text sources can be registered and fingerprinted.
- Source ranges can be searched with BM25.
- `context prepare` gives an external agent enough grounded context to write a knowledge page.
- The agent can write the page manually.
- `artifact validate` checks schema and citations.
- `artifact apply` can dry-run and apply atomically.
- `lint` can detect stale citations and broken artifacts.
- `guide` is good enough that Codex can use the CLI without reading external documentation.
- All commands return the standard envelope.
- Writes are safe, locked, and test-covered.
- No core code calls an LLM or depends on LLM APIs.

---

## 28. Example end-to-end transcript

```bash
kc init --yes
```

```json
{
  "schema_version": "kc.result.v1",
  "ok": true,
  "command": "init",
  "result": {
    "created": ["kc.toml", "knowledge/", ".kc/"],
    "noop": []
  },
  "warnings": [],
  "errors": [],
  "metrics": { "duration_ms": 25 }
}
```

```bash
kc source add docs/bcm-governance.md --domain bcm --yes
```

```json
{
  "schema_version": "kc.result.v1",
  "ok": true,
  "command": "source.add",
  "result": {
    "source_id": "src_01HX...",
    "fingerprint": "sha256:...",
    "ranges_extracted": 14,
    "authority": { "level": "unknown" }
  },
  "warnings": [
    {
      "code": "KC_AUTHORITY_UNKNOWN",
      "message": "Source authority was not provided; artifacts based on this source should remain draft."
    }
  ],
  "errors": [],
  "metrics": { "duration_ms": 51 }
}
```

```bash
kc context prepare --ask "Create a BCM ownership page" --shape knowledge_page --domain bcm --target knowledge/wiki/bcm/ownership.md
```

The CLI returns candidate ranges and instructions. The external agent writes the artifact.

```bash
kc artifact validate --file knowledge/wiki/bcm/ownership.md
kc artifact diff --file knowledge/wiki/bcm/ownership.md
kc artifact apply --file knowledge/wiki/bcm/ownership.md --dry-run
kc artifact apply --file knowledge/wiki/bcm/ownership.md --yes
kc lint
```

---

## 29. TODO backlog after v1

### 29.1 Retrieval and knowledge quality

- Add semantic index with explicit model checksum.
- Add hybrid ranking tuning.
- Add duplicate source and duplicate artifact detection.
- Add contradiction candidate detection using deterministic heuristics.
- Add source authority model with review workflows.
- Add confidence signals based on source quality, recency, and corroboration.
- Add stale-claim reports.

### 29.2 Source adapters

- PDF extraction with page citations.
- DOCX extraction.
- HTML extraction.
- Confluence export ingestion.
- SharePoint/OneDrive export ingestion.
- Google Drive export ingestion.
- GitHub issue/PR/discussion ingestion.
- Teams transcript ingestion from exported files.

V1 should not call SaaS APIs directly. Future adapters may support explicit import commands.

### 29.3 Artifact types

- Architecture decision records.
- Business capability model notes.
- Guardrail records compatible with `archguard`.
- Glossaries and controlled vocabularies.
- Policy summaries.
- Research evidence matrices.
- Meeting-to-artifact compilation packs.
- `llms.txt` and `AGENTS.md` generation.

### 29.4 Agent workflow integration

- Export task to `checkpointflow` workflow.
- Import task results from `checkpointflow`.
- MCP server exposing read-only commands.
- ACP-style client/server bridge.
- GitHub PR bot integration.
- Codex/Copilot/Claude skill packs.

### 29.5 Governance and enterprise controls

- Policy profiles for regulated environments.
- Raw-source redaction.
- Sensitive data scanner hooks.
- Repository signing or attestation.
- Approval workflow for promoting draft to active.
- Review due dates.
- Ownership model.
- Evidence retention rules.

### 29.6 UX and operations

- TUI for humans.
- HTML report export.
- Mermaid/graph export of artifact-source relationships.
- Watch mode for local development, but not autonomous background mutation.
- Better onboarding templates.
- VS Code task definitions.
- PowerShell completion.

### 29.7 Engineering hardening

- Migration framework for JSONL and SQLite schemas.
- Large corpus performance tests.
- Windows path and locking hardening.
- Crash recovery tests.
- Cross-platform atomic write tests.
- Golden compatibility suite.
- `kc conformance` command for CLI-MANIFEST compliance.

---

## 30. Open design questions

1. Should `knowledge/source_ranges.jsonl` be committed by default, or should it be treated as rebuildable cache?

   Recommendation: commit it for small and medium repos because it gives stable citation IDs. For large repos, allow rebuildable mode.

2. Should semantic search be enabled in v1?

   Recommendation: implement BM25 first. Add semantic search behind an optional extra only after source/range/citation mechanics are stable.

3. Should `kc task start` return exit code `40` by default?

   Recommendation: yes when `--await-agent` or task mode is used; no for ordinary read commands. Make configurable.

4. Should `kc artifact new` create files directly?

   Recommendation: only skeletons, and still dry-run by default. Substantive content must come from the external agent.

5. Should `kc` update `log.md` automatically?

   Recommendation: yes, but only with deterministic metadata from the plan. No generated prose.

6. Should `kc` use YAML or TOML config?

   Recommendation: TOML for `kc.toml`; JSON Schema for machine validation; YAML only for human-authored eval packs if useful.

---

## 31. Initial implementation prompt for Codex

Use this as the first implementation instruction:

```text
Implement the v1 skeleton for kc as a Python 3.12+ Typer CLI.

Hard constraints:
- Do not call any LLM or include LLM provider dependencies.
- Every JSON command output must use the kc.result.v1 envelope.
- Implement kc guide and kc init first.
- Implement typed errors with stable error codes and exit codes.
- Implement --format json and respect LLM=true by forcing JSON/no ANSI/no prompts.
- Writes must support --dry-run and must not overwrite existing files without --yes.
- Add tests for envelope shape, guide output, init dry-run, and init apply.

Initial files:
- pyproject.toml
- src/kc/cli.py
- src/kc/output.py
- src/kc/errors.py
- src/kc/config.py
- src/kc/commands/guide.py
- src/kc/commands/init.py
- tests/test_guide.py
- tests/test_init.py
- tests/test_envelope.py

After skeleton passes, implement source registry and FTS search.
```

---

## 32. Summary

`kc` should be a deterministic knowledge compiler harness for external agents. Its value is not that it thinks. Its value is that it makes knowledge compilation safe, inspectable, repeatable, and testable.

The v1 design should stay disciplined:

- No internal LLM calls.
- Git-friendly artifacts.
- Strong provenance.
- Agent-readable guide.
- Prepared context, not generated answers.
- Validation before mutation.
- Dry-run before apply.
- Atomic writes and locks.
- Search and indexing borrowed from `archguard`.
- Agent instruction and waiting-state patterns borrowed from `checkpointflow`.

Build the boring rails. Let the agent do the thinking.
