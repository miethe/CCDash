"""Project status and workflow failure handler functions for the v1 client router.

These are plain async functions (not a router) intended to be registered on
``client_v1_router`` by the router module that imports them.
"""
from __future__ import annotations

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.agent_queries import (
    ProjectStatusDTO,
    ProjectStatusQueryService,
    WorkflowDiagnosticsDTO,
    WorkflowDiagnosticsQueryService,
)
from backend.routers.client_v1_models import ClientV1Envelope, ClientV1Meta

# ---------------------------------------------------------------------------
# Module-level service singletons (stateless; safe to share across requests)
# ---------------------------------------------------------------------------

project_status_query_service = ProjectStatusQueryService()
workflow_diagnostics_query_service = WorkflowDiagnosticsQueryService()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_instance_id() -> str:
    """Return a stable instance identifier, falling back to a default label."""
    return getattr(config, "INSTANCE_ID", "") or "ccdash-local"


async def _resolve_app_request(
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    requested_project_id: str | None = None,
):
    """Resolve an application request using the shared transport-neutral helper."""
    return await resolve_application_request(
        request_context,
        core_ports,
        core_ports.storage.db,
        requested_project_id=requested_project_id,
    )


# ---------------------------------------------------------------------------
# Handler functions
# ---------------------------------------------------------------------------


async def get_project_status_v1(
    project_id: str | None,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[ProjectStatusDTO]:
    """Return the current project status snapshot wrapped in a v1 envelope.

    Delegates to :class:`ProjectStatusQueryService` using the same resolution
    pattern as the agent REST router.
    """
    app_request = await _resolve_app_request(
        request_context,
        core_ports,
        requested_project_id=project_id,
    )
    result: ProjectStatusDTO = await project_status_query_service.get_status(
        app_request.context,
        app_request.ports,
        project_id_override=project_id,
    )
    return ClientV1Envelope(
        data=result,
        meta=ClientV1Meta(instance_id=_get_instance_id()),
    )


async def get_workflow_failures_v1(
    feature_id: str | None,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[WorkflowDiagnosticsDTO]:
    """Return workflow diagnostics (failure patterns) wrapped in a v1 envelope.

    Delegates to :class:`WorkflowDiagnosticsQueryService` using the same
    resolution pattern as the agent REST router.
    """
    app_request = await _resolve_app_request(request_context, core_ports)
    result: WorkflowDiagnosticsDTO = await workflow_diagnostics_query_service.get_diagnostics(
        app_request.context,
        app_request.ports,
        feature_id=feature_id,
    )
    return ClientV1Envelope(
        data=result,
        meta=ClientV1Meta(instance_id=_get_instance_id()),
    )
