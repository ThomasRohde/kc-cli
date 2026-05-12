from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import typer

from kc.atomic_write import atomic_write_text
from kc.commands.common import json_dumps, parse_input_json, run, validate_payload_schema
from kc.config import load_config
from kc.errors import KcError
from kc.ids import new_id
from kc.models.task import TaskRecord
from kc.output import emit_success
from kc.paths import current_paths
from kc.search.fts import ensure_index, search_ranges
from kc.store.sqlite import load_task, save_task
from kc.store.transaction import mutation_transaction

app = typer.Typer(help="Manage durable task records for external-agent workflows.")

STATE_EVENTS = {
    "awaiting_agent": "artifact_created",
    "awaiting_validation": "artifact_validated",
    "awaiting_apply": "artifact_applied",
}


def _event_schema(event: str | None) -> dict | None:
    if event in {"artifact_created", "artifact_validated", "artifact_apply_dry_run", "artifact_applied"}:
        return {
            "type": "object",
            "required": ["path"],
            "properties": {"path": {"type": "string"}, "valid": {"type": "boolean"}},
        }
    if event and event.startswith("blocked_"):
        return {
            "type": "object",
            "required": ["reason"],
            "properties": {"reason": {"type": "string"}, "path": {"type": "string"}},
        }
    return None


def _next_commands_for_status(task: TaskRecord) -> list[str]:
    target = task.target_artifacts[0] if task.target_artifacts else "<artifact>"
    if task.status == "awaiting_agent":
        return [f"kc task resume --task-id {task.task_id} --event artifact_created --input @event.json"]
    if task.status == "awaiting_validation":
        return [
            f"kc artifact validate --file {target}",
            f"kc task resume --task-id {task.task_id} --event artifact_validated --input @event.json",
        ]
    if task.status == "awaiting_apply":
        return [
            f"kc artifact diff --file {target}",
            f"kc artifact apply --file {target} --dry-run",
            f"kc artifact apply --file {target} --yes",
            f"kc task resume --task-id {task.task_id} --event artifact_applied --input @event.json",
        ]
    return []


def _set_expected_event(task: TaskRecord) -> None:
    task.expected_event_name = STATE_EVENTS.get(task.status)
    task.expected_event_schema = _event_schema(task.expected_event_name)
    task.next_commands = _next_commands_for_status(task)


def _now() -> str:
    return datetime.now(UTC).isoformat()


@app.command("start", help="Create a task, gather candidate ranges, and optionally enter awaiting-agent state.")
def start(
    goal: Annotated[str, typer.Option("--goal", help="Knowledge-work goal.")],
    shape: Annotated[
        str, typer.Option("--shape", help="Expected artifact/answer shape.")
    ] = "knowledge_page",
    domain: Annotated[list[str] | None, typer.Option("--domain", help="Domain tag.")] = None,
    target: Annotated[
        list[str] | None, typer.Option("--target", help="Target artifact path.")
    ] = None,
    await_agent: Annotated[bool, typer.Option("--await-agent/--no-await-agent")] = True,
) -> None:
    def _run() -> None:
        paths = current_paths()
        timestamp = _now()
        ensure_index(paths.sqlite_path, paths.sources_jsonl, paths.ranges_jsonl)
        ranges = search_ranges(
            paths.sqlite_path,
            goal,
            domain=(domain or [None])[0],
            limit=20,
        )
        task = TaskRecord(
            task_id=new_id("task"),
            goal=goal,
            status="awaiting_agent" if await_agent else "completed",
            created_at=timestamp,
            updated_at=timestamp,
            shape=shape,
            domain=list(domain or []),
            candidate_sources=sorted({item["source_id"] for item in ranges}),
            candidate_ranges=[item["range_id"] for item in ranges],
            target_artifacts=list(target or []),
            agent_instructions=[
                "Read the candidate source ranges.",
                "Create or update the target artifact yourself.",
                "Do not add material claims without kc citation tokens.",
                "Run kc artifact validate before apply.",
            ],
            next_commands=[
                f"kc artifact validate --file {target[0] if target else '<artifact>'}",
                f"kc artifact diff --file {target[0] if target else '<artifact>'}",
                f"kc artifact apply --file {target[0] if target else '<artifact>'} --dry-run",
            ],
            expected_event_name="artifact_created" if await_agent else None,
            expected_event_schema={
                "type": "object",
                "required": ["path"],
                "properties": {"path": {"type": "string"}},
            }
            if await_agent
            else None,
        )
        _set_expected_event(task)
        with mutation_transaction(paths, "task.start", [paths.tasks_dir / f"{task.task_id}.json"]) as tx:
            save_task(paths.sqlite_path, task)
            paths.tasks_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_text(
                paths.tasks_dir / f"{task.task_id}.json", json_dumps(task.model_dump(mode="json"))
            )
            tx.commit({"task_id": task.task_id})
        config = load_config(paths.root)
        exit_code = (
            config.waiting_exit_code
            if await_agent and config.enable_wait_exit_code
            else 0
        )
        emit_success(
            "task.start",
            {
                "task": task.model_dump(mode="json"),
                "candidate_ranges": ranges,
                "resume_command": (
                    f"kc task resume --task-id {task.task_id} --event artifact_created --input @event.json"
                    if await_agent
                    else None
                ),
            },
            exit_code=exit_code,
        )

    run("task.start", _run)


