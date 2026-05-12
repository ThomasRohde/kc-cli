from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from kc.commands.common import (
    load_artifacts,
    load_citation_edges,
    load_ranges,
    load_source_revisions,
    load_sources,
    run,
    save_ranges,
    save_source_revisions,
    save_sources,
    stale_source_warnings,
    validate_positive_int,
)
from kc.config import load_config
from kc.errors import KcError
from kc.fingerprints import normalized_fingerprint, raw_fingerprint
from kc.ids import stable_id
from kc.models.source import Authority, SourceRecord
from kc.models.source_range import SourceRangeRecord
from kc.models.source_revision import SourceRevisionRecord
from kc.output import emit_success, warning
from kc.paths import current_paths, repo_relative, resolve_repo_path
from kc.provenance.citations import find_range_for_token, parse_markdown_citations
from kc.search.extract import extract_ranges, guess_media_type, is_text_like
from kc.search.semantic import build_semantic_index
from kc.store.sqlite import rebuild_index
from kc.store.transaction import mutation_transaction

app = typer.Typer(help="Register, inspect, index, and search local source material.")


def _optional_semantic_rebuild(paths, ranges: list[SourceRangeRecord]) -> dict | None:
    try:
        build_semantic_index(paths.sqlite_path, ranges)
    except KcError as exc:
        if exc.code != "KC_RETRIEVAL_MODEL_UNAVAILABLE":
            raise
        return warning(
            "KC_RETRIEVAL_SEMANTIC_UNAVAILABLE",
            "Semantic index was not rebuilt; SQLite FTS search remains available.",
            {"reason": exc.message},
        )
    return None


def _resolve_source(identifier: str) -> tuple[SourceRecord, Path]:
    paths = current_paths()
    sources = load_sources()
    source = next((candidate for candidate in sources if candidate.source_id == identifier), None)
    if source is None:
        maybe_uri = f"file:{repo_relative(resolve_repo_path(identifier), paths.root)}"
        source = next((candidate for candidate in sources if candidate.uri == maybe_uri), None)
    if source is None:
        raise KcError(
            code="KC_SOURCE_NOT_FOUND",
            message=f"Source not found: {identifier}",
            details={"identifier": identifier},
        )

    original = source.metadata.get("original_path")
    if not isinstance(original, str):
        raise KcError(
            code="KC_SOURCE_NOT_FOUND",
            message=f"Source does not have a local original path: {source.source_id}",
            details={"source_id": source.source_id},
        )
    return source, resolve_repo_path(original, paths.root)


def _impacted_artifacts(
    source_id: str, new_ranges: list[SourceRangeRecord]
) -> list[dict[str, str | None]]:
    impacts: list[dict[str, str | None]] = []
    for edge in load_citation_edges():
        if edge.source_id != source_id:
            continue
        parsed = parse_markdown_citations(edge.citation_token)
        if not parsed:
            impacts.append(
                {
                    "artifact_id": edge.artifact_id,
                    "artifact_path": edge.artifact_path,
                    "citation_token": edge.citation_token,
                    "old_range_id": edge.range_id,
                    "reason": "invalid_token",
                }
            )
            continue
        if find_range_for_token(parsed[0], new_ranges) is None:
            impacts.append(
                {
                    "artifact_id": edge.artifact_id,
                    "artifact_path": edge.artifact_path,
                    "citation_token": edge.citation_token,
                    "old_range_id": edge.range_id,
                    "reason": "line_range_no_longer_resolves",
                }
            )
            continue
        current = find_range_for_token(parsed[0], new_ranges)
        if edge.range_id and current is not None and edge.range_id != current.range_id:
            impacts.append(
                {
                    "artifact_id": edge.artifact_id,
                    "artifact_path": edge.artifact_path,
                    "citation_token": edge.citation_token,
                    "old_range_id": edge.range_id,
                    "reason": "range_content_changed_at_locator",
                }
            )

    return impacts


