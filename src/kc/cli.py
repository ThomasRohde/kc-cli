"""Typer CLI application for kc."""

from __future__ import annotations

import sys
from typing import Annotated, Any

import click
import typer
from typer.core import TyperGroup

from kc.errors import KcError
from kc.output import emit_error, init_request, is_interactive, is_llm_mode, state


def _value_after(args: list[str], option: str) -> str | None:
    for idx, item in enumerate(args):
        if item == option and idx + 1 < len(args):
            return args[idx + 1]
        if item.startswith(f"{option}="):
            return item.split("=", 1)[1]
    return None


def _initialize_error_state(args: list[str]) -> None:
    if not state.request_id:
        init_request(_value_after(args, "--request-id"))
    requested_format = _value_after(args, "--format") or _value_after(args, "-f")
    state.format = requested_format if requested_format in {"json", "table", "markdown"} else "json"
    if is_llm_mode():
        state.format = "json"
    state.quiet = True


def _command_id_from_args(args: list[str]) -> str:
    value_opts = {"--format", "-f", "--data-dir", "--state-dir", "--request-id"}
    top_level = {
        "guide",
        "conformance",
        "init",
        "lint",
        "export",
        "source",
        "index",
        "context",
        "artifact",
        "citation",
        "task",
        "eval",
        "doctor",
    }
    tokens: list[str] = []
    index = 0
    while index < len(args):
        item = args[index]
        if item in value_opts:
            index += 2
            continue
        if any(item.startswith(f"{opt}=") for opt in value_opts):
            index += 1
            continue
        if item.startswith("-"):
            index += 1
            continue
        tokens.append(item)
        if len(tokens) == 2:
            break
        index += 1
    if not tokens or tokens[0] not in top_level:
        return "kc"
    if tokens[0] in {"source", "index", "context", "artifact", "citation", "task", "eval"} and len(tokens) > 1:
        return f"{tokens[0]}.{tokens[1]}"
    if tokens[0] == "doctor" and len(tokens) > 1:
        return f"doctor.{tokens[1]}"
    return tokens[0]


class FlexibleGroup(TyperGroup):
    """Allow root global options before or after the first subcommand."""

    _VALUE_OPTS = frozenset(("--format", "-f", "--data-dir", "--state-dir", "--request-id"))
    _FLAG_OPTS = frozenset(("--quiet", "-q", "--no-input", "--version", "-V"))
    _VALUE_PREFIXES = ("--format=", "--data-dir=", "--state-dir=", "--request-id=")

    def main(
        self,
        args: list[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        **extra: Any,
    ) -> object:
        raw_args = list(sys.argv[1:] if args is None else args)
        try:
            result = super().main(
                args=raw_args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                **extra,
            )
            if standalone_mode:
                raise SystemExit(result if isinstance(result, int) else 0)
            return result
        except click.UsageError as exc:
            if not standalone_mode:
                raise
            _initialize_error_state(raw_args)
            emit_error(
                _command_id_from_args(raw_args),
                KcError(
                    code="KC_USAGE_ERROR",
                    message=exc.format_message(),
                    details={"usage": exc.format_message()},
                ),
            )

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        cmd_idx: int | None = None
        i = 0
        while i < len(args):
            item = args[i]
            if not item.startswith("-"):
                cmd_idx = i
                break
            if item in self._VALUE_OPTS:
                i += 2
                continue
            if item.startswith(self._VALUE_PREFIXES):
                i += 1
                continue
            i += 1
        if cmd_idx is None:
            return super().parse_args(ctx, args)
        before = list(args[:cmd_idx])
        cmd_and_after = list(args[cmd_idx:])
        cmd_name = cmd_and_after[0]
        sub_cmd = self.commands.get(cmd_name) if self.commands else None
        sub_opts: set[str] = set()
        if sub_cmd:
            for param in sub_cmd.params:
                sub_opts.update(param.opts)
                sub_opts.update(getattr(param, "secondary_opts", []))
        moved: list[str] = []
        kept: list[str] = [cmd_name]
        i = 1
        end_of_opts = False
        while i < len(cmd_and_after):
            item = cmd_and_after[i]
            if item == "--":
                end_of_opts = True
                kept.append(item)
                i += 1
                continue
            if not end_of_opts and item in self._VALUE_OPTS and item not in sub_opts:
                moved.append(item)
                if i + 1 < len(cmd_and_after):
                    i += 1
                    moved.append(cmd_and_after[i])
                i += 1
                continue
            if not end_of_opts and item in self._FLAG_OPTS and item not in sub_opts:
                moved.append(item)
                i += 1
                continue
            if (
                not end_of_opts
                and item.startswith(self._VALUE_PREFIXES)
                and not any(item.startswith(f"{opt}=") for opt in sub_opts)
            ):
                moved.append(item)
                i += 1
                continue
            kept.append(item)
            i += 1
        return super().parse_args(ctx, before + moved + kept)


app = typer.Typer(
    name="kc",
    cls=FlexibleGroup,
    help=(
        "kc — deterministic knowledge compiler harness.\n\n"
        "Agents provide the intelligence. kc provides source registration, search, "
        "context preparation, citation validation, safe apply, and task state."
    ),
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        from kc import __version__

        typer.echo(f"kc {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: json, table, or markdown."),
    ] = "json",
    data_dir: Annotated[
        str, typer.Option("--data-dir", help="Knowledge data directory.")
    ] = "knowledge",
    state_dir: Annotated[str, typer.Option("--state-dir", help="kc state directory.")] = ".kc",
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Suppress stderr diagnostics.")
    ] = False,
    request_id: Annotated[
        str | None, typer.Option("--request-id", help="Trace request ID.")
    ] = None,
    no_input: Annotated[
        bool, typer.Option("--no-input", help="Fail instead of prompting.")
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    del version
    init_request(request_id)
    state.data_dir = data_dir
    state.state_dir = state_dir
    state.no_input = no_input or is_llm_mode()
    if format not in {"json", "table", "markdown"}:
        from kc.errors import KcError
        from kc.output import emit_error

        state.format = "json"
        emit_error(
            "kc",
            KcError(
                code="KC_VALIDATION_INVALID_ARGUMENT",
                message=f"Unknown output format: {format}",
                details={"requested": format, "supported": ["json", "table", "markdown"]},
            ),
        )
    state.format = "json" if is_llm_mode() else format
    state.quiet = quiet or is_llm_mode() or not is_interactive()


from kc.commands import artifact, citation, context, doctor, eval, index, source, task  # noqa: E402
from kc.commands import conformance as conformance_command  # noqa: E402
from kc.commands import export as export_command  # noqa: E402
from kc.commands import guide as guide_command  # noqa: E402
from kc.commands import init as init_command  # noqa: E402
from kc.commands import lint as lint_command  # noqa: E402

guide_command.register(app)
conformance_command.register(app)
init_command.register(app)
lint_command.register(app)
export_command.register(app)
app.add_typer(source.app, name="source")
app.add_typer(index.app, name="index")
app.add_typer(context.app, name="context")
app.add_typer(artifact.app, name="artifact")
app.add_typer(citation.app, name="citation")
app.add_typer(task.app, name="task")
app.add_typer(eval.app, name="eval")
app.add_typer(doctor.app, name="doctor")
