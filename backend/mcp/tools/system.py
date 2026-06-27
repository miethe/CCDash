"""System-wide metrics MCP tools (system-wide-metrics-v1)."""
from __future__ import annotations

from backend.application.services.agent_queries.system_metrics import SystemMetricsQueryService
from backend.mcp.bootstrap import execute_query
from backend.mcp.tools import build_envelope


_service = SystemMetricsQueryService()


def register_system_tools(mcp) -> None:
    @mcp.tool(name="ccdash_system_active_count")
    async def ccdash_system_active_count() -> dict:
        """Return the aggregated live-agent count across all known CCDash projects.

        Queries every project registered in the workspace and fans out active-count
        lookups in parallel (bounded by CCDASH_SYSTEM_METRICS_CONCURRENCY).

        Staleness semantics: a project is flagged ``is_stale=True`` when
        ``now() - max(sessions.updated_at)`` exceeds
        ``CCDASH_SYSTEM_METRICS_STALE_HORIZON_SECONDS`` (default 3600 s).
        Projects with no sessions at all return ``is_stale=null`` — staleness is
        indeterminate, not stale.  The result is cached server-side for
        ``CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS`` (default 30 s); consumers
        should not poll faster than once every 30 seconds.

        Returns:
            A dict with keys:
            - total (int): sum of active agent counts across all projects
            - per_project (list[dict]): per-project summaries with keys:
                - project_id (str)
                - project_name (str)
                - count (int | null): active session count; null on error
                - is_stale (bool | null): staleness flag; null when indeterminate
                - last_synced_at (str ISO-8601 | null): MAX(sessions.updated_at)
                - error (str | null): error message if the project query failed
            - window_seconds (int): freshness window used for the active-count query
            - generated_at (str ISO-8601): UTC timestamp when the response was produced
            - status (str): 'ok' when all projects succeeded; 'partial' when any errored
        """
        async def _query(context, ports):
            return await _service.get_system_active_count(context, ports)

        result = await execute_query(
            _query,
            tool_name="ccdash_system_active_count",
        )
        return build_envelope(result)


__all__ = ["register_system_tools"]
