"""Project status commands."""
from __future__ import annotations

import typer

from backend.application.services.agent_queries import ProjectStatusQueryService
from backend.cli import runtime
from backend.cli.output import OutputMode, get_formatter, resolve_output_mode


status_app = typer.Typer(help="Status queries.")
_status_service = ProjectStatusQueryService()


@status_app.command("project")
def project(
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Show a project status summary."""

    async def _query():
        async def _invoke(context, ports):
            return await _status_service.get_status(
                context,
                ports,
                project_id_override=runtime.PROJECT_OVERRIDE,
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

    typer.echo(get_formatter(mode).render(result, title="Project Status"))

