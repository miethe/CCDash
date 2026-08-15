"""Are-We-Winning dashboard query service (are-we-winning-dashboard-v1, M2 part A).

Computes weekly created/completed rollups and their drill-through row lookup
**entirely from CCDash's own `intent_tree_events` cache** (M1 — see
``backend/application/services/ingest/intenttree_events_ingest.py``). Zero
live IntentTree calls, zero model calls, on this module's render path.

Scope boundary (binding, per the M2-part-A task)
--------------------------------------------------
This module implements:
  - weekly created/completed trendlines, bucketed by **ISO calendar week**
    (Monday-Sunday, OQ-2 decision — a stable cache key, never a rolling
    7-day window)
  - drill-through: the exact underlying ``intent_tree_events`` rows behind
    any rendered (event_type, iso_year, iso_week) bucket, cursor-paginated

This module deliberately does **not** implement:
  - the ``reopened`` trendline (bounded per-node status-history derivation)
  - the 3-bucket self-caught ratio (self_caught/other_caught/unknown)

Those two are part B — a separate, deliberately claude-primary execution
lane per the plan's ``routing_constraints`` (a wrong terminal-status
transition boundary, or a misrouted self-caught/other-caught bucket, is
*silently plausible* and would misreport regression/attribution, not just
render wrong). ``compute_reopened_trendline`` and ``compute_self_caught_ratio``
below are the marked extension points part B plugs into — this module never
calls them, and ``get_summary`` always sets ``reopened``/``self_caught_ratio``
to ``None`` (never a fabricated ``0``).

Caching hazard (named in the plan's risk list)
-----------------------------------------------
``PostgresCacheBackend.aset`` (``cache.py``) already guards non-JSON-native
values via ``_json_safe`` (fixed on main, ``579aaf2``), so returning a
pydantic model from a memoized method is safe today. This module is still
deliberate about it: the memoized methods below return the pydantic response
DTOs directly (matching ``system_metrics.py``'s established pattern), relying
on that existing guard rather than hand-rolling a second serialization path.
See the implementation notes for why this was judged safe rather than
defensively flattening to plain dicts.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import aiosqlite

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.models import (
    AreWeWinningDrillThroughPageDTO,
    AreWeWinningDrillThroughRowDTO,
    AreWeWinningSummaryDTO,
    AreWeWinningTrendlineDTO,
    AreWeWinningWeeklyPointDTO,
)
from backend.observability import otel

from .cache import memoized_query

logger = logging.getLogger("ccdash.agent_queries.are_we_winning")

__all__ = [
    "EVENT_TYPES",
    "AreWeWinningQueryService",
    "compute_reopened_trendline",
    "compute_self_caught_ratio",
]

# The two event types M1 ingests and this module reads. Kept in sync with
# ``backend.application.services.ingest.intenttree_events_ingest.EVENT_TYPES``
# by convention, not by import — that module owns ingestion, this one owns
# reads, and the two are allowed to diverge if a future milestone ingests
# more event types than M2 part A rolls up.
EVENT_TYPES: tuple[str, ...] = ("node.created", "node.completed")

_DEFAULT_DRILL_THROUGH_LIMIT = 50
_MAX_DRILL_THROUGH_LIMIT = 200


# ── Part B extension points — NOT implemented here ──────────────────────────


def compute_reopened_trendline(*_args: Any, **_kwargs: Any) -> None:
    """Extension point for the M2 part-B reopened-derivation task.

    Deliberately raises: this module never calls it. Walking per-node status
    history to detect a terminal-status regression is silently plausible to
    get wrong (see the plan's ``routing_constraints``), so it is reserved for
    a separate claude-primary execution lane rather than implemented here.
    """
    raise NotImplementedError(
        "M2-part-B: reopened-trendline derivation is reserved for a separate "
        "execution lane. Do not implement it here — see the plan's "
        "routing_constraints."
    )


def compute_self_caught_ratio(*_args: Any, **_kwargs: Any) -> None:
    """Extension point for the M2 part-B self-caught-ratio task.

    Deliberately raises: this module never calls it. Misrouting a node into
    self_caught/other_caught instead of unknown when the proxy signal is
    absent is silently plausible and would violate the never-silently-divide
    requirement, so it is reserved for a separate claude-primary execution
    lane rather than implemented here.
    """
    raise NotImplementedError(
        "M2-part-B: self-caught-ratio bucketing is reserved for a separate "
        "execution lane. Do not implement it here — see the plan's "
        "routing_constraints."
    )


# ── Cursor helpers (opaque base64 JSON, mirrors session_detail.py) ─────────


def _encode_cursor(offset: int) -> str:
    raw = json.dumps({"o": offset}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        payload = json.loads(raw)
        return max(0, int(payload.get("o", 0)))
    except Exception:  # noqa: BLE001
        logger.warning("are_we_winning: invalid cursor %r — resetting to offset 0", cursor)
        return 0


# ── occurred_at parsing + ISO-week bucketing ────────────────────────────────


def _parse_occurred_at(raw: Any) -> datetime | None:
    """Parse an ``intent_tree_events.occurred_at`` TEXT value into a UTC datetime.

    Returns ``None`` on any unparseable value — a malformed row is skipped
    from bucketing/drill-through rather than crashing the whole query.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
    raw_str = str(raw).strip()
    if not raw_str:
        return None
    normalized = raw_str[:-1] if raw_str.endswith("Z") else raw_str
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    logger.warning("are_we_winning: could not parse occurred_at=%r", raw)
    return None


def _iso_week_bucket(dt: datetime) -> tuple[int, int, date]:
    """Return (iso_year, iso_week, week_start_date) for *dt* (Monday-Sunday).

    Delegates to ``datetime.isocalendar()`` — the standard-library ISO 8601
    week implementation — which is what makes the year-boundary case (a late
    December date landing in the *next* ISO year's week 1, or an early
    January date landing in the *previous* ISO year's week 52/53) correct by
    construction rather than by a hand-rolled boundary check.
    """
    iso_year, iso_week, iso_weekday = dt.isocalendar()
    week_start = dt.date() - timedelta(days=iso_weekday - 1)
    return iso_year, iso_week, week_start


# ── Raw event fetch (dual SQLite/Postgres path, mirrors system_metrics.py) ──


async def _fetch_events_by_type(db: Any, event_type: str) -> list[tuple[Any, ...]]:
    """Return every ``intent_tree_events`` row for *event_type*, oldest first.

    Full-table-scoped-by-type fetch, not a windowed query: the measured live
    volume (3,941 node.created + 745 node.completed rows, per the worknote)
    makes this affordable, and it sidesteps writing ISO-week-bucket SQL in
    two dialects (see the module docstring). Row shape:
    ``(id, node_id, event_type, occurred_at, payload_json)``.
    """
    sqlite_sql = (
        "SELECT id, node_id, event_type, occurred_at, payload_json "
        "FROM intent_tree_events WHERE event_type = ? ORDER BY occurred_at ASC"  # noqa: S608
    )
    pg_sql = (
        "SELECT id, node_id, event_type, occurred_at, payload_json "
        "FROM intent_tree_events WHERE event_type = $1 ORDER BY occurred_at ASC"  # noqa: S608
    )
    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sqlite_sql, (event_type,)) as cur:
            rows = await cur.fetchall()
    else:
        rows = await db.fetch(pg_sql, event_type)
    return [tuple(row) for row in rows]


