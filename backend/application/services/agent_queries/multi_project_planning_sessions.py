"""Multi-Project Active-Session Board aggregate service.

Implements MPCC-303: ``MultiProjectActiveSessionBoardQueryService`` fans out
across all registered projects using *active-only* repository queries, loads
feature/link correlation data only for projects with live candidates, nests
worker sessions under their root cards, and groups the result into
``AggregateBoardGroup`` columns.

Design principles
-----------------
- **No full-board loads**: the service NEVER calls ``get_session_board`` per
  project.  Active candidates are fetched via
  ``sessions_repo.list_active(project_id, ...)`` — a lightweight indexed query.
- **Zero-candidate skip gate**: when a project's ``list_active`` returns an
  empty list the service passes ``candidate_session_ids=[]`` to
  ``load_correlation_data``, which returns ``([], [], False)`` immediately
  without any DB I/O.  Cold projects pay zero correlation cost.
- **Worker nesting**: ``nest_worker_sessions(cards, include_workers_at_top_level=False)``
  ensures workers appear only under their root card's
  ``AggregateSessionCard.workers`` list, never as duplicate top-level entries.
- **Bounded fan-out**: asyncio.Semaphore caps concurrency to avoid saturating
  the shared SQLite connection during large project sweeps.
- **Cache**: ``@memoized_query`` mirrors the Phase 2 service key/TTL
  conventions.  The cache key encodes group_by, filters, window, workers
  toggle, pagination, and project scope.
- **Partial failure isolation**: a failing project emits a ``ProjectWarning``
  and does not abort other projects.

Grouping keys
-------------
Mirrors the V1 session board grouping modes plus the aggregate-specific
``"project"`` key:

    "state"   — card.state (running / thinking / completed / failed / …)
    "feature" — correlated feature_id ("unlinked" when none)
    "phase"   — correlated phase_number ("unlinked" when none)
    "agent"   — card.agent_name ("unknown" when absent)
    "model"   — card.model ("unknown" when absent)
    "project" — project_id (aggregate-specific; groups by source project)
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Sequence

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.agent_queries.models import (
    PlanningAgentSessionCardDTO,
    SessionCorrelation,
)
from backend.application.services.agent_queries.planning_sessions import (
    build_active_session_card,
    build_correlation_map,
    load_correlation_data,
    nest_worker_sessions,
)
from backend.application.services.agent_queries.system_metrics import (
    _compute_is_stale,
    _query_max_updated_at,
)
from backend.models import (
    AggregateBoardGroup,
    AggregatePagination,
    AggregateSessionCard,
    AggregateSessionWorkerSummary,
    MultiProjectSessionBoardResponse,
    Project,
    ProjectDisplayMetadata,
    ProjectIdentityFields,
    ProjectSummary,
    ProjectWarning,
    ProjectWorkItemCounts,
)
from backend.project_manager import resolve_display_metadata

from .cache import memoized_query

logger = logging.getLogger(__name__)

# ── Concurrency guard ─────────────────────────────────────────────────────────
# Mirrors the pattern used by MultiProjectPlanningCommandCenterQueryService and
# SystemMetricsQueryService.
_MAX_CONCURRENCY: int = getattr(config, "CCDASH_SYSTEM_METRICS_CONCURRENCY", 4)

# Active-session window for the portfolio board.  Wider than the 600s live-agents
# window so recently-indexed sessions (hours / days old) appear in the aggregate
# board while multi-month phantom rows are still excluded.  Defaults to 30 days.
# NOTE: the single-project board is intentionally NOT affected by this constant.
_ACTIVE_SESSION_WINDOW: int = getattr(
    config, "CCDASH_PLANNING_PORTFOLIO_ACTIVE_WINDOW_SECONDS", 30 * 24 * 60 * 60
)

# Valid grouping keys (V1 keys + aggregate-specific "project" key).
_VALID_GROUPINGS = frozenset({"state", "feature", "phase", "agent", "model", "project"})

# State ordering for "state" grouping (mirrors V1).
_STATE_ORDER = ["running", "thinking", "completed", "failed", "cancelled", "unknown"]


# ── Cache param extractor ─────────────────────────────────────────────────────

def _mpss_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    *,
    group_by: str = "state",
    project_ids: Sequence[str] | None = None,
    group_filter: str | None = None,
    feature_id: str | None = None,
    state_filter: str | None = None,
    window_seconds: int | None = None,
    include_workers: bool = True,
    page: int = 1,
    page_size: int = 50,
    **_: Any,
) -> dict[str, Any]:
    """Extract cache-key parameters for the aggregate session-board query.

    Project scope is "global" — the decorator maps to the 'global' key slot.
    """
    return {
        "group_by": group_by,
        "project_ids": sorted(project_ids) if project_ids else [],
        "group_filter": group_filter or "",
        "feature_id": feature_id or "",
        "state_filter": state_filter or "",
        "window_seconds": window_seconds if window_seconds is not None else _ACTIVE_SESSION_WINDOW,
        "include_workers": include_workers,
        "page": page,
        "page_size": page_size,
    }


# ── Per-project active-session collection ────────────────────────────────────

async def _collect_project_active_sessions(
    ports: CorePorts,
    project: Project,
    semaphore: asyncio.Semaphore,
    *,
    window_seconds: int,
    include_subagents: bool,
    limit: int | None,
) -> tuple[str, list[dict[str, Any]], bool, list[str]]:
    """Fetch active session rows for a single project.

    Returns ``(project_id, rows, partial, warnings)``.  On error returns an
    empty rows list with ``partial=True`` so other projects still proceed.

    Zero-candidate fast path
    ------------------------
    This function only calls ``list_active`` — it does NOT call
    ``get_session_board``.  If ``list_active`` returns an empty list the
    caller will detect this and skip correlation I/O entirely.
    """
    async with semaphore:
        try:
            sessions_repo = ports.storage.sessions()
            rows = await sessions_repo.list_active(
                project.id,
                window_seconds=window_seconds,
                limit=limit,
                include_subagents=include_subagents,
            )
            return project.id, rows, False, []
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "mpss: list_active failed for project=%s: %s",
                project.id,
                exc,
            )
            return project.id, [], True, [str(exc)]


# ── Per-project card building ─────────────────────────────────────────────────

async def _build_project_cards(
    ports: CorePorts,
    project: Project,
    active_rows: list[dict[str, Any]],
    semaphore: asyncio.Semaphore,
) -> tuple[str, list[PlanningAgentSessionCardDTO], bool, list[str]]:
    """Build session cards for one project from its pre-loaded active rows.

    Zero-candidate gate: when ``active_rows`` is empty the function invokes
    ``load_correlation_data`` with ``candidate_session_ids=[]``, which returns
    ``([], [], False)`` immediately without any DB I/O.

    Returns ``(project_id, cards, partial, warnings)``.
    """
    async with semaphore:
        candidate_ids: list[str] = [
            str(r.get("id", "")) for r in active_rows if r.get("id")
        ]

        # Zero-candidate skip gate — passes empty list to trigger fast path.
        features, links, corr_partial = await load_correlation_data(
            project.id,
            ports,
            candidate_session_ids=candidate_ids if active_rows else [],
        )
        partial = corr_partial

        if not active_rows:
            # No correlation I/O was performed; return immediately.
            return project.id, [], partial, []

        correlations = await build_correlation_map(active_rows, features, links)

        cards: list[PlanningAgentSessionCardDTO] = []
        warnings: list[str] = []
        for session in active_rows:
            sid = str(session.get("id", ""))
            if not sid:
                continue
            corr = correlations.get(sid, SessionCorrelation(confidence="unknown"))
            try:
                card = await build_active_session_card(session, corr, active_rows)
                cards.append(card)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "mpss: failed to build card for session=%s project=%s: %s",
                    sid,
                    project.id,
                    exc,
                )
                partial = True

        return project.id, cards, partial, warnings


# ── Project summary rollup ────────────────────────────────────────────────────

async def _build_session_project_summary(
    ports: CorePorts,
    project: Project,
    active_card_count: int,
    partial: bool,
    warnings: list[str],
    semaphore: asyncio.Semaphore,
    display_metadata: ProjectDisplayMetadata,
    *,
    window_seconds: int | None = None,
) -> ProjectSummary:
    """Build a ``ProjectSummary`` for a project in the session board context.

    Mirrors the Phase 2 ``_build_project_summary`` approach:
    - Uses ``sessions_repo.count_active`` for the active-session count (avoids
      a full board load).
    - Derives freshness and staleness from ``_query_max_updated_at`` /
      ``_compute_is_stale`` from system_metrics.

    The ``active_sessions`` count in the summary is the live count (from the
    repo primitive), which may differ from ``active_card_count`` when the
    window or include_subagents params diverge.
    """
    async with semaphore:
        active_sessions = 0
        last_updated: str | None = None
        freshness_seconds: int | None = None
        is_stale: bool | None = None
        error_msg: str | None = None

        effective_window = window_seconds if window_seconds is not None else _ACTIVE_SESSION_WINDOW
        if partial and not active_card_count:
            error_msg = "; ".join(warnings) if warnings else "Project session data unavailable"
        else:
            try:
                sessions_repo = ports.storage.sessions()
                active_sessions = await sessions_repo.count_active(
                    project.id,
                    window_seconds=effective_window,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "mpss summary: count_active failed for project=%s: %s",
                    project.id,
                    exc,
                )

            try:
                db = ports.storage.db
                max_updated = await _query_max_updated_at(db, project.id)
                if max_updated is not None:
                    last_updated = max_updated.isoformat()
                    age = datetime.now(timezone.utc) - max_updated
                    freshness_seconds = int(age.total_seconds())
                is_stale = _compute_is_stale(max_updated)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "mpss summary: freshness query failed for project=%s: %s",
                    project.id,
                    exc,
                )

        counts = ProjectWorkItemCounts(
            work_items=0,   # session board doesn't count work items
            blocked=0,
            review=0,
            stale=0,
            active_sessions=active_sessions,
            errors=0,
        )

        return ProjectSummary(
            project_id=project.id,
            name=project.name,
            display_metadata=display_metadata,
            counts=counts,
            is_stale=is_stale,
            error=error_msg,
            last_updated=last_updated,
            freshness_seconds=freshness_seconds,
        )


# ── Identity helpers ──────────────────────────────────────────────────────────

def _make_project_identity(
    project: Project,
    display_metadata: ProjectDisplayMetadata,
) -> ProjectIdentityFields:
    return ProjectIdentityFields(
        project_id=project.id,
        project_name=project.name,
        project_color=display_metadata.color,
        project_group=display_metadata.group,
    )


# ── Worker-summary mapping ────────────────────────────────────────────────────

def _card_to_worker_summary(card: PlanningAgentSessionCardDTO) -> AggregateSessionWorkerSummary:
    """Convert a worker ``PlanningAgentSessionCardDTO`` to a compact summary."""
    return AggregateSessionWorkerSummary(
        session_id=card.session_id,
        agent_name=card.agent_name,
        state=card.state or "unknown",
        model=card.model,
        started_at=card.started_at,
        last_activity_at=card.last_activity_at,
        duration_seconds=card.duration_seconds,
    )


# ── Aggregate-card assembly ───────────────────────────────────────────────────

def _make_aggregate_card(
    card: PlanningAgentSessionCardDTO,
    workers: list[PlanningAgentSessionCardDTO],
    identity: ProjectIdentityFields,
) -> AggregateSessionCard:
    """Wrap a root card + its workers into an ``AggregateSessionCard``."""
    worker_summaries = [_card_to_worker_summary(w) for w in workers]
    return AggregateSessionCard(
        project=identity,
        card=card.model_dump(mode="json"),
        workers=worker_summaries,
    )


# ── Grouping helpers ──────────────────────────────────────────────────────────

def _group_key_for_aggregate_card(
    agg_card: AggregateSessionCard,
    group_by: str,
) -> str:
    """Derive the group key for an ``AggregateSessionCard``."""
    if group_by == "project":
        return agg_card.project.project_id

    # For non-project groupings, read from the embedded card dict.
    card_dict = agg_card.card

    if group_by == "state":
        return str(card_dict.get("state") or "unknown")

    if group_by == "feature":
        corr = card_dict.get("correlation") or {}
        fid = (corr.get("feature_id") or "") if isinstance(corr, dict) else ""
        return fid or "unlinked"

    if group_by == "phase":
        corr = card_dict.get("correlation") or {}
        if isinstance(corr, dict):
            pnum = corr.get("phase_number")
            if pnum is not None:
                return str(pnum)
        return "unlinked"

    if group_by == "agent":
        return str(card_dict.get("agent_name") or "unknown")

    if group_by == "model":
        return str(card_dict.get("model") or "unknown")

    return "unknown"


def _group_label(key: str, group_by: str, cards: list[AggregateSessionCard]) -> str:
    """Derive a human-readable label for a group key."""
    if group_by == "state":
        return key.replace("_", " ").title()
    if group_by == "project":
        # Use project_name from the first card in the group.
        for ac in cards:
            if ac.project.project_id == key:
                return ac.project.project_name or key
        return key
    if group_by == "feature":
        if key == "unlinked":
            return "Unlinked"
        for ac in cards:
            corr = ac.card.get("correlation") or {}
            if isinstance(corr, dict) and corr.get("feature_id") == key:
                return str(corr.get("feature_name") or key)
        return key
    if group_by == "phase":
        if key == "unlinked":
            return "No Phase"
        for ac in cards:
            corr = ac.card.get("correlation") or {}
            if isinstance(corr, dict) and str(corr.get("phase_number", "")) == key:
                return str(corr.get("phase_title") or f"Phase {key}")
        return f"Phase {key}"
    return key.replace("_", " ").title()


def _group_aggregate_cards(
    cards: list[AggregateSessionCard],
    group_by: str,
) -> list[AggregateBoardGroup]:
    """Group ``AggregateSessionCard`` objects into ``AggregateBoardGroup`` columns."""
    buckets: dict[str, list[AggregateSessionCard]] = {}
    for card in cards:
        key = _group_key_for_aggregate_card(card, group_by)
        buckets.setdefault(key, []).append(card)

    # Sort keys — state grouping uses fixed ordering; others sort alpha with
    # "unlinked" / "unknown" last.
    if group_by == "state":
        sorted_keys = sorted(
            buckets.keys(),
            key=lambda k: (_STATE_ORDER.index(k) if k in _STATE_ORDER else 99, k),
        )
    else:
        sorted_keys = sorted(
            buckets.keys(),
            key=lambda k: (k in ("unlinked", "unknown"), k),
        )

    groups: list[AggregateBoardGroup] = []
    for key in sorted_keys:
        group_cards = buckets[key]
        label = _group_label(key, group_by, group_cards)
        groups.append(
            AggregateBoardGroup(
                group_key=key,
                group_label=label,
                group_type=group_by,
                cards=group_cards,
                card_count=len(group_cards),
            )
        )
    return groups


# ── Service ───────────────────────────────────────────────────────────────────

class MultiProjectActiveSessionBoardQueryService:
    """Aggregate active-session board spanning all registered projects.

    Implements MPCC-303:

    - **Bounded fan-out**: uses asyncio.Semaphore to cap project concurrency.
    - **Active-only**: calls ``sessions_repo.list_active`` per project — never
      calls ``get_session_board``.
    - **Zero-candidate skip**: projects with no active sessions skip
      feature/link correlation I/O entirely.
    - **Worker nesting**: workers are collapsed under their root
      ``AggregateSessionCard.workers`` list; not emitted as top-level duplicates.
    - **Grouping**: supports "state" / "feature" / "phase" / "agent" / "model"
      (mirrors V1) plus aggregate-specific "project".
    - **Cache**: ``@memoized_query`` with key encoding group_by, filters,
      window, workers toggle, pagination, and project scope.
    - **Partial failure**: a failing project emits a ``ProjectWarning`` without
      aborting the other projects.

    Usage::

        svc = MultiProjectActiveSessionBoardQueryService()
        response = await svc.get_multi_project_session_board(
            context, ports,
            group_by="state",
            page=1,
            page_size=50,
        )
    """

    # ------------------------------------------------------------------
    # Public API — MPCC-303
    # ------------------------------------------------------------------

    @memoized_query("mpss_session_board", param_extractor=_mpss_params)
    async def get_multi_project_session_board(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        group_by: str = "state",
        project_ids: Sequence[str] | None = None,
        group_filter: str | None = None,
        feature_id: str | None = None,
        state_filter: str | None = None,
        window_seconds: int | None = None,
        include_workers: bool = True,
        page: int = 1,
        page_size: int = 50,
    ) -> MultiProjectSessionBoardResponse:
        """Return active-session cards grouped across all registered projects.

        Parameters
        ----------
        context:
            Request context (used for cache key derivation; active project is
            NOT mutated).
        ports:
            Core ports providing storage and workspace_registry.
        group_by:
            Grouping dimension: "state" | "feature" | "phase" | "agent" |
            "model" | "project".  Defaults to "state".
        project_ids:
            Optional explicit allow-list of project IDs.  None means all
            registered projects.
        group_filter:
            When set, only cards whose group_key matches this value are
            included.  Used for project-rail filtering.
        feature_id:
            When set, only cards correlated to this feature are included.
        state_filter:
            When set, only cards in this state are included (e.g. "running").
        window_seconds:
            Active-session freshness window override (default from config).
        include_workers:
            When False, worker/subagent sessions are excluded from both
            ``list_active`` and the top-level card list.  Worker summaries
            are omitted from ``AggregateSessionCard.workers``.
        page, page_size:
            Pagination applied to the flat card list before grouping.

        Quality gates
        -------------
        - Does NOT call ``get_session_board`` per project.
        - Projects with zero active candidates skip correlation I/O (the
          ``candidate_session_ids=[]`` fast path in ``load_correlation_data``).
        - Workers are nested under root cards (not duplicated at top level)
          when ``include_workers=True``.
        """
        t_start = time.monotonic()

        effective_window = window_seconds if window_seconds is not None else _ACTIVE_SESSION_WINDOW
        safe_group_by = group_by if group_by in _VALID_GROUPINGS else "state"

        # ── Resolve project list ─────────────────────────────────────────
        projects = ports.workspace_registry.list_projects()
        if project_ids is not None:
            allowed = set(project_ids)
            projects = [p for p in projects if p.id in allowed]

        display_map: dict[str, ProjectDisplayMetadata] = {
            p.id: resolve_display_metadata(p) for p in projects
        }

        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

        # ── Phase 1: active-candidate fan-out ────────────────────────────
        # Each project calls list_active (indexed, no full board load).
        active_fetch_tasks = [
            _collect_project_active_sessions(
                ports,
                project,
                semaphore,
                window_seconds=effective_window,
                include_subagents=include_workers,
                limit=None,
            )
            for project in projects
        ]
        active_results: list[
            tuple[str, list[dict[str, Any]], bool, list[str]]
        ] = await asyncio.gather(*active_fetch_tasks, return_exceptions=False)

        # Partition: projects with candidates vs cold projects.
        project_map: dict[str, Project] = {p.id: p for p in projects}
        active_rows_map: dict[str, list[dict[str, Any]]] = {}
        partial_map: dict[str, bool] = {}
        warnings_map: dict[str, list[str]] = {}

        aggregate_warnings: list[ProjectWarning] = []
        aggregate_partial = False

        for proj_id, rows, proj_partial, proj_warnings in active_results:
            active_rows_map[proj_id] = rows
            partial_map[proj_id] = proj_partial
            warnings_map[proj_id] = proj_warnings

            if proj_partial or proj_warnings:
                aggregate_partial = True
                for msg in proj_warnings:
                    aggregate_warnings.append(
                        ProjectWarning(
                            project_id=proj_id,
                            message=msg,
                            severity="high" if not rows else "medium",
                            code="session_load_failed" if not rows else "partial_data",
                        )
                    )

        # ── Fast path: no project has active candidates ──────────────────
        # Zero total active rows means no correlation work at all.
        total_active_rows = sum(len(r) for r in active_rows_map.values())
        if total_active_rows == 0:
            # Build project summaries (still useful for project rail rendering).
            summary_tasks = [
                _build_session_project_summary(
                    ports=ports,
                    project=proj,
                    active_card_count=0,
                    partial=partial_map.get(proj.id, False),
                    warnings=warnings_map.get(proj.id, []),
                    semaphore=semaphore,
                    display_metadata=display_map[proj.id],
                    window_seconds=effective_window,
                )
                for proj in projects
            ]
            project_summaries: list[ProjectSummary] = list(
                await asyncio.gather(*summary_tasks)
            )
            duration_ms = (time.monotonic() - t_start) * 1000
            logger.info(
                "mpss: fast path (no active sessions) in %.1f ms — projects=%d partial=%s",
                duration_ms,
                len(projects),
                aggregate_partial,
            )
            return MultiProjectSessionBoardResponse(
                status="partial" if aggregate_partial else "ok",
                grouping=safe_group_by,
                groups=[],
                project_summaries=project_summaries,
                pagination=AggregatePagination(
                    page=1,
                    page_size=min(200, max(1, int(page_size or 50))),
                    total=0,
                    has_more=False,
                ),
                warnings=aggregate_warnings,
                total_card_count=0,
                active_count=0,
                completed_count=0,
                generated_at=datetime.now(timezone.utc),
            )

        # ── Phase 2: correlation + card building ─────────────────────────
        # Only projects with active rows trigger correlation I/O.
        card_build_tasks = [
            _build_project_cards(
                ports,
                project_map[proj_id],
                active_rows_map[proj_id],
                semaphore,
            )
            for proj_id in active_rows_map
            if proj_id in project_map
        ]
        card_build_results: list[
            tuple[str, list[PlanningAgentSessionCardDTO], bool, list[str]]
        ] = await asyncio.gather(*card_build_tasks, return_exceptions=False)

        # Collect cards by project and propagate build-phase warnings.
        cards_by_project: dict[str, list[PlanningAgentSessionCardDTO]] = {}
        for proj_id, cards, proj_partial, proj_warnings in card_build_results:
            cards_by_project[proj_id] = cards
            if proj_partial or proj_warnings:
                aggregate_partial = True
                partial_map[proj_id] = partial_map.get(proj_id, False) or proj_partial
                for msg in proj_warnings:
                    aggregate_warnings.append(
                        ProjectWarning(
                            project_id=proj_id,
                            message=msg,
                            severity="medium",
                            code="session_build_partial",
                        )
                    )

        # ── Phase 3: worker nesting + aggregate card assembly ────────────
        all_aggregate_cards: list[AggregateSessionCard] = []

        for proj_id, project_cards in cards_by_project.items():
            proj = project_map.get(proj_id)
            if proj is None:
                continue
            identity = _make_project_identity(proj, display_map[proj_id])

            top_level_cards, workers_by_root = nest_worker_sessions(
                project_cards,
                include_workers_at_top_level=False,
            )

            for card in top_level_cards:
                nested_workers = workers_by_root.get(card.session_id, [])
                agg_card = _make_aggregate_card(card, nested_workers, identity)
                all_aggregate_cards.append(agg_card)

        # ── Phase 4: optional client-side filtering ───────────────────────
        filtered_cards = all_aggregate_cards

        if state_filter:
            filtered_cards = [
                c for c in filtered_cards
                if (c.card.get("state") or "") == state_filter
            ]

        if feature_id:
            filtered_cards = [
                c for c in filtered_cards
                if (
                    (c.card.get("correlation") or {}).get("feature_id", "")
                    if isinstance(c.card.get("correlation"), dict)
                    else ""
                ) == feature_id
            ]

        if group_filter:
            # Filter by group_key under the active grouping.
            filtered_cards = [
                c for c in filtered_cards
                if _group_key_for_aggregate_card(c, safe_group_by) == group_filter
            ]

        # ── Phase 5: pagination ───────────────────────────────────────────
        safe_page_size = min(200, max(1, int(page_size or 50)))
        safe_page = max(1, int(page or 1))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        total = len(filtered_cards)
        page_slice = filtered_cards[start:end]
        has_more = end < total

        # ── Phase 6: grouping ─────────────────────────────────────────────
        groups = _group_aggregate_cards(page_slice, safe_group_by)

        # ── Phase 7: convenience tallies ──────────────────────────────────
        active_states = {"running", "thinking"}
        completed_states = {"completed"}
        active_count = sum(
            1 for c in filtered_cards
            if (c.card.get("state") or "") in active_states
        )
        completed_count = sum(
            1 for c in filtered_cards
            if (c.card.get("state") or "") in completed_states
        )

        # ── Phase 8: project summary rollup ──────────────────────────────
        cards_count_by_project: dict[str, int] = {}
        for proj_id, cards in cards_by_project.items():
            cards_count_by_project[proj_id] = len(cards)

        summary_tasks = [
            _build_session_project_summary(
                ports=ports,
                project=proj,
                active_card_count=cards_count_by_project.get(proj.id, 0),
                partial=partial_map.get(proj.id, False),
                warnings=warnings_map.get(proj.id, []),
                semaphore=semaphore,
                display_metadata=display_map[proj.id],
                window_seconds=effective_window,
            )
            for proj in projects
        ]
        project_summaries = list(await asyncio.gather(*summary_tasks))

        duration_ms = (time.monotonic() - t_start) * 1000
        logger.info(
            "mpss: completed in %.1f ms — projects=%d total_cards=%d page=%d/%d "
            "groups=%d partial=%s",
            duration_ms,
            len(projects),
            total,
            safe_page,
            max(1, -(-total // safe_page_size)),
            len(groups),
            aggregate_partial,
        )

        return MultiProjectSessionBoardResponse(
            status="partial" if aggregate_partial else "ok",
            grouping=safe_group_by,
            groups=groups,
            project_summaries=project_summaries,
            pagination=AggregatePagination(
                page=safe_page,
                page_size=safe_page_size,
                total=total,
                has_more=has_more,
            ),
            warnings=aggregate_warnings,
            total_card_count=total,
            active_count=active_count,
            completed_count=completed_count,
            generated_at=datetime.now(timezone.utc),
        )
