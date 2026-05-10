"""kc.result.v1 envelope and output mode handling."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Any

import orjson
from pydantic import BaseModel

from kc.errors import KcError
from kc.ids import new_id

SCHEMA_VERSION = "kc.result.v1"


@dataclass
class RuntimeState:
    format: str = "json"
    quiet: bool = False
    data_dir: str = "knowledge"
    state_dir: str = ".kc"
    request_id: str = ""
    no_input: bool = False
    start_time: float = 0.0


state = RuntimeState()


def is_llm_mode() -> bool:
    return os.environ.get("LLM", "").lower() == "true"


def is_interactive() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def init_request(request_id: str | None = None) -> None:
    state.request_id = request_id or new_id("req")
    state.start_time = time.monotonic()


def duration_ms() -> int:
    if state.start_time == 0.0:
        return 0
    return int((time.monotonic() - state.start_time) * 1000)


def to_data(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [to_data(v) for v in value]
    if isinstance(value, tuple):
        return [to_data(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_data(v) for k, v in value.items()}
    return value


def warning(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "details": details or {}}


def envelope(
    command: str,
    result: Any,
    *,
    target: dict[str, Any] | None = None,
    ok: bool = True,
    warnings: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metric_payload = {"duration_ms": duration_ms()}
    if metrics:
        metric_payload.update(metrics)
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": state.request_id,
        "ok": ok,
        "command": command,
        "target": target or {},
        "result": to_data(result),
        "warnings": warnings or [],
        "errors": errors or [],
        "metrics": metric_payload,
    }


def dumps(payload: dict[str, Any]) -> str:
    return orjson.dumps(to_data(payload), option=orjson.OPT_INDENT_2).decode()


def emit(payload: dict[str, Any], *, exit_code: int = 0) -> None:
    sys.stdout.write(dumps(payload) + "\n")
    raise SystemExit(exit_code)


def emit_success(
    command: str,
    result: Any,
    *,
    target: dict[str, Any] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
    exit_code: int = 0,
) -> None:
    emit(
        envelope(
            command,
            result,
            target=target,
            warnings=warnings,
            metrics=metrics,
        ),
        exit_code=exit_code,
    )


def emit_error(command: str, error: KcError, *, target: dict[str, Any] | None = None) -> None:
    emit(
        envelope(
            command,
            None,
            target=target,
            ok=False,
            errors=[error.to_message()],
        ),
        exit_code=error.exit_code or 90,
    )


def emit_unexpected(command: str, exc: BaseException) -> None:
    emit_error(
        command,
        KcError(
            code="KC_INTERNAL_ERROR",
            message=f"Internal error: {exc}",
            details={"exception_type": type(exc).__name__},
        ),
    )


def progress(message: str) -> None:
    if state.quiet:
        return
    sys.stderr.write(message.rstrip() + "\n")
    sys.stderr.flush()
