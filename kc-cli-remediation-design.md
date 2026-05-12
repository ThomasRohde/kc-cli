# kc-cli developer-ready design document: correctness, UX, and AX remediation plan

**Repository reviewed:** `ThomasRohde/kc-cli`  
**Branch reviewed:** `master`  
**Document date:** 2026-05-12  
**Target outcome:** make `kc` a valuable deterministic CLI for humans and external agents without turning it into an LLM client.

---

## 1. Executive summary

`kc-cli` has a good product thesis and a useful first implementation: a local-first Typer CLI that registers trusted sources, extracts ranges, builds local retrieval indexes, prepares evidence for external agents, validates citations, applies artifacts safely, tracks tasks, and emits stable JSON envelopes.

The gap is not the product idea. The gap is trust. For this CLI to become genuinely valuable, users and agents must be able to rely on three things:

1. **Correctness:** citations must not silently point to changed evidence, workspace paths must resolve consistently, mutations must be serialized, and apply/diff must represent the actual repository state.
2. **UX:** the first 10 minutes must be obvious; failures must explain the exact next command; search must work even when optional semantic ranking is unavailable; supported artifact types must match what the CLI can actually validate.
3. **AX:** agents need durable, machine-readable context packs, stable command contracts, citation rewrite/repair workflows, and a control plane that lets Codex or another agent work without scraping human text.

The remediation should be executed in phases. The first two phases are correctness work and should not be skipped. UX and AX work can start in parallel only after the workspace/path and citation/range contracts are settled.

---

## 2. Review basis

This review is based on source-level inspection of the repository files exposed through the GitHub connector. I did not execute the test suite in a local checkout in this session. The implementation plan below includes test commands and acceptance criteria that Codex should run in the repo.

Reviewed areas include:

- `README.md`, `AGENTS.md`, `pyproject.toml`
- CLI wiring: `src/kc/cli.py`, `src/kc/output.py`, `src/kc/errors.py`
- Workspace/config/storage: `src/kc/paths.py`, `src/kc/config.py`, `src/kc/store/jsonl.py`, `src/kc/store/sqlite.py`, `src/kc/atomic_write.py`, `src/kc/locks.py`
- Search/extraction: `src/kc/search/extract.py`, `src/kc/search/fts.py`, `src/kc/search/semantic.py`
- Provenance/artifacts: `src/kc/provenance/citations.py`, `src/kc/artifacts/markdown.py`, `src/kc/artifacts/diff.py`, `src/kc/commands/artifact.py`
- Commands: `init`, `source`, `index`, `context`, `citation`, `lint`, `doctor`, `task`, `eval`, `export`, `guide`, `conformance`
- Tests: `tests/test_cli_contract.py`, `tests/test_source_search.py`, `tests/test_artifact_flow.py`, `tests/test_semantic_search.py`, `tests/test_task_and_no_llm.py`, `tests/test_v1_conformance.py`

---

## 3. Product target

### 3.1 One-sentence target

`kc` should be a deterministic knowledge compiler harness that turns local, trusted project evidence into searchable, citable, validated knowledge artifacts and agent-ready evidence packs.

### 3.2 Non-goals

Keep these firm:

- `kc` must not call an LLM.
- `kc` must not synthesize semantic answers.
- `kc` must not silently mutate semantic content written by a human or external agent.
- `kc` must not require network access at runtime.
- `kc` must not make provenance unverifiable in order to improve convenience.

### 3.3 Success criteria

The CLI becomes valuable when:

- A new repository can run `kc init --yes`, register sources, search, prepare context, create an artifact, validate, diff, apply, lint, and export without reading source code.
- An agent can run `kc guide`, `kc context prepare`, and `kc task start` and get machine-readable next steps without scraping human-formatted text.
- A citation fails when the cited source content changes in a way that invalidates the original evidence, even if the same line numbers still exist.
- Write commands cannot corrupt JSONL or SQLite state when run concurrently.
- `kc doctor` and `kc lint` clearly identify recoverable state problems and provide exact commands to fix them.
- Tests protect the CLI contract, not just implementation details.

---

## 4. Current strengths

The repo already has several good foundations. Keep them.

### 4.1 Clear no-LLM boundary

The README and `AGENTS.md` are explicit that external agents write semantic content and `kc` handles deterministic source registration, search, context preparation, citation validation, safe apply, and task state. This is the right boundary.

### 4.2 Stable JSON envelope

`kc.result.v1` is a strong integration design. It gives agents a stable shape with `ok`, `command`, `target`, `result`, `warnings`, `errors`, and `metrics`.

### 4.3 Good error taxonomy

`KC_*` error codes and stable exit codes are a major AX win. This should be expanded, not replaced.

### 4.4 Git-friendly stores

JSONL records plus SQLite derived indexes are a sensible split:

- JSONL = durable canonical repository record.
- SQLite = local derived state/cache/index.
- `.kc/` = runtime state.

### 4.5 Useful command surface

The current command set is close to right:

- `kc init`
- `kc source add/inspect/refresh/search`
- `kc index build`
- `kc context prepare`
- `kc artifact new/validate/diff/apply`
- `kc citation check`
- `kc lint`
- `kc task start/status/inspect/resume`
- `kc eval run`
- `kc export`
- `kc doctor`
- `kc conformance`
- `kc guide`

The design should improve semantics, not churn the surface unnecessarily.

---

## 5. Priority findings

### P0 findings: must fix before broad use

#### P0-1. Citation correctness can silently fail after source refresh

Current behavior:

- Markdown citation tokens encode `source_id` plus locator, for example `[kc:src_x:L12-L18]`.
- `SourceRangeRecord.range_id` is derived from `source_id + locator`, not from the cited text hash or source revision.
- `validate_citations()` resolves the current range by source and locator.
- After `kc source refresh`, if the same line range still exists but the text changed, the citation can validate against different evidence.

Why this matters:

A user can have an artifact claim backed by line 12, refresh the source, line 12 now says something different, and validation can still pass. That is fatal for a provenance-oriented CLI.

Design direction:

- Introduce source revisions.
- Make range identity revision/content aware.
- Add range-aware citation tokens.
- Keep locator-only tokens temporarily for compatibility, but warn or fail under strict validation.

Recommended v2 token:

```text
[kc:src_<source_id>:rng_<range_id>]
```

Optional human locator suffix:

```text
[kc:src_<source_id>:rng_<range_id>:L12-L18]
```

The range ID must be content/revision aware.

