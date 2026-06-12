"""Session-level MCP tools (Phase 3 / T3-001).

Exposes:
  ccdash_session_search     — keyword / full-text search across session transcripts.
  ccdash_session_detail     — full session detail bundle (transcript-bearing).
  ccdash_session_transcript — cursor-paginated transcript page only.

All three tools require an explicit ``project_id``.  Missing project_id
returns a structured tool error (no active-project fallback).  Unknown
session_id returns a structured not-found.  Empty optional segments return
an empty list — never a 500.

MCP Payload Budget (T3-004)
---------------------------
MCP_TRANSCRIPT_DEFAULT_LIMIT : 50   items per MCP call (default)
MCP_TRANSCRIPT_MAX_LIMIT     : 200  items per MCP call (per-call ceiling;
                                    below the service MAX_TRANSCRIPT_LIMIT of 1 000)
MCP_ENVELOPE_MAX_BYTES       : 1_048_576  (1 MiB) — byte ceiling applied after
                               serialisation.  Over-budget responses paginate
                               via nextCursor and flag ``truncated: true``
                               (with reason) in response metadata rather than
                               silently dropping items.

Budget rationale:
  • 50-item default keeps cold-start latency low for typical sessions.
  • 200-item per-call ceiling avoids blowing common MCP client streaming buffers.
  • 1 MiB envelope cap matches typical MCP stdio message-size limits.
"""
from __future__ import annotations

import json
import logging

from backend.application.services.agent_queries.session_detail import (
    INCLUDE_TRANSCRIPT,
    get_session_detail,
)
from backend.application.services.session_intelligence import TranscriptSearchService
from backend.mcp.bootstrap import execute_query

__all__ = [
    "register_session_tools",
    "MCP_TRANSCRIPT_DEFAULT_LIMIT",
    "MCP_TRANSCRIPT_MAX_LIMIT",
    "MCP_ENVELOPE_MAX_BYTES",
]

logger = logging.getLogger("ccdash.mcp.tools.sessions")

# ── Payload budget constants (T3-004) ─────────────────────────────────────────

MCP_TRANSCRIPT_DEFAULT_LIMIT: int = 50
"""Default transcript page size for MCP session tools (conservative for stdio transport)."""

MCP_TRANSCRIPT_MAX_LIMIT: int = 200
"""Per-call transcript page ceiling for MCP session tools.

Intentionally below the service MAX_TRANSCRIPT_LIMIT (1 000) to keep MCP
message sizes within common client buffer limits (see MCP_ENVELOPE_MAX_BYTES).
"""

MCP_ENVELOPE_MAX_BYTES: int = 1_048_576  # 1 MiB
"""Hard byte ceiling for MCP tool response envelopes.

When a serialised response exceeds this threshold the transcript items list
is trimmed from the tail and ``meta.truncated`` is set to ``True`` with a
``meta.truncated_reason`` containing cursor guidance.
"""

# ── Module-level service singleton ────────────────────────────────────────────

_search_service = TranscriptSearchService()


# ── Internal helpers ──────────────────────────────────────────────────────────


def _clamp_limit(requested: int | None, *, default: int, ceiling: int) -> int:
    """Clamp *requested* to [1, *ceiling*], applying *default* when None."""
    raw = requested if requested is not None else default
    if raw > ceiling:
        logger.info(
            "session MCP tool: requested limit %d > MCP ceiling %d; clamped",
            raw,
            ceiling,
        )
    return max(1, min(raw, ceiling))


def _apply_byte_guard(response: dict, *, tool_name: str) -> dict:
    """Apply the MCP_ENVELOPE_MAX_BYTES ceiling to *response* in-place.

    If within budget: ``meta.truncated = False``, ``meta.payload_bytes`` recorded.
    If over budget:   transcript items trimmed from tail until within budget;
                      ``meta.truncated = True``, ``meta.truncated_reason`` set,
                      ``meta.payload_bytes`` reflects final size.
    """
    try:
        encoded = json.dumps(response, default=str).encode("utf-8")
    except Exception:
        return response

    meta = response.setdefault("meta", {})
    byte_count = len(encoded)

    if byte_count <= MCP_ENVELOPE_MAX_BYTES:
        meta["truncated"] = False
        meta["payload_bytes"] = byte_count
        return response

    # Over budget — trim transcript items from the tail
    logger.warning(
        "%s: envelope %d bytes > MCP_ENVELOPE_MAX_BYTES %d; trimming transcript",
        tool_name,
        byte_count,
        MCP_ENVELOPE_MAX_BYTES,
    )
    inner = response.get("data") or {}
    transcript = inner.get("transcript") if isinstance(inner, dict) else None
    if isinstance(transcript, dict):
        items = transcript.get("items")
        if isinstance(items, list) and items:
            while items:
                items.pop()
                if len(json.dumps(response, default=str).encode("utf-8")) <= MCP_ENVELOPE_MAX_BYTES:
                    break

    meta["truncated"] = True
    meta["truncated_reason"] = (
        f"Transcript trimmed: serialised envelope exceeded the MCP budget of "
        f"{MCP_ENVELOPE_MAX_BYTES} bytes ({byte_count} bytes before trim). "
        "Use the nextCursor field in data.transcript to retrieve remaining pages."
    )
    try:
        meta["payload_bytes"] = len(json.dumps(response, default=str).encode("utf-8"))
    except Exception:
        pass
    return response


# ── Tool registration ─────────────────────────────────────────────────────────


def register_session_tools(mcp) -> None:
    """Register all session intelligence tools onto *mcp*."""

    @mcp.tool(name="ccdash_session_search")
    async def ccdash_session_search(
        project_id: str | None = None,
        query: str | None = None,
        feature_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict:
        """Search session transcripts by keyword or topic within a project.

        Performs full-text / semantic search across session messages.

        Args:
            project_id: Required. Project to search. No active-project fallback.
            query:      Required. Search text (min 2 characters).
            feature_id: Optional. Filter to sessions linked to this feature ID.
            limit:      Max matches to return (default 25, max 100).
            offset:     Pagination offset (default 0).

        Returns:
            {status, data: {query, total, matches, capability}, meta: {project_id, ...}}

        Errors:
            status "error" when project_id or query is absent / too short.
        """
        if not project_id:
            return {
                "status": "error",
                "error": (
                    "project_id is required for ccdash_session_search. "
                    "Pass project_id=<your_project_id>. "
                    "No active-project fallback is supported."
                ),
                "data": {},
                "meta": {},
            }

        if not query or len(query.strip()) < 2:
            return {
                "status": "error",
                "error": "query must be at least 2 characters.",
                "data": {},
                "meta": {"project_id": project_id},
            }

        eff_limit = _clamp_limit(limit, default=25, ceiling=100)

        async def _query(context, ports):
            return await _search_service.search(
                context,
                ports,
                query=query.strip(),
                feature_id=feature_id,
                root_session_id=None,
                session_id=None,
                offset=offset,
                limit=eff_limit,
            )

        try:
            result = await execute_query(
                _query,
                tool_name="ccdash_session_search",
                project_id=project_id,
            )
        except Exception as exc:
            logger.error("ccdash_session_search failed: %s", exc, exc_info=True)
            return {
                "status": "error",
                "error": str(exc),
                "data": {},
                "meta": {"project_id": project_id},
            }

        try:
            result_data = (
                result.model_dump(mode="json")
                if hasattr(result, "model_dump")
                else dict(result)
            )
        except Exception:
            result_data = {}

        return {
            "status": "ok",
            "data": result_data,
            "meta": {
                "project_id": project_id,
                "query": query.strip(),
                "limit": eff_limit,
                "offset": offset,
            },
        }

    @mcp.tool(name="ccdash_session_detail")
    async def ccdash_session_detail(
        project_id: str | None = None,
        session_id: str | None = None,
        include: list[str] | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict:
        """Return the full session detail bundle for any project's session.

        All include segments (transcript, tokens, subagents, artifacts, links)
        are returned by default.  Pass ``include`` to restrict to specific segments.
        Transcript is cursor-paginated via ``data.transcript.nextCursor``.

        Redaction is applied by the Phase 1 service before egress — secrets are
        scrubbed identically for all transports.

        Args:
            project_id: Required. Project that owns the session. No active-project fallback.
            session_id: Required. Session ID to retrieve.
            include:    Segment filter (transcript, tokens, subagents, artifacts, links).
                        Omit to return all segments.
            cursor:     Opaque transcript page cursor from a previous nextCursor.
            limit:      Max transcript items per page.
                        Default MCP_TRANSCRIPT_DEFAULT_LIMIT (50).
                        Max MCP_TRANSCRIPT_MAX_LIMIT (200).

        Returns:
            {status, data: {sessionId, projectId, session, transcript?, tokens?, ...},
             meta: {project_id, session_id, truncated, payload_bytes, ...}}

        Errors:
            status "error"     — project_id or session_id missing.
            status "not_found" — session not found in the given project.
        """
        if not project_id:
            return {
                "status": "error",
                "error": (
                    "project_id is required for ccdash_session_detail. "
                    "Pass project_id=<your_project_id>. "
                    "No active-project fallback is supported."
                ),
                "data": {},
                "meta": {},
            }

        if not session_id:
            return {
                "status": "error",
                "error": "session_id is required for ccdash_session_detail.",
                "data": {},
                "meta": {"project_id": project_id},
            }

        eff_limit = _clamp_limit(
            limit,
            default=MCP_TRANSCRIPT_DEFAULT_LIMIT,
            ceiling=MCP_TRANSCRIPT_MAX_LIMIT,
        )
        eff_include = frozenset(include) if include is not None else None

        async def _query(context, ports):
            return await get_session_detail(
                project_id=project_id,
                session_id=session_id,
                ports=ports,
                include=eff_include,
                cursor=cursor,
                limit=eff_limit,
                context=context,
            )

        try:
            bundle = await execute_query(
                _query,
                tool_name="ccdash_session_detail",
                project_id=project_id,
            )
        except Exception as exc:
            logger.error("ccdash_session_detail failed: %s", exc, exc_info=True)
            return {
                "status": "error",
                "error": str(exc),
                "data": {},
                "meta": {"project_id": project_id, "session_id": session_id},
            }

        if bundle is None:
            return {
                "status": "not_found",
                "error": (
                    f"Session '{session_id}' not found in project '{project_id}'. "
                    "Verify the session_id and project_id are correct."
                ),
                "data": {},
                "meta": {"project_id": project_id, "session_id": session_id},
            }

        response = {
            "status": "ok",
            "data": bundle.as_dict(),
            "meta": {
                "project_id": project_id,
                "session_id": session_id,
                "redacted_field_count": bundle.redacted_field_count,
            },
        }
        return _apply_byte_guard(response, tool_name="ccdash_session_detail")

    @mcp.tool(name="ccdash_session_transcript")
    async def ccdash_session_transcript(
        project_id: str | None = None,
        session_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict:
        """Return a cursor-paginated transcript page for any project's session.

        Use ``data.nextCursor`` to retrieve subsequent pages.
        ``meta.truncated`` is ``true`` when the envelope was byte-capped at
        MCP_ENVELOPE_MAX_BYTES (1 MiB); use cursor to continue.

        Args:
            project_id: Required. Project that owns the session. No active-project fallback.
            session_id: Required. Session to retrieve the transcript for.
            cursor:     Opaque cursor from a previous response ``data.nextCursor``.
            limit:      Max items per page.
                        Default MCP_TRANSCRIPT_DEFAULT_LIMIT (50).
                        Max MCP_TRANSCRIPT_MAX_LIMIT (200).

        Returns:
            {status, data: {sessionId, projectId, items, cursor, limit, nextCursor,
                            redactedFieldCount}, meta: {truncated, payload_bytes, ...}}
            data.nextCursor is null on the final page.

        Errors:
            status "error"     — project_id or session_id missing.
            status "not_found" — session not found in the given project.
        """
        if not project_id:
            return {
                "status": "error",
                "error": (
                    "project_id is required for ccdash_session_transcript. "
                    "Pass project_id=<your_project_id>. "
                    "No active-project fallback is supported."
                ),
                "data": {},
                "meta": {},
            }

        if not session_id:
            return {
                "status": "error",
                "error": "session_id is required for ccdash_session_transcript.",
                "data": {},
                "meta": {"project_id": project_id},
            }

        eff_limit = _clamp_limit(
            limit,
            default=MCP_TRANSCRIPT_DEFAULT_LIMIT,
            ceiling=MCP_TRANSCRIPT_MAX_LIMIT,
        )

        async def _query(context, ports):
            return await get_session_detail(
                project_id=project_id,
                session_id=session_id,
                ports=ports,
                include={INCLUDE_TRANSCRIPT},
                cursor=cursor,
                limit=eff_limit,
                context=context,
            )

        try:
            bundle = await execute_query(
                _query,
                tool_name="ccdash_session_transcript",
                project_id=project_id,
            )
        except Exception as exc:
            logger.error("ccdash_session_transcript failed: %s", exc, exc_info=True)
            return {
                "status": "error",
                "error": str(exc),
                "data": {},
                "meta": {"project_id": project_id, "session_id": session_id},
            }

        if bundle is None:
            return {
                "status": "not_found",
                "error": (
                    f"Session '{session_id}' not found in project '{project_id}'. "
                    "Verify the session_id and project_id are correct."
                ),
                "data": {},
                "meta": {"project_id": project_id, "session_id": session_id},
            }

        transcript = bundle.transcript
        if transcript is not None:
            page_data = {
                "sessionId": bundle.session_id,
                "projectId": bundle.project_id,
                "items": transcript.items,
                "cursor": transcript.cursor,
                "limit": transcript.limit,
                "nextCursor": transcript.next_cursor,
                "redactedFieldCount": bundle.redacted_field_count,
            }
        else:
            # Transcript segment not populated — resilient empty response
            page_data = {
                "sessionId": bundle.session_id,
                "projectId": bundle.project_id,
                "items": [],
                "cursor": "",
                "limit": eff_limit,
                "nextCursor": None,
                "redactedFieldCount": 0,
            }

        response = {
            "status": "ok",
            "data": page_data,
            "meta": {
                "project_id": project_id,
                "session_id": session_id,
                "redacted_field_count": bundle.redacted_field_count,
            },
        }
        return _apply_byte_guard(response, tool_name="ccdash_session_transcript")
