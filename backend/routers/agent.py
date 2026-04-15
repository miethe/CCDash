"""Agent-facing REST endpoints backed by transport-neutral query services."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.agent_queries import (
    AARReportDTO,
    FeatureForensicsDTO,
    FeatureForensicsQueryService,
    ProjectStatusDTO,
    ProjectStatusQueryService,
    ReportingQueryService,
    WorkflowDiagnosticsDTO,
    WorkflowDiagnosticsQueryService,
)
from backend.request_scope import get_core_ports, get_request_context


agent_router = APIRouter(prefix="/api/agent", tags=["agent"])
project_status_query_service = ProjectStatusQueryService()
feature_forensics_query_service = FeatureForensicsQueryService()
workflow_diagnostics_query_service = WorkflowDiagnosticsQueryService()
reporting_query_service = ReportingQueryService()


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
