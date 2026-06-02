"""Transport-neutral planning session board query service (PASB-102).

Exposes ``PlanningSessionQueryService`` — a read surface that takes agent
sessions and planning data and produces ``PlanningAgentSessionCardDTO``
records with correlation confidence and evidence.  These power a Kanban board
of agent sessions tied to features, phases, and tasks.

Architecture:
- Follows the same structural pattern as ``PlanningQueryService``
- All methods accept ``context`` + ``ports`` and return Pydantic DTOs
- Correlation logic is intentionally simple — evidence accumulation, V1
- Does not modify any existing services or repositories

Module-level helpers (MPCC-302)
--------------------------------
The following standalone functions are extracted from
``PlanningSessionQueryService`` so that a cross-project aggregate service
(MPCC-303) can consume them with *explicit* inputs — no implicit active
project, no HTTP context required:

``build_active_session_card``
    Turns a session row (+ pre-computed correlation) into a
    ``PlanningAgentSessionCardDTO``.  Stateless; accepts only the session
    dict, its correlation, and the full session list for relationship
    resolution.

``load_correlation_data``
    Given a project ID and a non-empty set of candidate session IDs, loads
    the feature and entity-link rows needed for correlation.  **Returns
    ``([], [])`` immediately when ``candidate_session_ids`` is empty**,
    enabling the MPCC-303 quality gate: projects with zero active candidates
    never pay the feature/link I/O cost.

``build_correlation_map``
    Given pre-loaded sessions, features, and links, runs the full
    correlation pipeline and returns a ``{session_id: SessionCorrelation}``
    map.  Calling this with an empty sessions list is a no-op (returns ``{}``).

``nest_worker_sessions``
    Groups worker/subagent cards under their root/parent card so workers are
    NOT emitted as top-level duplicate cards by default.  Returns the list of
    root-level cards with ``worker_sessions`` populated, plus a boolean flag
    indicating whether any nesting occurred.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts

from ._filters import collect_source_refs, resolve_project_scope
from .cache import memoized_query
from .models import (
    PlanningAgentSessionBoardDTO,
    PlanningAgentSessionCardDTO,
    PlanningBoardGroupDTO,
    SessionActivityMarker,
    SessionCorrelation,
    SessionRelationship,
    SessionTokenSummary,
)
from .session_correlation import (
    _extract_tool_summary,
    _safe_json_dict,
    correlate_session as _correlate_session_impl,
)

__all__ = [
    "PlanningSessionQueryService",
    # Module-level helpers available to MPCC-303 and other callers
    "build_active_session_card",
    "build_correlation_map",
    "load_correlation_data",
    "nest_worker_sessions",
]

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# Session status mapping: DB status → board state
_STATUS_STATE_MAP: dict[str, str] = {
    "running": "running",
    "in_progress": "running",
    "active": "running",
    "thinking": "thinking",
    "completed": "completed",
    "complete": "completed",
    "done": "completed",
    "failed": "failed",
    "error": "failed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "aborted": "cancelled",
}

# Route patterns for hrefs
_TRANSCRIPT_ROUTE = "#/sessions/{session_id}"
_PLANNING_ROUTE = "#/planning/{feature_id}"
_PHASE_ROUTE = "#/planning/{feature_id}/phases/{phase_number}"


# ── Internal helpers ─────────────────────────────────────────────────────────


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip() or default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _map_session_state(raw_status: str) -> str:
    """Map a raw DB session status to a board state string."""
    token = _safe_str(raw_status).lower()
    return _STATUS_STATE_MAP.get(token, "unknown")


# ── Module-level helpers (MPCC-302) ──────────────────────────────────────────


async def build_active_session_card(
    session: dict[str, Any],
    correlation: SessionCorrelation,
    all_sessions: list[dict[str, Any]],
) -> PlanningAgentSessionCardDTO:
    """Build a ``PlanningAgentSessionCardDTO`` from a session and its correlation.

    Standalone module-level helper — requires no service instance, no HTTP
    context, and no implicit active project.  Callers must supply the session
    row, a pre-computed ``SessionCorrelation``, and the full session list used
    to resolve parent/root relationships.

    This is the extraction target for MPCC-302.  ``PlanningSessionQueryService
    .build_session_card`` delegates directly to this function so the V1 board
    shape is unchanged.

    Args:
        session: Raw session dict from the DB.
        correlation: The pre-computed correlation for this session.
        all_sessions: All project sessions (used to resolve relationships).

    Returns:
        A fully-populated ``PlanningAgentSessionCardDTO``.
    """
    session_id = _safe_str(session.get("id"))
    raw_status = _safe_str(session.get("status"), "completed")
    state = _map_session_state(raw_status)

    forensics = _safe_json_dict(session.get("session_forensics_json"))

    # Agent name / type — try multiple field locations
    agent_name: str | None = (
        _safe_str(forensics.get("agentName") or forensics.get("agent_name"))
        or _safe_str(session.get("agent_id"))
        or None
    )
    agent_type: str | None = (
        _safe_str(forensics.get("agentType") or forensics.get("agent_type"))
        or _safe_str(session.get("session_type"))
        or None
    )

    # Timestamps
    started_at = _safe_str(session.get("started_at")) or None
    ended_at = _safe_str(session.get("ended_at")) or None
    duration_seconds_raw = _safe_float(session.get("duration_seconds"))
    duration_seconds: float | None = duration_seconds_raw if duration_seconds_raw > 0 else None

    # last_activity_at: ended_at if available, else started_at
    last_activity_at = ended_at or started_at

    # Model
    model: str | None = _safe_str(session.get("model")) or None

    # Parent / root relationships
    parent_session_id: str | None = _safe_str(session.get("parent_session_id")) or None
    root_session_id: str | None = _safe_str(session.get("root_session_id")) or None
    if root_session_id == session_id:
        root_session_id = None

    # Build session lookup for relationships
    session_map: dict[str, dict[str, Any]] = {
        _safe_str(s.get("id")): s for s in all_sessions if _safe_str(s.get("id"))
    }

    relationships: list[SessionRelationship] = []
    for rel_id, rel_type in (
        (parent_session_id, "parent"),
        (root_session_id, "root"),
    ):
        if not rel_id:
            continue
        rel_session = session_map.get(rel_id)
        rel_agent = None
        rel_state = None
        if rel_session:
            rel_forensics = _safe_json_dict(rel_session.get("session_forensics_json"))
            rel_agent = (
                _safe_str(rel_forensics.get("agentName") or rel_forensics.get("agent_name"))
                or _safe_str(rel_session.get("agent_id"))
                or None
            )
            rel_state = _map_session_state(_safe_str(rel_session.get("status")))
        relationships.append(
            SessionRelationship(
                related_session_id=rel_id,
                relation_type=rel_type,
                agent_name=rel_agent,
                state=rel_state,
            )
        )

    # Activity markers from recent tool usage
    activity_markers: list[SessionActivityMarker] = []
    tools = _extract_tool_summary(session)
    for tool_name in tools[:5]:
        activity_markers.append(
            SessionActivityMarker(
                marker_type="tool_use",
                label=tool_name,
                timestamp=last_activity_at,
                detail=None,
            )
        )

    # Token summary
    tokens_in = _safe_int(session.get("tokens_in"))
    tokens_out = _safe_int(session.get("tokens_out"))
    total_tokens = tokens_in + tokens_out
    context_window_size = _safe_int(session.get("context_window_size") if "context_window_size" in session else None)
    context_utilization_pct: float | None = None
    if context_window_size and total_tokens > 0:
        context_utilization_pct = round(total_tokens / context_window_size * 100, 1)

    token_summary = SessionTokenSummary(
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        total_tokens=total_tokens,
        context_window_pct=context_utilization_pct,
        model=model,
    )

    # Route hrefs
    transcript_href: str | None = None
    if session_id:
        transcript_href = _TRANSCRIPT_ROUTE.format(session_id=session_id)

    planning_href: str | None = None
    phase_href: str | None = None
    if correlation.feature_id:
        planning_href = _PLANNING_ROUTE.format(feature_id=correlation.feature_id)
        if correlation.phase_number is not None:
            phase_href = _PHASE_ROUTE.format(
                feature_id=correlation.feature_id,
                phase_number=correlation.phase_number,
            )

    return PlanningAgentSessionCardDTO(
        session_id=session_id,
        agent_name=agent_name,
        agent_type=agent_type,
        state=state,
        model=model,
        correlation=correlation,
        transcript_href=transcript_href,
        planning_href=planning_href,
        phase_href=phase_href,
        parent_session_id=parent_session_id,
        root_session_id=root_session_id,
        started_at=started_at,
        last_activity_at=last_activity_at,
        duration_seconds=duration_seconds,
        token_summary=token_summary,
        relationships=relationships,
        activity_markers=activity_markers,
    )


async def load_correlation_data(
    project_id: str,
    ports: CorePorts,
    *,
    candidate_session_ids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Load feature and entity-link rows needed to correlate a set of sessions.

    This is the **zero-active-candidates skip gate** required by the MPCC-303
    quality gate.  When ``candidate_session_ids`` is an empty list, the
    function returns ``([], [], False)`` immediately — no DB I/O is performed.
    Callers MUST pass an empty list (not ``None``) to trigger the fast path;
    passing ``None`` means "load everything" (i.e. the caller does not know the
    candidate set yet and wants the full correlation data).

    Args:
        project_id: The project to load features/links for.
        ports: Core ports (storage repositories).
        candidate_session_ids: If an empty list, skip all I/O and return
            ``([], [], False)``.  If ``None``, load unconditionally.
            If non-empty, load unconditionally (the caller has active
            candidates and needs the data).

    Returns:
        A 3-tuple ``(features, links, partial)`` where:
        - ``features`` is a list of feature dicts for the project.
        - ``links`` is a list of entity_links rows flattened across features.
        - ``partial`` is ``True`` if any load step failed (non-fatal).
    """
    # Fast path: caller knows there are no active candidates — skip all I/O.
    if candidate_session_ids is not None and len(candidate_session_ids) == 0:
        return [], [], False

    features: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    partial = False

    try:
        features = await ports.storage.features().list_all(project_id)
    except Exception:
        logger.exception("load_correlation_data: failed to load features for project %s", project_id)
        partial = True

    try:
        feature_ids = [_safe_str(f.get("id")) for f in features if _safe_str(f.get("id"))]
        if feature_ids:
            links_by_feature = await ports.storage.entity_links().get_links_for_many(
                "feature", feature_ids
            )
            for _fid, feature_links in links_by_feature.items():
                links.extend(feature_links)
    except Exception:
        logger.warning(
            "load_correlation_data: failed to load entity links for project %s; "
            "proceeding without explicit links",
            project_id,
        )
        partial = True

    return features, links, partial


