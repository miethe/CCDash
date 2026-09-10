"""Shared normalization helpers for agent query services."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import aiosqlite

from backend.application.context import ProjectScope, RequestContext
from backend.application.ports import CorePorts
from backend.application.services.common import resolve_project
from backend.models import Project


def _coerce_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class AgentQueryProjectScope:
    project: Project
    request_scope: ProjectScope | None


def resolve_project_scope(
    context: RequestContext,
    ports: CorePorts,
    project_id_override: str | None = None,
) -> AgentQueryProjectScope | None:
    """Resolve the effective project for an agent query request."""

    project = resolve_project(context, ports, requested_project_id=project_id_override)
    if project is None:
        return None

    scope = context.project
    if scope is None or scope.project_id != project.id:
        try:
            _, scope = ports.workspace_registry.resolve_scope(project.id)
        except Exception:
            scope = None
    return AgentQueryProjectScope(project=project, request_scope=scope)


def resolve_time_window(
    since: datetime | str | None = None,
    until: datetime | str | None = None,
    default_days: int = 7,
) -> tuple[datetime, datetime]:
    """Return a normalized UTC time window for query filters."""

    end = _coerce_datetime(until) or datetime.now(timezone.utc)
    start = _coerce_datetime(since) or (end - timedelta(days=default_days))
    if start > end:
        start, end = end, start
    return start, end


def normalize_entity_ids(*groups: object) -> list[str]:
    """Flatten, trim, de-duplicate, and sort entity identifiers."""

    normalized: set[str] = set()
    for group in groups:
        if group is None:
            continue
        if isinstance(group, (str, int)):
            raw_values: Iterable[object] = [group]
        else:
            try:
                raw_values = list(group)  # type: ignore[arg-type]
            except TypeError:
                raw_values = [group]
        for value in raw_values:
            token = str(value or "").strip()
            if token:
                normalized.add(token)
    return sorted(normalized)


def collect_source_refs(*groups: object) -> list[str]:
    """Collect stable source references used to assemble a response."""

    return normalize_entity_ids(*groups)


# ── ccdash-unattributed-0910 ────────────────────────────────────────────────
# THE single exclusion predicate for cross-project aggregates/leaderboards/the
# effort_tier package (routing_rollup.py): a project row with
# ``bucket_role IS NOT NULL`` (the unattributed-bucket fold's frozen row, or a
# drained former catch-all kept for audit). Every consumer that builds a
# multi-project rollup calls this one function rather than re-deriving the
# excluded id set ad hoc. Session-level reads (a specific project_id's own
# sessions) must NOT call this -- the bucket's sessions stay directly
# queryable by design (see scripts/fold_unattributed_bucket.py).
_BUCKET_ROLE_SQLITE_SQL = "SELECT id FROM projects WHERE bucket_role IS NOT NULL"
_BUCKET_ROLE_PG_SQL = "SELECT id FROM projects WHERE bucket_role IS NOT NULL"


async def fetch_bucket_project_ids(db: Any) -> set[str]:
    """Return ids of every project flagged ``bucket_role IS NOT NULL``.

    Dual-path for SQLite (aiosqlite) and PostgreSQL (asyncpg), mirroring the
    ``isinstance(db, aiosqlite.Connection)`` convention established in
    ``system_metrics.py``. An empty result (the common case pre-fold) means
    "exclude nothing" -- callers must not treat it as an error.
    """
    if isinstance(db, aiosqlite.Connection):
        async with db.execute(_BUCKET_ROLE_SQLITE_SQL) as cur:
            rows = await cur.fetchall()
            return {row[0] for row in rows}
    rows = await db.fetch(_BUCKET_ROLE_PG_SQL)
    return {row["id"] for row in rows}


def exclude_bucket_projects(projects: Iterable[Project], excluded_ids: set[str]) -> list[Project]:
    """Drop any project whose id is in *excluded_ids* (see ``fetch_bucket_project_ids``)."""

    return [p for p in projects if p.id not in excluded_ids]


def derive_data_freshness(*values: object) -> datetime:
    """Return the freshest timestamp seen across successful source rows."""

    candidates = [_coerce_datetime(value) for value in values]
    filtered = [candidate for candidate in candidates if candidate is not None]
    if not filtered:
        return datetime.now(timezone.utc)
    return max(filtered)
