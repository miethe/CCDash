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

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.routers._client_v1_auth import require_v1_auth
from backend.services.ai_insight import generate_dashboard_insight

# ADR-008: identity resolution lives in ONE place — replace require_v1_auth to
# upgrade the auth model; no handler body here needs to change.
ai_router = APIRouter(
    prefix="/api/ai",
    tags=["ai"],
    dependencies=[Depends(require_v1_auth)],
)


class AIInsightRequest(BaseModel):
    """Input payload for the AI insight endpoint."""

    metrics: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)


class AIInsightResponse(BaseModel):
    """Response payload — always 200; check ``disabled`` / ``error`` for degraded states."""

    text: str = ""
    disabled: bool = False
    error: str = ""


@ai_router.post("/insight", response_model=AIInsightResponse)
async def ai_insight(body: AIInsightRequest) -> AIInsightResponse:
    """Generate a dashboard AI insight via the server-side Gemini proxy.

    Returns a graceful DISABLED response when CCDASH_GEMINI_API_KEY is unset
    (never 500).
    """
    result = await generate_dashboard_insight(
        metrics=body.metrics,
        tasks=body.tasks,
    )
    return AIInsightResponse(
        text=result.text,
        disabled=result.disabled,
        error=result.error,
    )