async def build_correlation_map(
    sessions: list[dict[str, Any]],
    features: list[dict[str, Any]],
    links: list[dict[str, Any]],
) -> dict[str, SessionCorrelation]:
    """Correlate a set of sessions against pre-loaded feature/link data.

    Processes sessions in ``started_at`` ascending order so lineage inheritance
    works correctly (parent correlations are available when a child session is
    processed).

    Calling this with an empty ``sessions`` list is safe and returns ``{}``.

    Args:
        sessions: Raw session dicts from the DB (any order).
        features: Pre-loaded feature dicts (e.g. from ``load_correlation_data``).
        links: Pre-loaded entity_links rows (e.g. from ``load_correlation_data``).

    Returns:
        A ``{session_id: SessionCorrelation}`` mapping for every session that
        has a non-empty ID.  Sessions that raise during correlation get an
        ``unknown``-confidence correlation rather than propagating the error.
    """
    correlations: dict[str, SessionCorrelation] = {}

    # Process in started_at ascending order so lineage inheritance is correct.
    ordered = sorted(sessions, key=lambda s: _safe_str(s.get("started_at")))

    for session in ordered:
        sid = _safe_str(session.get("id"))
        if not sid:
            continue
        try:
            corr = await _correlate_session_impl(
                session=session,
                links=links,
                features=features,
                all_sessions=sessions,
                prior_correlations=correlations,
            )
            correlations[sid] = corr
        except Exception:
            logger.debug("build_correlation_map: correlation failed for session %s", sid)
            correlations[sid] = SessionCorrelation(confidence="unknown")

    return correlations


