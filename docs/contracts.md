# kc Remediation Contracts

This file records the shared interfaces frozen during the remediation work.

## Workspace

`src/kc/workspace.py` exposes `Workspace` and `resolve_workspace()`.

Resolution order:

1. `--root`
2. `KC_ROOT`
3. nearest parent containing `kc.toml`
4. nearest parent containing `.git`
5. current working directory

`current_paths()` derives `KcPaths` from the resolved workspace and honors
`kc.toml` unless `--data-dir` or `--state-dir` overrides are supplied.

## Sources And Ranges

`SourceRecord` remains `kc.source.v1` with additive fields:

- `canonical_source_key`
- `current_revision_id`
- `first_registered_at`
- `last_refreshed_at`

`SourceRevisionRecord` uses `kc.source_revision.v1`.

`SourceRangeRecord` remains `kc.source_range.v1` with additive fields:

- `revision_id`
- `status`

New range IDs are source, revision, locator, and text-hash aware.

## Citations

Preferred Markdown citation tokens:

```text
[kc:src_<source_id>:rng_<range_id>]
[kc:src_<source_id>:rng_<range_id>:L<start>-L<end>]
[kc:src_<source_id>:rng_<range_id>:JP:<json-pointer>]
[kc:src_<source_id>:rng_<range_id>:CSV:R<start>-R<end>]
```

Legacy locator tokens remain parseable:

```text
[kc:src_<source_id>:L<start>-L<end>]
[kc:src_<source_id>:JP:<json-pointer>]
[kc:src_<source_id>:CSV:R<start>-R<end>]
```

`kc citation rewrite` performs exact legacy-to-v2 rewrites. `kc citation
repair` reports deterministic repair candidates and applies only exact
mechanical rewrites.

## Search Results

Search results expose:

- `range_id`
- `source_id`
- `locator`
- `excerpt`
- `scores`
- preferred `citation_token`
- `legacy_citation_token`

When semantic ranking is unavailable, search and context preparation return
FTS results with `mode: "fts_fallback"` and a
`KC_RETRIEVAL_SEMANTIC_UNAVAILABLE` warning.

## Mutations

Write commands use a repo-level `repo-write` lock through
`MutationTransaction`. Operation records are written under `.kc/operations/`
with `kc.operation.v1`.

Artifact apply still also takes the artifact-specific lock.

## Context Packs

`kc context prepare --out <file>` writes a durable `kc.context_pack.v1` record
with the ask, target, workspace, candidate ranges, citation policy, agent
instructions, validation commands, and next commands.

## Tasks

Task states:

- `created`
- `awaiting_agent`
- `awaiting_validation`
- `awaiting_apply`
- `completed`
- `blocked`
- `cancelled`
- `failed`

`kc task next --task-id <id>` returns state-specific next commands and the
expected event.

## Eval Packs

Eval packs use `kc.eval_pack.v1` and can assert expected source IDs, expected
range IDs, required citation tokens, and minimum recall at k. `kc eval run
--out <file>` writes deterministic result JSON with recall and MRR metrics.
