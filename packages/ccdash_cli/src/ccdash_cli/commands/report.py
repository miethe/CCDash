"""Reports and narrative output commands for the standalone CLI."""
from __future__ import annotations

import typer

from ccdash_cli.runtime import state as app_state
from ccdash_cli.formatters import OutputMode, get_formatter, resolve_output_mode
from ccdash_cli.runtime.client import build_client, CCDashClientError
from ccdash_cli.runtime.config import resolve_target

report_app = typer.Typer(help="Reports and narrative output.")


@report_app.command("aar")
def aar(
    feature_id: str = typer.Option(..., "--feature", help="Feature ID to generate AAR for."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the server-side query cache and fetch fresh data."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Generate an after-action report for a feature."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    params: dict = {"feature_id": feature_id}
    if no_cache:
        params["bypass_cache"] = "true"

    try:
        with build_client(target) as client:
            body = client.post("/api/v1/reports/aar", params=params)
    except CCDashClientError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    if body.get("status") == "error":
        typer.echo("Error: Could not generate after-action report.", err=True)
        raise typer.Exit(code=2)

    try:
        mode = resolve_output_mode(
            output=output,
            json_output=json_output,
            markdown_output=markdown_output,
            default=OutputMode.markdown,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(get_formatter(mode).render(body.get("data", {}), title="After-Action Report"))


@report_app.command("feature")
def feature(
    feature_id: str = typer.Argument(..., help="Feature ID to report on."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the server-side query cache and fetch fresh data."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Show a narrative forensic report for a feature."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    params: dict = {}
    if no_cache:
        params["bypass_cache"] = "true"

    try:
        with build_client(target) as client:
            body = client.get(f"/api/v1/features/{feature_id}", params=params or None)
    except CCDashClientError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    if body.get("status") == "error":
        typer.echo("Error: Could not fetch feature report.", err=True)
        raise typer.Exit(code=2)

    try:
        mode = resolve_output_mode(
            output=output,
            json_output=json_output,
            markdown_output=markdown_output,
            default=OutputMode.markdown,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(get_formatter(mode).render(body.get("data", {}), title=f"Feature Report: {feature_id}"))