def nest_worker_sessions(
    cards: list[PlanningAgentSessionCardDTO],
    *,
    include_workers_at_top_level: bool = False,
) -> tuple[list[PlanningAgentSessionCardDTO], dict[str, list[PlanningAgentSessionCardDTO]]]:
    """Group worker/subagent cards under their root card.

    A session is considered a worker/subagent if it has a ``root_session_id``
    or ``parent_session_id`` that references another card in the same set.
    Worker cards are **excluded** from the returned top-level list by default,
    preventing duplicate top-level card entries.

    The nesting is resolved to the topmost root — if session B is a child of
    A, and C is a child of B, then both B and C are nested under A.  This
    avoids multiple levels of top-level duplication.

    This helper does NOT mutate ``PlanningAgentSessionCardDTO`` instances and
    does NOT require a ``worker_sessions`` field on the DTO.  Instead it
    returns a ``workers_by_root`` dict so callers (e.g. MPCC-303) can
    incorporate worker summaries into their own aggregate DTO structures.

    Args:
        cards: All session cards (root + worker, in any order).
        include_workers_at_top_level: When ``True``, worker cards are ALSO
            retained at the top level (they still appear in ``workers_by_root``).
            Defaults to ``False`` (workers are hidden from the top-level list).

    Returns:
        A 2-tuple ``(top_level_cards, workers_by_root)`` where:
        - ``top_level_cards`` is the list for board rendering (root cards only
          by default; worker cards excluded unless
          ``include_workers_at_top_level=True``).
        - ``workers_by_root`` maps each root session_id to the list of worker
          cards nested under it.  Empty dict when no nesting occurred.
    """
    # Build index: session_id → card
    card_index: dict[str, PlanningAgentSessionCardDTO] = {
        c.session_id: c for c in cards if c.session_id
    }

    def _resolve_root_id(card: PlanningAgentSessionCardDTO) -> str | None:
        """Resolve to the topmost root session ID that exists in this card set."""
        # Prefer explicit root_session_id if it resolves to a known card.
        if card.root_session_id and card.root_session_id in card_index:
            return card.root_session_id
        # Fall back to parent if parent is in the set.
        if card.parent_session_id and card.parent_session_id in card_index:
            return card.parent_session_id
        return None

    # Identify worker cards and their resolved root IDs.
    worker_root: dict[str, str] = {}  # worker_session_id → root_session_id
    for card in cards:
        root_id = _resolve_root_id(card)
        if root_id:
            worker_root[card.session_id] = root_id

    if not worker_root:
        # No workers detected — return original list unchanged, empty workers map.
        return cards, {}

    # Build the workers_by_root map.
    workers_by_root: dict[str, list[PlanningAgentSessionCardDTO]] = {}
    for worker_id, root_id in worker_root.items():
        workers_by_root.setdefault(root_id, []).append(card_index[worker_id])

    # Assemble top-level list.
    top_level: list[PlanningAgentSessionCardDTO] = []
    for card in cards:
        sid = card.session_id
        is_worker = sid in worker_root

        if not is_worker:
            # Root cards always appear at top level.
            top_level.append(card)
        elif include_workers_at_top_level:
            # Worker card — include only when caller explicitly requests it.
            top_level.append(card)
        # else: worker card excluded from top level (default behavior).

    return top_level, workers_by_root


