"""Research run intelligence CLI commands (T2-005, FR-11).

Provides:
  ccdash research-run list   — cursor-paginated page of ``research_runs``
                                rollup rows for a project.
  ccdash research-run get    — a single run's full detail, including its
                                linked-session correlation (AC-3).

Thin transport wrappers over ``run_intelligence.py`` (T2-003) — no query
logic lives here. Both commands call the shared
:class:`RunIntelligenceQueryService` and render its DTOs verbatim, so the
CLI shape mirrors the REST route (T2-004) and the MCP tools
(``backend/mcp/tools/research_runs.py``) byte-for-byte.
"""
from __future__ import annotations

from typing import Optional

import typer

from backend.application.services.agent_queries.run_intelligence import (
    RunIntelligenceQueryService,
)
from backend.cli import runtime
from backend.cli.output import OutputMode, get_formatter, resolve_output_mode

research_run_app = typer.Typer(help="Research Foundry run intelligence commands.")
_run_service = RunIntelligenceQueryService()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@research_run_app.command("list")
def list_runs(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        help="Project ID to scope the list. Defaults to the active project.",
    ),
    cursor: Optional[str] = typer.Option(
        None,
        "--cursor",
        help="Opaque pagination cursor from a previous response's next_cursor.",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        help="Max rows per page (default 50, service-capped at 200).",
    ),
    output: Optional[OutputMode] = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """List Research Foundry ``research_runs`` rollup rows, newest-first.

    Flags:
      --project TEXT   Project ID to scope the list (defaults to active project).
      --cursor TEXT    Pagination cursor (from a previous next_cursor).
      --limit INT      Max rows per page (default 50).
      --json           JSON output (recommended for cursor-based pagination).
      --md             Markdown output.
    """
    effective_project = project.strip() if project and project.strip() else None
    if effective_project:
        runtime.PROJECT_OVERRIDE = effective_project

    async def _query_fn():
        async def _invoke(context, ports):
            return await _run_service.list_runs(
                context,
                ports,
                project_id_override=effective_project,
                cursor=cursor,
                limit=limit,
            )

        return await runtime.execute_query(_invoke)

    try:
        result = runtime.run_async(_query_fn())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.status == "error":
        typer.echo(f"Error: {runtime.project_resolution_error_message()}", err=True)
        raise typer.Exit(code=2)

    try:
        mode = resolve_output_mode(
            output=output,
            json_output=json_output,
            markdown_output=markdown_output,
            default=runtime.OUTPUT_MODE,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    payload = result.model_dump(mode="json")
    typer.echo(
        get_formatter(mode).render(payload, title=f"Research runs — {result.project_id}")
    )
    if mode == OutputMode.human:
        item_count = len(payload.get("items", []))
        has_more = payload.get("next_cursor") is not None
        summary = f"{item_count} run(s) on this page"
        if has_more:
            summary += " (more available — use --cursor to continue)"
        typer.echo(summary)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@research_run_app.command("get")
def get_run(
    run_id: str = typer.Argument(
        ..., help="CCDash-canonical UUID run_id (never RF's raw semantic slug)."
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        help="Project ID that owns the run. Defaults to the active project.",
    ),
    output: Optional[OutputMode] = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Return a single ``research_runs`` rollup row plus its linked sessions.

    Flags:
      --project TEXT   Project ID that owns the run (defaults to active project).
      --json           JSON output.
      --md             Markdown output.
    """
    effective_project = project.strip() if project and project.strip() else None
    if effective_project:
        runtime.PROJECT_OVERRIDE = effective_project

    async def _query_fn():
        async def _invoke(context, ports):
            return await _run_service.get_run_detail(
                context,
                ports,
                run_id,
                project_id_override=effective_project,
            )

        return await runtime.execute_query(_invoke)

    try:
        result = runtime.run_async(_query_fn())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.status == "error":
        typer.echo(f"Error: {runtime.project_resolution_error_message()}", err=True)
        raise typer.Exit(code=2)

    if not result.found:
        typer.echo(
            f"Error: Research run '{run_id}' was not found in project "
            f"'{result.project_id}'.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        mode = resolve_output_mode(
            output=output,
            json_output=json_output,
            markdown_output=markdown_output,
            default=runtime.OUTPUT_MODE,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    payload = result.model_dump(mode="json")
    typer.echo(get_formatter(mode).render(payload, title=f"Research run {run_id}"))
