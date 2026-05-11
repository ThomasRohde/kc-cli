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
  - source_id: src_01KR8GDA7V19F05T6R93ZAWZ35
    ranges: []
  - source_id: src_01KR8Q43CZJXAM4ACWW4Y7GWT1
    ranges: []
  - source_id: src_01KR8Q47XCTWN53DZJ3BE8PD88
    ranges: []
  - source_id: src_01KR8W45SSBZB8AA4FNSHZZFCQ
    ranges: []
  - source_id: src_01KR8W4S76SRDQKJDQ700PDTGG
    ranges: []
  - source_id: src_01KR8W7A30Q9G8RF9CYP7P7TCF
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
  - source_id: src_01KR93G91G16H3XQ8MHQ13NXJM
    ranges: []
  - source_id: src_01KR93G9W8C0NF3PE57GAV813F
    ranges: []
  - source_id: src_01KR93GAQK523QMTD7E1FH7RPF
    ranges: []
---

# kc Implementation Notes

## Summary

`kc-cli` is now closer to the v1 harness goal: citation parsing, source extraction, artifact validation, direct-edit apply, lint, index health, guide output, context preparation, export, and conformance coverage have all been hardened while preserving the local-first, retrieval-only CLI shape. The v1 design names line ranges, JSON pointers, and CSV row ranges as locator kinds, and it keeps semantic retrieval metadata local and ranking-only rather than generative. [kc:src_01KR89M77M0SR209C87M6RKAY2:L402-L405] [kc:src_01KR89M77M0SR209C87M6RKAY2:L2210-L2213]

## Source-Backed Facts

- Citation records and Markdown validation now share the same locator model for line ranges, JSON pointers, and CSV row ranges. [kc:src_01KR93G7B0GP8C5J7WTECXA6NN:L38-L47] [kc:src_01KR93G6FG1161NN4Z6Z2NVXBW:L18-L25] [kc:src_01KR93G6FG1161NN4Z6Z2NVXBW:L90-L104]
- Citation validation detects malformed kc tokens, missing ranges, stale registered fingerprints, and changed current source fingerprints. [kc:src_01KR93G6FG1161NN4Z6Z2NVXBW:L68-L83] [kc:src_01KR93G6FG1161NN4Z6Z2NVXBW:L165-L188] [kc:src_01KR93G6FG1161NN4Z6Z2NVXBW:L189-L212]
- Search token rendering emits Markdown citation tokens for line ranges, JSON pointers, and CSV row ranges, and human output renders JSON pointer and CSV row locators. [kc:src_01KR8GD8XVCEYBW80M2SKVZVKS:L52-L60] [kc:src_01KR8W45SSBZB8AA4FNSHZZFCQ:L151-L161]
- Source extraction now treats JSON, YAML, TOML, and CSV as structured inputs where parsing succeeds, falling back to text extraction on parser failures; CSV rows receive `csv_row_range` locators. [kc:src_01KR93G4RJRP13TTXQX28SKF85:L48-L71] [kc:src_01KR93G4RJRP13TTXQX28SKF85:L72-L84] [kc:src_01KR93G4RJRP13TTXQX28SKF85:L215-L238]
- Artifact validation enforces known artifact types and statuses, required Markdown frontmatter, valid status transitions, source references, required sections, citation coverage, and JSON artifact citation checks. [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L48-L71] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L239-L262] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L457-L480] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L481-L504]
- Artifact apply remains a direct-edit registry commit, but dry-run plans are enriched, idempotency conflicts are rejected, locks are used, fingerprints are rechecked under lock, and snapshots include the artifact plus kc-owned state files. [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L347-L370] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L974-L997] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L902-L925] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L1056-L1078]
- Lint now has checks for duplicate IDs, orphan citation edges, missing source ranges, stale indexes, and log references, with index stale issues reported as `KC_INDEX_BUILD_FAILED`. [kc:src_01KR8W7A30Q9G8RF9CYP7P7TCF:L20-L41] [kc:src_01KR8W7A30Q9G8RF9CYP7P7TCF:L73-L96] [kc:src_01KR8W7A30Q9G8RF9CYP7P7TCF:L132-L141]
- SQLite indexing stores source count, range count, and a corpus fingerprint; `index_status` compares current source/range state against the last build metadata so doctor, lint, and search can detect stale indexes. [kc:src_01KR93G5MN8R7Q1PCGH7RB4Y00:L178-L191] [kc:src_01KR93G5MN8R7Q1PCGH7RB4Y00:L290-L309] [kc:src_01KR8W45SSBZB8AA4FNSHZZFCQ:L657-L680]
- Semantic retrieval remains bundled but retrieval-only: config and guide expose `model2vec`, `potion-base-8M`, checksum, explicit activation, and `ranking_only` purpose. [kc:src_01KR8GDB389BYFVFP2E09YMTD9:L38-L43] [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L37-L60] [kc:src_01KR8GD8FTQ0BZXKM91NPZ4BC9:L60-L68]
- `context prepare` validates grounding, mode, and retrieval budgets while retaining the v1 role of preparing evidence and instructions rather than answering the task itself. [kc:src_01KR8GDA7V19F05T6R93ZAWZ35:L44-L67] [kc:src_01KR89M77M0SR209C87M6RKAY2:L905-L905] [kc:src_01KR89M77M0SR209C87M6RKAY2:L925-L932]
- `export --out` is path-safe and guide contracts now describe eval/export error behavior and mutation semantics through the standard envelope. [kc:src_01KR93G91G16H3XQ8MHQ13NXJM:L15-L38] [kc:src_01KR93G91G16H3XQ8MHQ13NXJM:L39-L48] [kc:src_01KR8Q47XCTWN53DZJ3BE8PD88:L419-L442]
- Coverage was broadened for structured source search, malformed and stale citation validation, lock-held apply behavior, changed-fingerprint apply preconditions, path safety, doctor output, guide goldens, and conformance output. [kc:src_01KR93GAQK523QMTD7E1FH7RPF:L49-L59] [kc:src_01KR93G9W8C0NF3PE57GAV813F:L192-L207] [kc:src_01KR93G9W8C0NF3PE57GAV813F:L303-L310] [kc:src_01KR93G9W8C0NF3PE57GAV813F:L317-L327] [kc:src_01KR8W4S76SRDQKJDQ700PDTGG:L243-L257] [kc:src_01KR8W4S76SRDQKJDQ700PDTGG:L259-L261] [kc:src_01KR90ZGMHFEFNST5FRX05AER0:L128-L129] [kc:src_01KR90ZGMHFEFNST5FRX05AER0:L136-L137]

## Inferences

- This pass is intentionally v1-close rather than post-v1: it hardens the core harness and avoids adding SaaS ingestion, MCP, web UI, workflow-engine behavior, or generative LLM dependencies. [kc:inference] [kc:src_01KR89M77M0SR209C87M6RKAY2:L2210-L2213] [kc:src_01KR89M77M0SR209C87M6RKAY2:L2462-L2468]
- The direct-edit artifact flow is preserved, but the registry commit is now safer because apply recomputes evidence after validation and records enough plan/snapshot detail for deterministic review. [kc:inference] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L974-L997] [kc:src_01KR8Q43CZJXAM4ACWW4Y7GWT1:L1056-L1078]

## Open Questions

- [kc:todo] Decide separately whether historical log entries that reference untracked local plan files should be normalized, ignored as local history, or moved behind an explicit `lint --checks log` cleanup task.
