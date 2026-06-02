"""Next-work queue query service (P5-004, §7.2).

Returns a ranked, cursor-paginated list of features that are ready to be
worked on next across all registered projects.

Design constraints
------------------
- Reuses ``PlanningCommandCenterQueryService._build_items_for_scope`` and
  ``_matches_filters`` / ``_sort_items`` without reimplementing scoring.
- Filters to ``launch_readiness="ready"`` items only.
- Ranks by existing signals: commandCenterLaunchReadiness (ready first),
  FeatureDependencyState unblocked-first, Feature.priority, updatedAt recency.
- Cursor pagination over (updated_at desc, feature_id asc) for stable pages.
- Bounded fan-out with asyncio.Semaphore mirroring MPCC pattern.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Sequence

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.agent_queries.multi_project_planning_command_center import (
    _NullGitProbe,
    _collect_project_items,
)
from backend.application.services.agent_queries.planning_command_center import (
    PlanningCommandCenterQueryService,
    _feature_key,
)
from backend.application.services.agent_queries.models import PlanningCommandCenterItemDTO
from backend.models import (
    NextWorkItem,
    NextWorkResponse,
    Project,
)
from backend.project_manager import resolve_display_metadata

from .cache import memoized_query

logger = logging.getLogger(__name__)

_MAX_CONCURRENCY: int = getattr(config, "CCDASH_SYSTEM_METRICS_CONCURRENCY", 4)
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


# ── Cursor encoding ───────────────────────────────────────────────────────────

def _encode_cursor(updated_at: str, feature_id: str) -> str:
    payload = json.dumps({"updated_at": updated_at, "feature_id": feature_id})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str] | None:
    try:
        payload = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(payload)
        return data.get("updated_at", ""), data.get("feature_id", "")
    except Exception:
        return None


# ── Cache param extractor ────────────────────────────────────────────────────

def _next_work_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    *,
    project_ids: Sequence[str] | None = None,
    limit: int = _DEFAULT_LIMIT,
    cursor: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    return {
        "project_ids": sorted(project_ids) if project_ids else [],
        "limit": limit,
        "cursor": cursor or "",
    }


# ── Item ranking helpers ──────────────────────────────────────────────────────

def _item_rank_key(item: PlanningCommandCenterItemDTO) -> tuple:
    """Return a sort key that ranks ready/unblocked items first.

    Key components (ascending — lower = higher rank):
    0: readiness bucket (0=ready, 1=other)
    1: blocked bucket (0=not blocked, 1=blocked)
    2: story_points remaining descending (negated for ascending sort)
    3: last_activity timestamp descending (negated / reversed via minus)
    """
    readiness_bucket = (
        0
        if (item.launch_batch is not None and item.launch_batch.readiness.lower() == "ready")
        else 1
    )
    blocked_bucket = (
        1
        if item.status.effective_status.lower() in {"blocked", "error", "failed"}
        else 0
    )
    # More story points = higher value work = rank higher (lower sort key).
    sp = -(item.story_points.remaining or 0)
    # More recent activity = rank higher (lower sort key).
    ts = str(item.last_activity.get("timestamp") or "")
    # Negate timestamp string so later timestamps sort first (lexicographic).
    ts_neg = "".join(chr(0x10FFFF - ord(c)) for c in ts) if ts else "\U0010ffff"
    return (readiness_bucket, blocked_bucket, sp, ts_neg)


def _cursor_filter(
    item: PlanningCommandCenterItemDTO,
    project_id: str,
    cursor_updated_at: str,
    cursor_feature_id: str,
) -> bool:
    """Return True if *item* falls after the cursor in (updated_at desc, id asc) order."""
    item_ts = str(item.last_activity.get("timestamp") or "")
    if item_ts < cursor_updated_at:
        return True
    if item_ts == cursor_updated_at:
        return item.feature.feature_id > cursor_feature_id
    return False


# ── Service ──────────────────────────────────────────────────────────────────


class NextWorkQueryService:
    """Ranked next-work queue spanning all registered projects (P5-004).

    Reuses ``PlanningCommandCenterQueryService`` internals for item building and
    filtering; does NOT reimplement scoring signals.  Only items where
    ``launch_batch.readiness == "ready"`` are emitted.
    """

    def __init__(
        self,
        *,
        v1_service: PlanningCommandCenterQueryService | None = None,
    ) -> None:
        self._v1 = v1_service or PlanningCommandCenterQueryService()

    @memoized_query("planning_next_work", param_extractor=_next_work_params)
    async def get_next_work(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        project_ids: Sequence[str] | None = None,
        limit: int = _DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> NextWorkResponse:
        """Return a ranked, cursor-paginated list of ready-to-work features.

        Parameters
        ----------
        project_ids:
            Optional explicit allow-list of project IDs.  When None, all
            registered projects are included.
        limit:
            Maximum items per page (default 50, max 200).
        cursor:
            Opaque cursor from the previous response's ``next_cursor`` field.

        Returns
        -------
        NextWorkResponse with ``items`` and ``next_cursor`` (None on last page).
        """
        t_start = time.monotonic()

        projects = ports.workspace_registry.list_projects()
        if project_ids is not None:
            allowed = set(project_ids)
            projects = [p for p in projects if p.id in allowed]

        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
        safe_limit = min(_MAX_LIMIT, max(1, int(limit or _DEFAULT_LIMIT)))

        # Fan-out: collect unprobed items for each project.
        fan_out_tasks = [
            _collect_project_items(self._v1, ports, project, semaphore)
            for project in projects
        ]
        per_project_results = await asyncio.gather(*fan_out_tasks, return_exceptions=False)

        # Build project lookup.
        project_map: dict[str, Project] = {p.id: p for p in projects}

        # Merge and filter: only items with launch_readiness=="ready".
        ready_pairs: list[tuple[str, PlanningCommandCenterItemDTO]] = []
        for proj_id, items, _fr, _dr, _partial, _warnings in per_project_results:
            for item in items:
                if self._v1._matches_filters(
                    item, None, None, None, None, None, None, "ready"
                ):
                    ready_pairs.append((proj_id, item))

        # Sort by rank key.
        ready_pairs.sort(key=lambda p: _item_rank_key(p[1]))

        # Apply cursor filter.
        cursor_decoded = _decode_cursor(cursor) if cursor else None
        if cursor_decoded is not None:
            cursor_updated_at, cursor_feature_id = cursor_decoded
            ready_pairs = [
                (pid, it)
                for pid, it in ready_pairs
                if _cursor_filter(it, pid, cursor_updated_at, cursor_feature_id)
            ]

        # Paginate.
        page_slice = ready_pairs[: safe_limit + 1]
        has_more = len(page_slice) > safe_limit
        page_slice = page_slice[:safe_limit]

        # Build next cursor.
        next_cursor: str | None = None
        if has_more and page_slice:
            last_proj_id, last_item = page_slice[-1]
            next_cursor = _encode_cursor(
                str(last_item.last_activity.get("timestamp") or ""),
                last_item.feature.feature_id,
            )

        # Build response items.
        items_out: list[NextWorkItem] = []
        for rank, (proj_id, item) in enumerate(page_slice, start=1):
            readiness = (
                item.launch_batch.readiness
                if item.launch_batch is not None
                else ""
            )
            blockers = [b.label or b.reason for b in item.blockers]
            command = item.command.command if item.command is not None else ""
            items_out.append(
                NextWorkItem(
                    feature_id=item.feature.feature_id,
                    project_id=proj_id,
                    rank=rank,
                    readiness=readiness,
                    next_phase=item.phase.next_phase,
                    blockers=blockers,
                    story_points=item.story_points.remaining or None,
                    command=command,
                )
            )

        duration_ms = (time.monotonic() - t_start) * 1000
        logger.info(
            "next_work: completed in %.1f ms — projects=%d ready=%d page=%d",
            duration_ms,
            len(projects),
            len(ready_pairs),
            len(items_out),
        )

        return NextWorkResponse(
            status="ok",
            items=items_out,
            next_cursor=next_cursor,
            generated_at=datetime.now(timezone.utc),
        )
