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
  - source_id: src_9F5299B94F508840AAB5A9A19B
    ranges: []
  - source_id: src_AE85F8EDD94C03FD66CF2FE13D
    ranges: []
  - source_id: src_CCBDF433DC72CF207BC924636B
    ranges: []
  - source_id: src_21D68E95E8C70C3E493EDF5AF4
    ranges: []
  - source_id: src_C9A5F720414316E2A8340E3007
    ranges: []
---

# kc Implementation Notes

## Summary

`kc-cli` keeps the v1 local-first harness boundary: source registration, retrieval, context preparation, artifact validation, safe apply, and task state are deterministic CLI responsibilities, while external agents remain responsible for semantic authoring. [kc:src_01KR89M77M0SR209C87M6RKAY2:L2210-L2213] [kc:src_01KR89M77M0SR209C87M6RKAY2:L2462-L2468] The 2026-05-11 black-box feedback pass tightened command-contract behavior around structured usage errors, invalid arguments, missing workspace state, stale-source warnings, artifact warnings, task resume payload validation, and guide/readme documentation without adding provider or generative reasoning dependencies. [kc:inference] A subsequent 2026-05-11 versioning pass added an `archguard`-style single-source release regime with changelog discipline, SemVer rules, and tests for version-surface drift. [kc:src_AE85F8EDD94C03FD66CF2FE13D:L42-L42] [kc:src_AE85F8EDD94C03FD66CF2FE13D:L44-L49] [kc:src_01KR8W4S76SRDQKJDQ700PDTGG:L47-L52] [kc:src_01KR8W4S76SRDQKJDQ700PDTGG:L54-L56] [kc:src_01KR8W4S76SRDQKJDQ700PDTGG:L59-L62] The 1.0.0 retrieval pass made hybrid BM25-plus-semantic retrieval the default for search and context preparation, made `kc index build` rebuild semantic embeddings by default, and removed the public retrieval-selection switches. [kc:src_C9A5F720414316E2A8340E3007:L5-L5] [kc:src_CCBDF433DC72CF207BC924636B:L20-L22] [kc:src_CCBDF433DC72CF207BC924636B:L26-L27]

## Source-Backed Facts

