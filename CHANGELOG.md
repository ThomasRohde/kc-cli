# Changelog

All notable changes to this project will be documented in this file.

This project uses Semantic Versioning for the Python package version exposed by
`src/kc/__init__.py`, the Hatch build metadata, `kc --version`, and `kc guide`.

## [Unreleased]

## [0.4.0] - 2026-05-12

### Changed

- Bumped the package version for the next minor release.

## [0.3.0] - 2026-05-12

### Added

- Workspace root discovery with `--root`, `KC_ROOT`, `kc.toml`, `.git`, and
  current-directory fallback resolution.
- Source revisions, revision-aware range IDs, v2 range citation tokens, and
  deterministic `kc citation rewrite` / `kc citation repair` workflows.
- Repo-level mutation transactions with `.kc/operations/` journals.
- Durable context packs via `kc context prepare --out`.
- `kc task next` and a state-specific task workflow through validation and
  apply.
- Eval pack schema validation, expected range checks, recall/MRR metrics, and
  `kc eval run --out`.
- Artifact diffs now use the last applied snapshot when available.
- `kc init` now creates and maintains a repo-local `.agents/skills/kc/` skill
  so external agents can discover the local `kc` workflow, query-answering
  guidance, remote-ingestion guidance, and original-source citation helper.
- Release discipline for future changes: update this changelog, bump
  `src/kc/__init__.py::__version__`, run the published verification commands,
  and tag releases as `vX.Y.Z`.

### Changed

- Search and context preparation fall back to SQLite FTS with a structured
  warning when semantic ranking is unavailable.
- `kc.toml` `data_dir` and `state_dir` settings are honored unless explicitly
  overridden by global options.

## [0.2.0] - 2026-05-11

### Changed

- Made hybrid retrieval the default behavior for search and context preparation,
  combining SQLite BM25 with bundled local semantic vectors.
- `kc index build` now rebuilds semantic embeddings by default.

### Removed

- Removed public retrieval-selection switches: `--mode` on `source search` and
  `context prepare`, and `--semantic` on `index build`.

## [0.1.0] - 2026-05-11

### Added

- Initial `kc` CLI package with deterministic source registration, search,
  context preparation, citation validation, safe artifact apply, task state,
  exports, and contract conformance checks.
