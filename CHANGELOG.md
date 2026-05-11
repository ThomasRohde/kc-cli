# Changelog

All notable changes to this project will be documented in this file.

This project uses Semantic Versioning for the Python package version exposed by
`src/kc/__init__.py`, the Hatch build metadata, `kc --version`, and `kc guide`.

## [Unreleased]

### Added

- Release discipline for future changes: update this changelog, bump
  `src/kc/__init__.py::__version__`, run the published verification commands,
  and tag releases as `vX.Y.Z`.

## [1.0.0] - 2026-05-11

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
