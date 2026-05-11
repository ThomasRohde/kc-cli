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

app = typer.Typer(help="Manage durable task records for external-agent workflows.")


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
        save_task(paths.sqlite_path, task)
        paths.tasks_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            paths.tasks_dir / f"{task.task_id}.json", json_dumps(task.model_dump(mode="json"))
        )
        config = load_config()
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
        if task.status != "awaiting_agent":
            raise KcError(
                code="KC_TASK_NOT_WAITING",
                message=f"Task is not awaiting agent input: {task_id}",
                details={"status": task.status},
            )
        if event != task.expected_event_name:
            raise KcError(
                code="KC_EVENT_INVALID",
                message=f"Expected event {task.expected_event_name}, got {event}",
            )
        payload = parse_input_json(input_data)
        validate_payload_schema(payload, task.expected_event_schema)
        task.events.append({"event": event, "input": payload, "received_at": _now()})
        task.status = "completed"
        task.updated_at = _now()
        save_task(paths.sqlite_path, task)
        atomic_write_text(
            paths.tasks_dir / f"{task.task_id}.json", json_dumps(task.model_dump(mode="json"))
        )
        emit_success(
            "task.resume", {"task": task.model_dump(mode="json")}, target={"task_id": task_id}
        )

    run("task.resume", _run)
