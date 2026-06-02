"""Agent-facing REST endpoints backed by transport-neutral query services."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, Field

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.agent_queries import (
    AARReportDTO,
    ArtifactRankingsDTO,
    ArtifactRecommendationsDTO,
    ArtifactIntelligenceQueryService,
    FeatureEvidenceSummary,
    FeatureEvidenceSummaryService,
    FeatureForensicsDTO,
    FeatureForensicsQueryService,
    FeaturePlanningContextDTO,
    LiveActiveCountDTO,
    LiveMetricsQueryService,
    PlanningCommandCenterItemDTO,
    PlanningCommandCenterPageDTO,
    PlanningCommandCenterQueryService,
    PhaseOperationsDTO,
    PlanningAgentSessionBoardDTO,
    PlanningNextRunPreviewDTO,
    PlanningQueryService,
    PlanningSessionQueryService,
    PlanningViewBundleDTO,
    ProjectPlanningGraphDTO,
    ProjectPlanningSummaryDTO,
    ProjectStatusDTO,
    ProjectStatusQueryService,
    PromptContextSelection,
    ReportingQueryService,
    SnapshotDiagnosticsDTO,
    WorkflowDiagnosticsDTO,
    WorkflowDiagnosticsQueryService,
)
from backend.application.services.agent_queries.system_metrics import SystemMetricsQueryService
from backend.application.services.agent_queries.multi_project_planning_command_center import (
    MultiProjectPlanningCommandCenterQueryService,
)
from backend.application.services.agent_queries.multi_project_planning_sessions import (
    MultiProjectActiveSessionBoardQueryService,
)
from backend.application.services.agent_queries.planning_next_work import NextWorkQueryService
from backend.models import (
    AggregateWorkItem,
    MultiProjectCommandCenterResponse,
    MultiProjectSessionBoardResponse,
    NextWorkResponse,
    PortfolioRollupResponse,
    SystemActiveCountDTO,
    SystemTokenRollupResponse,
)
from backend.application.services.common import resolve_project_bundle
from backend.observability import otel
from backend.request_scope import get_core_ports, get_request_context
from backend.services.spec_create import create_spec_document


agent_router = APIRouter(prefix="/api/agent", tags=["agent"])


def _require_planning_enabled() -> None:
    if not config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "planning_disabled",
                "message": "Planning control plane is disabled.",
                "hint": "Set CCDASH_PLANNING_CONTROL_PLANE_ENABLED=true to enable.",
            },
        )


def _require_multi_project_command_center_enabled() -> None:
    if not config.CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "multi_project_command_center_disabled",
                "message": "Multi-project planning command center is disabled.",
                "hint": "Set CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true to enable.",
            },
        )


def _require_next_run_preview_enabled() -> None:
    if not config.CCDASH_NEXT_RUN_PREVIEW_ENABLED:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "next_run_preview_disabled",
                "message": "Next-run preview feature is disabled.",
                "hint": "Set CCDASH_NEXT_RUN_PREVIEW_ENABLED=true to enable.",
            },
        )


project_status_query_service = ProjectStatusQueryService()
feature_forensics_query_service = FeatureForensicsQueryService()
feature_evidence_summary_service = FeatureEvidenceSummaryService()
workflow_diagnostics_query_service = WorkflowDiagnosticsQueryService()
reporting_query_service = ReportingQueryService()
artifact_intelligence_query_service = ArtifactIntelligenceQueryService()
# PCP-202: planning query surface — one singleton for the whole process lifetime.
planning_query_service = PlanningQueryService()
# PCC-201/PCC-202: aggregate planning command center query surface.
planning_command_center_query_service = PlanningCommandCenterQueryService()
# PASB-102: planning session board query surface.
planning_session_query_service = PlanningSessionQueryService()
# live-agents-count-v1: live metrics query surface.
live_metrics_query_service = LiveMetricsQueryService()
# system-wide-metrics-v1: system-wide active count surface.
system_metrics_query_service = SystemMetricsQueryService()
# MPCC-204: multi-project aggregate planning command center query surface.
multi_project_command_center_query_service = MultiProjectPlanningCommandCenterQueryService()
# MPCC-304: multi-project aggregate active-session board query surface.
multi_project_session_board_query_service = MultiProjectActiveSessionBoardQueryService()
# P5-004: next-work ranked queue service.
next_work_query_service = NextWorkQueryService()


class AARReportRequest(BaseModel):
    feature_id: str = Field(description="Feature id to generate an after-action report for.")
    bypass_cache: bool = Field(default=False, description="Bypass the server-side query cache and fetch fresh data.")


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


@agent_router.get("/project-status", response_model=ProjectStatusDTO)
async def get_project_status(
    project_id: str | None = Query(default=None, description="Optional project override."),
    bypass_cache: bool = Query(default=False, description="Bypass the server-side query cache and fetch fresh data."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ProjectStatusDTO:
    """Return the current project status snapshot for agent consumers."""
    app_request = await _resolve_app_request(
        request_context,
        core_ports,
        requested_project_id=project_id,
    )
    return await project_status_query_service.get_status(
        app_request.context,
        app_request.ports,
        project_id_override=project_id,
        bypass_cache=bypass_cache,
    )


@agent_router.get("/live/active-count", response_model=LiveActiveCountDTO)
async def get_live_active_count(
    project_id: str | None = Query(default=None, description="Optional project override."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> LiveActiveCountDTO:
    """Return the number of currently active agent sessions for a project.

    Sessions are counted when both conditions hold:
    - ``status = 'active'``
    - ``updated_at >= now() - CCDASH_LIVE_AGENTS_WINDOW_SECONDS`` (default 600 s)

    The freshness window defends against stale-active rows (OQ-3 finding: rows
    with ``status='active'`` up to 93 days old from un-rebounded file watchers).

    When ``project_id`` is omitted the active project is resolved from the
    request context (same as all other agent endpoints).  A project with no
    sessions or no active sessions within the window returns ``{count: 0}``,
    not an error.

    Response fields:
    - ``project_id``: resolved project identifier
    - ``count``: integer count of active sessions
    - ``window_seconds``: freshness window used for the query
    - ``generated_at``: UTC timestamp when this response was produced
    """
    app_request = await _resolve_app_request(
        request_context,
        core_ports,
        requested_project_id=project_id,
    )
    return await live_metrics_query_service.get_active_count(
        app_request.context,
        app_request.ports,
        project_id_override=project_id,
    )


@agent_router.get(
    "/system/active-count",
    response_model=SystemActiveCountDTO,
    summary="System-wide active agent count across all projects",
)
async def get_system_active_count(
    response: Response,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> SystemActiveCountDTO:
    """Return the aggregated live-agent count across **all** known projects.

    Per-project rows include an ``is_stale`` flag (``True`` when
    ``now() - max(sessions.updated_at)`` exceeds
    ``CCDASH_SYSTEM_METRICS_STALE_HORIZON_SECONDS``, default 3600 s) and a
    ``last_synced_at`` timestamp.  Projects with no sessions return
    ``is_stale=null`` (staleness indeterminate, not stale).

    Consumers should poll this endpoint at most once every 30 seconds; the
    response is cached server-side for ``CCDASH_SYSTEM_METRICS_CACHE_TTL_SECONDS``
    (default 30 s).  A ``Cache-Control: max-age=30`` header is set to inform
    intermediate caches and polling clients.

    Response fields:
    - ``total``: sum of active counts across all projects with valid data
    - ``per_project``: list of per-project summaries (count, is_stale, last_synced_at, error)
    - ``window_seconds``: freshness window used for the count query
    - ``generated_at``: UTC timestamp when this response was produced
    - ``status``: ``"ok"`` when all projects succeeded; ``"partial"`` when any errored
    """
    app_request = await _resolve_app_request(request_context, core_ports)
    result = await system_metrics_query_service.get_system_active_count(
        app_request.context,
        app_request.ports,
    )
    response.headers["Cache-Control"] = "max-age=30"
    return result


@agent_router.get("/feature-forensics/{feature_id}", response_model=FeatureForensicsDTO)
async def get_feature_forensics(
    feature_id: str = Path(..., description="Feature id to inspect."),
    bypass_cache: bool = Query(default=False, description="Bypass the server-side query cache and fetch fresh data."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> FeatureForensicsDTO:
    """Return feature execution history and linked delivery evidence."""
    app_request = await _resolve_app_request(request_context, core_ports)
    return await feature_forensics_query_service.get_forensics(
        app_request.context,
        app_request.ports,
        feature_id,
        bypass_cache=bypass_cache,
    )


@agent_router.get("/feature-evidence-summary/{feature_id}", response_model=FeatureEvidenceSummary)
async def get_feature_evidence_summary(
    feature_id: str = Path(..., description="Feature id to summarise."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> FeatureEvidenceSummary:
    """Return a bounded evidence summary for a feature without transcript enrichment."""
    app_request = await _resolve_app_request(request_context, core_ports)
    result = await feature_evidence_summary_service.get_summary(
        app_request.context,
        app_request.ports,
        feature_id,
    )
    if result.status == "error":
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found.")
    return result


@agent_router.get("/workflow-diagnostics", response_model=WorkflowDiagnosticsDTO)
async def get_workflow_diagnostics(
    feature_id: str | None = Query(default=None, description="Optional feature filter."),
    bypass_cache: bool = Query(default=False, description="Bypass the server-side query cache and fetch fresh data."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> WorkflowDiagnosticsDTO:
    """Return workflow effectiveness diagnostics for the current project scope."""
    app_request = await _resolve_app_request(request_context, core_ports)
    return await workflow_diagnostics_query_service.get_diagnostics(
        app_request.context,
        app_request.ports,
        feature_id=feature_id,
        bypass_cache=bypass_cache,
    )


@agent_router.get("/artifact-intelligence/snapshot-diagnostics", response_model=SnapshotDiagnosticsDTO)
async def get_artifact_snapshot_diagnostics(
    project_id: str | None = Query(default=None, description="Optional project override."),
    bypass_cache: bool = Query(default=False, description="Reserved for parity with cached agent queries."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> SnapshotDiagnosticsDTO:
    """Return SkillMeat artifact snapshot diagnostics for the current project scope."""
    app_request = await _resolve_app_request(
        request_context,
        core_ports,
        requested_project_id=project_id,
    )
    return await artifact_intelligence_query_service.get_snapshot_diagnostics(
        app_request.context,
        app_request.ports,
        project_id_override=project_id,
        bypass_cache=bypass_cache,
    )


@agent_router.get("/artifact-intelligence/rankings", response_model=ArtifactRankingsDTO)
async def get_artifact_rankings(
    project_id: str | None = Query(default=None, description="Optional project override."),
    period: str = Query(default="30d", description="Ranking period."),
    collection_id: str | None = Query(default=None, description="Collection id filter."),
    user_scope: str | None = Query(default=None, description="User scope filter."),
    artifact_uuid: str | None = Query(default=None, description="Artifact UUID filter."),
    artifact_id: str | None = Query(default=None, description="Observed artifact id filter."),
    version_id: str | None = Query(default=None, description="Version id filter."),
    workflow_id: str | None = Query(default=None, description="Workflow id filter."),
    artifact_type: str | None = Query(default=None, description="Artifact type filter."),
    recommendation_type: str | None = Query(default=None, description="Recommendation type filter."),
    limit: int = Query(default=25, ge=1, le=100),
    bypass_cache: bool = Query(default=False, description="Reserved for parity with cached agent queries."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ArtifactRankingsDTO:
    """Return artifact ranking rows for agent consumers."""
    app_request = await _resolve_app_request(
        request_context,
        core_ports,
        requested_project_id=project_id,
    )
    return await artifact_intelligence_query_service.get_rankings(
        app_request.context,
        app_request.ports,
        project_id_override=project_id,
        period=period,
        collection_id=collection_id,
        user_scope=user_scope,
        artifact_uuid=artifact_uuid,
        artifact_id=artifact_id,
        version_id=version_id,
        workflow_id=workflow_id,
        artifact_type=artifact_type,
        recommendation_type=recommendation_type,
        limit=limit,
        bypass_cache=bypass_cache,
    )


@agent_router.get("/artifact-intelligence/recommendations", response_model=ArtifactRecommendationsDTO)
async def get_artifact_recommendations(
    project_id: str | None = Query(default=None, description="Optional project override."),
    period: str = Query(default="30d", description="Ranking period."),
    collection_id: str | None = Query(default=None, description="Collection id filter."),
    user_scope: str | None = Query(default=None, description="User scope filter."),
    workflow_id: str | None = Query(default=None, description="Workflow id filter."),
    recommendation_type: str | None = Query(default=None, description="Recommendation type filter."),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=100, ge=1, le=500),
    bypass_cache: bool = Query(default=False, description="Reserved for parity with cached agent queries."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ArtifactRecommendationsDTO:
    """Return advisory artifact recommendations for agent consumers."""
    app_request = await _resolve_app_request(
        request_context,
        core_ports,
        requested_project_id=project_id,
    )
    return await artifact_intelligence_query_service.get_recommendations(
        app_request.context,
        app_request.ports,
        project_id_override=project_id,
        period=period,
        collection_id=collection_id,
        user_scope=user_scope,
        workflow_id=workflow_id,
        recommendation_type=recommendation_type,
        min_confidence=min_confidence,
        limit=limit,
        bypass_cache=bypass_cache,
    )


@agent_router.post("/reports/aar", response_model=AARReportDTO)
async def generate_aar_report(
    req: AARReportRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> AARReportDTO:
    """Generate a deterministic after-action report for a feature."""
    app_request = await _resolve_app_request(request_context, core_ports)
    return await reporting_query_service.generate_aar(
        app_request.context,
        app_request.ports,
        req.feature_id,
        bypass_cache=req.bypass_cache,
    )


# ── Planning endpoints (PCP-202) ─────────────────────────────────────────────
# All four handlers are intentionally thin: resolve the app request, delegate
# to the PlanningQueryService singleton, and return the DTO unchanged.
# 404 semantics: the service signals a missing entity via status="error" with
# an empty primary field (feature_id/phase_number present but entity not found).
# We check for that condition and raise HTTPException(404) here so REST clients
# get the correct status code — the service itself stays transport-neutral.


@agent_router.get(
    "/planning/summary",
    response_model=ProjectPlanningSummaryDTO,
    dependencies=[Depends(_require_planning_enabled)],
)
async def get_planning_summary(
    project_id: str | None = Query(default=None, description="Optional project override."),
    active_first: bool = Query(default=True, description="Sort active/planned planning work before lower-priority items."),
    include_terminal: bool = Query(default=False, description="Include terminal feature statuses in the summary list."),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum feature summaries to return."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ProjectPlanningSummaryDTO:
    """Return project-level planning health counts and per-feature summaries."""
    with otel.start_span("planning.summary", {"project_id": project_id or ""}):
        app_request = await _resolve_app_request(
            request_context,
            core_ports,
            requested_project_id=project_id,
        )
        return await planning_query_service.get_project_planning_summary(
            app_request.context,
            app_request.ports,
            project_id_override=project_id,
            active_first=active_first,
            include_terminal=include_terminal,
            limit=limit,
        )


@agent_router.get(
    "/planning/graph",
    response_model=ProjectPlanningGraphDTO,
    dependencies=[Depends(_require_planning_enabled)],
)
async def get_planning_graph(
    project_id: str | None = Query(default=None, description="Optional project override."),
    feature_id: str | None = Query(default=None, description="Scope graph to a single feature."),
    depth: int | None = Query(default=None, ge=1, description="Reserved: future depth-limited traversal."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> ProjectPlanningGraphDTO:
    """Return aggregated planning graph nodes and edges for the project or a feature seed."""
    with otel.start_span("planning.graph", {"project_id": project_id or "", "feature_id": feature_id or ""}):
        app_request = await _resolve_app_request(
            request_context,
            core_ports,
            requested_project_id=project_id,
        )
        result = await planning_query_service.get_project_planning_graph(
            app_request.context,
            app_request.ports,
            project_id_override=project_id,
            feature_id=feature_id,
            depth=depth,
        )
        # The service returns status="error" when a requested feature_id is not found.
        if result.status == "error" and feature_id and not result.nodes:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found in planning graph.")
        return result


@agent_router.get(
    "/planning/command-center",
    response_model=PlanningCommandCenterPageDTO,
    dependencies=[Depends(_require_planning_enabled)],
)
async def get_planning_command_center(
    project_id: str | None = Query(default=None, description="Optional project override."),
    q: str | None = Query(default=None, description="Search text across feature, command, and artifact paths."),
    status: str | None = Query(default=None, description="Raw or effective planning status filter."),
    phase: int | None = Query(default=None, ge=1, description="Current or next phase number filter."),
    artifact_type: str | None = Query(default=None, description="Required linked artifact type."),
    worktree_state: str | None = Query(default=None, description="Stored worktree context status filter."),
    pr_state: str | None = Query(default=None, description="Pull request state filter."),
    launch_readiness: str | None = Query(default=None, description="Launch batch readiness filter."),
    sort_by: str = Query(default="last_activity", description="Sort key."),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$", description="Sort direction."),
    page: int = Query(default=1, ge=1, description="1-based page number."),
    page_size: int = Query(default=50, ge=1, le=200, description="Page size."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> PlanningCommandCenterPageDTO:
    """Return enriched planning work items for the project command center."""
    with otel.start_span("planning.command_center", {"project_id": project_id or ""}):
        app_request = await _resolve_app_request(
            request_context,
            core_ports,
            requested_project_id=project_id,
        )
        return await planning_command_center_query_service.get_command_center(
            app_request.context,
            app_request.ports,
            project_id_override=project_id,
            q=q,
            status=status,
            phase=phase,
            artifact_type=artifact_type,
            worktree_state=worktree_state,
            pr_state=pr_state,
            launch_readiness=launch_readiness,
            sort_by=sort_by,
            sort_direction=sort_direction,
            page=page,
            page_size=page_size,
        )


@agent_router.get(
    "/planning/command-center/{feature_id}",
    response_model=PlanningCommandCenterItemDTO,
    dependencies=[Depends(_require_planning_enabled)],
)
async def get_planning_command_center_item(
    feature_id: str = Path(..., description="Feature id to inspect."),
    project_id: str | None = Query(default=None, description="Optional project override."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> PlanningCommandCenterItemDTO:
    """Return one enriched command-center row without loading the whole UI list."""
    with otel.start_span("planning.command_center.item", {"feature_id": feature_id, "project_id": project_id or ""}):
        app_request = await _resolve_app_request(
            request_context,
            core_ports,
            requested_project_id=project_id,
        )
        result = await planning_command_center_query_service.get_command_center_item(
            app_request.context,
            app_request.ports,
            feature_id=feature_id,
            project_id_override=project_id,
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found in planning command center.")
        return result


@agent_router.get(
    "/planning/features/{feature_id}",
    response_model=FeaturePlanningContextDTO,
    dependencies=[Depends(_require_planning_enabled)],
)
async def get_feature_planning_context(
    feature_id: str = Path(..., description="Feature id to inspect."),
    project_id: str | None = Query(default=None, description="Optional project override."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> FeaturePlanningContextDTO:
    """Return one feature's planning subgraph, status provenance, and per-phase context."""
    with otel.start_span("planning.feature_context", {"feature_id": feature_id}):
        app_request = await _resolve_app_request(
            request_context,
            core_ports,
            requested_project_id=project_id,
        )
        result = await planning_query_service.get_feature_planning_context(
            app_request.context,
            app_request.ports,
            feature_id=feature_id,
            project_id_override=project_id,
        )
        if result.status == "error" and not result.feature_name:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found.")
        return result


