from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from kc.atomic_write import atomic_write_text
from kc.commands.common import load_artifacts, load_ranges, run
from kc.errors import EXIT_PROVENANCE, KcError
from kc.output import emit, emit_success, envelope
from kc.paths import current_paths, repo_relative, resolve_repo_path
from kc.provenance.citations import find_range_for_token, parse_markdown_citations, validate_citations
from kc.search.fts import citation_token
from kc.store.transaction import mutation_transaction

app = typer.Typer(help="Validate kc citation tokens and source-range provenance.")


@app.command("check", help="Check citations in one artifact or all registered artifacts.")
def check(
    file: Annotated[Path | None, typer.Option("--file", help="Artifact file.")] = None,
    all: Annotated[bool, typer.Option("--all", help="Check all registered artifacts.")] = False,
    fail_on_warning: Annotated[
        bool, typer.Option("--fail-on-warning", help="Fail on warnings.")
    ] = False,
) -> None:
    def _run() -> None:
        paths = current_paths()
        files: list[Path] = []
        if file:
            files.append(resolve_repo_path(file))
        if all:
            files.extend(
                resolve_repo_path(artifact.path)
                for artifact in load_artifacts()
            )
        if not files:
            raise KcError(
                code="KC_USAGE_ERROR",
                message="Provide --file or --all.",
            )
        results = []
        problems = []
        for candidate in files:
            if not candidate.exists():
                raise KcError(
                    code="KC_ARTIFACT_NOT_FOUND",
                    message=f"Artifact not found: {repo_relative(candidate)}",
                    details={"path": repo_relative(candidate)},
                )
            text = candidate.read_text(encoding="utf-8-sig")
            edges, candidate_problems = validate_citations(
                repo_relative(candidate),
                text,
                sources_path=paths.sources_jsonl,
                ranges_path=paths.ranges_jsonl,
                citation_edges_path=paths.citation_edges_jsonl,
            )
            results.append(
                {
                    "path": repo_relative(candidate),
                    "citations": len(edges),
                    "valid": not candidate_problems,
                    "edges": [edge.model_dump(mode="json") for edge in edges],
                }
            )
            problems.extend(candidate_problems)
        result = {"valid": not problems, "files": results, "problems": problems}
        if problems:
            emit(
                envelope(
                    "citation.check",
                    None,
                    ok=False,
                    target={"file": str(file) if file else None, "all": all},
                    errors=[
                        KcError(
                            code=str(p["code"]),
                            message=str(p["message"]),
                            details=p,
                            exit_code=EXIT_PROVENANCE,
                            suggested_action="fix citation token or register source range",
                        ).to_message()
                        for p in problems
                    ],
                ),
                exit_code=EXIT_PROVENANCE,
            )
        emit_success(
            "citation.check",
            result | {"fail_on_warning": fail_on_warning},
            target={"file": str(file) if file else None, "all": all},
        )

    run("citation.check", _run)


@app.command("rewrite", help="Rewrite legacy locator citations to v2 range citations where exact ranges exist.")
def rewrite(
    file: Annotated[Path, typer.Option("--file", help="Artifact file.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Write rewritten citations.")] = False,
) -> None:
    def _run() -> None:
        target = resolve_repo_path(file)
        if not target.exists():
            raise KcError(
                code="KC_ARTIFACT_NOT_FOUND",
                message=f"Artifact not found: {repo_relative(target)}",
                details={"path": repo_relative(target)},
            )
        ranges = load_ranges()
        text = target.read_text(encoding="utf-8-sig")
        rewritten = text
        changes = []
        for parsed in parse_markdown_citations(text):
            if parsed.token_version != "v1":
                continue
            source_range = find_range_for_token(parsed, ranges)
            if source_range is None:
                changes.append(
                    {
                        "token": parsed.token,
                        "line": parsed.line,
                        "status": "unresolved",
                    }
                )
                continue
            replacement = citation_token(
                parsed.source_id,
                source_range.locator.model_dump(mode="json"),
                range_id=source_range.range_id,
            )
            rewritten = rewritten.replace(parsed.token, replacement)
            changes.append(
                {
                    "token": parsed.token,
                    "replacement": replacement,
                    "line": parsed.line,
                    "range_id": source_range.range_id,
                    "status": "rewritten",
                }
            )
        effective_dry_run = dry_run or not yes
        if not effective_dry_run and rewritten != text:
            paths = current_paths()
            with mutation_transaction(paths, "citation.rewrite", [target]) as tx:
                atomic_write_text(target, rewritten)
                tx.commit({"path": repo_relative(target), "rewritten": True})
        emit_success(
            "citation.rewrite",
            {
                "dry_run": effective_dry_run,
                "path": repo_relative(target),
                "rewritten": sum(1 for change in changes if change["status"] == "rewritten"),
                "unresolved": sum(1 for change in changes if change["status"] == "unresolved"),
                "changes": changes,
                "content_preview": rewritten if effective_dry_run else None,
            },
            target={"file": repo_relative(target)},
        )

    run("citation.rewrite", _run)


@app.command("repair", help="Report deterministic citation repair candidates without inventing evidence.")
def repair(
    file: Annotated[Path, typer.Option("--file", help="Artifact file.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview repair candidates.")] = True,
    yes: Annotated[bool, typer.Option("--yes", help="Apply exact mechanical repairs.")] = False,
) -> None:
    def _run() -> None:
        target = resolve_repo_path(file)
        if not target.exists():
            raise KcError(
                code="KC_ARTIFACT_NOT_FOUND",
                message=f"Artifact not found: {repo_relative(target)}",
                details={"path": repo_relative(target)},
            )
        ranges = load_ranges()
        text = target.read_text(encoding="utf-8-sig")
        candidates = []
        repaired = text
        for parsed in parse_markdown_citations(text):
            source_range = find_range_for_token(parsed, ranges)
            if source_range is None:
                same_source = [item for item in ranges if item.source_id == parsed.source_id]
                candidates.append(
                    {
                        "token": parsed.token,
                        "line": parsed.line,
                        "status": "unresolved",
                        "candidate_range_ids": [item.range_id for item in same_source[:5]],
                    }
                )
                continue
            if parsed.token_version == "v1":
                replacement = citation_token(
                    parsed.source_id,
                    source_range.locator.model_dump(mode="json"),
                    range_id=source_range.range_id,
                )
                repaired = repaired.replace(parsed.token, replacement)
                candidates.append(
                    {
                        "token": parsed.token,
                        "replacement": replacement,
                        "line": parsed.line,
                        "status": "mechanical_rewrite",
                    }
                )
        effective_dry_run = dry_run or not yes
        if not effective_dry_run and repaired != text:
            paths = current_paths()
            with mutation_transaction(paths, "citation.repair", [target]) as tx:
                atomic_write_text(target, repaired)
                tx.commit({"path": repo_relative(target), "repaired": True})
        emit_success(
            "citation.repair",
            {
                "dry_run": effective_dry_run,
                "path": repo_relative(target),
                "applied": not effective_dry_run,
                "candidates": candidates,
                "unresolved": sum(1 for item in candidates if item["status"] == "unresolved"),
            },
            target={"file": repo_relative(target)},
        )

    run("citation.repair", _run)