#### P0-2. Workspace resolution is too dependent on current working directory

Current behavior:

- `current_paths()` roots the workspace at `Path.cwd()`.
- `state.data_dir` and `state.state_dir` are set by CLI defaults or global flags.
- `load_config()` reads `kc.toml`, but the config values are not consistently used by `current_paths()`.
- Running from a subdirectory or using custom `kc.toml` directories is fragile.

Why this matters:

Humans and agents often run commands from subdirectories. A CLI that manages repository knowledge must reliably discover the workspace root.

Design direction:

- Add a `WorkspaceResolver`.
- Discover root by walking up for `kc.toml`, then `.git`, unless `--root` or `KC_ROOT` is supplied.
- Load `kc.toml` before constructing `KcPaths`.
- Treat CLI `--data-dir` and `--state-dir` as overrides, not unconditional defaults.
- Make every path in command outputs repo-relative to the resolved root.

#### P0-3. Mutation commands do not consistently lock or transact

The guide says write commands are serialized with `.kc/locks`, but the code only visibly uses `FileLock` for artifact apply. Commands such as `source add`, `source refresh`, `index build`, `task start/resume`, `export --out`, and `init` mutate files without a shared transaction pattern.

Why this matters:

Codex or another agent can run multiple commands in parallel. Concurrent writes to JSONL and SQLite can corrupt state or lose updates.

Design direction:

- Introduce `MutationTransaction`.
- All mutating commands acquire a repo-level write lock or a precise store lock.
- JSONL writes use compare-and-swap preconditions.
- SQLite rebuild/update occurs inside the same logical transaction boundary.
- Store an operation journal so interrupted writes can be diagnosed.

#### P0-4. Artifact diff is not a real diff against registered content

Current `build_artifact_plan()` compares registered fingerprint to current file fingerprint, but it does not have registered content. The diff for existing artifacts is effectively from an empty baseline unless another mechanism supplies old content.

Why this matters:

`artifact diff` is a safety feature. It must show what will change. A fake or incomplete diff erodes trust.

Design direction:

- Store artifact snapshots at apply time.
- Diff current file against last applied snapshot for that artifact.
- If no snapshot exists, clearly mark baseline as `unavailable` and show what is known.
- Add `artifact history` and `artifact restore` later.

---

## 6. Target architecture

### 6.1 Workspace resolution

Add a central module:

```text
src/kc/workspace.py
```

Proposed API:

```python
@dataclass(frozen=True)
class Workspace:
    root: Path
    config: KcConfig
    paths: KcPaths
    source: Literal["explicit", "kc.toml", "git", "cwd"]

def resolve_workspace(
    start: Path | None = None,
    *,
    root_override: Path | None = None,
    data_dir_override: str | None = None,
    state_dir_override: str | None = None,
    require_initialized: bool = False,
) -> Workspace:
    ...
```

Resolution rules:

1. `--root` wins.
2. `KC_ROOT` wins if no `--root`.
3. Walk upward from `cwd` for `kc.toml`.
4. If no `kc.toml`, walk upward for `.git`.
5. If neither exists, use `cwd`.
6. If `require_initialized=True` and no `kc.toml`, emit `KC_CONFIG_NOT_FOUND`.

`KcPaths` should be derived from `Workspace`, not global state alone.

CLI changes:

```bash
kc --root <repo> source search "ownership"
kc --data-dir <path> --state-dir <path> doctor
```

AX changes:

- JSON envelopes should include `target.workspace_root` or `target.project_id` for commands that depend on a workspace.
- `kc doctor` should report `workspace_resolution.source`.

### 6.2 Store model

Keep JSONL canonical stores, but enforce a stricter store abstraction.

Proposed files:

```text
knowledge/
  sources.jsonl
  source_revisions.jsonl          # new
  source_ranges.jsonl             # active ranges, revision-aware
  source_ranges_history.jsonl     # optional, for stale token diagnostics
  artifacts.jsonl
  citation_edges.jsonl
  citation_edge_history.jsonl     # optional
  migrations.jsonl                # applied schema/data migrations
```

Derived state remains:

```text
.kc/
  state.sqlite
  locks/
  snapshots/
  operations/
  tasks/
  context/
  plans/
```

### 6.3 Source and range identity

Current `SourceRecord` can stay at `kc.source.v1` with additive fields to avoid a breaking schema version. Pydantic models need to tolerate extra fields if historical records contain them.

Add fields:

```python
canonical_source_key: str        # stable key, usually repo-relative URI
current_revision_id: str
first_registered_at: str
last_refreshed_at: str | None
```

Add source revision records:

```python
class SourceRevisionRecord(BaseModel):
    schema_version: Literal["kc.source_revision.v1"] = "kc.source_revision.v1"
    revision_id: str
    source_id: str
    uri: str
    raw_fingerprint: str
    normalized_fingerprint: str
    media_type: str
    extracted_at: str
    status: Literal["active", "superseded"] = "active"
    previous_revision_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Change source ID strategy:

```text
source_id = stable_id("src", canonical_uri)
revision_id = stable_id("rev", source_id, raw_fingerprint, normalized_fingerprint)
range_id = stable_id("rng", source_id, revision_id, locator, text_hash)
```

This fixes the current problem where the source ID is initially content-derived but later preserved through refresh.

### 6.4 Citation syntax

Support both token families during migration.

Current v1 locator token:

```text
[kc:src_<id>:L12-L18]
[kc:src_<id>:JP:/policy/owner]
[kc:src_<id>:CSV:R2-R2]
```

New v2 range token:

```text
[kc:src_<id>:rng_<id>]
[kc:src_<id>:rng_<id>:L12-L18]
[kc:src_<id>:rng_<id>:JP:/policy/owner]
[kc:src_<id>:rng_<id>:CSV:R2-R2]
```

Validation behavior:

| Token type | Draft artifact | Active artifact | Agent guidance |
| --- | --- | --- | --- |
| v2 range token resolves to active range | pass | pass | preferred |
| v2 range token resolves to superseded range | warning or fail depending policy | fail | run `kc citation repair` |
| v2 range token missing | fail | fail | source/range missing |
| v1 locator token resolves to active range | pass with warning | fail under strict policy after deprecation window | run `kc citation rewrite` |
| v1 locator token resolves ambiguously | fail | fail | use range ID |
| v1 locator token resolves but source changed since artifact validation | fail | fail | refresh/rewrite evidence |

New commands:

```bash
kc citation rewrite --file knowledge/wiki/ownership.md --dry-run
kc citation rewrite --file knowledge/wiki/ownership.md --yes
kc citation repair --file knowledge/wiki/ownership.md --dry-run
kc citation repair --file knowledge/wiki/ownership.md --yes
```

`rewrite` is mechanical: locator token to range token where exact match exists.  
`repair` is assisted but deterministic: find candidate replacement ranges by source, locator shift, text hash similarity, and search.

### 6.5 Retrieval architecture

Search should be useful even when semantic ranking is unavailable.

Default behavior:

- Use hybrid when semantic index is ready.
- Fall back to FTS-only with `KC_RETRIEVAL_SEMANTIC_UNAVAILABLE` warning when semantic is not ready and config permits fallback.
- Keep strict mode available for CI/eval.

Config:

```toml
[index]
default_mode = "hybrid"
allow_fts_fallback = true
rrf_k = 60

