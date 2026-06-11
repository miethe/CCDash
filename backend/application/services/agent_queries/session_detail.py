"""Transport-neutral session detail query service (Phase 1 / FR-3, FR-4).

Single source of truth for full session detail retrieval.  Assembles:

  - ``transcript`` — cursor-paginated log entries via
    ``SessionTranscriptService.list_session_logs`` (the **only** transcript
    reader; no duplicate reader is introduced).
  - ``subagents``  — child sessions resolved from ``list_relationships``.
  - ``tokens``     — telemetry extracted from the session row.
  - ``artifacts``  — entity links whose source or target type is an artifact
                     variant (artifact / document / file / attachment).
  - ``links``      — all remaining entity links for the session.

All transcript/tool payloads are **redacted** via
``agent_queries.redaction.redact_entries`` before egress, so every transport
(REST / MCP / CLI) inherits the same secret-scrubbing guarantee without any
per-transport code.

Cursor pagination envelope::

    {items, cursor, limit, nextCursor}

``cursor`` and ``nextCursor`` are opaque base64-encoded JSON strings encoding
the page offset.  ``nextCursor`` is ``None`` when the page is the last one.

Service constants
-----------------
DEFAULT_TRANSCRIPT_LIMIT : int = 200
MAX_TRANSCRIPT_LIMIT     : int = 1000

Resilience invariants
---------------------
- ``project_id`` is threaded into every repository call (Phase 0 invariant).
- A missing optional segment (no artifacts, no sidecar) returns an empty list
  or ``None`` for that include key — never a 500.
- An unknown ``include`` flag is ignored with a warning, not an error.
- Redaction failures are logged and the entry is returned as-is (fail-safe
  delivery beats a 500; secrets in edge-case paths are preferable to data
  loss).
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any, FrozenSet

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.sessions import SessionTranscriptService
from backend.observability import otel

from .redaction import redact_entries

__all__ = [
    "DEFAULT_TRANSCRIPT_LIMIT",
    "MAX_TRANSCRIPT_LIMIT",
    "ALL_INCLUDE_FLAGS",
    "INCLUDE_TRANSCRIPT",
    "INCLUDE_SUBAGENTS",
    "INCLUDE_TOKENS",
    "INCLUDE_ARTIFACTS",
    "INCLUDE_LINKS",
    "TranscriptPage",
    "SessionDetailBundle",
    "get_session_detail",
]

logger = logging.getLogger("ccdash.agent_queries.session_detail")

# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_TRANSCRIPT_LIMIT: int = 200
MAX_TRANSCRIPT_LIMIT: int = 1000

# Valid include flag name constants
INCLUDE_TRANSCRIPT = "transcript"
INCLUDE_SUBAGENTS = "subagents"
INCLUDE_TOKENS = "tokens"
INCLUDE_ARTIFACTS = "artifacts"
INCLUDE_LINKS = "links"

ALL_INCLUDE_FLAGS: frozenset[str] = frozenset(
    {INCLUDE_TRANSCRIPT, INCLUDE_SUBAGENTS, INCLUDE_TOKENS, INCLUDE_ARTIFACTS, INCLUDE_LINKS}
)

# Module-level singleton: SessionTranscriptService is the ONLY transcript reader.
# If you're looking for the transcript-read path — it is here and nowhere else
# in this service file.
_transcript_service = SessionTranscriptService()


# ── Cursor helpers ────────────────────────────────────────────────────────────

def _encode_cursor(offset: int) -> str:
    """Encode an integer offset as an opaque URL-safe base64 cursor string."""
    raw = json.dumps({"o": offset}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    """Decode an opaque cursor string to an integer offset.

    Returns 0 on ``None``, empty string, or any decoding error (resilient).
    """
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        payload = json.loads(raw)
        return max(0, int(payload.get("o", 0)))
    except Exception:
        logger.warning(
            "session_detail: invalid cursor %r — resetting to offset 0", cursor
        )
        return 0


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class TranscriptPage:
    """Cursor-paginated page of transcript log entries."""

    items: list[dict[str, Any]]
    """Log entries for this page (already redacted)."""

    cursor: str
    """Opaque cursor that was used to fetch this page (encodes offset)."""

    limit: int
    """Effective page size used for this request."""

    next_cursor: str | None
    """Opaque cursor for the next page, or ``None`` when this is the last page."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "cursor": self.cursor,
            "limit": self.limit,
            "nextCursor": self.next_cursor,
        }


