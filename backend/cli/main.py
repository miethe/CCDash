"""Root Typer app for CCDash CLI."""
from __future__ import annotations

import typer

from backend.cli import runtime
from backend.cli.commands.artifact import artifact_app
from backend.cli.commands.feature import feature_app
from backend.cli.commands.live import live_app
from backend.cli.commands.persona import persona_app
from backend.cli.commands.report import report_app
from backend.cli.commands.session import session_app
from backend.cli.commands.status import status_app
from backend.cli.commands.system import system_app
from backend.cli.commands.workflow import workflow_app
from backend.cli.output import OutputMode


app = typer.Typer(
    help="CCDash CLI for project intelligence access.",
    no_args_is_help=True,
)


@app.callback()
def main(
    output: OutputMode = typer.Option(
        OutputMode.human,
        "--output",
        help="Default output format for commands.",
    ),
    project: str | None = typer.Option(
        None,
        "--project",
        help="Override the active project ID.",
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        envvar="CCDASH_OFFLINE",
        help="Run against local session logs with no server/worker.",
    ),
    ephemeral: bool = typer.Option(
        False,
        "--ephemeral",
        help="Use a throwaway temp cache DB (offline only).",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Force a full re-parse of session logs (offline only).",
    ),
    config: str | None = typer.Option(
        None,
        "--config",
        help="Path to an offline projects.json registry (offline only).",
    ),
) -> None:
    runtime.OUTPUT_MODE = output
    runtime.PROJECT_OVERRIDE = project.strip() if project and project.strip() else None
    runtime.OFFLINE = bool(offline)
    runtime.EPHEMERAL = bool(ephemeral)
    runtime.REFRESH = bool(refresh)
    runtime.OFFLINE_CONFIG = config.strip() if config and config.strip() else None


app.add_typer(status_app, name="status", help="Show status snapshots.")
app.add_typer(feature_app, name="feature", help="Feature forensics commands.")
app.add_typer(workflow_app, name="workflow", help="Workflow diagnostics commands.")
app.add_typer(report_app, name="report", help="Reporting commands.")
app.add_typer(artifact_app, name="artifact", help="Artifact intelligence commands.")
app.add_typer(live_app, name="live", help="Live agent metrics.")
app.add_typer(system_app, name="system", help="System-wide metrics across all projects.")
app.add_typer(session_app, name="session", help="Session intelligence commands.")
app.add_typer(persona_app, name="persona", help="Persona extraction from session logs.")
