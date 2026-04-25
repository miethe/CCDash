"""Agent-facing REST endpoints backed by transport-neutral query services."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.agent_queries import (
    AARReportDTO,
    FeatureForensicsDTO,
    FeatureForensicsQueryService,
    FeaturePlanningContextDTO,
    PhaseOperationsDTO,
    PlanningAgentSessionBoardDTO,
    PlanningQueryService,
    PlanningSessionQueryService,
    ProjectPlanningGraphDTO,
    ProjectPlanningSummaryDTO,
    ProjectStatusDTO,
    ProjectStatusQueryService,
    ReportingQueryService,
    WorkflowDiagnosticsDTO,
    WorkflowDiagnosticsQueryService,
)
from backend.observability import otel
from backend.request_scope import get_core_ports, get_request_context


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


project_status_query_service = ProjectStatusQueryService()
feature_forensics_query_service = FeatureForensicsQueryService()
workflow_diagnostics_query_service = WorkflowDiagnosticsQueryService()
reporting_query_service = ReportingQueryService()
# PCP-202: planning query surface — one singleton for the whole process lifetime.
planning_query_service = PlanningQueryService()
# PASB-102: planning session board query surface.
planning_session_query_service = PlanningSessionQueryService()


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
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> PlanningAgentSessionBoardDTO:
    """Return a project-wide Kanban board of agent sessions correlated to planning entities."""
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
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> PlanningAgentSessionBoardDTO:
    """Return a feature-scoped Kanban board of agent sessions correlated to planning entities."""
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
        )
        if result.status == "error":
            raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found or project scope could not be resolved.")
        return result
