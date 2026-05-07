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
"""
from __future__ import annotations

import logging
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts

from ._filters import collect_source_refs, resolve_project_scope
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

__all__ = ["PlanningSessionQueryService"]

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


# ── Service class ────────────────────────────────────────────────────────────


class PlanningSessionQueryService:
    """Transport-neutral planning session board query service (PASB-102).

    Accepts agent sessions and planning data, and produces
    ``PlanningAgentSessionCardDTO`` records with correlation confidence
    and evidence, grouped into ``PlanningAgentSessionBoardDTO``.

    All methods are ``async`` and follow the same structural contract as
    ``PlanningQueryService``: they accept ``context`` + ``ports`` and return
    Pydantic DTOs.
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

        Maps session DB columns to card fields, builds relationship links,
        activity markers from recent tools, token summary, and route hrefs.

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

    async def get_session_board(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        project_id: str | None = None,
        feature_id: str | None = None,
        grouping: str = "state",
    ) -> PlanningAgentSessionBoardDTO:
        """Fetch all sessions, correlate them to planning entities, and return a board.

        Loads sessions and features from the DB, correlates each session,
        builds cards, groups them by the requested grouping mode, and returns
        a ``PlanningAgentSessionBoardDTO``.

        Args:
            context: Current request context (used for project scope resolution).
            ports: Core ports (storage repositories).
            project_id: Explicit project ID override. Falls back to context scope.
            feature_id: When provided, board is scoped to sessions correlated to
                this feature only.
            grouping: One of "state", "feature", "phase", "agent", "model".

        Returns:
            A ``PlanningAgentSessionBoardDTO`` with groups and per-group cards.
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

        # ── Load sessions ────────────────────────────────────────────────────
        sessions: list[dict[str, Any]] = []
        try:
            sessions = await ports.storage.sessions().list_paginated(
                offset=0,
                limit=500,
                project_id=effective_project_id,
                sort_by="started_at",
                sort_order="desc",
                filters={"include_subagents": True},
            )
        except Exception:
            logger.exception("Failed to load sessions for project %s", effective_project_id)
            partial = True

        # ── Load features ────────────────────────────────────────────────────
        features: list[dict[str, Any]] = []
        try:
            features = await ports.storage.features().list_all(effective_project_id)
        except Exception:
            logger.exception("Failed to load features for project %s", effective_project_id)
            partial = True

        # ── Load entity links for session→feature bindings ───────────────────
        links: list[dict[str, Any]] = []
        try:
            # Bulk load links for all features in a single query to avoid N+1.
            feature_ids = [_safe_str(f.get("id")) for f in features if _safe_str(f.get("id"))]
            if feature_ids:
                links_by_feature = await ports.storage.entity_links().get_links_for_many(
                    "feature", feature_ids
                )
                for fid, feature_links in links_by_feature.items():
                    links.extend(feature_links)
        except Exception:
            logger.warning(
                "planning-sessions: failed to load entity links for project %s; proceeding without explicit links",
                effective_project_id,
            )
            partial = True

        # ── Correlate sessions ───────────────────────────────────────────────
        correlations: dict[str, SessionCorrelation] = {}
        # Process sessions in started_at order (ascending) so lineage works correctly
        ordered_sessions = sorted(
            sessions,
            key=lambda s: _safe_str(s.get("started_at")),
        )

        for session in ordered_sessions:
            sid = _safe_str(session.get("id"))
            if not sid:
                continue
            try:
                corr = await self.correlate_session(
                    session,
                    features,
                    links,
                    all_sessions=sessions,
                    prior_correlations=correlations,
                )
                correlations[sid] = corr
            except Exception:
                logger.debug("Correlation failed for session %s", sid)
                correlations[sid] = SessionCorrelation(confidence="unknown")

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
                card = await self.build_session_card(session, corr, sessions)
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

        return PlanningAgentSessionBoardDTO(
            status="partial" if partial else "ok",
            project_id=effective_project_id,
            feature_id=feature_id,
            grouping=grouping,
            groups=groups,
            total_card_count=len(all_cards),
            active_count=active_count,
            completed_count=completed_count,
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