@app.command("add", help="Register a local text/Markdown source, extract citation ranges, and update indexes.")
def add(
    file: Annotated[str, typer.Argument(help="Local file path to register.")],
    domain: Annotated[list[str] | None, typer.Option("--domain", help="Domain tag.")] = None,
    copy: Annotated[bool, typer.Option("--copy", help="Copy source into knowledge/raw.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Register the source.")] = False,
) -> None:
    def _run() -> None:
        if file.startswith("http://") or file.startswith("https://"):
            raise KcError(
                code="KC_UNSUPPORTED_FEATURE",
                message="HTTP source fetching is out of scope for v1. Register exported local files instead.",
                details={"uri": file},
            )
        paths = current_paths()
        source_path = resolve_repo_path(file, paths.root)
        if not source_path.exists():
            raise KcError(
                code="KC_FILE_NOT_FOUND",
                message=f"Source file not found: {file}",
                details={"path": repo_relative(source_path)},
            )
        media_type = guess_media_type(source_path)
        if not is_text_like(source_path, media_type):
            raise KcError(
                code="KC_SOURCE_UNSUPPORTED_MEDIA_TYPE",
                message=f"Unsupported media type for v1 extraction: {media_type}",
                details={"path": repo_relative(source_path), "media_type": media_type},
            )
        rel = repo_relative(source_path)
        uri = f"file:{rel}"
        sources = load_sources()
        for existing in sources:
            if existing.uri == uri:
                raise KcError(
                    code="KC_SOURCE_ALREADY_REGISTERED",
                    message=f"Source already registered: {uri}",
                    details={"source_id": existing.source_id, "uri": uri},
                    suggested_action=f"refresh existing source with kc source refresh {existing.source_id} --dry-run",
                )
        raw_fp = raw_fingerprint(source_path)
        norm_fp = normalized_fingerprint(source_path)
        timestamp = datetime.now(UTC).isoformat()
        source_id = stable_id("src", uri)
        revision_id = stable_id("rev", source_id, raw_fp, norm_fp)
        source = SourceRecord(
            source_id=source_id,
            uri=uri,
            display_name=source_path.name,
            media_type=media_type,
            fingerprint=raw_fp,
            raw_fingerprint=raw_fp,
            normalized_fingerprint=norm_fp,
            registered_at=timestamp,
            domain=list(domain or []),
            authority=Authority(),
            metadata={"original_path": rel, "repo_relative": True},
            canonical_source_key=uri,
            current_revision_id=revision_id,
            first_registered_at=timestamp,
        )
        revision = SourceRevisionRecord(
            revision_id=revision_id,
            source_id=source.source_id,
            uri=uri,
            raw_fingerprint=raw_fp,
            normalized_fingerprint=norm_fp,
            media_type=media_type,
            extracted_at=timestamp,
            metadata={"original_path": rel},
        )
        ranges = extract_ranges(
            source_path,
            source.source_id,
            source.fingerprint,
            revision_id=revision.revision_id,
        )
        effective_dry_run = dry_run or not yes
        copied_to: str | None = None
        semantic_warning: dict | None = None
        if not effective_dry_run:
            with mutation_transaction(paths, "source.add", [source_path]) as tx:
                if copy:
                    raw_dir = paths.data_dir / "raw"
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    target = raw_dir / source_path.name
                    shutil.copy2(source_path, target)
                    copied_to = repo_relative(target)
                    source.immutability = "copied"
                    source.metadata["copied_to"] = copied_to
                save_sources([*sources, source])
                save_source_revisions([*load_source_revisions(), revision])
                save_ranges([*load_ranges(), *ranges])
                all_ranges = load_ranges()
                rebuild_index(paths.sqlite_path, load_sources(), all_ranges)
                semantic_warning = _optional_semantic_rebuild(paths, all_ranges)
                tx.commit({"source_id": source.source_id, "ranges": len(ranges)})
        warnings = [
            warning(
                "KC_AUTHORITY_UNKNOWN",
                "Source authority was not provided; artifacts based on this source should remain draft.",
                {"source_id": source.source_id},
            )
        ]
        if not ranges:
            warnings.append(
                warning(
                    "KC_SOURCE_NO_RANGES",
                    "Source registered with no extractable ranges.",
                    {"source_id": source.source_id, "path": rel},
                )
            )
        if semantic_warning is not None:
            warnings.append(semantic_warning)
        emit_success(
            "source.add",
            {
                "dry_run": effective_dry_run,
                "source_id": source.source_id,
                "uri": source.uri,
                "fingerprint": source.fingerprint,
                "normalized_fingerprint": source.normalized_fingerprint,
                "media_type": media_type,
                "ranges_extracted": len(ranges),
                "copied": bool(copied_to),
                "copied_to": copied_to,
                "authority": source.authority.model_dump(mode="json"),
            },
            warnings=warnings,
        )

    run("source.add", _run)


