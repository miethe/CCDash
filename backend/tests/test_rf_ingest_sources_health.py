"""Tests for the ``rf`` ingest source in the health-detail rollup (T1-007).

AC-5: ``/api/health/detail`` -> ``ingest_sources[]`` includes an ``rf`` entry
whose state transitions ``idle`` -> ``connected`` -> ``backed_up`` ->
``disconnected`` per the existing freshness-threshold logic
(``backend/application/services/agent_queries/ingest_sources.py``),
unmodified.

Structure mirrors ``backend/tests/test_ingest_sources_health.py`` exactly,
pinned to ``source_id="rf"`` to prove the *existing* generic
``get_ingest_sources_health()`` rollup already covers the new source with
zero source-id-specific branching required — plus one integration test that
proves ``RfEventsIngestService`` actually registers the ``source_id='rf'``
``ingest_cursors`` row end-to-end via ``POST /api/v1/ingest/rf-events``.

NOTE: Run ONLY this named file — the test suite hangs on unscoped runs:
  backend/.venv/bin/python -m pytest backend/tests/test_rf_ingest_sources_health.py -v
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import aiosqlite
from fastapi.testclient import TestClient

from backend import config
from backend.adapters.auth.context import AuthContext
from backend.adapters.auth.dependency import get_auth_context
from backend.application.services.agent_queries.ingest_sources import (
    get_ingest_sources_health,
)
from backend.db.sqlite_migrations import run_migrations
from backend.runtime.bootstrap import build_runtime_app


# ---------------------------------------------------------------------------
# Helpers (mirrors test_ingest_sources_health.py)
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


async def _insert_rf_cursor(
    db: aiosqlite.Connection,
    *,
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
        VALUES ('rf', ?, ?, ?, ?, 0, NULL, NULL)
        """,
        (project_id, workspace_id, last_cursor, last_ingest_at),
    )
    await db.commit()


def _event_id() -> str:
    return str(uuid.uuid4())


def _make_event(event_id: str | None = None) -> dict:
    eid = event_id or _event_id()
    return {
        "event_id": eid,
        "timestamp": "2026-07-21T10:00:00.000000Z",
        "project": "research-foundry",
        "run_id": f"run-{eid[:8]}",
    }


# ---------------------------------------------------------------------------
# Unit-level: source_id='rf' through the four states
# (existing freshness-threshold logic, unmodified — AC-5)
# ---------------------------------------------------------------------------

class TestRfIngestSourceIdle(unittest.IsolatedAsyncioTestCase):
    """rf cursor row with no last_ingest_at -> state == 'idle'."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        await _insert_rf_cursor(self.db, project_id="proj-rf-1", last_ingest_at=None)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_idle_state(self) -> None:
        results = await get_ingest_sources_health(self.db)
        by_id = {r["source_id"]: r for r in results}
        self.assertIn("rf", by_id)
        self.assertEqual(by_id["rf"]["state"], "idle")
        self.assertIsNone(by_id["rf"]["lag_seconds"])


class TestRfIngestSourceConnected(unittest.IsolatedAsyncioTestCase):
    """lag < FRESH_SECONDS -> state == 'connected'."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        ts = _iso(_now_utc() - timedelta(seconds=30))
        await _insert_rf_cursor(self.db, project_id="proj-rf-2", last_ingest_at=ts)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_connected_state(self) -> None:
        results = await get_ingest_sources_health(self.db)
        by_id = {r["source_id"]: r for r in results}
        self.assertEqual(by_id["rf"]["state"], "connected")
        self.assertLess(by_id["rf"]["lag_seconds"], config.CCDASH_INGEST_SOURCE_FRESH_SECONDS)


class TestRfIngestSourceBackedUp(unittest.IsolatedAsyncioTestCase):
    """FRESH_SECONDS <= lag < STALE_SECONDS -> state == 'backed_up'."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        ts = _iso(_now_utc() - timedelta(seconds=600))
        await _insert_rf_cursor(self.db, project_id="proj-rf-3", last_ingest_at=ts)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_backed_up_state(self) -> None:
        results = await get_ingest_sources_health(self.db)
        by_id = {r["source_id"]: r for r in results}
        self.assertEqual(by_id["rf"]["state"], "backed_up")
        fresh = config.CCDASH_INGEST_SOURCE_FRESH_SECONDS
        stale = config.CCDASH_INGEST_SOURCE_STALE_SECONDS
        self.assertGreaterEqual(by_id["rf"]["lag_seconds"], fresh)
        self.assertLess(by_id["rf"]["lag_seconds"], stale + 5)


class TestRfIngestSourceDisconnected(unittest.IsolatedAsyncioTestCase):
    """lag >= STALE_SECONDS -> state == 'disconnected'."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        ts = _iso(_now_utc() - timedelta(seconds=1200))
        await _insert_rf_cursor(self.db, project_id="proj-rf-4", last_ingest_at=ts)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_disconnected_state(self) -> None:
        results = await get_ingest_sources_health(self.db)
        by_id = {r["source_id"]: r for r in results}
        self.assertEqual(by_id["rf"]["state"], "disconnected")
        self.assertGreaterEqual(
            by_id["rf"]["lag_seconds"],
            config.CCDASH_INGEST_SOURCE_STALE_SECONDS,
        )


