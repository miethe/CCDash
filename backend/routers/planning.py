"""Planning writeback REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend import config
from backend.application.context import RequestContext
from backend.application.live_updates.domain_events import publish_planning_invalidation
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.agent_queries import (
    OpenQuestionResolutionDTO,
    PlanningQueryService,
)
from backend.request_scope import get_core_ports, get_request_context


planning_router = APIRouter(prefix="/api/planning", tags=["planning"])
planning_query_service = PlanningQueryService()


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


class ResolveOpenQuestionRequest(BaseModel):
    answer: str = Field(description="Resolution text for the target open question.")


@planning_router.patch(
    "/features/{feature_id}/open-questions/{oq_id}",
    response_model=OpenQuestionResolutionDTO,
    dependencies=[Depends(_require_planning_enabled)],
)
async def resolve_open_question(
    req: ResolveOpenQuestionRequest,
    feature_id: str = Path(..., description="Feature id containing the target open question."),
    oq_id: str = Path(..., description="Open-question identifier."),
    request_context: RequestContext = Depends(get_request_context),
    core_ports: CorePorts = Depends(get_core_ports),
) -> JSONResponse:
    app_request = await _resolve_app_request(request_context, core_ports)
    try:
        result = await planning_query_service.resolve_open_question(
            app_request.context,
            app_request.ports,
            feature_id=feature_id,
            oq_id=oq_id,
            answer_text=req.answer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if app_request.context.project is not None:
        await publish_planning_invalidation(
            app_request.context.project.project_id,
            feature_id=feature_id,
            reason="open_question_resolved",
            source="planning.resolve_open_question",
            payload={
                "oqId": result.oq.oq_id,
                "pendingSync": result.oq.pending_sync,
            },
        )

    return JSONResponse(
        status_code=202 if result.oq.pending_sync else 200,
        content=result.model_dump(mode="json"),
    )
