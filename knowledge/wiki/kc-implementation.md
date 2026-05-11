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
  - source_id: src_01KR8GDB389BYFVFP2E09YMTD9
    ranges: []
  - source_id: src_01KR8GD8FTQ0BZXKM91NPZ4BC9
    ranges: []
  - source_id: src_01KR8GD8XVCEYBW80M2SKVZVKS
    ranges: []
  - source_id: src_01KR8GD9T9JFNPC5R9WMBHWXCH
    ranges: []
  - source_id: src_01KR8GDA7V19F05T6R93ZAWZ35
    ranges: []
  - source_id: src_01KR8Q43CZJXAM4ACWW4Y7GWT1
    ranges: []
  - source_id: src_01KR8Q47XCTWN53DZJ3BE8PD88
    ranges: []
  - source_id: src_01KR8W45S5XX5M0XE6SA23EHK1
    ranges: []
  - source_id: src_01KR8W45SSBZB8AA4FNSHZZFCQ
    ranges: []
  - source_id: src_01KR8W4S76SRDQKJDQ700PDTGG
    ranges: []
  - source_id: src_01KR8W7A30Q9G8RF9CYP7P7TCF
    ranges: []
  - source_id: src_01KR90ZDMFJ36C9QP9END5F46W
    ranges: []
  - source_id: src_01KR90ZGMHFEFNST5FRX05AER0
    ranges: []
  - source_id: src_01KR93G4RJRP13TTXQX28SKF85
    ranges: []
  - source_id: src_01KR93G5MN8R7Q1PCGH7RB4Y00
    ranges: []
  - source_id: src_01KR93G6FG1161NN4Z6Z2NVXBW
    ranges: []
  - source_id: src_01KR93G7B0GP8C5J7WTECXA6NN
    ranges: []
  - source_id: src_01KR93G85YFT0HVHVM8C8XAKRW
    ranges: []
  - source_id: src_01KR93G91G16H3XQ8MHQ13NXJM
    ranges: []
  - source_id: src_01KR93G9W8C0NF3PE57GAV813F
    ranges: []
  - source_id: src_01KR93GAQK523QMTD7E1FH7RPF
    ranges: []
  - source_id: src_90D0AC3379D12836F586472A7D
    ranges: []
  - source_id: src_A3CBFE85BE1E938A3881D3498B
    ranges: []
  - source_id: src_D1DAAEE984DBDAA5CE1993D0D1
    ranges: []
  - source_id: src_9405FC69F97131789713475CFC
    ranges: []
  - source_id: src_CA300356A8703AE94ACE629B8A
    ranges: []
---

# kc Implementation Notes

## Summary

`kc-cli` keeps the v1 local-first harness boundary: source registration, retrieval, context preparation, artifact validation, safe apply, and task state are deterministic CLI responsibilities, while external agents remain responsible for semantic authoring. [kc:src_01KR89M77M0SR209C87M6RKAY2:L2210-L2213] [kc:src_01KR89M77M0SR209C87M6RKAY2:L2462-L2468] The 2026-05-11 black-box feedback pass tightened command-contract behavior around structured usage errors, invalid arguments, missing workspace state, stale-source warnings, artifact warnings, task resume payload validation, and guide/readme documentation without adding provider or generative reasoning dependencies. [kc:inference]

## Source-Backed Facts

