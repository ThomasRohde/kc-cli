"""JSONL canonical store helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import orjson
from pydantic import BaseModel

from kc.atomic_write import atomic_write_bytes
from kc.errors import KcError


def read_jsonl[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    if not path.exists():
        return []
    records: list[T] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(model.model_validate(orjson.loads(line)))
        except Exception as exc:
            raise KcError(
                code="KC_CONFIG_INVALID",
                message=f"Invalid JSONL record in {path} at line {line_no}: {exc}",
                details={"path": str(path), "line": line_no},
            ) from exc
    return records


def write_jsonl(path: Path, records: Sequence[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = [
        orjson.dumps(record.model_dump(mode="json"), option=orjson.OPT_APPEND_NEWLINE)
        for record in records
    ]
    atomic_write_bytes(path, b"".join(chunks))


def append_jsonl(path: Path, records: Iterable[BaseModel]) -> None:
    existing: list[BaseModel] = []
    if path.exists():
        existing_lines = path.read_bytes().splitlines()
        existing_data = [orjson.loads(line) for line in existing_lines if line.strip()]
        existing = [_RawModel(value=item) for item in existing_data]
    write_jsonl(path, [*existing, *records])


class _RawModel(BaseModel):
    value: dict

    def model_dump(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self.value