class TestRfIngestSourceCoexistsWithOtherSources(unittest.IsolatedAsyncioTestCase):
    """An 'rf' row and a non-rf row both appear correctly (no cross-contamination)."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        await _insert_rf_cursor(
            self.db,
            project_id="proj-rf-5",
            last_ingest_at=_iso(_now_utc() - timedelta(seconds=10)),
        )
        await self.db.execute(
            """
            INSERT OR REPLACE INTO ingest_cursors
                (source_id, project_id, workspace_id,
                 last_cursor, last_ingest_at, error_count, last_error, last_error_at)
            VALUES ('remote_ingest', 'proj-rf-5', 'default-local', NULL, NULL, 0, NULL, NULL)
            """
        )
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_both_sources_present_independently(self) -> None:
        results = await get_ingest_sources_health(self.db)
        by_id = {r["source_id"]: r for r in results}
        self.assertEqual(len(results), 2)
        self.assertIn("rf", by_id)
        self.assertIn("remote_ingest", by_id)
        self.assertEqual(by_id["rf"]["state"], "connected")
        self.assertEqual(by_id["remote_ingest"]["state"], "idle")


# ---------------------------------------------------------------------------
# Integration: POST /api/v1/ingest/rf-events actually registers the
# source_id='rf' ingest_cursors row (T1-004 cursor bookkeeping).
# ---------------------------------------------------------------------------

class TestRfEventsIngestRegistersCursorSource(unittest.TestCase):
    """End-to-end: an accepted rf-events POST creates/advances the 'rf' cursor row."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()

        cls._env_patcher = patch.dict(
            os.environ,
            {
                "CCDASH_DB_PATH": cls._tmpdb.name,
                "CCDASH_DB_BACKEND": "sqlite",
            },
        )
        cls._env_patcher.start()

        cls._app = build_runtime_app("test")

        cls._patches = [
            patch("backend.runtime.container.initialize_observability"),
            patch("backend.runtime.container.shutdown_observability"),
            patch(
                "backend.adapters.jobs.runtime.file_watcher.start",
                new_callable=lambda: lambda: AsyncMock(),
            ),
            patch(
                "backend.adapters.jobs.runtime.file_watcher.stop",
                new_callable=lambda: lambda: AsyncMock(),
            ),
        ]
        for p in cls._patches:
            p.start()

        cls._app.dependency_overrides[get_auth_context] = lambda: AuthContext.synthesize_local(
            project_id="test-project"
        )

        cls._tc = TestClient(cls._app, raise_server_exceptions=False)
        cls._tc.__enter__()
        cls.client = cls._tc

    @classmethod
    def tearDownClass(cls) -> None:
        cls._app.dependency_overrides.clear()
        cls._tc.__exit__(None, None, None)
        for p in reversed(cls._patches):
            p.stop()
        cls._env_patcher.stop()
        try:
            os.unlink(cls._tmpdb.name)
        except OSError:
            pass

    def _fetch_cursor_row(self, *, source_id: str, project_id: str) -> sqlite3.Row | None:
        from backend.db.connection import _resolve_db_path

        conn = sqlite3.connect(str(_resolve_db_path()))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                "SELECT * FROM ingest_cursors WHERE source_id = ? AND project_id = ?",
                (source_id, project_id),
            )
            return cur.fetchone()
        finally:
            conn.close()

    def test_accepted_post_registers_rf_cursor_row(self) -> None:
        event = _make_event()
        resp = self.client.post(
            "/api/v1/ingest/rf-events",
            content=json.dumps(event).encode(),
            headers={
                "Content-Type": "application/json",
                "x-ccdash-project-id": "test-project",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["accepted"], 1)

        row = self._fetch_cursor_row(source_id="rf", project_id="test-project")
        self.assertIsNotNone(row, "expected an ingest_cursors row for source_id='rf'")
        self.assertEqual(row["workspace_id"], "default-local")
        self.assertEqual(row["last_cursor"], event["event_id"])
        self.assertIsNotNone(row["last_ingest_at"])


if __name__ == "__main__":
    unittest.main()
