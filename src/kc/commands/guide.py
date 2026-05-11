from __future__ import annotations

from typing import Annotated, Any

import typer

from kc import __version__
from kc.commands.common import run
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
            "stable_contracts": [
                "kc.result.v1 JSON envelopes",
                "KC_* error codes",
                "core JSONL schemas",
                "deterministic table and markdown human views",
            ],
        },
        "capabilities": {
            "calls_llm": False,
            "local_first": True,
            "bm25_search": True,
            "semantic_search": "bundled_model2vec_default",
            "hybrid_search": "default_rrf",
            "safe_apply": True,
            "task_wait_state": True,
        },
        "retrieval_models": {
            "bm25": {
                "provider": "sqlite_fts5",
                "score": "SQLite FTS5 bm25(); lower scores rank better and scores may be negative.",
                "purpose": "ranking_only",
            },
            "semantic": {
                "provider": "model2vec",
                "model": "potion-base-8M",
                "purpose": "ranking_only",
                "network": "never called by kc at runtime",
                "activation": "default hybrid retrieval and kc index build",
            }
        },
        "bootstrap": {
            "bootstrap_sequence": [
                "kc guide --section bootstrap",
                "kc init --yes",
                "kc source add <file> --domain <domain> --yes",
                "kc source refresh <source-id-or-path> --dry-run",
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
            "--format": {
                "values": ["json", "table", "markdown"],
                "default": "json",
                "contract": "json emits kc.result.v1; table and markdown emit deterministic human views",
            },
            "--data-dir": {"default": "knowledge"},
            "--state-dir": {"default": ".kc"},
            "--quiet": {"type": "bool"},
            "--request-id": {"type": "string"},
            "--no-input": {"type": "bool"},
        },
        "output_formats": {
            "json": {
                "contract": "machine",
                "shape": "kc.result.v1 envelope",
                "failure_result": None,
            },
            "table": {
                "contract": "human",
                "shape": "deterministic command-specific text table",
            },
            "markdown": {
                "contract": "human",
                "shape": "deterministic command-specific markdown",
            },
            "llm_mode": "LLM=true always forces json output, quiet mode, no prompts, and no ANSI.",
            "usage_errors": "Command-line usage errors are returned as kc.result.v1 envelopes with KC_USAGE_ERROR and process exit 2.",
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
            "markdown": [
                "[kc:src_<id>:L<start>-L<end>]",
                "[kc:src_<id>:JP:<percent-encoded-json-pointer>]",
                "[kc:src_<id>:CSV:R<start>-R<end>]",
            ],
            "json_artifacts": "Use structured citations: [{\"source_id\":\"src_...\",\"range_id\":\"rng_...\"}]",
            "markers": {
                "[kc:inference]": "marks explicit synthesis or inference",
                "[kc:todo]": "marks unresolved work and is valid only while artifact status is draft",
                "[kc:uncited]": "marks intentionally uncited content and fails unless --allow-uncited is used",
            },
            "rule": "[kc:uncited] fails unless explicitly allowed; [kc:todo] is draft-only.",
        },
        "workflows": {
            "add_source": [
                "kc source add docs/policy.md --domain policy --dry-run",
                "kc source add docs/policy.md --domain policy --yes",
                "kc source search 'ownership responsibilities' --domain policy",
            ],
            "refresh_source": [
                "kc source inspect docs/policy.md --ranges",
                "kc source refresh docs/policy.md --dry-run",
                "kc source refresh docs/policy.md --yes",
                "kc lint",
            ],
            "create_page": [
                "kc context prepare --ask 'Create an ownership page' --shape knowledge_page --target knowledge/wiki/ownership.md",
                "kc artifact new --type knowledge_page --path knowledge/wiki/ownership.md --title 'Ownership' --yes",
                "Edit the page with cited facts.",
                "kc artifact validate --file knowledge/wiki/ownership.md",
                "kc artifact diff --file knowledge/wiki/ownership.md",
                "kc artifact apply --file knowledge/wiki/ownership.md --dry-run",
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
            "2": "Usage error",
            "0": "Success",
            "10": "Validation error",
            "11": "Not found",
            "12": "Already exists",
            "13": "Conflict or invalid transition",
            "20": "Provenance/citation error",
            "30": "Index/build error",
            "31": "Retrieval model error",
            "40": "Optional waiting-state code when enable_wait_exit_code is explicitly enabled",
            "50": "I/O error",
            "60": "Lock/concurrency error",
            "70": "Persistence/state error",
            "80": "Unsupported feature or configuration",
            "90": "Internal error",
        },
    }
    full["errors"] = {
        "shape": {
            "code": "KC_*",
            "category": "stable category string",
            "message": "human-readable explanation",
            "exit_code": "stable numeric exit code",
            "retryable": "boolean",
            "suggested_action": "machine-friendly next action",
            "details": "structured details object",
        },
        "error_codes": full["error_codes"],
        "exit_codes": full["exit_codes"],
        "process_exit_code": "When multiple errors are present, the process exits with the maximum error exit_code in the envelope.",
    }
    full["examples"] = {
        "json_contract": "kc --format json guide --section commands",
        "table_human": "kc --format table lint",
        "markdown_human": "kc --format markdown source search 'ownership lifecycle'",
        "llm_forced_json": "LLM=true kc --format table guide",
    }
    if section:
        if section not in full:
            return {"section": section, "available_sections": sorted(full)}
        return {section: full[section]}
    return full


def _command(
    syntax: str,
    *,
    mutates: bool,
    confirmation: str,
    important_options: list[str],
    result_summary: str,
    examples: list[str],
    common_errors: list[str],
    exit_codes: list[int],
) -> dict[str, Any]:
    return {
        "command_id": "",
        "mutates": mutates,
        "confirmation": confirmation,
        "syntax": syntax,
        "important_options": important_options,
        "result_summary": result_summary,
        "examples": examples,
        "common_errors": common_errors,
        "exit_codes": exit_codes,
    }


def _commands() -> dict[str, Any]:
    commands = {
        "guide": _command(
            "kc guide [--section SECTION]",
            mutates=False,
            confirmation="none",
            important_options=["--section"],
            result_summary="CLI manifest, schemas, workflows, examples, and error taxonomy.",
            examples=["kc guide", "kc guide --section commands"],
            common_errors=["KC_UNSUPPORTED_FEATURE"],
            exit_codes=[0, 80],
        ),
        "conformance": _command(
            "kc conformance",
            mutates=False,
            confirmation="none",
            important_options=[],
            result_summary="Read-only V1 CLI manifest, renderer, error, and envelope conformance checks.",
            examples=["kc conformance", "kc --format markdown conformance"],
            common_errors=["KC_CONFORMANCE_FAILED"],
            exit_codes=[0, 10],
        ),
        "init": _command(
            "kc init --dry-run|--yes",
            mutates=True,
            confirmation="dry-run unless --yes",
            important_options=["--profile", "--dry-run", "--yes"],
            result_summary="Planned, created, and existing repository layout paths.",
            examples=["kc init --dry-run", "kc init --yes"],
            common_errors=["KC_VALIDATION_INVALID_ARGUMENT", "KC_PATH_OUTSIDE_REPO", "KC_CONFIG_INVALID"],
            exit_codes=[0, 10],
        ),
        "source.add": _command(
            "kc source add FILE --domain DOMAIN --dry-run|--yes",
            mutates=True,
            confirmation="dry-run unless --yes",
            important_options=["--domain", "--copy", "--dry-run", "--yes"],
            result_summary="Source ID, fingerprints, media type, copied path, and extracted range count.",
            examples=["kc source add docs/policy.md --domain policy --dry-run"],
            common_errors=["KC_SOURCE_ALREADY_REGISTERED", "KC_FILE_NOT_FOUND", "KC_SOURCE_UNSUPPORTED_MEDIA_TYPE"],
            exit_codes=[0, 11, 12, 80],
        ),
        "source.inspect": _command(
            "kc source inspect SOURCE_OR_PATH [--ranges]",
            mutates=False,
            confirmation="none",
            important_options=["--ranges"],
            result_summary="Registered source metadata, current fingerprint state, and optional ranges.",
            examples=["kc source inspect docs/policy.md --ranges"],
            common_errors=["KC_SOURCE_NOT_FOUND"],
            exit_codes=[0, 11],
        ),
        "source.refresh": _command(
            "kc source refresh SOURCE_OR_PATH --dry-run|--yes",
            mutates=True,
            confirmation="dry-run unless --yes",
            important_options=["--dry-run", "--yes"],
            result_summary="Fingerprint changes, replaced ranges, impacted artifacts, and index status.",
            examples=["kc source refresh docs/policy.md --dry-run"],
            common_errors=["KC_SOURCE_NOT_FOUND", "KC_FILE_NOT_FOUND", "KC_SOURCE_UNSUPPORTED_MEDIA_TYPE"],
            exit_codes=[0, 11, 80],
        ),
        "source.search": _command(
            "kc source search QUERY [--domain DOMAIN]",
            mutates=False,
            confirmation="none",
            important_options=["--domain", "--limit"],
            result_summary="Ranked source ranges with citation tokens and retrieval scores.",
            examples=["kc source search 'ownership lifecycle' --domain policy"],
            common_errors=["KC_VALIDATION_INVALID_ARGUMENT", "KC_INDEX_BUILD_FAILED", "KC_RETRIEVAL_MODEL_UNAVAILABLE"],
            exit_codes=[0, 10, 30, 31],
        ),
        "index.build": _command(
            "kc index build [--dry-run]",
            mutates=True,
            confirmation="cache rebuild; --dry-run previews",
            important_options=["--clean", "--dry-run"],
            result_summary="SQLite/BM25 rebuild status and semantic index metadata.",
            examples=["kc index build"],
            common_errors=["KC_VALIDATION_INVALID_ARGUMENT", "KC_INDEX_BUILD_FAILED", "KC_RETRIEVAL_MODEL_UNAVAILABLE"],
            exit_codes=[0, 10, 30, 31],
        ),
        "context.prepare": _command(
            "kc context prepare --ask ASK --shape SHAPE",
            mutates=False,
            confirmation="none",
            important_options=["--ask", "--shape", "--domain", "--target", "--grounding", "--budget"],
            result_summary="Grounded source context, artifact matches, citation policy, and next commands.",
            examples=["kc context prepare --ask 'Create an ownership page' --shape knowledge_page"],
            common_errors=["KC_INDEX_BUILD_FAILED", "KC_RETRIEVAL_MODEL_UNAVAILABLE"],
            exit_codes=[0, 30, 31],
        ),
        "artifact.new": _command(
            "kc artifact new --type TYPE --path PATH --title TITLE --dry-run|--yes",
            mutates=True,
            confirmation="dry-run unless --yes",
            important_options=["--path", "--title", "--type", "--domain", "--source-id", "--status", "--dry-run", "--yes"],
            result_summary="Deterministic artifact skeleton metadata and preview content on dry run.",
            examples=["kc artifact new --type knowledge_page --path knowledge/wiki/ownership.md --title Ownership --dry-run"],
            common_errors=["KC_VALIDATION_INVALID_ARGUMENT", "KC_FILE_EXISTS", "KC_PATH_OUTSIDE_REPO"],
            exit_codes=[0, 10, 12],
        ),
        "artifact.validate": _command(
            "kc artifact validate --file PATH",
            mutates=False,
            confirmation="none",
            important_options=["--file", "--schema", "--allow-uncited"],
            result_summary="Artifact validity, checks, fingerprint, and citation edges.",
            examples=["kc artifact validate --file knowledge/wiki/ownership.md"],
            common_errors=["KC_ARTIFACT_NOT_FOUND", "KC_VALIDATION_MISSING_CITATION", "KC_CITATION_RANGE_MISSING"],
            exit_codes=[0, 10, 11, 20],
        ),
        "artifact.diff": _command(
            "kc artifact diff --file PATH",
            mutates=False,
            confirmation="none",
            important_options=["--file", "--against"],
            result_summary="Structured artifact apply plan, diff text, and risk flags.",
            examples=["kc artifact diff --file knowledge/wiki/ownership.md"],
            common_errors=["KC_ARTIFACT_NOT_FOUND", "KC_UNSUPPORTED_FEATURE"],
            exit_codes=[0, 11, 80],
        ),
        "artifact.apply": _command(
            "kc artifact apply --file PATH|--plan PLAN --dry-run|--yes [--idempotency-key KEY]",
            mutates=True,
            confirmation="dry-run unless --yes",
            important_options=["--file", "--plan", "--dry-run", "--yes", "--skip-validate", "--idempotency-key"],
            result_summary="Apply plan, validation result, artifact record, citation edge count, and snapshot.",
            examples=["kc artifact apply --file knowledge/wiki/ownership.md --dry-run"],
            common_errors=["KC_FILE_NOT_FOUND", "KC_APPLY_NOT_VALIDATED", "KC_PLAN_PRECONDITION_FAILED", "KC_LOCK_HELD"],
            exit_codes=[0, 10, 11, 13, 60],
        ),
        "citation.check": _command(
            "kc citation check --file PATH|--all",
            mutates=False,
            confirmation="none",
            important_options=["--file", "--all", "--fail-on-warning"],
            result_summary="Citation edge validity and provenance problems for selected artifacts.",
            examples=["kc citation check --file knowledge/wiki/ownership.md"],
            common_errors=["KC_USAGE_ERROR", "KC_CITATION_INVALID_TOKEN", "KC_CITATION_RANGE_MISSING"],
            exit_codes=[0, 2, 20],
        ),
        "lint": _command(
            "kc lint [--checks citations,stale,orphans,duplicates,index,log|all]",
            mutates=False,
            confirmation="none",
            important_options=["--checks"],
            result_summary="Repository integrity status, enabled checks, counts, and issues.",
            examples=["kc lint", "kc --format markdown lint"],
            common_errors=["KC_VALIDATION_INVALID_ARGUMENT", "KC_SOURCE_STALE", "KC_ARTIFACT_SCHEMA_INVALID"],
            exit_codes=[0, 10, 20],
        ),
        "task.start": _command(
            "kc task start --goal GOAL",
            mutates=True,
            confirmation="task state write; no --yes required",
            important_options=["--goal", "--shape", "--domain", "--target", "--await-agent"],
            result_summary="Task record, candidate ranges, instructions, and resume command.",
            examples=["kc task start --goal 'Create ownership page' --target knowledge/wiki/ownership.md"],
            common_errors=["KC_INDEX_BUILD_FAILED"],
            exit_codes=[0, 30],
        ),
        "task.status": _command(
            "kc task status --task-id TASK_ID",
            mutates=False,
            confirmation="none",
            important_options=["--task-id"],
            result_summary="Compact task state and next commands.",
            examples=["kc task status --task-id task_01HX"],
            common_errors=["KC_TASK_NOT_FOUND"],
            exit_codes=[0, 11],
        ),
        "task.inspect": _command(
            "kc task inspect --task-id TASK_ID",
            mutates=False,
            confirmation="none",
            important_options=["--task-id"],
            result_summary="Full stored task record.",
            examples=["kc task inspect --task-id task_01HX"],
            common_errors=["KC_TASK_NOT_FOUND"],
            exit_codes=[0, 11],
        ),
        "task.resume": _command(
            "kc task resume --task-id TASK_ID --event EVENT --input JSON",
            mutates=True,
            confirmation="task state write; no --yes required",
            important_options=["--task-id", "--event", "--input"],
            result_summary="Updated task record with appended event.",
            examples=["kc task resume --task-id task_01HX --event artifact_created --input @event.json"],
            common_errors=["KC_TASK_NOT_FOUND", "KC_TASK_NOT_WAITING", "KC_EVENT_INVALID", "KC_JSON_INVALID"],
            exit_codes=[0, 10, 11, 13],
        ),
        "eval.run": _command(
            "kc eval run --pack FILE",
            mutates=False,
            confirmation="none",
            important_options=["--pack"],
            result_summary="Retrieval eval case totals, pass count, and case results.",
            examples=["kc eval run --pack knowledge/evals/basic.yaml"],
            common_errors=[
                "KC_USAGE_ERROR",
                "KC_INDEX_BUILD_FAILED",
                "KC_FILE_NOT_FOUND",
                "KC_CONFIG_INVALID",
                "KC_ARTIFACT_SCHEMA_INVALID",
            ],
            exit_codes=[0, 2, 10, 11, 30],
        ),
        "export": _command(
            "kc export --format jsonl|markdown-bundle|llms-txt [--out FILE]",
            mutates=True,
            confirmation="writes --out when provided; no --yes required",
            important_options=["--format", "--out"],
            result_summary="Export format, byte count, output path, content location, or inline content.",
            examples=["kc export --format llms-txt", "kc export --format markdown-bundle --out knowledge/exports/bundle.md"],
            common_errors=["KC_VALIDATION_INVALID_ARGUMENT", "KC_PATH_OUTSIDE_REPO"],
            exit_codes=[0, 10, 80],
        ),
        "doctor": _command(
            "kc doctor",
            mutates=False,
            confirmation="none",
            important_options=[],
            result_summary="Config, state, lock count, and semantic index health.",
            examples=["kc doctor"],
            common_errors=["KC_RETRIEVAL_MODEL_UNAVAILABLE"],
            exit_codes=[0, 31],
        ),
        "doctor.locks": _command(
            "kc doctor locks [--clear-stale --yes]",
            mutates=True,
            confirmation="dry-run unless --clear-stale --yes",
            important_options=["--clear-stale", "--yes"],
            result_summary="Lock files, metadata, clear-stale flag, and cleared files.",
            examples=["kc doctor locks", "kc doctor locks --clear-stale --yes"],
            common_errors=["KC_LOCK_HELD"],
            exit_codes=[0, 60],
        ),
    }
    for command_id, contract in commands.items():
        contract["command_id"] = command_id
    return commands


def register(app: typer.Typer) -> None:
    @app.command("guide", help="Emit the machine-readable kc playbook for agents and tooling.")
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
            emit_success("guide", build_guide(section), target={"section": section})

        run("guide", _run)
