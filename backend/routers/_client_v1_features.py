"""Handler functions for v1 client API feature endpoints.

This module defines handlers only — no router is created here.
Handlers are registered on ``client_v1_router`` in ``client_v1.py``.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.agent_queries import (
    FeatureForensicsDTO,
    FeatureForensicsQueryService,
)
from backend.routers.client_v1_models import (
    ClientV1Envelope,
    ClientV1PaginatedEnvelope,
    FeatureDocumentsDTO,
    FeatureSummaryDTO,
    FeatureSessionsDTO,
    build_client_v1_meta,
    build_client_v1_paginated_meta,
)

logger = logging.getLogger("ccdash.client_v1.features")

_feature_forensics_query_service = FeatureForensicsQueryService()

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MAX_LIMIT = 200


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, _MAX_LIMIT))


def _instance_id() -> str:
    from backend import config as _cfg

    return getattr(_cfg, "INSTANCE_ID", "") or "ccdash-local"


async def _resolve_app_request(
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    requested_project_id: str | None = None,
):
    return await resolve_application_request(
        request_context,
        core_ports,
        core_ports.storage.db,
        requested_project_id=requested_project_id,
    )


def _row_to_feature_summary(row: dict) -> FeatureSummaryDTO:
    return FeatureSummaryDTO(
        id=row.get("id", ""),
        name=row.get("name", ""),
        status=row.get("status", ""),
        category=row.get("category", ""),
        priority=row.get("priority", ""),
        total_tasks=row.get("total_tasks", 0) or 0,
        completed_tasks=row.get("completed_tasks", 0) or 0,
        updated_at=row.get("updated_at", ""),
    )


async def _get_forensics(
    feature_id: str,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> tuple[FeatureForensicsDTO, str]:
    """Return ``(forensics_dto, feature_slug)``.

    Raises ``HTTPException(404)`` when the feature is not found.
    """
    app_request = await _resolve_app_request(request_context, core_ports)
    forensics = await _feature_forensics_query_service.get_forensics(
        app_request.context,
        app_request.ports,
        feature_id,
    )
    if forensics.status == "error":
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_id}' not found.",
        )
    return forensics, forensics.feature_slug or feature_id


# ---------------------------------------------------------------------------
# Handler: list features
# ---------------------------------------------------------------------------


async def list_features_v1(
    status: list[str] | None,
    category: str | None,
    limit: int,
    offset: int,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1PaginatedEnvelope[FeatureSummaryDTO]:
    """Return a paginated list of features for the active project."""
    effective_limit = _clamp_limit(limit)
    effective_offset = max(0, offset)

    app_request = await _resolve_app_request(request_context, core_ports)
    feature_repo = app_request.ports.storage.features()

    # Resolve project_id from the resolved context scope
    project_id: str | None = None
    try:
        scope = app_request.ports.workspace_registry.resolve_scope()
        _, project_scope = scope
        if project_scope is not None:
            project_id = project_scope.project_id
    except Exception:
        logger.debug("Could not resolve project scope for list_features_v1")

    rows = await feature_repo.list_paginated(project_id, effective_offset, effective_limit)
    total = await feature_repo.count(project_id)

    # Apply optional in-memory filters (status and category are low-cardinality
    # and not yet supported at the repository layer).
    if status:
        status_lower = {s.lower() for s in status}
        rows = [r for r in rows if str(r.get("status", "")).lower() in status_lower]
    if category:
        category_lower = category.lower()
        rows = [r for r in rows if str(r.get("category", "")).lower() == category_lower]

    items = [_row_to_feature_summary(row) for row in rows]

    return ClientV1PaginatedEnvelope(
        data=items,
        meta=build_client_v1_paginated_meta(
            instance_id=_instance_id(),
            total=total,
            offset=effective_offset,
            limit=effective_limit,
            has_more=(effective_offset + len(items)) < total,
        ),
    )


# ---------------------------------------------------------------------------
# Handler: feature detail
# ---------------------------------------------------------------------------


async def get_feature_detail_v1(
    feature_id: str,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[FeatureForensicsDTO]:
    """Return full forensic detail for a single feature.

    The ``data.linked_sessions`` field in the response is the authoritative
    session list. This endpoint and ``GET /v1/features/{id}/sessions`` both
    source that list from the same ``FeatureForensicsDTO`` via ``_get_forensics()``
    — they cannot disagree. Linkage is eventually-consistent (populated by the
    background sync engine).
    """
    forensics, _ = await _get_forensics(feature_id, request_context, core_ports)
    return ClientV1Envelope(
        data=forensics,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Handler: feature sessions
# ---------------------------------------------------------------------------


async def get_feature_sessions_v1(
    feature_id: str,
    limit: int,
    offset: int,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[FeatureSessionsDTO]:
    """Return sessions linked to a feature, paginated.

    Session data is drawn from ``forensics.linked_sessions`` — the same field
    served by ``GET /v1/features/{id}`` — so both endpoints are always in sync.
    ``data.total`` reflects the full linked-session count; ``data.sessions``
    contains the requested page slice.
    """
    effective_limit = _clamp_limit(limit)
    effective_offset = max(0, offset)

    forensics, feature_slug = await _get_forensics(feature_id, request_context, core_ports)

    all_sessions = forensics.linked_sessions
    page = all_sessions[effective_offset : effective_offset + effective_limit]

    dto = FeatureSessionsDTO(
        feature_id=feature_id,
        feature_slug=feature_slug,
        sessions=page,
        total=len(all_sessions),
    )
    return ClientV1Envelope(
        data=dto,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Handler: feature documents
# ---------------------------------------------------------------------------


async def get_feature_documents_v1(
    feature_id: str,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[FeatureDocumentsDTO]:
    """Return documents linked to a feature."""
    forensics, feature_slug = await _get_forensics(feature_id, request_context, core_ports)

    dto = FeatureDocumentsDTO(
        feature_id=feature_id,
        feature_slug=feature_slug,
        documents=forensics.linked_documents,
    )
    return ClientV1Envelope(
        data=dto,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )
