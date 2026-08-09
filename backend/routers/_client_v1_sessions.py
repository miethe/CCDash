"""Session intelligence handler functions for the versioned CCDash client API (v1).

This module defines pure handler functions (no router).  Each handler is
intended to be wired onto ``client_v1_router`` by the router registration
layer.  All handlers follow the ``_resolve_app_request`` pattern used
throughout the analytics and agent routers.

Phase 2 additions
-----------------
``get_session_full_detail_v1`` and ``get_session_transcript_page_v1`` are the
new transcript-bearing detail endpoints.  They delegate to the Phase 1 service
(``backend.application.services.agent_queries.session_detail.get_session_detail``)
and require an explicit ``project_id`` query param — there is NO active-project
fallback (HTTP 400 if ``project_id`` is missing).
"""
from __future__ import annotations

import base64
import json
import logging

from fastapi import HTTPException

from ccdash_contracts import SessionDetailV1, SessionToolCallsPageV1, SessionTranscriptPageV1

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.agent_queries.models import SessionRef
from backend.application.services.agent_queries.redaction import redact_entries
from backend.application.services.agent_queries.session_detail import (
    DEFAULT_TRANSCRIPT_LIMIT,
    INCLUDE_TRANSCRIPT,
    get_session_detail,
)
from backend.application.services.session_intelligence import (
    SessionIntelligenceReadService,
    TranscriptSearchService,
)
from backend.application.services.sessions import SessionTranscriptService
from backend.db.factory import get_session_repository
from backend.models import (
    SessionIntelligenceConcern,
    SessionIntelligenceDetailResponse,
    SessionIntelligenceDrilldownResponse,
    SessionIntelligenceListResponse,
    SessionIntelligenceSessionRollup,
    SessionSemanticSearchResponse,
)
from backend.routers.client_v1_models import (
    ClientV1Envelope,
    ClientV1PaginatedEnvelope,
    SessionFamilyDTO,
    build_client_v1_meta,
    build_client_v1_paginated_meta,
)


# ---------------------------------------------------------------------------
# Module-level service singletons (same pattern as analytics.py)
# ---------------------------------------------------------------------------

logger = logging.getLogger("ccdash.client_v1.sessions")

session_intelligence_read_service = SessionIntelligenceReadService()
transcript_search_service = TranscriptSearchService()
# itt-node-session-cost-join (AC2): the only transcript reader used by the
# tool-calls endpoint below -- mirrors session_detail.py's own singleton, but
# this module does not go through the Phase 1 bundle service since the
# tool-calls endpoint reuses list_session_logs directly (no new SQL).
session_transcript_service = SessionTranscriptService()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _resolve_app_request(
    request_context: RequestContext,
    core_ports: CorePorts,
):
    """Resolve a transport-neutral application request from FastAPI dependencies."""
    return await resolve_application_request(
        request_context,
        core_ports,
        core_ports.storage.db,
    )


def _instance_id() -> str:
    """Return a best-effort instance identifier from config."""
    from backend import config as _cfg

    return getattr(_cfg, "INSTANCE_ID", "") or "ccdash-local"


# ---------------------------------------------------------------------------
# Handler: list sessions
# ---------------------------------------------------------------------------


