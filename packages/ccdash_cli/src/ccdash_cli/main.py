"""Root Typer app for standalone CCDash CLI."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as pkg_version

import typer

from ccdash_cli.commands.doctor import doctor_app
from ccdash_cli.commands.feature import feature_app
from ccdash_cli.commands.report import report_app
from ccdash_cli.commands.session import session_app
from ccdash_cli.commands.status import status_app
from ccdash_cli.commands.target import target_app
from ccdash_cli.commands.workflow import workflow_app
from ccdash_cli.formatters import OutputMode
from ccdash_cli.runtime import state as app_state
from ccdash_cli.runtime.state import resolve_timeout

app = typer.Typer(
    help="CCDash CLI — project intelligence from any terminal.",
    no_args_is_help=True,
)

app.add_typer(target_app, name="target")
app.add_typer(doctor_app, name="doctor")
app.add_typer(status_app, name="status")
app.add_typer(workflow_app, name="workflow")
app.add_typer(feature_app, name="feature")
app.add_typer(report_app, name="report")
app.add_typer(session_app, name="session")


def _cli_version() -> str:
    try:
        return pkg_version("ccdash-cli")
    except PackageNotFoundError:
        return "0.1.0-dev"


def _print_version_and_exit(value: bool) -> None:
    if not value:
        return
    typer.echo(f"ccdash-cli {_cli_version()}")
    raise typer.Exit()


@app.callback()
def _global_options(
    target: str | None = typer.Option(None, "--target", help="Named target from config."),
    output: OutputMode | None = typer.Option(None, "--output", help="Default output format."),
    timeout: float | None = typer.Option(
        None,
        "--timeout",
        help="HTTP request timeout in seconds (overrides CCDASH_TIMEOUT env var).",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_print_version_and_exit,
        is_eager=True,
        help="Show CLI version and exit.",
    ),
) -> None:
    """Global options applied to all sub-commands."""
    _ = version
    if target is not None:
        app_state.TARGET_FLAG = target
    if output is not None:
        app_state.OUTPUT_MODE = output
    resolved_secs, resolved_src = resolve_timeout(timeout)
    app_state.TIMEOUT_SECONDS = resolved_secs
    app_state.TIMEOUT_SOURCE = resolved_src


@app.command()
def version() -> None:
    """Show CLI version."""
    typer.echo(f"ccdash-cli {_cli_version()}")
