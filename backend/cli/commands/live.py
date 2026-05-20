"""Live metrics commands."""
from __future__ import annotations

import json

import typer

from backend.application.services.agent_queries import LiveMetricsQueryService
from backend.cli import runtime


live_app = typer.Typer(help="Live agent metrics.")
_live_service = LiveMetricsQueryService()


@live_app.command("active-count")
def active_count(
    project: str | None = typer.Option(
        None,
        "--project",
        help="Project ID to query (defaults to the active project).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON response."),
) -> None:
    """Show the number of currently active agent sessions for a project.

    Sessions are counted when both conditions hold:
    - status = 'active'
    - updated_at within the last 10 minutes (configurable via CCDASH_LIVE_AGENTS_WINDOW_SECONDS)

    Exits with code 0 on success, 1 on unexpected error, 2 on project-resolution failure.

    Options:
        --project TEXT   Override the active project ID.
        --json           Emit JSON matching the REST /api/agent/live/active-count response.
    """
    project_override = (project or "").strip() or runtime.PROJECT_OVERRIDE

    async def _query():
        async def _invoke(context, ports):
            return await _live_service.get_active_count(
                context,
                ports,
                project_id_override=project_override,
            )

        return await runtime.execute_query(_invoke)

    try:
        result = runtime.run_async(_query())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.status == "error":
        typer.echo(f"Error: {runtime.project_resolution_error_message()}", err=True)
        raise typer.Exit(code=2)

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "project_id": result.project_id,
                    "count": result.count,
                    "window_seconds": result.window_seconds,
                    "generated_at": result.generated_at.isoformat(),
                    "status": result.status,
                },
                indent=2,
            )
        )
    else:
        window_min = result.window_seconds // 60
        typer.echo(
            f"Active agents (last {window_min} min): {result.count}"
            f"  [project: {result.project_id}]"
        )