@app.command("status", help="Show a compact task status and next commands.")
def status(task_id: Annotated[str, typer.Option("--task-id", help="Task ID.")]) -> None:
    def _run() -> None:
        task = load_task(current_paths().sqlite_path, task_id)
        if task is None:
            raise KcError(code="KC_TASK_NOT_FOUND", message=f"Task not found: {task_id}")
        emit_success(
            "task.status",
            {
                "task_id": task.task_id,
                "status": task.status,
                "updated_at": task.updated_at,
                "next_commands": task.next_commands,
            },
            target={"task_id": task_id},
        )

    run("task.status", _run)


@app.command("next", help="Return state-specific next commands for a task.")
def next_command(task_id: Annotated[str, typer.Option("--task-id", help="Task ID.")]) -> None:
    def _run() -> None:
        task = load_task(current_paths().sqlite_path, task_id)
        if task is None:
            raise KcError(code="KC_TASK_NOT_FOUND", message=f"Task not found: {task_id}")
        _set_expected_event(task)
        emit_success(
            "task.next",
            {
                "task_id": task.task_id,
                "status": task.status,
                "expected_event_name": task.expected_event_name,
                "expected_event_schema": task.expected_event_schema,
                "next_commands": task.next_commands,
            },
            target={"task_id": task_id},
        )

    run("task.next", _run)


@app.command("inspect", help="Show the full stored task record.")
def inspect(task_id: Annotated[str, typer.Option("--task-id", help="Task ID.")]) -> None:
    def _run() -> None:
        task = load_task(current_paths().sqlite_path, task_id)
        if task is None:
            raise KcError(code="KC_TASK_NOT_FOUND", message=f"Task not found: {task_id}")
        emit_success(
            "task.inspect", {"task": task.model_dump(mode="json")}, target={"task_id": task_id}
        )

    run("task.inspect", _run)


@app.command("resume", help="Resume an awaiting task with a structured event payload.")
def resume(
    task_id: Annotated[str, typer.Option("--task-id", help="Task ID.")],
    event: Annotated[str, typer.Option("--event", help="Event name.")],
    input_data: Annotated[str, typer.Option("--input", help="Inline JSON or @file.")],
) -> None:
    def _run() -> None:
        paths = current_paths()
        task = load_task(paths.sqlite_path, task_id)
        if task is None:
            raise KcError(code="KC_TASK_NOT_FOUND", message=f"Task not found: {task_id}")
        if task.status not in {"awaiting_agent", "awaiting_validation", "awaiting_apply"}:
            raise KcError(
                code="KC_TASK_NOT_WAITING",
                message=f"Task is not awaiting agent input: {task_id}",
                details={"status": task.status},
            )
        if event != task.expected_event_name and event not in {"blocked_missing_source", "blocked_validation_failed"}:
            raise KcError(
                code="KC_EVENT_INVALID",
                message=f"Expected event {task.expected_event_name}, got {event}",
            )
        payload = parse_input_json(input_data)
        validate_payload_schema(payload, _event_schema(event) if event.startswith("blocked_") else task.expected_event_schema)
        task.events.append({"event": event, "input": payload, "received_at": _now()})
        if event == "artifact_created":
            task.status = "awaiting_validation"
        elif event in {"artifact_validated", "artifact_apply_dry_run"}:
            task.status = "awaiting_apply"
        elif event == "artifact_applied":
            task.status = "completed"
        elif event in {"blocked_missing_source", "blocked_validation_failed"}:
            task.status = "blocked"
        else:
            task.status = "completed"
        task.updated_at = _now()
        _set_expected_event(task)
        with mutation_transaction(paths, "task.resume", [paths.tasks_dir / f"{task.task_id}.json"]) as tx:
            save_task(paths.sqlite_path, task)
            atomic_write_text(
                paths.tasks_dir / f"{task.task_id}.json", json_dumps(task.model_dump(mode="json"))
            )
            tx.commit({"task_id": task.task_id, "event": event, "status": task.status})
        emit_success(
            "task.resume", {"task": task.model_dump(mode="json")}, target={"task_id": task_id}
        )

    run("task.resume", _run)
