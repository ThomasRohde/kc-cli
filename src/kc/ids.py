"""Deterministic-looking public IDs with kc prefixes."""

from __future__ import annotations

import uuid

try:
    from ulid import ULID
except Exception:  # pragma: no cover - fallback for unusual environments
    ULID = None  # type: ignore[assignment]


def new_id(prefix: str) -> str:
    if ULID is not None:
        return f"{prefix}_{ULID()}"
    return f"{prefix}_{uuid.uuid4().hex}"
