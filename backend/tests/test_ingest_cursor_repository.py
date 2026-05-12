"""Unit tests for IngestCursorRepository — SQLite and (opt-in) Postgres impls.

SQLite tests use an in-memory DB seeded by run_migrations().
Postgres tests are skipped unless RUN_POSTGRES_TESTS=1 is set in the
environment (no asyncpg connection is available in the standard CI runner).
"""
from __future__ import annotations

import os
import unittest

import aiosqlite

from backend.application.ports.ingest import IngestCursor
from backend.db.repositories.ingest_cursors import (
    PostgresIngestCursorRepository,
    SqliteIngestCursorRepository,
)
from backend.db.sqlite_migrations import run_migrations


# ── SQLite ──────────────────────────────────────────────────────────────────


class SqliteIngestCursorRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteIngestCursorRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # ── get_or_create ──

    async def test_get_or_create_fresh_row_returns_null_cursor(self) -> None:
        cursor = await self.repo.get_or_create(
            source_id="filesystem",
            project_id="proj-1",
            workspace_id="default",
        )
        self.assertIsInstance(cursor, IngestCursor)
        self.assertIsNone(cursor.last_cursor)
        self.assertIsNone(cursor.last_ingest_at)
        self.assertEqual(cursor.error_count, 0)
        self.assertIsNone(cursor.last_error)
        self.assertIsNone(cursor.last_error_at)

    async def test_get_or_create_workspace_defaults_to_default(self) -> None:
        cursor = await self.repo.get_or_create(
            source_id="filesystem",
            project_id="proj-2",
        )
        self.assertEqual(cursor.workspace_id, "default")

    async def test_get_or_create_existing_row_no_overwrite(self) -> None:
        # Create and advance so last_cursor is non-NULL.
        await self.repo.get_or_create(
            source_id="remote_ingest",
            project_id="proj-3",
            workspace_id="default",
        )
        await self.repo.advance(
            source_id="remote_ingest",
            project_id="proj-3",
            workspace_id="default",
            cursor_value="cursor-abc",
            occurred_at="2026-05-12T10:00:00+00:00",
        )

        # Second get_or_create must NOT reset the cursor.
        cursor = await self.repo.get_or_create(
            source_id="remote_ingest",
            project_id="proj-3",
            workspace_id="default",
        )
        self.assertEqual(cursor.last_cursor, "cursor-abc")
        self.assertEqual(cursor.last_ingest_at, "2026-05-12T10:00:00+00:00")

    # ── advance ──

    async def test_advance_writes_cursor_and_clears_error_fields(self) -> None:
        await self.repo.get_or_create(
            source_id="filesystem",
            project_id="proj-4",
            workspace_id="default",
        )
        # Seed an error so we can confirm advance clears it.
        await self.repo.record_error(
            source_id="filesystem",
            project_id="proj-4",
            workspace_id="default",
            error_message="transient error",
        )

        await self.repo.advance(
            source_id="filesystem",
            project_id="proj-4",
            workspace_id="default",
            cursor_value="cursor-xyz",
            occurred_at="2026-05-12T11:00:00+00:00",
        )

        cursor = await self.repo.get_or_create(
            source_id="filesystem",
            project_id="proj-4",
            workspace_id="default",
        )
        self.assertEqual(cursor.last_cursor, "cursor-xyz")
        self.assertEqual(cursor.last_ingest_at, "2026-05-12T11:00:00+00:00")
        self.assertEqual(cursor.error_count, 0)
        self.assertIsNone(cursor.last_error)
        self.assertIsNone(cursor.last_error_at)

    # ── record_error ──

    async def test_record_error_increments_count_and_stamps_error_at(self) -> None:
        await self.repo.get_or_create(
            source_id="entire",
            project_id="proj-5",
            workspace_id="default",
        )

        await self.repo.record_error(
            source_id="entire",
            project_id="proj-5",
            workspace_id="default",
            error_message="connection refused",
        )
        cursor = await self.repo.get_or_create(
            source_id="entire",
            project_id="proj-5",
            workspace_id="default",
        )
        self.assertEqual(cursor.error_count, 1)
        self.assertEqual(cursor.last_error, "connection refused")
        self.assertIsNotNone(cursor.last_error_at)

        # Second error — count must reach 2.
        await self.repo.record_error(
            source_id="entire",
            project_id="proj-5",
            workspace_id="default",
            error_message="timeout",
        )
        cursor = await self.repo.get_or_create(
            source_id="entire",
            project_id="proj-5",
            workspace_id="default",
        )
        self.assertEqual(cursor.error_count, 2)
        self.assertEqual(cursor.last_error, "timeout")

    async def test_different_triplets_are_independent(self) -> None:
        for ws in ("ws-a", "ws-b"):
            await self.repo.get_or_create(
                source_id="remote_ingest",
                project_id="proj-6",
                workspace_id=ws,
            )
        await self.repo.advance(
            source_id="remote_ingest",
            project_id="proj-6",
            workspace_id="ws-a",
            cursor_value="cursor-a",
            occurred_at="2026-05-12T12:00:00+00:00",
        )

        cursor_b = await self.repo.get_or_create(
            source_id="remote_ingest",
            project_id="proj-6",
            workspace_id="ws-b",
        )
        # ws-b was not advanced — must still be NULL.
        self.assertIsNone(cursor_b.last_cursor)


