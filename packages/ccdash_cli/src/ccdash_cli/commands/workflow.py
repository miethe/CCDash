"""Workflow diagnostics commands for the standalone CLI."""
from __future__ import annotations

import typer

from ccdash_cli import main as app_state
from ccdash_cli.formatters import OutputMode, get_formatter, resolve_output_mode
from ccdash_cli.runtime.client import CCDashClient, CCDashClientError
from ccdash_cli.runtime.config import resolve_target

workflow_app = typer.Typer(help="Workflow diagnostics.")


@workflow_app.command("failures")
def failures(
    feature_id: str | None = typer.Option(None, "--feature", help="Filter by feature ID."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Show workflows with the highest observed failure burden."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    params = {}
    if feature_id:
        params["feature_id"] = feature_id

    try:
        with CCDashClient(target.url, token=target.token) as client:
            body = client.get("/api/v1/workflows/failures", params=params or None)
    except CCDashClientError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    if body.get("status") == "error":
        typer.echo("Error: Could not fetch workflow diagnostics.", err=True)
        raise typer.Exit(code=2)

    try:
        mode = resolve_output_mode(
            output=output,
            json_output=json_output,
            markdown_output=markdown_output,
            default=app_state.OUTPUT_MODE,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(get_formatter(mode).render(body.get("data", {}), title="Workflow Failures"))
