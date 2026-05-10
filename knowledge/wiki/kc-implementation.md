---
schema_version: kc.knowledge_page.v1
artifact_id: art_kc_implementation
title: kc Implementation Notes
status: draft
domain:
  - kc
artifact_type: knowledge_page
requires_citations: true
source_refs:
  - source_id: src_01KR89M77M0SR209C87M6RKAY2
    ranges: []
  - source_id: src_01KR8GD8FTQ0BZXKM91NPZ4BC9
    ranges: []
  - source_id: src_01KR8GD8XVCEYBW80M2SKVZVKS
    ranges: []
  - source_id: src_01KR8GD9CVD7PNQVA1KT2E73K6
    ranges: []
  - source_id: src_01KR8GD9T9JFNPC5R9WMBHWXCH
    ranges: []
  - source_id: src_01KR8GDA7V19F05T6R93ZAWZ35
    ranges: []
  - source_id: src_01KR8GDBGSD5NX7GS8X8CC8YQW
    ranges: []
  - source_id: src_01KR8Q43CZJXAM4ACWW4Y7GWT1
    ranges: []
  - source_id: src_01KR8Q47XCTWN53DZJ3BE8PD88
    ranges: []
last_validated_at: null
---
# kc Implementation Notes

## Summary

The repository now contains the v1 deterministic knowledge harness plus the phase 2 semantic retrieval slice and phase 3 release-hardening work: BM25 remains the default search mode, semantic or hybrid modes are available after building the semantic index, registered sources can be refreshed deterministically, and artifact apply can enforce persisted plans. [kc:src_01KR89M77M0SR209C87M6RKAY2:L881-L881] [kc:src_01KR8GD8XVCEYBW80M2SKVZVKS:L231-L254] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L232-L253] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L390-L413]

## Source-backed facts

- The initialized repository layout follows the design shape with `kc.toml`, `knowledge/` JSONL and wiki files, and `.kc/` state directories for indexes, locks, snapshots, plans, and tasks. [kc:src_01KR89M77M0SR209C87M6RKAY2:L212-L235]
- The first implementation milestone called for a Python package, Typer CLI, envelope output, error handling, minimal `guide` and `init`, and tests for envelope/init behavior. [kc:src_01KR89M77M0SR209C87M6RKAY2:L2234-L2240]
- The guide command catalog now exposes `source.refresh` as a mutating command and documents `artifact.apply` as accepting either `--file` or `--plan` plus an optional idempotency key. [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L143-L166] [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L167-L188]
- The phase 2 design requirement permits an optional local semantic index, but requires explicit configuration, no network calls during indexing, stored model metadata, embedding dimension and checksum, rebuild behavior on metadata changes, and clear unavailable-model errors. [kc:src_01KR89M77M0SR209C87M6RKAY2:L1494-L1499]
- The package metadata now includes `model2vec` and `numpy` as core dependencies, and the wheel build explicitly includes `src/kc/embedding_models`. [kc:src_01KR8GDBGSD5NX7GS8X8CC8YQW:L29-L34] [kc:src_01KR8GDBGSD5NX7GS8X8CC8YQW:L52-L53]
- The semantic implementation declares the bundled `potion-base-8M` model, expected dimension, checksum, and `ranking_only` metadata payload. [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L21-L25] [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L60-L68]
- The semantic model loader resolves the bundled model directory, validates the checksum, imports Model2Vec, loads the local model path, and rejects dimension mismatches. [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L35-L36] [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L71-L94]
- `kc index build --semantic` rebuilds the SQLite cache and then calls the semantic index builder; the semantic builder embeds source-range excerpts, stores vector rows, and records semantic model metadata. [kc:src_01KR8GD9CVD7PNQVA1KT2E73K6:L40-L54] [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L173-L190] [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L192-L215] [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L216-L226]
- `kc source search` accepts `bm25`, `semantic`, and `hybrid` modes, and search results expose BM25 rank, semantic rank, semantic score, hybrid rank, RRF score, citation token, and source metadata. [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L317-L332] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L334-L349] [kc:src_01KR8GD8XVCEYBW80M2SKVZVKS:L134-L157]
- Hybrid retrieval combines BM25 and semantic candidate lists with reciprocal rank fusion, matching the deterministic fusion formula in the design. [kc:src_01KR89M77M0SR209C87M6RKAY2:L1507-L1509] [kc:src_01KR8GD8XVCEYBW80M2SKVZVKS:L182-L204] [kc:src_01KR8GD8XVCEYBW80M2SKVZVKS:L206-L228]
- `kc context prepare` now passes the requested retrieval mode, RRF constant, and current source ranges into shared search while still emitting grounded context rather than answering the task. [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L29-L52] [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L53-L76] [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L77-L100]
- `kc source refresh` resolves an existing source by ID or path, rejects missing or unsupported local files, preserves the existing `source_id`, recomputes raw and normalized fingerprints, replaces that source's extracted ranges, reports impacted artifact citations, and rebuilds the BM25 index on apply. [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L35-L46] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L48-L55] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L58-L81] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L82-L86] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L232-L253] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L255-L278] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L281-L291]
- `kc source refresh` returns old and new fingerprints, range counts, impacted artifacts, index rebuild status, semantic index staleness, and a `kc index build --semantic` next command when semantic vectors need an explicit rebuild. [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L293-L312]
- `kc artifact apply --plan` loads only `kc.plan.v1` records, rejects non-`artifact.apply` or multi-operation plans, enforces path and fingerprint preconditions before writing registry state, and persists the applied plan under `.kc/plans/<plan_id>.json`. [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L390-L413] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L416-L430] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L458-L481] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L485-L488] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L563-L586] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L624-L647]

## Inferences

- The project is now ready to maintain its own registered implementation sources through `kc source refresh` rather than direct JSONL edits, while keeping semantic embedding rebuilds explicit. [kc:inference] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L281-L291] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L293-L312]

## Open questions

- [kc:todo] Decide whether previously tracked generated state and Python cache files should be removed from the Git index now that `.gitignore` excludes future `.kc/`, cache, and build artifacts.

## Source notes

- `src_01KR89M77M0SR209C87M6RKAY2` is `kc-design-v1.md`, registered from this repo. [kc:src_01KR89M77M0SR209C87M6RKAY2:L5-L8]
- `src_01KR8GD8FTQ0BZXKM91NPZ4BC9`, `src_01KR8GD8XVCEYBW80M2SKVZVKS`, `src_01KR8GD9CVD7PNQVA1KT2E73K6`, `src_01KR8GD9T9JFNPC5R9WMBHWXCH`, `src_01KR8GDA7V19F05T6R93ZAWZ35`, `src_01KR8GDBGSD5NX7GS8X8CC8YQW`, `src_01KR8Q43CZJXAM4ACWW4Y7GWT1`, and `src_01KR8Q47XCTWN53DZJ3BE8PD88` are implementation sources registered from this repo during phase 2 and phase 3 self-use. [kc:inference]
