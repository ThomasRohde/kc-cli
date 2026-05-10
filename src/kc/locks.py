"""Simple visible lock files for write commands."""

from __future__ import annotations

import json
import os
import socket
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kc.errors import KcError
from kc.ids import new_id
from kc.output import state


@dataclass
class FileLock:
    locks_dir: Path
    name: str
    command: str
    target: str

    def __post_init__(self) -> None:
        self.locks_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.locks_dir / f"{self.name}.lock"
        self.acquired = False

    def __enter__(self) -> FileLock:
        metadata = {
            "schema_version": "kc.lock.v1",
            "lock_id": new_id("lock"),
            "created_at": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "command": self.command,
            "request_id": state.request_id,
            "target": self.target,
        }
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            holder: dict[str, Any] = {}
            try:
                holder = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                holder = {"lock_file": str(self.path)}
            raise KcError(
                code="KC_LOCK_HELD",
                message=f"Lock is held: {self.path}",
                details={"lock_file": str(self.path), "holder": holder},
                retryable=True,
            ) from exc
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
            f.write("\n")
        self.acquired = True
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.acquired:
            with suppress(FileNotFoundError):
                self.path.unlink()
