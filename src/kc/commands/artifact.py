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
from kc.models.citation import CitationEdgeRecord
from kc.output import emit, emit_success, envelope, is_llm_mode
from kc.paths import current_paths, ensure_under_root, repo_relative
from kc.provenance.citations import validate_citations
from kc.store.sqlite import get_idempotency, rebuild_index, save_idempotency, save_plan

app = typer.Typer(help="Artifact commands.")


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


@app.command("new")
def new(
    artifact_type: Annotated[str, typer.Option("--type", help="Artifact type.")] = "knowledge_page",
    path: Annotated[Path, typer.Option("--path", help="Artifact path.")] = ...,
    title: Annotated[str, typer.Option("--title", help="Artifact title.")] = ...,
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
        status = str(frontmatter.get("status", "draft"))
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


@app.command("validate")
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
            errors = [
                {
                    "code": item.get("code", "KC_ARTIFACT_SCHEMA_INVALID"),
                    "category": "validation",
                    "message": item.get("message", "Artifact validation failed."),
                    "exit_code": EXIT_PROVENANCE
                    if str(item.get("code", "")).startswith("KC_CITATION")
                    else EXIT_VALIDATION,
                    "retryable": False,
                    "suggested_action": "fix artifact content or citations",
                    "details": item,
                }
                for item in result["errors"]
            ]
            exit_code = max(error["exit_code"] for error in errors) if errors else EXIT_VALIDATION
            emit(
                envelope(
                    "artifact.validate",
                    {k: v for k, v in result.items() if k not in {"text", "body"}},
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


@app.command("diff")
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


@app.command("apply")
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
        target: Path
        if file is not None:
            target = ensure_under_root((Path.cwd() / file).resolve())
        else:
            data = orjson.loads((Path.cwd() / plan_file).read_bytes())  # type: ignore[arg-type]
            op_path = data["operations"][0]["path"]
            target = ensure_under_root((Path.cwd() / op_path).resolve())
        effective_dry_run = dry_run or not yes
        previous = get_idempotency(paths.sqlite_path, idempotency_key) if idempotency_key else None
        if previous:
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
        plan, diff_text = build_artifact_plan(
            target,
            registered_fingerprint=existing.fingerprint if existing else None,
            mode="dry_run" if effective_dry_run else "apply",
            idempotency_key=idempotency_key,
        )
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
            save_artifacts(sorted(artifacts, key=lambda a: a.path))
            save_citation_edges(all_edges)
            if cfg.update_log:
                _append_log(paths.log_path, artifact, plan.plan_id)
            save_plan(paths.sqlite_path, plan)
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
                "snapshot": {
                    "schema_version": "kc.snapshot.v1",
                    "snapshot_id": new_id("snap"),
                    "plan_id": plan.plan_id,
                    "files": [
                        {
                            "path": artifact.path,
                            "fingerprint": validation["fingerprint"],
                            "snapshot_path": repo_relative(snapshot_path),
                        }
                    ],
                },
            }
            if idempotency_key:
                save_idempotency(paths.sqlite_path, idempotency_key, plan.plan_id, result)
            emit_success("artifact.apply", result, target={"file": repo_relative(target)})

    run("artifact.apply", _run)


def _append_log(log_path: Path, artifact: ArtifactRecord, plan_id: str) -> None:
    current = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Knowledge Log\n\n"
    entry = (
        f"## {datetime.now(UTC).date().isoformat()} - {artifact.title}\n\n"
        f"- Plan: {plan_id}\n"
        f"- Artifact: {artifact.path}\n"
        f"- Fingerprint: {artifact.fingerprint}\n\n"
    )
    atomic_write_text(log_path, current.rstrip() + "\n\n" + entry)
