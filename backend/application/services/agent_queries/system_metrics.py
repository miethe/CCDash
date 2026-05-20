"""System-wide metrics query service.

Design note — OQ-5 two-query staleness approach
-------------------------------------------------
This service intentionally uses two separate queries per project:
1. ``SessionsRepository.count_active(project_id, window_seconds=...)`` — the
   existing live-agents-count primitive, left completely unchanged.
2. A small ``SELECT MAX(updated_at) FROM sessions WHERE project_id = ?`` query
   run directly against the shared DB connection — used solely to compute the
   ``is_stale`` / ``last_synced_at`` fields.

The spike (OQ-5 decision) chose this two-query approach to avoid modifying the
``count_active`` signature and to keep the staleness computation entirely local
to this service.  The ``count_active`` primitive is reused as-is by the
per-project live-counts endpoint (Phase 2).

Staleness semantics: a project is flagged ``is_stale=True`` when
``now() - max(sessions.updated_at)`` exceeds
``CCDASH_SYSTEM_METRICS_STALE_HORIZON_SECONDS`` (default 3600 s).  Projects
with no sessions at all get ``is_stale=None`` (indeterminate, not stale).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.models import ProjectActiveCountSummaryDTO, SystemActiveCountDTO
from backend.observability import otel

from .cache import memoized_query

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _query_max_updated_at(db: Any, project_id: str) -> datetime | None:
    """Return MAX(updated_at) for *project_id* in the sessions table.

    Returns ``None`` when the project has no session rows.  Dual-path for
    SQLite (aiosqlite) and PostgreSQL (asyncpg Pool/Connection) following the
    pattern established in ``backend/application/services/agent_queries/cache.py``.
    """
    sqlite_sql = (
        "SELECT MAX(updated_at) AS m FROM sessions WHERE project_id = ?"  # noqa: S608
    )
    pg_sql = (
        "SELECT MAX(updated_at) AS m FROM sessions WHERE project_id = $1"  # noqa: S608
    )

    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sqlite_sql, (project_id,)) as cur:
            row = await cur.fetchone()
            raw = row[0] if row else None
    else:
        row = await db.fetchrow(pg_sql, project_id)
        raw = row["m"] if row else None

    if not raw:
        return None

    # ``updated_at`` is stored as an ISO 8601 string in SQLite; asyncpg may
    # return a datetime object directly.
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)

    raw_str = str(raw).strip()
    if not raw_str:
        return None

    # Normalise: strip trailing 'Z', add UTC offset if missing
    raw_str = raw_str.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _compute_is_stale(max_updated_at: datetime | None) -> bool | None:
    """Return whether the project data is considered stale.

    Returns ``None`` when *max_updated_at* is ``None`` (project has no sessions
    — staleness is indeterminate).
    """
    if max_updated_at is None:
        return None
    horizon = timedelta(seconds=config.CCDASH_SYSTEM_METRICS_STALE_HORIZON_SECONDS)
    return (datetime.now(timezone.utc) - max_updated_at) > horizon


# ── Per-project fan-out logic ────────────────────────────────────────────────

async def _fetch_project_summary(
    db: Any,
    sessions_repo: Any,
    project_id: str,
    project_name: str,
    window_seconds: int,
    semaphore: asyncio.Semaphore,
) -> ProjectActiveCountSummaryDTO:
    """Fetch active count + staleness for a single project under *semaphore*."""
    async with semaphore:
        try:
            logger.debug(
                "system_metrics: fetching project=%s name=%r",
                project_id,
                project_name,
            )
            count = await sessions_repo.count_active(
                project_id,
                window_seconds=window_seconds,
            )
            max_updated_at = await _query_max_updated_at(db, project_id)
            is_stale = _compute_is_stale(max_updated_at)
            return ProjectActiveCountSummaryDTO(
                project_id=project_id,
                project_name=project_name,
                count=count,
                is_stale=is_stale,
                last_synced_at=max_updated_at,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "system_metrics: error fetching project=%s: %s",
                project_id,
                exc,
            )
            return ProjectActiveCountSummaryDTO(
                project_id=project_id,
                project_name=project_name,
                count=None,
                is_stale=None,
                last_synced_at=None,
                error=str(exc),
            )


# ── Cache param extractor ────────────────────────────────────────────────────

def _system_active_count_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    **_: Any,
) -> dict[str, Any]:
    # No per-invocation parameters vary the result; use an empty dict so the
    # cache key scope resolves to "global" via project_id=None.
    return {}


# ── Service ──────────────────────────────────────────────────────────────────

class SystemMetricsQueryService:
    """Aggregate live-agent counts across all known projects.

    Mirrors the structural shape of ``ProjectStatusQueryService`` in
    ``backend/application/services/agent_queries/project_status.py``.
    """

    @memoized_query("system_active_count", param_extractor=_system_active_count_params)
    async def get_system_active_count(
        self,
        context: RequestContext,
        ports: CorePorts,
    ) -> SystemActiveCountDTO:
        """Fan out active-count + staleness queries across all known projects.

        Uses ``asyncio.gather(return_exceptions=True)`` bounded by
        ``asyncio.Semaphore(CCDASH_SYSTEM_METRICS_CONCURRENCY)`` so the fan-out
        never saturates the shared SQLite connection.

        Per-project exceptions are caught individually: they produce a
        ``ProjectActiveCountSummaryDTO`` with ``count=None`` and an ``error``
        field.  The overall ``status`` is set to ``"partial"`` when any project
        errors.
        """
        t_start = time.monotonic()

        with otel.start_span(
            "system_metrics.get_system_active_count",
            {"window_seconds": config.CCDASH_LIVE_AGENTS_WINDOW_SECONDS},
        ) as span:
            projects = ports.workspace_registry.list_projects()
            db = ports.storage.db
            sessions_repo = ports.storage.sessions()

            semaphore = asyncio.Semaphore(config.CCDASH_SYSTEM_METRICS_CONCURRENCY)
            window_seconds = config.CCDASH_LIVE_AGENTS_WINDOW_SECONDS

            tasks = [
                _fetch_project_summary(
                    db,
                    sessions_repo,
                    project.id,
                    project.name,
                    window_seconds,
                    semaphore,
                )
                for project in projects
            ]

            results: list[ProjectActiveCountSummaryDTO | BaseException] = await asyncio.gather(
                *tasks, return_exceptions=True
            )

            per_project: list[ProjectActiveCountSummaryDTO] = []
            for project, result in zip(projects, results):
                if isinstance(result, BaseException):
                    # Outer gather exception (should not happen given inner try/except,
                    # but handled defensively).
                    per_project.append(
                        ProjectActiveCountSummaryDTO(
                            project_id=project.id,
                            project_name=project.name,
                            count=None,
                            is_stale=None,
                            last_synced_at=None,
                            error=str(result),
                        )
                    )
                else:
                    per_project.append(result)

            total = sum(p.count for p in per_project if p.count is not None)
            has_errors = any(p.error for p in per_project)
            status: str = "partial" if has_errors else "ok"

            stale_count = sum(1 for p in per_project if p.is_stale is True)
            error_count = sum(1 for p in per_project if p.error is not None)
            duration_ms = (time.monotonic() - t_start) * 1000

            if span is not None:
                span.set_attribute("project_count", len(per_project))
                span.set_attribute("stale_project_count", stale_count)
                span.set_attribute("error_project_count", error_count)
                # cache_hit is not knowable here (the decorator wraps this method);
                # set False as a placeholder — the decorator emits its own hit metric.
                span.set_attribute("cache_hit", False)

            logger.info(
                "system_metrics: completed in %.1f ms — total=%d stale=%d errors=%d projects=%d",
                duration_ms,
                total,
                stale_count,
                error_count,
                len(per_project),
            )

            return SystemActiveCountDTO(
                total=total,
                per_project=per_project,
                generated_at=datetime.now(timezone.utc),
                window_seconds=window_seconds,
                status=status,  # type: ignore[arg-type]
            )
