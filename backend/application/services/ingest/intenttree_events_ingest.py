"""Cursor-paginated, fail-soft ingestion of IntentTree lifecycle events.

are-we-winning-dashboard-v1 M1 (see ``docs/project_plans/implementation_plans/
features/are-we-winning-dashboard-v1.md`` and the mandatory ground-truth
worknote ``.claude/worknotes/are-we-winning-dashboard/measured-data-
availability.md``). CCDash holds zero IntentTree lifecycle-event data before
this module; it is the sole source that populates ``intent_tree_events``.

Pipeline, once per configured event type (``node.created``, ``node.completed``):

  1. GET ``{api_url}/api/v1/events`` with ``workspace_id`` (required by the
     IntentTree API), ``event_type``, an optional ``tree_id`` filter, and
     ``limit`` (server-capped at 200 -- ``limit=500`` silently returns 200;
     see the worknote). The envelope is ``{items, next_cursor, total}``.
  2. Loop on ``next_cursor`` until it is falsy -- a single call is never
     trusted to have fetched everything (AC1).
  3. Upsert every item into ``intent_tree_events`` keyed on the IntentTree
     event ``id`` (idempotent -- re-ingesting an overlapping page is a
     silent no-op for already-seen rows, AC3).
  4. On success, advance the ``ingest_cursors`` watermark row (bookkeeping/
     durability only -- see ``_cursor_advance`` docstring). On any HTTP
     failure (connection error or non-2xx status) at any point in a given
     event type's sweep, log a warning, record the error on the cursor
     (best-effort), and return cleanly for that event type without raising
     (AC2, fail-soft). Rows already committed from earlier successful pages
     in the same run are NOT rolled back -- they are real, idempotently
     upserted events; only a *totally* unreachable IntentTree API (the
     failure mode ``verified`` by the fail-soft test) leaves the cache
     byte-identical to before the run, because zero pages ever succeed.

The ``ingest_cursors`` table (ADR-009) is reused rather than adding a
dedicated cursor table -- see the module docstring on ``SOURCE_ID`` below for
why and how it's keyed for this non-project-scoped source.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx

from backend.db.repositories.base import retry_on_locked

logger = logging.getLogger("ccdash.ingest.intenttree_events")

# ── Cursor source identity ───────────────────────────────────────────────────
#
# ``ingest_cursors`` is keyed on (source_id, project_id, workspace_id) and
# ``project_id`` is NOT NULL with no default (ADR-009) -- it exists to scope
# per-CCDash-project sources like the filesystem/remote-session ingest. This
# feature's events are IntentTree-workspace-scoped, not CCDash-project-scoped,
# so we reuse the table with a fixed sentinel project_id ("global") rather
# than adding a dedicated cursor table -- documented deviation, see
# .claude/worknotes/are-we-winning-dashboard/implementation-notes.md.
# One source_id per event type so each type's watermark advances
# independently (the table has no event_type column of its own).

SENTINEL_PROJECT_ID: str = "global"
EVENT_TYPES: tuple[str, ...] = ("node.created", "node.completed")


def source_id_for(event_type: str) -> str:
    return f"intenttree:{event_type}"


# ── Result types ──────────────────────────────────────────────────────────────


@dataclass(slots=True)
class EventTypeIngestResult:
    event_type: str
    ok: bool
    rows_seen: int = 0
    rows_written: int = 0
    pages_fetched: int = 0
    error: str | None = None


@dataclass(slots=True)
class IntentTreeIngestResult:
    per_event_type: list[EventTypeIngestResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.per_event_type)

    @property
    def rows_written(self) -> int:
        return sum(r.rows_written for r in self.per_event_type)

    @property
    def rows_seen(self) -> int:
        return sum(r.rows_seen for r in self.per_event_type)


# ── HTTP fetch (injectable for tests) ────────────────────────────────────────

HttpGetter = Callable[[str, dict[str, Any], dict[str, str], float], Awaitable[dict[str, Any]]]


async def _default_http_get(
    url: str, params: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


def _event_to_row(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("payload")
    return {
        "id": item["id"],
        "workspace_id": item.get("workspace_id"),
        "tree_id": item.get("tree_id"),
        "node_id": item.get("node_id"),
        "event_type": item.get("event_type"),
        "actor_type": item.get("actor_type"),
        "actor_id": item.get("actor_id"),
        "occurred_at": item.get("occurred_at"),
        "payload_json": json.dumps(payload) if payload is not None else None,
    }


class IntentTreeEventsIngestService:
    """Sweeps ``EVENT_TYPES`` from IntentTree's event log into ``intent_tree_events``.

    Parameters
    ----------
    repo:
        A ``SqliteIntentTreeEventsRepository`` / ``PostgresIntentTreeEventsRepository``
        (or duck-typed equivalent) exposing ``async insert_if_not_exists(row) -> bool``.
    cursor_repo:
        Optional ``SqliteIngestCursorRepository`` / ``PostgresIngestCursorRepository``.
        Cursor bookkeeping is always best-effort and never blocks persistence.
    api_url, api_token, workspace_id:
        Required IntentTree connection details. ``workspace_id`` is required by
        the IntentTree API itself (422 without it).
    tree_id:
        Optional filter, forwarded verbatim when set.
    page_size:
        Clamped to <= 200 (the measured server cap) regardless of the caller's
        request, so a misconfigured larger value can never look like a single
        uncapped call returned everything.
    http_get:
        Injectable HTTP GET callable for tests; defaults to a real
        ``httpx.AsyncClient`` call.
    """

    MAX_PAGE_SIZE: int = 200
    MAX_PAGES_PER_SWEEP: int = 500

    def __init__(
        self,
        repo: Any,
        cursor_repo: Any | None,
        *,
        api_url: str,
        api_token: str,
        workspace_id: str,
        tree_id: str | None = None,
        page_size: int = 200,
        timeout_seconds: float = 10.0,
        http_get: HttpGetter | None = None,
    ) -> None:
        self._repo = repo
        self._cursor_repo = cursor_repo
        self._api_url = api_url.rstrip("/")
        self._api_token = api_token
        self._workspace_id = workspace_id
        self._tree_id = tree_id
        self._page_size = min(int(page_size), self.MAX_PAGE_SIZE)
        self._timeout_seconds = timeout_seconds
        self._http_get = http_get or _default_http_get

    async def ingest_all(self) -> IntentTreeIngestResult:
        """Sweep every configured event type. Never raises."""
        results = [await self._ingest_event_type(event_type) for event_type in EVENT_TYPES]
        return IntentTreeIngestResult(per_event_type=results)

    async def _ingest_event_type(self, event_type: str) -> EventTypeIngestResult:
        source_id = source_id_for(event_type)
        await self._cursor_get_or_create(source_id)

        rows_seen = 0
        rows_written = 0
        pages_fetched = 0
        newest_id_seen: str | None = None
        cursor: str | None = None
        seen_cursors: set[str] = set()

        while True:
            params: dict[str, Any] = {
                "workspace_id": self._workspace_id,
                "event_type": event_type,
                "limit": self._page_size,
            }
            if self._tree_id:
                params["tree_id"] = self._tree_id
            if cursor:
                params["cursor"] = cursor

            try:
                page = await self._http_get(
                    f"{self._api_url}/api/v1/events",
                    params,
                    {"Authorization": f"Bearer {self._api_token}"},
                    self._timeout_seconds,
                )
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                # fail-soft: the remote is unreachable or returned a non-2xx
                # status. Anything else (AttributeError, TypeError, KeyError,
                # ...) is a bug in our own code, not a remote-availability
                # problem, and must propagate to the runtime failure handler
                # rather than be reported as a silent success.
                logger.warning(
                    "intenttree events ingest: fetch failed for event_type=%s "
                    "after %d page(s) (rows_written=%d so far, not rolled back): %s",
                    event_type,
                    pages_fetched,
                    rows_written,
                    exc,
                )
                await self._cursor_record_error(source_id, str(exc))
                return EventTypeIngestResult(
                    event_type=event_type,
                    ok=False,
                    rows_seen=rows_seen,
                    rows_written=rows_written,
                    pages_fetched=pages_fetched,
                    error=str(exc),
                )

            pages_fetched += 1
            items = page.get("items") or []
            if newest_id_seen is None and items:
                newest_id_seen = items[0].get("id")

            for item in items:
                rows_seen += 1
                row = _event_to_row(item)
                was_new = await retry_on_locked(
                    lambda r=row: self._repo.insert_if_not_exists(r),
                    repo="intent_tree_events",
                )
                if was_new:
                    rows_written += 1

            cursor = page.get("next_cursor")
            if not cursor:
                break

            if cursor in seen_cursors:
                error_msg = (
                    f"intenttree events ingest: stable/cyclic next_cursor "
                    f"{cursor!r} detected for event_type={event_type} after "
                    f"{pages_fetched} page(s) -- aborting sweep to avoid "
                    f"looping forever"
                )
                logger.warning(error_msg)
                await self._cursor_record_error(source_id, error_msg)
                return EventTypeIngestResult(
                    event_type=event_type,
                    ok=False,
                    rows_seen=rows_seen,
                    rows_written=rows_written,
                    pages_fetched=pages_fetched,
                    error=error_msg,
                )
            seen_cursors.add(cursor)

            if pages_fetched >= self.MAX_PAGES_PER_SWEEP:
                error_msg = (
                    f"intenttree events ingest: exceeded MAX_PAGES_PER_SWEEP "
                    f"({self.MAX_PAGES_PER_SWEEP}) for event_type={event_type} "
                    f"without pagination terminating -- aborting sweep"
                )
                logger.warning(error_msg)
                await self._cursor_record_error(source_id, error_msg)
                return EventTypeIngestResult(
                    event_type=event_type,
                    ok=False,
                    rows_seen=rows_seen,
                    rows_written=rows_written,
                    pages_fetched=pages_fetched,
                    error=error_msg,
                )

        if newest_id_seen is not None:
            await self._cursor_advance(source_id, cursor_value=newest_id_seen)

        return EventTypeIngestResult(
            event_type=event_type,
            ok=True,
            rows_seen=rows_seen,
            rows_written=rows_written,
            pages_fetched=pages_fetched,
        )

    # ── Cursor bookkeeping helpers ───────────────────────────────────────────
    #
    # Each helper is a no-op when no cursor_repo was injected, and swallows any
    # exception after logging -- watermark bookkeeping is secondary telemetry
    # and must never fail the primary ingest path (mirrors
    # backend/application/services/ingest/rf_events_ingest.py exactly).

    async def _cursor_get_or_create(self, source_id: str) -> None:
        if self._cursor_repo is None:
            return
        try:
            await retry_on_locked(
                lambda: self._cursor_repo.get_or_create(
                    source_id=source_id,
                    project_id=SENTINEL_PROJECT_ID,
                    workspace_id=self._workspace_id,
                ),
                repo="ingest_cursors",
            )
        except Exception as exc:
            logger.warning(
                "intenttree events ingest: cursor get_or_create failed for source_id=%s: %s",
                source_id,
                exc,
            )

    async def _cursor_advance(self, source_id: str, *, cursor_value: str) -> None:
        if self._cursor_repo is None:
            return
        try:
            await retry_on_locked(
                lambda: self._cursor_repo.advance(
                    source_id=source_id,
                    project_id=SENTINEL_PROJECT_ID,
                    workspace_id=self._workspace_id,
                    cursor_value=cursor_value,
                    # ``last_ingest_at`` is a timestamp column -- it records
                    # when this sweep last succeeded, not an opaque event id.
                    # The cursor value (an event id, not a time) belongs only
                    # in ``cursor_value``/``last_cursor``.
                    occurred_at=datetime.now(timezone.utc).isoformat(),
                ),
                repo="ingest_cursors",
            )
        except Exception as exc:
            logger.warning(
                "intenttree events ingest: cursor advance failed for source_id=%s: %s",
                source_id,
                exc,
            )

    async def _cursor_record_error(self, source_id: str, error_message: str) -> None:
        if self._cursor_repo is None:
            return
        try:
            await retry_on_locked(
                lambda: self._cursor_repo.record_error(
                    source_id=source_id,
                    project_id=SENTINEL_PROJECT_ID,
                    workspace_id=self._workspace_id,
                    error_message=error_message,
                ),
                repo="ingest_cursors",
            )
        except Exception as exc:
            logger.warning(
                "intenttree events ingest: cursor record_error failed for source_id=%s: %s",
                source_id,
                exc,
            )


__all__ = [
    "IntentTreeEventsIngestService",
    "IntentTreeIngestResult",
    "EventTypeIngestResult",
    "EVENT_TYPES",
    "SENTINEL_PROJECT_ID",
    "source_id_for",
]
