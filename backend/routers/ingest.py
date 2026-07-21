"""POST /api/v1/ingest/sessions — chunked NDJSON session ingest endpoint.

Transport contract: ADR-006.
Auth: WorkspaceTokenAuthBackend via get_auth_context (ADR-008).
project_id: from AuthContext.project_id (resolved from workspace token).
workspace_id: from AuthContext.workspace_id (resolved from workspace token).
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from backend import config
from backend.adapters.auth.context import AuthContext
from backend.adapters.auth.dependency import get_auth_context
from backend.application.models.ingest import (
    IngestBatchResponse,
    IngestSessionEvent,
    RejectedEvent,
    RfEventPayload,
)
from backend.application.services.ingest.session_ingest import (
    IngestProcessingError,
    MAX_EVENTS_PER_BATCH,
)
from backend.application.services.ingest.rf_events_ingest import (
    RfEventProcessingError,
    MAX_EVENTS_PER_BATCH as RF_MAX_EVENTS_PER_BATCH,
)
from backend.request_scope import get_runtime_container

logger = logging.getLogger("ccdash.routers.ingest")

ingest_router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


def _require_rf_telemetry_enabled() -> None:
    """Gate for POST /api/v1/ingest/rf-events (T1-006).

    Fail-open default (CCDASH_RF_TELEMETRY_ENABLED=true). When disabled, the
    route 404s with zero effect on any other ingest source, router, or
    surface — sessions ingest, health/detail, and capabilities are unaffected.
    """
    if not config.CCDASH_RF_TELEMETRY_ENABLED:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "rf_telemetry_disabled",
                "message": "Research Foundry run telemetry ingest is disabled.",
                "hint": "Set CCDASH_RF_TELEMETRY_ENABLED=true to enable.",
            },
        )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@ingest_router.post("/sessions")
async def post_ingest_sessions(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    container: object = Depends(get_runtime_container),
) -> Response:
    """Accept a chunked NDJSON batch of IngestSessionEvent records.

    The ``get_auth_context`` dependency resolves the workspace token and
    provides workspace-scoped project_id and workspace_id.  A 401/403 is
    raised before we reach the body-parsing logic if auth fails.

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

    # ── Project / workspace resolution (from workspace token, ADR-008) ────────
    project_id: str = auth.project_id
    workspace_id: str = auth.workspace_id

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


@ingest_router.post(
    "/rf-events",
    dependencies=[Depends(_require_rf_telemetry_enabled)],
)
async def post_ingest_rf_events(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    container: object = Depends(get_runtime_container),
) -> Response:
    """Accept a single JSON or NDJSON batch of RF ``ccdash_event`` records (T1-003).

    Research Foundry run telemetry ingest — Phase 1
    (docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1/phase-1-ingest.md).

    Reuses ``WorkspaceTokenAuthBackend`` via ``get_auth_context`` (ADR-008) —
    zero new auth code. Accepts either:
      * ``Content-Type: application/x-ndjson`` — one RfEventPayload JSON
        object per line (mirrors ``POST /api/v1/ingest/sessions`` transport).
      * ``Content-Type: application/json`` — a single RfEventPayload JSON
        object.

    Every event runs through the Layer 1 known-secret pattern redaction scan
    (FR-14) inside ``RfEventsIngestService.process()`` BEFORE the row is
    persisted to ``rf_events`` (T1-001).

    Dead-letter classification (T1-004, reusing the existing NDJSON
    dead-letter contract per ``docs/guides/remote-ingest-operator-guide.md``):
      * A payload that fails Pydantic validation (malformed/missing required
        fields) never reaches ``process()`` — it is appended to ``rejected[]``
        with ``code="invalid_event"``, unchanged from T1-003.
      * A schema-valid payload that fails to persist (``RfEventProcessingError``
        — the insert failed even after ``retry_on_locked`` exhausted its
        retries) is a *permanent* failure and is appended to
        ``dead_lettered[]`` instead, so it is never silently dropped.

    Returns
    -------
    200 JSON IngestBatchResponse on full or partial success (including
        per-event validation failures in ``rejected[]`` and permanent
        processing failures in ``dead_lettered[]``).
    413 JSON IngestBatchResponse when the NDJSON batch limit is exceeded.
    415 plain-text when Content-Type is neither of the above.
    """
    content_type = request.headers.get("content-type", "").lower()
    project_id: str = auth.project_id
    workspace_id: str = auth.workspace_id
    ingest_service = container.rf_events_ingest_service  # type: ignore[attr-defined]

    if "application/x-ndjson" in content_type:
        body = await request.body()
        lines = [line for line in body.split(b"\n") if line.strip()]

        accepted = 0
        rejected: list[RejectedEvent] = []
        dead_lettered: list[RejectedEvent] = []
        last_cursor: str | None = None
        batch_limit_exceeded = False

        for raw_line in lines:
            if accepted + len(rejected) + len(dead_lettered) >= RF_MAX_EVENTS_PER_BATCH:
                batch_limit_exceeded = True
                break

            try:
                event = RfEventPayload.model_validate_json(raw_line)
            except Exception as exc:
                rejected.append(
                    RejectedEvent(
                        event_id=_extract_event_id(raw_line),
                        reason=f"validation_error: {exc}",
                        code="invalid_event",
                    )
                )
                continue

            try:
                _was_new, event_id = await ingest_service.process(
                    event,
                    project_id=project_id,
                    workspace_id=workspace_id,
                )
                accepted += 1
                last_cursor = event_id
            except RfEventProcessingError as exc:
                # Permanent failure (insert failed even after retry_on_locked
                # exhausted its retries) — dead-letter, don't silently drop
                # or conflate with a validation rejection (T1-004).
                dead_lettered.append(
                    RejectedEvent(event_id=event.event_id, reason=exc.reason, code=exc.code)
                )

        if batch_limit_exceeded:
            body_resp = IngestBatchResponse(
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
            return JSONResponse(content=body_resp.model_dump(), status_code=413)

        body_resp = IngestBatchResponse(
            accepted=accepted,
            rejected=rejected,
            dead_lettered=dead_lettered,
            cursor_advanced_to=last_cursor,
        )
        return JSONResponse(content=body_resp.model_dump(), status_code=200)

    if "application/json" in content_type:
        raw = await request.body()
        try:
            event = RfEventPayload.model_validate_json(raw)
        except Exception as exc:
            body_resp = IngestBatchResponse(
                accepted=0,
                rejected=[
                    RejectedEvent(
                        event_id=_extract_event_id(raw),
                        reason=f"validation_error: {exc}",
                        code="invalid_event",
                    )
                ],
                dead_lettered=[],
                cursor_advanced_to=None,
            )
            return JSONResponse(content=body_resp.model_dump(), status_code=200)

        try:
            _was_new, event_id = await ingest_service.process(
                event,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        except RfEventProcessingError as exc:
            # Permanent failure — dead-letter, not rejected (T1-004).
            body_resp = IngestBatchResponse(
                accepted=0,
                rejected=[],
                dead_lettered=[
                    RejectedEvent(event_id=event.event_id, reason=exc.reason, code=exc.code)
                ],
                cursor_advanced_to=None,
            )
            return JSONResponse(content=body_resp.model_dump(), status_code=200)

        body_resp = IngestBatchResponse(
            accepted=1,
            rejected=[],
            dead_lettered=[],
            cursor_advanced_to=event_id,
        )
        return JSONResponse(content=body_resp.model_dump(), status_code=200)

    return Response(
        content="Content-Type must be application/x-ndjson or application/json",
        status_code=415,
        media_type="text/plain",
    )


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