- Error definitions now distinguish process usage failures from domain validation failures: `EXIT_USAGE` is `2`, `KC_USAGE_ERROR` maps to usage failures, and `KC_VALIDATION_INVALID_ARGUMENT` remains a validation error. [kc:src_01KR90ZDMFJ36C9QP9END5F46W:L25-L48]
- The CLI group catches Click usage errors, initializes output state, infers the command id when possible, and emits a structured `KC_USAGE_ERROR` envelope; invalid global `--format` values emit `KC_VALIDATION_INVALID_ARGUMENT` before normal command dispatch. [kc:src_01KR8W45S5XX5M0XE6SA23EHK1:L85-L108] [kc:src_01KR8W45S5XX5M0XE6SA23EHK1:L109-L116] [kc:src_01KR8W45S5XX5M0XE6SA23EHK1:L240-L250]
- Shared command helpers now centralize choice validation, positive integer validation, named integer parsing for `context prepare --budget`, lint check parsing, JSON payload schema validation, data-store loading guards, and stale-source warning assembly. [kc:src_90D0AC3379D12836F586472A7D:L48-L64] [kc:src_90D0AC3379D12836F586472A7D:L67-L74] [kc:src_90D0AC3379D12836F586472A7D:L77-L100] [kc:src_90D0AC3379D12836F586472A7D:L101-L124] [kc:src_90D0AC3379D12836F586472A7D:L125-L131] [kc:src_90D0AC3379D12836F586472A7D:L236-L259] [kc:src_90D0AC3379D12836F586472A7D:L296-L319]
- Storage-facing command helpers call `ensure_data_dir_exists()` before loading JSONL stores, so commands tolerate a missing `.kc` directory; the path helper creates the configured data directory and returns its path. [kc:src_90D0AC3379D12836F586472A7D:L154-L156] [kc:src_90D0AC3379D12836F586472A7D:L163-L165] [kc:src_90D0AC3379D12836F586472A7D:L172-L174] [kc:src_90D0AC3379D12836F586472A7D:L181-L183] [kc:src_A3CBFE85BE1E938A3881D3498B:L76-L84]
- `artifact new` validates artifact type and status, `artifact validate` returns warnings as well as errors, draft TODO markers are reported with `KC_ARTIFACT_TODO_MARKERS`, and artifact apply carries validation warnings into dry-run and apply results. [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L598-L617] [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L335-L358]
- `artifact diff` validates `--against` and reports missing artifact files with `KC_ARTIFACT_NOT_FOUND`, while artifact plan loading reports missing plan files with `KC_FILE_NOT_FOUND`. [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L335-L358] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L598-L617]
- `init` accepts only the `generic` profile and treats an existing `.kc/state.sqlite` as a successful noop rather than a fatal initialization error. [kc:src_D1DAAEE984DBDAA5CE1993D0D1:L15-L15] [kc:src_D1DAAEE984DBDAA5CE1993D0D1:L18-L41] [kc:src_D1DAAEE984DBDAA5CE1993D0D1:L66-L89]
- `source add` reports `KC_SOURCE_NO_RANGES` when extraction produces no ranges, duplicate source detection points callers at `kc source refresh <source_id> --dry-run`, and `source search` validates mode and positive limit values before returning results. [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L167-L190] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L331-L342] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L344-L361]
- `source search` and `context prepare` attach stale-source warnings via the shared warning helper, and `context prepare` echoes parsed budget values after validating grounding, retrieval mode, and budget syntax. [kc:src_90D0AC3379D12836F586472A7D:L320-L336] [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L30-L53] [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L126-L132]
- `task resume` validates JSON payloads against a task's expected event schema before appending the resume event. [kc:src_9405FC69F97131789713475CFC:L50-L73] [kc:src_9405FC69F97131789713475CFC:L74-L97] [kc:src_9405FC69F97131789713475CFC:L140-L163]
- Guide contracts now document usage errors, BM25 scoring, marker meanings, process exit aggregation, and eval/export behavior; `eval run` requires `--pack`, and export results identify whether content was emitted inline or to a file. [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L431-L454]
- Regression coverage includes invalid lint checks, empty lint checks, source search validation, stale-source warning propagation, artifact warnings, missing artifact/plan paths, usage envelopes, missing data-dir behavior, init idempotency, eval pack requirements, citation target requirements, and task resume schema validation. [kc:src_01KR93GAQK523QMTD7E1FH7RPF:L252-L256] [kc:src_01KR93GAQK523QMTD7E1FH7RPF:L258-L260] [kc:src_CA300356A8703AE94ACE629B8A:L44-L49] [kc:src_CA300356A8703AE94ACE629B8A:L51-L67]

## Inferences

- The black-box feedback fixes are primarily command-contract hardening: they make failure modes machine-readable and predictable without expanding `kc` into a planner, workflow engine, or LLM provider integration. [kc:inference] [kc:src_01KR89M77M0SR209C87M6RKAY2:L2210-L2213] [kc:src_01KR89M77M0SR209C87M6RKAY2:L2462-L2468]
- Centralizing validators and store guards should reduce future contract drift between commands, because new commands can reuse the same structured error and warning helpers instead of hand-rolling envelope details. [kc:inference] [kc:src_90D0AC3379D12836F586472A7D:L48-L64] [kc:src_90D0AC3379D12836F586472A7D:L154-L156] [kc:src_90D0AC3379D12836F586472A7D:L296-L319]

## Open Questions

- [kc:todo] Decide separately whether historical log entries that reference untracked local plan files should be normalized, ignored as local history, or moved behind an explicit `lint --checks log` cleanup task.
