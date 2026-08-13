"""Asyncpg-path regression coverage for RemoteSessionIngestService.

The production bug (measured on the live node): ``POST /api/v1/ingest/sessions``
returns 500 on Postgres because ``RemoteSessionIngestService._source_ref_exists``
used the aiosqlite ``async with db.execute(...) as cur`` idiom unconditionally.
On the Postgres path ``self._session_repo.db`` is an asyncpg Pool/Connection —
``pool.execute()`` returns a coroutine (asyncpg has no async-context-manager
``execute()``), so ``async with`` on it raises::

    TypeError: 'coroutine' object does not support the asynchronous context
    manager protocol

A test that merely asserts "``_source_ref_exists`` was called" would pass
against the broken code too (the call would just always raise before
returning). These tests assert the ACTUAL boolean result, so the pre-fix
TypeError propagates instead of being silently absorbed.

Mirrors the ``TestWorkspaceTokenAuthBackendAsyncpgPath`` template in
``backend/tests/test_workspace_token_auth.py`` — a minimal fake asyncpg-style
Pool that is deliberately NOT an ``aiosqlite.Connection`` so the
``isinstance(db, aiosqlite.Connection)`` dispatch in the fixed code takes the
Postgres branch, exactly like the real asyncpg Pool from
``backend/db/connection.py`` on the Postgres backend.
"""
from __future__ import annotations

import unittest

from backend.application.services.ingest.session_ingest import RemoteSessionIngestService
from backend.db.repositories.ingest_cursors import PostgresIngestCursorRepository


class _FakeAsyncpgPool:
    """Minimal stand-in for asyncpg.Pool: fetchrow/execute only.

    Deliberately NOT an aiosqlite.Connection subclass/instance, so
    `isinstance(db, aiosqlite.Connection)` is False for it — exactly like the
    real asyncpg.Pool returned by backend/db/connection.py on the Postgres
    backend. ``execute`` is a real coroutine function (as on the real
    asyncpg Pool) so that calling `async with pool.execute(...)` — the
    pre-fix code path — reproduces the exact TypeError observed in
    production rather than a generic AttributeError.
    """

    def __init__(self, existing_refs: set[str] | None = None) -> None:
        self._existing = existing_refs or set()
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, query: str, *args):
        self.fetchrow_calls.append((query, args))
        source_ref = args[0] if args else None
        if source_ref in self._existing:
            return (1,)
        return None

    async def execute(self, query: str, *args) -> str:
        self.execute_calls.append((query, args))
        return "UPDATE 1"


class _FakeSessionRepo:
    """Duck-typed session repo exposing only the ``.db`` attribute needed by
    ``_source_ref_exists`` — the upsert/upsert_logs paths are not exercised
    by these tests.
    """

    def __init__(self, db) -> None:
        self.db = db


class RemoteSessionIngestServiceSourceRefExistsAsyncpgPathTests(unittest.IsolatedAsyncioTestCase):
    """Drives ``_source_ref_exists`` against a fake asyncpg-style Pool."""

    async def asyncSetUp(self) -> None:
        self.pool = _FakeAsyncpgPool(existing_refs={"remote:existing-event"})
        session_repo = _FakeSessionRepo(self.pool)
        # cursor_repo is unused by _source_ref_exists; None is sufficient.
        self.service = RemoteSessionIngestService(session_repo, cursor_repo=None)

    async def test_source_ref_exists_true_via_asyncpg_fetchrow(self) -> None:
        """A present source_ref must resolve True via pool.fetchrow(), not
        the aiosqlite cursor idiom."""
        exists = await self.service._source_ref_exists("remote:existing-event")
        self.assertTrue(exists)
        self.assertEqual(len(self.pool.fetchrow_calls), 1)
        query, args = self.pool.fetchrow_calls[0]
        self.assertIn("$1", query, "Postgres branch must use $1, not aiosqlite's ?")
        self.assertEqual(args, ("remote:existing-event",))

    async def test_source_ref_exists_false_via_asyncpg_fetchrow(self) -> None:
        """An absent source_ref must resolve False, not raise."""
        exists = await self.service._source_ref_exists("remote:missing-event")
        self.assertFalse(exists)
        self.assertEqual(len(self.pool.fetchrow_calls), 1)


# ── PG ingest-cursor repository (asyncpg path) ───────────────────────────────


class _FakeCursorRecord(dict):
    """asyncpg.Record stand-in: supports both dict and attribute access."""

    def __getattr__(self, item: str):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(item)


class _FakeCursorConnection:
    """Minimal asyncpg.Connection fake driving PostgresIngestCursorRepository."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str, str], dict] = {}

    async def fetchrow(self, query: str, *args):
        key = (args[0], args[1], args[2])
        row = self._store.get(key)
        return _FakeCursorRecord(row) if row else None

    async def execute(self, query: str, *args) -> None:
        q = query.strip().upper()
        if q.startswith("INSERT"):
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
            key = (args[2], args[3], args[4])
            if key in self._store:
                self._store[key].update(
                    last_cursor=args[0],
                    last_ingest_at=args[1],
                    error_count=0,
                    last_error=None,
                    last_error_at=None,
                )


class PostgresIngestCursorRepositoryAsyncpgPathTests(unittest.IsolatedAsyncioTestCase):
    """get_or_create/advance against a fake asyncpg Connection — no real
    Postgres needed. Confirms the repository already dispatched via the
    factory (backend/db/factory.py:get_ingest_cursor_repository) is
    asyncpg-correct end to end."""

    async def asyncSetUp(self) -> None:
        self.conn = _FakeCursorConnection()
        self.repo = PostgresIngestCursorRepository(self.conn)

    async def test_get_or_create_then_advance_round_trips_via_asyncpg(self) -> None:
        cursor = await self.repo.get_or_create(
            source_id="remote_ingest",
            project_id="proj-asyncpg-1",
            workspace_id="default",
        )
        self.assertIsNone(cursor.last_cursor)

        await self.repo.advance(
            source_id="remote_ingest",
            project_id="proj-asyncpg-1",
            workspace_id="default",
            cursor_value="event-42",
            occurred_at="2026-08-13T00:00:00+00:00",
        )

        cursor = await self.repo.get_or_create(
            source_id="remote_ingest",
            project_id="proj-asyncpg-1",
            workspace_id="default",
        )
        self.assertEqual(cursor.last_cursor, "event-42")
        self.assertEqual(cursor.last_ingest_at, "2026-08-13T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
