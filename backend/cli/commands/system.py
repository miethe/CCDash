"""System-wide metrics commands (system-wide-metrics-v1)."""
from __future__ import annotations

import json

import typer

from backend.application.services.agent_queries.system_metrics import SystemMetricsQueryService
from backend.cli import runtime


system_app = typer.Typer(help="System-wide metrics across all projects.")
_system_service = SystemMetricsQueryService()


@system_app.command("active-count")
def active_count(
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON response."),
) -> None:
    """Show the aggregated live-agent count across all known projects.

    Queries every registered project in parallel and displays a table with one
    row per project.  Stale projects (no session activity within
    CCDASH_SYSTEM_METRICS_STALE_HORIZON_SECONDS, default 3600 s) are flagged.

    Projects with no sessions show ``is_stale=?`` (indeterminate).

    Exits with code 0 on success, 1 on unexpected error.

    Options:
        --json   Emit JSON matching the REST /api/agent/system/active-count response.
    """

    async def _query():
        async def _invoke(context, ports):
            return await _system_service.get_system_active_count(context, ports)

        return await runtime.execute_query(_invoke)

    try:
        result = runtime.run_async(_query())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(
            json.dumps(
                result.model_dump(mode="json"),
                indent=2,
                default=str,
            )
        )
        return

    # Human-readable table
    col_name = "Project"
    col_count = "Active"
    col_stale = "Stale"
    col_synced = "Last Synced"

    # Column widths
    name_w = max(len(col_name), max((len(p.project_name) for p in result.per_project), default=0))
    count_w = max(len(col_count), 6)
    stale_w = max(len(col_stale), 5)
    synced_w = max(len(col_synced), 19)

    sep = f"+-{'-' * name_w}-+-{'-' * count_w}-+-{'-' * stale_w}-+-{'-' * synced_w}-+"
    header = (
        f"| {col_name:<{name_w}} | {col_count:>{count_w}} "
        f"| {col_stale:^{stale_w}} | {col_synced:<{synced_w}} |"
    )

    typer.echo(sep)
    typer.echo(header)
    typer.echo(sep)

    for p in result.per_project:
        count_str = str(p.count) if p.count is not None else "err"
        stale_str = "yes" if p.is_stale is True else ("no" if p.is_stale is False else "?")
        if p.error:
            stale_str = "err"
        synced_str = (
            p.last_synced_at.strftime("%Y-%m-%d %H:%M:%S") if p.last_synced_at else "-"
        )
        typer.echo(
            f"| {p.project_name:<{name_w}} | {count_str:>{count_w}} "
            f"| {stale_str:^{stale_w}} | {synced_str:<{synced_w}} |"
        )

    typer.echo(sep)

    window_min = result.window_seconds // 60
    typer.echo(
        f"Total active agents: {result.total}"
        f"  [window: {window_min} min | status: {result.status}]"
    )
