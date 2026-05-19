"""Regression tests: upsert_logs must survive duplicate source_log_id values.

UNIQUE constraint failed: session_logs.session_id, session_logs.source_log_id

SQLite repo  — uses a real in-memory DB via aiosqlite + run_migrations.
Postgres repo — uses a fake-connection stub (no live Postgres required); skips
               if asyncpg is unavailable.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

import aiosqlite

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations

_NOW = datetime.now(timezone.utc).isoformat()

_MINIMAL_SESSION = {
    "id": "S-DEDUPE-1",
    "status": "completed",
    "model": "claude-sonnet-4-5",
    "startedAt": _NOW,
    "endedAt": _NOW,
    # Fields the upsert() method maps to required DB columns
    "createdAt": _NOW,
    "updatedAt": _NOW,
    # source_file is required; upsert() maps "sourceFile" key or falls back to ""
}


class TestSqliteUpsertLogsDedupe(unittest.IsolatedAsyncioTestCase):
    """SQLite: duplicate source_log_id entries in logs[] must not raise and must be collapsed."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteSessionRepository(self.db)
        # Insert a parent session row via the repo so the FK on session_logs is satisfied.
        await self.repo.upsert(_MINIMAL_SESSION, "project-1")
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_duplicate_source_log_id_collapses_to_one_row(self) -> None:
        """Two log entries sharing the same non-empty id must produce exactly one DB row."""
        duplicate_id = "log-dup-abc"
        logs = [
            {
                "id": duplicate_id,
                "timestamp": "2026-05-19T10:00:01Z",
                "speaker": "user",
                "type": "message",
                "content": "first occurrence",
            },
            {
                "id": duplicate_id,
                "timestamp": "2026-05-19T10:00:02Z",
                "speaker": "user",
                "type": "message",
                "content": "duplicate — should be dropped",
            },
        ]

        # Must not raise IntegrityError.
        await self.repo.upsert_logs("S-DEDUPE-1", logs)

        async with self.db.execute(
            "SELECT COUNT(*) FROM session_logs WHERE session_id = ?",
            ("S-DEDUPE-1",),
        ) as cur:
            count = (await cur.fetchone())[0]

        self.assertEqual(count, 1, "Duplicate source_log_id must be collapsed to a single row")

    async def test_duplicate_source_log_id_logs_warning(self) -> None:
        """The WARNING must be emitted with session_id and drop-count details."""
        duplicate_id = "log-warn-xyz"
        logs = [
            {"id": duplicate_id, "timestamp": "T1", "speaker": "user", "type": "message", "content": "a"},
            {"id": duplicate_id, "timestamp": "T2", "speaker": "user", "type": "message", "content": "b"},
            {"id": duplicate_id, "timestamp": "T3", "speaker": "user", "type": "message", "content": "c"},
        ]

        with self.assertLogs("ccdash.db.sessions", level="WARNING") as log_cm:
            await self.repo.upsert_logs("S-DEDUPE-1", logs)

        # Exactly one warning should be emitted per call.
        warning_lines = [m for m in log_cm.output if "WARNING" in m]
        self.assertEqual(len(warning_lines), 1)

        warning_text = warning_lines[0]
        self.assertIn("S-DEDUPE-1", warning_text)
        # 2 duplicates dropped (3 entries, 1 kept)
        self.assertIn("2", warning_text)

    async def test_no_warning_when_no_duplicates(self) -> None:
        """No WARNING should be emitted when all source_log_ids are distinct."""
        logs = [
            {"id": "log-a", "timestamp": "T1", "speaker": "user", "type": "message", "content": "a"},
            {"id": "log-b", "timestamp": "T2", "speaker": "user", "type": "message", "content": "b"},
        ]

        with self.assertNoLogs("ccdash.db.sessions", level="WARNING"):
            await self.repo.upsert_logs("S-DEDUPE-1", logs)

        async with self.db.execute(
            "SELECT COUNT(*) FROM session_logs WHERE session_id = ?",
            ("S-DEDUPE-1",),
        ) as cur:
            count = (await cur.fetchone())[0]

        self.assertEqual(count, 2)

    async def test_empty_source_log_id_not_deduplicated(self) -> None:
        """Entries with empty id (source_log_id='') must all be kept — the constraint is partial."""
        logs = [
            {"id": "", "timestamp": "T1", "speaker": "user", "type": "message", "content": "no-id-1"},
            {"id": "", "timestamp": "T2", "speaker": "user", "type": "message", "content": "no-id-2"},
        ]

        await self.repo.upsert_logs("S-DEDUPE-1", logs)

        async with self.db.execute(
            "SELECT COUNT(*) FROM session_logs WHERE session_id = ?",
            ("S-DEDUPE-1",),
        ) as cur:
            count = (await cur.fetchone())[0]

        self.assertEqual(count, 2, "Empty source_log_id rows must all be kept")


