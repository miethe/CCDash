"""Project status commands for the standalone CLI."""
from __future__ import annotations

import typer

from ccdash_cli.runtime import state as app_state
from ccdash_cli.formatters import OutputMode, get_formatter, resolve_output_mode
from ccdash_cli.runtime.client import build_client, CCDashClientError
from ccdash_cli.runtime.config import resolve_target

status_app = typer.Typer(help="Status queries.")


@status_app.command("project")
def project(
    project_id: str | None = typer.Option(None, "--project", help="Project ID override."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the server-side query cache and fetch fresh data."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Show a project status summary."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    params: dict = {}
    # Use project from command flag, then from target config
    effective_project = project_id or target.project
    if effective_project:
        params["project_id"] = effective_project
    if no_cache:
        params["bypass_cache"] = "true"

    try:
        with build_client(target) as client:
            body = client.get("/api/v1/project/status", params=params or None)
    except CCDashClientError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    # Check envelope status
    if body.get("status") == "error":
        typer.echo("Error: Could not resolve project status.", err=True)
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

    typer.echo(get_formatter(mode).render(body.get("data", {}), title="Project Status"))