- Error definitions now distinguish process usage failures from domain validation failures: `EXIT_USAGE` is `2`, `KC_USAGE_ERROR` maps to usage failures, and `KC_VALIDATION_INVALID_ARGUMENT` remains a validation error. [kc:src_01KR90ZDMFJ36C9QP9END5F46W:L25-L48]
- The CLI group catches Click usage errors, initializes output state, infers the command id when possible, and emits a structured `KC_USAGE_ERROR` envelope; invalid global `--format` values emit `KC_VALIDATION_INVALID_ARGUMENT` before normal command dispatch. [kc:src_01KR8W45S5XX5M0XE6SA23EHK1:L85-L108] [kc:src_01KR8W45S5XX5M0XE6SA23EHK1:L109-L116] [kc:src_01KR8W45S5XX5M0XE6SA23EHK1:L240-L250]
- Shared command helpers now centralize choice validation, positive integer validation, named integer parsing for `context prepare --budget`, lint check parsing, JSON payload schema validation, data-store loading guards, and stale-source warning assembly. [kc:src_90D0AC3379D12836F586472A7D:L48-L64] [kc:src_90D0AC3379D12836F586472A7D:L67-L74] [kc:src_90D0AC3379D12836F586472A7D:L77-L100] [kc:src_90D0AC3379D12836F586472A7D:L101-L124] [kc:src_90D0AC3379D12836F586472A7D:L125-L131] [kc:src_90D0AC3379D12836F586472A7D:L236-L259] [kc:src_90D0AC3379D12836F586472A7D:L296-L319]
- Storage-facing command helpers call `ensure_data_dir_exists()` before loading JSONL stores, so commands tolerate a missing `.kc` directory; the path helper creates the configured data directory and returns its path. [kc:src_90D0AC3379D12836F586472A7D:L154-L156] [kc:src_90D0AC3379D12836F586472A7D:L163-L165] [kc:src_90D0AC3379D12836F586472A7D:L172-L174] [kc:src_90D0AC3379D12836F586472A7D:L181-L183] [kc:src_A3CBFE85BE1E938A3881D3498B:L76-L84]
- `artifact new` validates artifact type and status, `artifact validate` returns warnings as well as errors, draft TODO markers are reported with `KC_ARTIFACT_TODO_MARKERS`, and artifact apply carries validation warnings into dry-run and apply results. [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L598-L617] [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L334-L357]
- `artifact diff` validates `--against` and reports missing artifact files with `KC_ARTIFACT_NOT_FOUND`, while artifact plan loading reports missing plan files with `KC_FILE_NOT_FOUND`. [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L334-L357] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L598-L617]
- `init` accepts only the `generic` profile and treats an existing `.kc/state.sqlite` as a successful noop rather than a fatal initialization error. [kc:src_D1DAAEE984DBDAA5CE1993D0D1:L15-L15] [kc:src_D1DAAEE984DBDAA5CE1993D0D1:L18-L41] [kc:src_D1DAAEE984DBDAA5CE1993D0D1:L66-L89]
- `source add` reports `KC_SOURCE_NO_RANGES` when extraction produces no ranges, duplicate source detection points callers at `kc source refresh <source_id> --dry-run`, and applied source registration now rebuilds both the SQLite search index and semantic embeddings. [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L165-L188]
- `source refresh --yes` replaces ranges, rebuilds the SQLite index, rebuilds semantic embeddings, and reports `semantic_index_rebuilt`; `source search` exposes hybrid retrieval without a retrieval-mode option and returns `mode: "hybrid"` in the result and target payload. [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L290-L298] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L300-L319] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L324-L333] [kc:src_01KR8GD9T9JFNPC5R9WMBHWXCH:L335-L351]
- `context prepare` no longer exposes retrieval mode selection; it validates grounding and budget input, calls the shared hybrid `search_ranges` path with the configured RRF constant, emits `mode: "hybrid"`, and still attaches stale-source warnings via the shared warning helper. [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L29-L52] [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L53-L76] [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L77-L100] [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L101-L124] [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L125-L126] [kc:src_90D0AC3379D12836F586472A7D:L320-L336]
- `ensure_index` now rebuilds stale or missing SQLite indexes and then builds semantic embeddings when semantic metadata or vectors are missing, stale, or model-mismatched; `search_ranges` asserts semantic readiness and always combines BM25 and semantic rankings with RRF. [kc:src_01KR8GD8XVCEYBW80M2SKVZVKS:L44-L58] [kc:src_01KR8GD8XVCEYBW80M2SKVZVKS:L231-L254]
- `kc index build` no longer exposes `--semantic`; dry-run previews semantic model metadata, and real builds always run `build_semantic_index` after the SQLite rebuild. [kc:src_01KR8GD9CVD7PNQVA1KT2E73K6:L16-L39] [kc:src_01KR8GD9CVD7PNQVA1KT2E73K6:L40-L49]
- `task resume` validates JSON payloads against a task's expected event schema before appending the resume event. [kc:src_9405FC69F97131789713475CFC:L50-L73] [kc:src_9405FC69F97131789713475CFC:L74-L97] [kc:src_9405FC69F97131789713475CFC:L140-L163]
- Guide contracts now document usage errors, BM25 scoring, marker meanings, process exit aggregation, and eval/export behavior; `eval run` requires `--pack`, and export results identify whether content was emitted inline or to a file. [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L430-L453]
- Guide contracts now list hybrid retrieval as the default, describe semantic retrieval activation as default hybrid retrieval plus `kc index build`, and remove `--mode`/`--semantic` from the command catalog. [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L37-L60] [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L286-L309] [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L310-L333]
- Regression coverage includes invalid lint checks, empty lint checks, source search validation, stale-source warning propagation, artifact warnings, missing artifact/plan paths, usage envelopes, missing data-dir behavior, init idempotency, eval pack requirements, citation target requirements, task resume schema validation, hybrid search defaults, semantic index builds, context hybrid mode, checksum failures, and hard-removal usage errors for the old retrieval switches. [kc:src_01KR93GAQK523QMTD7E1FH7RPF:L248-L252] [kc:src_01KR93GAQK523QMTD7E1FH7RPF:L254-L256] [kc:src_CA300356A8703AE94ACE629B8A:L44-L49] [kc:src_CA300356A8703AE94ACE629B8A:L51-L67] [kc:src_21D68E95E8C70C3E493EDF5AF4:L56-L58] [kc:src_21D68E95E8C70C3E493EDF5AF4:L60-L73] [kc:src_21D68E95E8C70C3E493EDF5AF4:L75-L80] [kc:src_21D68E95E8C70C3E493EDF5AF4:L83-L85] [kc:src_21D68E95E8C70C3E493EDF5AF4:L87-L102] [kc:src_21D68E95E8C70C3E493EDF5AF4:L105-L115] [kc:src_21D68E95E8C70C3E493EDF5AF4:L118-L120] [kc:src_21D68E95E8C70C3E493EDF5AF4:L122-L131]
- Release documentation now defines the package version as `src/kc/__init__.py::__version__`, uses Hatch dynamic versioning from that file, requires `kc --version` and `kc guide` to report the same value, keeps `[Unreleased]` and current-version changelog sections, and classifies patch, minor, and major changes by compatibility impact. [kc:src_9F5299B94F508840AAB5A9A19B:L511-L515] [kc:src_AE85F8EDD94C03FD66CF2FE13D:L44-L49] [kc:src_CCBDF433DC72CF207BC924636B:L5-L6]
- The versioning regression tests assert that `__version__` has a version-shaped value, `kc --version` prints it, `kc guide` returns it, `pyproject.toml` keeps `dynamic = ["version"]` with Hatch pointing at `src/kc/__init__.py`, and `CHANGELOG.md` contains both `[Unreleased]` and the current version. [kc:src_01KR8W4S76SRDQKJDQ700PDTGG:L47-L52] [kc:src_01KR8W4S76SRDQKJDQ700PDTGG:L54-L56] [kc:src_01KR8W4S76SRDQKJDQ700PDTGG:L59-L62]

