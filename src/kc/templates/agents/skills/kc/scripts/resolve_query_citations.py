#!/usr/bin/env python3
# kc-managed-agent-skill:v1
"""Resolve kc source search results to original source URLs.

Reads a kc JSON result from a file or stdin and prints compact JSON records
with source ids, line ranges, local snapshot paths, and original URLs parsed
from kc snapshot metadata headers.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HEADER_KEYS = {
    "source_url": re.compile(r"^\s*Source URL:\s*(.+?)\s*$"),
    "markdown_url": re.compile(r"^\s*Markdown URL:\s*(.+?)\s*$"),
    "publisher": re.compile(r"^\s*Publisher:\s*(.+?)\s*$"),
}


def read_json(path: str) -> dict[str, Any]:
    if path == "-":
        import sys

        return json.load(sys.stdin)
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_sources(repo_root: Path) -> dict[str, dict[str, Any]]:
    sources_path = repo_root / "knowledge" / "sources.jsonl"
    sources: dict[str, dict[str, Any]] = {}
    with sources_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            sources[record["source_id"]] = record
    return sources


def source_path(repo_root: Path, source: dict[str, Any]) -> Path | None:
    metadata = source.get("metadata") or {}
    original_path = metadata.get("original_path")
    if original_path:
        return (repo_root / original_path).resolve()

    uri = source.get("uri", "")
    if uri.startswith("file:"):
        return (repo_root / uri.removeprefix("file:")).resolve()
    return None


def parse_header(path: Path | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path or not path.exists():
        return values

    with path.open(encoding="utf-8-sig") as handle:
        for index, line in enumerate(handle):
            if index >= 60:
                break
            for key, pattern in HEADER_KEYS.items():
                match = pattern.match(line)
                if match:
                    values[key] = match.group(1)
    return values


def results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") or {}
    items = result.get("results")
    if isinstance(items, list):
        return items
    if isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_result", help="kc JSON result path, or '-' for stdin")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root containing knowledge/sources.jsonl",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    payload = read_json(args.json_result)
    sources = load_sources(repo_root)

    resolved = []
    for item in results(payload):
        item_source_id = item.get("source_id")
        source = sources.get(item_source_id, {}) if isinstance(item_source_id, str) else {}
        path = source_path(repo_root, source)
        header = parse_header(path)
        locator = item.get("locator") or {}
        start = locator.get("start_line")
        end = locator.get("end_line")
        line_range = f"L{start}-L{end}" if start and end else None
        original_url = header.get("source_url") or source.get("uri")

        resolved.append(
            {
                "display_name": item.get("display_name") or source.get("display_name"),
                "source_id": item_source_id,
                "line_range": line_range,
                "original_url": original_url,
                "markdown_url": header.get("markdown_url"),
                "publisher": header.get("publisher"),
                "local_snapshot": str(path.relative_to(repo_root)) if path else None,
                "citation_token": item.get("citation_token"),
                "excerpt": item.get("excerpt"),
            }
        )

    print(json.dumps(resolved, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
