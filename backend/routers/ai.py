"""AI router — POST /api/ai/insight proxies to Gemini server-side.

The Gemini API key is never exposed to the browser bundle. When the key
is unset the endpoint returns a 200 with ``disabled: true`` so the FE
can degrade gracefully without triggering error states.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.ai_insight import generate_dashboard_insight

ai_router = APIRouter(prefix="/api/ai", tags=["ai"])


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