def _extract_title(payload_json: Any) -> str | None:
    if not payload_json:
        return None
    try:
        payload = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    title = payload.get("title")
    return str(title) if title else None


async def _build_title_map(db: Any, node_ids: set[str]) -> dict[str, str]:
    """Resolve *node_ids* to their ``node.created`` payload title, when available."""
    if not node_ids:
        return {}
    created_rows = await _fetch_events_by_type(db, "node.created")
    titles: dict[str, str] = {}
    for _id, node_id, _event_type, _occurred_at, payload_json in created_rows:
        if node_id not in node_ids:
            continue
        title = _extract_title(payload_json)
        if title:
            titles[str(node_id)] = title
    return titles


# ── Weekly rollup ────────────────────────────────────────────────────────────


async def _weekly_rollup(db: Any, event_type: str) -> list[AreWeWinningWeeklyPointDTO]:
    rows = await _fetch_events_by_type(db, event_type)
    buckets: dict[tuple[int, int], dict[str, Any]] = {}
    for _id, _node_id, _event_type, occurred_at, _payload_json in rows:
        dt = _parse_occurred_at(occurred_at)
        if dt is None:
            continue
        iso_year, iso_week, week_start = _iso_week_bucket(dt)
        key = (iso_year, iso_week)
        bucket = buckets.setdefault(key, {"week_start_date": week_start, "count": 0})
        bucket["count"] += 1

    return [
        AreWeWinningWeeklyPointDTO(
            iso_year=iso_year,
            iso_week=iso_week,
            week_start_date=bucket["week_start_date"].isoformat(),
            count=bucket["count"],
        )
        for (iso_year, iso_week), bucket in sorted(buckets.items())
    ]


# ── Drill-through ────────────────────────────────────────────────────────────


async def _drill_through_rows(
    db: Any,
    *,
    event_type: str,
    iso_year: int,
    iso_week: int,
) -> list[dict[str, Any]]:
    """Return every ``intent_tree_events`` row matching (event_type, iso_year, iso_week).

    Takes the exact same bucket coordinates ``_weekly_rollup`` emits, so a UI
    click on a rendered point maps 1:1 onto this query.
    """
    week_start = date.fromisocalendar(iso_year, iso_week, 1)
    week_end = week_start + timedelta(days=7)

    rows = await _fetch_events_by_type(db, event_type)
    matched: list[dict[str, Any]] = []
    for row_id, node_id, row_event_type, occurred_at, _payload_json in rows:
        dt = _parse_occurred_at(occurred_at)
        if dt is None:
            continue
        if not (week_start <= dt.date() < week_end):
            continue
        matched.append(
            {
                "id": row_id,
                "node_id": node_id,
                "event_type": row_event_type,
                "occurred_at": str(occurred_at),
            }
        )
    return matched


