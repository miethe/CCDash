"""Routing-feedback rollup CLI command (T5-003).

Exposes the persisted ``routing_rollup`` table -- the same read path as the
REST (``backend/routers/_client_v1_routing_rollup.py``) and MCP
(``backend/mcp/tools/routing.py``) transports -- through a single ``ccdash
routing rollup`` command. Mirrors ``report.py``'s ``aar_review`` command
shape as closely as the underlying contract allows: a
``runtime.execute_query(_invoke)`` closure, the standard
``--output``/``--json``/``--md`` flags, and ``get_formatter(mode).render(...)``
for final output.

Two divergences from ``aar_review``'s literal shape, both already flagged as
Findings in T5-001/T5-002 and repeated here for the same reason (not
independently re-discovered):

1. There is no ``RoutingRollupQueryService`` "read the persisted table back"
   method to delegate to -- this command reuses
   ``_client_v1_routing_rollup._fetch_routing_rollup`` directly, the exact
   same coroutine the REST and MCP transports call, so all three transports
   stay byte-identical by construction (T5-004) rather than by three
   independently-written implementations happening to agree.
2. ``RoutingRollupResponseDTO`` defines no ``status`` field (unlike
   ``AARReviewDTO``/``WorkflowDiagnosticsResult``), so this command cannot
   branch on ``result.status == "error"`` the way ``aar_review``/``workflow
   failures`` do -- ``_fetch_routing_rollup`` never raises a transport-level
   error state; it always degrades to a normalized disabled/empty/full
   envelope (D6/FR-10, resilience-by-default). This command therefore always
   renders the returned envelope; there is no error branch for this DTO.

No command-specific ``--project`` flag is added: the global ``--project``
override (``backend/cli/main.py``'s ``app.callback``) already threads through
``runtime.execute_query``'s header-based project resolution -- the same
pattern ``workflow failures`` uses, which also takes no per-command project
flag.
"""
from __future__ import annotations

import typer

from backend.cli import runtime
from backend.cli.output import OutputMode, get_formatter, resolve_output_mode
from backend.routers._client_v1_routing_rollup import _fetch_routing_rollup


routing_app = typer.Typer(help="Routing feedback commands.")


@routing_app.command("rollup")
def rollup(
    output: OutputMode | None = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Read-only Proof -> Routing Feedback Loop rollup (BP-6 producer surface).

    Serves the persisted ``routing_rollup`` table computed offline by Phase
    4's worker sweep -- the same read path as the REST and MCP transports,
    byte-identical by construction. Returns the deterministic disabled
    envelope (``enabled: false``, empty ``keys[]``, zero counters) when
    ``CCDASH_ROUTING_FEEDBACK_ENABLED`` is false.
    """

    async def _query():
        async def _invoke(context, ports):
            return await _fetch_routing_rollup(context, ports)

        return await runtime.execute_query(_invoke)

    try:
        result = runtime.run_async(_query())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

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

    typer.echo(get_formatter(mode).render(result, title="Routing Feedback Rollup"))
