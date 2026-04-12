"""Report generation commands."""
from __future__ import annotations

import typer

from backend.application.services.agent_queries import ReportingQueryService
from backend.cli import runtime
from backend.cli.output import OutputMode, get_formatter, resolve_output_mode


report_app = typer.Typer(help="Generate report artifacts.")
_report_service = ReportingQueryService()


@report_app.command("aar")
def aar(
    feature_id: str = typer.Option(..., "--feature", "-f", help="Feature ID for AAR generation."),
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Generate an after-action report for a feature."""

    async def _query():
        async def _invoke(context, ports):
            result = await _report_service.generate_aar(context, ports, feature_id)
            feature_exists = await ports.storage.features().get_by_id(feature_id)
            return result, context.project.project_id if context.project else None, bool(feature_exists)

        return await runtime.execute_query(_invoke)

    try:
        result, project_id, feature_exists = runtime.run_async(_query())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.status == "error":
        if not project_id:
            typer.echo(f"Error: {runtime.project_resolution_error_message()}", err=True)
        elif not feature_exists:
            typer.echo(
                f"Error: {runtime.feature_not_found_error_message(feature_id, project_id)}",
                err=True,
            )
        else:
            typer.echo("Error: AAR report could not be generated.", err=True)
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

    typer.echo(get_formatter(mode).render(result, title=f"AAR Report: {feature_id}"))