# ── Cache param extractors ──────────────────────────────────────────────────


def _summary_params(
    self: Any,  # noqa: ARG001
    context: RequestContext,  # noqa: ARG001
    ports: CorePorts,  # noqa: ARG001
    **_: Any,
) -> dict[str, Any]:
    # IntentTree's event log is workspace-scoped, not CCDash-project-scoped
    # (M1 precedent — see the SENTINEL_PROJECT_ID note in the ingest service).
    # Force project_id="" so the cache key lands in the global scope slot,
    # mirroring system_metrics._system_active_count_params exactly.
    return {"project_id": ""}


def _drill_through_params(
    self: Any,  # noqa: ARG001
    context: RequestContext,  # noqa: ARG001
    ports: CorePorts,  # noqa: ARG001
    *,
    event_type: str,
    iso_year: int,
    iso_week: int,
    cursor: str | None = None,
    limit: int = _DEFAULT_DRILL_THROUGH_LIMIT,
    **_: Any,
) -> dict[str, Any]:
    return {
        "project_id": "",
        "event_type": event_type,
        "iso_year": iso_year,
        "iso_week": iso_week,
        "cursor": cursor or "",
        "limit": limit,
    }


# ── Service ──────────────────────────────────────────────────────────────────


class AreWeWinningQueryService:
    """Transport-neutral query service for the are-we-winning dashboard (M2 part A).

    Mirrors the structural shape of ``SystemMetricsQueryService`` — a
    ``@memoized_query``-decorated method per read, computed entirely from
    CCDash's own cache DB, with zero live IntentTree calls and zero model
    calls at request time.
    """

    @memoized_query("are_we_winning_summary", param_extractor=_summary_params)
    async def get_summary(
        self,
        context: RequestContext,
        ports: CorePorts,
    ) -> AreWeWinningSummaryDTO:
        """Return the weekly created/completed trendlines (+ absent part-B fields).

        ``reopened`` and ``self_caught_ratio`` are always ``None`` here — see
        the module docstring's scope boundary. Never call
        ``compute_reopened_trendline``/``compute_self_caught_ratio`` from
        this method; that is part B's job, in a separate change.
        """
        with otel.start_span("ccdash.are_we_winning.get_summary", {}):
            db = ports.storage.db
            created_points = await _weekly_rollup(db, "node.created")
            completed_points = await _weekly_rollup(db, "node.completed")

            return AreWeWinningSummaryDTO(
                created=AreWeWinningTrendlineDTO(event_type="node.created", points=created_points),
                completed=AreWeWinningTrendlineDTO(event_type="node.completed", points=completed_points),
                reopened=None,
                self_caught_ratio=None,
                generated_at=datetime.now(timezone.utc),
            )

    @memoized_query("are_we_winning_drill_through", param_extractor=_drill_through_params)
    async def get_drill_through(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        event_type: str,
        iso_year: int,
        iso_week: int,
        cursor: str | None = None,
        limit: int = _DEFAULT_DRILL_THROUGH_LIMIT,
    ) -> AreWeWinningDrillThroughPageDTO:
        """Return the exact ``intent_tree_events`` rows behind one rendered bucket.

        Takes the same (event_type, iso_year, iso_week) coordinates
        ``get_summary``'s trendline points emit. Paginated in the repo's
        ``{items, cursor, limit, nextCursor}`` envelope shape (mirrors
        ``session_detail.py``'s transcript pagination).
        """
        if event_type not in EVENT_TYPES:
            return AreWeWinningDrillThroughPageDTO(
                items=[],
                total=0,
                limit=limit,
                cursor=_encode_cursor(0),
                next_cursor=None,
            )

        eff_limit = max(1, min(limit, _MAX_DRILL_THROUGH_LIMIT))
        offset = _decode_cursor(cursor)

        with otel.start_span(
            "ccdash.are_we_winning.get_drill_through",
            {"event_type": event_type, "iso_year": iso_year, "iso_week": iso_week},
        ):
            db = ports.storage.db
            all_rows = await _drill_through_rows(
                db, event_type=event_type, iso_year=iso_year, iso_week=iso_week
            )
            total = len(all_rows)
            page_rows = all_rows[offset : offset + eff_limit]

            node_ids = {str(r["node_id"]) for r in page_rows if r.get("node_id")}
            title_map = await _build_title_map(db, node_ids)

            items = [
                AreWeWinningDrillThroughRowDTO(
                    node_id=(str(r["node_id"]) if r.get("node_id") else None),
                    event_type=str(r["event_type"]),
                    occurred_at=str(r["occurred_at"]),
                    title=title_map.get(str(r["node_id"])) if r.get("node_id") else None,
                )
                for r in page_rows
            ]

            has_more = offset + eff_limit < total
            next_cursor = _encode_cursor(offset + eff_limit) if has_more else None

            return AreWeWinningDrillThroughPageDTO(
                items=items,
                total=total,
                limit=eff_limit,
                cursor=_encode_cursor(offset),
                next_cursor=next_cursor,
            )
