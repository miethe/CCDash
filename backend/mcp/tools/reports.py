"""Report-generation MCP tools."""
from __future__ import annotations

from backend.application.services.agent_queries import ReportingQueryService
from backend.mcp.bootstrap import execute_query
from backend.mcp.tools import build_envelope


_service = ReportingQueryService()


def register_report_tools(mcp) -> None:
    @mcp.tool(name="ccdash_generate_aar")
    async def ccdash_generate_aar(feature_id: str, project_id: str | None = None) -> dict:
        """Generate a read-only after-action report for a feature from existing CCDash evidence."""

        async def _query(context, ports):
            return await _service.generate_aar(context, ports, feature_id)

        result = await execute_query(
            _query,
            tool_name="ccdash_generate_aar",
            project_id=project_id,
        )
        return build_envelope(result)


__all__ = ["register_report_tools"]
