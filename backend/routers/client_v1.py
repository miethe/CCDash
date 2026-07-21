"""Versioned client API for the standalone CCDash CLI.

All endpoints live under ``/api/v1/`` and return responses wrapped in the
standard ``ClientV1Envelope`` or ``ClientV1PaginatedEnvelope``.  Handlers
are defined in domain-specific modules and wired onto the router here.

Auth (T10-004 / OQ-6):
  All routes are gated by ``require_v1_auth`` — a single injectable Depends
  that is a no-op when ``CCDASH_API_TOKEN`` is unset (local-trust default)
  and validates a bearer token when set.  See
  ``backend/routers/_client_v1_auth.py`` for the ADR-008 forward-compat
  contract.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, Path, Query

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.agent_queries import (
    AARReportDTO,
    DashboardBundleDTO,
    DashboardQueryService,
    FeatureForensicsDTO,
    ProjectStatusDTO,
    WorkflowDiagnosticsDTO,
)
from backend.observability import otel
from backend.application.services.feature_surface import (
    FeatureModalOverviewDTO,
    FeatureModalSectionDTO,
    LinkedFeatureSessionPageDTO,
)
from backend.models import SessionIntelligenceConcern
from backend.models import (
    SessionIntelligenceDetailResponse,
    SessionIntelligenceDrilldownResponse,
    SessionIntelligenceSessionRollup,
    SessionSemanticSearchResponse,
)
from ccdash_contracts import CapabilityV1, SessionDetailV1, SessionTranscriptPageV1
from backend.request_scope import get_core_ports, get_request_context
from backend.routers._client_v1_auth import require_v1_auth
from backend.routers.client_v1_models import (
    ClientV1Envelope,
    ClientV1PaginatedEnvelope,
    FeatureDocumentsDTO,
    FeatureRollupResponseDTO,
    FeatureSessionsDTO,
    FeatureSummaryDTO,
    InstanceMetaDTO,
    SessionFamilyDTO,
    build_client_v1_meta,
)
from backend.routers._client_v1_project import (
    get_project_status_v1,
    get_workflow_failures_v1,
)
from backend.routers._client_v1_features import (
    FeatureRollupsRequest,
    get_feature_detail_v1,
    get_feature_documents_v1,
    get_feature_linked_session_page_v1,
    get_feature_modal_overview_v1,
    get_feature_modal_section_v1,
    get_feature_sessions_v1,
    list_features_v1,
    post_feature_rollups_v1,
)
from backend.routers._client_v1_sessions import (
    get_session_detail_v1,
    get_session_drilldown_v1,
    get_session_family_v1,
    get_session_full_detail_v1,
    get_session_transcript_page_v1,
    list_sessions_v1,
    search_sessions_v1,
)

# ---------------------------------------------------------------------------
# Router — single auth dependency applied to ALL /api/v1 routes (T10-004).
# When CCDASH_API_TOKEN is unset the dependency is a no-op (local-trust).
# ADR-008: replace require_v1_auth to upgrade auth model; no handler changes.
# ---------------------------------------------------------------------------

client_v1_router = APIRouter(
    prefix="/api/v1",
    tags=["client-v1"],
    dependencies=[Depends(require_v1_auth)],
)

# P5a: dashboard bundle service singleton (T5-001/T5-002)
_dashboard_query_service = DashboardQueryService()


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
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Capability discovery (T10-001)
# ---------------------------------------------------------------------------

#: Server-declared capability identifiers for IntentTree / LAN agent feature-detection.
#: Consumers MUST NOT hard-fail on an unknown capability string — future minor
#: versions may extend this list.
_V1_CAPABILITIES: list[str] = [
    "sessions:cross-project",  # detail+transcript accept explicit project_id (required, 400 if missing)
    "sessions:detail",         # full transcript-bearing bundle at /sessions/{id}/detail
    "research-runs:*",        # Research Foundry run telemetry ingest (T1-007) — POST
                               # /api/v1/ingest/rf-events + rf_events persistence; wildcard
                               # placeholder for the eventual query surface (Phase 3+).
]


@client_v1_router.get(
    "/capabilities",
    summary="Capability discovery for IntentTree and LAN agents",
    response_description="Advertised API capabilities and version string.",
)
async def get_capabilities() -> ClientV1Envelope[CapabilityV1]:
    """Return the server-declared capability set for feature-detection by agents.

    Callers SHOULD check ``capabilities`` before using a capability-dependent
    endpoint.  An absent capability means the server predates that feature; a
    present one means the server honours the documented contract for that
    capability string.  Unknown strings must be treated as future additions
    and MUST NOT cause the client to error.

    Served without active-project state — safe to call before establishing a
    project context.
    """
    data = CapabilityV1(
        api_version="1",
        capabilities=_V1_CAPABILITIES,
        instance_id=_instance_id(),
        server_time=datetime.now(timezone.utc),
    )
    return ClientV1Envelope(
        data=data,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


@client_v1_router.get("/project/status")
async def project_status(
    project_id: str | None = Query(default=None, description="Optional project override."),
    bypass_cache: bool = Query(default=False, description="Bypass the server-side query cache and fetch fresh data."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[ProjectStatusDTO]:
    """Return the project status snapshot."""
    return await get_project_status_v1(project_id, request_context, core_ports, bypass_cache=bypass_cache)


# ---------------------------------------------------------------------------
# Dashboard bundle (T5-002)
# ---------------------------------------------------------------------------


@client_v1_router.get("/dashboard")
async def dashboard_bundle(
    project_id: str | None = Query(default=None, description="Optional project override."),
    bypass_cache: bool = Query(default=False, description="Bypass the server-side query cache and fetch fresh data."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[DashboardBundleDTO]:
    """Return the Dashboard fat-read bundle.

    Composes the most-recent sessions page (limit 20, ``started_at`` desc) and
    task counts by status into a single above-fold response, collapsing ≤N
    parallel Dashboard requests to exactly 1.
    """
    with otel.start_span(
        "ccdash.dashboard.bundle",
        {"project_id": project_id or ""},
    ):
        data = await _dashboard_query_service.get_dashboard_bundle(
            request_context,
            core_ports,
            project_id_override=project_id,
            bypass_cache=bypass_cache,
        )
    return ClientV1Envelope(
        data=data,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------


@client_v1_router.get("/workflows/failures")
async def workflow_failures(
    feature_id: str | None = Query(default=None, description="Optional feature filter."),
    bypass_cache: bool = Query(default=False, description="Bypass the server-side query cache and fetch fresh data."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[WorkflowDiagnosticsDTO]:
    """Return workflow failure patterns and diagnostics."""
    return await get_workflow_failures_v1(feature_id, request_context, core_ports, bypass_cache=bypass_cache)


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


@client_v1_router.get("/features")
async def features_list(
    view: str = Query(default="summary", description="Response view: 'summary' preserves the legacy list, 'cards' uses the Phase 2 feature surface."),
    status: list[str] | None = Query(default=None, description="Filter by status (repeatable)."),
    stage: list[str] | None = Query(default=None, description="Filter by derived board stage (cards view only, repeatable)."),
    category: str | None = Query(default=None, description="Filter by category."),
    tags: list[str] | None = Query(default=None, description="Filter by tags (cards view only, repeatable)."),
    has_deferred: bool | None = Query(default=None, description="Filter to features with deferred tasks (cards view only)."),
    planned_from: str | None = Query(default=None, description="Planned lower date bound (cards view only)."),
    planned_to: str | None = Query(default=None, description="Planned upper date bound (cards view only)."),
    started_from: str | None = Query(default=None, description="Started lower date bound (cards view only)."),
    started_to: str | None = Query(default=None, description="Started upper date bound (cards view only)."),
    completed_from: str | None = Query(default=None, description="Completed lower date bound (cards view only)."),
    completed_to: str | None = Query(default=None, description="Completed upper date bound (cards view only)."),
    updated_from: str | None = Query(default=None, description="Updated lower date bound (cards view only)."),
    updated_to: str | None = Query(default=None, description="Updated upper date bound (cards view only)."),
    progress_min: float | None = Query(default=None, ge=0.0, le=1.0, description="Minimum progress ratio (cards view only)."),
    progress_max: float | None = Query(default=None, ge=0.0, le=1.0, description="Maximum progress ratio (cards view only)."),
    task_count_min: int | None = Query(default=None, ge=0, description="Minimum task count (cards view only)."),
    task_count_max: int | None = Query(default=None, ge=0, description="Maximum task count (cards view only)."),
    sort_by: str = Query(default="updated_at", description="Sort key for cards view."),
    sort_direction: str | None = Query(default=None, description="Sort direction for cards view."),
    include: list[str] | None = Query(default=None, description="Optional include fields for cards view."),
    limit: int = Query(default=200, ge=1, le=200, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    q: str | None = Query(default=None, description="Keyword substring filter on feature name and slug (case-insensitive)."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> object:
    """Return the legacy summary list or the richer Phase 2 feature-card view."""
    return await list_features_v1(
        status,
        category,
        limit,
        offset,
        request_context,
        core_ports,
        q=q,
        view=view,
        stage=stage,
        tags=tags,
        has_deferred=has_deferred,
        planned_from=planned_from,
        planned_to=planned_to,
        started_from=started_from,
        started_to=started_to,
        completed_from=completed_from,
        completed_to=completed_to,
        updated_from=updated_from,
        updated_to=updated_to,
        progress_min=progress_min,
        progress_max=progress_max,
        task_count_min=task_count_min,
        task_count_max=task_count_max,
        sort_by=sort_by,
        sort_direction=sort_direction,
        include=include,
    )


@client_v1_router.post("/features/rollups")
async def feature_rollups(
    payload: FeatureRollupsRequest = Body(...),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[FeatureRollupResponseDTO]:
    """Return bounded Phase 2 rollups for a list of feature IDs."""
    return await post_feature_rollups_v1(payload, request_context, core_ports)


@client_v1_router.get("/features/{feature_id}")
async def feature_detail(
    feature_id: str = Path(..., description="Feature ID to inspect."),
    bypass_cache: bool = Query(default=False, description="Bypass the server-side query cache and fetch fresh data."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[FeatureForensicsDTO]:
    """Return full forensic detail for a single feature."""
    return await get_feature_detail_v1(feature_id, request_context, core_ports, bypass_cache=bypass_cache)


@client_v1_router.get("/features/{feature_id}/sessions")
async def feature_sessions(
    feature_id: str = Path(..., description="Feature ID."),
    limit: int = Query(default=50, ge=1, le=200, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    bypass_cache: bool = Query(default=False, description="Bypass the server-side query cache and fetch fresh data."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[FeatureSessionsDTO]:
    """Return sessions linked to a feature."""
    return await get_feature_sessions_v1(feature_id, limit, offset, request_context, core_ports, bypass_cache=bypass_cache)


@client_v1_router.get("/features/{feature_id}/sessions/page")
async def feature_sessions_page(
    feature_id: str = Path(..., description="Feature ID."),
    limit: int = Query(default=20, ge=1, le=50, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[LinkedFeatureSessionPageDTO]:
    """Return the Phase 2 linked-session page DTO for a feature."""
    return await get_feature_linked_session_page_v1(feature_id, request_context, core_ports, limit=limit, offset=offset)


@client_v1_router.get("/features/{feature_id}/documents")
async def feature_documents(
    feature_id: str = Path(..., description="Feature ID."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[FeatureDocumentsDTO]:
    """Return documents linked to a feature."""
    return await get_feature_documents_v1(feature_id, request_context, core_ports)


@client_v1_router.get("/features/{feature_id}/modal")
async def feature_modal_overview(
    feature_id: str = Path(..., description="Feature ID."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[FeatureModalOverviewDTO]:
    """Return the Phase 2 modal overview payload for a feature."""
    return await get_feature_modal_overview_v1(feature_id, request_context, core_ports)


@client_v1_router.get("/features/{feature_id}/modal/{section}")
async def feature_modal_section(
    feature_id: str = Path(..., description="Feature ID."),
    section: str = Path(..., description="Modal section key."),
    include: list[str] | None = Query(default=None, description="Optional include fields for the requested section."),
    limit: int = Query(default=20, ge=1, le=200, description="Page size for pageable sections."),
    offset: int = Query(default=0, ge=0, description="Page offset for pageable sections."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[FeatureModalSectionDTO]:
    """Return a single Phase 2 modal section/tab payload for a feature."""
    return await get_feature_modal_section_v1(
        feature_id,
        section,
        request_context,
        core_ports,
        include=include,
        limit=limit,
        offset=offset,
    )


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
) -> ClientV1Envelope[SessionSemanticSearchResponse]:
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
) -> ClientV1PaginatedEnvelope[SessionIntelligenceSessionRollup]:
    """Return a paginated list of session intelligence rollups."""
    return await list_sessions_v1(feature_id, root_session_id, limit, offset, request_context, core_ports)


@client_v1_router.get("/sessions/{session_id}")
async def session_detail(
    session_id: str = Path(..., description="Session ID to inspect."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[SessionIntelligenceDetailResponse]:
    """Return detailed intelligence for a single session."""
    return await get_session_detail_v1(session_id, request_context, core_ports)


@client_v1_router.get("/sessions/{session_id}/drilldown")
async def session_drilldown(
    session_id: str = Path(..., description="Session ID."),
    concern: SessionIntelligenceConcern = Query(..., description="Which intelligence concern to inspect."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[SessionIntelligenceDrilldownResponse]:
    """Return drilldown intelligence for a specific concern on a session."""
    return await get_session_drilldown_v1(session_id, concern, request_context, core_ports)


@client_v1_router.get("/sessions/{session_id}/family")
async def session_family(
    session_id: str = Path(..., description="Session ID."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[SessionFamilyDTO]:
    """Return all sessions sharing the same root session."""
    return await get_session_family_v1(session_id, request_context, core_ports)


# Phase 2: transcript-bearing detail endpoint (/sessions/{id}/detail)
@client_v1_router.get("/sessions/{session_id}/detail")
async def session_full_detail(
    session_id: str = Path(..., description="Session ID to inspect."),
    project_id: str | None = Query(
        default=None,
        description=(
            "Required. The project that owns the session. "
            "Missing project_id returns HTTP 400 — there is no active-project fallback."
        ),
    ),
    include: list[str] | None = Query(
        default=None,
        description=(
            "Repeatable include flags: transcript, subagents, tokens, artifacts, links. "
            "Omit to include all segments."
        ),
    ),
    cursor: str | None = Query(
        default=None,
        description="Opaque transcript pagination cursor (base64-encoded offset). Omit to start from the beginning.",
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=1000,
        description="Max transcript items per page (1-1000; default 200).",
    ),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[SessionDetailV1]:
    """Return full session detail bundle (transcript-bearing) for any project.

    ``project_id`` is **required** (HTTP 400 if absent).  Unknown session yields
    HTTP 404.  Optional segments (transcript/subagents/tokens/artifacts/links)
    are selected via the repeatable ``include`` param; omit to include all.
    Redaction is applied by the Phase 1 service before serialisation.
    """
    return await get_session_full_detail_v1(
        session_id,
        project_id,
        include,
        cursor,
        limit,
        request_context,
        core_ports,
    )


# Phase 2: transcript-only paginated endpoint (/sessions/{id}/transcript)
@client_v1_router.get("/sessions/{session_id}/transcript")
async def session_transcript(
    session_id: str = Path(..., description="Session ID."),
    project_id: str | None = Query(
        default=None,
        description=(
            "Required. The project that owns the session. "
            "Missing project_id returns HTTP 400 — there is no active-project fallback."
        ),
    ),
    cursor: str | None = Query(
        default=None,
        description="Opaque pagination cursor (base64-encoded offset). Omit to start from the beginning.",
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=1000,
        description="Max transcript items per page (1-1000; default 200).",
    ),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[SessionTranscriptPageV1]:
    """Return a cursor-paginated transcript page for any project.

    ``project_id`` is **required** (HTTP 400 if absent).  Unknown session yields
    HTTP 404.  Redaction is applied by the Phase 1 service before serialisation.
    Uses ``{items, cursor, limit, nextCursor}`` envelope.
    """
    return await get_session_transcript_page_v1(
        session_id,
        project_id,
        cursor,
        limit,
        request_context,
        core_ports,
    )


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@client_v1_router.post("/reports/aar")
async def generate_aar_report(
    feature_id: str = Query(..., description="Feature ID for the after-action report."),
    bypass_cache: bool = Query(default=False, description="Bypass the server-side query cache and fetch fresh data."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ClientV1Envelope[AARReportDTO]:
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
        bypass_cache=bypass_cache,
    )
    return ClientV1Envelope(
        data=result,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )
