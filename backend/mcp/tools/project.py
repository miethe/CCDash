"""Project-level MCP tools."""
from __future__ import annotations

from backend.application.services.agent_queries import ProjectStatusQueryService
from backend.mcp.bootstrap import execute_query
from backend.mcp.tools import build_envelope


_service = ProjectStatusQueryService()


def register_project_tools(mcp) -> None:
    @mcp.tool(name="ccdash_project_status")
    async def ccdash_project_status(project_id: str | None = None) -> dict:
        """Get the current CCDash project status snapshot for the active or specified project."""

        async def _query(context, ports):
            return await _service.get_status(
                context,
                ports,
                project_id_override=project_id,
            )

        result = await execute_query(
            _query,
            tool_name="ccdash_project_status",
            project_id=project_id,
        )
        return build_envelope(result)


__all__ = ["register_project_tools"]
