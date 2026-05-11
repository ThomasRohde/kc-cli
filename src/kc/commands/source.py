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
    load_sources,
    run,
    save_ranges,
    save_sources,
)
from kc.config import load_config
from kc.errors import KcError
from kc.fingerprints import normalized_fingerprint, raw_fingerprint
from kc.ids import stable_id
from kc.models.source import Authority, SourceRecord
from kc.models.source_range import SourceRangeRecord
from kc.output import emit_success, warning
from kc.paths import current_paths, ensure_under_root, repo_relative
from kc.provenance.citations import find_range_for_token, parse_markdown_citations
from kc.search.extract import extract_ranges, guess_media_type, is_text_like
from kc.search.semantic import build_semantic_index, semantic_index_status
from kc.store.sqlite import rebuild_index

app = typer.Typer(help="Register, inspect, index, and search local source material.")


def _resolve_source(identifier: str) -> tuple[SourceRecord, Path]:
    sources = load_sources()
    source = next((candidate for candidate in sources if candidate.source_id == identifier), None)
    if source is None:
        maybe_uri = f"file:{repo_relative((Path.cwd() / identifier).resolve())}"
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
    return source, ensure_under_root((Path.cwd() / original).resolve())


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
        source_path = ensure_under_root((Path.cwd() / file).resolve())
        if not source_path.exists():
            raise KcError(
                code="KC_FILE_NOT_FOUND",
                message=f"Source file not found: {file}",
                details={"path": file},
            )
        media_type = guess_media_type(source_path)
        if not is_text_like(source_path, media_type):
            raise KcError(
                code="KC_SOURCE_UNSUPPORTED_MEDIA_TYPE",
                message=f"Unsupported media type for v1 extraction: {media_type}",
                details={"path": file, "media_type": media_type},
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
                )
        raw_fp = raw_fingerprint(source_path)
        norm_fp = normalized_fingerprint(source_path)
        timestamp = datetime.now(UTC).isoformat()
        source = SourceRecord(
            source_id=stable_id("src", uri, raw_fp, norm_fp),
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
        )
        ranges = extract_ranges(source_path, source.source_id, source.fingerprint)
        effective_dry_run = dry_run or not yes
        copied_to: str | None = None
        if not effective_dry_run:
            if copy:
                raw_dir = paths.data_dir / "raw"
                raw_dir.mkdir(parents=True, exist_ok=True)
                target = raw_dir / source_path.name
                shutil.copy2(source_path, target)
                copied_to = repo_relative(target)
                source.immutability = "copied"
                source.metadata["copied_to"] = copied_to
            save_sources([*sources, source])
            save_ranges([*load_ranges(), *ranges])
            all_ranges = load_ranges()
            rebuild_index(paths.sqlite_path, load_sources(), all_ranges)
            if load_config().semantic_enabled:
                build_semantic_index(paths.sqlite_path, all_ranges)
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
            warnings=[
                warning(
                    "KC_AUTHORITY_UNKNOWN",
                    "Source authority was not provided; artifacts based on this source should remain draft.",
                    {"source_id": source.source_id},
                )
            ],
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
            maybe_uri = f"file:{repo_relative((Path.cwd() / identifier).resolve())}"
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
            path = Path.cwd() / original
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


@app.command("refresh", help="Refresh a registered local source, replace its ranges, and rebuild BM25 indexes.")
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
            }
        )
        new_ranges = extract_ranges(source_path, source.source_id, refreshed_source.fingerprint)
        impacts = _impacted_artifacts(source.source_id, new_ranges)
        effective_dry_run = dry_run or not yes
        semantic_before = semantic_index_status(paths.sqlite_path, load_ranges())
        semantic_index_stale = bool(
            semantic_before.get("index_metadata") or semantic_before.get("vector_count")
        )

        if not effective_dry_run:
            sources = [
                refreshed_source if item.source_id == source.source_id else item
                for item in load_sources()
            ]
            ranges = [
                item for item in load_ranges() if item.source_id != source.source_id
            ] + new_ranges
            save_sources(sources)
            save_ranges(ranges)
            rebuild_index(paths.sqlite_path, sources, ranges, load_artifacts(), load_citation_edges())

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
                "semantic_index_stale": semantic_index_stale,
                "next_commands": ["kc index build --semantic"] if semantic_index_stale else [],
            },
            target={"identifier": identifier, "source_id": source.source_id},
        )

    run("source.refresh", _run)


@app.command("search", help="Search source ranges with BM25, semantic, or hybrid retrieval and return citation tokens.")
def search(
    query: Annotated[str, typer.Argument(help="Search query.")],
    domain: Annotated[str | None, typer.Option("--domain", help="Domain filter.")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum results.")] = 10,
    mode: Annotated[str, typer.Option("--mode", help="bm25, semantic, or hybrid.")] = "bm25",
) -> None:
    def _run() -> None:
        if mode not in {"bm25", "semantic", "hybrid"}:
            raise KcError(
                code="KC_RETRIEVAL_MODEL_UNAVAILABLE",
                message=f"Unsupported retrieval mode: {mode}",
                details={"mode": mode},
            )
        paths = current_paths()
        from kc.search.fts import ensure_index, search_ranges

        ensure_index(paths.sqlite_path, paths.sources_jsonl, paths.ranges_jsonl)
        config = load_config()
        results = search_ranges(
            paths.sqlite_path,
            query,
            domain=domain,
            limit=limit,
            mode=mode,
            rrf_k=config.rrf_k,
            ranges=load_ranges(),
        )
        emit_success(
            "source.search",
            {"query": query, "mode": mode, "total": len(results), "results": results},
            target={"query": query, "domain": domain},
        )

    run("source.search", _run)
