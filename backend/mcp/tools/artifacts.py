"""Artifact intelligence MCP tools."""
from __future__ import annotations

from typing import Any

from backend.application.services.agent_queries import ArtifactIntelligenceQueryService
from backend.mcp.bootstrap import execute_query


_service = ArtifactIntelligenceQueryService()


def _recommendation_value(recommendation: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = recommendation.get(key)
        if value is not None:
            return value
    return None


def _format_confidence(value: Any) -> str:
    if value is None or value == "":
        return "unknown confidence"
    try:
        return f"{float(value) * 100:.0f}% confidence"
    except (TypeError, ValueError):
        return f"{value} confidence"


def _format_artifact_ids(value: Any) -> str:
    if isinstance(value, list):
        ids = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(ids) if ids else "unknown artifact"
    token = str(value or "").strip()
    return token or "unknown artifact"


def format_recommendations_markdown(project_id: str, recommendations: list[dict[str, Any]]) -> str:
    if not recommendations:
        return "No recommendations available"

    lines = [f"## Artifact recommendations for {project_id}", ""]
    for recommendation in recommendations:
        rec_type = _recommendation_value(recommendation, "type", "recommendation_type") or "recommendation"
        artifact_ids = _format_artifact_ids(
            _recommendation_value(recommendation, "affectedArtifactIds", "affected_artifact_ids")
        )
        confidence = _format_confidence(recommendation.get("confidence"))
        next_action = _recommendation_value(recommendation, "nextAction", "next_action")
        line = f"- **{artifact_ids}**: {rec_type} ({confidence})"
        if next_action:
            line = f"{line} - {next_action}"
        lines.append(line)
    return "\n".join(lines)


def register_artifact_tools(mcp) -> None:
    @mcp.tool(name="artifact_recommendations")
    async def artifact_recommendations(
        project_id: str,
        min_confidence: float = 0.7,
        limit: int = 5,
    ) -> str:
        """Return concise advisory artifact optimization recommendations for a CCDash project."""

        async def _query(context, ports):
            return await _service.get_recommendations(
                context,
                ports,
                project_id_override=project_id,
                min_confidence=min_confidence,
                limit=limit,
            )

        result = await execute_query(
            _query,
            tool_name="artifact_recommendations",
            project_id=project_id,
        )
        if result.status == "error":
            return "No recommendations available"
        return format_recommendations_markdown(
            result.project_id,
            result.recommendations[: max(0, limit)],
        )


__all__ = ["format_recommendations_markdown", "register_artifact_tools"]
