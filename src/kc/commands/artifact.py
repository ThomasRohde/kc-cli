from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import orjson
import typer

from kc.artifacts.diff import build_artifact_plan
from kc.artifacts.frontmatter import dump_frontmatter
from kc.artifacts.markdown import (
    citation_coverage_issues,
    markdown_title,
    read_markdown_artifact,
    required_section_names,
)
from kc.atomic_write import atomic_write_text, copy_snapshot
from kc.commands.common import (
    artifact_by_path,
    json_dumps,
    load_artifacts,
    load_citation_edges,
    load_ranges,
    load_sources,
    now,
    path_lock_name,
    run,
    save_artifacts,
    save_citation_edges,
)
from kc.config import load_config
from kc.errors import EXIT_PROVENANCE, EXIT_VALIDATION, KcError
from kc.fingerprints import raw_fingerprint
from kc.ids import new_id
from kc.locks import FileLock
from kc.models.artifact import ArtifactRecord, SourceRef
from kc.models.citation import ArtifactLocator, CitationEdgeRecord
from kc.models.plan import PlanRecord
from kc.output import emit, emit_success, envelope, is_llm_mode
from kc.paths import current_paths, ensure_under_root, repo_relative
from kc.provenance.citations import validate_citations
from kc.store.sqlite import get_idempotency, rebuild_index, save_idempotency, save_plan

app = typer.Typer(help="Create, validate, diff, and safely apply knowledge artifacts.")

ALLOWED_ARTIFACT_TYPES = {
    "knowledge_page",
    "glossary",
    "decision_note",
    "source_index",
    "log_entry",
    "eval_pack",
}
ALLOWED_ARTIFACT_STATUSES = {"draft", "active", "deprecated", "superseded"}
REQUIRED_MARKDOWN_FRONTMATTER = {
    "schema_version",
    "artifact_id",
    "title",
    "status",
    "domain",
    "artifact_type",
    "requires_citations",
    "source_refs",
}
ALLOWED_STATUS_TRANSITIONS = {
    "draft": {"draft", "active", "deprecated", "superseded"},
    "active": {"active", "deprecated", "superseded"},
    "deprecated": {"deprecated"},
    "superseded": {"superseded"},
}


def _artifact_template(
    *,
    artifact_id: str,
    title: str,
    artifact_type: str,
    status: str,
    domain: list[str],
    source_ids: list[str],
) -> str:
    frontmatter = {
        "schema_version": "kc.knowledge_page.v1",
        "artifact_id": artifact_id,
        "title": title,
        "status": status,
        "domain": domain,
        "artifact_type": artifact_type,
        "requires_citations": True,
        "source_refs": [{"source_id": source_id, "ranges": []} for source_id in source_ids],
        "last_validated_at": None,
    }
    body = f"""# {title}

## Summary

[kc:todo] Add a source-backed summary.

## Source-backed facts

- [kc:todo] Add cited facts.

## Inferences

- [kc:todo] Add marked inferences only when needed.

## Open questions

- [kc:todo] Capture unresolved questions.

## Source notes

"""
    return dump_frontmatter(frontmatter, body)


@app.command("new", help="Create a deterministic artifact skeleton; writes only with --yes.")
def new(
    path: Annotated[Path, typer.Option("--path", help="Artifact path.")],
    title: Annotated[str, typer.Option("--title", help="Artifact title.")],
    artifact_type: Annotated[str, typer.Option("--type", help="Artifact type.")] = "knowledge_page",
    domain: Annotated[list[str] | None, typer.Option("--domain", help="Domain tag.")] = None,
    source_id: Annotated[
        list[str] | None, typer.Option("--source-id", help="Source reference.")
    ] = None,
    status: Annotated[str, typer.Option("--status", help="draft or active.")] = "draft",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Write skeleton.")] = False,
) -> None:
    def _run() -> None:
        target = ensure_under_root((Path.cwd() / path).resolve())
        effective_dry_run = dry_run or not yes
        if target.exists() and not effective_dry_run:
            raise KcError(
                code="KC_FILE_EXISTS",
                message=f"Artifact already exists: {path}",
                details={"path": str(path)},
            )
        artifact_id = new_id("art")
        content = _artifact_template(
            artifact_id=artifact_id,
            title=title,
            artifact_type=artifact_type,
            status=status,
            domain=list(domain or []),
            source_ids=list(source_id or []),
        )
        if not effective_dry_run:
            atomic_write_text(target, content)
        emit_success(
            "artifact.new",
            {
                "dry_run": effective_dry_run,
                "artifact_id": artifact_id,
                "path": repo_relative(target),
                "bytes": len(content.encode("utf-8")),
                "content_preview": content if effective_dry_run else None,
            },
            target={"path": str(path), "artifact_type": artifact_type},
        )

    run("artifact.new", _run)


