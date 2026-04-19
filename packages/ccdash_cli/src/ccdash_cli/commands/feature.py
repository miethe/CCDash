from __future__ import annotations

from typing import List, Optional

import typer

from ccdash_cli.runtime import state as app_state
from ccdash_cli.formatters import OutputMode, get_formatter, resolve_output_mode
from ccdash_cli.runtime.client import build_client, CCDashClientError
from ccdash_cli.runtime.config import resolve_target

feature_app = typer.Typer(help="Feature investigations.")


def _expand_csv_values(values: list[str] | None) -> list[str]:
    expanded: list[str] = []
    for value in values or []:
        expanded.extend(item.strip() for item in value.split(",") if item.strip())
    return expanded


@feature_app.command("list")
def feature_list(
    status: Optional[List[str]] = typer.Option(None, "--status", help="Filter by status (repeatable or comma-separated)."),
    category: Optional[str] = typer.Option(None, "--category", help="Filter by category."),
    limit: int = typer.Option(200, "--limit", help="Maximum results to return."),
    offset: int = typer.Option(0, "--offset", help="Pagination offset."),
    q: Optional[str] = typer.Option(None, "--q", help="Keyword filter: case-insensitive substring match on feature name and ID."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """List features with optional filters."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    expanded_statuses = _expand_csv_values(status)

    params: dict = {"limit": limit, "offset": offset}
    if expanded_statuses:
        params["status"] = expanded_statuses
    if category:
        params["category"] = category
    if q:
        params["q"] = q

    try:
        with build_client(target) as client:
            body = client.get("/api/v1/features", params=params)
    except CCDashClientError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    if body.get("status") == "error":
        typer.echo("Error: Could not fetch features.", err=True)
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

    data = body.get("data", [])
    meta = body.get("meta", {})

    typer.echo(get_formatter(mode).render(data, title="Features"))

    if mode == OutputMode.human and meta:
        total = meta.get("total", len(data))
        has_more = meta.get("has_more", False)
        truncated = meta.get("truncated", False)
        end = offset + len(data) if isinstance(data, list) else offset
        start = offset + 1 if data else 0
        summary = f"Showing {start}-{end} of {total} features"
        if has_more:
            summary += " (more available)"
        typer.echo(summary)
        if truncated:
            typer.secho(
                f"Showing {limit} of {total} features. Use --limit {total} to see all.",
                dim=True,
            )


@feature_app.command("show")
def feature_show(
    feature_id: str = typer.Argument(..., help="Feature ID to inspect."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the server-side query cache and fetch fresh data."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Show full forensic detail for a feature."""
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
        typer.echo(f"Error: Could not fetch feature {feature_id}.", err=True)
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

    data = body.get("data", {})
    typer.echo(get_formatter(mode).render(data, title=f"Feature {feature_id}"))

    if mode not in (OutputMode.json, OutputMode.markdown):
        n_sessions = len(data.get("linked_sessions", []))
        typer.secho(
            f"Sessions: {n_sessions} linked"
            f" — run 'ccdash feature sessions {feature_id}' for paginated details.",
            dim=True,
        )


@feature_app.command("sessions")
def feature_sessions(
    feature_id: str = typer.Argument(..., help="Feature ID."),
    limit: int = typer.Option(50, "--limit", help="Maximum results to return."),
    offset: int = typer.Option(0, "--offset", help="Pagination offset."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the server-side query cache and fetch fresh data."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """List sessions linked to a feature."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    params: dict = {"limit": limit, "offset": offset}
    if no_cache:
        params["bypass_cache"] = "true"

    try:
        with build_client(target) as client:
            body = client.get(f"/api/v1/features/{feature_id}/sessions", params=params)
    except CCDashClientError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    if body.get("status") == "error":
        typer.echo(f"Error: Could not fetch sessions for feature {feature_id}.", err=True)
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

    data = body.get("data", {})
    sessions = data.get("sessions", []) if isinstance(data, dict) else data

    typer.echo(get_formatter(mode).render(sessions, title=f"Sessions for {feature_id}"))


@feature_app.command("documents")
def feature_documents(
    feature_id: str = typer.Argument(..., help="Feature ID."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """List documents linked to a feature."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    try:
        with build_client(target) as client:
            body = client.get(f"/api/v1/features/{feature_id}/documents")
    except CCDashClientError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    if body.get("status") == "error":
        typer.echo(f"Error: Could not fetch documents for feature {feature_id}.", err=True)
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

    data = body.get("data", {})
    documents = data.get("documents", []) if isinstance(data, dict) else data

    typer.echo(get_formatter(mode).render(documents, title=f"Documents for {feature_id}"))
