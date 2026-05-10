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
last_validated_at: null
---
# kc Implementation Notes

## Summary

The repository now contains the v1 deterministic knowledge harness plus the phase 2 semantic retrieval slice: BM25 remains the default search mode, and semantic or hybrid modes are available after building the semantic index. [kc:src_01KR89M77M0SR209C87M6RKAY2:L881-L881] [kc:src_01KR8GD8XVCEYBW80M2SKVZVKS:L231-L254] [kc:src_01KR8GD8XVCEYBW80M2SKVZVKS:L255-L270]

## Source-backed facts

- The initialized repository layout follows the design shape with `kc.toml`, `knowledge/` JSONL and wiki files, and `.kc/` state directories for indexes, locks, snapshots, plans, and tasks. [kc:src_01KR89M77M0SR209C87M6RKAY2:L212-L235]
- The first implementation milestone called for a Python package, Typer CLI, envelope output, error handling, minimal `guide` and `init`, and tests for envelope/init behavior. [kc:src_01KR89M77M0SR209C87M6RKAY2:L2234-L2240]
- The implemented command surface covers the read commands expected by the safe-mutation model, including guide, source inspect/search, context prepare, artifact validate/diff, citation check, lint, task status/inspect, eval run, and doctor. [kc:src_01KR89M77M0SR209C87M6RKAY2:L1355-L1366]
- The phase 2 design requirement permits an optional local semantic index, but requires explicit configuration, no network calls during indexing, stored model metadata, embedding dimension and checksum, rebuild behavior on metadata changes, and clear unavailable-model errors. [kc:src_01KR89M77M0SR209C87M6RKAY2:L1494-L1499]
- The package metadata now includes `model2vec` and `numpy` as core dependencies, and the wheel build explicitly includes `src/kc/embedding_models`. [kc:src_01KR8GDBGSD5NX7GS8X8CC8YQW:L29-L34] [kc:src_01KR8GDBGSD5NX7GS8X8CC8YQW:L52-L53]
- The semantic implementation declares the bundled `potion-base-8M` model, expected dimension, checksum, and `ranking_only` metadata payload. [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L21-L25] [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L60-L68]
- The semantic model loader resolves the bundled model directory, validates the checksum, imports Model2Vec, loads the local model path, and rejects dimension mismatches. [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L35-L36] [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L71-L94]
- `kc index build --semantic` rebuilds the SQLite cache and then calls the semantic index builder; the semantic builder embeds source-range excerpts, stores vector rows, and records semantic model metadata. [kc:src_01KR8GD9CVD7PNQVA1KT2E73K6:L40-L54] [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L173-L190] [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L192-L215] [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L216-L226]
- `kc source search` accepts `bm25`, `semantic`, and `hybrid` modes, and search results expose BM25 rank, semantic rank, semantic score, hybrid rank, RRF score, citation token, and source metadata. [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L166-L181] [kc:src_01KR8GD8XVCEYBW80M2SKVZVKS:L134-L157]
- Hybrid retrieval combines BM25 and semantic candidate lists with reciprocal rank fusion, matching the deterministic fusion formula in the design. [kc:src_01KR89M77M0SR209C87M6RKAY2:L1507-L1509] [kc:src_01KR8GD8XVCEYBW80M2SKVZVKS:L182-L204] [kc:src_01KR8GD8XVCEYBW80M2SKVZVKS:L206-L228]
- `kc context prepare` now passes the requested retrieval mode, RRF constant, and current source ranges into shared search while still emitting grounded context rather than answering the task. [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L29-L52] [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L53-L76] [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L77-L100]

## Inferences

- The project is now ready to use `kc` with hybrid retrieval for design-grounded follow-up tasks, while keeping semantic search retrieval-only and outside any generative reasoning path. [kc:inference] [kc:src_01KR89M77M0SR209C87M6RKAY2:L30-L30] [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L288-L305]

## Open questions

- [kc:todo] Decide whether previously tracked generated state and Python cache files should be removed from the Git index now that `.gitignore` excludes future `.kc/`, cache, and build artifacts.

## Source notes

- `src_01KR89M77M0SR209C87M6RKAY2` is `kc-design-v1.md`, registered from this repo. [kc:src_01KR89M77M0SR209C87M6RKAY2:L5-L8]
- `src_01KR8GD8FTQ0BZXKM91NPZ4BC9`, `src_01KR8GD8XVCEYBW80M2SKVZVKS`, `src_01KR8GD9CVD7PNQVA1KT2E73K6`, `src_01KR8GD9T9JFNPC5R9WMBHWXCH`, `src_01KR8GDA7V19F05T6R93ZAWZ35`, and `src_01KR8GDBGSD5NX7GS8X8CC8YQW` are implementation sources registered from this repo during phase 2 self-use. [kc:inference]
