from __future__ import annotations

import typer

from kc.commands.common import load_artifacts, load_ranges, load_sources, run
from kc.output import emit_success
from kc.paths import current_workspace
from kc.store.sqlite import index_status


def register(app: typer.Typer) -> None:
    @app.command("status", help="Show workspace status and deterministic next commands.")
    def status() -> None:
        def _run() -> None:
            workspace = current_workspace()
            paths = workspace.paths
            initialized = paths.config_path.exists() and paths.data_dir.exists()
            sources = load_sources() if paths.sources_jsonl.exists() else []
            ranges = load_ranges() if paths.ranges_jsonl.exists() else []
            artifacts = load_artifacts() if paths.artifacts_jsonl.exists() else []
            index = index_status(paths.sqlite_path, sources, ranges) if initialized else None
            next_commands = []
            if not initialized:
                next_commands.append("kc init --yes")
            elif not sources:
                next_commands.append("kc source add <file> --domain <domain> --yes")
            elif index and index.get("stale"):
                next_commands.append("kc index build")
            else:
                next_commands.extend(["kc source search '<query>'", "kc context prepare --ask '<task>' --out .kc/context/<id>.json"])
            emit_success(
                "status",
                {
                    "initialized": initialized,
                    "workspace": {
                        "root": workspace.root.as_posix(),
                        "resolution_source": workspace.source,
                        "project_id": workspace.config.project_id,
                        "data_dir": paths.data_dir.as_posix(),
                        "state_dir": paths.state_dir.as_posix(),
                    },
                    "counts": {
                        "sources": len(sources),
                        "ranges": len(ranges),
                        "artifacts": len(artifacts),
                    },
                    "index": index,
                    "next_commands": next_commands,
                },
            )

        run("status", _run)
