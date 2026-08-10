"""Postgres-backend coverage for the provider dimension repositories (Fix 2).

``backend/db/repositories/provider_dimensions.py`` previously shipped a
SQLite-only repository; ``SyncEngine.__init__`` built it only when
``isinstance(db, aiosqlite.Connection)`` and set it to ``None`` otherwise, so
the Postgres deployment target -- the actual production backend -- silently
skipped phase-1 provider backfill entirely (the tables would exist, per the
v52 migration, and stay permanently empty). This module covers the fix:

1. ``get_provider_dimensions_repository`` picks
   :class:`PostgresProviderDimensionsRepository` for a non-``aiosqlite``
   connection and :class:`SqliteProviderDimensionsRepository` for an
   ``aiosqlite.Connection`` -- exercised with a real in-memory SQLite
   connection for the SQLite branch and a minimal asyncpg-shaped fake for the
   Postgres branch, so this assertion needs no live Postgres server.
2. SECURITY (the reviewer's explicit, non-negotiable requirement): on the
   Postgres path, the secret guard MUST fire BEFORE ``self.db.execute`` is
   ever reached -- PostgreSQL's UNIQUE-violation ``DETAIL`` line echoes the
   offending values (unlike SQLite's ``IntegrityError``, which names only the
   column), so a secret-shaped value that reached the SQL layer and collided
   would leak through the duplicate-key error itself. These tests assert,
   for every guarded field on every write method,
   that: (a) the fake connection's ``execute`` was NEVER called when the
   guard rejects, and (b) the raised message never contains the secret. No
   live Postgres server is required -- only guard-vs-execute call ordering
   and message content are asserted, mirroring the existing SQLite leak-lock
   tests in ``test_provider_dimensions_repo.py``.
3. A minimal happy-path smoke test per write method against the fake
   connection, confirming the ``$N``-placeholder SQL is well-formed enough to
   reach ``execute``/``fetchrow``/``fetch`` with the expected arg count (a
   live-Postgres smoke test is out of scope here; the SQL text itself is
   reviewed by inspection and exercised for real by
   ``docker:hosted:smoke:seeded-pg`` per this repo's Postgres-integration
   convention).

Run as a named module (unscoped collection can hang this repo):
    backend/.venv/bin/python -m pytest backend/tests/test_provider_dimensions_postgres_repo.py -q -p no:cacheprovider
"""
from __future__ import annotations

import unittest
from typing import Any

import aiosqlite

from backend.db.repositories.provider_dimensions import (
    PostgresProviderDimensionsRepository,
    SqliteProviderDimensionsRepository,
    get_provider_dimensions_repository,
)


# ── Minimal asyncpg-shaped fake (no live Postgres required) ─────────────────


class _FakeAsyncpgConnection:
    """Records every call made to it; never actually touches a database.

    Mirrors the ``_FakeConnection``/``_FakePool`` double pattern already used
    in ``backend/tests/test_postgres_listener_reconnect.py`` for offline
    Postgres-shaped testing.
    """

    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fetchrow_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fetch_calls: list[tuple[str, tuple[Any, ...]]] = []

    async def execute(self, query: str, *args: Any) -> str:
        self.execute_calls.append((query, args))
        return "INSERT 0 1"

    async def fetchrow(self, query: str, *args: Any) -> None:
        self.fetchrow_calls.append((query, args))
        return None

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.fetch_calls.append((query, args))
        return []


# ── Factory: picks the right backend by connection type ─────────────────────


class ProviderDimensionsFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_factory_returns_sqlite_repo_for_aiosqlite_connection(self) -> None:
        db = await aiosqlite.connect(":memory:")
        try:
            repo = get_provider_dimensions_repository(db)
            self.assertIsInstance(repo, SqliteProviderDimensionsRepository)
        finally:
            await db.close()

    def test_factory_returns_postgres_repo_for_non_aiosqlite_connection(self) -> None:
        fake_db = _FakeAsyncpgConnection()
        repo = get_provider_dimensions_repository(fake_db)
        self.assertIsInstance(repo, PostgresProviderDimensionsRepository)