## Inferences

- The black-box feedback fixes are primarily command-contract hardening: they make failure modes machine-readable and predictable without expanding `kc` into a planner, workflow engine, or LLM provider integration. [kc:inference] [kc:src_01KR89M77M0SR209C87M6RKAY2:L2210-L2213] [kc:src_01KR89M77M0SR209C87M6RKAY2:L2462-L2468]
- Centralizing validators and store guards should reduce future contract drift between commands, because new commands can reuse the same structured error and warning helpers instead of hand-rolling envelope details. [kc:inference] [kc:src_90D0AC3379D12836F586472A7D:L48-L64] [kc:src_90D0AC3379D12836F586472A7D:L154-L156] [kc:src_90D0AC3379D12836F586472A7D:L296-L319]
- Keeping the version value in one Python source and testing every published version surface should prevent build metadata, CLI output, and agent guide metadata from diverging during future releases. [kc:inference] [kc:src_9F5299B94F508840AAB5A9A19B:L511-L515] [kc:src_01KR8W4S76SRDQKJDQ700PDTGG:L47-L52] [kc:src_01KR8W4S76SRDQKJDQ700PDTGG:L54-L56]

## Open Questions

- [kc:todo] Decide separately whether historical log entries that reference untracked local plan files should be normalized, ignored as local history, or moved behind an explicit `lint --checks log` cleanup task.
