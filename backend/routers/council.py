"""ARC (Agent Review Council) REST router (P5-012).

All endpoints are capability-gated: when ``CCDASH_ARC_ENABLED=false`` (default)
the query service returns an empty-state DTO with ``enabled=False`` — never a
503.  The frontend should hide the ARC surface when ``enabled=False``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.agent_queries.council_review_queries import (
    CouncilReviewQueryService,
)
from backend.application.services.common import resolve_project
from backend.models import CouncilReviewResponse
from backend.request_scope import get_core_ports, get_request_context

arc_router = APIRouter(prefix="/api/agent", tags=["arc"])

_council_review_query_service = CouncilReviewQueryService()


@arc_router.get(
    "/features/{feature_id}/council",
    response_model=CouncilReviewResponse,
    summary="ARC council reviews for a feature",
)
async def get_feature_council_reviews(
    feature_id: str = Path(..., description="Feature to retrieve ARC reviews for."),
    project_id: str | None = Query(default=None, description="Optional project override."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> CouncilReviewResponse:
    """Return ARC council reviews for a feature.

    Returns ``{items: [], enabled: false}`` when ``CCDASH_ARC_ENABLED`` is off.
    The response is never a 503 — callers must inspect ``enabled`` to decide
    whether to surface the ARC panel.
    """
    project = resolve_project(
        request_context,
        core_ports,
        requested_project_id=project_id,
    )
    resolved_project_id = project.id if project is not None else ""

    return await _council_review_query_service.get_for_feature(
        request_context,
        core_ports,
        project_id=resolved_project_id,
        feature_id=feature_id,
    )
