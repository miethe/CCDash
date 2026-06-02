"""MeatyWiki research notes REST router (P5-013).

All endpoints are capability-gated: when ``CCDASH_MEATYWIKI_ENABLED=false``
(default) the query service returns an empty-state DTO with ``enabled=False``
— never a 503.  The frontend should hide the MeatyWiki surface when
``enabled=False``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.agent_queries.research_note_queries import (
    ResearchNoteQueryService,
)
from backend.application.services.common import resolve_project
from backend.models import ResearchNoteResponse
from backend.request_scope import get_core_ports, get_request_context

meatywiki_router = APIRouter(prefix="/api/integrations/meatywiki", tags=["meatywiki"])

_research_note_query_service = ResearchNoteQueryService()


@meatywiki_router.get(
    "/research",
    response_model=ResearchNoteResponse,
    summary="MeatyWiki research notes for a feature",
)
async def get_research_notes(
    feature_id: str = Query(..., description="Feature to retrieve research notes for."),
    project_id: str | None = Query(default=None, description="Optional project override."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ResearchNoteResponse:
    """Return MeatyWiki research notes for a feature.

    Returns ``{items: [], enabled: false}`` when ``CCDASH_MEATYWIKI_ENABLED``
    is off.  The response is never a 503 — callers must inspect ``enabled`` to
    decide whether to surface the MeatyWiki panel.
    """
    project = resolve_project(
        request_context,
        core_ports,
        requested_project_id=project_id,
    )
    resolved_project_id = project.id if project is not None else ""

    return await _research_note_query_service.get_for_feature(
        request_context,
        core_ports,
        project_id=resolved_project_id,
        feature_id=feature_id,
    )