def validate_artifact_file(
    file: Path,
    *,
    allow_uncited: bool = False,
    schema: str | None = None,
) -> dict[str, Any]:
    paths = current_paths()
    target = ensure_under_root((Path.cwd() / file).resolve())
    if not target.exists():
        raise KcError(
            code="KC_ARTIFACT_NOT_FOUND",
            message=f"Artifact not found: {file}",
            details={"path": str(file)},
        )
    checks: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    edges: list[CitationEdgeRecord] = []
    frontmatter: dict[str, Any] = {}
    body = ""
    text = target.read_text(encoding="utf-8-sig")
    sources = load_sources()
    ranges = load_ranges()
    source_ids = {source.source_id for source in sources}
    range_by_id = {source_range.range_id: source_range for source_range in ranges}
    existing = artifact_by_path(target)
    if target.suffix.lower() in {".md", ".markdown"}:
        frontmatter, body, text = read_markdown_artifact(target)
        if not frontmatter:
            errors.append(
                {
                    "code": "KC_ARTIFACT_SCHEMA_INVALID",
                    "message": "Markdown artifact requires YAML frontmatter.",
                    "line": 1,
                }
            )
        missing_fields = sorted(REQUIRED_MARKDOWN_FRONTMATTER - set(frontmatter))
        if missing_fields:
            errors.append(
                {
                    "code": "KC_ARTIFACT_SCHEMA_INVALID",
                    "message": "Markdown artifact frontmatter is missing required fields.",
                    "details": {"missing_fields": missing_fields},
                }
            )
        declared_schema = frontmatter.get("schema_version")
        if schema and declared_schema != schema:
            errors.append(
                {
                    "code": "KC_ARTIFACT_SCHEMA_INVALID",
                    "message": f"Artifact schema_version does not match --schema {schema}.",
                    "details": {"schema": schema, "actual": declared_schema},
                }
            )
        status = str(frontmatter.get("status", "draft"))
        artifact_type = str(frontmatter.get("artifact_type", "knowledge_page"))
        if artifact_type not in ALLOWED_ARTIFACT_TYPES:
            errors.append(
                {
                    "code": "KC_ARTIFACT_SCHEMA_INVALID",
                    "message": f"Unknown artifact_type: {artifact_type}",
                    "details": {"artifact_type": artifact_type},
                }
            )
        if status not in ALLOWED_ARTIFACT_STATUSES:
            errors.append(
                {
                    "code": "KC_ARTIFACT_STATUS_INVALID",
                    "message": f"Unknown artifact status: {status}",
                    "details": {"status": status},
                }
            )
        if existing and status not in ALLOWED_STATUS_TRANSITIONS.get(existing.status, {existing.status}):
            errors.append(
                {
                    "code": "KC_ARTIFACT_STATUS_INVALID",
                    "message": f"Invalid artifact status transition: {existing.status} -> {status}",
                    "details": {"from": existing.status, "to": status},
                }
            )
        errors.extend(_validate_source_refs(frontmatter.get("source_refs"), source_ids, range_by_id))
        requires_citations = bool(frontmatter.get("requires_citations", True))
        required_sections = {"summary", "source-backed facts", "open questions"}
        headings = required_section_names(body)
        missing_sections = sorted(required_sections - headings)
        if missing_sections:
            errors.append(
                {
                    "code": "KC_ARTIFACT_SCHEMA_INVALID",
                    "message": "Missing required sections.",
                    "details": {"missing_sections": missing_sections},
                }
            )
        errors.extend(
            citation_coverage_issues(
                body,
                status=status,
                requires_citations=requires_citations,
                allow_uncited=allow_uncited,
            )
        )
        edges, citation_problems = validate_citations(
            repo_relative(target),
            text,
            sources_path=paths.sources_jsonl,
            ranges_path=paths.ranges_jsonl,
            artifact_id=frontmatter.get("artifact_id"),
        )
        errors.extend(citation_problems)
        checks.append(
            {
                "name": "markdown_frontmatter",
                "passed": bool(frontmatter),
                "schema_version": frontmatter.get("schema_version"),
            }
        )
        checks.append(
            {
                "name": "citation_tokens",
                "passed": not citation_problems,
                "citations": len(edges),
            }
        )
    elif target.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(
                {
                    "code": "KC_JSON_INVALID",
                    "message": f"Invalid JSON artifact: {exc}",
                }
            )
            data = {}
        checks.append({"name": "json_parse", "passed": not errors})
        if isinstance(data, dict):
            missing_json_fields = sorted(
                {"schema_version", "artifact_id", "title", "artifact_type", "status"} - set(data)
            )
            if missing_json_fields:
                errors.append(
                    {
                        "code": "KC_ARTIFACT_SCHEMA_INVALID",
                        "message": "JSON artifact is missing required fields.",
                        "details": {"missing_fields": missing_json_fields},
                    }
                )
        if schema and isinstance(data, dict) and data.get("schema_version") != schema:
            errors.append(
                {
                    "code": "KC_ARTIFACT_SCHEMA_INVALID",
                    "message": f"JSON artifact schema_version does not match --schema {schema}.",
                    "details": {"schema": schema, "actual": data.get("schema_version")},
                }
            )
        json_edges, json_problems = _validate_json_citations(
            data,
            artifact_path=repo_relative(target),
            artifact_id=data.get("artifact_id") if isinstance(data, dict) else None,
            sources_by_id={source.source_id: source for source in sources},
            ranges_by_id=range_by_id,
        )
        edges.extend(json_edges)
        errors.extend(json_problems)
        frontmatter = {
            "schema_version": schema or data.get("schema_version", "kc.json_artifact.v1")
            if isinstance(data, dict)
            else schema,
            "artifact_type": data.get("artifact_type", "glossary")
            if isinstance(data, dict)
            else "glossary",
            "status": data.get("status", "draft") if isinstance(data, dict) else "draft",
            "title": data.get("title", target.stem) if isinstance(data, dict) else target.stem,
            "domain": data.get("domain", []) if isinstance(data, dict) else [],
            "artifact_id": data.get("artifact_id") if isinstance(data, dict) else None,
        }
    else:
        errors.append(
            {
                "code": "KC_ARTIFACT_SCHEMA_INVALID",
                "message": f"Unsupported artifact file type: {target.suffix}",
            }
        )

    valid = not errors
    checks.append({"name": "artifact_valid", "passed": valid})
    return {
        "valid": valid,
        "path": repo_relative(target),
        "fingerprint": raw_fingerprint(target),
        "frontmatter": frontmatter,
        "checks": checks,
        "errors": errors,
        "citation_edges": [edge.model_dump(mode="json") for edge in edges],
        "text": text,
        "body": body,
    }


