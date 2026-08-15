"""Are-We-Winning dashboard query service (are-we-winning-dashboard-v1, M2).

Computes weekly created/completed/reopened rollups and the 3-bucket
self-caught ratio, plus their drill-through row lookups, **entirely from
CCDash's own cache** — ``intent_tree_events`` (M1 — see
``backend/application/services/ingest/intenttree_events_ingest.py``) and the
two M2-part-B derived-cache tables, ``intent_tree_reopened_events`` /
``intent_tree_self_caught_buckets`` (see
``backend/application/services/ingest/intenttree_reopened_derivation.py`` /
``intenttree_self_caught_derivation.py``). Zero live IntentTree calls, zero
model calls, on this module's render path — the derivation passes that
populate the two part-B tables run only from a scheduled job, never from
here.

Scope boundary
----------------
This module implements:
  - weekly created/completed trendlines (M2 part A), bucketed by **ISO
    calendar week** (Monday-Sunday, OQ-2 decision — a stable cache key,
    never a rolling 7-day window)
  - the weekly reopened trendline (M2 part B), read from the pre-derived
    ``intent_tree_reopened_events`` cache
  - the 3-bucket self-caught ratio (M2 part B: self_caught/other_caught/
    unknown), read from the pre-derived ``intent_tree_self_caught_buckets``
    cache
  - drill-through: the exact underlying node rows behind any rendered count
    (per-week bucket for created/completed/reopened; per-bucket for the
    self-caught ratio), cursor-paginated

``compute_reopened_trendline`` and ``compute_self_caught_ratio`` are pure
cache readers — they never call IntentTree, never re-derive, and never
invent a value for a field the derivation job hasn't populated yet.
``get_summary`` only populates ``reopened``/``self_caught_ratio`` once the
corresponding derivation pass has completed at least one successful sweep
(checked via the ``ingest_cursors`` watermark, never inferred from table
row-count alone — an empty-but-*derived* result must be distinguishable from
"never derived"); until then both stay ``None`` (never a fabricated ``0``).

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
from typing import Any, Literal

import aiosqlite

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.ingest.intenttree_reopened_derivation import (
    SOURCE_ID as REOPENED_DERIVATION_SOURCE_ID,
)
from backend.application.services.ingest.intenttree_self_caught_derivation import (
    OTHER_CAUGHT_BUCKET,
    SELF_CAUGHT_BUCKET,
    SOURCE_ID as SELF_CAUGHT_DERIVATION_SOURCE_ID,
    UNKNOWN_BUCKET,
)
from backend.models import (
    AreWeWinningDrillThroughPageDTO,
    AreWeWinningDrillThroughRowDTO,
    AreWeWinningSelfCaughtDrillThroughPageDTO,
    AreWeWinningSelfCaughtDrillThroughRowDTO,
    AreWeWinningSummaryDTO,
    AreWeWinningTrendlineDTO,
    AreWeWinningWeeklyPointDTO,
    SelfCaughtRatioBucketDTO,
    SelfCaughtRatioDTO,
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

#: The closed 3-value vocabulary for self-caught-ratio buckets, mirrored from
#: ``SelfCaughtRatioBucketDTO.bucket``'s own ``Literal`` type (backend/models.py).
SelfCaughtBucket = Literal["self_caught", "other_caught", "unknown"]


def _narrow_self_caught_bucket(value: str) -> SelfCaughtBucket:
    """Narrow an arbitrary DB-stored bucket token to the closed vocabulary.

    This is the boundary where a stored value leaves the database and enters
    a ``Literal["self_caught", "other_caught", "unknown"]``-typed surface
    (``SelfCaughtRatioBucketDTO.bucket``). An unrecognized token -- which
    should never happen since the derivation service only ever writes the
    closed vocabulary, but a stored value is never trustworthy by
    construction -- maps to ``"unknown"`` rather than raising or passing a
    bare ``str`` through un-narrowed. This is the one check that makes the
    closed-vocabulary guarantee real rather than merely documented.
    """
    if value == SELF_CAUGHT_BUCKET:
        return "self_caught"
    if value == OTHER_CAUGHT_BUCKET:
        return "other_caught"
    return "unknown"


#: Canonical, closed-vocabulary iteration order for self-caught-ratio buckets
#: (mirrors the ``decide_attribution`` never-silently-divide convention).
_SELF_CAUGHT_BUCKET_ORDER: tuple[SelfCaughtBucket, ...] = tuple(
    _narrow_self_caught_bucket(value)
    for value in (SELF_CAUGHT_BUCKET, OTHER_CAUGHT_BUCKET, UNKNOWN_BUCKET)
)

# The two event types M1 ingests and this module reads. Kept in sync with
# ``backend.application.services.ingest.intenttree_events_ingest.EVENT_TYPES``
# by convention, not by import — that module owns ingestion, this one owns
# reads, and the two are allowed to diverge if a future milestone ingests
# more event types than M2 part A rolls up.
EVENT_TYPES: tuple[str, ...] = ("node.created", "node.completed")

_DEFAULT_DRILL_THROUGH_LIMIT = 50
_MAX_DRILL_THROUGH_LIMIT = 200


# ── Part B extension points — NOT implemented here ──────────────────────────


async def _derivation_has_ever_run(db: Any, source_id: str) -> bool:
    """True iff the derivation job identified by *source_id* has completed a
    successful pass at least once (``ingest_cursors.last_ingest_at`` set on
    any row for that source, regardless of which IntentTree workspace it
    ran against — this deployment binds to exactly one workspace).

    This is the never-run-yet vs. ran-and-empty distinguisher: a table with
    zero rows is ambiguous on its own (could mean "job never ran" or "job
    ran, found nothing"), but the ``ingest_cursors`` watermark is not — a row
    with ``last_ingest_at IS NOT NULL`` only ever gets written by
    ``IntentTreeReopenedDerivationService``/``IntentTreeSelfCaughtDerivationService``
    on a fully clean pass (see those modules' fail-soft contracts). A read-
    only SELECT — this is the render path and must never write.
    """
    sqlite_sql = (
        "SELECT 1 FROM ingest_cursors WHERE source_id = ? "
        "AND last_ingest_at IS NOT NULL LIMIT 1"  # noqa: S608
    )
    pg_sql = (
        "SELECT 1 FROM ingest_cursors WHERE source_id = $1 "
        "AND last_ingest_at IS NOT NULL LIMIT 1"  # noqa: S608
    )
    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sqlite_sql, (source_id,)) as cur:
            row = await cur.fetchone()
    else:
        row = await db.fetchrow(pg_sql, source_id)
    return row is not None


async def _fetch_reopened_events(db: Any) -> list[tuple[Any, ...]]:
    """Return every ``intent_tree_reopened_events`` row, oldest first.

    Row shape: ``(id, node_id, from_status, to_status, occurred_at)``. Pure
    cache read — never touches IntentTree.
    """
    sqlite_sql = (
        "SELECT id, node_id, from_status, to_status, occurred_at "
        "FROM intent_tree_reopened_events ORDER BY occurred_at ASC"  # noqa: S608
    )
    pg_sql = sqlite_sql
    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sqlite_sql) as cur:
            rows = await cur.fetchall()
    else:
        rows = await db.fetch(pg_sql)
    return [tuple(row) for row in rows]


async def _fetch_self_caught_buckets(db: Any) -> list[tuple[Any, ...]]:
    """Return every ``intent_tree_self_caught_buckets`` row.

    Row shape: ``(node_id, bucket, reason)``. Pure cache read — never
    touches IntentTree.
    """
    sqlite_sql = "SELECT node_id, bucket, reason FROM intent_tree_self_caught_buckets"  # noqa: S608
    pg_sql = sqlite_sql
    if isinstance(db, aiosqlite.Connection):
        async with db.execute(sqlite_sql) as cur:
            rows = await cur.fetchall()
    else:
        rows = await db.fetch(pg_sql)
    return [tuple(row) for row in rows]


async def compute_reopened_trendline(db: Any) -> AreWeWinningTrendlineDTO:
    """Weekly reopened trendline, read entirely from the pre-derived cache.

    A pure cache reader — never calls IntentTree, never re-derives. Buckets
    each ``intent_tree_reopened_events`` row's ``occurred_at`` (the terminal-
    status-leaving transition timestamp) by ISO calendar week, identically to
    ``_weekly_rollup``'s created/completed bucketing (same OQ-2 convention).
    """
    rows = await _fetch_reopened_events(db)
    buckets: dict[tuple[int, int], dict[str, Any]] = {}
    for _id, _node_id, _from_status, _to_status, occurred_at in rows:
        dt = _parse_occurred_at(occurred_at)
        if dt is None:
            continue
        iso_year, iso_week, week_start = _iso_week_bucket(dt)
        key = (iso_year, iso_week)
        bucket = buckets.setdefault(key, {"week_start_date": week_start, "count": 0})
        bucket["count"] += 1

    points = [
        AreWeWinningWeeklyPointDTO(
            iso_year=iso_year,
            iso_week=iso_week,
            week_start_date=bucket["week_start_date"].isoformat(),
            count=bucket["count"],
        )
        for (iso_year, iso_week), bucket in sorted(buckets.items())
    ]
    return AreWeWinningTrendlineDTO(event_type="node.reopened", points=points)


async def compute_self_caught_ratio(db: Any) -> SelfCaughtRatioDTO:
    """3-bucket self-caught ratio, read entirely from the pre-derived cache.

    A pure cache reader — never calls IntentTree, never re-derives, never
    re-decides a bucket (that is ``decide_self_caught_bucket``'s job, at
    derivation time only). Counts every bucket, including ``unknown`` — the
    total is the sum of all three, never a denominator with ``unknown``
    removed (never-silently-divide, structural: there is no branch here that
    skips a bucket).
    """
    rows = await _fetch_self_caught_buckets(db)
    counts: dict[SelfCaughtBucket, int] = {bucket: 0 for bucket in _SELF_CAUGHT_BUCKET_ORDER}
    for _node_id, bucket, _reason in rows:
        # Forward-compat: an unrecognized token in the cache (should never
        # happen -- the derivation service only ever writes the closed
        # vocabulary) is narrowed to unknown via _narrow_self_caught_bucket
        # rather than raising or being silently dropped from the total.
        key = _narrow_self_caught_bucket(bucket)
        counts[key] = counts.get(key, 0) + 1

    buckets = [
        SelfCaughtRatioBucketDTO(bucket=bucket, count=counts[bucket])
        for bucket in _SELF_CAUGHT_BUCKET_ORDER
    ]
    return SelfCaughtRatioDTO(buckets=buckets, total=sum(counts.values()))


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


async def _reopened_drill_through_rows(
    db: Any,
    *,
    iso_year: int,
    iso_week: int,
) -> list[dict[str, Any]]:
    """Return every ``intent_tree_reopened_events`` row matching (iso_year, iso_week).

    Mirrors ``_drill_through_rows`` exactly, reading the pre-derived reopened
    cache instead of the raw ingested event log -- the M2-part-B drill-
    through parity requirement (any rendered count returns its exact
    underlying node rows, including the reopened trendline).
    """
    week_start = date.fromisocalendar(iso_year, iso_week, 1)
    week_end = week_start + timedelta(days=7)

    rows = await _fetch_reopened_events(db)
    matched: list[dict[str, Any]] = []
    for row_id, node_id, from_status, to_status, occurred_at in rows:
        dt = _parse_occurred_at(occurred_at)
        if dt is None:
            continue
        if not (week_start <= dt.date() < week_end):
            continue
        matched.append(
            {
                "id": row_id,
                "node_id": node_id,
                "event_type": "node.reopened",
                "occurred_at": str(occurred_at),
                "from_status": from_status,
                "to_status": to_status,
            }
        )
    return matched


async def _self_caught_drill_through_rows(db: Any, *, bucket: str) -> list[dict[str, Any]]:
    """Return every ``intent_tree_self_caught_buckets`` row for *bucket*.

    Unlike the trendline drill-throughs, there is no week coordinate here --
    a self-caught bucket is a per-node, non-time-bucketed verdict.
    """
    rows = await _fetch_self_caught_buckets(db)
    return [
        {"node_id": node_id, "bucket": row_bucket, "reason": reason}
        for node_id, row_bucket, reason in rows
        if row_bucket == bucket
    ]


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


def _reopened_drill_through_params(
    self: Any,  # noqa: ARG001
    context: RequestContext,  # noqa: ARG001
    ports: CorePorts,  # noqa: ARG001
    *,
    iso_year: int,
    iso_week: int,
    cursor: str | None = None,
    limit: int = _DEFAULT_DRILL_THROUGH_LIMIT,
    **_: Any,
) -> dict[str, Any]:
    return {
        "project_id": "",
        "iso_year": iso_year,
        "iso_week": iso_week,
        "cursor": cursor or "",
        "limit": limit,
    }


def _self_caught_drill_through_params(
    self: Any,  # noqa: ARG001
    context: RequestContext,  # noqa: ARG001
    ports: CorePorts,  # noqa: ARG001
    *,
    bucket: str,
    cursor: str | None = None,
    limit: int = _DEFAULT_DRILL_THROUGH_LIMIT,
    **_: Any,
) -> dict[str, Any]:
    return {
        "project_id": "",
        "bucket": bucket,
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
        """Return the weekly created/completed/reopened trendlines + self-caught ratio.

        ``reopened``/``self_caught_ratio`` are populated from the pre-derived
        M2-part-B cache tables **only if** that derivation's ``ingest_cursors``
        watermark shows at least one completed pass (``_derivation_has_ever_run``)
        — otherwise they stay ``None`` (never a fabricated ``0``/empty-shape).
        This method never calls IntentTree and never re-derives; it is a pure
        cache read exactly like the created/completed rollups above.
        """
        with otel.start_span("ccdash.are_we_winning.get_summary", {}):
            db = ports.storage.db
            created_points = await _weekly_rollup(db, "node.created")
            completed_points = await _weekly_rollup(db, "node.completed")

            reopened: AreWeWinningTrendlineDTO | None = None
            if await _derivation_has_ever_run(db, REOPENED_DERIVATION_SOURCE_ID):
                reopened = await compute_reopened_trendline(db)

            self_caught_ratio: SelfCaughtRatioDTO | None = None
            if await _derivation_has_ever_run(db, SELF_CAUGHT_DERIVATION_SOURCE_ID):
                self_caught_ratio = await compute_self_caught_ratio(db)

            return AreWeWinningSummaryDTO(
                created=AreWeWinningTrendlineDTO(event_type="node.created", points=created_points),
                completed=AreWeWinningTrendlineDTO(event_type="node.completed", points=completed_points),
                reopened=reopened,
                self_caught_ratio=self_caught_ratio,
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
        """Return the exact node rows behind one rendered (event_type, iso_year, iso_week) bucket.

        Takes the same coordinates ``get_summary``'s trendline points emit,
        for **any** of the three trendlines -- ``event_type`` may be
        ``node.created``/``node.completed`` (read from the raw ``intent_tree_
        events`` cache) or ``node.reopened`` (M2 part B: read from the
        pre-derived ``intent_tree_reopened_events`` cache). This single
        generic endpoint is what the already-shipped M3 frontend calls for
        every trendline's click handler (``trendline.event_type`` round-
        trips verbatim into this parameter) -- ``node.reopened`` support was
        added here, not as a frontend change, specifically so that surface
        does not silently start returning a decorative empty page the
        moment ``reopened`` stops being ``None`` (the plan's rubric: "a
        decorative click target is an AC failure"). Paginated in the repo's
        ``{items, cursor, limit, nextCursor}`` envelope shape (mirrors
        ``session_detail.py``'s transcript pagination).
        """
        if event_type not in EVENT_TYPES and event_type != "node.reopened":
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
            if event_type == "node.reopened":
                all_rows = await _reopened_drill_through_rows(db, iso_year=iso_year, iso_week=iso_week)
            else:
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

    @memoized_query("are_we_winning_reopened_drill_through", param_extractor=_reopened_drill_through_params)
    async def get_reopened_drill_through(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        iso_year: int,
        iso_week: int,
        cursor: str | None = None,
        limit: int = _DEFAULT_DRILL_THROUGH_LIMIT,
    ) -> AreWeWinningDrillThroughPageDTO:
        """Return the exact ``intent_tree_reopened_events`` rows behind one rendered week bucket.

        Same (iso_year, iso_week) coordinates ``get_summary``'s ``reopened``
        trendline points emit -- M2-part-B drill-through parity with the
        created/completed trendlines. Pure cache read.
        """
        eff_limit = max(1, min(limit, _MAX_DRILL_THROUGH_LIMIT))
        offset = _decode_cursor(cursor)

        with otel.start_span(
            "ccdash.are_we_winning.get_reopened_drill_through",
            {"iso_year": iso_year, "iso_week": iso_week},
        ):
            db = ports.storage.db
            all_rows = await _reopened_drill_through_rows(db, iso_year=iso_year, iso_week=iso_week)
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

    @memoized_query(
        "are_we_winning_self_caught_drill_through", param_extractor=_self_caught_drill_through_params
    )
    async def get_self_caught_drill_through(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        bucket: str,
        cursor: str | None = None,
        limit: int = _DEFAULT_DRILL_THROUGH_LIMIT,
    ) -> AreWeWinningSelfCaughtDrillThroughPageDTO:
        """Return the exact ``intent_tree_self_caught_buckets`` rows behind one rendered ratio bucket.

        *bucket* must be one of the closed vocabulary
        (self_caught/other_caught/unknown); an unrecognized value returns an
        empty page rather than raising -- mirrors ``get_drill_through``'s
        unknown-``event_type`` handling. Pure cache read.
        """
        from backend.application.services.ingest.intenttree_self_caught_derivation import (
            SELF_CAUGHT_RATIO_VOCAB,
        )

        if bucket not in SELF_CAUGHT_RATIO_VOCAB:
            return AreWeWinningSelfCaughtDrillThroughPageDTO(
                items=[],
                total=0,
                limit=limit,
                cursor=_encode_cursor(0),
                next_cursor=None,
            )

        eff_limit = max(1, min(limit, _MAX_DRILL_THROUGH_LIMIT))
        offset = _decode_cursor(cursor)

        with otel.start_span(
            "ccdash.are_we_winning.get_self_caught_drill_through", {"bucket": bucket}
        ):
            db = ports.storage.db
            all_rows = await _self_caught_drill_through_rows(db, bucket=bucket)
            total = len(all_rows)
            page_rows = all_rows[offset : offset + eff_limit]

            node_ids = {str(r["node_id"]) for r in page_rows if r.get("node_id")}
            title_map = await _build_title_map(db, node_ids)

            items = [
                AreWeWinningSelfCaughtDrillThroughRowDTO(
                    node_id=str(r["node_id"]),
                    bucket=r["bucket"],
                    reason=r.get("reason"),
                    title=title_map.get(str(r["node_id"])),
                )
                for r in page_rows
            ]

            has_more = offset + eff_limit < total
            next_cursor = _encode_cursor(offset + eff_limit) if has_more else None

            return AreWeWinningSelfCaughtDrillThroughPageDTO(
                items=items,
                total=total,
                limit=eff_limit,
                cursor=_encode_cursor(offset),
                next_cursor=next_cursor,
            )
