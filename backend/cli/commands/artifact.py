"""Artifact intelligence commands."""
from __future__ import annotations

from typing import Any

import typer

from backend.application.services.agent_queries import ArtifactIntelligenceQueryService
from backend.cli import runtime
from backend.cli.output import OutputMode, get_formatter, resolve_output_mode
from backend.mcp.tools.artifacts import format_recommendations_markdown


artifact_app = typer.Typer(help="Artifact intelligence commands.")
_artifact_service = ArtifactIntelligenceQueryService()


def _resolve_mode(
    *,
    output: OutputMode | None,
    json_output: bool,
    markdown_output: bool,
) -> OutputMode:
    try:
        return resolve_output_mode(
            output=output,
            json_output=json_output,
            markdown_output=markdown_output,
            default=runtime.OUTPUT_MODE,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc


def _project_resolution_error(project_id: str | None) -> str:
    if project_id:
        return f"Project '{project_id}' was not found."
    return runtime.project_resolution_error_message()


@artifact_app.command("rankings")
def rankings(
    project_id: str | None = typer.Option(None, "--project", help="Project ID to inspect."),
    period: str = typer.Option("7d", "--period", help="Ranking period."),
    limit: int = typer.Option(25, "--limit", min=1, max=100, help="Maximum rows to return."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Show artifact rankings for a project."""

    async def _query():
        async def _invoke(context, ports):
            return await _artifact_service.get_rankings(
                context,
                ports,
                project_id_override=project_id,
                period=period,
                limit=limit,
            )

        return await runtime.execute_query(_invoke)

    try:
        result = runtime.run_async(_query())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.status == "error":
        typer.echo(f"Error: {_project_resolution_error(project_id)}", err=True)
        raise typer.Exit(code=2)

    mode = _resolve_mode(output=output, json_output=json_output, markdown_output=markdown_output)
    rows: list[dict[str, Any]] = result.rows[:limit]
    if not rows and mode == OutputMode.human:
        typer.echo("")
        return
    if mode == OutputMode.json:
        payload: Any = {
            "status": result.status,
            "project_id": result.project_id,
            "period": result.period,
            "total": result.total,
            "rows": rows,
        }
    else:
        payload = rows
    typer.echo(get_formatter(mode).render(payload, title="Artifact Rankings"))


@artifact_app.command("recommendations")
def recommendations(
    project_id: str | None = typer.Option(None, "--project", help="Project ID to inspect."),
    min_confidence: float = typer.Option(0.7, "--min-confidence", min=0.0, max=1.0, help="Minimum confidence."),
    limit: int = typer.Option(5, "--limit", min=1, max=100, help="Maximum recommendations to return."),
    period: str = typer.Option("30d", "--period", help="Ranking period."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Show artifact optimization recommendations for a project."""

    async def _query():
        async def _invoke(context, ports):
            return await _artifact_service.get_recommendations(
                context,
                ports,
                project_id_override=project_id,
                period=period,
                min_confidence=min_confidence,
                limit=limit,
            )

        return await runtime.execute_query(_invoke)

    try:
        result = runtime.run_async(_query())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.status == "error":
        typer.echo(f"Error: {_project_resolution_error(project_id)}", err=True)
        raise typer.Exit(code=2)

    mode = _resolve_mode(output=output, json_output=json_output, markdown_output=markdown_output)
    recommendations_payload = result.recommendations[:limit]
    if not recommendations_payload and mode != OutputMode.json:
        typer.echo("No recommendations available")
        return
    if mode == OutputMode.markdown:
        typer.echo(format_recommendations_markdown(result.project_id, recommendations_payload))
        return
    payload: Any = {
        "status": result.status,
        "project_id": result.project_id,
        "period": result.period,
        "total": result.total,
        "recommendations": recommendations_payload,
    }
    typer.echo(get_formatter(mode).render(payload, title="Artifact Recommendations"))


__all__ = ["artifact_app"]