# ── Postgres (fake-connection unit tests) ──────────────────────────────────


class _FakeRecord(dict):
    """asyncpg.Record stand-in: supports both dict and attribute access."""

    def __getattr__(self, item: str):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(item)


class _FakePostgresConnection:
    """Minimal asyncpg.Connection fake for unit testing."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str, str], dict] = {}
        self.execute_calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, query: str, *args) -> _FakeRecord | None:
        if len(args) == 3:
            key = (args[0], args[1], args[2])
            row = self._store.get(key)
            return _FakeRecord(row) if row else None
        return None

    async def execute(self, query: str, *args) -> None:
        self.execute_calls.append((query, args))
        q = query.strip().upper()
        if q.startswith("INSERT"):
            # INSERT ... ON CONFLICT DO NOTHING semantics
            if len(args) == 3:
                key = (args[0], args[1], args[2])
                if key not in self._store:
                    self._store[key] = {
                        "source_id": args[0],
                        "project_id": args[1],
                        "workspace_id": args[2],
                        "last_cursor": None,
                        "last_ingest_at": None,
                        "error_count": 0,
                        "last_error": None,
                        "last_error_at": None,
                    }
        elif q.startswith("UPDATE"):
            # advance has "last_cursor" in SET clause; record_error has "error_count + 1"
            if "LAST_CURSOR" in q:
                # advance: (cursor_value, occurred_at, source_id, project_id, workspace_id)
                key = (args[2], args[3], args[4])
                if key in self._store:
                    self._store[key].update(
                        last_cursor=args[0],
                        last_ingest_at=args[1],
                        error_count=0,
                        last_error=None,
                        last_error_at=None,
                    )
            else:
                # record_error: (error_message, now_iso, source_id, project_id, workspace_id)
                key = (args[2], args[3], args[4])
                if key in self._store:
                    self._store[key]["error_count"] += 1
                    self._store[key]["last_error"] = args[0]
                    self._store[key]["last_error_at"] = args[1]


class PostgresIngestCursorRepositoryTests(unittest.IsolatedAsyncioTestCase):
    """Uses a fake asyncpg connection — no real Postgres needed."""

    async def asyncSetUp(self) -> None:
        self.conn = _FakePostgresConnection()
        self.repo = PostgresIngestCursorRepository(self.conn)

    async def _seed(self, source_id: str, project_id: str, workspace_id: str = "default") -> IngestCursor:
        return await self.repo.get_or_create(
            source_id=source_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )

    async def test_get_or_create_fresh_row_null_cursor(self) -> None:
        cursor = await self._seed("filesystem", "proj-pg-1")
        self.assertIsNone(cursor.last_cursor)
        self.assertEqual(cursor.error_count, 0)

    async def test_get_or_create_existing_no_overwrite(self) -> None:
        await self._seed("remote_ingest", "proj-pg-2")
        await self.repo.advance(
            source_id="remote_ingest",
            project_id="proj-pg-2",
            workspace_id="default",
            cursor_value="ev-001",
            occurred_at="2026-05-12T10:00:00+00:00",
        )
        cursor = await self._seed("remote_ingest", "proj-pg-2")
        self.assertEqual(cursor.last_cursor, "ev-001")

    async def test_advance_writes_and_clears_errors(self) -> None:
        await self._seed("filesystem", "proj-pg-3")
        await self.repo.record_error(
            source_id="filesystem",
            project_id="proj-pg-3",
            workspace_id="default",
            error_message="oops",
        )
        await self.repo.advance(
            source_id="filesystem",
            project_id="proj-pg-3",
            workspace_id="default",
            cursor_value="c-999",
            occurred_at="2026-05-12T13:00:00+00:00",
        )
        cursor = await self._seed("filesystem", "proj-pg-3")
        self.assertEqual(cursor.last_cursor, "c-999")
        self.assertEqual(cursor.error_count, 0)
        self.assertIsNone(cursor.last_error)

    async def test_record_error_increments_count(self) -> None:
        await self._seed("entire", "proj-pg-4")
        await self.repo.record_error(
            source_id="entire",
            project_id="proj-pg-4",
            workspace_id="default",
            error_message="err-1",
        )
        await self.repo.record_error(
            source_id="entire",
            project_id="proj-pg-4",
            workspace_id="default",
            error_message="err-2",
        )
        cursor = await self._seed("entire", "proj-pg-4")
        self.assertEqual(cursor.error_count, 2)
        self.assertEqual(cursor.last_error, "err-2")


if __name__ == "__main__":
    unittest.main()
