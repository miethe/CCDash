"""AI router — POST /api/ai/insight proxies to Gemini server-side.

The Gemini API key is never exposed to the browser bundle. When the key
is unset the endpoint returns a 200 with ``disabled: true`` so the FE
can degrade gracefully without triggering error states.

Auth: this router is gated by ``require_v1_auth`` — the SAME single
identity-resolution dependency that gates every ``/api/v1`` route (ADR-008).
Without it the endpoint was an unauthenticated LLM proxy funded by
CCDASH_GEMINI_API_KEY on any non-loopback deployment, with caller-controlled
prompt content. Behaviour matches /api/v1 exactly: no-op when
CCDASH_API_TOKEN is unset (local-trust default), 401 on a missing bearer and
403 on a wrong one once it is set.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from backend.application.ports import CorePorts
from backend.routers._client_v1_auth import require_v1_auth
from backend.services.ai_insight import generate_dashboard_insight

logger = logging.getLogger(__name__)

# ADR-008: identity resolution lives in ONE place — replace require_v1_auth to
# upgrade the auth model; no handler body here needs to change.
ai_router = APIRouter(
    prefix="/api/ai",
    tags=["ai"],
    dependencies=[Depends(require_v1_auth)],
)


class AIInsightRequest(BaseModel):
    """Input payload for the AI insight endpoint.

    ``project_id`` names the project whose data this payload summarises. It
    exists so this lane can honour ``projects.llm_egress_consent`` -- the
    per-project half of the two-level egress consent gate -- exactly as the
    session-naming sweep does. It is Optional in the SCHEMA only so an older
    client is rejected by the CONSENT GATE rather than by a 422: absent means
    "no project consented", which fails closed. It is not an optional
    behaviour.
    """

    metrics: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    project_id: str | None = Field(
        default=None,
        description=(
            "Project whose data this payload summarises; its "
            "llm_egress_consent is required for egress. Absent => refused."
        ),
    )


class AIInsightResponse(BaseModel):
    """Response payload — always 200; check ``disabled`` / ``error`` for degraded states."""

    text: str = ""
    disabled: bool = False
    error: str = ""


def _resolve_project_consent(request: Request, project_id: str | None) -> bool:
    """Read ``projects.llm_egress_consent`` for ``project_id``, fail-closed.

    Returns False -- never raises, never 500s -- for every "cannot confirm
    consent" case: no project id, runtime ports unavailable, unknown project,
    or a registry read that throws. "We could not confirm a yes" and "they
    said no" both refuse; only an explicit stored True permits egress.

    This deliberately does NOT use ``Depends(get_core_ports)`` the way
    ``backend/routers/projects.py`` does. That dependency raises HTTP 500 when
    runtime ports are unavailable, which would break this endpoint's stated
    "always 200; check ``disabled``/``error``" contract and convert a
    consent-unconfirmable state into a server error. For a consent gate the
    correct degrade is REFUSAL, not a 500 -- so ports are resolved
    defensively here and unavailability is treated as "not consented".
    """
    if not project_id:
        return False

    ports = getattr(request.app.state, "core_ports", None)
    if not isinstance(ports, CorePorts):
        # Same two lookup sites, in the same order, as ``get_core_ports``
        # (backend/request_scope.py): ``app.state.core_ports`` first, then the
        # runtime container's ``ports``. The attribute is ``runtime_container``
        # -- see ``get_runtime_container`` in backend/runtime/dependencies.py.
        container = getattr(request.app.state, "runtime_container", None)
        ports = getattr(container, "ports", None)
    if not isinstance(ports, CorePorts):
        logger.info(
            "ai_insight: runtime ports unavailable -- cannot confirm "
            "llm_egress_consent for project_id=%s; refusing egress "
            "(fail-closed, not a 500).",
            project_id,
        )
        return False

    try:
        project = ports.workspace_registry.get_project(project_id)
    except Exception:  # noqa: BLE001 -- a registry failure must refuse, not 500
        logger.warning(
            "ai_insight: llm_egress_consent read FAILED for project_id=%s -- "
            "refusing egress rather than trusting an unconfirmed consent.",
            project_id,
        )
        return False

    if project is None:
        logger.info(
            "ai_insight: project_id=%s is not registered -- refusing egress "
            "(unknown project is never an implicit consent). Deliberately "
            "NOT a 404: this route's contract is always-200 + disabled.",
            project_id,
        )
        return False

    return bool(getattr(project, "llm_egress_consent", False))


@ai_router.post("/insight", response_model=AIInsightResponse)
async def ai_insight(request: Request, body: AIInsightRequest) -> AIInsightResponse:
    """Generate a dashboard AI insight via the server-side Gemini proxy.

    Returns a graceful DISABLED response -- never a 500 -- when any egress
    precondition is absent: global ``CCDASH_LLM_EGRESS_CONSENT``, the
    per-project ``projects.llm_egress_consent`` for ``body.project_id``, or
    ``CCDASH_GEMINI_API_KEY``. The consent decision itself is made inside
    ``generate_dashboard_insight``; this handler only performs the registry
    READ that the service layer has no port for.
    """
    result = await generate_dashboard_insight(
        metrics=body.metrics,
        tasks=body.tasks,
        project_id=body.project_id,
        project_consent=_resolve_project_consent(request, body.project_id),
    )
    return AIInsightResponse(
        text=result.text,
        disabled=result.disabled,
        error=result.error,
    )
