"""Transport-neutral dashboard bundle query service (T5-001).

Composes the most-recent sessions page (limit 20, ``started_at`` desc) and
task counts by status into a single ``DashboardBundleDTO``.  The bundle reduces
the Dashboard above-fold waterfall to ≤1 request.

All reads delegate to the existing storage repositories — no new DB queries are
introduced.  The service is wrapped with ``@memoized_query`` (10 s TTL, matching
the live-count window) and emits an OTEL span named ``ccdash.dashboard.bundle``.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.observability import otel

from ._filters import collect_source_refs, resolve_project_scope
from .cache import memoized_query
from .models import DashboardBundleDTO, SessionCardDTO

__all__ = ["DashboardQueryService"]

logger = logging.getLogger(__name__)

# ── Internal helpers ─────────────────────────────────────────────────────────


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _session_card_from_row(row: Any) -> SessionCardDTO:
    """Map a raw session DB row to a ``SessionCardDTO``."""
    if isinstance(row, dict):
        get = row.get
    else:
        # Support mapping-like objects (asyncpg Record, aiosqlite Row)
        def get(key: str, default: Any = None) -> Any:  # type: ignore[misc]
            try:
                return row[key]
            except (KeyError, TypeError, IndexError):
                return default

    return SessionCardDTO(
        session_id=str(get("id") or get("session_id") or ""),
        title=str(get("title") or ""),
        status=str(get("status") or ""),
        started_at=str(get("started_at") or ""),
        ended_at=str(get("ended_at") or ""),
        model=str(get("model") or ""),
        total_cost=_safe_float(get("total_cost")),
        total_tokens=_safe_int(
            get("observed_tokens")
            or get("model_io_tokens")
            or get("tokens_in")
        ),
        feature_id=str(get("feature_id") or get("task_id") or ""),
        root_session_id=str(get("root_session_id") or ""),
    )


def _task_counts_from_rows(rows: list[Any]) -> dict[str, int]:
    """Derive status-keyed counts from a list of task rows."""
    counts: dict[str, int] = {}
    for row in rows:
        if isinstance(row, dict):
            status = str(row.get("status") or "unknown").strip()
        else:
            try:
                status = str(row["status"] or "unknown").strip()
            except (KeyError, TypeError):
                status = "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


# ── Param extractor for memoized_query ──────────────────────────────────────

def _dashboard_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    project_id_override: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    return {"project_id_override": project_id_override}


# ── Service ──────────────────────────────────────────────────────────────────


class DashboardQueryService:
    """Transport-neutral dashboard bundle query service (T5-001).

    The singleton pattern (one instance per process) is consistent with the
    other agent query services (``ProjectStatusQueryService``, etc.).
    """

    @memoized_query("dashboard_bundle", param_extractor=_dashboard_params)
    async def get_dashboard_bundle(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        project_id_override: str | None = None,
    ) -> DashboardBundleDTO:
        """Return the Dashboard fat-read bundle.

        Composes:
        - ``sessions``: up to 20 most-recent session cards (``started_at`` desc).
        - ``task_counts``: dict of status → count across all project tasks.

        Both sub-reads are guarded defensively; a failure in either degrades the
        bundle to ``status="partial"`` rather than raising.
        """
        with otel.start_span(
            "ccdash.dashboard.bundle",
            {"project_id": project_id_override or ""},
        ):
            scope = resolve_project_scope(context, ports, project_id_override)
            if scope is None:
                return DashboardBundleDTO(
                    status="error",
                    project_id=str(project_id_override or ""),
                    source_refs=[],
                )

            project = scope.project
            partial = False
            source_refs: list[str] = []

            # ── Sessions page (limit 20, started_at desc) ─────────────────
            sessions: list[SessionCardDTO] = []
            try:
                rows = await ports.storage.sessions().list_paginated(
                    0,
                    20,
                    project.id,
                    "started_at",
                    "desc",
                    {"include_subagents": True},
                )
                sessions = [_session_card_from_row(row) for row in rows]
                source_refs = collect_source_refs(source_refs, "sessions")
            except Exception:
                logger.warning(
                    "DashboardQueryService: failed to load sessions for project %s",
                    project.id,
                )
                partial = True

            # ── Task counts by status ─────────────────────────────────────
            task_counts: dict[str, int] = {}
            try:
                task_rows = await ports.storage.tasks().list_all(project.id)
                task_counts = _task_counts_from_rows(task_rows)
                source_refs = collect_source_refs(source_refs, "tasks")
            except Exception:
                logger.warning(
                    "DashboardQueryService: failed to load tasks for project %s",
                    project.id,
                )
                partial = True

            status = "partial" if partial else "ok"
            return DashboardBundleDTO(
                status=status,
                project_id=project.id,
                sessions=sessions,
                task_counts=task_counts,
                source_refs=source_refs,
            )
