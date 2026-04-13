from __future__ import annotations

from enum import Enum

import typer

from ccdash_cli.runtime import state as app_state
from ccdash_cli.formatters import OutputMode, get_formatter, resolve_output_mode
from ccdash_cli.runtime.client import CCDashClient, CCDashClientError
from ccdash_cli.runtime.config import resolve_target

session_app = typer.Typer(help="Session intelligence.")


class Concern(str, Enum):
    sentiment = "sentiment"
    churn = "churn"
    scope_drift = "scope_drift"


@session_app.command("list")
def session_list(
    feature: str | None = typer.Option(None, "--feature", help="Filter by feature ID."),
    root_session: str | None = typer.Option(None, "--root-session", help="Filter by root session ID."),
    limit: int = typer.Option(50, "--limit", help="Max results to return."),
    offset: int = typer.Option(0, "--offset", help="Pagination offset."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """List sessions with optional filters."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    params: dict = {"limit": limit, "offset": offset}
    if feature:
        params["feature_id"] = feature
    if root_session:
        params["root_session_id"] = root_session

    try:
        with CCDashClient(target.url, token=target.token) as client:
            body = client.get("/api/v1/sessions", params=params)
    except CCDashClientError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    if body.get("status") == "error":
        typer.echo("Error: Could not fetch sessions.", err=True)
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

    typer.echo(get_formatter(mode).render(data, title="Sessions"))

    if mode == OutputMode.human and meta:
        total = meta.get("total", len(data) if isinstance(data, list) else 0)
        shown = len(data) if isinstance(data, list) else 0
        start = offset + 1 if shown else 0
        end = offset + shown
        summary = f"Showing {start}-{end} of {total} sessions"
        if meta.get("has_more"):
            summary += " (more available)"
        typer.echo(summary)


@session_app.command("show")
def session_show(
    session_id: str = typer.Argument(..., help="Session ID to inspect."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Show detailed intelligence for a session."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    try:
        with CCDashClient(target.url, token=target.token) as client:
            body = client.get(f"/api/v1/sessions/{session_id}")
    except CCDashClientError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    if body.get("status") == "error":
        typer.echo(f"Error: Could not fetch session {session_id}.", err=True)
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

    typer.echo(get_formatter(mode).render(body.get("data", {}), title=f"Session {session_id}"))


@session_app.command("search")
def session_search(
    query: str = typer.Argument(..., help="Search text (min 2 characters)."),
    feature: str | None = typer.Option(None, "--feature", help="Filter by feature ID."),
    root_session: str | None = typer.Option(None, "--root-session", help="Filter by root session ID."),
    session: str | None = typer.Option(None, "--session", help="Filter by session ID."),
    limit: int = typer.Option(25, "--limit", help="Max results to return."),
    offset: int = typer.Option(0, "--offset", help="Pagination offset."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Search session transcripts."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    params: dict = {"q": query, "limit": limit, "offset": offset}
    if feature:
        params["feature_id"] = feature
    if root_session:
        params["root_session_id"] = root_session
    if session:
        params["session_id"] = session

    try:
        with CCDashClient(target.url, token=target.token) as client:
            body = client.get("/api/v1/sessions/search", params=params)
    except CCDashClientError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    if body.get("status") == "error":
        typer.echo("Error: Could not search sessions.", err=True)
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

    typer.echo(get_formatter(mode).render(data, title=f'Search: "{query}"'))

    if mode == OutputMode.human and meta:
        total = meta.get("total", len(data) if isinstance(data, list) else 0)
        shown = len(data) if isinstance(data, list) else 0
        start = offset + 1 if shown else 0
        end = offset + shown
        summary = f"Showing {start}-{end} of {total} results"
        if meta.get("has_more"):
            summary += " (more available)"
        typer.echo(summary)


@session_app.command("drilldown")
def session_drilldown(
    session_id: str = typer.Argument(..., help="Session ID to drilldown into."),
    concern: Concern = typer.Option(..., "--concern", help="Concern to drilldown on."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Drilldown on a specific concern for a session."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    try:
        with CCDashClient(target.url, token=target.token) as client:
            body = client.get(
                f"/api/v1/sessions/{session_id}/drilldown",
                params={"concern": concern.value},
            )
    except CCDashClientError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    if body.get("status") == "error":
        typer.echo(f"Error: Could not drilldown on session {session_id}.", err=True)
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

    typer.echo(
        get_formatter(mode).render(
            body.get("data", {}),
            title=f"Session {session_id} — {concern.value}",
        )
    )


@session_app.command("family")
def session_family(
    session_id: str = typer.Argument(..., help="Session ID to fetch family for."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """List all sessions sharing the same root as SESSION_ID."""
    target = resolve_target(target_flag=app_state.TARGET_FLAG)

    try:
        with CCDashClient(target.url, token=target.token) as client:
            body = client.get(f"/api/v1/sessions/{session_id}/family")
    except CCDashClientError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc

    if body.get("status") == "error":
        typer.echo(f"Error: Could not fetch family for session {session_id}.", err=True)
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
    members = data.get("members", []) if isinstance(data, dict) else data

    typer.echo(get_formatter(mode).render(members, title=f"Session Family — {session_id}"))

    if mode == OutputMode.human:
        count = data.get("session_count", len(members)) if isinstance(data, dict) else len(members)
        root = data.get("root_session_id", session_id) if isinstance(data, dict) else session_id
        typer.echo(f"{count} session(s) in family (root: {root})")
