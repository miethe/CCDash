"""Research run intelligence MCP tools (T2-005, FR-11).

Thin transport wrappers over ``run_intelligence.py`` (T2-003) — no query
logic lives here. Both tools call the shared
:class:`RunIntelligenceQueryService` and return its DTOs verbatim (via
``build_envelope``), so the MCP shape mirrors the REST route (T2-004) and the
CLI commands (``backend/cli/commands/research_run.py``) byte-for-byte.

Tools:
  ccdash_research_runs_list  — cursor-paginated page of ``research_runs``
                                rollup rows for a project.
  ccdash_research_run_detail — a single run's full detail, including its
                                linked-session correlation (AC-3).
"""
from __future__ import annotations

from backend.application.services.agent_queries.run_intelligence import (
    RunIntelligenceQueryService,
)
from backend.mcp.bootstrap import execute_query
from backend.mcp.tools import build_envelope

_service = RunIntelligenceQueryService()

# ``run_id`` is added to the default (project_id, feature_id, feature_slug)
# identifier set so both tools surface it in ``meta`` when present — the
# list DTO omits it (absent -> skipped by build_envelope), the detail DTO
# always carries it.
_IDENTIFIERS = ("project_id", "run_id")


def register_research_run_tools(mcp) -> None:
    @mcp.tool(name="ccdash_research_runs_list")
    async def ccdash_research_runs_list(
        project_id: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Return a cursor-paginated page of Research Foundry ``research_runs`` rollups.

        Args:
            project_id: Optional project identifier; when None, uses the active project.
            cursor:     Opaque pagination cursor from a previous response's ``next_cursor``.
            limit:      Max rows per page (default 50, service-capped at 200).

        Returns:
            {status, data: {items, cursor, limit, next_cursor, ...},
             meta: {project_id, generated_at, data_freshness, source_refs}}
        """

        async def _query(context, ports):
            return await _service.list_runs(
                context,
                ports,
                project_id_override=project_id,
                cursor=cursor,
                limit=limit,
            )

        result = await execute_query(
            _query,
            tool_name="ccdash_research_runs_list",
            project_id=project_id,
        )
        return build_envelope(result, identifiers=_IDENTIFIERS)

    @mcp.tool(name="ccdash_research_run_detail")
    async def ccdash_research_run_detail(
        run_id: str,
        project_id: str | None = None,
    ) -> dict:
        """Return a single ``research_runs`` rollup row plus its linked sessions.

        "No such run" (missing, or belonging to a different project) is a
        normal ``status="ok"``/``found=False`` response — never an error.

        Args:
            run_id:     The CCDash-canonical UUID ``run_id`` (never RF's raw
                        semantic slug — see ``rf_run_id`` on the returned run).
            project_id: Optional project identifier; when None, uses the active project.

        Returns:
            {status, data: {run_id, found, run, ...},
             meta: {project_id, run_id, generated_at, data_freshness, source_refs}}
        """

        async def _query(context, ports):
            return await _service.get_run_detail(
                context,
                ports,
                run_id,
                project_id_override=project_id,
            )

        result = await execute_query(
            _query,
            tool_name="ccdash_research_run_detail",
            project_id=project_id,
        )
        return build_envelope(result, identifiers=_IDENTIFIERS)


__all__ = ["register_research_run_tools"]
