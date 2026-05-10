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
    ranges:
      - rng_01KR89M77QQBPGT0K1TC7ZHW12
      - rng_01KR89M77R7W0WMGJGSGWYVZZP
      - rng_01KR89M77Y3RJTM1MRVBM8QB6S
      - rng_01KR89M77Y3RJTM1MRVBM8QB7F
last_validated_at: null
---
# kc Implementation Notes

## Summary

The repository now contains a Python CLI implementation for the local-first knowledge harness described by the design goal: compile, maintain, validate, and query a durable knowledge base without the CLI calling an LLM. [kc:src_01KR89M77M0SR209C87M6RKAY2:L5-L8]

## Source-backed facts

- The initialized repository layout follows the design shape with `kc.toml`, `knowledge/` JSONL and wiki files, and `.kc/` state directories for indexes, locks, snapshots, plans, and tasks. [kc:src_01KR89M77M0SR209C87M6RKAY2:L212-L235]
- The first implementation milestone called for a Python package, Typer CLI, envelope output, error handling, minimal `guide` and `init`, and tests for envelope/init behavior. [kc:src_01KR89M77M0SR209C87M6RKAY2:L2234-L2240]
- The implemented command surface covers the read commands expected by the safe-mutation model, including guide, source inspect/search, context prepare, artifact validate/diff, citation check, lint, task status/inspect, eval run, and doctor. [kc:src_01KR89M77M0SR209C87M6RKAY2:L1355-L1366]
- The current self-hosted milestone targets the v1 definition of done: initialization, source registration and BM25 search, context preparation, artifact validation/apply, linting, guide usability, standard envelopes, safe locked writes, tests, and no core LLM dependencies. [kc:src_01KR89M77M0SR209C87M6RKAY2:L2316-L2327]

## Inferences

- The project is ready to use `kc` for implementation notes and design-grounded follow-up tasks, while still treating semantic retrieval and richer adapters as later work. [kc:inference] [kc:src_01KR89M77M0SR209C87M6RKAY2:L2316-L2327]

## Open questions

- [kc:todo] Decide whether generated `.kc/state.sqlite` should remain local-only if this directory is later turned into a Git repository.

## Source notes

- `src_01KR89M77M0SR209C87M6RKAY2` is `kc-design-v1.md`, registered from this repo. [kc:src_01KR89M77M0SR209C87M6RKAY2:L5-L8]
