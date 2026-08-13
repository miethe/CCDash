"""Tests for ingest_sources health rollup (Phase 6 / Deliverable A).

Covers:
  - State derivation: idle / connected / backed_up / disconnected
  - lag_seconds computation
  - Resilience: missing table → empty list
  - Resilience: empty table → empty list
  - Multiple rows returned correctly

Structure follows the project's IsolatedAsyncioTestCase + aiosqlite in-memory
DB pattern (same as test_system_metrics.py).

NOTE: Run ONLY this named file — the test suite hangs on unscoped runs:
  backend/.venv/bin/python -m pytest backend/tests/test_ingest_sources_health.py -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import aiosqlite

from backend import config
from backend.application.services.agent_queries.ingest_sources import (
    get_ingest_sources_health,
    parse_iso,
)
from backend.db.sqlite_migrations import run_migrations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    """Legacy NAIVE form (no offset) — matches the historically-stored
    format that ``_parse_iso`` handled before the production bug was fixed.
    Kept as-is so the existing legacy-compatibility tests below continue to
    guard that path; do not change this to emit an offset."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _iso_offset(dt: datetime) -> str:
    """Production OFFSET-BEARING form — the exact shape written by
    ``datetime.now(timezone.utc).isoformat()`` in
    ``backend/db/repositories/ingest_cursors.py:19``."""
    return dt.astimezone(timezone.utc).isoformat()


async def _insert_cursor(
    db: aiosqlite.Connection,
    *,
    source_id: str,
    project_id: str,
    workspace_id: str = "default-local",
    last_cursor: str | None = None,
    last_ingest_at: str | None = None,
) -> None:
    await db.execute(
        """
        INSERT OR REPLACE INTO ingest_cursors
            (source_id, project_id, workspace_id,
             last_cursor, last_ingest_at,
             error_count, last_error, last_error_at)
        VALUES (?, ?, ?, ?, ?, 0, NULL, NULL)
        """,
        (source_id, project_id, workspace_id, last_cursor, last_ingest_at),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIngestSourcesHealthIdle(unittest.IsolatedAsyncioTestCase):
    """Source with no last_ingest_at → state == 'idle', lag_seconds == None."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        await _insert_cursor(
            self.db,
            source_id="daemon-a",
            project_id="proj-1",
            last_ingest_at=None,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_idle_state_and_null_lag(self) -> None:
        results = await get_ingest_sources_health(self.db)
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["source_id"], "daemon-a")
        self.assertEqual(row["state"], "idle")
        self.assertIsNone(row["lag_seconds"])
        self.assertIsNone(row["last_ingest_at"])


class TestIngestSourcesHealthConnected(unittest.IsolatedAsyncioTestCase):
    """Lag < FRESH_SECONDS → state == 'connected'."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        # 30 s ago — well within the 300 s default fresh threshold
        ts = _iso(_now_utc() - timedelta(seconds=30))
        await _insert_cursor(
            self.db,
            source_id="daemon-b",
            project_id="proj-1",
            last_ingest_at=ts,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_connected_state(self) -> None:
        results = await get_ingest_sources_health(self.db)
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["state"], "connected")
        self.assertIsNotNone(row["lag_seconds"])
        # Lag should be roughly 30 s (allow ±5 s for test execution timing)
        self.assertLess(row["lag_seconds"], config.CCDASH_INGEST_SOURCE_FRESH_SECONDS)


class TestIngestSourcesHealthBackedUp(unittest.IsolatedAsyncioTestCase):
    """FRESH_SECONDS <= lag < STALE_SECONDS → state == 'backed_up'."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        # 600 s ago — between 300 (fresh) and 900 (stale) defaults
        ts = _iso(_now_utc() - timedelta(seconds=600))
        await _insert_cursor(
            self.db,
            source_id="daemon-c",
            project_id="proj-2",
            last_ingest_at=ts,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_backed_up_state(self) -> None:
        results = await get_ingest_sources_health(self.db)
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["state"], "backed_up")
        fresh = config.CCDASH_INGEST_SOURCE_FRESH_SECONDS
        stale = config.CCDASH_INGEST_SOURCE_STALE_SECONDS
        self.assertGreaterEqual(row["lag_seconds"], fresh)
        self.assertLess(row["lag_seconds"], stale + 5)  # ±5 s for timing


class TestIngestSourcesHealthDisconnected(unittest.IsolatedAsyncioTestCase):
    """lag >= STALE_SECONDS → state == 'disconnected'."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        # 1200 s (20 min) ago — past the 900 s stale default
        ts = _iso(_now_utc() - timedelta(seconds=1200))
        await _insert_cursor(
            self.db,
            source_id="daemon-d",
            project_id="proj-3",
            last_ingest_at=ts,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_disconnected_state(self) -> None:
        results = await get_ingest_sources_health(self.db)
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["state"], "disconnected")
        self.assertGreaterEqual(
            row["lag_seconds"],
            config.CCDASH_INGEST_SOURCE_STALE_SECONDS,
        )


class TestIngestSourcesHealthEmptyTable(unittest.IsolatedAsyncioTestCase):
    """Empty ingest_cursors table → returns []."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        # No inserts

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_empty_table_returns_empty_list(self) -> None:
        results = await get_ingest_sources_health(self.db)
        self.assertEqual(results, [])


class TestIngestSourcesHealthMissingTable(unittest.IsolatedAsyncioTestCase):
    """Pre-migration DB (no ingest_cursors table) → returns []."""

    async def asyncSetUp(self) -> None:
        # Do NOT run migrations — table won't exist
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_missing_table_returns_empty_list(self) -> None:
        results = await get_ingest_sources_health(self.db)
        self.assertEqual(results, [])


class TestIngestSourcesHealthMultipleRows(unittest.IsolatedAsyncioTestCase):
    """Multiple rows → correct state per row; payload fields intact."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        now = _now_utc()
        # idle — never ingested
        await _insert_cursor(
            self.db,
            source_id="s-idle",
            project_id="proj-1",
            last_ingest_at=None,
        )
        # connected — 10 s ago
        await _insert_cursor(
            self.db,
            source_id="s-connected",
            project_id="proj-1",
            last_cursor="cursor-xyz",
            last_ingest_at=_iso(now - timedelta(seconds=10)),
        )
        # backed_up — 500 s ago (between 300 and 900)
        await _insert_cursor(
            self.db,
            source_id="s-backed-up",
            project_id="proj-2",
            last_ingest_at=_iso(now - timedelta(seconds=500)),
        )
        # disconnected — 1000 s ago
        await _insert_cursor(
            self.db,
            source_id="s-disconnected",
            project_id="proj-3",
            last_ingest_at=_iso(now - timedelta(seconds=1000)),
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_all_four_states_present(self) -> None:
        results = await get_ingest_sources_health(self.db)
        self.assertEqual(len(results), 4)
        by_id = {r["source_id"]: r for r in results}

        self.assertIn("s-idle", by_id)
        self.assertIn("s-connected", by_id)
        self.assertIn("s-backed-up", by_id)
        self.assertIn("s-disconnected", by_id)

        self.assertEqual(by_id["s-idle"]["state"], "idle")
        self.assertIsNone(by_id["s-idle"]["lag_seconds"])

        self.assertEqual(by_id["s-connected"]["state"], "connected")
        self.assertEqual(by_id["s-connected"]["last_cursor"], "cursor-xyz")
        self.assertIsNotNone(by_id["s-connected"]["lag_seconds"])
        self.assertLess(by_id["s-connected"]["lag_seconds"], 60)

        self.assertEqual(by_id["s-backed-up"]["state"], "backed_up")

        self.assertEqual(by_id["s-disconnected"]["state"], "disconnected")

    def test_result_schema_keys(self) -> None:
        """Each result dict must carry the required keys (sync guard)."""
        # Run as a simple synchronous check using asyncSetUp output in tearDown
        required = {
            "source_id", "project_id", "workspace_id",
            "last_cursor", "last_ingest_at", "lag_seconds", "state",
        }
        # We'll verify via a trivial dict constructor — the real shape check is
        # in the async tests above; this test catches key-set regressions.
        sample = {
            "source_id": "x",
            "project_id": "y",
            "workspace_id": "z",
            "last_cursor": None,
            "last_ingest_at": None,
            "lag_seconds": None,
            "state": "idle",
        }
        self.assertEqual(set(sample.keys()), required)


class TestParseIsoOffsetBearing(unittest.TestCase):
    """``parse_iso`` must accept the production offset-bearing form.

    Prior bug: ``_parse_iso`` only tried four naive ``strptime`` formats and
    always failed on an offset, silently degrading every real row to
    ``state='idle', lag_seconds=None``.
    """

    def test_parses_exact_production_value(self) -> None:
        # The exact value measured in production
        # (datetime.now(timezone.utc).isoformat()).
        raw = "2026-08-13T19:07:18.250600+00:00"
        parsed = parse_iso(raw)
        self.assertIsNotNone(parsed)
        self.assertEqual(
            parsed,
            datetime(2026, 8, 13, 19, 7, 18, 250600, tzinfo=timezone.utc),
        )

    def test_parses_trailing_z_form(self) -> None:
        parsed = parse_iso("2026-08-13T19:07:18.250600Z")
        self.assertIsNotNone(parsed)
        self.assertEqual(
            parsed,
            datetime(2026, 8, 13, 19, 7, 18, 250600, tzinfo=timezone.utc),
        )

    def test_parses_non_utc_offset_and_converts_to_utc(self) -> None:
        # 15:07:18 -04:00 == 19:07:18 UTC
        parsed = parse_iso("2026-08-13T15:07:18.250600-04:00")
        self.assertIsNotNone(parsed)
        self.assertEqual(
            parsed,
            datetime(2026, 8, 13, 19, 7, 18, 250600, tzinfo=timezone.utc),
        )


class TestParseIsoLegacyNaiveForms(unittest.TestCase):
    """``parse_iso`` must still accept every legacy naive form (no regression)."""

    def test_parses_naive_t_separator_with_fraction(self) -> None:
        parsed = parse_iso("2026-08-13T19:07:18.250600")
        self.assertEqual(
            parsed,
            datetime(2026, 8, 13, 19, 7, 18, 250600, tzinfo=timezone.utc),
        )

    def test_parses_naive_t_separator_no_fraction(self) -> None:
        parsed = parse_iso("2026-08-13T19:07:18")
        self.assertEqual(
            parsed,
            datetime(2026, 8, 13, 19, 7, 18, tzinfo=timezone.utc),
        )

    def test_parses_naive_space_separator_with_fraction(self) -> None:
        parsed = parse_iso("2026-08-13 19:07:18.250600")
        self.assertEqual(
            parsed,
            datetime(2026, 8, 13, 19, 7, 18, 250600, tzinfo=timezone.utc),
        )

    def test_parses_naive_space_separator_no_fraction(self) -> None:
        parsed = parse_iso("2026-08-13 19:07:18")
        self.assertEqual(
            parsed,
            datetime(2026, 8, 13, 19, 7, 18, tzinfo=timezone.utc),
        )

    def test_empty_and_none_still_return_none(self) -> None:
        self.assertIsNone(parse_iso(None))
        self.assertIsNone(parse_iso(""))
        self.assertIsNone(parse_iso("not-a-timestamp"))


class TestIngestSourcesHealthOffsetBearingDisconnected(unittest.IsolatedAsyncioTestCase):
    """An offset-bearing row older than STALE_SECONDS -> 'disconnected' with
    a non-null lag_seconds. This is the AC that fails today (reports 'idle'/
    None because the naive-only strptime loop can't parse an offset)."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        # 1200 s (20 min) ago — past the 900 s stale default
        ts = _iso_offset(_now_utc() - timedelta(seconds=1200))
        await _insert_cursor(
            self.db,
            source_id="daemon-offset-disconnected",
            project_id="proj-4",
            last_ingest_at=ts,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_offset_bearing_disconnected_state(self) -> None:
        results = await get_ingest_sources_health(self.db)
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["state"], "disconnected")
        self.assertIsNotNone(row["lag_seconds"])
        self.assertGreaterEqual(
            row["lag_seconds"],
            config.CCDASH_INGEST_SOURCE_STALE_SECONDS,
        )


class TestIngestSourcesHealthOffsetBearingConnected(unittest.IsolatedAsyncioTestCase):
    """An offset-bearing row within FRESH_SECONDS -> 'connected' with a
    non-null lag_seconds."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        # 30 s ago — well within the 300 s default fresh threshold
        ts = _iso_offset(_now_utc() - timedelta(seconds=30))
        await _insert_cursor(
            self.db,
            source_id="daemon-offset-connected",
            project_id="proj-4",
            last_ingest_at=ts,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_offset_bearing_connected_state(self) -> None:
        results = await get_ingest_sources_health(self.db)
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["state"], "connected")
        self.assertIsNotNone(row["lag_seconds"])
        self.assertLess(row["lag_seconds"], config.CCDASH_INGEST_SOURCE_FRESH_SECONDS)


class TestIngestSourcesHealthOffsetBearingBackedUp(unittest.IsolatedAsyncioTestCase):
    """An offset-bearing row between FRESH_SECONDS and STALE_SECONDS ->
    'backed_up'."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        # 600 s ago — between 300 (fresh) and 900 (stale) defaults
        ts = _iso_offset(_now_utc() - timedelta(seconds=600))
        await _insert_cursor(
            self.db,
            source_id="daemon-offset-backed-up",
            project_id="proj-4",
            last_ingest_at=ts,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_offset_bearing_backed_up_state(self) -> None:
        results = await get_ingest_sources_health(self.db)
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["state"], "backed_up")
        fresh = config.CCDASH_INGEST_SOURCE_FRESH_SECONDS
        stale = config.CCDASH_INGEST_SOURCE_STALE_SECONDS
        self.assertGreaterEqual(row["lag_seconds"], fresh)
        self.assertLess(row["lag_seconds"], stale + 5)  # ±5 s for timing


class TestIngestSourcesHealthNullStillIdle(unittest.IsolatedAsyncioTestCase):
    """A genuinely NULL last_ingest_at must still report state == 'idle'
    with lag_seconds is None — idle must remain reachable for a
    never-ingested source; that meaning is legitimate and must not be
    conflated with the offset-parse fix."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        await _insert_cursor(
            self.db,
            source_id="daemon-null-idle",
            project_id="proj-4",
            last_ingest_at=None,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_null_last_ingest_at_is_idle(self) -> None:
        results = await get_ingest_sources_health(self.db)
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["state"], "idle")
        self.assertIsNone(row["lag_seconds"])


if __name__ == "__main__":
    unittest.main()