[index.semantic]
required = false
```

Optional flags:

```bash
kc source search "ownership" --explain
kc index build --strict
kc doctor --strict
```

Avoid reintroducing noisy mode flags unless needed. The repo already tests that removed retrieval options are usage errors. If adding explicit mode later, treat it as a minor feature and update the guide/conformance tests.

### 6.6 Agent context packs

`kc context prepare` should not only emit a JSON envelope. It should optionally persist a durable context pack:

```bash
kc context prepare \
  --ask "Create an ownership page" \
  --target knowledge/wiki/ownership.md \
  --shape knowledge_page \
  --out .kc/context/context_01.json
```

Context pack schema:

```json
{
  "schema_version": "kc.context_pack.v1",
  "context_id": "ctx_...",
  "created_at": "...",
  "ask": "...",
  "target": "knowledge/wiki/ownership.md",
  "grounding_policy": "required",
  "candidate_ranges": [],
  "citation_policy": {},
  "artifact_policy": {},
  "agent_instructions": [],
  "next_commands": [],
  "failure_modes": [],
  "expected_output": {
    "artifact_path": "...",
    "validation_command": "kc artifact validate --file ..."
  }
}
```

This helps Codex: it can read a file, produce an artifact, then run deterministic validation.

### 6.7 Mutation transaction

Introduce:

```text
src/kc/store/transaction.py
```

Proposed API:

```python
class MutationTransaction:
    def __init__(self, workspace: Workspace, command: str, targets: list[str]): ...
    def __enter__(self): ...
    def load_jsonl(self, store: StoreName): ...
    def stage_jsonl(self, store: StoreName, records: Sequence[BaseModel]): ...
    def stage_sqlite_rebuild(self, ...): ...
    def stage_snapshot(self, source: Path, logical_name: str): ...
    def commit(self) -> CommitResult: ...
