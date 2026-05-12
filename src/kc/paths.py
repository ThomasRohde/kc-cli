"""Repository path resolution and traversal checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kc.errors import KcError


@dataclass(frozen=True)
class KcPaths:
    root: Path
    data_dir: Path
    state_dir: Path

    @property
    def config_path(self) -> Path:
        return self.root / "kc.toml"

    @property
    def sources_jsonl(self) -> Path:
        return self.data_dir / "sources.jsonl"

    @property
    def ranges_jsonl(self) -> Path:
        return self.data_dir / "source_ranges.jsonl"

    @property
    def source_revisions_jsonl(self) -> Path:
        return self.data_dir / "source_revisions.jsonl"

    @property
    def artifacts_jsonl(self) -> Path:
        return self.data_dir / "artifacts.jsonl"

    @property
    def citation_edges_jsonl(self) -> Path:
        return self.data_dir / "citation_edges.jsonl"

    @property
    def sqlite_path(self) -> Path:
        return self.state_dir / "state.sqlite"

    @property
    def locks_dir(self) -> Path:
        return self.state_dir / "locks"

    @property
    def plans_dir(self) -> Path:
        return self.state_dir / "plans"

    @property
    def snapshots_dir(self) -> Path:
        return self.state_dir / "snapshots"

    @property
    def tasks_dir(self) -> Path:
        return self.state_dir / "tasks"

    @property
    def context_dir(self) -> Path:
        return self.state_dir / "context"

    @property
    def operations_dir(self) -> Path:
        return self.state_dir / "operations"

    @property
    def wiki_dir(self) -> Path:
        return self.data_dir / "wiki"

    @property
    def log_path(self) -> Path:
        return self.wiki_dir / "log.md"


def current_paths() -> KcPaths:
    return current_workspace().paths


def current_workspace():
    from kc.workspace import resolve_workspace

    return resolve_workspace()


def ensure_data_dir_exists() -> KcPaths:
    paths = current_paths()
    if not paths.data_dir.exists():
        raise KcError(
            code="KC_CONFIG_NOT_FOUND",
            message=f"Knowledge data directory not found: {repo_relative(paths.data_dir)}",
            details={"data_dir": repo_relative(paths.data_dir)},
        )
    return paths


def ensure_under_root(path: Path, root: Path | None = None) -> Path:
    root = root or current_paths().root
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise KcError(
            code="KC_PATH_OUTSIDE_REPO",
            message=f"Path is outside repository root: {path}",
            details={"path": str(path), "repo_root": str(root)},
        ) from exc
    return resolved


def resolve_repo_path(path: Path | str, root: Path | None = None) -> Path:
    root = root or current_paths().root
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return ensure_under_root(candidate.resolve(), root=root)


def repo_relative(path: Path, root: Path | None = None) -> str:
    root = root or current_paths().root
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
