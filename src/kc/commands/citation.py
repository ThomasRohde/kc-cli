from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from kc.commands.common import load_artifacts, run
from kc.errors import EXIT_PROVENANCE, KcError
from kc.output import emit, emit_success, envelope
from kc.paths import current_paths, ensure_under_root, repo_relative
from kc.provenance.citations import validate_citations

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
            files.append(ensure_under_root((Path.cwd() / file).resolve()))
        if all:
            files.extend(
                ensure_under_root((Path.cwd() / artifact.path).resolve())
                for artifact in load_artifacts()
            )
        if not files:
            raise KcError(
                code="KC_ARTIFACT_NOT_FOUND",
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