# ---------------------------------------------------------------------------
# Postgres repo — stub-based, no live connection required
# ---------------------------------------------------------------------------

try:
    import asyncpg as _asyncpg  # noqa: F401
    _ASYNCPG_AVAILABLE = True
except ImportError:
    _ASYNCPG_AVAILABLE = False


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePostgresConnection:
    """Minimal asyncpg connection stub that records SQL calls."""

    def __init__(self):
        self.execute_calls: list[tuple[str, tuple]] = []
        self.executemany_calls: list[tuple[str, list]] = []

    def transaction(self):
        return _AsyncContext(self)

    async def execute(self, query: str, *args):
        self.execute_calls.append((query, args))

    async def executemany(self, query: str, records):
        self.executemany_calls.append((query, list(records)))


@unittest.skipUnless(_ASYNCPG_AVAILABLE, "asyncpg not installed — Postgres repo tests skipped")
class TestPostgresUpsertLogsDedupe(unittest.IsolatedAsyncioTestCase):
    """Postgres repo: duplicate source_log_id entries are dropped before executemany."""

    async def asyncSetUp(self) -> None:
        from backend.db.repositories.postgres.sessions import PostgresSessionRepository

        self.conn = _FakePostgresConnection()
        self.repo = PostgresSessionRepository(self.conn)

    async def test_duplicate_source_log_id_produces_one_record(self) -> None:
        duplicate_id = "log-pg-dup"
        logs = [
            {"id": duplicate_id, "timestamp": "T1", "speaker": "user", "type": "message", "content": "first"},
            {"id": duplicate_id, "timestamp": "T2", "speaker": "user", "type": "message", "content": "dup"},
        ]

        await self.repo.upsert_logs("S-PG-1", logs)

        self.assertEqual(len(self.conn.executemany_calls), 1)
        _query, records = self.conn.executemany_calls[0]
        self.assertEqual(len(records), 1, "Duplicate source_log_id must be collapsed before executemany")
        # Confirm ON CONFLICT clause is present in the query
        self.assertIn("ON CONFLICT", _query)
        self.assertIn("idx_logs_source_log_unique", _query)

    async def test_duplicate_source_log_id_logs_warning(self) -> None:
        duplicate_id = "log-pg-warn"
        logs = [
            {"id": duplicate_id, "timestamp": "T1", "speaker": "user", "type": "message", "content": "a"},
            {"id": duplicate_id, "timestamp": "T2", "speaker": "user", "type": "message", "content": "b"},
        ]

        with self.assertLogs("ccdash.db.postgres.sessions", level="WARNING") as log_cm:
            await self.repo.upsert_logs("S-PG-1", logs)

        warning_lines = [m for m in log_cm.output if "WARNING" in m]
        self.assertEqual(len(warning_lines), 1)
        self.assertIn("S-PG-1", warning_lines[0])

    async def test_no_warning_when_no_duplicates(self) -> None:
        logs = [
            {"id": "pg-log-a", "timestamp": "T1", "speaker": "user", "type": "message", "content": "a"},
            {"id": "pg-log-b", "timestamp": "T2", "speaker": "user", "type": "message", "content": "b"},
        ]

        with self.assertNoLogs("ccdash.db.postgres.sessions", level="WARNING"):
            await self.repo.upsert_logs("S-PG-2", logs)

        _query, records = self.conn.executemany_calls[0]
        self.assertEqual(len(records), 2)

    async def test_empty_source_log_id_not_deduplicated(self) -> None:
        """Empty-id entries bypass the dedup set; all must reach executemany."""
        logs = [
            {"id": "", "timestamp": "T1", "speaker": "user", "type": "message", "content": "no-id-1"},
            {"id": "", "timestamp": "T2", "speaker": "user", "type": "message", "content": "no-id-2"},
        ]

        await self.repo.upsert_logs("S-PG-3", logs)

        _query, records = self.conn.executemany_calls[0]
        self.assertEqual(len(records), 2, "Empty source_log_id rows must all be forwarded")


if __name__ == "__main__":
    unittest.main()
