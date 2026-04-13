"""Session intelligence handler functions for the versioned CCDash client API (v1).

This module defines pure handler functions (no router).  Each handler is
intended to be wired onto ``client_v1_router`` by the router registration
layer.  All handlers follow the ``_resolve_app_request`` pattern used
throughout the analytics and agent routers.
"""
from __future__ import annotations

from fastapi import HTTPException

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.agent_queries.models import SessionRef
from backend.application.services.session_intelligence import (
    SessionIntelligenceReadService,
    TranscriptSearchService,
)
from backend.db.factory import get_session_repository
from backend.models import (
    SessionIntelligenceConcern,
    SessionIntelligenceDetailResponse,
    SessionIntelligenceDrilldownResponse,
    SessionIntelligenceListResponse,
    SessionIntelligenceSessionRollup,
    SessionSemanticSearchResponse,
)
from backend.routers.client_v1_models import (
    ClientV1Envelope,
    ClientV1PaginatedEnvelope,
    SessionFamilyDTO,
    build_client_v1_meta,
    build_client_v1_paginated_meta,
)


# ---------------------------------------------------------------------------
# Module-level service singletons (same pattern as analytics.py)
# ---------------------------------------------------------------------------

session_intelligence_read_service = SessionIntelligenceReadService()
transcript_search_service = TranscriptSearchService()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _resolve_app_request(
    request_context: RequestContext,
    core_ports: CorePorts,
):
    """Resolve a transport-neutral application request from FastAPI dependencies."""
    return await resolve_application_request(
        request_context,
        core_ports,
        core_ports.storage.db,
    )


def _instance_id() -> str:
    """Return a best-effort instance identifier from config."""
    from backend import config as _cfg

    return getattr(_cfg, "INSTANCE_ID", "") or "ccdash-local"


# ---------------------------------------------------------------------------
# Handler: list sessions
# ---------------------------------------------------------------------------


