"""Workflow-level MCP tools."""
from __future__ import annotations

from backend.application.services.agent_queries import WorkflowDiagnosticsQueryService
from backend.mcp.bootstrap import execute_query
from backend.mcp.tools import build_envelope


_service = WorkflowDiagnosticsQueryService()


def register_workflow_tools(mcp) -> None:
    @mcp.tool(name="ccdash_workflow_failure_patterns")
    async def ccdash_workflow_failure_patterns(
        feature_id: str | None = None,
        project_id: str | None = None,
    ) -> dict:
        """Summarize workflow effectiveness and recurring failure patterns for a project or feature."""

        async def _query(context, ports):
            return await _service.get_diagnostics(
                context,
                ports,
                feature_id=feature_id,
            )

        result = await execute_query(
            _query,
            tool_name="ccdash_workflow_failure_patterns",
            project_id=project_id,
        )
        return build_envelope(result)


__all__ = ["register_workflow_tools"]