@app.command("inspect", help="Show source metadata, current fingerprint state, and optional extracted ranges.")
def inspect(
    identifier: Annotated[str, typer.Argument(help="Source ID or source path.")],
    ranges: Annotated[bool, typer.Option("--ranges", help="Include source ranges.")] = False,
) -> None:
    def _run() -> None:
        sources = load_sources()
        source = next((s for s in sources if s.source_id == identifier), None)
        if source is None:
            paths = current_paths()
            maybe_uri = f"file:{repo_relative(resolve_repo_path(identifier, paths.root), paths.root)}"
            source = next((s for s in sources if s.uri == maybe_uri), None)
        if source is None:
            raise KcError(
                code="KC_SOURCE_NOT_FOUND",
                message=f"Source not found: {identifier}",
                details={"identifier": identifier},
            )
        current_fingerprint = None
        stale = False
        original = source.metadata.get("original_path")
        if isinstance(original, str):
            path = resolve_repo_path(original)
            if path.exists():
                current_fingerprint = raw_fingerprint(path)
                stale = current_fingerprint != source.fingerprint
            else:
                stale = True
        result = {
            "source": source.model_dump(mode="json"),
            "current_fingerprint": current_fingerprint,
            "stale": stale,
        }
        if ranges:
            result["ranges"] = [
                r.model_dump(mode="json") for r in load_ranges() if r.source_id == source.source_id
            ]
        emit_success("source.inspect", result, target={"identifier": identifier})

    run("source.inspect", _run)


