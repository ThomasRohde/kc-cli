from __future__ import annotations

from typing import Annotated

import typer

from kc.commands.common import (
    load_artifacts,
    load_ranges,
    load_sources,
    parse_named_ints,
    run,
    stale_source_warnings,
    validate_choice,
)
from kc.config import load_config
from kc.output import emit_success, warning
from kc.paths import current_paths
from kc.search.fts import ensure_index, search_ranges

app = typer.Typer(help="Prepare grounded source context for an external agent.")
ALLOWED_GROUNDING = {"required", "optional"}


def _parse_budget(raw: str | None) -> dict[str, int]:
    return parse_named_ints(raw, option="--budget", defaults={"max_sources": 12, "max_ranges": 40})


@app.command("prepare", help="Search sources and emit evidence, policies, and next commands without answering.")
def prepare(
    ask: Annotated[str, typer.Option("--ask", help="Knowledge task or question.")],
    shape: Annotated[
        str, typer.Option("--shape", help="Output shape requested from agent.")
    ] = "knowledge_page",
    domain: Annotated[str | None, typer.Option("--domain", help="Domain filter.")] = None,
    target: Annotated[str | None, typer.Option("--target", help="Target artifact path.")] = None,
    grounding: Annotated[
        str, typer.Option("--grounding", help="Grounding policy: required or optional.")
    ] = "required",
    budget: Annotated[
        str | None, typer.Option("--budget", help="max_sources=N,max_ranges=N")
    ] = None,
) -> None:
    def _run() -> None:
        paths = current_paths()
        validate_choice(grounding, option="--grounding", supported=ALLOWED_GROUNDING)
        limits = _parse_budget(budget)
        ensure_index(paths.sqlite_path, paths.sources_jsonl, paths.ranges_jsonl)
        sources = load_sources()
        candidate_ranges = search_ranges(
            paths.sqlite_path,
            ask,
            domain=domain,
            limit=limits["max_ranges"],
            rrf_k=load_config().rrf_k,
            ranges=load_ranges(),
        )
        seen_sources: set[str] = set()
        filtered = []
        for item in candidate_ranges:
            if item["source_id"] not in seen_sources and len(seen_sources) >= limits["max_sources"]:
                continue
            seen_sources.add(item["source_id"])
            filtered.append(item)
        artifacts = load_artifacts()
        existing = [
            {
                "artifact_id": artifact.artifact_id,
                "path": artifact.path,
                "status": artifact.status,
                "validation_status": artifact.validation_status,
                "title": artifact.title,
            }
            for artifact in artifacts
            if (target and artifact.path == target)
            or (domain and domain in artifact.domain)
            or (not target and not domain)
        ]
        warnings = []
        if not filtered:
            warnings.append(
                warning(
                    "KC_NO_CONTEXT_RANGES",
                    "No source ranges matched the request; register or index sources first.",
                    {"ask": ask, "domain": domain},
                )
            )
        emit_success(
            "context.prepare",
            {
                "search_query": ask,
                "mode": "hybrid",
                "budget": limits,
                "candidate_ranges": filtered,
                "existing_artifacts": existing,
                "required_output_shape": shape,
                "grounding_policy": grounding,
                "citation_policy": {
                    "material_claims_require_citations": grounding == "required",
                    "citation_token_formats": [
                        "[kc:src_<id>:L<start>-L<end>]",
                        "[kc:src_<id>:JP:<percent-encoded-json-pointer>]",
                        "[kc:src_<id>:CSV:R<start>-R<end>]",
                    ],
                },
                "agent_instructions": [
                    "Use the returned source ranges for factual claims.",
                    "If no candidate range supports a claim, mark it [kc:todo] or leave it out.",
                    "Do not invent owner, authority, review date, or lifecycle status.",
                    "If sources conflict, report the conflict instead of silently resolving it.",
                    "kc does not answer the question; you must write the answer or artifact.",
                ],
                "validation_commands": [
                    "kc citation check --file <artifact-or-answer>",
                    "kc artifact validate --file <artifact>",
                ],
                "next_commands": [
                    f"kc artifact validate --file {target or '<artifact>'}",
                    f"kc artifact diff --file {target or '<artifact>'}",
                    f"kc artifact apply --file {target or '<artifact>'} --dry-run",
                    f"kc artifact apply --file {target or '<artifact>'} --yes",
                ],
            },
            target={"ask": ask, "shape": shape, "target": target, "mode": "hybrid", "budget": limits},
            warnings=[*warnings, *stale_source_warnings(filtered, sources)],
        )

    run("context.prepare", _run)