@agent_router.get(
    "/planning/features/{feature_id}/phases/{phase_number}",
    response_model=PhaseOperationsDTO,
    dependencies=[Depends(_require_planning_enabled)],
)
async def get_phase_operations(
    feature_id: str = Path(..., description="Feature id containing the target phase."),
    phase_number: int = Path(..., ge=1, description="1-based phase number to inspect."),
    project_id: str | None = Query(default=None, description="Optional project override."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> PhaseOperationsDTO:
    """Return operational detail — batch readiness, tasks, and dependency state — for a single phase."""
    with otel.start_span(
        "planning.phase_operations",
        {"feature_id": feature_id, "phase_number": phase_number},
    ):
        app_request = await _resolve_app_request(
            request_context,
            core_ports,
            requested_project_id=project_id,
        )
        result = await planning_query_service.get_phase_operations(
            app_request.context,
            app_request.ports,
            feature_id=feature_id,
            phase_number=phase_number,
            project_id_override=project_id,
        )
        # status="error" covers both missing feature and missing phase; no phase_token
        # confirms the phase was not located (a found phase always has a non-empty token).
        if result.status == "error" and not result.phase_token:
            detail = (
                f"Phase {phase_number} not found for feature '{feature_id}'."
                if result.feature_id
                else f"Feature '{feature_id}' not found."
            )
            raise HTTPException(status_code=404, detail=detail)
        return result


# ── Planning session board endpoints (PASB-103) ──────────────────────────────
# Project-wide and feature-scoped Kanban board of agent sessions correlated to
# planning entities.  Both handlers are thin: resolve the app request, delegate
# to the PlanningSessionQueryService singleton, and return the DTO unchanged.
# status="error" from the service means the project scope could not be resolved;
# we surface that as a 404 rather than a 500 so REST clients get the right code.


@agent_router.get(
    "/planning/session-board",
    response_model=PlanningAgentSessionBoardDTO,
    dependencies=[Depends(_require_planning_enabled)],
)
async def get_planning_session_board(
    project_id: str | None = Query(default=None, description="Optional project override."),
    grouping: str = Query(
        default="state",
        description="Board grouping mode: one of 'state', 'feature', 'phase', 'agent', 'model'.",
    ),
    cursor: str | None = Query(
        default=None,
        description=(
            "Opaque pagination cursor returned as next_cursor in a prior response. "
            "Omit to fetch the first page."
        ),
    ),
    limit: int = Query(
        default=500,
        ge=1,
        le=1000,
        description=(
            "Maximum number of sessions per page. "
            "Defaults to 500 for backward compatibility. "
            "Use a smaller value (e.g. 50–100) for faster initial loads."
        ),
    ),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> PlanningAgentSessionBoardDTO:
    """Return a project-wide Kanban board of agent sessions correlated to planning entities.

    Supports cursor-based pagination via ``cursor`` + ``limit`` query params (T4-001).
    Omitting both params preserves the legacy single-page behavior (limit=500).
    """
    with otel.start_span("planning.session_board", {"project_id": project_id or "", "grouping": grouping}):
        app_request = await _resolve_app_request(
            request_context,
            core_ports,
            requested_project_id=project_id,
        )
        result = await planning_session_query_service.get_session_board(
            app_request.context,
            app_request.ports,
            project_id=project_id,
            grouping=grouping,
            cursor=cursor,
            limit=limit,
        )
        if result.status == "error":
            raise HTTPException(status_code=404, detail="Project scope could not be resolved.")
        return result


@agent_router.get(
    "/planning/session-board/{feature_id}",
    response_model=PlanningAgentSessionBoardDTO,
    dependencies=[Depends(_require_planning_enabled)],
)
async def get_planning_session_board_for_feature(
    feature_id: str = Path(..., description="Feature id to scope the session board to."),
    project_id: str | None = Query(default=None, description="Optional project override."),
    grouping: str = Query(
        default="state",
        description="Board grouping mode: one of 'state', 'feature', 'phase', 'agent', 'model'.",
    ),
    cursor: str | None = Query(
        default=None,
        description=(
            "Opaque pagination cursor returned as next_cursor in a prior response. "
            "Omit to fetch the first page."
        ),
    ),
    limit: int = Query(
        default=500,
        ge=1,
        le=1000,
        description=(
            "Maximum number of sessions per page. "
            "Defaults to 500 for backward compatibility. "
            "Use a smaller value (e.g. 50–100) for faster initial loads."
        ),
    ),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> PlanningAgentSessionBoardDTO:
    """Return a feature-scoped Kanban board of agent sessions correlated to planning entities.

    Supports cursor-based pagination via ``cursor`` + ``limit`` query params (T4-001).
    Omitting both params preserves the legacy single-page behavior (limit=500).
    """
    with otel.start_span(
        "planning.session_board_feature",
        {"feature_id": feature_id, "project_id": project_id or "", "grouping": grouping},
    ):
        app_request = await _resolve_app_request(
            request_context,
            core_ports,
            requested_project_id=project_id,
        )
        result = await planning_session_query_service.get_session_board(
            app_request.context,
            app_request.ports,
            project_id=project_id,
            feature_id=feature_id,
            grouping=grouping,
            cursor=cursor,
            limit=limit,
        )
        if result.status == "error":
            raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found or project scope could not be resolved.")
        return result


# ── Planning view bundle (T5-003) ────────────────────────────────────────────
# Fat-read bundle for the Planning above-fold view.  Always includes the project
# planning summary; optional sub-payloads (graph, session_board) are included
# when present in the ``include=`` query parameter.


@agent_router.get(
    "/planning/view",
    response_model=PlanningViewBundleDTO,
    dependencies=[Depends(_require_planning_enabled)],
)
async def get_planning_view_bundle(
    project_id: str | None = Query(default=None, description="Optional project override."),
    include: list[str] | None = Query(
        default=None,
        description="Optional sub-payloads to include: 'graph', 'session_board'.",
    ),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> PlanningViewBundleDTO:
    """Return the Planning view fat-read bundle.

    Always returns the project planning summary.  Include ``?include=graph`` and/or
    ``?include=session_board`` to add those optional sub-payloads.  Absent sub-payloads
    are ``null`` in the response — the FE should request them lazily when needed.
    """
    with otel.start_span(
        "ccdash.planning.view.bundle",
        {"project_id": project_id or "", "include": ",".join(include or [])},
    ):
        app_request = await _resolve_app_request(
            request_context,
            core_ports,
            requested_project_id=project_id,
        )
        result = await planning_query_service.get_planning_view_bundle(
            app_request.context,
            app_request.ports,
            project_id_override=project_id,
            include=include or [],
        )
        if result.status == "error":
            raise HTTPException(
                status_code=404,
                detail="Project scope could not be resolved.",
            )
        return result


# ── Next-run preview (PASB-401) ───────────────────────────────────────────────


@agent_router.get(
    "/planning/next-run-preview/{feature_id}",
    response_model=PlanningNextRunPreviewDTO,
    dependencies=[Depends(_require_planning_enabled), Depends(_require_next_run_preview_enabled)],
)
async def get_planning_next_run_preview(
    feature_id: str = Path(..., description="Feature id to generate the next-run preview for."),
    phase_number: int | None = Query(default=None, description="Optional phase number to scope the preview to."),
    project_id: str | None = Query(default=None, description="Optional project override."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> PlanningNextRunPreviewDTO:
    """Return a next-run CLI command and prompt skeleton for the given feature/phase.

    The response includes a copyable ``command`` string and a ``prompt_skeleton``
    template with ``{{placeholder}}`` tokens showing what context would be
    injected.  ``warnings`` surfaces missing context, stale data, or blocked
    predecessors that may affect run quality.
    """
    with otel.start_span(
        "planning.next_run_preview",
        {"feature_id": feature_id, "project_id": project_id or "", "phase_number": str(phase_number or "")},
    ):
        app_request = await _resolve_app_request(
            request_context,
            core_ports,
            requested_project_id=project_id,
        )
        result = await planning_query_service.get_next_run_preview(
            app_request.context,
            app_request.ports,
            feature_id=feature_id,
            phase_number=phase_number,
            project_id_override=project_id,
        )
        if result.status == "error":
            raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found or project scope could not be resolved.")
        return result


@agent_router.post(
    "/planning/next-run-preview/{feature_id}",
    response_model=PlanningNextRunPreviewDTO,
    dependencies=[Depends(_require_planning_enabled), Depends(_require_next_run_preview_enabled)],
)
async def post_planning_next_run_preview(
    context_selection: PromptContextSelection,
    feature_id: str = Path(..., description="Feature id to generate the next-run preview for."),
    phase_number: int | None = Query(default=None, description="Optional phase number to scope the preview to."),
    project_id: str | None = Query(default=None, description="Optional project override."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> PlanningNextRunPreviewDTO:
    """Return a next-run CLI command and prompt skeleton with explicit context selection.

    Accepts a ``PromptContextSelection`` body so the caller can inject specific
    session IDs, phase refs, task refs, and artifact refs into the composed prompt.
    The GET variant is for simple, unselected previews; this POST variant drives
    the full interactive context-composer flow.

    The response includes a copyable ``command`` string and a ``prompt_skeleton``
    template populated with the provided context references.  ``warnings`` surfaces
    missing context, stale data, or blocked predecessors.
    """
    with otel.start_span(
        "planning.next_run_preview.post",
        {"feature_id": feature_id, "project_id": project_id or "", "phase_number": str(phase_number or "")},
    ):
        app_request = await _resolve_app_request(
            request_context,
            core_ports,
            requested_project_id=project_id,
        )
        result = await planning_query_service.get_next_run_preview(
            app_request.context,
            app_request.ports,
            feature_id=feature_id,
            phase_number=phase_number,
            context_selection=context_selection,
            project_id_override=project_id,
        )
        if result.status == "error":
            raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found or project scope could not be resolved.")
        return result


# ── Multi-project planning command center (MPCC-204) ─────────────────────────
# Aggregate cross-project work-item surface.  Both handlers are thin: resolve
# the app request, delegate to MultiProjectPlanningCommandCenterQueryService,
# and return the DTO unchanged.  Flag-off behaviour matches the next-run preview
# convention: 404 with a disabled-payload so REST clients get the right code.


@agent_router.get(
    "/planning/multi-project/command-center",
    response_model=MultiProjectCommandCenterResponse,
    dependencies=[Depends(_require_multi_project_command_center_enabled)],
)
async def get_multi_project_command_center(
    q: str | None = Query(default=None, description="Search text across feature, command, and artifact paths."),
    status: str | None = Query(default=None, description="Raw or effective planning status filter."),
    phase: int | None = Query(default=None, ge=1, description="Current or next phase number filter."),
    artifact_type: str | None = Query(default=None, description="Required linked artifact type."),
    worktree_state: str | None = Query(default=None, description="Stored worktree context status filter."),
    pr_state: str | None = Query(default=None, description="Pull request state filter."),
    launch_readiness: str | None = Query(default=None, description="Launch batch readiness filter."),
    sort_by: str = Query(default="last_activity", description="Sort key."),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$", description="Sort direction."),
    page: int = Query(default=1, ge=1, description="1-based page number."),
    page_size: int = Query(default=50, ge=1, le=200, description="Page size."),
    project_ids: list[str] | None = Query(default=None, description="Optional project id allowlist; omit to include all."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> MultiProjectCommandCenterResponse:
    """Return enriched aggregate planning work items spanning all registered projects."""
    with otel.start_span("planning.multi_project_command_center", {}):
        app_request = await _resolve_app_request(request_context, core_ports)
        return await multi_project_command_center_query_service.get_multi_project_command_center(
            app_request.context,
            app_request.ports,
            q=q,
            status=status,
            phase=phase,
            artifact_type=artifact_type,
            worktree_state=worktree_state,
            pr_state=pr_state,
            launch_readiness=launch_readiness,
            sort_by=sort_by,
            sort_direction=sort_direction,
            page=page,
            page_size=page_size,
            project_ids=project_ids,
        )


@agent_router.get(
    "/planning/multi-project/command-center/item/{feature_id}",
    response_model=AggregateWorkItem,
    dependencies=[Depends(_require_multi_project_command_center_enabled)],
)
async def get_multi_project_command_center_item(
    feature_id: str = Path(..., description="Feature id to inspect."),
    project_id: str | None = Query(default=None, description="Optional project scope — limits search to one project."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> AggregateWorkItem:
    """Return one enriched aggregate work item by feature id without loading the full list."""
    with otel.start_span(
        "planning.multi_project_command_center.item",
        {"feature_id": feature_id, "project_id": project_id or ""},
    ):
        app_request = await _resolve_app_request(request_context, core_ports)
        result = await multi_project_command_center_query_service.get_multi_project_item(
            app_request.context,
            app_request.ports,
            feature_id=feature_id,
            project_id=project_id,
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found in any registered project.")
        return result


# ── Multi-project active-session board (MPCC-304) ────────────────────────────
# Aggregate cross-project session-board surface.  The handler is thin: resolve
# the app request, delegate to MultiProjectActiveSessionBoardQueryService, and
# return the DTO unchanged.  Flag-off behaviour matches the Phase 2 convention:
# 404 with a disabled-payload.  The same gate (_require_multi_project_command_center_enabled)
# covers both surfaces — session board is a sub-feature of the MPCC flag.


@agent_router.get(
    "/planning/multi-project/session-board",
    response_model=MultiProjectSessionBoardResponse,
    dependencies=[Depends(_require_multi_project_command_center_enabled)],
)
async def get_multi_project_session_board(
    group_by: str = Query(default="state", description="Grouping dimension: state | feature | phase | agent | model | project."),
    project_ids: list[str] | None = Query(default=None, description="Optional project id allowlist; omit to include all."),
    group_filter: str | None = Query(default=None, description="Only include cards whose group_key matches this value."),
    feature_id: str | None = Query(default=None, description="Only include cards correlated to this feature."),
    state_filter: str | None = Query(default=None, description="Only include cards in this state (e.g. 'running')."),
    window_seconds: int | None = Query(default=None, ge=1, description="Active-session freshness window in seconds; overrides server default."),
    include_workers: bool = Query(default=True, description="When false, worker sessions are omitted from all groups."),
    page: int = Query(default=1, ge=1, description="1-based page number."),
    page_size: int = Query(default=50, ge=1, le=200, description="Page size."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> MultiProjectSessionBoardResponse:
    """Return active-session cards grouped across all registered projects."""
    with otel.start_span("planning.multi_project_session_board", {}):
        app_request = await _resolve_app_request(request_context, core_ports)
        return await multi_project_session_board_query_service.get_multi_project_session_board(
            app_request.context,
            app_request.ports,
            group_by=group_by,
            project_ids=project_ids,
            group_filter=group_filter,
            feature_id=feature_id,
            state_filter=state_filter,
            window_seconds=window_seconds,
            include_workers=include_workers,
            page=page,
            page_size=page_size,
        )


# ── P5-003a: Portfolio rollup ─────────────────────────────────────────────────

@agent_router.get(
    "/planning/portfolio/rollup",
    response_model=PortfolioRollupResponse,
    dependencies=[Depends(_require_multi_project_command_center_enabled)],
)
async def get_planning_portfolio_rollup(
    project_ids: list[str] | None = Query(
        default=None,
        description="Optional project id allowlist; omit to include all.",
    ),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> PortfolioRollupResponse:
    """Return a lightweight portfolio rollup across all registered projects (§7.1)."""
    with otel.start_span("planning.portfolio_rollup", {}):
        app_request = await _resolve_app_request(request_context, core_ports)
        return await multi_project_command_center_query_service.get_portfolio_rollup(
            app_request.context,
            app_request.ports,
            project_ids=project_ids,
        )


# ── P5-003b: System token rollup ─────────────────────────────────────────────

@agent_router.get(
    "/system/token-rollup",
    response_model=SystemTokenRollupResponse,
)
async def get_system_token_rollup(
    project_ids: list[str] | None = Query(
        default=None,
        description="Optional project id allowlist; omit to include all.",
    ),
    period: str = Query(
        default="daily",
        description="Aggregation period label (daily, weekly, all-time). Stored in response.",
    ),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> SystemTokenRollupResponse:
    """Return cross-project token and cost aggregates (§7.3)."""
    with otel.start_span("system_metrics.token_rollup", {}):
        app_request = await _resolve_app_request(request_context, core_ports)
        return await system_metrics_query_service.get_system_token_rollup(
            app_request.context,
            app_request.ports,
            project_ids=project_ids,
            period=period,
        )


# ── P5-004: Next-work ranked queue ────────────────────────────────────────────

@agent_router.get(
    "/planning/next-work",
    response_model=NextWorkResponse,
    dependencies=[Depends(_require_planning_enabled)],
)
async def get_planning_next_work(
    project_ids: list[str] | None = Query(
        default=None,
        description="Optional project id allowlist; omit to include all.",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum items per page.",
    ),
    cursor: str | None = Query(
        default=None,
        description="Opaque pagination cursor from a previous response's next_cursor.",
    ),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> NextWorkResponse:
    """Return a ranked, cursor-paginated list of ready-to-work features (§7.2)."""
    with otel.start_span("planning.next_work", {}):
        app_request = await _resolve_app_request(request_context, core_ports)
        return await next_work_query_service.get_next_work(
            app_request.context,
            app_request.ports,
            project_ids=project_ids,
            limit=limit,
            cursor=cursor,
        )


# ── P5-010: New Spec creation endpoint ───────────────────────────────────────


class SpecCreateRequest(BaseModel):
    """Request body for POST /api/agent/planning/specs."""

    title: str = Field(
        description="Human-readable spec title (1–200 chars).",
        min_length=1,
        max_length=200,
    )
    docType: str = Field(
        default="design-spec",
        description="Frontmatter doc_type value (lower-kebab-case).",
    )
    projectId: str | None = Field(
        default=None,
        description="Target project id. Defaults to the active project.",
    )


class SpecCreateResponse(BaseModel):
    """Response body for POST /api/agent/planning/specs."""

    id: str = Field(description="DOC-<slug> identifier the sync engine will assign.")
    path: str = Field(description="Relative path from the project plan-docs root.")
    status: str = Field(description="Always 'created' on success.")


@agent_router.post(
    "/planning/specs",
    response_model=SpecCreateResponse,
    status_code=201,
    dependencies=[Depends(_require_planning_enabled)],
)
async def post_planning_spec_create(
    body: SpecCreateRequest,
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> SpecCreateResponse:
    """Scaffold a new spec document under the project plan-docs directory.

    Writes a markdown file with YAML frontmatter (schema_version: 2,
    doc_type, title, status: draft) and a minimal body stub.  The filename
    is derived from a slugified title + short UID suffix to avoid collisions.

    The returned ``id`` matches what the sync engine will assign (DOC-<slug>).
    The new file is picked up by the next background sync cycle; for immediate
    visibility call the cache-invalidation endpoint.

    Returns 422 if the project has no resolvable plan-docs directory or if
    the request body is invalid.  Returns 400 if the write fails for any
    other input reason.
    """
    with otel.start_span(
        "planning.spec_create",
        {"project_id": body.projectId or "", "doc_type": body.docType},
    ):
        # Resolve the target project bundle (includes plan_docs path).
        bundle = resolve_project_bundle(
            request_context,
            core_ports,
            requested_project_id=body.projectId,
        )
        if bundle is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "no_active_project",
                    "message": "No active project found and no projectId supplied.",
                },
            )

        plan_docs_path = bundle.paths.plan_docs.path
        if not plan_docs_path or not str(plan_docs_path).strip():
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "no_plan_docs_path",
                    "message": (
                        f"Project '{bundle.project.id}' has no resolvable plan-docs "
                        "directory.  Configure planDocsPath in project settings."
                    ),
                },
            )

        try:
            result = create_spec_document(
                plan_docs_dir=plan_docs_path,
                title=body.title,
                doc_type=body.docType,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": "invalid_input", "message": str(exc)}) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "write_failed",
                    "message": f"Could not write spec file: {exc}",
                },
            ) from exc

        return SpecCreateResponse(
            id=result["id"],
            path=result["path"],
            status=result["status"],
        )