# ── Guard-before-execute ordering (the reviewer's hard security requirement) ─


class PostgresGuardFiresBeforeExecuteTests(unittest.IsolatedAsyncioTestCase):
    """For every guarded field on every write method: the fake connection's
    ``execute`` must NEVER be called when the guard rejects, and the raised
    message must never contain the secret. This is the offline-testable
    proxy for "the guard runs before any SQL reaches Postgres" -- if a future
    refactor reordered guard-vs-SQL-build, these tests would start recording
    a call in ``execute_calls`` and fail.
    """

    _SECRET = "sk-ant-api03-SUPERSECRETVALUE123"

    async def asyncSetUp(self) -> None:
        self.db = _FakeAsyncpgConnection()
        self.repo = PostgresProviderDimensionsRepository(self.db)

    def _assert_guard_fired_before_any_call(self, ctx: Any) -> None:
        self.assertEqual(self.db.execute_calls, [])
        message = str(ctx.exception)
        self.assertNotIn(self._SECRET, message)
        self.assertNotIn("SUPERSECRETVALUE123", message)

    async def test_provider_dimension_provider_id_guard_fires_before_execute(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            await self.repo.upsert_provider_dimension(provider_id=self._SECRET)
        self._assert_guard_fired_before_any_call(ctx)

    async def test_provider_dimension_provider_vendor_guard_fires_before_execute(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            await self.repo.upsert_provider_dimension(
                provider_id="anthropic:claude-code:ica", provider_vendor=self._SECRET
            )
        self._assert_guard_fired_before_any_call(ctx)

    async def test_provider_dimension_provider_surface_guard_fires_before_execute(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            await self.repo.upsert_provider_dimension(
                provider_id="anthropic:claude-code:ica", provider_surface=self._SECRET
            )
        self._assert_guard_fired_before_any_call(ctx)

    async def test_provider_dimension_provider_label_guard_fires_before_execute(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            await self.repo.upsert_provider_dimension(
                provider_id="anthropic:claude-code:ica", provider_label=self._SECRET
            )
        self._assert_guard_fired_before_any_call(ctx)

    async def test_provider_channel_label_guard_fires_before_execute(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            await self.repo.upsert_provider_channel(channel="ica", label=self._SECRET)
        self._assert_guard_fired_before_any_call(ctx)

    async def test_provider_credential_credential_name_guard_fires_before_execute(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            await self.repo.upsert_provider_credential(channel="ica", credential_name=self._SECRET)
        self._assert_guard_fired_before_any_call(ctx)

    async def test_provider_credential_provider_id_guard_fires_before_execute(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            await self.repo.upsert_provider_credential(
                channel="ica", credential_name="CC1", provider_id=self._SECRET
            )
        self._assert_guard_fired_before_any_call(ctx)

    async def test_provider_dimension_provider_channel_guard_fires_before_execute(self) -> None:
        """provider_channel IS guarded (like every other field) since the
        entropy-alphabet narrowing -- see the module docstring."""
        with self.assertRaises(ValueError) as ctx:
            await self.repo.upsert_provider_dimension(
                provider_id="anthropic:claude-code:x", provider_channel=self._SECRET
            )
        self._assert_guard_fired_before_any_call(ctx)

    async def test_provider_channel_channel_guard_fires_before_execute(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            await self.repo.upsert_provider_channel(channel=self._SECRET)
        self._assert_guard_fired_before_any_call(ctx)

    async def test_provider_credential_channel_guard_fires_before_execute(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            await self.repo.upsert_provider_credential(channel=self._SECRET, credential_name="CC1")
        self._assert_guard_fired_before_any_call(ctx)


class PostgresChannelAcceptsLongHyphenatedSlugTests(unittest.IsolatedAsyncioTestCase):
    """``channel`` / ``provider_channel`` ARE guarded on the Postgres backend
    (like every other field, since the entropy-alphabet narrowing) -- but a
    long/hyphenated legitimate open-vocabulary channel token must still reach
    ``execute``, not raise. Mirrors the SQLite-side
    ``test_unrecognized_future_channel_slug_still_accepted``."""

    async def asyncSetUp(self) -> None:
        self.db = _FakeAsyncpgConnection()
        self.repo = PostgresProviderDimensionsRepository(self.db)

    async def test_long_channel_slug_reaches_execute_on_provider_dimension(self) -> None:
        long_channel = "vertex-ai-workbench-preview-2027-rollout"
        await self.repo.upsert_provider_dimension(
            provider_id="google:unknown:" + long_channel, provider_channel=long_channel
        )
        self.assertEqual(len(self.db.execute_calls), 1)

    async def test_long_channel_slug_reaches_execute_on_provider_channels_table(self) -> None:
        long_channel = "vertex-ai-workbench-preview-2027-rollout"
        await self.repo.upsert_provider_channel(channel=long_channel)
        self.assertEqual(len(self.db.execute_calls), 1)

    async def test_long_channel_slug_reaches_execute_on_provider_credentials(self) -> None:
        long_channel = "vertex-ai-workbench-preview-2027-rollout"
        await self.repo.upsert_provider_credential(channel=long_channel, credential_name="CC1")
        self.assertEqual(len(self.db.execute_calls), 1)


# ── Happy-path smoke: legitimate values reach execute/fetch with the right shape ──


class PostgresHappyPathSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = _FakeAsyncpgConnection()
        self.repo = PostgresProviderDimensionsRepository(self.db)

    async def test_upsert_provider_dimension_reaches_execute_with_nine_dollar_placeholders(self) -> None:
        await self.repo.upsert_provider_dimension(
            provider_id="anthropic:claude-code:ica",
            provider_vendor="Anthropic",
            provider_surface="Claude Code",
            provider_channel="ica",
            provider_label="Anthropic · Claude Code · ICA",
        )
        self.assertEqual(len(self.db.execute_calls), 1)
        query, args = self.db.execute_calls[0]
        self.assertIn("$1", query)
        self.assertIn("$9", query)
        self.assertIn("ON CONFLICT(provider_id)", query)
        self.assertEqual(len(args), 9)
        self.assertEqual(args[0], "anthropic:claude-code:ica")

    async def test_upsert_provider_channel_reaches_execute(self) -> None:
        await self.repo.upsert_provider_channel(channel="ica", label="ICA")
        query, args = self.db.execute_calls[0]
        self.assertIn("ON CONFLICT(channel)", query)
        self.assertEqual(args[0], "ica")
        self.assertEqual(args[1], "ICA")

    async def test_upsert_provider_credential_reaches_execute(self) -> None:
        await self.repo.upsert_provider_credential(
            channel="ica", credential_name="CC1", provider_id="anthropic:claude-code:ica"
        )
        query, args = self.db.execute_calls[0]
        self.assertIn("ON CONFLICT(channel, credential_name)", query)
        self.assertEqual(args[:3], ("ica", "CC1", "anthropic:claude-code:ica"))

    async def test_get_provider_dimension_reaches_fetchrow(self) -> None:
        result = await self.repo.get_provider_dimension("anthropic:claude-code:ica")
        self.assertIsNone(result)
        query, args = self.db.fetchrow_calls[0]
        self.assertIn("$1", query)
        self.assertEqual(args, ("anthropic:claude-code:ica",))

    async def test_list_provider_credentials_reaches_fetch(self) -> None:
        result = await self.repo.list_provider_credentials()
        self.assertEqual(result, [])
        self.assertEqual(len(self.db.fetch_calls), 1)

    async def test_backfill_reaches_fetch_with_dollar_one_placeholder(self) -> None:
        stats = await self.repo.backfill_provider_dimensions_from_sessions("proj1")
        self.assertEqual(stats["sessions_scanned"], 0)
        query, args = self.db.fetch_calls[0]
        self.assertIn("$1", query)
        self.assertEqual(args, ("proj1",))


if __name__ == "__main__":
    unittest.main()
