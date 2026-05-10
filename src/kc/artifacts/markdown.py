"""Markdown artifact helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kc.artifacts.frontmatter import parse_frontmatter
from kc.provenance.citations import has_citation_or_marker


def read_markdown_artifact(path: Path) -> tuple[dict[str, Any], str, str]:
    text = path.read_text(encoding="utf-8-sig")
    frontmatter, body = parse_frontmatter(text)
    return frontmatter, body, text


def required_section_names(body: str) -> set[str]:
    headings = set()
    for line in body.splitlines():
        if line.startswith("## "):
            headings.add(line[3:].strip().lower())
    return headings


def citation_coverage_issues(
    body: str,
    *,
    status: str,
    requires_citations: bool,
    allow_uncited: bool,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not requires_citations:
        return issues

    in_code = False
    paragraph: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        text = " ".join(line for _line_no, line in paragraph).strip()
        first_line = paragraph[0][0]
        paragraph = []
        if not text:
            return
        if text.startswith("#"):
            return
        if text.startswith("|") and text.endswith("|"):
            return
        if has_citation_or_marker(text):
            if "[kc:uncited]" in text and not allow_uncited:
                issues.append(
                    {
                        "code": "KC_VALIDATION_MISSING_CITATION",
                        "message": "[kc:uncited] is not allowed without --allow-uncited.",
                        "line": first_line,
                    }
                )
            if "[kc:todo]" in text and status != "draft":
                issues.append(
                    {
                        "code": "KC_VALIDATION_TODO_IN_ACTIVE_ARTIFACT",
                        "message": "[kc:todo] is allowed only for draft artifacts.",
                        "line": first_line,
                    }
                )
            return
        issues.append(
            {
                "code": "KC_VALIDATION_MISSING_CITATION",
                "message": "Paragraph requires at least one citation token or explicit kc marker.",
                "line": first_line,
            }
        )

    for line_no, raw_line in enumerate(body.splitlines(), start=1):
        line = raw_line.strip()
        if line.startswith("```"):
            flush()
            in_code = not in_code
            continue
        if in_code:
            continue
        if not line:
            flush()
            continue
        if line.startswith("#"):
            flush()
            continue
        paragraph.append((line_no, line))
    flush()
    return issues


def markdown_title(frontmatter: dict[str, Any], body: str, fallback: str) -> str:
    title = frontmatter.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback
