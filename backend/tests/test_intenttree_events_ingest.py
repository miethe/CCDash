"""Ingest tests for IntentTree lifecycle events (are-we-winning-dashboard-v1 M1).

CCDash held zero IntentTree lifecycle-event data before this milestone.
Exercises the service layer (``IntentTreeEventsIngestService``) end-to-end
against a real in-memory SQLite DB migrated via ``run_migrations``, with an
injected fake HTTP getter standing in for the live IntentTree API. Covers the
milestone's three explicit AC:

  1. Pagination beyond the server's 200-row/page cap — a faked API returning
     rows across multiple ``next_cursor`` pages results in ALL rows
     persisted. Would fail if the ``while`` loop in
     ``IntentTreeEventsIngestService._ingest_event_type`` were replaced with
     a single call.
  2. Fail-soft — a simulated-unreachable IntentTree (connection error and a
     non-2xx status) leaves cache state byte-identical to before the run and
     raises nothing out of ``ingest_all()``.
  3. Idempotency — re-ingesting the same page twice yields the same direct
     row count (ADR-007 §4 persistence-assertion convention, mirrors
     ``test_rf_events_ingest_idempotency.py``).

Also pins the migration-governance exit gate (AC4) at the unit level,
mirroring ``test_rf_events_migration_governance.py``'s established shape;
``test_migration_governance.py`` is the authoritative broad-sweep check.

Run as a named module (full collection can hang in this repo):
    python3 -m pytest backend/tests/test_intenttree_events_ingest.py -v
"""
from __future__ import annotations

import unittest
from typing import Any

import aiosqlite
import httpx

from backend.application.services.ingest.intenttree_events_ingest import (
    EVENT_TYPES,
    IntentTreeEventsIngestService,
    source_id_for,
)
from backend.db.migration_governance import (
    COLUMN_PARITY_DRIFT_ALLOWLIST,
    column_parity_diff,
    get_postgres_migration_tables,
    get_sqlite_migration_tables,
)
from backend.db.repositories.ingest_cursors import SqliteIngestCursorRepository
from backend.db.repositories.intent_tree_events import SqliteIntentTreeEventsRepository
from backend.db.sqlite_migrations import run_migrations


def _make_item(event_id: str, event_type: str, *, node_id: str = "node-1", payload: dict | None = None) -> dict:
    return {
        "id": event_id,
        "workspace_id": "ws-test",
        "tree_id": "tree-test",
        "node_id": node_id,
        "event_type": event_type,
        "actor_type": "system",
        "actor_id": None,
        "occurred_at": "2026-08-14T00:00:00.000000Z",
        "payload": payload,
    }


