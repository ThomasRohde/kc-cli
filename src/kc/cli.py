"""Typer CLI application for kc."""

from __future__ import annotations

from typing import Annotated

import click
import typer
from typer.core import TyperGroup

from kc.output import init_request, is_interactive, is_llm_mode, state


class FlexibleGroup(TyperGroup):
    """Allow root global options before or after the first subcommand."""

    _VALUE_OPTS = frozenset(("--format", "-f", "--data-dir", "--state-dir", "--request-id"))
    _FLAG_OPTS = frozenset(("--quiet", "-q", "--no-input", "--version", "-V"))
    _VALUE_PREFIXES = ("--format=", "--data-dir=", "--state-dir=", "--request-id=")

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
        typer.Option("--format", "-f", help="Output format: json, table, markdown."),
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

        emit_error(
            "kc",
            KcError(
                code="KC_UNSUPPORTED_FEATURE",
                message=f"Unknown output format: {format}",
                details={"requested": format, "supported": ["json", "table", "markdown"]},
            ),
        )
    state.format = (
        "json" if (is_llm_mode() or not is_interactive()) and format == "json" else format
    )
    state.quiet = quiet or is_llm_mode() or not is_interactive()


from kc.commands import artifact, citation, context, doctor, eval, index, source, task  # noqa: E402
from kc.commands import export as export_command  # noqa: E402
from kc.commands import guide as guide_command  # noqa: E402
from kc.commands import init as init_command  # noqa: E402
from kc.commands import lint as lint_command  # noqa: E402

guide_command.register(app)
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