async def list_sessions_v1(
    feature_id: str | None,
    root_session_id: str | None,
    limit: int,
    offset: int,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1PaginatedEnvelope[SessionIntelligenceSessionRollup]:
    """Return a paginated list of session intelligence rollups.

    Wraps ``SessionIntelligenceReadService.list_sessions``.  Default limit is
    50; maximum is 100.
    """
    app_request = await _resolve_app_request(request_context, core_ports)
    result: SessionIntelligenceListResponse = await session_intelligence_read_service.list_sessions(
        app_request.context,
        app_request.ports,
        feature_id=feature_id,
        root_session_id=root_session_id,
        session_id=None,
        offset=offset,
        limit=limit,
    )

    items = result.items if hasattr(result, "items") else []
    total = result.total if hasattr(result, "total") else len(items)

    return ClientV1PaginatedEnvelope(
        status="ok",
        data=items,
        meta=build_client_v1_paginated_meta(
            instance_id=_instance_id(),
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        ),
    )


# ---------------------------------------------------------------------------
# Handler: session detail
# ---------------------------------------------------------------------------


async def get_session_detail_v1(
    session_id: str,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[SessionIntelligenceDetailResponse]:
    """Return detailed intelligence for a single session.

    Raises HTTP 404 when the session is unknown.
    Wraps ``SessionIntelligenceReadService.get_session_detail``.
    """
    app_request = await _resolve_app_request(request_context, core_ports)
    detail: SessionIntelligenceDetailResponse | None = (
        await session_intelligence_read_service.get_session_detail(
            app_request.context,
            app_request.ports,
            session_id=session_id,
        )
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session intelligence for '{session_id}' not found",
        )
    return ClientV1Envelope(
        status="ok",
        data=detail,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Handler: session search
# ---------------------------------------------------------------------------


async def search_sessions_v1(
    q: str,
    feature_id: str | None,
    root_session_id: str | None,
    session_id: str | None,
    limit: int,
    offset: int,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[SessionSemanticSearchResponse]:
    """Full-text / semantic search across session transcripts.

    ``q`` must be at least 2 characters.  Default limit is 25; maximum is 100.
    Wraps ``TranscriptSearchService.search``.
    """
    if len(q) < 2:
        raise HTTPException(
            status_code=422,
            detail="Query parameter 'q' must be at least 2 characters",
        )

    app_request = await _resolve_app_request(request_context, core_ports)
    result: SessionSemanticSearchResponse = await transcript_search_service.search(
        app_request.context,
        app_request.ports,
        query=q,
        feature_id=feature_id,
        root_session_id=root_session_id,
        session_id=session_id,
        offset=offset,
        limit=limit,
    )
    return ClientV1Envelope(
        status="ok",
        data=result,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Handler: session drilldown
# ---------------------------------------------------------------------------


async def get_session_drilldown_v1(
    session_id: str,
    concern: SessionIntelligenceConcern,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[SessionIntelligenceDrilldownResponse]:
    """Return drilldown intelligence for a specific concern on a single session.

    ``session_id`` is a path parameter (unlike the legacy analytics endpoint
    where it is a query parameter).  Raises HTTP 404 when no data is found.
    Wraps ``SessionIntelligenceReadService.drilldown``.
    """
    app_request = await _resolve_app_request(request_context, core_ports)
    detail: SessionIntelligenceDrilldownResponse | None = (
        await session_intelligence_read_service.drilldown(
            app_request.context,
            app_request.ports,
            concern=concern,
            feature_id=None,
            root_session_id=None,
            session_id=session_id,
            offset=0,
            limit=50,
        )
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session intelligence drilldown for '{session_id}' / concern '{concern}' not found",
        )
    return ClientV1Envelope(
        status="ok",
        data=detail,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Handler: session family
# ---------------------------------------------------------------------------


async def get_session_family_v1(
    session_id: str,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[SessionFamilyDTO]:
    """Return all sessions that share the same ``root_session_id`` as *session_id*.

    Algorithm:
    1. Look up the target session to obtain its ``root_session_id``.
    2. Query all sessions in the project whose ``root_session_id`` matches.
    3. Return a ``SessionFamilyDTO`` wrapped in a ``ClientV1Envelope``.

    Raises HTTP 404 when the target session does not exist.

    Note on ``SessionRef.tool_names``: every member in this response's ``members`` list
    has ``tool_names == []`` today, always. It is not a column on the ``sessions`` row this
    endpoint reads (only ``workflow_refs``/``source_ref`` are plain columns and are
    populated directly below); populating it would require a separate per-session
    tool-usage/transcript query for every family member, which this endpoint does not run
    (see the inline comment at the ``SessionRef(...)`` construction below, and
    ``feature_forensics.py``'s ``_enrich_session_refs`` ~L180-196 for the only call site
    that does run that query). An empty list here is a contract state, not a bug — see
    ``SessionRef.tool_names``'s field description and
    ``.claude/worknotes/session-family-and-team-sidecar/implementation-notes.md``.
    """
    app_request = await _resolve_app_request(request_context, core_ports)
    session_repo = get_session_repository(core_ports.storage.db)

    # Resolve the requested project (active-project resolution when unscoped).
    requested_project_id: str | None = (
        app_request.context.project.project_id if app_request.context.project else None
    )

    # Step 1: resolve the anchor session, scoped to the requested project so a
    # family request for a non-active project never resolves the wrong project's
    # row. When no project is in scope (None/''), the lookup is unscoped and falls
    # back to the active-project hot path. Anchor-not-found-in-project yields a 404
    # with NO silent fallback to the active project.
    anchor = await session_repo.get_by_id(session_id, project_id=requested_project_id)
    if anchor is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found",
        )

    root_id: str = anchor.get("root_session_id") or session_id

    # Step 2: fetch all family members. Derive project_id from the ANCHOR ROW (its
    # authoritative project), not the active-project singleton, and thread that
    # derived id into the family lookup so descendants/ancestors are scoped to the
    # anchor's project end-to-end.
    project_id: str = anchor.get("project_id") or requested_project_id or ""
    # ``include_subagents`` defaults to False in list_paginated's filter logic
    # (see repositories/sessions.py ~L425), which appends
    # "(session_type IS NULL OR session_type != 'subagent')" and silently
    # drops every subagent child from the family. A session family MUST
    # include subagent children, so this is explicitly requested here.
    rows: list[dict] = await session_repo.list_paginated(
        offset=0,
        limit=500,
        project_id=project_id or None,
        sort_by="started_at",
        sort_order="asc",
        filters={"root_session_id": root_id, "include_subagents": True},
        workspace_id="default-local",  # TODO(workspace-routing)
    )

    # Step 3: map raw rows to SessionRef DTOs.
    members: list[SessionRef] = [
        SessionRef(
            session_id=row.get("id", ""),
            feature_id=row.get("task_id", ""),
            root_session_id=row.get("root_session_id", ""),
            title=row.get("title", ""),
            status=row.get("status", ""),
            started_at=row.get("started_at", ""),
            ended_at=row.get("ended_at", ""),
            model=row.get("model", ""),
            total_cost=float(row.get("total_cost") or 0.0),
            total_tokens=int(row.get("tokens_in", 0) or 0) + int(row.get("tokens_out", 0) or 0),
            duration_seconds=float(row.get("duration_seconds") or 0.0),
            # workflow_id is a plain column on the sessions row; wrap it as a
            # single-element list to match SessionSummary.workflow_refs shape
            # (same pattern as workflow_intelligence.py:_row_to_ref).
            workflow_refs=(
                [str(row["workflow_id"])] if str(row.get("workflow_id") or "").strip() else []
            ),
            # source_ref is a plain column on the sessions row (see
            # repositories/sessions.py:compute_source_ref) — populate directly.
            source_ref=str(row.get("source_ref") or ""),
            # tool_names is NOT present on the sessions row itself; deriving it
            # requires a separate tool-usage query (see feature_forensics.py
            # ~L180-196), which is out of scope here. Left empty — documented
            # gap in .claude/worknotes/session-family-and-team-sidecar/
            # implementation-notes.md.
        )
        for row in rows
    ]

    dto = SessionFamilyDTO(
        root_session_id=root_id,
        session_count=len(members),
        members=members,
    )

    return ClientV1Envelope(
        status="ok",
        data=dto,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Handler: full session detail (transcript-bearing) — Phase 2 / T2-002/T2-003
# ---------------------------------------------------------------------------


async def get_session_full_detail_v1(
    session_id: str,
    project_id: str | None,
    include: list[str] | None,
    cursor: str | None,
    limit: int,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[SessionDetailV1]:
    """Return full session detail bundle (transcript-bearing) for **any** project.

    Delegates to the Phase 1 transport-neutral service
    ``session_detail.get_session_detail``.  The service applies redaction
    before returning, so secrets are scrubbed before this handler serialises
    the response.

    ``project_id`` is **required** — HTTP 400 if absent.  There is no
    active-project fallback.  Unknown ``session_id`` yields HTTP 404.

    ``include`` is a repeatable query param (``?include=transcript&include=tokens``);
    omitting it defaults to ALL segments.
    """
    if not project_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "project_id is required for GET /sessions/{id}/detail. "
                "Pass ?project_id=<project_id>. "
                "Active-project fallback is not supported on this endpoint."
            ),
        )

    effective_include = frozenset(include) if include is not None else None

    bundle = await get_session_detail(
        project_id=project_id,
        session_id=session_id,
        ports=core_ports,
        include=effective_include,
        cursor=cursor,
        limit=limit if limit > 0 else None,
        context=request_context,
    )

    if bundle is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found in project '{project_id}'",
        )

    data = SessionDetailV1.model_validate(bundle.as_dict())
    return ClientV1Envelope(
        status="ok",
        data=data,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Handler: transcript page — Phase 2 / T2-002/T2-003
# ---------------------------------------------------------------------------


async def get_session_transcript_page_v1(
    session_id: str,
    project_id: str | None,
    cursor: str | None,
    limit: int,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[SessionTranscriptPageV1]:
    """Return a cursor-paginated transcript page for **any** project.

    Delegates to the Phase 1 service with ``include={transcript}`` only —
    no subagents, tokens, artifacts, or links are fetched.  Redaction is
    applied by the service before this handler serialises the response.

    ``project_id`` is **required** — HTTP 400 if absent.  There is no
    active-project fallback.  Unknown ``session_id`` yields HTTP 404.
    """
    if not project_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "project_id is required for GET /sessions/{id}/transcript. "
                "Pass ?project_id=<project_id>. "
                "Active-project fallback is not supported on this endpoint."
            ),
        )

    bundle = await get_session_detail(
        project_id=project_id,
        session_id=session_id,
        ports=core_ports,
        include={INCLUDE_TRANSCRIPT},
        cursor=cursor,
        limit=limit if limit > 0 else None,
        context=request_context,
    )

    if bundle is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found in project '{project_id}'",
        )

    transcript = bundle.transcript
    if transcript is not None:
        page_data = SessionTranscriptPageV1(
            sessionId=bundle.session_id,
            projectId=bundle.project_id,
            items=transcript.items,
            cursor=transcript.cursor,
            limit=transcript.limit,
            nextCursor=transcript.next_cursor,
            redactedFieldCount=bundle.redacted_field_count,
        )
    else:
        # Transcript segment was not populated — resilient empty response.
        page_data = SessionTranscriptPageV1(
            sessionId=bundle.session_id,
            projectId=bundle.project_id,
            items=[],
            cursor="",
            limit=limit,
            nextCursor=None,
            redactedFieldCount=0,
        )

    return ClientV1Envelope(
        status="ok",
        data=page_data,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


# ---------------------------------------------------------------------------
# Handler: tool-calls page — itt-node-session-cost-join (AC2)
# ---------------------------------------------------------------------------


def _encode_offset_cursor(offset: int) -> str:
    """Encode an integer offset as an opaque URL-safe base64 cursor string.

    Deliberately duplicated from ``session_detail.py``'s private
    ``_encode_cursor`` (same shape: ``{"o": offset}``) rather than importing
    a leading-underscore symbol across modules — this endpoint bypasses the
    Phase 1 bundle service entirely (reuses ``list_session_logs`` directly,
    no new SQL), so it owns its own tiny cursor codec instead of reaching
    into that service's internals.
    """
    raw = json.dumps({"o": offset}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_offset_cursor(cursor: str | None) -> int:
    """Decode an opaque cursor string to an integer offset.

    Returns 0 on ``None``, empty string, or any decoding error (resilient —
    a malformed cursor restarts pagination rather than erroring).
    """
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        payload = json.loads(raw)
        return max(0, int(payload.get("o", 0)))
    except Exception:
        return 0


async def get_session_tool_calls_v1(
    session_id: str,
    project_id: str | None,
    tool: str | None,
    cursor: str | None,
    limit: int,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[SessionToolCallsPageV1]:
    """Return a cursor-paginated page of tool-call ``session_logs`` rows (AC2).

    Makes ``session_logs`` rows reachable by an external script over HTTP
    without direct postgres access. Reuses
    ``SessionTranscriptService.list_session_logs`` directly (the same reader
    ``GET /sessions/{id}/logs`` and the Phase 1 ``session_detail`` bundle
    service use) — no new SQL is introduced by this endpoint.

    ``items`` is narrowed to entries carrying a non-empty ``toolCall.name``
    (a truthy ``toolCall`` dict alone is not sufficient — see the inline
    comment at the filter below), and further narrowed by exact
    ``toolCall.name`` match when ``tool`` is supplied. The narrowing happens
    AFTER a raw ``limit``-sized page is
    fetched, so a page may contain fewer than ``limit`` items even when more
    raw rows remain downstream — callers MUST keep following ``nextCursor``
    until it is ``null``, not stop at a short page (documented contract
    state, see ``SessionToolCallsPageV1``'s docstring).

    Session-detail redaction (``agent_queries.redaction.redact_entries``) is
    applied before egress, identically to every other transcript-bearing
    endpoint.

    ``project_id`` is **required** — HTTP 400 if absent.  There is no
    active-project fallback.  Unknown ``session_id`` yields HTTP 404.
    """
    # request_context is accepted for signature symmetry with its sibling
    # handlers in this module (supplied by the router already) but is
    # intentionally unused here: this path takes no active-project
    # fallback (project_id is required above), and neither
    # list_session_logs nor redact_entries accepts a context.
    if not project_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "project_id is required for GET /sessions/{id}/tool-calls. "
                "Pass ?project_id=<project_id>. "
                "Active-project fallback is not supported on this endpoint."
            ),
        )

    session_repo = core_ports.storage.sessions()
    session_row = await session_repo.get_by_id(session_id, project_id=project_id)
    if session_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found in project '{project_id}'",
        )

    offset = _decode_offset_cursor(cursor)
    eff_limit = max(1, int(limit or DEFAULT_TRANSCRIPT_LIMIT))

    # Request one extra raw row to detect whether a next page exists in the
    # underlying (pre-filter) log stream.
    raw_items = await session_transcript_service.list_session_logs(
        session_row, core_ports, limit=eff_limit + 1, offset=offset
    )
    has_more = len(raw_items) > eff_limit
    page_items = raw_items[:eff_limit]

    # A toolCall dict is present on every legacy-round-tripped row (the
    # storage layer defaults tool_status to "success" even for plain
    # messages), so "has a tool call" MUST be judged by a non-empty
    # ``toolCall.name`` -- a truthy ``toolCall`` dict alone is not sufficient.
    tool_call_items = [
        entry for entry in page_items if (entry.get("toolCall") or {}).get("name")
    ]
    if tool:
        tool_call_items = [
            entry
            for entry in tool_call_items
            if str((entry.get("toolCall") or {}).get("name") or "") == tool
        ]

    try:
        redacted_items, redacted_count = redact_entries(tool_call_items)
    except Exception:
        logger.warning(
            "get_session_tool_calls_v1: redaction raised unexpectedly for session %r; "
            "proceeding without redaction for this page",
            session_id,
            exc_info=True,
        )
        # Fail-safe delivery beats a 500 (same posture as session_detail.py).
        redacted_items, redacted_count = tool_call_items, 0

    next_cursor = _encode_offset_cursor(offset + eff_limit) if has_more else None
    page_data = SessionToolCallsPageV1(
        sessionId=session_id,
        projectId=project_id,
        items=redacted_items,
        cursor=_encode_offset_cursor(offset),
        limit=eff_limit,
        nextCursor=next_cursor,
        redactedFieldCount=redacted_count,
    )
    return ClientV1Envelope(
        status="ok",
        data=page_data,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )
