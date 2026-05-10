from __future__ import annotations

from typing import Annotated, Any

import typer

from kc import __version__
from kc.commands.common import require_json_format, run
from kc.errors import ERROR_EXIT_MAP
from kc.output import SCHEMA_VERSION, emit_success


def build_guide(section: str | None = None) -> dict[str, Any]:
    full = {
        "name": "kc",
        "version": __version__,
        "description": "Deterministic local-first knowledge compiler harness for external agents.",
        "schema_version": SCHEMA_VERSION,
        "compatibility": {
            "additive_changes": "minor",
            "breaking_changes": "major",
            "stable_contracts": ["kc.result.v1", "KC_* error codes", "core JSONL schemas"],
        },
        "capabilities": {
            "calls_llm": False,
            "local_first": True,
            "bm25_search": True,
            "semantic_search": "optional_future",
            "safe_apply": True,
            "task_wait_state": True,
        },
        "bootstrap": {
            "bootstrap_sequence": [
                "kc guide --section bootstrap",
                "kc init --yes",
                "kc source add <file> --domain <domain> --yes",
                "kc index build",
                "kc context prepare --ask '<task>' --shape knowledge_page --grounding required",
                "Edit or create the requested artifact yourself; kc will not generate it.",
                "kc artifact validate --file <path>",
                "kc artifact diff --file <path>",
                "kc artifact apply --file <path> --dry-run",
                "kc artifact apply --file <path> --yes",
                "kc lint",
            ],
            "agent_rule": "The agent writes semantic content. kc validates, indexes, and applies safely.",
        },
        "global_options": {
            "--format": {"values": ["json", "table", "markdown"], "default": "json"},
            "--data-dir": {"default": "knowledge"},
            "--state-dir": {"default": ".kc"},
            "--quiet": {"type": "bool"},
            "--request-id": {"type": "string"},
            "--no-input": {"type": "bool"},
        },
        "environment": {
            "LLM=true": "forces JSON, quiet/no ANSI/no prompts, and blocks unsafe validation skips",
        },
        "commands": _commands(),
        "schemas": {
            "source": "kc.source.v1",
            "source_range": "kc.source_range.v1",
            "artifact": "kc.artifact.v1",
            "citation_edge": "kc.citation_edge.v1",
            "task": "kc.task.v1",
            "plan": "kc.plan.v1",
        },
        "citation_syntax": {
            "markdown": "[kc:src_<id>:L<start>-L<end>]",
            "markers": ["[kc:inference]", "[kc:todo]", "[kc:uncited]"],
            "rule": "[kc:uncited] fails unless explicitly allowed; [kc:todo] is draft-only.",
        },
        "workflows": {
            "add_source": [
                "kc source add docs/policy.md --domain policy --dry-run",
                "kc source add docs/policy.md --domain policy --yes",
                "kc source search 'ownership responsibilities' --domain policy",
            ],
            "create_page": [
                "kc context prepare --ask 'Create an ownership page' --shape knowledge_page --target knowledge/wiki/ownership.md",
                "kc artifact new --type knowledge_page --path knowledge/wiki/ownership.md --title 'Ownership' --yes",
                "Edit the page with cited facts.",
                "kc artifact validate --file knowledge/wiki/ownership.md",
                "kc artifact apply --file knowledge/wiki/ownership.md --yes",
            ],
        },
        "anti_patterns": [
            "Do not ask kc to summarize, answer, rewrite, classify, or judge truth.",
            "Do not invent source authority, owner, review date, or lifecycle status.",
            "Do not apply artifacts with stale or missing citations.",
            "Do not run parallel write commands against the same repo.",
        ],
        "quality_rubric": [
            "Material claims have kc citation tokens.",
            "Inferences are explicitly marked.",
            "Draft TODOs are not promoted to active artifacts.",
            "Artifacts validate before apply.",
        ],
        "concurrency": {
            "rule": "Read commands can run in parallel; write commands are serialized with .kc/locks.",
            "lock_error": "KC_LOCK_HELD",
        },
        "error_codes": {
            code: {
                "exit_code": exit_code,
                "retryable": code == "KC_LOCK_HELD",
            }
            for code, exit_code in sorted(ERROR_EXIT_MAP.items())
        },
        "exit_codes": {
            "0": "Success",
            "10": "Validation error",
            "11": "Not found",
            "12": "Already exists",
            "13": "Conflict or invalid transition",
            "20": "Provenance/citation error",
            "30": "Index/build error",
            "31": "Retrieval model error",
            "40": "Waiting for external agent/user event; not a failure",
            "50": "I/O error",
            "60": "Lock/concurrency error",
            "70": "Persistence/state error",
            "80": "Unsupported feature or configuration",
            "90": "Internal error",
        },
    }
    if section:
        if section not in full:
            return {"section": section, "available_sections": sorted(full)}
        return {section: full[section]}
    return full


def _commands() -> dict[str, Any]:
    return {
        "guide": {"mutates": False, "syntax": "kc guide [--section SECTION]"},
        "init": {"mutates": True, "syntax": "kc init --dry-run|--yes"},
        "source.add": {"mutates": True, "syntax": "kc source add FILE --domain DOMAIN --yes"},
        "source.inspect": {
            "mutates": False,
            "syntax": "kc source inspect SOURCE_OR_PATH [--ranges]",
        },
        "source.search": {"mutates": False, "syntax": "kc source search QUERY [--domain DOMAIN]"},
        "index.build": {"mutates": True, "syntax": "kc index build"},
        "context.prepare": {
            "mutates": False,
            "syntax": "kc context prepare --ask ASK --shape SHAPE",
        },
        "artifact.new": {
            "mutates": True,
            "syntax": "kc artifact new --type TYPE --path PATH --title TITLE",
        },
        "artifact.validate": {"mutates": False, "syntax": "kc artifact validate --file PATH"},
        "artifact.diff": {"mutates": False, "syntax": "kc artifact diff --file PATH"},
        "artifact.apply": {
            "mutates": True,
            "syntax": "kc artifact apply --file PATH --dry-run|--yes",
        },
        "citation.check": {"mutates": False, "syntax": "kc citation check --file PATH|--all"},
        "lint": {"mutates": False, "syntax": "kc lint"},
        "task.start": {"mutates": True, "syntax": "kc task start --goal GOAL"},
        "task.status": {"mutates": False, "syntax": "kc task status --task-id TASK_ID"},
        "task.inspect": {"mutates": False, "syntax": "kc task inspect --task-id TASK_ID"},
        "task.resume": {
            "mutates": True,
            "syntax": "kc task resume --task-id TASK_ID --event EVENT --input JSON",
        },
        "eval.run": {"mutates": False, "syntax": "kc eval run [--pack FILE]"},
        "export": {"mutates": False, "syntax": "kc export --format jsonl|markdown-bundle|llms-txt"},
        "doctor": {"mutates": False, "syntax": "kc doctor"},
        "doctor.locks": {"mutates": True, "syntax": "kc doctor locks [--clear-stale --yes]"},
    }


def register(app: typer.Typer) -> None:
    @app.command("guide")
    def guide(
        section: Annotated[
            str | None,
            typer.Option(
                "--section",
                help="Return a specific guide section.",
            ),
        ] = None,
    ) -> None:
        def _run() -> None:
            require_json_format("guide")
            emit_success("guide", build_guide(section), target={"section": section})

        run("guide", _run)
