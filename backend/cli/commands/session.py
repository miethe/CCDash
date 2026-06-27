"""Session intelligence CLI commands (Phase 3 / T3-002).

Provides:
  ccdash session search   — keyword / full-text search across session transcripts
  ccdash session get      — full session detail bundle (transcript-bearing)
  ccdash session transcript — cursor-paginated transcript page

All commands accept ``--project`` to scope to a non-active project.
``--project`` is required for ``get`` and ``transcript`` (no active-project
fallback — mirrors the Phase 2 REST invariant).

Delegates to the transport-neutral Phase 1 service
``backend.application.services.agent_queries.session_detail.get_session_detail``.
No raw SQL; no duplicate transcript reader.
"""
from __future__ import annotations

from typing import Optional

import typer

from backend.application.services.agent_queries.session_detail import (
    ALL_INCLUDE_FLAGS,
    INCLUDE_TRANSCRIPT,
    get_session_detail,
)
from backend.application.services.session_intelligence import TranscriptSearchService
from backend.cli import runtime
from backend.cli.output import OutputMode, get_formatter, resolve_output_mode

session_app = typer.Typer(help="Session intelligence commands.")

_search_service = TranscriptSearchService()


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@session_app.command("search")
def search(
    query: str = typer.Argument(..., help="Search text (min 2 characters)."),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        help="Project ID to search within.  Defaults to the active project.",
    ),
    feature: Optional[str] = typer.Option(
        None,
        "--feature",
        help="Filter results to sessions linked to this feature ID.",
    ),
    limit: int = typer.Option(25, "--limit", help="Max results to return (default 25)."),
    offset: int = typer.Option(0, "--offset", help="Pagination offset."),
    output: Optional[OutputMode] = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Search session transcripts by keyword or topic.

    Flags:
      --project TEXT   Project ID to scope the search (defaults to active project).
      --feature TEXT   Filter by feature ID.
      --limit INT      Max matches (default 25).
      --offset INT     Pagination offset.
      --json           JSON output.
      --md             Markdown output.
    """
    if len(query.strip()) < 2:
        typer.echo("Error: query must be at least 2 characters.", err=True)
        raise typer.Exit(code=2)

    # project override: explicit --project flag takes precedence over global
    effective_project = project.strip() if project and project.strip() else None
    if effective_project:
        runtime.PROJECT_OVERRIDE = effective_project

    async def _query_fn():
        async def _invoke(context, ports):
            return await _search_service.search(
                context,
                ports,
                query=query.strip(),
                feature_id=feature,
                root_session_id=None,
                session_id=None,
                offset=offset,
                limit=limit,
            )

        return await runtime.execute_query(_invoke)

    try:
        result = runtime.run_async(_query_fn())
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

    try:
        payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
    except Exception:
        payload = {}

    typer.echo(get_formatter(mode).render(payload, title=f'Session search: "{query}"'))


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@session_app.command("get")
def get(
    session_id: str = typer.Argument(..., help="Session ID to retrieve."),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        help=(
            "Required. Project that owns the session. "
            "No active-project fallback."
        ),
    ),
    include: Optional[list[str]] = typer.Option(
        None,
        "--include",
        help=(
            "Segment(s) to include: transcript, tokens, subagents, artifacts, links. "
            "Omit to return all segments."
        ),
    ),
    cursor: Optional[str] = typer.Option(
        None,
        "--cursor",
        help="Opaque pagination cursor for the transcript page.",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        help="Max transcript items per page (default 50, max 1000).",
    ),
    output: Optional[OutputMode] = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Return full session detail (transcript-bearing) for any project's session.

    ``--project`` is required — there is no active-project fallback.  This
    mirrors the Phase 2 REST invariant that ensures cross-project isolation.

    Flags:
      --project TEXT    Required. Project that owns the session.
      --include TEXT    Segment filter (repeatable): transcript, tokens, subagents,
                        artifacts, links.  Omit to return all segments.
      --cursor TEXT     Transcript page cursor (from previous --cursor or nextCursor).
      --limit INT       Max transcript items per page (default 50).
      --json            JSON output.
      --md              Markdown output.
    """
    effective_project = project.strip() if project and project.strip() else None
    if not effective_project:
        typer.echo(
            "Error: --project is required for `session get`. "
            "Pass --project <project_id>. "
            "No active-project fallback is supported.",
            err=True,
        )
        raise typer.Exit(code=2)

    eff_include = frozenset(include) if include else None

    async def _query_fn():
        async def _invoke(context, ports):
            bundle = await get_session_detail(
                project_id=effective_project,
                session_id=session_id,
                ports=ports,
                include=eff_include,
                cursor=cursor,
                limit=limit if limit > 0 else None,
                context=context,
            )
            return bundle

        return await runtime.execute_query(_invoke)

    try:
        bundle = runtime.run_async(_query_fn())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if bundle is None:
        typer.echo(
            f"Error: Session '{session_id}' not found in project '{effective_project}'.",
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

    payload = bundle.as_dict()
    typer.echo(get_formatter(mode).render(payload, title=f"Session {session_id}"))


# ---------------------------------------------------------------------------
# transcript
# ---------------------------------------------------------------------------


@session_app.command("transcript")
def transcript(
    session_id: str = typer.Argument(..., help="Session ID to retrieve the transcript for."),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        help=(
            "Required. Project that owns the session. "
            "No active-project fallback."
        ),
    ),
    cursor: Optional[str] = typer.Option(
        None,
        "--cursor",
        help="Opaque pagination cursor from a previous response nextCursor.",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        help="Max transcript items per page (default 50, max 1000).",
    ),
    output: Optional[OutputMode] = typer.Option(None, "--output", help="Output format."),
    json_output: bool = typer.Option(False, "--json", help="Shortcut for --output json."),
    markdown_output: bool = typer.Option(False, "--md", help="Shortcut for --output markdown."),
) -> None:
    """Return a cursor-paginated transcript page for any project's session.

    ``--project`` is required — there is no active-project fallback.  Use
    the ``nextCursor`` field from the output (with ``--json``) to retrieve
    subsequent pages.

    Flags:
      --project TEXT    Required. Project that owns the session.
      --cursor TEXT     Opaque pagination cursor (from previous nextCursor).
      --limit INT       Max items per page (default 50).
      --json            JSON output (recommended for cursor-based pagination).
      --md              Markdown output.
    """
    effective_project = project.strip() if project and project.strip() else None
    if not effective_project:
        typer.echo(
            "Error: --project is required for `session transcript`. "
            "Pass --project <project_id>. "
            "No active-project fallback is supported.",
            err=True,
        )
        raise typer.Exit(code=2)

    async def _query_fn():
        async def _invoke(context, ports):
            bundle = await get_session_detail(
                project_id=effective_project,
                session_id=session_id,
                ports=ports,
                include={INCLUDE_TRANSCRIPT},
                cursor=cursor,
                limit=limit if limit > 0 else None,
                context=context,
            )
            return bundle

        return await runtime.execute_query(_invoke)

    try:
        bundle = runtime.run_async(_query_fn())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if bundle is None:
        typer.echo(
            f"Error: Session '{session_id}' not found in project '{effective_project}'.",
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

    transcript_page = bundle.transcript
    if transcript_page is not None:
        payload = {
            "sessionId": bundle.session_id,
            "projectId": bundle.project_id,
            "items": transcript_page.items,
            "cursor": transcript_page.cursor,
            "limit": transcript_page.limit,
            "nextCursor": transcript_page.next_cursor,
            "redactedFieldCount": bundle.redacted_field_count,
        }
    else:
        payload = {
            "sessionId": bundle.session_id,
            "projectId": bundle.project_id,
            "items": [],
            "cursor": "",
            "limit": limit,
            "nextCursor": None,
            "redactedFieldCount": 0,
        }

    typer.echo(
        get_formatter(mode).render(payload, title=f"Transcript — {session_id}")
    )
    if mode == OutputMode.human and transcript_page:
        item_count = len(transcript_page.items)
        has_more = transcript_page.next_cursor is not None
        summary = f"{item_count} item(s) on this page"
        if has_more:
            summary += " (more available — use --cursor to continue)"
        typer.echo(summary)
