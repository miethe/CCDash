"""Versioned client API for the standalone CCDash CLI.

All endpoints live under ``/api/v1/`` and return responses wrapped in the
standard ``ClientV1Envelope`` or ``ClientV1PaginatedEnvelope``.  Handlers
are defined in domain-specific modules and wired onto the router here.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path, Query

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.models import SessionIntelligenceConcern
from backend.request_scope import get_core_ports, get_request_context
from backend.routers.client_v1_models import (
    ClientV1Envelope,
    ClientV1Meta,
    InstanceMetaDTO,
)
from backend.routers._client_v1_project import (
    get_project_status_v1,
    get_workflow_failures_v1,
)
from backend.routers._client_v1_features import (
    get_feature_detail_v1,
    get_feature_documents_v1,
    get_feature_sessions_v1,
    list_features_v1,
)
from backend.routers._client_v1_sessions import (
    get_session_detail_v1,
    get_session_drilldown_v1,
    get_session_family_v1,
    list_sessions_v1,
    search_sessions_v1,
)


client_v1_router = APIRouter(prefix="/api/v1", tags=["client-v1"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _instance_id() -> str:
    return getattr(config, "INSTANCE_ID", "") or "ccdash-local"


def _version() -> str:
    return getattr(config, "CCDASH_VERSION", "") or "0.1.0"


def _environment() -> str:
    return getattr(config, "ENVIRONMENT", "") or "local"


# ---------------------------------------------------------------------------
# Instance / connectivity
# ---------------------------------------------------------------------------


@client_v1_router.get("/instance")
async def get_instance_metadata() -> ClientV1Envelope[InstanceMetaDTO]:
    """Return instance identity, version, and capability advertisement."""
    data = InstanceMetaDTO(
        instance_id=_instance_id(),
        version=_version(),
        environment=_environment(),
        db_backend=config.DB_BACKEND,
        capabilities=["project", "features", "sessions", "workflows", "reports"],
        server_time=datetime.now(timezone.utc),
    )
    return ClientV1Envelope(
        data=data,
        meta=ClientV1Meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


@client_v1_router.get("/project/status")
async def project_status(
    project_id: str | None = Query(default=None, description="Optional project override."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return the project status snapshot."""
    return await get_project_status_v1(project_id, request_context, core_ports)


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------


@client_v1_router.get("/workflows/failures")
async def workflow_failures(
    feature_id: str | None = Query(default=None, description="Optional feature filter."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return workflow failure patterns and diagnostics."""
    return await get_workflow_failures_v1(feature_id, request_context, core_ports)


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


@client_v1_router.get("/features")
async def features_list(
    status: list[str] | None = Query(default=None, description="Filter by status (repeatable)."),
    category: str | None = Query(default=None, description="Filter by category."),
    limit: int = Query(default=50, ge=1, le=200, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return a paginated list of features."""
    return await list_features_v1(status, category, limit, offset, request_context, core_ports)


@client_v1_router.get("/features/{feature_id}")
async def feature_detail(
    feature_id: str = Path(..., description="Feature ID to inspect."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return full forensic detail for a single feature."""
    return await get_feature_detail_v1(feature_id, request_context, core_ports)


@client_v1_router.get("/features/{feature_id}/sessions")
async def feature_sessions(
    feature_id: str = Path(..., description="Feature ID."),
    limit: int = Query(default=50, ge=1, le=200, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return sessions linked to a feature."""
    return await get_feature_sessions_v1(feature_id, limit, offset, request_context, core_ports)


@client_v1_router.get("/features/{feature_id}/documents")
async def feature_documents(
    feature_id: str = Path(..., description="Feature ID."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return documents linked to a feature."""
    return await get_feature_documents_v1(feature_id, request_context, core_ports)


# ---------------------------------------------------------------------------
# Sessions — search MUST be registered before {session_id} path
# ---------------------------------------------------------------------------


@client_v1_router.get("/sessions/search")
async def sessions_search(
    q: str = Query(..., min_length=2, description="Transcript query text."),
    feature_id: str | None = Query(default=None, description="Filter to a specific feature."),
    root_session_id: str | None = Query(default=None, description="Filter to a root session family."),
    session_id: str | None = Query(default=None, description="Filter to a single session."),
    limit: int = Query(default=25, ge=1, le=100, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Full-text / semantic search across session transcripts."""
    return await search_sessions_v1(q, feature_id, root_session_id, session_id, limit, offset, request_context, core_ports)


@client_v1_router.get("/sessions")
async def sessions_list(
    feature_id: str | None = Query(default=None, description="Filter to a specific feature."),
    root_session_id: str | None = Query(default=None, description="Filter to a root session family."),
    limit: int = Query(default=50, ge=1, le=100, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return a paginated list of session intelligence rollups."""
    return await list_sessions_v1(feature_id, root_session_id, limit, offset, request_context, core_ports)


@client_v1_router.get("/sessions/{session_id}")
async def session_detail(
    session_id: str = Path(..., description="Session ID to inspect."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return detailed intelligence for a single session."""
    return await get_session_detail_v1(session_id, request_context, core_ports)


@client_v1_router.get("/sessions/{session_id}/drilldown")
async def session_drilldown(
    session_id: str = Path(..., description="Session ID."),
    concern: SessionIntelligenceConcern = Query(..., description="Which intelligence concern to inspect."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return drilldown intelligence for a specific concern on a session."""
    return await get_session_drilldown_v1(session_id, concern, request_context, core_ports)


@client_v1_router.get("/sessions/{session_id}/family")
async def session_family(
    session_id: str = Path(..., description="Session ID."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Return all sessions sharing the same root session."""
    return await get_session_family_v1(session_id, request_context, core_ports)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@client_v1_router.post("/reports/aar")
async def generate_aar_report(
    feature_id: str = Query(..., description="Feature ID for the after-action report."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
):
    """Generate a deterministic after-action report for a feature."""
    from backend.application.services.agent_queries import ReportingQueryService
    from backend.application.services import resolve_application_request

    reporting_query_service = ReportingQueryService()
    app_request = await resolve_application_request(
        request_context, core_ports, core_ports.storage.db,
    )
    result = await reporting_query_service.generate_aar(
        app_request.context,
        app_request.ports,
        feature_id,
    )
    return ClientV1Envelope(
        data=result,
        meta=ClientV1Meta(instance_id=_instance_id()),
    )
