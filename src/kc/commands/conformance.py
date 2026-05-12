"""Read-only V1 CLI contract conformance checks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import typer

from kc.commands.common import run
from kc.commands.guide import build_guide
from kc.errors import ERROR_EXIT_MAP, KcError
from kc.output import HUMAN_RENDERERS, emit_success, envelope

PUBLIC_COMMAND_IDS = frozenset(
    {
        "guide",
        "init",
        "status",
        "source.add",
        "source.inspect",
        "source.refresh",
        "source.search",
        "index.build",
        "context.prepare",
        "artifact.new",
        "artifact.validate",
        "artifact.diff",
        "artifact.apply",
        "citation.check",
        "citation.rewrite",
        "citation.repair",
        "lint",
        "task.start",
        "task.status",
        "task.inspect",
        "task.next",
        "task.resume",
        "eval.run",
        "export",
        "doctor",
        "doctor.locks",
        "conformance",
    }
)

REQUIRED_GUIDE_SECTIONS = frozenset(
    {
        "name",
        "version",
        "description",
        "schema_version",
        "compatibility",
        "capabilities",
        "bootstrap",
        "global_options",
        "output_formats",
        "environment",
        "commands",
        "schemas",
        "citation_syntax",
        "workflows",
        "anti_patterns",
        "quality_rubric",
        "concurrency",
        "error_codes",
        "exit_codes",
        "errors",
        "examples",
    }
)

REQUIRED_COMMAND_FIELDS = frozenset(
    {
        "command_id",
        "mutates",
        "confirmation",
        "syntax",
        "important_options",
        "result_summary",
        "examples",
        "common_errors",
        "exit_codes",
    }
)

REQUIRED_ERROR_FIELDS = frozenset(
    {
        "code",
        "category",
        "message",
        "exit_code",
        "retryable",
        "suggested_action",
        "details",
    }
)

REQUIRED_ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "request_id",
        "ok",
        "command",
        "target",
        "result",
        "warnings",
        "errors",
        "metrics",
    }
)


def _row(check_id: str, passed: bool, message: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": passed,
        "message": message,
        "details": dict(details or {}),
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    passed = sum(1 for row in rows if row["passed"])
    return {"total": len(rows), "passed": passed, "failed": len(rows) - passed}


def _guide_commands(guide: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    commands = guide.get("commands", {})
    if not isinstance(commands, dict):
        return {}
    return {str(command_id): command for command_id, command in commands.items() if isinstance(command, Mapping)}


def _check_guide_sections(guide: Mapping[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED_GUIDE_SECTIONS - set(guide))
    return _row(
        "guide.required_sections",
        not missing,
        "Guide exposes all required V1 sections.",
        {"missing": missing} if missing else {},
    )


def _check_command_fields(commands: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    failures = []
    for command_id, command in sorted(commands.items()):
        missing = sorted(REQUIRED_COMMAND_FIELDS - set(command))
        command_id_mismatch = command.get("command_id") != command_id
        if missing or command_id_mismatch:
            failures.append(
                {
                    "command_id": command_id,
                    "missing": missing,
                    "command_id_mismatch": command_id_mismatch,
                }
            )
    return _row(
        "guide.command_fields",
        not failures,
        "Every guide command has the required manifest fields.",
        {"failures": failures} if failures else {},
    )


def _check_public_commands(commands: Mapping[str, Mapping[str, Any]], public_command_ids: set[str]) -> dict[str, Any]:
    guide_command_ids = set(commands)
    missing = sorted(public_command_ids - guide_command_ids)
    extra = sorted(guide_command_ids - public_command_ids)
    return _row(
        "guide.public_commands",
        not missing and not extra,
        "Guide command IDs match the public command set.",
        {"missing": missing, "extra": extra} if missing or extra else {},
    )


def _check_renderer_coverage(commands: Mapping[str, Mapping[str, Any]], human_renderers: Mapping[str, Any]) -> dict[str, Any]:
    guide_command_ids = set(commands)
    renderer_ids = set(human_renderers)
    missing = sorted(guide_command_ids - renderer_ids)
    extra = sorted(renderer_ids - guide_command_ids)
    return _row(
        "renderers.coverage",
        not missing and not extra,
        "Human renderer coverage matches guide commands.",
        {"missing": missing, "extra": extra} if missing or extra else {},
    )


def _check_error_contract(guide: Mapping[str, Any], commands: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    guide_error_codes = guide.get("error_codes", {})
    if not isinstance(guide_error_codes, Mapping):
        guide_error_codes = {}

    unknown_guide_errors = sorted(set(guide_error_codes) - set(ERROR_EXIT_MAP))
    missing_guide_errors = sorted(set(ERROR_EXIT_MAP) - set(guide_error_codes))
    exit_mismatches = []
    for code, metadata in guide_error_codes.items():
        if code not in ERROR_EXIT_MAP or not isinstance(metadata, Mapping):
            continue
        if metadata.get("exit_code") != ERROR_EXIT_MAP[code]:
            exit_mismatches.append({"code": code, "guide_exit": metadata.get("exit_code"), "mapped_exit": ERROR_EXIT_MAP[code]})

    unknown_common_errors = []
    for command_id, command in sorted(commands.items()):
        common_errors = command.get("common_errors", [])
        if not isinstance(common_errors, list):
            unknown_common_errors.append({"command_id": command_id, "error": "<common_errors-not-list>"})
            continue
        for code in common_errors:
            if code not in ERROR_EXIT_MAP:
                unknown_common_errors.append({"command_id": command_id, "error": code})

    shape_keys = set(KcError(code="KC_CONFORMANCE_FAILED", message="shape probe").to_message())
    shape_missing = sorted(REQUIRED_ERROR_FIELDS - shape_keys)

    failures = {
        "unknown_guide_errors": unknown_guide_errors,
        "missing_guide_errors": missing_guide_errors,
        "exit_mismatches": exit_mismatches,
        "unknown_common_errors": unknown_common_errors,
        "shape_missing": shape_missing,
    }
    failed = any(failures.values())
    return _row(
        "errors.contract",
        not failed,
        "Guide errors and common errors resolve to the stable KcError contract.",
        failures if failed else {},
    )


def _check_envelope_shape() -> dict[str, Any]:
    payload = envelope("conformance.shape", {"valid": True})
    missing = sorted(REQUIRED_ENVELOPE_FIELDS - set(payload))
    metrics = payload.get("metrics", {})
    missing_metrics = [] if isinstance(metrics, Mapping) and "duration_ms" in metrics else ["duration_ms"]
    return _row(
        "envelope.shape",
        not missing and not missing_metrics,
        "JSON envelope exposes the locked V1 fields.",
        {"missing": missing, "missing_metrics": missing_metrics} if missing or missing_metrics else {},
    )


def build_conformance_report(
    *,
    guide: Mapping[str, Any] | None = None,
    human_renderers: Mapping[str, Any] | None = None,
    public_command_ids: set[str] | None = None,
) -> dict[str, Any]:
    guide = build_guide() if guide is None else guide
    human_renderers = HUMAN_RENDERERS if human_renderers is None else human_renderers
    public_command_ids = set(PUBLIC_COMMAND_IDS if public_command_ids is None else public_command_ids)
    commands = _guide_commands(guide)

    rows = [
        _check_guide_sections(guide),
        _check_command_fields(commands),
        _check_public_commands(commands, public_command_ids),
        _check_renderer_coverage(commands, human_renderers),
        _check_error_contract(guide, commands),
        _check_envelope_shape(),
    ]
    summary = _summarize(rows)
    return {
        "profile": "v1",
        "valid": summary["failed"] == 0,
        "summary": summary,
        "checks": rows,
    }


def register(app: typer.Typer) -> None:
    @app.command("conformance", help="Run read-only CLI contract conformance checks.")
    def conformance() -> None:
        def _run() -> None:
            result = build_conformance_report()
            if not result["valid"]:
                failed_checks = [check for check in result["checks"] if not check["passed"]]
                raise KcError(
                    code="KC_CONFORMANCE_FAILED",
                    message="V1 conformance checks failed.",
                    details={
                        "profile": result["profile"],
                        "summary": result["summary"],
                        "failed_checks": failed_checks,
                    },
                )
            emit_success("conformance", result)

        run("conformance", _run)
