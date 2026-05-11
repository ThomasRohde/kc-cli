"""kc.result.v1 envelope and output mode handling."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
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


Summary = dict[str, Any]
SummaryRenderer = Callable[[dict[str, Any]], Summary]
HUMAN_RENDERERS: dict[str, SummaryRenderer] = {}


def _renderer(command: str) -> Callable[[SummaryRenderer], SummaryRenderer]:
    def _register(func: SummaryRenderer) -> SummaryRenderer:
        HUMAN_RENDERERS[command] = func
        return func

    return _register


def _value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "0"
        if all(not isinstance(item, dict | list | tuple) for item in value) and len(value) <= 5:
            return ", ".join(_value(item) for item in value)
        return f"{len(value)} items"
    if isinstance(value, dict):
        return f"{len(value)} fields"
    return str(value)


def _count(value: Any) -> int:
    return len(value) if isinstance(value, list | dict | tuple | set) else 0


def _summary(title: str, pairs: list[tuple[str, Any]], rows: list[dict[str, Any]] | None = None) -> Summary:
    return {"title": title, "pairs": pairs, "rows": rows or []}


def _plan_id(result: dict[str, Any]) -> str:
    plan = result.get("plan")
    return str(plan.get("plan_id", "")) if isinstance(plan, dict) else ""


def _artifact_path(result: dict[str, Any]) -> str:
    artifact = result.get("artifact")
    if isinstance(artifact, dict):
        return str(artifact.get("path", ""))
    return str(result.get("path", ""))


def _locator_text(row: dict[str, Any]) -> str:
    locator = row.get("locator")
    if not isinstance(locator, dict):
        return ""
    if locator.get("kind") == "json_pointer":
        return str(locator.get("pointer", ""))
    if locator.get("kind") == "csv_row_range":
        return f"R{locator.get('start_row')}-R{locator.get('end_row')}"
    start = locator.get("start_line")
    end = locator.get("end_line")
    return f"L{start}-L{end}" if start is not None and end is not None else ""


def _first_results(result: dict[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    rows = result.get("results")
    return list(rows[:limit]) if isinstance(rows, list) else []


def _render_pairs_table(pairs: list[tuple[str, Any]]) -> list[str]:
    if not pairs:
        return []
    width = max(len(label) for label, _value_item in pairs)
    return [f"{label.ljust(width)}  {_value(value)}" for label, value in pairs]


def _render_rows_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    headers = list(rows[0])
    widths = {
        header: max(len(header), *(len(_value(row.get(header))) for row in rows))
        for header in headers
    }
    output = ["  ".join(header.ljust(widths[header]) for header in headers)]
    output.append("  ".join("-" * widths[header] for header in headers))
    output.extend(
        "  ".join(_value(row.get(header)).ljust(widths[header]) for header in headers)
        for row in rows
    )
    return output


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    if not rows:
        return []
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _header in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(_value(item).replace("\n", " ") for item in row) + " |")
    return output


def _warning_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return []
    return [
        {"code": warning.get("code", ""), "message": warning.get("message", "")}
        for warning in warnings
        if isinstance(warning, dict)
    ]


def _render_success_table(payload: dict[str, Any]) -> str:
    renderer = HUMAN_RENDERERS.get(str(payload.get("command")))
    summary = renderer(payload) if renderer else _generic_summary(payload)
    lines = [str(summary["title"])]
    lines.extend(_render_pairs_table(list(summary.get("pairs", []))))
    rows = list(summary.get("rows", []))
    if rows:
        lines.append("")
        lines.extend(_render_rows_table(rows))
    warnings = _warning_rows(payload)
    if warnings:
        lines.append("")
        lines.append("Warnings")
        lines.extend(_render_rows_table(warnings))
    return "\n".join(lines)


def _render_success_markdown(payload: dict[str, Any]) -> str:
    renderer = HUMAN_RENDERERS.get(str(payload.get("command")))
    summary = renderer(payload) if renderer else _generic_summary(payload)
    lines = [f"# {summary['title']}", ""]
    pair_rows = [[label, value] for label, value in list(summary.get("pairs", []))]
    lines.extend(_markdown_table(["Field", "Value"], pair_rows))
    rows = list(summary.get("rows", []))
    if rows:
        headers = list(rows[0])
        lines.extend(["", "## Results", ""])
        lines.extend(_markdown_table(headers, [[row.get(header) for header in headers] for row in rows]))
    warnings = _warning_rows(payload)
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(
            _markdown_table(["Code", "Message"], [[row["code"], row["message"]] for row in warnings])
        )
    return "\n".join(lines)


def _render_error_table(payload: dict[str, Any]) -> str:
    raw_errors = payload.get("errors")
    errors = raw_errors if isinstance(raw_errors, list) else []
    rows = [
        {
            "code": error.get("code", ""),
            "message": error.get("message", ""),
            "exit_code": error.get("exit_code", ""),
            "suggested_action": error.get("suggested_action", ""),
        }
        for error in errors
        if isinstance(error, dict)
    ]
    lines = [f"Error: {payload.get('command', 'kc')}"]
    lines.extend(_render_rows_table(rows))
    return "\n".join(lines)


def _render_error_markdown(payload: dict[str, Any]) -> str:
    raw_errors = payload.get("errors")
    errors = raw_errors if isinstance(raw_errors, list) else []
    rows = [
        [
            error.get("code", ""),
            error.get("message", ""),
            error.get("exit_code", ""),
            error.get("suggested_action", ""),
        ]
        for error in errors
        if isinstance(error, dict)
    ]
    lines = [f"# Error: {payload.get('command', 'kc')}", ""]
    lines.extend(_markdown_table(["Code", "Message", "Exit Code", "Suggested Action"], rows))
    return "\n".join(lines)


def render_human(payload: dict[str, Any]) -> str:
    if state.format == "markdown":
        return _render_success_markdown(payload) if payload.get("ok") else _render_error_markdown(payload)
    return _render_success_table(payload) if payload.get("ok") else _render_error_table(payload)


def _generic_summary(payload: dict[str, Any]) -> Summary:
    result = payload.get("result")
    pairs: list[tuple[str, Any]] = [("command", payload.get("command")), ("ok", payload.get("ok"))]
    if isinstance(result, dict):
        pairs.extend((key, value) for key, value in result.items() if not isinstance(value, list | dict))
    return _summary(str(payload.get("command", "kc")), pairs)


@_renderer("guide")
def _guide_summary(payload: dict[str, Any]) -> Summary:
    raw_result = payload.get("result")
    result: dict[str, Any] = raw_result if isinstance(raw_result, dict) else {}
    raw_commands = result.get("commands")
    commands: dict[str, Any] = raw_commands if isinstance(raw_commands, dict) else {}
    raw_target = payload.get("target")
    target: dict[str, Any] = raw_target if isinstance(raw_target, dict) else {}
    rows = [
        {
            "command": command,
            "mutates": data.get("mutates"),
            "confirmation": data.get("confirmation"),
        }
        for command, data in list(commands.items())[:12]
        if isinstance(data, dict)
    ]
    return _summary(
        "guide",
        [
            ("section", target.get("section")),
            ("commands", len(commands)),
            ("schema_version", result.get("schema_version")),
        ],
        rows,
    )


@_renderer("conformance")
def _conformance_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    rows = [
        {
            "check": check.get("check_id"),
            "passed": check.get("passed"),
            "message": check.get("message"),
        }
        for check in result.get("checks", [])
        if isinstance(check, dict)
    ]
    return _summary(
        "conformance",
        [
            ("profile", result.get("profile")),
            ("valid", result.get("valid")),
            ("total", summary.get("total")),
            ("passed", summary.get("passed")),
            ("failed", summary.get("failed")),
        ],
        rows,
    )


@_renderer("init")
def _init_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    return _summary(
        "init",
        [
            ("dry_run", result.get("dry_run")),
            ("profile", result.get("profile")),
            ("created", _count(result.get("created"))),
            ("planned", _count(result.get("planned"))),
            ("noop", _count(result.get("noop"))),
        ],
    )


@_renderer("source.add")
def _source_add_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    return _summary(
        "source.add",
        [
            ("dry_run", result.get("dry_run")),
            ("source_id", result.get("source_id")),
            ("uri", result.get("uri")),
            ("media_type", result.get("media_type")),
            ("ranges_extracted", result.get("ranges_extracted")),
            ("copied", result.get("copied")),
        ],
    )


@_renderer("source.inspect")
def _source_inspect_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    source = result.get("source") if isinstance(result.get("source"), dict) else {}
    rows = []
    ranges = result.get("ranges")
    if isinstance(ranges, list):
        rows = [
            {
                "range_id": row.get("range_id"),
                "locator": _locator_text(row),
                "excerpt": str(row.get("excerpt", ""))[:80],
            }
            for row in ranges[:8]
            if isinstance(row, dict)
        ]
    return _summary(
        "source.inspect",
        [
            ("source_id", source.get("source_id")),
            ("uri", source.get("uri")),
            ("stale", result.get("stale")),
            ("ranges", _count(ranges)),
        ],
        rows,
    )


@_renderer("source.refresh")
def _source_refresh_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    return _summary(
        "source.refresh",
        [
            ("dry_run", result.get("dry_run")),
            ("source_id", result.get("source_id")),
            ("ranges_removed", result.get("ranges_removed")),
            ("ranges_extracted", result.get("ranges_extracted")),
            ("impacted_artifacts", _count(result.get("impacted_artifacts"))),
            ("semantic_index_rebuilt", result.get("semantic_index_rebuilt")),
        ],
    )


@_renderer("source.search")
def _source_search_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    rows = [
        {
            "rank": item.get("scores", {}).get("hybrid_rank"),
            "source_id": item.get("source_id"),
            "locator": _locator_text(item),
            "citation": item.get("citation_token"),
        }
        for item in _first_results(result)
        if isinstance(item, dict)
    ]
    return _summary(
        "source.search",
        [("query", result.get("query")), ("mode", result.get("mode")), ("total", result.get("total"))],
        rows,
    )


@_renderer("index.build")
def _index_build_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    semantic = result.get("semantic")
    enabled = semantic.get("enabled") if isinstance(semantic, dict) else result.get("semantic")
    return _summary(
        "index.build",
        [
            ("dry_run", result.get("dry_run")),
            ("clean", result.get("clean")),
            ("sources", result.get("sources")),
            ("ranges", result.get("ranges")),
            ("semantic", enabled),
            ("db_path", result.get("db_path")),
        ],
    )


@_renderer("context.prepare")
def _context_prepare_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    rows = [
        {
            "source_id": item.get("source_id"),
            "locator": _locator_text(item),
            "citation": item.get("citation_token"),
        }
        for item in list(result.get("candidate_ranges", []))[:8]
        if isinstance(item, dict)
    ]
    return _summary(
        "context.prepare",
        [
            ("query", result.get("search_query")),
            ("mode", result.get("mode")),
            ("candidate_ranges", _count(result.get("candidate_ranges"))),
            ("existing_artifacts", _count(result.get("existing_artifacts"))),
            ("grounding_policy", result.get("grounding_policy")),
        ],
        rows,
    )


@_renderer("artifact.new")
def _artifact_new_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    return _summary(
        "artifact.new",
        [
            ("dry_run", result.get("dry_run")),
            ("artifact_id", result.get("artifact_id")),
            ("path", result.get("path")),
            ("bytes", result.get("bytes")),
        ],
    )


@_renderer("artifact.validate")
def _artifact_validate_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    return _summary(
        "artifact.validate",
        [
            ("valid", result.get("valid")),
            ("path", result.get("path")),
            ("fingerprint", result.get("fingerprint")),
            ("citations", _count(result.get("citation_edges"))),
            ("errors", _count(result.get("errors"))),
        ],
    )


@_renderer("artifact.diff")
def _artifact_diff_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    return _summary(
        "artifact.diff",
        [
            ("plan_id", plan.get("plan_id")),
            ("operations", _count(plan.get("operations"))),
            ("risk_flags", _count(result.get("risk_flags"))),
        ],
    )


@_renderer("artifact.apply")
def _artifact_apply_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    return _summary(
        "artifact.apply",
        [
            ("dry_run", result.get("dry_run")),
            ("applied", result.get("applied")),
            ("noop", result.get("noop")),
            ("plan_id", _plan_id(result)),
            ("artifact", _artifact_path(result)),
            ("citation_edges", result.get("citation_edges")),
        ],
    )


@_renderer("citation.check")
def _citation_check_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    rows = [
        {"path": item.get("path"), "valid": item.get("valid"), "citations": item.get("citations")}
        for item in list(result.get("files", []))[:8]
        if isinstance(item, dict)
    ]
    return _summary(
        "citation.check",
        [("valid", result.get("valid")), ("files", _count(result.get("files"))), ("problems", _count(result.get("problems")))],
        rows,
    )


@_renderer("lint")
def _lint_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    return _summary(
        "lint",
        [
            ("valid", result.get("valid")),
            ("checks", result.get("checks")),
            ("sources", result.get("sources")),
            ("artifacts", result.get("artifacts")),
            ("issues", _count(result.get("issues"))),
        ],
    )


@_renderer("export")
def _export_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    return _summary(
        "export",
        [("format", result.get("format")), ("bytes", result.get("bytes")), ("out", result.get("out"))],
    )


@_renderer("task.start")
def _task_start_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    return _summary(
        "task.start",
        [
            ("task_id", task.get("task_id")),
            ("status", task.get("status")),
            ("candidate_ranges", _count(task.get("candidate_ranges"))),
            ("resume_command", result.get("resume_command")),
        ],
    )


@_renderer("task.status")
def _task_status_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    rows = [{"next_command": command} for command in result.get("next_commands", [])]
    return _summary(
        "task.status",
        [("task_id", result.get("task_id")), ("status", result.get("status")), ("updated_at", result.get("updated_at"))],
        rows,
    )


@_renderer("task.inspect")
def _task_inspect_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    return _summary(
        "task.inspect",
        [
            ("task_id", task.get("task_id")),
            ("status", task.get("status")),
            ("goal", task.get("goal")),
            ("events", _count(task.get("events"))),
        ],
    )


@_renderer("task.resume")
def _task_resume_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    return _summary(
        "task.resume",
        [
            ("task_id", task.get("task_id")),
            ("status", task.get("status")),
            ("events", _count(task.get("events"))),
        ],
    )


@_renderer("eval.run")
def _eval_run_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    return _summary(
        "eval.run",
        [("pack", result.get("pack")), ("total", result.get("total")), ("passed", result.get("passed"))],
    )


@_renderer("doctor")
def _doctor_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    index = result.get("index") if isinstance(result.get("index"), dict) else {}
    raw_last_build = index.get("last_build")
    last_build: dict[str, Any] = raw_last_build if isinstance(raw_last_build, dict) else {}
    semantic = result.get("semantic") if isinstance(result.get("semantic"), dict) else {}
    raw_index_metadata = semantic.get("index_metadata")
    index_metadata: dict[str, Any] = raw_index_metadata if isinstance(raw_index_metadata, dict) else {}
    return _summary(
        "doctor",
        [
            ("config_exists", result.get("config_exists")),
            ("data_dir_exists", result.get("data_dir_exists")),
            ("state_dir_exists", result.get("state_dir_exists")),
            ("sqlite_exists", result.get("sqlite_exists")),
            ("locks", result.get("locks")),
            ("index_stale", index.get("stale")),
            ("index_sources", last_build.get("sources")),
            ("index_ranges", last_build.get("ranges")),
            ("semantic_model_available", semantic.get("model_available")),
            ("semantic_metadata_match", semantic.get("metadata_match")),
            ("semantic_vectors", semantic.get("vector_count")),
            ("semantic_index_ranges", index_metadata.get("ranges")),
            ("semantic_missing_vectors", semantic.get("missing_vectors")),
            ("semantic_stale_vectors", semantic.get("stale_vectors")),
            ("semantic_unavailable_reason", semantic.get("unavailable_reason")),
        ],
    )


@_renderer("doctor.locks")
def _doctor_locks_summary(payload: dict[str, Any]) -> Summary:
    result = payload["result"]
    rows = [
        {"path": item.get("path"), "metadata": _count(item.get("metadata"))}
        for item in list(result.get("locks", []))[:8]
        if isinstance(item, dict)
    ]
    return _summary(
        "doctor.locks",
        [
            ("clear_stale", result.get("clear_stale")),
            ("dry_run", result.get("dry_run")),
            ("locks", _count(result.get("locks"))),
            ("cleared", _count(result.get("cleared"))),
        ],
        rows,
    )


def emit(payload: dict[str, Any], *, exit_code: int = 0) -> None:
    rendered = dumps(payload) if state.format == "json" else render_human(payload)
    sys.stdout.write(rendered + "\n")
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
