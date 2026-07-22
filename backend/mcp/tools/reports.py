"""Report-generation MCP tools."""
from __future__ import annotations

from backend.application.services.agent_queries import AARReviewQueryService, ReportingQueryService
from backend.mcp.bootstrap import execute_query
from backend.mcp.tools import build_envelope


_service = ReportingQueryService()
_aar_review_service = AARReviewQueryService()


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

    @mcp.tool(name="ccdash_aar_review")
    async def ccdash_aar_review(document_id: str, project_id: str | None = None) -> dict:
        """Deterministic, model-free AAR-document-to-session triage review.

        Resolves an agent-written AAR document to the session(s) it describes
        and returns four deterministic surface flags plus a triage verdict
        (``surface_only`` vs ``deep_review_recommended``). No LLM call is made
        anywhere on this tool's compute path.
        """

        async def _query(context, ports):
            return await _aar_review_service.get_review(context, ports, document_id)

        result = await execute_query(
            _query,
            tool_name="ccdash_aar_review",
            project_id=project_id,
        )
        return build_envelope(result)


__all__ = ["register_report_tools"]
