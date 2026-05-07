"""Root Typer app for CCDash CLI."""
from __future__ import annotations

import typer

from backend.cli import runtime
from backend.cli.commands.artifact import artifact_app
from backend.cli.commands.feature import feature_app
from backend.cli.commands.report import report_app
from backend.cli.commands.status import status_app
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
) -> None:
    runtime.OUTPUT_MODE = output
    runtime.PROJECT_OVERRIDE = project.strip() if project and project.strip() else None


app.add_typer(status_app, name="status", help="Show status snapshots.")
app.add_typer(feature_app, name="feature", help="Feature forensics commands.")
app.add_typer(workflow_app, name="workflow", help="Workflow diagnostics commands.")
app.add_typer(report_app, name="report", help="Reporting commands.")
app.add_typer(artifact_app, name="artifact", help="Artifact intelligence commands.")