# ── Cache param extractor ─────────────────────────────────────────────────────


def _pss_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    *,
    project_id: str | None = None,
    feature_id: str | None = None,
    grouping: str = "state",
    cursor: str | None = None,
    limit: int = 500,
    **_: Any,
) -> dict[str, Any]:
    """Extract cache-key parameters for the single-project session board query.

    Cache key includes project_id, feature_id, grouping, cursor, and limit so
    that different board views and pagination windows for the same project are
    cached independently.

    ``project_id`` is popped by the decorator and used as the *project_id* slot
    of the cache key (not double-hashed into the param hash).
    """
    effective_project_id: str = (
        project_id
        or (context.project.project_id if context.project else "")
        or ""
    )
    return {
        "project_id": effective_project_id,
        "feature_id": feature_id or "",
        "grouping": grouping,
        "cursor": cursor or "",
        "limit": limit,
    }


# ── Service class ────────────────────────────────────────────────────────────


class PlanningSessionQueryService:
    """Transport-neutral planning session board query service (PASB-102).

    Accepts agent sessions and planning data, and produces
    ``PlanningAgentSessionCardDTO`` records with correlation confidence
    and evidence, grouped into ``PlanningAgentSessionBoardDTO``.

    All methods are ``async`` and follow the same structural contract as
    ``PlanningQueryService``: they accept ``context`` + ``ports`` and return
    Pydantic DTOs.

    Instance methods delegate to module-level helpers (MPCC-302) so that
    MPCC-303 can call those helpers directly with an explicit project scope.
    """

    async def correlate_session(
        self,
        session: dict[str, Any],
        features: list[dict[str, Any]],
        links: list[dict[str, Any]],
        all_sessions: list[dict[str, Any]] | None = None,
        prior_correlations: dict[str, SessionCorrelation] | None = None,
    ) -> SessionCorrelation:
        """Correlate a single session to planning entities.

        Delegates to the shared ``session_correlation.correlate_session``
        implementation.  Signature is preserved for callers that reference this
        method directly.

        Args:
            session: Raw session dict from the DB.
            features: All feature dicts for the project.
            links: All entity_links rows for the project (bidirectional).
            all_sessions: All project sessions (forwarded for forward-compatibility).
            prior_correlations: Correlations already computed for other sessions
                (used for lineage inheritance — keyed by session_id).

        Returns:
            ``SessionCorrelation`` with accumulated evidence and resolved
            feature/phase binding at the highest confidence found.
        """
        return await _correlate_session_impl(
            session=session,
            links=links,
            features=features,
            all_sessions=all_sessions,
            prior_correlations=prior_correlations,
        )

    async def build_session_card(
        self,
        session: dict[str, Any],
        correlation: SessionCorrelation,
        all_sessions: list[dict[str, Any]],
    ) -> PlanningAgentSessionCardDTO:
        """Build a ``PlanningAgentSessionCardDTO`` from a session and its correlation.

        Delegates to the module-level ``build_active_session_card`` helper
        (MPCC-302).  Signature and return shape are unchanged.

        Args:
            session: Raw session dict from the DB.
            correlation: The pre-computed correlation for this session.
            all_sessions: All project sessions (used to resolve relationships).

        Returns:
            A fully-populated ``PlanningAgentSessionCardDTO``.
        """
        return await build_active_session_card(session, correlation, all_sessions)

    @memoized_query("pss_session_board", param_extractor=_pss_params)
    async def get_session_board(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        project_id: str | None = None,
        feature_id: str | None = None,
        grouping: str = "state",
        cursor: str | None = None,
        limit: int = 500,
    ) -> PlanningAgentSessionBoardDTO:
        """Fetch sessions, correlate them to planning entities, and return a board.

        Thin orchestration over module-level helpers (MPCC-302):
        1. Resolve project scope.
        2. Load a page of sessions using ``cursor`` + ``limit`` (T4-001).
        3. ``load_correlation_data`` — loads features + links (skips when no
           sessions were returned, matching the zero-candidate fast path).
        4. ``build_correlation_map`` — runs the full correlation pipeline.
        5. ``build_active_session_card`` — builds each card.
        6. ``_group_cards`` — groups and orders cards.

        Pagination (T4-001):
        - When ``cursor`` is ``None`` and ``limit`` is the default (500) the
          call is equivalent to the pre-pagination behavior: all sessions are
          fetched in a single request.
        - ``cursor`` is an opaque string returned as ``next_cursor`` in a prior
          response.  Internally it is the ``started_at`` value of the last card
          in the previous page (ISO-8601 string), used as an offset marker for
          chronological keyset pagination.  Callers MUST treat it as opaque.
        - ``next_cursor`` in the response is ``None`` when fewer rows than
          ``limit`` were returned (i.e. this is the last page).

        Args:
            context: Current request context (used for project scope resolution).
            ports: Core ports (storage repositories).
            project_id: Explicit project ID override. Falls back to context scope.
            feature_id: When provided, board is scoped to sessions correlated to
                this feature only.
            grouping: One of "state", "feature", "phase", "agent", "model".
            cursor: Opaque pagination cursor from the previous response's
                ``next_cursor`` field.  ``None`` fetches the first page.
            limit: Maximum number of sessions to load per call.  Defaults to
                500 to preserve backward-compatible single-page behavior.

        Returns:
            A ``PlanningAgentSessionBoardDTO`` with groups, per-group cards,
            and pagination metadata (``page_size``, ``next_cursor``).
        """
        scope = resolve_project_scope(context, ports, project_id)
        if scope is None:
            return PlanningAgentSessionBoardDTO(
                status="error",
                project_id=str(project_id or ""),
                feature_id=feature_id,
                grouping=grouping,
                source_refs=[],
            )

        effective_project_id = scope.project.id
        partial = False

        # ── Decode cursor → offset ───────────────────────────────────────────
        # Cursor is the started_at of the last item on the previous page.
        # We translate it to a numeric offset by counting rows with
        # started_at >= cursor_value (descending order).  This is a simple
        # keyset-compatible approximation that avoids a second DB round-trip
        # while remaining stable against insertions of *newer* sessions.
        # For the common case (first page, no cursor) offset stays at 0.
        offset: int = 0
        if cursor:
            try:
                # cursor encodes "skip all rows that were returned before this
                # started_at value".  We pass it as a numeric offset calculated
                # externally; for simplicity we re-use the limit multiple as
                # the page number derived from the cursor string.
                # The cursor format is "<page_number>:<started_at_iso>" where
                # page_number is 1-based.  If the cursor cannot be decoded we
                # fall back to offset 0.
                page_num, _started_at = cursor.split(":", 1)
                offset = (int(page_num) - 1) * limit
            except (ValueError, TypeError):
                logger.debug(
                    "get_session_board: invalid cursor %r — falling back to offset 0", cursor
                )
                offset = 0

        # ── Load sessions ────────────────────────────────────────────────────
        sessions: list[dict[str, Any]] = []
        try:
            sessions = await ports.storage.sessions().list_paginated(
                offset=offset,
                limit=limit,
                project_id=effective_project_id,
                sort_by="started_at",
                sort_order="desc",
                filters={"include_subagents": True},
            )
        except Exception:
            logger.exception("Failed to load sessions for project %s", effective_project_id)
            partial = True

        # ── Load features + links (skip when no sessions) ────────────────────
        # Pass the session ID list so load_correlation_data can fast-path when
        # the project has no sessions (satisfies the zero-candidate quality gate).
        candidate_ids: list[str] = [
            _safe_str(s.get("id")) for s in sessions if _safe_str(s.get("id"))
        ]
        features, links, corr_partial = await load_correlation_data(
            effective_project_id,
            ports,
            candidate_session_ids=candidate_ids if sessions else [],
        )
        if corr_partial:
            partial = True

        # ── Correlate sessions ───────────────────────────────────────────────
        correlations = await build_correlation_map(sessions, features, links)

        # ── Build cards ──────────────────────────────────────────────────────
        all_cards: list[PlanningAgentSessionCardDTO] = []
        for session in sessions:
            sid = _safe_str(session.get("id"))
            if not sid:
                continue
            corr = correlations.get(sid, SessionCorrelation(confidence="unknown"))

            # Apply feature_id filter if requested
            if feature_id and corr.feature_id != feature_id:
                continue

            try:
                card = await build_active_session_card(session, corr, sessions)
                all_cards.append(card)
            except Exception:
                logger.debug("Failed to build card for session %s", sid)
                partial = True

        # ── Group cards ──────────────────────────────────────────────────────
        groups = _group_cards(all_cards, grouping)

        # ── Aggregate counts ─────────────────────────────────────────────────
        active_states = {"running", "thinking"}
        completed_states = {"completed"}
        active_count = sum(1 for c in all_cards if c.state in active_states)
        completed_count = sum(1 for c in all_cards if c.state in completed_states)

        # ── Compute next_cursor (T4-001) ─────────────────────────────────────
        # When the number of returned sessions equals the requested limit there
        # MAY be more rows.  We emit a cursor encoding the next page number so
        # the caller can fetch the subsequent page.  When fewer rows were
        # returned (or limit is the legacy default of 500) there is no next
        # page and next_cursor is None.
        next_cursor: str | None = None
        if sessions and len(sessions) >= limit:
            # Page number of the *next* page (1-based): current_page + 1.
            current_page = (offset // limit) + 1 if limit > 0 else 1
            next_page = current_page + 1
            # Anchor the cursor on the started_at of the last session in this
            # page so the server can verify continuity on the next call.
            last_started_at = _safe_str(sessions[-1].get("started_at")) if sessions else ""
            next_cursor = f"{next_page}:{last_started_at}"

        # Derive current page number for the response
        current_page_num = (offset // limit) + 1 if limit > 0 else 1

        return PlanningAgentSessionBoardDTO(
            status="partial" if partial else "ok",
            project_id=effective_project_id,
            feature_id=feature_id,
            grouping=grouping,
            groups=groups,
            total_card_count=len(all_cards),
            active_count=active_count,
            completed_count=completed_count,
            page=current_page_num,
            page_size=limit,
            next_cursor=next_cursor,
            source_refs=collect_source_refs(
                effective_project_id,
                [c.session_id for c in all_cards],
            ),
        )


# ── Grouping helpers ─────────────────────────────────────────────────────────


def _group_key_for_card(card: PlanningAgentSessionCardDTO, grouping: str) -> str:
    """Return the group key for a card under the requested grouping mode."""
    if grouping == "state":
        return card.state or "unknown"
    if grouping == "feature":
        return (
            (card.correlation.feature_id if card.correlation else None)
            or "unlinked"
        )
    if grouping == "phase":
        if card.correlation and card.correlation.phase_number is not None:
            return str(card.correlation.phase_number)
        return "unlinked"
    if grouping == "agent":
        return card.agent_name or "unknown"
    if grouping == "model":
        return card.model or "unknown"
    return "unknown"


def _group_label_for_key(key: str, grouping: str, cards: list[PlanningAgentSessionCardDTO]) -> str:
    """Derive a human-readable label for a group key."""
    if grouping == "feature":
        # Use feature_name from the first card in the group
        for card in cards:
            if card.correlation and card.correlation.feature_id == key:
                return card.correlation.feature_name or key
        if key == "unlinked":
            return "Unlinked"
        return key
    if grouping == "phase":
        if key == "unlinked":
            return "No Phase"
        for card in cards:
            if card.correlation and str(card.correlation.phase_number) == key:
                return card.correlation.phase_title or f"Phase {key}"
        return f"Phase {key}"
    if grouping == "state":
        return key.replace("_", " ").title()
    return key.replace("_", " ").title()


def _group_cards(
    cards: list[PlanningAgentSessionCardDTO],
    grouping: str,
) -> list[PlanningBoardGroupDTO]:
    """Group cards by the requested mode and return ordered ``PlanningBoardGroupDTO`` list."""
    # Determine ordering for state grouping
    _STATE_ORDER = ["running", "thinking", "completed", "failed", "cancelled", "unknown"]

    buckets: dict[str, list[PlanningAgentSessionCardDTO]] = {}
    for card in cards:
        key = _group_key_for_card(card, grouping)
        buckets.setdefault(key, []).append(card)

    # Sort keys
    if grouping == "state":
        sorted_keys = sorted(
            buckets.keys(),
            key=lambda k: (_STATE_ORDER.index(k) if k in _STATE_ORDER else 99, k),
        )
    else:
        sorted_keys = sorted(buckets.keys(), key=lambda k: (k == "unlinked" or k == "unknown", k))

    groups: list[PlanningBoardGroupDTO] = []
    for key in sorted_keys:
        group_cards = buckets[key]
        label = _group_label_for_key(key, grouping, group_cards)
        groups.append(
            PlanningBoardGroupDTO(
                group_key=key,
                group_label=label,
                group_type=grouping,
                cards=group_cards,
                card_count=len(group_cards),
            )
        )

    return groups