def _paged_http_get(pages_by_event_type: dict[str, list[list[dict]]]):
    """Fake HTTP GET keyed on ``event_type``; ``cursor`` is the page index (as a string).

    Returns ``(http_get, calls)`` -- ``calls`` records every params dict
    passed, for pagination-loop assertions.
    """
    calls: list[dict[str, Any]] = []

    async def _http_get(url: str, params: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        calls.append(dict(params))
        event_type = params["event_type"]
        pages = pages_by_event_type.get(event_type, [])
        cursor = params.get("cursor")
        idx = 0 if cursor is None else int(cursor)
        if idx >= len(pages):
            return {"items": [], "next_cursor": None, "total": sum(len(p) for p in pages)}
        page = pages[idx]
        next_cursor = str(idx + 1) if idx + 1 < len(pages) else None
        return {"items": page, "next_cursor": next_cursor, "total": sum(len(p) for p in pages)}

    return _http_get, calls


def _raising_http_get(exc: Exception):
    async def _http_get(url: str, params: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        raise exc

    return _http_get


class _AsyncSqliteHarness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteIntentTreeEventsRepository(self.db)
        self.cursor_repo = SqliteIngestCursorRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _count(self) -> int:
        cursor = await self.db.execute("SELECT COUNT(*) FROM intent_tree_events")
        (count,) = await cursor.fetchone()
        return int(count)

    def _service(self, http_get, **kwargs) -> IntentTreeEventsIngestService:
        return IntentTreeEventsIngestService(
            self.repo,
            self.cursor_repo,
            api_url="http://intenttree.example.invalid",
            api_token="test-token",
            workspace_id="ws-test",
            http_get=http_get,
            **kwargs,
        )


# ── AC1: pagination beyond the 200-row cap ──────────────────────────────────


class PaginationBeyondCapTests(_AsyncSqliteHarness):
    async def test_multi_page_sweep_persists_every_row_not_just_the_first_page(self) -> None:
        created_pages = [
            [_make_item(f"evt-created-{i}", "node.created") for i in range(5)],
            [_make_item(f"evt-created-{i}", "node.created") for i in range(5, 10)],
            [_make_item(f"evt-created-{i}", "node.created") for i in range(10, 15)],
        ]
        completed_pages = [
            [_make_item(f"evt-completed-{i}", "node.completed") for i in range(2)],
        ]
        http_get, calls = _paged_http_get(
            {"node.created": created_pages, "node.completed": completed_pages}
        )
        service = self._service(http_get)

        result = await service.ingest_all()

        self.assertTrue(result.ok)
        self.assertEqual(result.rows_written, 17)  # 15 + 2 -- proves every page landed
        self.assertEqual(await self._count(), 17)

        created_result = next(r for r in result.per_event_type if r.event_type == "node.created")
        # A single-call implementation would have fetched exactly 1 page.
        self.assertEqual(created_result.pages_fetched, 3)
        self.assertEqual(created_result.rows_written, 15)

        # The pagination loop must have actually chained cursor -> cursor.
        created_calls = [c for c in calls if c["event_type"] == "node.created"]
        self.assertEqual([c.get("cursor") for c in created_calls], [None, "1", "2"])


# ── Pagination loop guard: stable/cyclic next_cursor must terminate,
#    non-success, rather than loop forever ──────────────────────────────────


class PaginationLoopGuardTests(_AsyncSqliteHarness):
    async def test_stable_cursor_forever_terminates_with_non_success_result(self) -> None:
        """A server that returns the SAME next_cursor on every page (never
        advancing) must not be trusted to eventually stop -- the guard must
        detect the repeat and abort. The fake itself is bounded (raises past
        a small call cap) so a regressed guard fails fast instead of hanging
        the suite."""
        calls = {"n": 0}

        async def _http_get(url, params, headers, timeout):
            if params["event_type"] != "node.created":
                return {"items": [], "next_cursor": None, "total": 0}
            calls["n"] += 1
            if calls["n"] > 10:
                raise AssertionError(
                    "pagination loop guard regressed: stable cursor was not detected"
                )
            return {
                "items": [_make_item(f"evt-stable-{calls['n']}", "node.created")],
                "next_cursor": "same-cursor-forever",
                "total": 999,
            }

        service = self._service(_http_get)

        result = await service.ingest_all()  # must not raise, must not hang

        created_result = next(r for r in result.per_event_type if r.event_type == "node.created")
        self.assertFalse(result.ok)
        self.assertFalse(created_result.ok)
        self.assertIsNotNone(created_result.error)
        self.assertLess(calls["n"], 10, "guard must abort well before the fake's hard cap")

    async def test_empty_items_page_with_non_null_cursor_terminates_with_non_success_result(
        self,
    ) -> None:
        """An empty ``items`` page that still carries a non-null next_cursor
        has the same forever-loop hazard as a stable cursor -- no new rows
        ever arrive, but pagination never naturally ends."""
        calls = {"n": 0}

        async def _http_get(url, params, headers, timeout):
            if params["event_type"] != "node.created":
                return {"items": [], "next_cursor": None, "total": 0}
            calls["n"] += 1
            if calls["n"] > 10:
                raise AssertionError(
                    "pagination loop guard regressed: empty-page-with-cursor was not detected"
                )
            return {"items": [], "next_cursor": "always-more-apparently", "total": 0}

        service = self._service(_http_get)

        result = await service.ingest_all()  # must not raise, must not hang

        created_result = next(r for r in result.per_event_type if r.event_type == "node.created")
        self.assertFalse(result.ok)
        self.assertFalse(created_result.ok)
        self.assertEqual(created_result.rows_written, 0)
        self.assertIsNotNone(created_result.error)
        self.assertLess(calls["n"], 10, "guard must abort well before the fake's hard cap")


# ── AC2: fail-soft on unreachable IntentTree ────────────────────────────────


class FailSoftTests(_AsyncSqliteHarness):
    async def _seed_cursor(self, event_type: str, *, cursor_value: str, occurred_at: str) -> None:
        """Pre-populate a real watermark so failure tests can prove it is
        left byte-identical, not merely that nothing new was added."""
        source_id = source_id_for(event_type)
        await self.cursor_repo.get_or_create(
            source_id=source_id, project_id="global", workspace_id="ws-test"
        )
        await self.cursor_repo.advance(
            source_id=source_id,
            project_id="global",
            workspace_id="ws-test",
            cursor_value=cursor_value,
            occurred_at=occurred_at,
        )

    async def _cursor_snapshot(self, event_type: str):
        return await self.cursor_repo.get_or_create(
            source_id=source_id_for(event_type), project_id="global", workspace_id="ws-test"
        )

    async def test_connection_error_leaves_cache_untouched_and_does_not_raise(self) -> None:
        for event_type in EVENT_TYPES:
            await self._seed_cursor(
                event_type, cursor_value="evt-preexisting", occurred_at="2020-01-01T00:00:00+00:00"
            )
        before = {et: await self._cursor_snapshot(et) for et in EVENT_TYPES}

        service = self._service(_raising_http_get(httpx.ConnectError("connection refused")))

        result = await service.ingest_all()  # must not raise

        self.assertFalse(result.ok)
        self.assertEqual(result.rows_written, 0)
        self.assertEqual(await self._count(), 0)
        for per_type in result.per_event_type:
            self.assertFalse(per_type.ok)
            self.assertIsNotNone(per_type.error)
        for event_type in EVENT_TYPES:
            after = await self._cursor_snapshot(event_type)
            self.assertEqual(after.last_cursor, before[event_type].last_cursor)
            self.assertEqual(after.last_ingest_at, before[event_type].last_ingest_at)

    async def test_non_2xx_status_leaves_cache_untouched_and_does_not_raise(self) -> None:
        for event_type in EVENT_TYPES:
            await self._seed_cursor(
                event_type, cursor_value="evt-preexisting", occurred_at="2020-01-01T00:00:00+00:00"
            )
        before = {et: await self._cursor_snapshot(et) for et in EVENT_TYPES}

        request = httpx.Request("GET", "http://intenttree.example.invalid/api/v1/events")
        response = httpx.Response(500, request=request)
        exc = httpx.HTTPStatusError("server error", request=request, response=response)
        service = self._service(_raising_http_get(exc))

        result = await service.ingest_all()  # must not raise

        self.assertFalse(result.ok)
        self.assertEqual(result.rows_written, 0)
        self.assertEqual(await self._count(), 0)
        for event_type in EVENT_TYPES:
            after = await self._cursor_snapshot(event_type)
            self.assertEqual(after.last_cursor, before[event_type].last_cursor)
            self.assertEqual(after.last_ingest_at, before[event_type].last_ingest_at)

    async def test_unexpected_exception_type_propagates_instead_of_being_swallowed(self) -> None:
        """Fail-soft must mean 'the remote is unavailable', never 'our code
        is wrong' -- a programming-error exception type must not be caught
        by the transport-error handler."""
        service = self._service(_raising_http_get(AttributeError("boom: no such attribute")))

        with self.assertRaises(AttributeError):
            await service.ingest_all()

    async def test_failure_after_a_successful_page_still_does_not_raise(self) -> None:
        """A later-page failure is fail-soft too -- it just doesn't roll back
        the idempotent rows already committed from earlier successful pages
        in the same run (only *total* unreachability guarantees byte-identical
        cache state -- see the module docstring's fail-soft AC wording)."""
        calls = {"n": 0}

        async def _http_get(url, params, headers, timeout):
            if params["event_type"] != "node.created":
                return {"items": [], "next_cursor": None, "total": 0}
            calls["n"] += 1
            if calls["n"] == 1:
                return {
                    "items": [_make_item("evt-a", "node.created")],
                    "next_cursor": "1",
                    "total": 2,
                }
            raise httpx.ConnectError("dropped mid-sweep")

        service = self._service(_http_get)

        result = await service.ingest_all()  # must not raise

        created_result = next(r for r in result.per_event_type if r.event_type == "node.created")
        self.assertFalse(created_result.ok)
        self.assertEqual(created_result.rows_written, 1)
        self.assertEqual(await self._count(), 1)


# ── AC3: idempotency ─────────────────────────────────────────────────────────


class IdempotencyTests(_AsyncSqliteHarness):
    async def test_reingesting_the_same_page_twice_yields_the_same_count(self) -> None:
        created_pages = [[_make_item(f"evt-{i}", "node.created") for i in range(4)]]
        http_get, _ = _paged_http_get({"node.created": created_pages, "node.completed": []})
        service = self._service(http_get)

        first = await service.ingest_all()
        first_count = await self._count()
        second = await service.ingest_all()
        second_count = await self._count()

        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertEqual(first_count, 4)
        self.assertEqual(second_count, 4, "re-ingesting an overlapping page must not duplicate rows")
        # The second sweep saw the same 4 rows again but wrote 0 new ones.
        self.assertEqual(second.rows_seen, 4)
        self.assertEqual(second.rows_written, 0)


# ── AC4 (unit-level pin; test_migration_governance.py is authoritative) ────


class IntentTreeEventsMigrationGovernanceTests(unittest.TestCase):
    def test_intent_tree_events_registered_in_sqlite_migration_tables(self) -> None:
        self.assertIn("intent_tree_events", get_sqlite_migration_tables())

    def test_intent_tree_events_registered_in_postgres_migration_tables(self) -> None:
        self.assertIn("intent_tree_events", get_postgres_migration_tables())

    def test_intent_tree_events_column_parity_diff_is_empty(self) -> None:
        diff = column_parity_diff("intent_tree_events")
        self.assertEqual(diff, {}, msg=f"intent_tree_events must be column-parity-clean; found: {diff}")

    def test_intent_tree_events_has_zero_allowlist_entries(self) -> None:
        entries = {pair for pair in COLUMN_PARITY_DRIFT_ALLOWLIST if pair[0] == "intent_tree_events"}
        self.assertEqual(entries, set())

    def test_event_types_match_plan_scope(self) -> None:
        self.assertEqual(set(EVENT_TYPES), {"node.created", "node.completed"})


if __name__ == "__main__":
    unittest.main()
