"""Live-metrics MCP tools (live-agents-count-v1)."""
from __future__ import annotations

from backend.application.services.agent_queries import LiveMetricsQueryService
from backend.mcp.bootstrap import execute_query
from backend.mcp.tools import build_envelope


_service = LiveMetricsQueryService()


def register_live_tools(mcp) -> None:
    @mcp.tool(name="ccdash_live_active_count")
    async def ccdash_live_active_count(project_id: str | None = None) -> dict:
        """Return the number of currently active agent sessions for a project.

        Sessions are counted when both conditions hold:
        - status = 'active'
        - updated_at >= now() - window_seconds (default 600 s / 10 min)

        The freshness window defends against stale-active rows from un-rebounded
        file watchers (OQ-3 spike finding: rows up to 93 days old with status='active').

        Args:
            project_id: Optional project identifier; when None, uses the active project.

        Returns:
            A dict with keys:
            - project_id (str): resolved project identifier
            - count (int): number of currently active sessions
            - window_seconds (int): freshness window used for the query
            - generated_at (str ISO-8601): timestamp when the count was produced
            - status (str): 'ok' | 'partial' | 'error'
        """
        async def _query(context, ports):
            return await _service.get_active_count(
                context,
                ports,
                project_id_override=project_id,
            )

        result = await execute_query(
            _query,
            tool_name="ccdash_live_active_count",
            project_id=project_id,
        )
        return build_envelope(result)


__all__ = ["register_live_tools"]
