"""Repo-level mutation transaction and operation journal."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kc.atomic_write import atomic_write_text
from kc.commands.common import json_dumps
from kc.ids import new_id
from kc.locks import FileLock
from kc.paths import KcPaths, repo_relative


@dataclass
class MutationTransaction:
    paths: KcPaths
    command: str
    targets: list[str]
    lock_name: str = "repo-write"
    operation_id: str = field(default_factory=lambda: new_id("op"))

    def __enter__(self) -> MutationTransaction:
        self._lock = FileLock(
            self.paths.locks_dir,
            self.lock_name,
            self.command,
            ", ".join(self.targets),
        )
        self._lock.__enter__()
        self.paths.operations_dir.mkdir(parents=True, exist_ok=True)
        self.operation_path = self.paths.operations_dir / f"{self.operation_id}.json"
        self._write_status("started")
        return self

    def commit(self, details: dict[str, Any] | None = None) -> None:
        self._write_status("committed", details=details)

    def _write_status(self, status: str, details: dict[str, Any] | None = None) -> None:
        payload = {
            "schema_version": "kc.operation.v1",
            "operation_id": self.operation_id,
            "command": self.command,
            "targets": self.targets,
            "status": status,
            "updated_at": datetime.now(UTC).isoformat(),
            "details": details or {},
        }
        atomic_write_text(self.operation_path, json_dumps(payload) + "\n")

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None:
            self._write_status("failed", details={"exception_type": getattr(exc_type, "__name__", str(exc_type))})
        self._lock.__exit__(exc_type, exc, tb)


def mutation_transaction(paths: KcPaths, command: str, targets: list[Path | str]) -> MutationTransaction:
    return MutationTransaction(
        paths=paths,
        command=command,
        targets=[
            repo_relative(target) if isinstance(target, Path) else str(target)
            for target in targets
        ],
    )