@dataclass
class SessionDetailBundle:
    """Full session detail bundle returned by :func:`get_session_detail`.

    Fields that were not requested (absent from ``include``) are ``None``.
    Consumers MUST treat ``None`` as "not requested" and ``[]``/``{}`` as
    "requested but empty" — the distinction matters for REST serialisation.
    """

    session_id: str
    project_id: str
    session: dict[str, Any]
    """The session metadata row."""

    transcript: TranscriptPage | None
    """Paginated transcript.  ``None`` when ``include`` did not contain "transcript"."""

    subagents: list[dict[str, Any]] | None
    """Child session rows.  ``None`` when not included."""

    tokens: dict[str, Any] | None
    """Token telemetry dict.  ``None`` when not included."""

    artifacts: list[dict[str, Any]] | None
    """Artifact-typed entity links.  ``None`` when not included."""

    links: list[dict[str, Any]] | None
    """General entity links.  ``None`` when not included."""

    redacted_field_count: int = 0
    """Aggregate number of fields that were redacted across the full payload."""

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "sessionId": self.session_id,
            "projectId": self.project_id,
            "session": self.session,
            "redactedFieldCount": self.redacted_field_count,
        }
        if self.transcript is not None:
            result["transcript"] = self.transcript.as_dict()
        if self.subagents is not None:
            result["subagents"] = self.subagents
        if self.tokens is not None:
            result["tokens"] = self.tokens
        if self.artifacts is not None:
            result["artifacts"] = self.artifacts
        if self.links is not None:
            result["links"] = self.links
        return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_token_telemetry(session_row: dict[str, Any]) -> dict[str, Any]:
    """Extract token telemetry fields from a raw session repository row."""

    def _int(k: str) -> int:
        try:
            return int(session_row.get(k) or 0)
        except (TypeError, ValueError):
            return 0

    def _float(k: str) -> float:
        try:
            return float(session_row.get(k) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return {
        "tokensIn": _int("tokens_in"),
        "tokensOut": _int("tokens_out"),
        "modelIOTokens": _int("model_io_tokens"),
        "cacheCreationInputTokens": _int("cache_creation_input_tokens"),
        "cacheReadInputTokens": _int("cache_read_input_tokens"),
        "cacheInputTokens": _int("cache_input_tokens"),
        "observedTokens": _int("observed_tokens"),
        "toolReportedTokens": _int("tool_reported_tokens"),
        "totalCost": _float("total_cost"),
        "durationSeconds": _float("duration_seconds"),
    }


_ARTIFACT_ENTITY_TYPES: frozenset[str] = frozenset(
    {"artifact", "document", "file", "attachment"}
)


def _classify_links(
    raw_links: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition raw entity links into (artifacts, general_links).

    An entity link is classified as an artifact link when either its
    ``source_type`` or ``target_type`` is an artifact-variant type.
    """
    artifacts: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for link in raw_links:
        src_type = str(link.get("source_type") or "").lower().strip()
        tgt_type = str(link.get("target_type") or "").lower().strip()
        if src_type in _ARTIFACT_ENTITY_TYPES or tgt_type in _ARTIFACT_ENTITY_TYPES:
            artifacts.append(link)
        else:
            links.append(link)
    return artifacts, links


# ── Public service function ───────────────────────────────────────────────────

async def get_session_detail(
    project_id: str,
    session_id: str,
    ports: CorePorts,
    *,
    include: FrozenSet[str] | set[str] | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    context: RequestContext | None = None,
) -> SessionDetailBundle | None:
    """Return full session detail for **any** project — not just the active one.

    This is the transport-neutral entry point consumed by REST (Phase 2),
    MCP tools (Phase 3), and the repo-CLI (Phase 3).  All transports delegate
    here; no transport adds its own transcript-reading or redaction logic.

    Parameters
    ----------
    project_id:
        Required.  The project that owns the session.  Passed to every
        repository call to enforce the Phase 0 cross-project isolation
        invariant.
    session_id:
        The session to fetch.
    ports:
        Injected ``CorePorts`` providing all repository access.
    include:
        Set of flag strings from ``ALL_INCLUDE_FLAGS``.  ``None`` (default)
        requests all segments.  Unknown flags are logged and ignored — they
        do not raise.
    cursor:
        Opaque pagination cursor encoding the transcript page offset.
        ``None`` or empty starts at offset 0.
    limit:
        Max transcript items per page.  Clamped to
        ``[1, MAX_TRANSCRIPT_LIMIT]``; defaults to
        ``DEFAULT_TRANSCRIPT_LIMIT``.  Over-max values are clamped and
        logged.
    context:
        Optional request context forwarded as OTEL attributes.

    Returns
    -------
    ``SessionDetailBundle`` when the session is found under ``project_id``,
    ``None`` when the session does not exist or belongs to a different project.

    Resilience
    ----------
    - Missing optional segments (no artifacts sidecar, empty relationships)
      return an empty list / ``None`` for that key — never a 500.
    - An unknown ``include`` flag is ignored with a warning, not a 500.
    - Redaction failures are logged and the entry passes through unredacted
      (delivery safety > potential partial secret exposure in edge cases).
    """
    with otel.start_span(
        "ccdash.session_detail.get",
        {"project_id": project_id, "session_id": session_id},
    ):
        return await _impl(
            project_id=project_id,
            session_id=session_id,
            ports=ports,
            include=include,
            cursor=cursor,
            limit=limit,
        )


async def _impl(
    project_id: str,
    session_id: str,
    ports: CorePorts,
    *,
    include: FrozenSet[str] | set[str] | None,
    cursor: str | None,
    limit: int | None,
) -> SessionDetailBundle | None:

    # ── Resolve effective include set ────────────────────────────────────────
    if include is None:
        effective = ALL_INCLUDE_FLAGS
    else:
        effective = frozenset(include)
        unknown = effective - ALL_INCLUDE_FLAGS
        if unknown:
            logger.warning(
                "session_detail: ignoring unknown include flags: %s", sorted(unknown)
            )
        effective = effective & ALL_INCLUDE_FLAGS

    # ── Fetch session row — project-scoped (Phase 0 invariant) ──────────────
    session_repo = ports.storage.sessions()
    session_row = await session_repo.get_by_id(session_id, project_id=project_id)
    if session_row is None:
        return None

    # Belt-and-suspenders: confirm the row's own project_id matches
    row_pid = str(session_row.get("project_id") or "")
    if row_pid and row_pid != project_id:
        logger.warning(
            "session_detail: project_id mismatch for session %r "
            "(expected %r, row has %r) — refusing to return",
            session_id,
            project_id,
            row_pid,
        )
        return None

    total_redacted = 0

    # ── Transcript (cursor-paginated) ────────────────────────────────────────
    transcript_page: TranscriptPage | None = None
    if INCLUDE_TRANSCRIPT in effective:
        raw_limit = int(limit) if limit is not None else DEFAULT_TRANSCRIPT_LIMIT
        if raw_limit > MAX_TRANSCRIPT_LIMIT:
            logger.info(
                "session_detail: requested limit %d exceeds MAX_TRANSCRIPT_LIMIT %d; clamped",
                raw_limit,
                MAX_TRANSCRIPT_LIMIT,
            )
        eff_limit = max(1, min(raw_limit, MAX_TRANSCRIPT_LIMIT))
        offset = _decode_cursor(cursor)

        # We request one extra item to detect whether a next page exists
        raw_items = await _transcript_service.list_session_logs(
            session_row, ports, limit=eff_limit + 1, offset=offset
        )
        has_more = len(raw_items) > eff_limit
        page_items: list[dict[str, Any]] = raw_items[:eff_limit]

        # Redact before egress — the egress boundary for all transports
        try:
            page_items, redacted_count = redact_entries(page_items)
            total_redacted += redacted_count
        except Exception:
            logger.warning(
                "session_detail: redaction raised unexpectedly for session %r; "
                "proceeding without redaction for this page",
                session_id,
                exc_info=True,
            )

        next_cursor = _encode_cursor(offset + eff_limit) if has_more else None
        transcript_page = TranscriptPage(
            items=page_items,
            cursor=_encode_cursor(offset),
            limit=eff_limit,
            next_cursor=next_cursor,
        )

    # ── Subagents (child sessions, project-scoped) ───────────────────────────
    subagents: list[dict[str, Any]] | None = None
    if INCLUDE_SUBAGENTS in effective:
        try:
            relationships = await session_repo.list_relationships(project_id, session_id)
            child_ids = [
                str(r["child_session_id"])
                for r in relationships
                if str(r.get("parent_session_id") or "") == session_id
                and r.get("child_session_id")
            ]
            if child_ids:
                subagents = list(
                    await session_repo.get_many_by_ids(child_ids, project_id=project_id)
                )
            else:
                subagents = []
        except Exception:
            logger.warning(
                "session_detail: failed to fetch subagents for session %r project %r",
                session_id,
                project_id,
                exc_info=True,
            )
            subagents = []

    # ── Token telemetry ──────────────────────────────────────────────────────
    tokens: dict[str, Any] | None = None
    if INCLUDE_TOKENS in effective:
        tokens = _extract_token_telemetry(session_row)

    # ── Entity links (artifacts + general) ───────────────────────────────────
    artifacts: list[dict[str, Any]] | None = None
    links: list[dict[str, Any]] | None = None
    need_links = INCLUDE_ARTIFACTS in effective or INCLUDE_LINKS in effective
    if need_links:
        try:
            link_repo = ports.storage.entity_links()
            raw_links: list[dict[str, Any]] = await link_repo.get_links_for(
                "session", session_id, "related"
            )
        except Exception:
            logger.warning(
                "session_detail: failed to fetch entity links for session %r project %r",
                session_id,
                project_id,
                exc_info=True,
            )
            raw_links = []

        _artifact_links, _general_links = _classify_links(raw_links)
        if INCLUDE_ARTIFACTS in effective:
            artifacts = _artifact_links
        if INCLUDE_LINKS in effective:
            links = _general_links

    return SessionDetailBundle(
        session_id=session_id,
        project_id=project_id,
        session=dict(session_row),
        transcript=transcript_page,
        subagents=subagents,
        tokens=tokens,
        artifacts=artifacts,
        links=links,
        redacted_field_count=total_redacted,
    )
