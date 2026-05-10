from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from kc.commands.common import load_artifacts, run
from kc.errors import EXIT_PROVENANCE
from kc.output import emit, emit_success, envelope
from kc.paths import current_paths
from kc.provenance.citations import validate_citations

app = typer.Typer(help="Citation commands.")


@app.command("check")
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
            files.append(Path.cwd() / file)
        if all:
            files.extend(Path.cwd() / artifact.path for artifact in load_artifacts())
        results = []
        problems = []
        for candidate in files:
            text = candidate.read_text(encoding="utf-8-sig")
            edges, candidate_problems = validate_citations(
                candidate.relative_to(Path.cwd()).as_posix(),
                text,
                sources_path=paths.sources_jsonl,
                ranges_path=paths.ranges_jsonl,
            )
            results.append(
                {
                    "path": candidate.relative_to(Path.cwd()).as_posix(),
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
                    result,
                    ok=False,
                    errors=[
                        {
                            "code": p["code"],
                            "category": "provenance",
                            "message": p["message"],
                            "exit_code": EXIT_PROVENANCE,
                            "retryable": False,
                            "suggested_action": "fix citation token or register source range",
                            "details": p,
                        }
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
