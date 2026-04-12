"""Workflow diagnostics commands."""
from __future__ import annotations

import typer

from backend.application.services.agent_queries import WorkflowDiagnosticsQueryService
from backend.cli import runtime
from backend.cli.output import OutputMode, get_formatter, resolve_output_mode


workflow_app = typer.Typer(help="Workflow diagnostics.")
_workflow_service = WorkflowDiagnosticsQueryService()


@workflow_app.command("failures")
def failures(
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Show workflows with the highest observed failure burden."""

    async def _query():
        async def _invoke(context, ports):
            return await _workflow_service.get_diagnostics(context, ports)

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

    payload = {
        "status": result.status,
        "project_id": result.project_id,
        "feature_id": result.feature_id,
        "generated_at": result.generated_at,
        "data_freshness": result.data_freshness,
        "source_refs": result.source_refs,
        "problem_workflows": [item.model_dump(mode="json") for item in result.problem_workflows],
    }
    typer.echo(get_formatter(mode).render(payload, title="Workflow Failures"))

