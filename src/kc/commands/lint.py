from __future__ import annotations

import re
from typing import Annotated

import typer

from kc.commands.artifact import validate_artifact_file
from kc.commands.common import (
    load_artifacts,
    load_citation_edges,
    load_ranges,
    load_sources,
    parse_checks,
    run,
)
from kc.errors import EXIT_VALIDATION, KcError
from kc.fingerprints import raw_fingerprint
from kc.output import emit, emit_success, envelope
from kc.paths import current_paths, resolve_repo_path
from kc.store.sqlite import index_status

LOG_REF_RE = re.compile(r"\b(?P<kind>plan|task)_[A-Z0-9]+\b")
DEFAULT_CHECKS = {"citations", "stale", "orphans"}
ALLOWED_CHECKS = {"citations", "stale", "orphans", "duplicates", "index", "log"}


def register(app: typer.Typer) -> None:
    @app.command("lint", help="Run repository integrity checks for citations, stale sources, and orphaned artifacts.")
    def lint(
        checks: Annotated[
            str,
            typer.Option("--checks", help="Comma-separated checks: citations,stale,orphans."),
        ] = "citations,stale,orphans",
    ) -> None:
        def _run() -> None:
            enabled = parse_checks(checks, allowed=ALLOWED_CHECKS, all_checks=ALLOWED_CHECKS)
            issues: list[dict] = []
            paths = current_paths()
            sources = load_sources()
            ranges = load_ranges()
            artifacts = load_artifacts()
            citation_edges = load_citation_edges()
            source_ids = [source.source_id for source in sources]
            range_ids = [source_range.range_id for source_range in ranges]
            artifact_ids = [artifact.artifact_id for artifact in artifacts]
            artifact_paths = {artifact.path for artifact in artifacts}

            if "duplicates" in enabled:
                issues.extend(_duplicate_issues("source_id", source_ids, "KC_CONFIG_INVALID"))
                issues.extend(_duplicate_issues("range_id", range_ids, "KC_CONFIG_INVALID"))
                issues.extend(
                    _duplicate_issues("artifact_id", artifact_ids, "KC_ARTIFACT_SCHEMA_INVALID")
                )

            if "stale" in enabled:
                for source in sources:
                    original = source.metadata.get("original_path")
                    if not isinstance(original, str):
                        continue
                    path = resolve_repo_path(original, paths.root)
                    if not path.exists():
                        issues.append(
                            {
                                "code": "KC_SOURCE_STALE",
                                "message": f"Source file is missing: {source.uri}",
                                "source_id": source.source_id,
                            }
                        )
                    elif raw_fingerprint(path) != source.fingerprint:
                        issues.append(
                            {
                                "code": "KC_SOURCE_STALE",
                                "message": f"Source fingerprint changed: {source.uri}",
                                "source_id": source.source_id,
                            }
                        )

            if "orphans" in enabled:
                source_id_set = set(source_ids)
                range_id_set = set(range_ids)
                for source_range in ranges:
                    if source_range.source_id not in source_id_set:
                        issues.append(
                            {
                                "code": "KC_SOURCE_NOT_FOUND",
                                "message": f"Source range has no registered source: {source_range.range_id}",
                                "range_id": source_range.range_id,
                                "source_id": source_range.source_id,
                            }
                        )
                for edge in citation_edges:
                    if edge.artifact_path not in artifact_paths:
                        issues.append(
                            {
                                "code": "KC_ARTIFACT_NOT_FOUND",
                                "message": f"Citation edge has no registered artifact: {edge.artifact_path}",
                                "edge_id": edge.edge_id,
                                "artifact_path": edge.artifact_path,
                            }
                        )
                    if edge.source_id not in source_id_set:
                        issues.append(
                            {
                                "code": "KC_CITATION_SOURCE_MISSING",
                                "message": f"Citation edge source is missing: {edge.source_id}",
                                "edge_id": edge.edge_id,
                                "source_id": edge.source_id,
                            }
                        )
                    if edge.range_id and edge.range_id not in range_id_set:
                        issues.append(
                            {
                                "code": "KC_CITATION_RANGE_MISSING",
                                "message": f"Citation edge range is missing: {edge.range_id}",
                                "edge_id": edge.edge_id,
                                "range_id": edge.range_id,
                            }
                        )

            for artifact in artifacts:
                artifact_path = resolve_repo_path(artifact.path, paths.root)
                if "orphans" in enabled and not artifact_path.exists():
                    issues.append(
                        {
                            "code": "KC_ARTIFACT_NOT_FOUND",
                            "message": f"Registered artifact file is missing: {artifact.path}",
                            "artifact_id": artifact.artifact_id,
                        }
                    )
                    continue
                if "citations" in enabled and artifact_path.exists():
                    result = validate_artifact_file(artifact_path)
                    if not result["valid"]:
                        for error in result["errors"]:
                            issues.append(error | {"artifact_path": artifact.path})

            if "index" in enabled:
                status = index_status(paths.sqlite_path, sources, ranges)
                if status["stale"]:
                    issues.append(
                        {
                            "code": "KC_INDEX_BUILD_FAILED",
                            "message": "SQLite search index is missing or stale.",
                            "index": status,
                        }
                    )

            if "log" in enabled and paths.log_path.exists():
                plan_dir = paths.plans_dir
                task_dir = paths.tasks_dir
                for match in LOG_REF_RE.finditer(paths.log_path.read_text(encoding="utf-8")):
                    ref = match.group(0)
                    if ref.startswith("plan_") and not (plan_dir / f"{ref}.json").exists():
                        issues.append(
                            {
                                "code": "KC_ARTIFACT_SCHEMA_INVALID",
                                "message": f"Knowledge log references unknown plan: {ref}",
                                "reference": ref,
                            }
                        )
                    if ref.startswith("task_") and not (task_dir / f"{ref}.json").exists():
                        issues.append(
                            {
                                "code": "KC_ARTIFACT_SCHEMA_INVALID",
                                "message": f"Knowledge log references unknown task: {ref}",
                                "reference": ref,
                            }
                        )
            result = {
                "valid": not issues,
                "checks": sorted(enabled),
                "sources": len(sources),
                "artifacts": len(artifacts),
                "issues": issues,
                "next_commands": _next_commands(issues),
            }
            if issues:
                errors = [
                    KcError(
                        code=str(issue.get("code", "KC_ARTIFACT_SCHEMA_INVALID")),
                        message=str(issue.get("message", "Lint issue.")),
                        details=issue,
                        suggested_action="fix lint issue",
                    ).to_message()
                    for issue in issues
                ]
                emit(
                    envelope(
                        "lint",
                        None,
                        ok=False,
                        errors=errors,
                    ),
                    exit_code=max(int(error["exit_code"]) for error in errors)
                    if errors
                    else EXIT_VALIDATION,
                )
            emit_success("lint", result)

        run("lint", _run)


def _duplicate_issues(field: str, values: list[str], code: str) -> list[dict]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return [
        {
            "code": code,
            "message": f"Duplicate {field}: {value}",
            "field": field,
            "value": value,
        }
        for value in sorted(duplicates)
    ]


def _next_commands(issues: list[dict]) -> list[str]:
    commands: set[str] = set()
    for issue in issues:
        code = issue.get("code")
        if code == "KC_SOURCE_STALE" and issue.get("source_id"):
            commands.add(f"kc source refresh {issue['source_id']} --dry-run")
        elif code == "KC_INDEX_BUILD_FAILED":
            commands.add("kc index build")
        elif code in {"KC_CITATION_RANGE_MISSING", "KC_CITATION_STALE_SOURCE"}:
            artifact_path = issue.get("artifact_path")
            if artifact_path:
                commands.add(f"kc citation repair --file {artifact_path} --dry-run")
        elif code in {"KC_ARTIFACT_SCHEMA_INVALID", "KC_VALIDATION_MISSING_CITATION"}:
            artifact_path = issue.get("artifact_path")
            if artifact_path:
                commands.add(f"kc artifact validate --file {artifact_path}")
    return sorted(commands)