@app.command("refresh", help="Refresh a registered local source, replace its ranges, and rebuild search indexes.")
def refresh(
    identifier: Annotated[str, typer.Argument(help="Source ID or source path.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Refresh the source and ranges.")] = False,
) -> None:
    def _run() -> None:
        paths = current_paths()
        source, source_path = _resolve_source(identifier)
        if not source_path.exists():
            raise KcError(
                code="KC_FILE_NOT_FOUND",
                message=f"Source file not found: {repo_relative(source_path)}",
                details={"source_id": source.source_id, "path": repo_relative(source_path)},
            )
        media_type = guess_media_type(source_path)
        if not is_text_like(source_path, media_type):
            raise KcError(
                code="KC_SOURCE_UNSUPPORTED_MEDIA_TYPE",
                message=f"Unsupported media type for v1 extraction: {media_type}",
                details={"path": repo_relative(source_path), "media_type": media_type},
            )

        old_ranges = [item for item in load_ranges() if item.source_id == source.source_id]
        new_raw_fingerprint = raw_fingerprint(source_path)
        new_normalized_fingerprint = normalized_fingerprint(source_path)
        revision_id = stable_id(
            "rev",
            source.source_id,
            new_raw_fingerprint,
            new_normalized_fingerprint,
        )
        refreshed_source = source.model_copy(
            update={
                "display_name": source_path.name,
                "media_type": media_type,
                "fingerprint": new_raw_fingerprint,
                "raw_fingerprint": new_raw_fingerprint,
                "normalized_fingerprint": new_normalized_fingerprint,
                "status": "active",
                "metadata": {
                    **source.metadata,
                    "original_path": repo_relative(source_path),
                    "repo_relative": True,
                },
                "canonical_source_key": source.canonical_source_key or source.uri,
                "current_revision_id": revision_id,
                "first_registered_at": source.first_registered_at or source.registered_at,
                "last_refreshed_at": datetime.now(UTC).isoformat(),
            }
        )
        revision = SourceRevisionRecord(
            revision_id=revision_id,
            source_id=source.source_id,
            uri=source.uri,
            raw_fingerprint=new_raw_fingerprint,
            normalized_fingerprint=new_normalized_fingerprint,
            media_type=media_type,
            extracted_at=refreshed_source.last_refreshed_at or datetime.now(UTC).isoformat(),
            previous_revision_id=source.current_revision_id,
            metadata={"original_path": repo_relative(source_path)},
        )
        new_ranges = extract_ranges(
            source_path,
            source.source_id,
            refreshed_source.fingerprint,
            revision_id=revision.revision_id,
        )
        impacts = _impacted_artifacts(source.source_id, new_ranges)
        effective_dry_run = dry_run or not yes
        semantic_warning: dict | None = None
        if not effective_dry_run:
            with mutation_transaction(paths, "source.refresh", [source_path]) as tx:
                sources = [
                    refreshed_source if item.source_id == source.source_id else item
                    for item in load_sources()
                ]
                ranges = [
                    item for item in load_ranges() if item.source_id != source.source_id
                ] + new_ranges
                save_sources(sources)
                existing_revisions = [
                    item.model_copy(update={"status": "superseded"})
                    if item.source_id == source.source_id and item.status == "active"
                    else item
                    for item in load_source_revisions()
                ]
                save_source_revisions([*existing_revisions, revision])
                save_ranges(ranges)
                rebuild_index(paths.sqlite_path, sources, ranges, load_artifacts(), load_citation_edges())
                semantic_warning = _optional_semantic_rebuild(paths, ranges)
                tx.commit({"source_id": source.source_id, "ranges": len(new_ranges)})

        emit_success(
            "source.refresh",
            {
                "dry_run": effective_dry_run,
                "source_id": source.source_id,
                "uri": source.uri,
                "old_fingerprint": source.fingerprint,
                "new_fingerprint": refreshed_source.fingerprint,
                "old_normalized_fingerprint": source.normalized_fingerprint,
                "new_normalized_fingerprint": refreshed_source.normalized_fingerprint,
                "media_type": media_type,
                "ranges_removed": len(old_ranges),
                "ranges_extracted": len(new_ranges),
                "impacted_artifacts": impacts,
                "index_rebuilt": not effective_dry_run,
                "semantic_index_rebuilt": not effective_dry_run,
                "next_commands": [],
            },
            target={"identifier": identifier, "source_id": source.source_id},
            warnings=[semantic_warning] if semantic_warning is not None else [],
        )

    run("source.refresh", _run)


@app.command("search", help="Search source ranges with hybrid retrieval and return citation tokens.")
def search(
    query: Annotated[str, typer.Argument(help="Search query.")],
    domain: Annotated[str | None, typer.Option("--domain", help="Domain filter.")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum results; must be positive.")] = 10,
) -> None:
    def _run() -> None:
        validate_positive_int(limit, option="--limit")
        paths = current_paths()
        from kc.search.fts import ensure_index, search_ranges

        ensure_index(paths.sqlite_path, paths.sources_jsonl, paths.ranges_jsonl)
        config = load_config(paths.root)
        sources = load_sources()
        retrieval_metadata: dict[str, str | None] = {}
        results = search_ranges(
            paths.sqlite_path,
            query,
            domain=domain,
            limit=limit,
            rrf_k=config.rrf_k,
            ranges=load_ranges(),
            metadata=retrieval_metadata,
        )
        warnings = stale_source_warnings(results, sources)
        if retrieval_metadata.get("mode") == "fts_fallback":
            warnings.append(
                warning(
                    "KC_RETRIEVAL_SEMANTIC_UNAVAILABLE",
                    "Semantic ranking is unavailable; results use SQLite FTS fallback.",
                    {"reason": retrieval_metadata.get("semantic_unavailable_reason")},
                )
            )
        emit_success(
            "source.search",
            {
                "query": query,
                "mode": retrieval_metadata.get("mode") or "hybrid",
                "total": len(results),
                "results": results,
            },
            target={"query": query, "domain": domain, "limit": limit, "mode": retrieval_metadata.get("mode") or "hybrid"},
            warnings=warnings,
        )

    run("source.search", _run)
