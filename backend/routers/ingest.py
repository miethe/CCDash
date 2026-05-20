"""POST /api/v1/ingest/sessions — chunked NDJSON session ingest endpoint.

Transport contract: ADR-006.
Auth: existing StaticBearerTokenIdentityProvider via request_scope DI (same
path as client_v1); no new auth code is introduced.
project_id: from ``x-ccdash-project-id`` header.
workspace_id: hardcoded to ``"default"`` until Phase 4 ADR-008 workspace auth.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from backend.application.models.ingest import (
    IngestBatchResponse,
    IngestSessionEvent,
    RejectedEvent,
)
from backend.application.services.ingest.session_ingest import (
    IngestProcessingError,
    MAX_EVENTS_PER_BATCH,
)
from backend.request_scope import get_request_context, get_runtime_container

logger = logging.getLogger("ccdash.routers.ingest")

ingest_router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

_WORKSPACE_ID_DEFAULT = "default"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@ingest_router.post("/sessions")
async def post_ingest_sessions(
    request: Request,
    container: object = Depends(get_runtime_container),
    _request_context: object = Depends(get_request_context),
) -> Response:
    """Accept a chunked NDJSON batch of IngestSessionEvent records.

    The ``get_request_context`` dependency triggers bearer-token authentication
    exactly as the client_v1 routes do.  A 401/403 is raised before we reach
    the body-parsing logic if auth fails.

    Returns
    -------
    200 JSON IngestBatchResponse on full or partial success.
    413 JSON IngestBatchResponse when the batch_limit is exceeded.
    415 plain-text when Content-Type is not application/x-ndjson.
    """
    # ── Content-Type guard ────────────────────────────────────────────────────
    content_type = request.headers.get("content-type", "").lower()
    if "application/x-ndjson" not in content_type:
        return Response(
            content="Content-Type must be application/x-ndjson",
            status_code=415,
            media_type="text/plain",
        )

    # ── Project / workspace resolution ────────────────────────────────────────
    project_id: str = (
        request.headers.get("x-ccdash-project-id", "").strip() or "default-project"
    )
    workspace_id: str = _WORKSPACE_ID_DEFAULT

    # ── Get (or lazy-create) the process-wide ingest service ─────────────────
    ingest_service = container.remote_ingest_service  # type: ignore[attr-defined]

    # ── Stream + parse ────────────────────────────────────────────────────────
    accepted: int = 0
    rejected: list[RejectedEvent] = []
    last_cursor: str | None = None
    line_buffer = b""
    batch_limit_exceeded = False

    async for chunk in request.stream():
        line_buffer += chunk
        while b"\n" in line_buffer:
            raw_line, line_buffer = line_buffer.split(b"\n", 1)
            stripped = raw_line.strip()
            if not stripped:
                continue

            # Enforce max-events-per-batch before parsing.
            if accepted + len(rejected) >= MAX_EVENTS_PER_BATCH:
                batch_limit_exceeded = True
                break

            # Parse line as IngestSessionEvent.
            try:
                event = IngestSessionEvent.model_validate_json(stripped)
            except Exception as exc:
                rejected.append(
                    RejectedEvent(
                        event_id=_extract_event_id(stripped),
                        reason=f"validation_error: {exc}",
                        code="invalid_event",
                    )
                )
                continue

            # Process event.
            try:
                was_new, source_ref = await ingest_service.process(
                    event,
                    project_id=project_id,
                    workspace_id=workspace_id,
                )
                if was_new:
                    accepted += 1
                    last_cursor = event.event_id
                else:
                    # Duplicate — count as accepted (idempotent).
                    accepted += 1
            except IngestProcessingError as exc:
                rejected.append(
                    RejectedEvent(
                        event_id=event.event_id,
                        reason=exc.reason,
                        code=exc.code,
                    )
                )

        if batch_limit_exceeded:
            break

    # ── Drain remaining buffer (no newline at EOF) ─────────────────────────────
    if not batch_limit_exceeded and line_buffer.strip():
        # One last line without a trailing newline.
        if accepted + len(rejected) < MAX_EVENTS_PER_BATCH:
            try:
                event = IngestSessionEvent.model_validate_json(line_buffer.strip())
                try:
                    was_new, source_ref = await ingest_service.process(
                        event,
                        project_id=project_id,
                        workspace_id=workspace_id,
                    )
                    accepted += 1
                    if was_new:
                        last_cursor = event.event_id
                except IngestProcessingError as exc:
                    rejected.append(
                        RejectedEvent(
                            event_id=event.event_id,
                            reason=exc.reason,
                            code=exc.code,
                        )
                    )
            except Exception as exc:
                rejected.append(
                    RejectedEvent(
                        event_id=_extract_event_id(line_buffer.strip()),
                        reason=f"validation_error: {exc}",
                        code="invalid_event",
                    )
                )
        else:
            batch_limit_exceeded = True

    # ── Build response ─────────────────────────────────────────────────────────
    if batch_limit_exceeded:
        body = IngestBatchResponse(
            accepted=accepted,
            rejected=[],
            dead_lettered=[
                RejectedEvent(
                    event_id=None,
                    reason="batch_limit_exceeded",
                    code="batch_too_large",
                )
            ],
            cursor_advanced_to=last_cursor,
        )
        return JSONResponse(content=body.model_dump(), status_code=413)

    body = IngestBatchResponse(
        accepted=accepted,
        rejected=rejected,
        dead_lettered=[],
        cursor_advanced_to=last_cursor,
    )
    return JSONResponse(content=body.model_dump(), status_code=200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_event_id(raw: bytes) -> str | None:
    """Best-effort extraction of event_id from a raw JSON line for rejection records."""
    try:
        obj = json.loads(raw)
        val = obj.get("event_id")
        return str(val) if val is not None else None
    except Exception:
        return None
