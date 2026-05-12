"""Workspace root discovery and config-aware path construction."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from kc.config import KcConfig, load_config
from kc.errors import KcError
from kc.output import state
from kc.paths import KcPaths

WorkspaceSource = Literal["explicit", "env", "kc.toml", "git", "cwd"]


@dataclass(frozen=True)
class Workspace:
    root: Path
    config: KcConfig
    paths: KcPaths
    source: WorkspaceSource


def _ancestors(start: Path) -> list[Path]:
    resolved = start.resolve()
    if resolved.is_file():
        resolved = resolved.parent
    return [resolved, *resolved.parents]


def _find_up(start: Path, name: str) -> Path | None:
    for parent in _ancestors(start):
        if (parent / name).exists():
            return parent
    return None


def _resolve_dir(root: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def resolve_workspace(
    start: Path | None = None,
    *,
    root_override: Path | str | None = None,
    data_dir_override: str | None = None,
    state_dir_override: str | None = None,
    require_initialized: bool = False,
) -> Workspace:
    start_path = (start or Path.cwd()).resolve()
    explicit = root_override if root_override is not None else state.root_override
    env_root = os.environ.get("KC_ROOT")

    if explicit:
        root = Path(explicit).expanduser().resolve()
        source: WorkspaceSource = "explicit"
    elif env_root:
        root = Path(env_root).expanduser().resolve()
        source = "env"
    else:
        config_root = _find_up(start_path, "kc.toml")
        if config_root is not None:
            root = config_root
            source = "kc.toml"
        else:
            git_root = _find_up(start_path, ".git")
            if git_root is not None:
                root = git_root
                source = "git"
            else:
                root = start_path if start_path.is_dir() else start_path.parent
                source = "cwd"

    config_exists = (root / "kc.toml").exists()
    if require_initialized and not config_exists:
        raise KcError(
            code="KC_CONFIG_NOT_FOUND",
            message="kc.toml not found. Run kc init --yes first.",
            details={"path": str(root / "kc.toml"), "workspace_root": root.as_posix()},
            suggested_action=f"run kc --root {root.as_posix()} init --yes",
        )

    config = load_config(root, required=False)
    data_dir = data_dir_override if data_dir_override is not None else state.data_dir
    state_dir = state_dir_override if state_dir_override is not None else state.state_dir
    paths = KcPaths(
        root=root,
        data_dir=_resolve_dir(root, data_dir or config.data_dir),
        state_dir=_resolve_dir(root, state_dir or config.state_dir),
    )
    state.workspace_root = root.as_posix()
    state.workspace_resolution_source = source
    return Workspace(root=root, config=config, paths=paths, source=source)