async def list_sessions_v1(
    feature_id: str | None,
    root_session_id: str | None,
    limit: int,
    offset: int,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1PaginatedEnvelope[SessionIntelligenceSessionRollup]:
    """Return a paginated list of session intelligence rollups.

    Wraps ``SessionIntelligenceReadService.list_sessions``.  Default limit is
    50; maximum is 100.
    """
    app_request = await _resolve_app_request(request_context, core_ports)
    result: SessionIntelligenceListResponse = await session_intelligence_read_service.list_sessions(
        app_request.context,
        app_request.ports,
        feature_id=feature_id,
        root_session_id=root_session_id,
        session_id=None,
        offset=offset,
        limit=limit,
    )

    items = result.items if hasattr(result, "items") else []
    total = result.total if hasattr(result, "total") else len(items)

    return ClientV1PaginatedEnvelope(
        status="ok",
        data=items,
        meta=build_client_v1_paginated_meta(
            instance_id=_instance_id(),
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        ),
    )


# ---------------------------------------------------------------------------
# Handler: session detail
# ---------------------------------------------------------------------------


async def get_session_detail_v1(
    session_id: str,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[SessionIntelligenceDetailResponse]:
    """Return detailed intelligence for a single session.

    Raises HTTP 404 when the session is unknown.
    Wraps ``SessionIntelligenceReadService.get_session_detail``.
    """
    app_request = await _resolve_app_request(request_context, core_ports)
    detail: SessionIntelligenceDetailResponse | None = (
        await session_intelligence_read_service.get_session_detail(
            app_request.context,
            app_request.ports,
            session_id=session_id,
        )
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session intelligence for '{session_id}' not found",
        )
    return ClientV1Envelope(
        status="ok",
        data=detail,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Handler: session search
# ---------------------------------------------------------------------------


async def search_sessions_v1(
    q: str,
    feature_id: str | None,
    root_session_id: str | None,
    session_id: str | None,
    limit: int,
    offset: int,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[SessionSemanticSearchResponse]:
    """Full-text / semantic search across session transcripts.

    ``q`` must be at least 2 characters.  Default limit is 25; maximum is 100.
    Wraps ``TranscriptSearchService.search``.
    """
    if len(q) < 2:
        raise HTTPException(
            status_code=422,
            detail="Query parameter 'q' must be at least 2 characters",
        )

    app_request = await _resolve_app_request(request_context, core_ports)
    result: SessionSemanticSearchResponse = await transcript_search_service.search(
        app_request.context,
        app_request.ports,
        query=q,
        feature_id=feature_id,
        root_session_id=root_session_id,
        session_id=session_id,
        offset=offset,
        limit=limit,
    )
    return ClientV1Envelope(
        status="ok",
        data=result,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Handler: session drilldown
# ---------------------------------------------------------------------------


async def get_session_drilldown_v1(
    session_id: str,
    concern: SessionIntelligenceConcern,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[SessionIntelligenceDrilldownResponse]:
    """Return drilldown intelligence for a specific concern on a single session.

    ``session_id`` is a path parameter (unlike the legacy analytics endpoint
    where it is a query parameter).  Raises HTTP 404 when no data is found.
    Wraps ``SessionIntelligenceReadService.drilldown``.
    """
    app_request = await _resolve_app_request(request_context, core_ports)
    detail: SessionIntelligenceDrilldownResponse | None = (
        await session_intelligence_read_service.drilldown(
            app_request.context,
            app_request.ports,
            concern=concern,
            feature_id=None,
            root_session_id=None,
            session_id=session_id,
            offset=0,
            limit=50,
        )
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session intelligence drilldown for '{session_id}' / concern '{concern}' not found",
        )
    return ClientV1Envelope(
        status="ok",
        data=detail,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Handler: session family
# ---------------------------------------------------------------------------


async def get_session_family_v1(
    session_id: str,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[SessionFamilyDTO]:
    """Return all sessions that share the same ``root_session_id`` as *session_id*.

    Algorithm:
    1. Look up the target session to obtain its ``root_session_id``.
    2. Query all sessions in the project whose ``root_session_id`` matches.
    3. Return a ``SessionFamilyDTO`` wrapped in a ``ClientV1Envelope``.

    Raises HTTP 404 when the target session does not exist.
    """
    app_request = await _resolve_app_request(request_context, core_ports)
    session_repo = get_session_repository(core_ports.storage.db)

    # Step 1: resolve the anchor session.
    anchor = await session_repo.get_by_id(session_id)
    if anchor is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found",
        )

    root_id: str = anchor.get("root_session_id") or session_id

    # Step 2: fetch all family members.
    project_id: str = app_request.context.project.project_id if app_request.context.project else ""
    rows: list[dict] = await session_repo.list_paginated(
        offset=0,
        limit=500,
        project_id=project_id or None,
        sort_by="started_at",
        sort_order="asc",
        filters={"root_session_id": root_id},
    )

    # Step 3: map raw rows to SessionRef DTOs.
    members: list[SessionRef] = [
        SessionRef(
            session_id=row.get("id", ""),
            feature_id=row.get("task_id", ""),
            root_session_id=row.get("root_session_id", ""),
            title=row.get("title", ""),
            status=row.get("status", ""),
            started_at=row.get("started_at", ""),
            ended_at=row.get("ended_at", ""),
            model=row.get("model", ""),
            total_cost=float(row.get("total_cost") or 0.0),
            total_tokens=int(row.get("tokens_in", 0) or 0) + int(row.get("tokens_out", 0) or 0),
            duration_seconds=float(row.get("duration_seconds") or 0.0),
        )
        for row in rows
    ]

    dto = SessionFamilyDTO(
        root_session_id=root_id,
        session_count=len(members),
        members=members,
    )

    return ClientV1Envelope(
        status="ok",
        data=dto,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )
