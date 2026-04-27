"""Observability ingress endpoints for client-side beacon events.

This router is intentionally thin: it accepts beacon payloads from the
frontend and delegates directly to the observability layer.  No service or
repository layer is needed because the operation is fire-and-record with no
persistent state.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.application.context import RequestContext
from backend.observability import otel
from backend.request_scope import get_request_context

observability_router = APIRouter(prefix="/api/observability", tags=["observability"])


class PollTeardownRequest(BaseModel):
    """Body for the frontend poll-teardown beacon.

    ``events`` is the number of teardown events accumulated in sessionStorage
    before the frontend was able to reconnect and flush the beacon.  Clamped
    to [1, 100] to prevent a single rogue client from flooding the counter.
    """

    events: int = Field(default=1, ge=1, le=100)


@observability_router.post(
    "/poll-teardown",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Record frontend polling teardown events",
    description=(
        "Accepts a beacon from the frontend when it successfully reconnects "
        "after a polling teardown.  Each event maps to one increment of the "
        "ccdash_frontend_poll_teardown_total counter."
    ),
)
async def record_poll_teardown(
    body: PollTeardownRequest = PollTeardownRequest(),
    _: RequestContext = Depends(get_request_context),
) -> JSONResponse:
    # Fire once per accumulated event.  The counter has no labels so this is
    # a tight loop over a lock-free atomic increment — negligible cost.
    for _ in range(body.events):
        otel.record_frontend_poll_teardown()

    return JSONResponse(
        content={"recorded": body.events},
        status_code=status.HTTP_202_ACCEPTED,
    )
