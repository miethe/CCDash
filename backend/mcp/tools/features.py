"""Feature-level MCP tools."""
from __future__ import annotations

from backend.application.services.agent_queries import FeatureForensicsQueryService
from backend.mcp.bootstrap import execute_query
from backend.mcp.tools import build_envelope


_service = FeatureForensicsQueryService()


def register_feature_tools(mcp) -> None:
    @mcp.tool(name="ccdash_feature_forensics")
    async def ccdash_feature_forensics(feature_id: str, project_id: str | None = None) -> dict:
        """Inspect a feature's execution history, linked evidence, and rework signals."""

        async def _query(context, ports):
            return await _service.get_forensics(context, ports, feature_id)

        result = await execute_query(
            _query,
            tool_name="ccdash_feature_forensics",
            project_id=project_id,
        )
        return build_envelope(result)


__all__ = ["register_feature_tools"]