```

Commit rules:

1. Acquire lock.
2. Record `.kc/operations/op_<id>.json` with status `started`.
3. Load current store fingerprints.
4. Compute staged output.
5. Recheck preconditions.
6. Write snapshots if needed.
7. Atomic write JSONL.
8. Update SQLite.
9. Mark operation `committed`.
10. Release lock.

`kc doctor` should surface interrupted operations and offer exact recovery commands.

---

## 7. Work packages

The work packages below are intended for Codex implementation. Each package includes scope, files, steps, tests, dependencies, and acceptance criteria.

### WP0 — Baseline contract and safety harness

**Priority:** P0  
**Can run in parallel?** No. Do first.  
**Goal:** establish a clean baseline so later changes can be merged safely.

#### Scope

- Confirm current tests pass.
- Add a review issue/backlog file or implementation plan in the repo.
- Add missing regression tests before changing behavior.
- Preserve `kc.result.v1` unless explicitly versioned.

#### Likely files

- `tests/test_cli_contract.py`
- `tests/test_source_search.py`
- `tests/test_artifact_flow.py`
- `tests/test_semantic_search.py`
- `tests/test_v1_conformance.py`
- `CHANGELOG.md`
- Optional: `docs/roadmap.md` or `knowledge/wiki/kc-implementation.md`

#### Implementation steps

1. Run:

   ```bash
   uv sync --extra dev
   uv run pytest
   uv run ruff check .
   uv run pyright
   uv run kc conformance
   ```

2. Add regression tests for:
   - Running from a subdirectory.
   - Custom `data_dir` and `state_dir` in `kc.toml`.
   - Source refresh where line locator stays the same but text changes.
   - Parallel `source add` attempts.
   - `artifact diff` for an already-applied artifact.
   - FTS fallback when semantic model unavailable.

3. Mark tests that currently fail as expected only if needed. Prefer failing tests that guide implementation.

#### Acceptance criteria

- Existing tests pass before behavior changes.
- New regression tests fail for the known issues before fixes.
- `kc conformance` remains meaningful.
- Codex has a stable set of checks to run per branch.

---

### WP1 — Workspace root, config, and path resolution

**Priority:** P0  
**Can run in parallel?** No. Other work depends on this.  
**Goal:** every command resolves the same workspace from any subdirectory and honors `kc.toml`.

#### Scope

- Add `WorkspaceResolver`.
- Integrate config loading with path construction.
- Add optional global `--root`.
- Cleanly handle uninitialized repos.

#### Likely files

- `src/kc/cli.py`
- `src/kc/paths.py`
- `src/kc/config.py`
- New: `src/kc/workspace.py`
- All commands currently using `current_paths()`
- Tests in `tests/test_cli_contract.py`, new `tests/test_workspace_resolution.py`

#### Implementation steps

1. Create `Workspace` and `resolve_workspace()`.
2. Update runtime state:
   - Add `root_override`.
   - Treat `data_dir` and `state_dir` global options as overrides.
   - Do not force CLI defaults over config when config exists.
3. Update `current_paths()` to use resolved workspace.
4. Add `current_workspace()` for commands needing config and paths.
5. Ensure `load_config()` accepts an explicit root and validates `schema_version`.
6. Add path output consistency:
   - All command result paths are repo-relative to workspace root.
   - Error details include both `path` and `repo_root` where helpful.
7. Update guide and help.

#### Tests

Add:

```python
def test_commands_work_from_subdirectory(...)
def test_kc_toml_custom_data_and_state_dirs_are_honored(...)
def test_root_override_wins(...)
def test_uninitialized_source_search_fails_with_clear_config_error(...)
```

#### Acceptance criteria

- `kc source search` works from `repo/subdir`.
- `kc.toml` `data_dir` and `state_dir` are honored without passing global flags.
- `kc doctor` reports resolved root and config source.
- No command writes `knowledge/` into the wrong subdirectory.

---

### WP2 — Source revisions, range identity, and citation v2

**Priority:** P0  
**Can run in parallel?** Start after WP1. It can run parallel with WP3/WP4 if schema contract is agreed first.  
**Goal:** citations remain trustworthy across source refreshes.

#### Scope

- Source ID becomes path-stable.
- Source revisions record content fingerprints.
- Range IDs become revision/content aware.
- Citation parser supports v1 and v2 tokens.
- Validation detects stale locator-only citations.
- Add citation rewrite/repair commands.

#### Likely files

- `src/kc/models/source.py`
- `src/kc/models/source_range.py`
- `src/kc/models/citation.py`
- `src/kc/search/extract.py`
- `src/kc/commands/source.py`
- `src/kc/provenance/citations.py`
- `src/kc/commands/citation.py`
- `src/kc/commands/artifact.py`
- `src/kc/commands/lint.py`
- `src/kc/store/sqlite.py`
- Tests: `test_source_search.py`, `test_artifact_flow.py`, new `test_citation_v2.py`

#### Implementation steps

1. Add source revision model.
2. Add `source_revisions.jsonl` path and JSONL helpers.
3. Change source ID generation:
   - `source_id = stable_id("src", uri)`
   - `revision_id = stable_id("rev", source_id, raw_fp, norm_fp)`
4. Change range ID generation:
   - `range_id = stable_id("rng", source_id, revision_id, locator, text_hash)`
5. Preserve compatibility:
   - Existing source records without `current_revision_id` get a derived migration revision.
   - Existing range records without revision fields are treated as legacy.
6. Update source search results:
   - Include `citation_token` as the preferred v2 token.
   - Include `legacy_citation_token`.
   - Include `range_id`, `revision_id`, `locator`.
7. Update citation parsing:
   - Parse v2 range tokens.
   - Parse legacy v1 locator tokens.
   - Invalid tokens continue to produce `KC_CITATION_INVALID_TOKEN`.
8. Update validation behavior:
   - v2 token validates by exact range ID and active revision.
   - v1 token validates by locator but emits `KC_CITATION_LEGACY_LOCATOR_TOKEN` warning.
   - If current range differs from last known validated range/content, fail or warn based on policy.
9. Add `kc citation rewrite`.
10. Add `kc citation repair` as a deterministic candidate generator. Do not let it invent semantic support.

#### Tests

Add high-value regressions:

```python
def test_refresh_same_locator_changed_text_makes_old_v2_citation_stale(...)
def test_legacy_locator_token_warns_and_rewrite_outputs_v2(...)
def test_range_id_changes_when_text_hash_changes(...)
def test_json_structured_citations_support_range_id(...)
def test_citation_repair_suggests_candidates_without_applying(...)
```

#### Acceptance criteria

- Old citations cannot silently pass after source content changes.
- Search emits ready-to-copy v2 citation tokens.
- Legacy artifacts still validate in draft mode with warnings.
- Active artifacts require strong citations unless a compatibility flag is used.
- `kc lint --checks citations` detects stale v1 and v2 citations.

---

### WP3 — Mutation transactions, locks, and recovery

**Priority:** P0  
**Can run in parallel?** Start after WP1. Coordinate with WP2 and WP5 because they mutate stores.  
**Goal:** all write commands are serialized, preconditioned, and recoverable.

#### Scope

- Replace ad hoc JSONL writes with a transaction helper.
- Extend locks beyond artifact apply.
- Add operation journal.
- Improve stale lock handling.

#### Likely files

- `src/kc/locks.py`
- `src/kc/store/jsonl.py`
- `src/kc/store/sqlite.py`
- New: `src/kc/store/transaction.py`
- `src/kc/commands/source.py`
- `src/kc/commands/index.py`
- `src/kc/commands/artifact.py`
- `src/kc/commands/task.py`
- `src/kc/commands/export.py`
- `src/kc/commands/init.py`
- `src/kc/commands/doctor.py`
- Tests: new `tests/test_mutation_transactions.py`

#### Implementation steps

1. Add lock scopes:
   - `repo-write`
   - `source:<source_id>`
   - `artifact:<artifact_id-or-path>`
   - `index`
   - `task:<task_id>`
2. Add lock metadata:
   - command
   - target
   - pid
   - hostname
   - created_at
   - workspace root
   - request ID
   - optional ttl/heartbeat
3. Add stale lock detection:
   - Do not clear all locks under `--clear-stale`.
   - Only clear lock if process is gone on same host or lock age exceeds configured TTL.
4. Implement `MutationTransaction`.
5. Update each mutating command.
6. Add store fingerprint preconditions:
   - Compute SHA256 of JSONL files before mutation.
   - Recheck before commit.
7. Add `.kc/operations/op_<id>.json`.
8. Update `doctor`:
   - report active locks
   - report stale locks
   - report interrupted operations
   - offer exact recovery command
9. Update guide/conformance.

#### Tests

Add:

```python
def test_source_add_lock_held_returns_kc_lock_held(...)
def test_parallel_source_add_does_not_corrupt_jsonl(...)
def test_doctor_reports_stale_lock_without_clearing_active_lock(...)
def test_interrupted_operation_is_reported_by_doctor(...)
def test_jsonl_compare_and_swap_detects_concurrent_change(...)
```

#### Acceptance criteria

- All mutating commands use locks.
- Concurrent writes either serialize or fail with `KC_LOCK_HELD` / `KC_PLAN_PRECONDITION_FAILED`.
- `doctor locks --clear-stale --yes` only clears stale locks.
- No test can produce partially written JSONL or mismatched SQLite/JSONL state.

---

### WP4 — Retrieval and extraction quality

**Priority:** P1  
**Can run in parallel?** Yes after WP1. Coordinate with WP2 for range IDs.  
**Goal:** search results are precise, robust, explainable, and useful without requiring semantic model success.

#### Scope

- Exact domain filtering.
- FTS query sanitization and ranking improvements.
- Optional semantic fallback.
- Better extraction chunks for Markdown, code, JSON/YAML/TOML, CSV.
- Search explainability.

#### Likely files

- `src/kc/search/extract.py`
- `src/kc/search/fts.py`
- `src/kc/search/semantic.py`
- `src/kc/store/sqlite.py`
- `src/kc/commands/source.py`
- `src/kc/commands/context.py`
- `src/kc/commands/index.py`
- `src/kc/commands/doctor.py`
- Tests: `tests/test_source_search.py`, `tests/test_semantic_search.py`, new `tests/test_extraction_quality.py`

#### Implementation steps

1. Replace domain `LIKE` matching with normalized exact matching.
   - Add SQLite table `source_domains(source_id, domain)`.
   - Index `(domain, source_id)`.
2. Improve FTS query handling:
   - Normalize Unicode.
   - Escape FTS5 special syntax.
   - Support phrase queries.
   - Use AND for multi-term precision, fallback to OR if no results.
3. Add `--explain`:
   - Include query tokens.
   - Include BM25 candidate count.
   - Include semantic candidate count.
   - Include RRF components.
4. Add fallback:
   - If semantic unavailable and `allow_fts_fallback=true`, return FTS results with warning.
   - If `strict` or eval requires semantic, fail with current retrieval model error.
5. Improve structured extraction:
   - JSON/YAML/TOML excerpts should include pointer and key context.
   - Example: `/policy/owner: "platform team"`, not only `"platform team"`.
6. Improve Markdown extraction:
   - Include heading path.
   - Avoid heading-only ranges unless useful.
   - Add small overlap for long sections.
   - Preserve code fence boundaries.
7. Add source context windows:
   - Result fields: `before_excerpt`, `after_excerpt` or `context_excerpt`.
   - Keep deterministic size.

#### Tests

Add:

```python
def test_domain_filter_is_exact_not_substring(...)
def test_semantic_unavailable_falls_back_to_fts_with_warning(...)
def test_structured_extraction_includes_json_pointer_context(...)
def test_markdown_extraction_does_not_emit_heading_only_when_section_has_body(...)
def test_source_search_explain_contains_score_components(...)
```

#### Acceptance criteria

- Search for domain `risk` does not match `brisk`.
- Search works in FTS-only fallback unless strict mode is requested.
- Structured source search can find keys as well as values.
- Results include enough context for an agent to write cited text accurately.

---

### WP5 — Artifact validation, diff, apply, and templates

**Priority:** P1  
**Can run in parallel?** Partly. Start after WP2/WP3 contracts are clear.  
**Goal:** artifact commands should be safe, honest, and type-correct.

#### Scope

- Real baseline diff.
- Artifact snapshots.
- Typed frontmatter/schema validation.
- Artifact-type-specific templates.
- Metadata stamping.
- Stronger source authority policy.

#### Likely files

- `src/kc/commands/artifact.py`
- `src/kc/artifacts/diff.py`
- `src/kc/artifacts/frontmatter.py`
- `src/kc/artifacts/markdown.py`
- `src/kc/models/artifact.py`
- `src/kc/models/plan.py`
- `src/kc/store/sqlite.py`
- Templates under `src/kc/templates/`
- Tests: `tests/test_artifact_flow.py`, new `tests/test_artifact_templates.py`

#### Implementation steps

1. Add artifact snapshot storage:
   - `.kc/snapshots/artifacts/<artifact_id>/<timestamp>_<fingerprint>.md`
   - Record snapshot path in `ArtifactRecord.metadata`.
2. Change `artifact diff`:
   - Existing artifact: diff last applied snapshot vs current file.
   - New artifact: diff `/dev/null` vs current file.
   - Missing snapshot: emit warning `KC_ARTIFACT_BASELINE_UNAVAILABLE`.
3. Change `artifact apply`:
   - Use `MutationTransaction`.
   - Validate before plan.
   - Revalidate after lock.
   - Snapshot previous applied content and/or current candidate.
   - Update artifact/citation registries.
   - Rebuild derived indexes or update relevant rows.
4. Add frontmatter Pydantic model:
   - `schema_version`
   - `artifact_id`
   - `title`
   - `status`
   - `domain`
   - `artifact_type`
   - `requires_citations`
   - `source_refs`
   - `last_validated_at`
5. Fix boolean parsing:
   - `"false"` must not become `True`.
6. Add templates by type:
   - `knowledge_page`
   - `glossary`
   - `decision_note`
   - `source_index`
   - `log_entry`
   - `eval_pack`
7. Or, if templates are not ready, restrict `artifact new --type` to supported types and update docs honestly.
8. Add source authority policy:
   - active artifact cannot rely only on `authority.level=unknown` unless policy allows it.
   - validation warning/fail should be configurable.
9. Add metadata stamping:
   - Applying can update `last_validated_at` and `source_refs`.
   - Because this mutates artifact content, it must be shown in the plan before apply.

#### Tests

Add:

```python
def test_artifact_diff_against_last_applied_snapshot(...)
def test_artifact_apply_revalidates_after_lock(...)
def test_requires_citations_false_string_is_parsed_as_false_or_rejected(...)
def test_each_artifact_type_new_template_validates_or_type_is_rejected(...)
def test_active_artifact_with_unknown_authority_fails_when_policy_requires_authority(...)
```

#### Acceptance criteria

- `artifact diff` is truthful.
- Apply cannot use stale validation from before lock acquisition.
- All advertised artifact types are either truly supported or not advertised.
- Frontmatter schema errors are precise and line-aware where possible.
- Active artifacts have stronger provenance checks than drafts.

---

### WP6 — UX command flow and diagnostics

**Priority:** P1  
**Can run in parallel?** Yes after WP1. Low conflict except guide/output changes.  
**Goal:** humans should know what to do next without reading implementation files.

#### Scope

- Better first-run path.
- More useful `doctor` and `lint`.
- Clear recovery commands.
- Better table/markdown views.
- Safer defaults and prompts.

#### Likely files

- `src/kc/output.py`
- `src/kc/commands/guide.py`
- `src/kc/commands/doctor.py`
- `src/kc/commands/lint.py`
- `src/kc/commands/init.py`
- `README.md`
- Tests: `tests/test_cli_contract.py`

#### Implementation steps

1. Add `kc status` as a friendly alias or high-level health command:
   - initialized?
   - sources count
   - artifacts count
   - stale sources
   - index stale?
   - next recommended command
2. Enhance `doctor`:
   - workspace root
   - config source
   - JSONL existence and parse status
   - SQLite/JSONL consistency
   - semantic model status
   - locks and operations
3. Enhance `lint`:
   - support `--fix-dry-run` for mechanical issues
   - include `next_commands`
4. Human output:
   - show next commands in table/markdown renderers.
   - keep JSON default.
5. Error UX:
   - Every `KcError` should have a useful `suggested_action`.
   - Include exact command in `details.next_commands` where deterministic.
6. Init UX:
   - `kc init --dry-run` should summarize what will be committed and what should stay local.
   - Warn if `.kc/` appears tracked by git if detectable.
7. Add quickstart guide section:
   - `kc guide --section quickstart`
   - `kc guide --section troubleshooting`

#### Tests

Add:

```python
def test_status_reports_next_command_for_uninitialized_repo(...)
def test_doctor_reports_workspace_resolution(...)
def test_errors_include_next_commands_when_possible(...)
def test_lint_index_issue_suggests_kc_index_build(...)
```

#### Acceptance criteria

- A new user can follow `kc status` and `kc guide --section quickstart`.
- Common failures include deterministic remediation.
- Human views remain deterministic and tested.
- JSON remains the default integration format.

---

### WP7 — Agent experience: context packs, task state, generated skill

**Priority:** P1  
**Can run in parallel?** Yes after WP1; best after WP2 token contract is stable.  
**Goal:** Codex and other agents can use `kc` as a control plane, not just a CLI with JSON output.

#### Scope

- Durable context packs.
- Stronger task state machine.
- Better generated `.agents/skills/kc`.
- Machine-readable recipes for Codex.
- Avoid scraping text output.

#### Likely files

- `src/kc/commands/context.py`
- `src/kc/commands/task.py`
- `src/kc/commands/guide.py`
- `src/kc/templates/agents/skills/kc/SKILL.md`
- `src/kc/templates/agents/skills/kc/agents/openai.yaml`
- `src/kc/templates/agents/skills/kc/scripts/resolve_query_citations.py`
- New models: `src/kc/models/context.py`
- Tests: `tests/test_task_and_no_llm.py`, new `tests/test_context_pack.py`

#### Implementation steps

1. Add `ContextPackRecord`.
2. Add `kc context prepare --out` and `--id`.
3. Save context packs under `.kc/context/`.
4. Add task events:
   - `artifact_created`
   - `artifact_validated`
   - `artifact_apply_dry_run`
   - `artifact_applied`
   - `blocked_missing_source`
   - `blocked_validation_failed`
5. Task state machine:
   - `created`
   - `awaiting_agent`
   - `awaiting_validation`
   - `awaiting_apply`
   - `completed`
   - `blocked`
   - `cancelled`
6. Add `kc task next --task-id`.
7. Add `kc task resume` validation per state.
8. Guide additions:
   - `kc guide --section agent_contract`
   - command recipes with expected inputs/outputs.
9. Skill update:
   - Teach agents to prefer v2 citations.
   - Teach agents to persist context packs.
   - Teach agents not to use legacy locator tokens except when rewriting.
   - Include exact command loops.
10. Add `LLM=true` contract tests:
    - JSON only.
    - no ANSI.
    - no prompts.
    - no unsafe skip-validate.

#### Tests

Add:

```python
def test_context_prepare_out_writes_context_pack(...)
def test_task_start_links_context_pack(...)
def test_task_next_returns_state_specific_commands(...)
def test_task_resume_rejects_wrong_event_for_state(...)
def test_generated_skill_mentions_v2_citations_and_context_pack_workflow(...)
```

#### Acceptance criteria

- Codex can start from `kc guide --section agent_contract`.
- Context pack contains all evidence and exact next commands.
- Task state is durable and inspectable.
- Agent skill is kept in sync by tests.

---

### WP8 — Eval, conformance, and quality gates

**Priority:** P1  
**Can run in parallel?** Yes, after WP4 retrieval contract is stable.  
**Goal:** make retrieval and CLI contract quality measurable.

#### Scope

- Stronger eval pack schema.
- Retrieval metrics.
- Golden outputs.
- Contract/conformance coverage.

#### Likely files

- `src/kc/commands/eval.py`
- `src/kc/commands/conformance.py`
- `tests/goldens/v1/*`
- `knowledge/evals/*`
- New: `src/kc/models/eval.py`
- Tests: new `tests/test_eval_packs.py`

#### Implementation steps

1. Define eval pack schema:
   - `schema_version`
   - `cases`
   - per case:
     - `id`
     - `query`
     - `domain`
     - `expected_source_ids`
     - `expected_range_ids`
     - `must_include_citation_tokens`
     - `min_recall_at_k`
2. Add metrics:
   - recall@k
   - MRR
   - pass/fail reason
3. Add `eval run --format` compatibility with existing global format.
4. Add `eval run --out`.
5. Add conformance checks for:
   - all commands have human renderer
   - all mutating commands declare confirmation
   - all errors are in guide
   - JSON envelope shape
   - no LLM/provider calls
   - generated skill exists after init
6. Add CI workflow if absent.

#### Tests

Add:

```python
def test_eval_pack_schema_validation(...)
def test_eval_expected_range_ids(...)
def test_eval_outputs_metrics(...)
def test_conformance_detects_missing_renderer_for_new_command(...)
```

#### Acceptance criteria

- Retrieval quality can be checked before release.
- New commands cannot silently skip guide/render/conformance coverage.
- `kc conformance` is useful to agents and CI.

---

### WP9 — Documentation, packaging, and release readiness

**Priority:** P2  
**Can run in parallel?** Yes after APIs stabilize.  
**Goal:** make the package installable, understandable, and releasable.

#### Scope

- README alignment.
- Changelog.
- Migration notes.
- Release checks.
- Optional CI.

#### Likely files

- `README.md`
- `CHANGELOG.md`
- `pyproject.toml`
- `AGENTS.md`
- `kc-design-v1.md`
- `knowledge/wiki/kc-implementation.md`
- `.github/workflows/*` if present or added

#### Implementation steps

1. Update README examples to v2 citations.
2. Add migration section:
   - legacy locator citations
   - source/range revision migration
   - `kc citation rewrite`
3. Add "First 10 minutes" quickstart.
4. Add "For agents" section.
5. Update `AGENTS.md` with new test commands and contracts.
6. Add CI:
   - pytest
   - ruff
   - pyright
   - conformance
7. Bump version according to SemVer:
   - If v1 tokens remain compatible: minor.
   - If active artifacts require v2 tokens by default: major or guarded behind config until major.
8. Update changelog.

#### Acceptance criteria

- README matches actual CLI behavior.
- Installation and dev commands work.
- Migration path is documented.
- Release checks pass.

---

## 8. Execution order and Codex parallelization

### 8.1 Required order

```text
Phase 0: WP0 baseline
  |
  v
Phase 1: WP1 workspace/config/root
  |
  v
Phase 2: contract freeze for schemas and citation v2
  |
  +--> WP2 source revisions and citation v2
  +--> WP3 transactions and locks
  +--> WP4 retrieval/extraction
  +--> WP6 UX diagnostics
  |
  v
Phase 3: merge correctness branches and run full test suite
  |
  +--> WP5 artifact diff/apply/templates
  +--> WP7 agent context/task/skill
  +--> WP8 eval/conformance
  |
  v
Phase 4: WP9 docs/release
```

### 8.2 Codex workstream split

Use separate branches and limit overlapping files.

#### Codex A — Workspace and baseline

**Branch:** `fix/workspace-root-config`  
**Packages:** WP0, WP1  
**File scope:**

- `src/kc/workspace.py`
- `src/kc/paths.py`
- `src/kc/config.py`
- `src/kc/cli.py`
- command imports of `current_paths()`
- workspace tests

**Do first.** Other Codex agents should not start implementation until this branch defines the resolver interface.

#### Codex B — Citation and source revision correctness

**Branch:** `fix/source-revisions-citations-v2`  
**Packages:** WP2  
**File scope:**

- models for source/range/citation
- `search/extract.py`
- `commands/source.py`
- `provenance/citations.py`
- `commands/citation.py`
- citation tests

**Can start after Codex A publishes the workspace API.** Coordinate with Codex C on range fields used by search results.

#### Codex C — Retrieval and extraction

**Branch:** `fix/retrieval-extraction-quality`  
**Packages:** WP4  
**File scope:**

- `search/fts.py`
- `search/semantic.py`
- `search/extract.py`
- `store/sqlite.py`
- `commands/source.py`
- `commands/context.py`
- retrieval tests

**Can run in parallel with Codex B** if the agreed `SourceRangeRecord` fields are stable. Avoid changing citation parsing.

#### Codex D — Transactions, locks, and apply safety

**Branch:** `fix/mutation-transactions-apply`  
**Packages:** WP3, later WP5 apply/diff  
**File scope:**

- `locks.py`
- `store/jsonl.py`
- `store/sqlite.py`
- `store/transaction.py`
- `commands/artifact.py`
- `commands/source.py`
- `commands/index.py`
- `commands/task.py`
- transaction/apply tests

**Can start WP3 after Codex A.** Defer artifact snapshot/diff work until Codex B settles citation/range identity.

#### Codex E — UX, AX, guide, skill, eval

**Branch:** `fix/ux-ax-guide-context`  
**Packages:** WP6, WP7, WP8, WP9 docs  
**File scope:**

- `output.py`
- `commands/guide.py`
- `commands/doctor.py`
- `commands/lint.py`
- `commands/context.py`
- `commands/task.py`
- templates under `src/kc/templates/agents/skills/kc/`
- README/AGENTS/CHANGELOG
- UX/AX tests

**Can start UX diagnostics after Codex A.** Defer v2 citation docs and skill updates until Codex B lands.

### 8.3 Merge strategy

1. Merge Codex A first.
2. Rebase all branches on Codex A.
3. Merge Codex B and Codex C together only after schema/search result contract is aligned.
4. Merge Codex D transaction work.
5. Merge WP5 artifact apply/diff after B + D.
6. Merge Codex E last, because guide/docs/conformance must reflect the final command behavior.

### 8.4 Parallel-safe interfaces to freeze early

Before parallel work, write down these interfaces in `docs/contracts.md` or `knowledge/wiki/kc-implementation.md`:

- `Workspace` and `KcPaths`
- `SourceRecord` additive fields
- `SourceRevisionRecord`
- `SourceRangeRecord` additive fields
- preferred citation token v2 grammar
- search result JSON fields
- mutation transaction API
- context pack schema

---

## 9. Detailed design notes

### 9.1 Citation validation state machine

For each citation token:

```text
parse token
  |
  +-- invalid grammar -> KC_CITATION_INVALID_TOKEN
  |
  +-- v2 range token
  |     |
  |     +-- source missing -> KC_CITATION_SOURCE_MISSING
  |     +-- range missing -> KC_CITATION_RANGE_MISSING
  |     +-- range source mismatch -> KC_CITATION_RANGE_MISSING / locator_mismatch
  |     +-- range superseded -> KC_CITATION_STALE_SOURCE
  |     +-- range active but source fingerprint mismatch -> KC_CITATION_STALE_SOURCE
  |     +-- valid
  |
  +-- v1 locator token
        |
        +-- source missing -> KC_CITATION_SOURCE_MISSING
        +-- no active range matches locator -> KC_CITATION_RANGE_MISSING
        +-- multiple active ranges match locator -> KC_CITATION_AMBIGUOUS
        +-- active range matches -> valid with KC_CITATION_LEGACY_LOCATOR_TOKEN warning
```

For active artifacts, default policy should eventually be:

```toml
[citation_policy]
allow_legacy_locator_tokens_for_active = false
```

During migration, allow this to be `true` with warnings.

### 9.2 Search result schema

Preferred search result shape:

```json
{
  "range_id": "rng_...",
  "source_id": "src_...",
  "revision_id": "rev_...",
  "display_name": "policy.md",
  "uri": "file:docs/policy.md",
  "domain": ["policy"],
  "authority": {
    "level": "team-approved",
    "owner": "Platform Architecture"
  },
  "locator": {
    "kind": "line_range",
    "start_line": 12,
    "end_line": 18
  },
  "excerpt": "...",
  "context_excerpt": "...",
  "citation_token": "[kc:src_...:rng_...]",
  "legacy_citation_token": "[kc:src_...:L12-L18]",
  "scores": {
    "bm25_rank": 1,
    "bm25_score": -1.2,
    "semantic_rank": 3,
    "semantic_score": 0.71,
    "hybrid_rank": 1,
    "rrf_score": 0.032
  },
  "warnings": []
}
```

### 9.3 Context pack schema

A context pack should contain enough for an external agent to work without another search call.

Minimum fields:

```json
{
  "schema_version": "kc.context_pack.v1",
  "context_id": "ctx_...",
  "request_id": "req_...",
  "created_at": "...",
  "workspace": {
    "root": "...",
    "project_id": "..."
  },
  "ask": "...",
  "shape": "knowledge_page",
  "target": "knowledge/wiki/ownership.md",
  "grounding_policy": "required",
  "candidate_ranges": [],
  "existing_artifacts": [],
  "citation_policy": {},
  "artifact_policy": {},
  "agent_instructions": [],
  "next_commands": [],
  "validation": {
    "commands": [],
    "expected_exit_codes": {
      "success": 0,
      "validation": 10,
      "provenance": 20
    }
  }
}
```

### 9.4 Artifact apply transaction

Target behavior:

```text
artifact apply --file X --yes
  |
  +-- resolve workspace
  +-- lock repo/artifact
  +-- validate current artifact
  +-- build plan from last snapshot/current registry
  +-- recheck file fingerprint after plan
  +-- snapshot prior applied version if exists
  +-- optionally stamp managed frontmatter
  +-- write artifact registry
  +-- write citation edges
  +-- update log
  +-- update SQLite
  +-- write plan record
  +-- commit transaction
```

The apply result should include:

```json
{
  "applied": true,
  "noop": false,
  "plan": {},
  "artifact": {},
  "citation_edges": 4,
  "snapshots": [],
  "changed_files": [],
  "next_commands": [
    "kc lint",
    "kc export --format llms-txt --out knowledge/exports/llms.txt"
  ]
}
```

---

## 10. Acceptance test matrix

| Area | Required regression |
| --- | --- |
| Workspace | commands work from subdirectories |
| Workspace | config `data_dir`/`state_dir` honored |
| Citations | old citation fails after source text changes at same locator |
| Citations | v2 token validates by range ID |
| Citations | legacy token rewrites to v2 |
| Source refresh | impacted artifacts include same-locator changed-text cases |
| Concurrency | parallel writes do not corrupt JSONL |
| Locks | active lock blocks mutation |
| Locks | stale lock detection is precise |
| Search | exact domain filtering |
| Search | semantic unavailable fallback |
| Search | explain output has score components |
| Extraction | structured excerpts include key/path context |
| Artifacts | each advertised type has valid template or is rejected |
| Artifacts | diff uses last applied snapshot |
| Artifacts | apply revalidates after lock |
| UX | errors include suggested next commands |
| AX | context pack is durable and complete |
| AX | task state machine rejects wrong events |
| Eval | expected range IDs checked |
| Conformance | all commands have guide contract and renderer |

---

## 11. Release and migration plan

### 11.1 Compatibility strategy

Do not break existing users immediately.

Recommended path:

1. Release minor version with v2 citation support.
2. Keep v1 locator tokens valid for draft artifacts.
3. Emit warnings for v1 locator tokens.
4. Add `kc citation rewrite`.
5. Update README and generated skill to prefer v2.
6. After one or more releases, make active artifacts fail on v1 by default.
7. Consider major version only if removing v1 support or changing envelope/schema semantics.

### 11.2 Migration command

Add:

```bash
kc migrate --dry-run
kc migrate --yes
```

Migration should:

- derive stable source IDs for legacy records only if safe
- create source revision records
- create revision-aware range IDs
- preserve old IDs in metadata
- rewrite citation edges
- offer artifact citation rewrite, not silently modify artifacts unless `--yes`

### 11.3 Changelog entries

Include:

- Added source revisions and v2 citation tokens.
- Added workspace root discovery.
- Added transaction/lock coverage for all write commands.
- Added context packs.
- Added search explain/fallback.
- Deprecated legacy locator-only citation tokens for active artifacts.

---

## 12. Concrete first Codex prompt

Use this prompt to start implementation with Codex A:

```text
You are working in ThomasRohde/kc-cli.

Goal: implement WP1 from docs/kc-cli-remediation-design.md: workspace root/config/path resolution.

Constraints:
- Preserve kc.result.v1 envelope.
- Do not add LLM/provider behavior.
- Keep JSON default.
- Keep existing command names.
- Add tests first for subdirectory execution and kc.toml custom data_dir/state_dir.
- Implement a WorkspaceResolver in src/kc/workspace.py.
- Update current_paths() and config loading so commands use the resolved workspace.
- Add --root global option if feasible.
- Update kc doctor and kc guide to expose workspace resolution.
- Run pytest, ruff, pyright, kc conformance.
```

After WP1 merges, use parallel Codex prompts for WP2/WP3/WP4/WP6 with file scopes from section 8.

---

## 13. Implementation risk register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Citation v2 breaks current artifacts | High | support legacy tokens with warnings; add rewrite command |
| Source ID migration invalidates existing stores | High | keep additive fields; preserve legacy IDs in metadata; migration dry-run |
| Multiple Codex branches edit same files | Medium | freeze interfaces; split file scopes; merge WP1 first |
| Semantic fallback weakens retrieval quality | Medium | warnings, strict mode for eval/CI, retrieval metrics |
| Transaction layer slows small commands | Low | keep implementation simple; only lock writes |
| Artifact apply stamping surprises users | Medium | show metadata stamping in diff plan; allow config |
| Too many commands hurt UX | Medium | keep advanced commands under citation/task/doctor; guide explains workflows |
| Conformance tests become brittle | Medium | test contract fields, not incidental ordering unless ordering is part of contract |

---

## 14. Final definition of done

The remediation is done when:

- `uv run pytest`, `uv run ruff check .`, `uv run pyright`, and `uv run kc conformance` pass.
- Running from any subdirectory uses the same workspace.
- `kc.toml` path settings are honored.
- Source refresh cannot silently preserve invalid citations.
- All mutation commands use locks/transactions.
- Artifact diff is based on a real snapshot or declares baseline unavailable.
- Search works in FTS fallback with warnings when semantic ranking is unavailable.
- `kc context prepare --out` creates a durable context pack.
- `kc task` exposes a usable state machine for external agents.
- README, AGENTS.md, guide, generated skill, changelog, and tests agree.
- A new user and Codex can complete this flow without reading source code:

```bash
kc init --yes
kc source add docs/policy.md --domain policy --yes
kc source search "ownership responsibilities" --domain policy
kc context prepare --ask "Create ownership page" --target knowledge/wiki/ownership.md --out .kc/context/ownership.json
kc artifact new --type knowledge_page --path knowledge/wiki/ownership.md --title "Ownership" --yes
# human or external agent edits artifact using v2 citation tokens
kc artifact validate --file knowledge/wiki/ownership.md
kc artifact diff --file knowledge/wiki/ownership.md
kc artifact apply --file knowledge/wiki/ownership.md --yes
kc lint
kc export --format llms-txt --out knowledge/exports/llms.txt
```
