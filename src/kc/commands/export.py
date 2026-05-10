from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from kc.atomic_write import atomic_write_text
from kc.commands.common import load_artifacts, load_citation_edges, load_ranges, load_sources, run
from kc.errors import KcError
from kc.output import emit_success


def register(app: typer.Typer) -> None:
    @app.command("export", help="Export registered knowledge as JSON, Markdown bundle, or llms.txt.")
    def export_command(
        export_format: Annotated[
            str,
            typer.Option("--format", help="jsonl, markdown-bundle, or llms-txt."),
        ] = "jsonl",
        out: Annotated[Path | None, typer.Option("--out", help="Optional output file.")] = None,
    ) -> None:
        def _run() -> None:
            if export_format == "jsonl":
                content = _jsonl_export()
            elif export_format == "markdown-bundle":
                content = _markdown_bundle()
            elif export_format == "llms-txt":
                content = _llms_txt()
            else:
                raise KcError(
                    code="KC_UNSUPPORTED_FEATURE",
                    message=f"Unsupported export format: {export_format}",
                    details={"supported": ["jsonl", "markdown-bundle", "llms-txt"]},
                )
            if out:
                atomic_write_text(Path.cwd() / out, content)
            emit_success(
                "export",
                {
                    "format": export_format,
                    "bytes": len(content.encode("utf-8")),
                    "out": str(out) if out else None,
                    "content": None if out else content,
                },
            )

        run("export", _run)


def _jsonl_export() -> str:
    import orjson

    records = {
        "sources": [s.model_dump(mode="json") for s in load_sources()],
        "source_ranges": [r.model_dump(mode="json") for r in load_ranges()],
        "artifacts": [a.model_dump(mode="json") for a in load_artifacts()],
        "citation_edges": [c.model_dump(mode="json") for c in load_citation_edges()],
    }
    return orjson.dumps(records, option=orjson.OPT_INDENT_2).decode() + "\n"


def _markdown_bundle() -> str:
    parts = ["# kc Markdown Bundle\n"]
    for artifact in load_artifacts():
        path = Path.cwd() / artifact.path
        if path.exists() and path.suffix.lower() in {".md", ".markdown"}:
            parts.append(f"\n<!-- artifact: {artifact.path} -->\n")
            parts.append(path.read_text(encoding="utf-8-sig"))
            parts.append("\n")
    return "\n".join(parts)


def _llms_txt() -> str:
    lines = ["# kc knowledge base", ""]
    for artifact in load_artifacts():
        lines.append(f"- {artifact.title}: {artifact.path}")
    return "\n".join(lines) + "\n"