def _validate_source_refs(
    raw_refs: Any,
    source_ids: set[str],
    range_by_id: dict[str, Any],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if raw_refs is None:
        return errors
    if not isinstance(raw_refs, list):
        return [
            {
                "code": "KC_ARTIFACT_SCHEMA_INVALID",
                "message": "source_refs must be a list.",
            }
        ]
    for ref in raw_refs:
        if not isinstance(ref, dict):
            errors.append(
                {
                    "code": "KC_ARTIFACT_SCHEMA_INVALID",
                    "message": "source_refs entries must be objects.",
                }
            )
            continue
        source_id = ref.get("source_id")
        if source_id not in source_ids:
            errors.append(
                {
                    "code": "KC_CITATION_SOURCE_MISSING",
                    "message": f"source_refs source does not exist: {source_id}",
                    "source_id": source_id,
                }
            )
        for range_id in ref.get("ranges", ref.get("range_ids", [])) or []:
            range_record = range_by_id.get(range_id)
            if range_record is None:
                errors.append(
                    {
                        "code": "KC_CITATION_RANGE_MISSING",
                        "message": f"source_refs range does not exist: {range_id}",
                        "source_id": source_id,
                        "range_id": range_id,
                    }
                )
            elif source_id is not None and range_record.source_id != source_id:
                errors.append(
                    {
                        "code": "KC_CITATION_RANGE_MISSING",
                        "message": f"source_refs range does not belong to source: {range_id}",
                        "source_id": source_id,
                        "range_id": range_id,
                    }
                )
    return errors


def _validate_json_citations(
    data: Any,
    *,
    artifact_path: str,
    artifact_id: str | None,
    sources_by_id: dict[str, Any],
    ranges_by_id: dict[str, Any],
) -> tuple[list[CitationEdgeRecord], list[dict[str, Any]]]:
    edges: list[CitationEdgeRecord] = []
    problems: list[dict[str, Any]] = []
    timestamp = now()

    def visit(value: Any, pointer: str) -> None:
        if isinstance(value, dict):
            raw_citations = value.get("citations")
            if isinstance(raw_citations, list):
                for citation in raw_citations:
                    if not isinstance(citation, dict):
                        problems.append(
                            {
                                "code": "KC_CITATION_INVALID_TOKEN",
                                "message": "JSON artifact citation entries must be objects.",
                                "pointer": pointer,
                            }
                        )
                        continue
                    source_id = str(citation.get("source_id", ""))
                    range_id = citation.get("range_id")
                    range_id_str = str(range_id) if range_id is not None else ""
                    source = sources_by_id.get(source_id)
                    range_record = ranges_by_id.get(range_id_str)
                    status = "valid"
                    if source is None:
                        status = "missing_source"
                        problems.append(
                            {
                                "code": "KC_CITATION_SOURCE_MISSING",
                                "message": f"JSON citation source does not exist: {source_id}",
                                "pointer": pointer,
                                "source_id": source_id,
                            }
                        )
                    elif range_record is None:
                        status = "missing_range"
                        problems.append(
                            {
                                "code": "KC_CITATION_RANGE_MISSING",
                                "message": f"JSON citation range does not exist: {range_id}",
                                "pointer": pointer,
                                "source_id": source_id,
                                "range_id": range_id_str,
                            }
                        )
                    elif range_record.source_id != source_id:
                        status = "locator_mismatch"
                        problems.append(
                            {
                                "code": "KC_CITATION_RANGE_MISSING",
                                "message": f"JSON citation range does not belong to source: {range_id}",
                                "pointer": pointer,
                                "source_id": source_id,
                                "range_id": range_id_str,
                            }
                        )
                    elif range_record.source_fingerprint != source.fingerprint:
                        status = "stale_source"
                        problems.append(
                            {
                                "code": "KC_CITATION_STALE_SOURCE",
                                "message": f"JSON citation points to stale source fingerprint: {range_id}",
                                "pointer": pointer,
                                "source_id": source_id,
                                "range_id": range_id_str,
                            }
                        )
                    edges.append(
                        CitationEdgeRecord(
                            edge_id=new_id("cite"),
                            artifact_id=artifact_id,
                            artifact_path=artifact_path,
                            artifact_locator=ArtifactLocator(start_line=1, end_line=1),
                            citation_token=f"json:{source_id}:{range_id_str}",
                            source_id=source_id,
                            range_id=range_id_str or None,
                            source_fingerprint_at_validation=source.fingerprint if source else None,
                            validated_at=timestamp,
                            status=status,  # type: ignore[arg-type]
                            metadata={"json_pointer": pointer or "/"},
                        )
                    )
            for key, child in value.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                visit(child, f"{pointer}/{escaped}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{pointer}/{index}")

    visit(data, "")
    return edges, problems


@app.command("validate", help="Validate artifact schema, required sections, citations, and provenance.")
def validate(
    file: Annotated[Path, typer.Option("--file", help="Artifact file.")],
    schema: Annotated[str | None, typer.Option("--schema", help="Schema override.")] = None,
    allow_uncited: Annotated[
        bool, typer.Option("--allow-uncited", help="Allow [kc:uncited].")
    ] = False,
) -> None:
    def _run() -> None:
        result = validate_artifact_file(file, allow_uncited=allow_uncited, schema=schema)
        if not result["valid"]:
            errors = []
            for item in result["errors"]:
                code = str(item.get("code", "KC_ARTIFACT_SCHEMA_INVALID"))
                exit_code = (
                    EXIT_PROVENANCE if str(code).startswith("KC_CITATION") else EXIT_VALIDATION
                )
                errors.append(
                    KcError(
                        code=code,
                        message=item.get("message", "Artifact validation failed."),
                        details=item,
                        exit_code=exit_code,
                        suggested_action="fix artifact content or citations",
                    ).to_message()
                )
            exit_code = max(error["exit_code"] for error in errors) if errors else EXIT_VALIDATION
            emit(
                envelope(
                    "artifact.validate",
                    None,
                    ok=False,
                    target={"file": str(file)},
                    errors=errors,
                ),
                exit_code=exit_code,
            )
        emit_success(
            "artifact.validate",
            {k: v for k, v in result.items() if k not in {"text", "body"}},
            target={"file": str(file)},
        )

    run("artifact.validate", _run)


@app.command("diff", help="Build a structured apply plan and show artifact changes before mutation.")
def diff(
    file: Annotated[Path, typer.Option("--file", help="Artifact file.")],
    against: Annotated[str | None, typer.Option("--against", help="Comparison baseline.")] = None,
) -> None:
    def _run() -> None:
        target = ensure_under_root((Path.cwd() / file).resolve())
        if against not in {None, "registry", "HEAD"}:
            raise KcError(
                code="KC_UNSUPPORTED_FEATURE",
                message="Only registry/HEAD labels are accepted for --against in v1.",
                details={"against": against},
            )
        existing = artifact_by_path(target)
        plan, diff_text = build_artifact_plan(
            target,
            registered_fingerprint=existing.fingerprint if existing else None,
        )
        try:
            validation = validate_artifact_file(target)
            plan = _enrich_plan(plan, target=target, validation=validation, existing=existing)
        except KcError as exc:
            plan = plan.model_copy(
                update={
                    "risk_flags": sorted({*plan.risk_flags, "validation_errors"}),
                    "metadata": {
                        **plan.metadata,
                        "validation_error": exc.to_message(),
                    },
                }
            )
        emit_success(
            "artifact.diff",
            {
                "plan": plan.model_dump(mode="json"),
                "diff": diff_text,
                "diff_path": None,
                "risk_flags": plan.risk_flags,
            },
            target={"file": str(file), "against": against or "registry"},
        )

    run("artifact.diff", _run)


def _source_refs_from_edges(edges: list[CitationEdgeRecord]) -> list[SourceRef]:
    by_source: dict[str, set[str]] = {}
    for edge in edges:
        if edge.status != "valid":
            continue
        by_source.setdefault(edge.source_id, set())
        if edge.range_id:
            by_source[edge.source_id].add(edge.range_id)
    return [
        SourceRef(source_id=source_id, range_ids=sorted(range_ids))
        for source_id, range_ids in sorted(by_source.items())
    ]


def _record_from_validation(
    target: Path, validation: dict[str, Any], existing: ArtifactRecord | None
) -> ArtifactRecord:
    frontmatter = validation.get("frontmatter") or {}
    body = validation.get("body") or ""
    timestamp = now()
    artifact_id = str(
        frontmatter.get("artifact_id") or (existing.artifact_id if existing else new_id("art"))
    )
    edges = [
        CitationEdgeRecord.model_validate(edge)
        for edge in validation.get("citation_edges", [])
        if edge.get("status") == "valid"
    ]
    return ArtifactRecord(
        artifact_id=artifact_id,
        path=repo_relative(target),
        artifact_type=str(frontmatter.get("artifact_type", "knowledge_page")),  # type: ignore[arg-type]
        title=markdown_title(frontmatter, body, target.stem),
        status=str(frontmatter.get("status", "draft")),  # type: ignore[arg-type]
        domain=list(frontmatter.get("domain", []) or []),
        fingerprint=validation["fingerprint"],
        created_at=existing.created_at if existing else timestamp,
        updated_at=timestamp,
        last_validated_at=timestamp,
        validation_status="passed",
        source_refs=_source_refs_from_edges(edges),
        metadata={"compiled_by": "external_agent", "agent_tool": "kc-cli"},
    )


def _enrich_plan(
    plan: PlanRecord,
    *,
    target: Path,
    validation: dict[str, Any],
    existing: ArtifactRecord | None,
) -> PlanRecord:
    frontmatter = validation.get("frontmatter") or {}
    new_status = str(frontmatter.get("status", existing.status if existing else "draft"))
    valid_edges = [
        edge
        for edge in validation.get("citation_edges", [])
        if isinstance(edge, dict) and edge.get("status") == "valid"
    ]
    old_ref_count = (
        sum(len(ref.range_ids) for ref in existing.source_refs)
        if existing is not None
        else 0
    )
    risk_flags = set(plan.risk_flags)
    if existing and existing.status == "active":
        risk_flags.add("updates_active_artifact")
    if existing and existing.status != new_status:
        risk_flags.add("status_transition")
    if old_ref_count > len(valid_edges):
        risk_flags.add("removes_citations")
    if "[kc:uncited]" in str(validation.get("text", "")):
        risk_flags.add("adds_uncited_claim_markers")
    if any(
        isinstance(error, dict) and error.get("code") == "KC_CITATION_STALE_SOURCE"
        for error in validation.get("errors", [])
    ):
        risk_flags.add("stale_source_reference")

    operations = [
        operation.model_copy(
            update={
                "risk": "medium" if risk_flags else "low",
                "details": {
                    **operation.details,
                    "registry_change": "update" if existing else "create",
                    "citation_edges_after": len(valid_edges),
                    "artifact_status_after": new_status,
                },
            }
        )
        for operation in plan.operations
    ]
    metadata = {
        **plan.metadata,
        "direct_edit_apply": True,
        "artifact_path": repo_relative(target),
        "registry_changes": {
            "artifact": "update" if existing else "create",
            "before_fingerprint": existing.fingerprint if existing else None,
            "after_fingerprint": validation.get("fingerprint"),
        },
        "citation_edge_changes": {
            "after": len(valid_edges),
            "registered_before": old_ref_count,
        },
        "log_preview": _log_entry_text(
            markdown_title(frontmatter, validation.get("body") or "", target.stem),
            repo_relative(target),
            validation.get("fingerprint"),
            plan.plan_id,
        ),
        "changed_files": [
            repo_relative(current_paths().artifacts_jsonl),
            repo_relative(current_paths().citation_edges_jsonl),
            repo_relative(current_paths().log_path),
            repo_relative(current_paths().sqlite_path),
            repo_relative(current_paths().plans_dir / f"{plan.plan_id}.json"),
        ],
    }
    return plan.model_copy(
        update={
            "operations": operations,
            "risk_flags": sorted(risk_flags),
            "metadata": metadata,
        }
    )
def _target_from_plan_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return ensure_under_root(candidate)
    return ensure_under_root((Path.cwd() / candidate).resolve())


def _load_plan_file(plan_file: Path) -> PlanRecord:
    plan_path = ensure_under_root((Path.cwd() / plan_file).resolve())
    try:
        data = orjson.loads(plan_path.read_bytes())
    except orjson.JSONDecodeError as exc:
        raise KcError(
            code="KC_JSON_INVALID",
            message=f"Invalid plan JSON: {exc}",
            details={"path": repo_relative(plan_path)},
        ) from exc
    if not isinstance(data, dict) or data.get("schema_version") != "kc.plan.v1":
        raise KcError(
            code="KC_PLAN_PRECONDITION_FAILED",
            message="Plan file must use schema_version kc.plan.v1.",
            details={"path": repo_relative(plan_path)},
        )
    try:
        return PlanRecord.model_validate(data)
    except Exception as exc:
        raise KcError(
            code="KC_PLAN_PRECONDITION_FAILED",
            message=f"Invalid kc plan record: {exc}",
            details={"path": repo_relative(plan_path)},
        ) from exc


def _plan_operation(plan: PlanRecord) -> tuple[str, Path]:
    if plan.command != "artifact.apply":
        raise KcError(
            code="KC_PLAN_PRECONDITION_FAILED",
            message=f"Plan command is not artifact.apply: {plan.command}",
            details={"plan_id": plan.plan_id, "command": plan.command},
        )
    if len(plan.operations) != 1:
        raise KcError(
            code="KC_PLAN_PRECONDITION_FAILED",
            message="Artifact apply plans must contain exactly one operation.",
            details={"plan_id": plan.plan_id, "operations": len(plan.operations)},
        )
    operation = plan.operations[0]
    return operation.path, _target_from_plan_path(operation.path)


def _enforce_plan_preconditions(
    plan: PlanRecord,
    target: Path,
    existing: ArtifactRecord | None,
    validation: dict[str, Any],
) -> None:
    operation_path, operation_target = _plan_operation(plan)
    if operation_target != target:
        raise KcError(
            code="KC_PLAN_PRECONDITION_FAILED",
            message="Plan operation path does not match the requested artifact.",
            details={
                "plan_id": plan.plan_id,
                "operation_path": operation_path,
                "target": repo_relative(target),
            },
        )
    for condition in plan.preconditions:
        if condition.kind == "file_exists" and condition.expected == "true" and not target.exists():
            raise KcError(
                code="KC_PLAN_PRECONDITION_FAILED",
                message="Plan precondition failed: artifact file must exist.",
                details={"plan_id": plan.plan_id, "path": repo_relative(target)},
            )

    operation = plan.operations[0]
    actual_before = existing.fingerprint if existing else None
    if operation.before_fingerprint != actual_before:
        raise KcError(
            code="KC_PLAN_PRECONDITION_FAILED",
            message="Plan registry fingerprint precondition failed.",
            details={
                "plan_id": plan.plan_id,
                "expected": operation.before_fingerprint,
                "actual": actual_before,
                "path": repo_relative(target),
            },
        )
    actual_after = str(validation["fingerprint"])
    if operation.after_fingerprint != actual_after:
        raise KcError(
            code="KC_PLAN_PRECONDITION_FAILED",
            message="Plan artifact fingerprint precondition failed.",
            details={
                "plan_id": plan.plan_id,
                "expected": operation.after_fingerprint,
                "actual": actual_after,
                "path": repo_relative(target),
            },
        )


def _save_plan_file(plan: PlanRecord) -> str:
    plan_path = current_paths().plans_dir / f"{plan.plan_id}.json"
    atomic_write_text(plan_path, json_dumps(plan.model_dump(mode="json")) + "\n")
    return repo_relative(plan_path)


def _snapshot_kc_state(snapshot_dir: Path, paths: Any) -> list[dict[str, str]]:
    snapshots: list[dict[str, str]] = []
    for source in [
        paths.artifacts_jsonl,
        paths.citation_edges_jsonl,
        paths.log_path,
    ]:
        if not source.exists():
            continue
        destination = snapshot_dir / ".kc-state" / source.name
        copy_snapshot(source, destination)
        snapshots.append(
            {
                "path": repo_relative(source),
                "fingerprint": raw_fingerprint(source),
                "snapshot_path": repo_relative(destination),
            }
        )
    return snapshots


def _log_entry_text(title: str, path: str, fingerprint: str | None, plan_id: str) -> str:
    return (
        f"## {datetime.now(UTC).date().isoformat()} - {title}\n\n"
        f"- Plan: {plan_id}\n"
        f"- Artifact: {path}\n"
        f"- Fingerprint: {fingerprint}\n\n"
    )


@app.command("apply", help="Validate, lock, snapshot, register, and apply an artifact safely.")
def apply(
    file: Annotated[Path | None, typer.Option("--file", help="Artifact file.")] = None,
    plan_file: Annotated[Path | None, typer.Option("--plan", help="Plan JSON file.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Apply registry/citation changes.")] = False,
    skip_validate: Annotated[
        bool, typer.Option("--skip-validate", help="Skip validation.")
    ] = False,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Safe retry key.")
    ] = None,
) -> None:
    def _run() -> None:
        cfg = load_config()
        paths = current_paths()
        if file is None and plan_file is None:
            raise KcError(
                code="KC_ARTIFACT_NOT_FOUND",
                message="Provide --file or --plan.",
            )
        loaded_plan: PlanRecord | None = None
        if file is not None:
            target = ensure_under_root((Path.cwd() / file).resolve())
        else:
            if plan_file is None:
                raise KcError(
                    code="KC_ARTIFACT_NOT_FOUND",
                    message="Provide --file or --plan.",
                )
            loaded_plan = _load_plan_file(plan_file)
            _operation_path, target = _plan_operation(loaded_plan)
        if file is not None and plan_file is not None:
            loaded_plan = _load_plan_file(plan_file)
            _operation_path, plan_target = _plan_operation(loaded_plan)
            if plan_target != target:
                raise KcError(
                    code="KC_PLAN_PRECONDITION_FAILED",
                    message="--file does not match --plan operation path.",
                    details={
                        "file": repo_relative(target),
                        "plan_target": repo_relative(plan_target),
                    },
                )
        effective_dry_run = dry_run or not yes
        previous = get_idempotency(paths.sqlite_path, idempotency_key) if idempotency_key else None
        if previous:
            current_fingerprint = raw_fingerprint(target) if target.exists() else None
            previous_plan = previous.get("plan") if isinstance(previous.get("plan"), dict) else {}
            previous_ops = previous_plan.get("operations") if isinstance(previous_plan, dict) else []
            previous_op = previous_ops[0] if isinstance(previous_ops, list) and previous_ops else {}
            previous_after = previous_op.get("after_fingerprint") if isinstance(previous_op, dict) else None
            previous_path = previous_op.get("path") if isinstance(previous_op, dict) else None
            if previous_after != current_fingerprint or (
                previous_path and repo_relative(_target_from_plan_path(str(previous_path))) != repo_relative(target)
            ):
                raise KcError(
                    code="KC_PLAN_PRECONDITION_FAILED",
                    message="Idempotency key was already used for a different artifact state.",
                    details={
                        "key": idempotency_key,
                        "previous_path": previous_path,
                        "target": repo_relative(target),
                        "previous_fingerprint": previous_after,
                        "current_fingerprint": current_fingerprint,
                    },
                )
            previous["noop"] = True
            previous["idempotency"] = {"key": idempotency_key, "status": "replayed"}
            emit_success("artifact.apply", previous, target={"file": repo_relative(target)})
        if skip_validate and is_llm_mode() and not cfg.allow_skip_validate_in_llm:
            raise KcError(
                code="KC_APPLY_NOT_VALIDATED",
                message="--skip-validate is blocked when LLM=true.",
                details={"allow_skip_validate_in_llm": False},
            )
        validation = (
            {
                "valid": True,
                "fingerprint": raw_fingerprint(target),
                "frontmatter": {},
                "citation_edges": [],
                "text": target.read_text(encoding="utf-8-sig"),
                "body": "",
            }
            if skip_validate
            else validate_artifact_file(target)
        )
        if not validation["valid"]:
            raise KcError(
                code="KC_APPLY_NOT_VALIDATED",
                message="Artifact does not validate; run kc artifact validate for details.",
                details={"path": repo_relative(target), "errors": validation["errors"]},
            )
        existing = artifact_by_path(target)
        if loaded_plan is not None:
            _enforce_plan_preconditions(loaded_plan, target, existing, validation)
            plan = loaded_plan.model_copy(
                update={
                    "mode": "dry_run" if effective_dry_run else "apply",
                    "idempotency_key": idempotency_key or loaded_plan.idempotency_key,
                }
            )
            _discarded_plan, diff_text = build_artifact_plan(
                target,
                registered_fingerprint=existing.fingerprint if existing else None,
            )
        else:
            plan, diff_text = build_artifact_plan(
                target,
                registered_fingerprint=existing.fingerprint if existing else None,
                mode="dry_run" if effective_dry_run else "apply",
                idempotency_key=idempotency_key,
            )
        plan = _enrich_plan(plan, target=target, validation=validation, existing=existing)
        if effective_dry_run:
            emit_success(
                "artifact.apply",
                {
                    "dry_run": True,
                    "applied": False,
                    "plan": plan.model_dump(mode="json"),
                    "diff": diff_text,
                    "validation": {
                        k: v for k, v in validation.items() if k not in {"text", "body"}
                    },
                },
                target={"file": repo_relative(target)},
            )

        with FileLock(
            paths.locks_dir, path_lock_name(target), "artifact.apply", repo_relative(target)
        ):
            locked_fingerprint = raw_fingerprint(target)
            if locked_fingerprint != validation["fingerprint"]:
                raise KcError(
                    code="KC_PLAN_PRECONDITION_FAILED",
                    message="Artifact changed after validation and before lock acquisition.",
                    details={
                        "path": repo_relative(target),
                        "validated_fingerprint": validation["fingerprint"],
                        "locked_fingerprint": locked_fingerprint,
                    },
                )
            artifact = _record_from_validation(target, validation, existing)
            artifacts = [a for a in load_artifacts() if a.path != artifact.path]
            artifacts.append(artifact)
            edges = [
                CitationEdgeRecord.model_validate(edge)
                for edge in validation.get("citation_edges", [])
            ]
            for idx, edge in enumerate(edges):
                edge.artifact_id = artifact.artifact_id
                edge.edge_id = edge.edge_id or new_id("cite")
                edges[idx] = edge
            all_edges = [e for e in load_citation_edges() if e.artifact_path != artifact.path]
            all_edges.extend(edges)
            snapshot_dir = (
                paths.snapshots_dir
                / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{plan.plan_id}"
            )
            snapshot_path = snapshot_dir / Path(artifact.path).name
            copy_snapshot(target, snapshot_path)
            state_snapshots = _snapshot_kc_state(snapshot_dir, paths)
            save_artifacts(sorted(artifacts, key=lambda a: a.path))
            save_citation_edges(all_edges)
            if cfg.update_log:
                _append_log(paths.log_path, artifact, plan.plan_id)
            save_plan(paths.sqlite_path, plan)
            plan_path = _save_plan_file(plan)
            rebuild_index(
                paths.sqlite_path,
                load_sources(),
                load_ranges(),
                load_artifacts(),
                load_citation_edges(),
            )
            result = {
                "dry_run": False,
                "applied": True,
                "artifact": artifact.model_dump(mode="json"),
                "citation_edges": len(edges),
                "plan": plan.model_dump(mode="json"),
                "plan_path": plan_path,
                "snapshot": {
                    "schema_version": "kc.snapshot.v1",
                    "snapshot_id": new_id("snap"),
                    "plan_id": plan.plan_id,
                    "files": [
                        {
                            "path": artifact.path,
                            "fingerprint": validation["fingerprint"],
                            "snapshot_path": repo_relative(snapshot_path),
                        },
                        *state_snapshots,
                    ],
                },
            }
            if idempotency_key:
                save_idempotency(paths.sqlite_path, idempotency_key, plan.plan_id, result)
            emit_success("artifact.apply", result, target={"file": repo_relative(target)})

    run("artifact.apply", _run)


def _append_log(log_path: Path, artifact: ArtifactRecord, plan_id: str) -> None:
    current = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Knowledge Log\n\n"
    entry = _log_entry_text(artifact.title, artifact.path, artifact.fingerprint, plan_id)
    atomic_write_text(log_path, current.rstrip() + "\n\n" + entry)
