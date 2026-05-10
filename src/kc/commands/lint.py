from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from kc.commands.artifact import validate_artifact_file
from kc.commands.common import load_artifacts, load_sources, run
from kc.errors import EXIT_VALIDATION
from kc.fingerprints import raw_fingerprint
from kc.output import emit, emit_success, envelope


def register(app: typer.Typer) -> None:
    @app.command("lint")
    def lint(
        checks: Annotated[
            str,
            typer.Option("--checks", help="Comma-separated checks: citations,stale,orphans."),
        ] = "citations,stale,orphans",
    ) -> None:
        def _run() -> None:
            enabled = {part.strip() for part in checks.split(",") if part.strip()}
            issues: list[dict] = []
            sources = load_sources()
            if "stale" in enabled:
                for source in sources:
                    original = source.metadata.get("original_path")
                    if not isinstance(original, str):
                        continue
                    path = Path.cwd() / original
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
            artifacts = load_artifacts()
            for artifact in artifacts:
                artifact_path = Path.cwd() / artifact.path
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
            result = {
                "valid": not issues,
                "checks": sorted(enabled),
                "sources": len(sources),
                "artifacts": len(artifacts),
                "issues": issues,
            }
            if issues:
                emit(
                    envelope(
                        "lint",
                        result,
                        ok=False,
                        errors=[
                            {
                                "code": issue.get("code", "KC_ARTIFACT_SCHEMA_INVALID"),
                                "category": "validation",
                                "message": issue.get("message", "Lint issue."),
                                "exit_code": EXIT_VALIDATION,
                                "retryable": False,
                                "suggested_action": "fix lint issue",
                                "details": issue,
                            }
                            for issue in issues
                        ],
                    ),
                    exit_code=EXIT_VALIDATION,
                )
            emit_success("lint", result)

        run("lint", _run)
