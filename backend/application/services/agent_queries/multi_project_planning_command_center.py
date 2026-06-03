"""Multi-Project Planning Command Center aggregate service.

Implements MPCC-202 (aggregate fan-out), MPCC-203 (project summary rollup),
and MPCC-206 (page-first + lazy enrichment):

- ``MultiProjectPlanningCommandCenterQueryService.get_multi_project_command_center``
  fans out over all registered projects, merges and filters work items,
  paginates the merged set, then enriches ONLY page-visible items with git
  probes.  Off-page items never trigger filesystem/git I/O.

- ``MultiProjectPlanningCommandCenterQueryService.get_multi_project_item``
  finds a single item across the full unfiltered/unprobed item pool (not
  capped to page 1) and enriches just that item.

- Project summary rollup uses ``sessions_repo.count_active`` for active-session
  counts (the same primitive as ``SystemMetricsQueryService``) rather than
  issuing a full board load per project.

MPCC-206 enforcement mechanism
-------------------------------
``_build_items_for_scope`` in V1 calls ``_build_item`` per item, which in turn
calls ``git_probe.probe()``.  For the aggregate list we avoid this by calling
``_build_items_for_scope`` with a *no-op* ``WorktreeGitStateProbe`` whose
``probe()`` returns immediately without filesystem access.  After pagination
we re-call ``_build_item`` for only the page-visible items using the real probe.
This keeps the V1 boundary clean: ``_build_items_for_scope`` is unmodified.

Cache
-----
Results are memoized with ``@memoized_query`` following the conventions of
other agent-query services.  The cache key includes filters, pagination, and
grouping so distinct query shapes hit distinct slots.  TTL follows
``CCDASH_QUERY_CACHE_TTL_SECONDS`` (default 60 s).
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
    PlanningCommandCenterGitStateDTO,
    PlanningCommandCenterItemDTO,
)
from backend.application.services.agent_queries.planning_command_center import (
    PlanningCommandCenterQueryService,
    _feature_key,
)
from backend.application.services.agent_queries.system_metrics import (
    _compute_is_stale,
    _query_max_updated_at,
)
from backend.application.services.worktree_git_state import WorktreeGitStateProbe
from backend.models import (
    AggregatePagination,
    AggregateWorkItem,
    MultiProjectCommandCenterResponse,
    PortfolioAttentionSummary,
    PortfolioNextWorkItem,
    PortfolioProjectEntry,
    PortfolioRollupResponse,
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

# ── Concurrency guard ────────────────────────────────────────────────────────
# Mirrors the semaphore pattern used by SystemMetricsQueryService.  Bounded to
# avoid saturating the shared SQLite connection during large project fan-outs.
_MAX_CONCURRENCY: int = getattr(config, "CCDASH_SYSTEM_METRICS_CONCURRENCY", 4)

# Active-session window mirrors SystemMetricsQueryService.
_ACTIVE_SESSION_WINDOW: int = getattr(config, "CCDASH_LIVE_AGENTS_WINDOW_SECONDS", 600)


# ── No-op git probe ───────────────────────────────────────────────────────────

class _NullGitProbe(WorktreeGitStateProbe):
    """WorktreeGitStateProbe that skips all filesystem and git I/O.

    Used during the *unprobed* build phase (MPCC-206) so that ``_build_item``
    calls inside ``_build_items_for_scope`` do not issue any git probes for
    items that will ultimately be off-page.

    The returned ``PlanningCommandCenterGitStateDTO`` is intentionally sparse
    (``path_exists=None``) so the aggregate enrichment pass can detect that
    the item still needs its git state resolved.
    """

    async def probe(self, worktree_path: str) -> PlanningCommandCenterGitStateDTO:
        return PlanningCommandCenterGitStateDTO(
            path_exists=None,
            probed_at="",
            warnings=["git probe deferred — off-page item"],
        )


# ── Cache param extractor ────────────────────────────────────────────────────

def _mpcc_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    *,
    q: str | None = None,
    status: str | None = None,
    phase: int | None = None,
    artifact_type: str | None = None,
    worktree_state: str | None = None,
    pr_state: str | None = None,
    launch_readiness: str | None = None,
    sort_by: str = "last_activity",
    sort_direction: str = "desc",
    page: int = 1,
    page_size: int = 50,
    project_ids: Sequence[str] | None = None,
    hide_done: bool = False,
    **_: Any,
) -> dict[str, Any]:
    """Extract cache-key parameters for the aggregate command-center query.

    Project scope is "global" (no single project_id) — the decorator will use
    ``project_id=None`` which maps to the "global" key slot.
    """
    return {
        "q": q or "",
        "status": status or "",
        "phase": phase,
        "artifact_type": artifact_type or "",
        "worktree_state": worktree_state or "",
        "pr_state": pr_state or "",
        "launch_readiness": launch_readiness or "",
        "sort_by": sort_by,
        "sort_direction": sort_direction,
        "page": page,
        "page_size": page_size,
        "project_ids": sorted(project_ids) if project_ids else [],
        "hide_done": hide_done,
    }


# ── Per-project item collection ──────────────────────────────────────────────

async def _collect_project_items(
    v1_service: PlanningCommandCenterQueryService,
    ports: CorePorts,
    project: Project,
    semaphore: asyncio.Semaphore,
) -> tuple[
    str,                                  # project_id
    list[PlanningCommandCenterItemDTO],   # unprobed items (all, unfiltered)
    list[dict[str, Any]],                 # feature_rows (for freshness)
    list[dict[str, Any]],                 # doc_rows (for freshness)
    bool,                                 # partial
    list[str],                            # per-project string warnings
]:
    """Load and build *unprobed* work items for a single project.

    The V1 ``_build_items_for_scope`` is called with ``_NullGitProbe`` so
    no git I/O happens.  All items (filtered=False) are returned so the
    caller can apply server-side filtering across the merged set.

    Returns a 6-tuple of (project_id, items, feature_rows, doc_rows,
    partial, warnings).  On failure returns empty items + partial=True with
    the error message in warnings so other projects still proceed.
    """
    async with semaphore:
        try:
            (
                feature_rows,
                features,
                feature_index,
                doc_rows,
                partial,
                warnings,
            ) = await v1_service._load_project_data(ports, project.id)

            # Build all items with no-op git probe — no filter applied here.
            # We pass empty strings for all filter args so _build_items_for_scope
            # returns ALL items and we filter across projects after merging.
            _, all_items, had_errors = await PlanningCommandCenterQueryService(
                resolver=v1_service.resolver,
                git_probe=_NullGitProbe(),
            )._build_items_for_scope(
                ports=ports,
                project_id=project.id,
                features=features,
                feature_index=feature_index,
                doc_rows=doc_rows,
                warnings=warnings,
            )
            partial = partial or had_errors
            return project.id, all_items, feature_rows, doc_rows, partial, warnings
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "mpcc: error loading project=%s: %s",
                project.id,
                exc,
            )
            return project.id, [], [], [], True, [str(exc)]


# ── Project summary rollup ───────────────────────────────────────────────────

async def _build_project_summary(
    ports: CorePorts,
    project: Project,
    items: Sequence[PlanningCommandCenterItemDTO],
    partial: bool,
    warnings: list[str],
    semaphore: asyncio.Semaphore,
    display_metadata: ProjectDisplayMetadata,
) -> ProjectSummary:
    """Build a ``ProjectSummary`` for a single project.

    Active-session count reuses ``sessions_repo.count_active`` directly
    (the same primitive as ``SystemMetricsQueryService``) to avoid a full
    board load.  Freshness and staleness are derived from
    ``_query_max_updated_at`` / ``_compute_is_stale`` from system_metrics.
    """
    async with semaphore:
        # Work-item counts derived from the unprobed item list.
        work_items = len(items)
        blocked = sum(
            1 for it in items
            if it.status.effective_status.lower() in {"blocked"}
        )
        review = sum(
            1 for it in items
            if it.status.effective_status.lower() in {"review", "review-ready", "review_ready"}
        )
        stale = sum(
            1 for it in items
            if it.status.raw_status.lower() in {"done", "completed", "closed", "deferred", "superseded"}
            and it.status.effective_status.lower() != it.status.raw_status.lower()
        )
        error_items = sum(
            1 for it in items
            if it.status.effective_status.lower() in {"error", "failed"}
        )

        # Active session count — reuse sessions_repo primitive.
        active_sessions = 0
        last_updated: str | None = None
        freshness_seconds: int | None = None
        is_stale: bool | None = None
        error_msg: str | None = None

        if partial and not items:
            # Project failed to load entirely.
            error_msg = "; ".join(warnings) if warnings else "Project data unavailable"
        else:
            try:
                sessions_repo = ports.storage.sessions()
                active_sessions = await sessions_repo.count_active(
                    project.id,
                    window_seconds=_ACTIVE_SESSION_WINDOW,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "mpcc summary: count_active failed for project=%s: %s",
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
                    "mpcc summary: freshness query failed for project=%s: %s",
                    project.id,
                    exc,
                )

        # Token and cost rollup from session stats (P5-003a).
        total_tokens = 0
        total_cost = 0.0
        try:
            sessions_repo = ports.storage.sessions()
            stats = await sessions_repo.get_project_stats(project.id)
            total_tokens = int(stats.get("tokens") or 0)
            total_cost = float(stats.get("cost") or 0.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "mpcc summary: token stats failed for project=%s: %s",
                project.id,
                exc,
            )

        counts = ProjectWorkItemCounts(
            work_items=work_items,
            blocked=blocked,
            review=review,
            stale=stale,
            active_sessions=active_sessions,
            errors=error_items,
            total_tokens=total_tokens,
            total_cost=total_cost,
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


# ── Identity helpers ─────────────────────────────────────────────────────────

def _project_identity(
    project: Project,
    display_metadata: ProjectDisplayMetadata,
) -> ProjectIdentityFields:
    return ProjectIdentityFields(
        project_id=project.id,
        project_name=project.name,
        project_color=display_metadata.color,
        project_group=display_metadata.group,
    )


# ── Portfolio rollup cache param extractor ───────────────────────────────────

def _portfolio_rollup_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    *,
    project_ids: Sequence[str] | None = None,
    **_: Any,
) -> dict[str, Any]:
    return {"project_ids": sorted(project_ids) if project_ids else []}


# ── Service ──────────────────────────────────────────────────────────────────

class MultiProjectPlanningCommandCenterQueryService:
    """Aggregate Planning Command Center service spanning all registered projects.

    Implements:
    - MPCC-202: bounded fan-out, per-project warnings, server-side
      sort/filter, aggregate pagination.
    - MPCC-203: project summary rollup with active-session counts and
      freshness/staleness data.
    - MPCC-206: page-first + lazy git enrichment (off-page items never
      trigger git probes).

    Usage::

        svc = MultiProjectPlanningCommandCenterQueryService()
        response = await svc.get_multi_project_command_center(context, ports,
            q="auth", page=1, page_size=20)
    """

    def __init__(
        self,
        *,
        v1_service: PlanningCommandCenterQueryService | None = None,
    ) -> None:
        # Compose over V1 — reuse resolver + real probe for enrichment pass.
        self._v1 = v1_service or PlanningCommandCenterQueryService()

    # ------------------------------------------------------------------
    # Public API — MPCC-202/203/206
    # ------------------------------------------------------------------

    @memoized_query("mpcc_command_center", param_extractor=_mpcc_params)
    async def get_multi_project_command_center(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        q: str | None = None,
        status: str | None = None,
        phase: int | None = None,
        artifact_type: str | None = None,
        worktree_state: str | None = None,
        pr_state: str | None = None,
        launch_readiness: str | None = None,
        sort_by: str = "last_activity",
        sort_direction: str = "desc",
        page: int = 1,
        page_size: int = 50,
        project_ids: Sequence[str] | None = None,
        hide_done: bool = False,
    ) -> MultiProjectCommandCenterResponse:
        """Return a paginated, sorted, filtered work-item list spanning all projects.

        Parameters
        ----------
        context:
            Request context (used for cache key derivation; active project is
            NOT mutated).
        ports:
            Core ports providing storage, workspace_registry, etc.
        q, status, phase, artifact_type, worktree_state, pr_state, launch_readiness:
            Filter parameters mirroring V1 ``get_command_center`` semantics.
        sort_by, sort_direction:
            Sort key and direction, mirroring V1 semantics.
        page, page_size:
            Aggregate pagination over the merged, sorted item set.
        project_ids:
            Optional explicit allow-list of project IDs.  When None all
            registered projects are included.

        MPCC-206 guarantee
        ------------------
        Git probes run only for items in the requested page window.
        Off-page items are built with ``_NullGitProbe`` and never touch
        the filesystem.
        """
        t_start = time.monotonic()

        projects = ports.workspace_registry.list_projects()
        if project_ids is not None:
            allowed = set(project_ids)
            projects = [p for p in projects if p.id in allowed]

        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

        # ── Phase 1: unprobed fan-out across projects ────────────────────
        fan_out_tasks = [
            _collect_project_items(self._v1, ports, project, semaphore)
            for project in projects
        ]
        per_project_results: list[
            tuple[str, list[PlanningCommandCenterItemDTO], list[dict], list[dict], bool, list[str]]
        ] = await asyncio.gather(*fan_out_tasks, return_exceptions=False)

        # ── Phase 2: merge, filter, sort ────────────────────────────────
        # Map project_id → project object for quick lookup.
        project_map: dict[str, Project] = {p.id: p for p in projects}
        display_map: dict[str, ProjectDisplayMetadata] = {
            p.id: resolve_display_metadata(p) for p in projects
        }

        warnings: list[ProjectWarning] = []
        partial = False

        # Collect unprobed items annotated with their project.
        unprobed_annotated: list[tuple[Project, PlanningCommandCenterItemDTO]] = []
        project_items_map: dict[str, list[PlanningCommandCenterItemDTO]] = {}
        project_partial_map: dict[str, bool] = {}
        project_warnings_map: dict[str, list[str]] = {}
        freshness_rows_map: dict[str, tuple[list[dict], list[dict]]] = {}

        for proj_id, items, feat_rows, doc_rows, proj_partial, proj_warnings in per_project_results:
            project_items_map[proj_id] = items
            project_partial_map[proj_id] = proj_partial
            project_warnings_map[proj_id] = proj_warnings
            freshness_rows_map[proj_id] = (feat_rows, doc_rows)

            if proj_partial or proj_warnings:
                partial = True
                for msg in proj_warnings:
                    warnings.append(ProjectWarning(
                        project_id=proj_id,
                        message=msg,
                        severity="high" if not items else "medium",
                        code="feature_load_failed" if not items else "partial_data",
                    ))

            proj = project_map.get(proj_id)
            if proj is None:
                continue
            for item in items:
                unprobed_annotated.append((proj, item))

        # Server-side filter across merged set.
        filtered: list[tuple[Project, PlanningCommandCenterItemDTO]] = [
            (proj, item)
            for proj, item in unprobed_annotated
            if self._v1._matches_filters(
                item, q, status, phase, artifact_type,
                worktree_state, pr_state, launch_readiness,
                hide_done=hide_done,
            )
        ]

        # Sort across merged set.
        sorted_items = self._sort_annotated(filtered, sort_by=sort_by, sort_direction=sort_direction)

        # ── Phase 3: pagination ──────────────────────────────────────────
        safe_page_size = min(200, max(1, int(page_size or 50)))
        safe_page = max(1, int(page or 1))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        page_slice = sorted_items[start:end]
        total = len(sorted_items)
        has_more = end < total

        # ── Phase 4: enrich ONLY page-visible items (MPCC-206) ──────────
        enriched_items: list[AggregateWorkItem] = []
        for proj, unprobed_item in page_slice:
            enriched = await self._enrich_item(ports, proj, unprobed_item)
            identity = _project_identity(proj, display_map[proj.id])
            enriched_items.append(
                AggregateWorkItem(
                    project=identity,
                    item=enriched.model_dump(mode="json"),
                )
            )

        # ── Phase 5: project summary rollup (MPCC-203) ──────────────────
        summary_tasks = [
            _build_project_summary(
                ports=ports,
                project=proj,
                items=project_items_map.get(proj.id, []),
                partial=project_partial_map.get(proj.id, False),
                warnings=project_warnings_map.get(proj.id, []),
                semaphore=semaphore,
                display_metadata=display_map[proj.id],
            )
            for proj in projects
        ]
        project_summaries: list[ProjectSummary] = await asyncio.gather(*summary_tasks)

        duration_ms = (time.monotonic() - t_start) * 1000
        logger.info(
            "mpcc: completed in %.1f ms — projects=%d total_items=%d page=%d/%d partial=%s",
            duration_ms,
            len(projects),
            total,
            safe_page,
            max(1, -(-total // safe_page_size)),
            partial,
        )

        return MultiProjectCommandCenterResponse(
            status="partial" if partial else "ok",
            items=enriched_items,
            project_summaries=list(project_summaries),
            pagination=AggregatePagination(
                page=safe_page,
                page_size=safe_page_size,
                total=total,
                has_more=has_more,
            ),
            warnings=warnings,
            generated_at=datetime.now(timezone.utc),
        )

    async def get_multi_project_item(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        feature_id: str,
        project_id: str | None = None,
    ) -> AggregateWorkItem | None:
        """Find and enrich a single item from any project (MPCC-206 detail path).

        Searches the *full* unprobed item pool — not limited to page 1 — so an
        item at any position in the merged set can be located.  When found the
        item is enriched with a real git probe and returned.

        Parameters
        ----------
        feature_id:
            The feature / work-item ID to locate.
        project_id:
            When provided, only that project is searched (faster path).
            When None all projects are searched.
        """
        projects = ports.workspace_registry.list_projects()
        if project_id is not None:
            projects = [p for p in projects if p.id == project_id]

        display_map: dict[str, ProjectDisplayMetadata] = {
            p.id: resolve_display_metadata(p) for p in projects
        }

        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
        fan_out = [
            _collect_project_items(self._v1, ports, proj, semaphore)
            for proj in projects
        ]
        results = await asyncio.gather(*fan_out, return_exceptions=False)

        project_map = {p.id: p for p in projects}
        target_key = _feature_key(feature_id)

        for proj_id, items, _, _, _, _ in results:
            for item in items:
                if _feature_key(item.feature.feature_id) == target_key:
                    proj = project_map.get(proj_id)
                    if proj is None:
                        continue
                    enriched = await self._enrich_item(ports, proj, item)
                    identity = _project_identity(proj, display_map[proj.id])
                    return AggregateWorkItem(
                        project=identity,
                        item=enriched.model_dump(mode="json"),
                    )
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _enrich_item(
        self,
        ports: CorePorts,
        project: Project,
        unprobed_item: PlanningCommandCenterItemDTO,
    ) -> PlanningCommandCenterItemDTO:
        """Re-run git probe for a page-visible item using the real probe.

        The unprobed item already has all fields populated except
        ``git_state`` (which is a sentinel from ``_NullGitProbe``).  We
        call the V1 ``_build_item`` only to resolve the git state,
        reusing the worktree path that is already embedded in the item.

        Because ``_build_item`` is a full rebuild (feature + docs re-derivation
        would be wasteful), we take the lighter-weight path: use the
        real probe directly and patch the ``git_state`` field.
        """
        path = ""
        if unprobed_item.worktree is not None:
            path = unprobed_item.worktree.path or ""

        git_state = await self._v1.git_probe.probe(path)

        # Pydantic models are immutable by default; use model_copy to patch.
        return unprobed_item.model_copy(update={"git_state": git_state})

    def _sort_annotated(
        self,
        items: list[tuple[Project, PlanningCommandCenterItemDTO]],
        *,
        sort_by: str,
        sort_direction: str,
    ) -> list[tuple[Project, PlanningCommandCenterItemDTO]]:
        """Sort annotated (project, item) pairs mirroring V1 sort semantics."""
        key_name = str(sort_by or "last_activity").lower()
        reverse = str(sort_direction or "desc").lower() == "desc"

        def sort_key(pair: tuple[Project, PlanningCommandCenterItemDTO]) -> Any:
            _, item = pair
            if key_name == "status":
                return item.status.effective_status
            if key_name == "phase":
                return item.phase.current_phase or item.phase.next_phase or 0
            if key_name == "story_points":
                return item.story_points.remaining
            if key_name == "command":
                return item.command.command if item.command is not None else ""
            if key_name == "name":
                return item.feature.name.lower()
            if key_name == "project":
                return pair[0].name.lower()
            # last_activity (catch-all): items with a timestamp sort before
            # items without one, regardless of direction.
            # Under desc (reverse=True):  (1, ts) > (0, "")  → timestamped first ✓
            # Under asc  (reverse=False): negate has_ts so no-ts (key 1) sinks last.
            ts = str(item.last_activity.get("timestamp") or "").strip()
            if reverse:
                return (1 if ts else 0, ts)
            else:
                return (0 if ts else 1, ts)

        return sorted(items, key=sort_key, reverse=reverse)

    # ------------------------------------------------------------------
    # P5-003a: Portfolio rollup
    # ------------------------------------------------------------------

    @memoized_query("planning_portfolio_rollup", param_extractor=_portfolio_rollup_params)
    async def get_portfolio_rollup(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        project_ids: Sequence[str] | None = None,
    ) -> PortfolioRollupResponse:
        """Return a lightweight portfolio rollup spanning all registered projects.

        Reuses ``_build_project_summary`` (MPCC-203) for per-project fan-out.
        Uses column-projected list_summary path (NOT the data_json BLOB) via
        the existing ``get_project_stats`` + ``count_active`` primitives.

        Response shape §7.1:
          { projects:[{projectId,display,statusCounts,activeSessions,
                       changedRecently,needsAttention,tokenTotal}],
            attention:{activeNow,changedRecently,needsAttention,nextWork},
            generatedAt }
        """
        t_start = time.monotonic()

        projects = ports.workspace_registry.list_projects()
        if project_ids is not None:
            allowed = set(project_ids)
            projects = [p for p in projects if p.id in allowed]

        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
        display_map: dict[str, ProjectDisplayMetadata] = {
            p.id: resolve_display_metadata(p) for p in projects
        }

        # Fan-out: collect items (unprobed) for each project so we can derive
        # status counts cheaply without a full board load.
        fan_out_tasks = [
            _collect_project_items(self._v1, ports, project, semaphore)
            for project in projects
        ]
        per_project_results = await asyncio.gather(*fan_out_tasks, return_exceptions=False)

        project_items_map: dict[str, list[PlanningCommandCenterItemDTO]] = {}
        for proj_id, items, _feat_rows, _doc_rows, _partial, _warnings in per_project_results:
            project_items_map[proj_id] = items

        # Build summaries in parallel using the MPCC-203 helper.
        summary_tasks = [
            _build_project_summary(
                ports=ports,
                project=proj,
                items=project_items_map.get(proj.id, []),
                partial=False,
                warnings=[],
                semaphore=semaphore,
                display_metadata=display_map[proj.id],
            )
            for proj in projects
        ]
        project_summaries: list[ProjectSummary] = await asyncio.gather(*summary_tasks)

        # Build per-project entries and attention summary.
        entries: list[PortfolioProjectEntry] = []
        active_now = 0
        changed_recently_count = 0
        needs_attention_count = 0
        next_work_ids: list[str] = []
        next_work_items_list: list[PortfolioNextWorkItem] = []

        _STALE_THRESHOLD_SECONDS = 3600  # 1 hour = "changed recently"

        for ps in project_summaries:
            status_counts: dict[str, int] = {}
            items = project_items_map.get(ps.project_id, [])
            for it in items:
                eff = it.status.effective_status.lower()
                status_counts[eff] = status_counts.get(eff, 0) + 1

            changed = (
                ps.freshness_seconds is not None
                and ps.freshness_seconds <= _STALE_THRESHOLD_SECONDS
            )
            needs_attn = ps.is_stale is True or bool(ps.error)

            if ps.counts.active_sessions > 0:
                active_now += 1
            if changed:
                changed_recently_count += 1
            if needs_attn:
                needs_attention_count += 1

            # Next-work: ready items in this project — carry project_id alongside feature_id.
            for it in items:
                if (
                    it.launch_batch is not None
                    and it.launch_batch.readiness.lower() == "ready"
                ):
                    next_work_ids.append(it.feature.feature_id)
                    next_work_items_list.append(
                        PortfolioNextWorkItem(
                            feature_id=it.feature.feature_id,
                            project_id=ps.project_id,
                        )
                    )

            entries.append(PortfolioProjectEntry(
                project_id=ps.project_id,
                display_name=ps.name,
                status_counts=status_counts,
                active_sessions=ps.counts.active_sessions,
                changed_recently=changed,
                needs_attention=needs_attn,
                token_total=ps.counts.total_tokens,
            ))

        attention = PortfolioAttentionSummary(
            active_now=active_now,
            changed_recently=changed_recently_count,
            needs_attention=needs_attention_count,
            next_work=next_work_ids[:20],  # cap for response size — backward compat
            next_work_items=next_work_items_list[:20],  # enriched shape with project_id
        )

        duration_ms = (time.monotonic() - t_start) * 1000
        logger.info(
            "mpcc portfolio rollup: completed in %.1f ms — projects=%d",
            duration_ms,
            len(projects),
        )

        return PortfolioRollupResponse(
            status="ok",
            projects=entries,
            attention=attention,
            generated_at=datetime.now(timezone.utc),
        )
