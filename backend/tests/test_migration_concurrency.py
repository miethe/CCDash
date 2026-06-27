"""Migration concurrency and idempotency tests.

T3-001 (AC-005): Concurrent-process migration safety on SQLite.
T3-003 (AC-007): Idempotent re-run safety on SQLite + Postgres skip variant.

Design choices:
- All tests use temp-dir databases, never data/ccdash_cache.db.
- Concurrency test uses multiprocessing.Process (not asyncio tasks) so each
  worker has its own OS file descriptor and flock acquisition contest is real.
- subprocess.run with CCDASH_DB_PATH env override is used so the flock-path
  resolver in sqlite_migrations picks up the temp dir correctly.
- Postgres idempotency test is skipped unless CCDASH_DB_BACKEND=postgres AND
  CCDASH_DATABASE_URL is set to a reachable server.
"""
from __future__ import annotations

import asyncio
import multiprocessing
import os
import sqlite3
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_migrations_in_subprocess(db_path: str, result_queue: "multiprocessing.Queue[str]") -> None:
    """Target for multiprocessing.Process: run SQLite migrations and report outcome."""
    # Must import inside worker so each process initialises its own event loop.
    import asyncio as _aio
    import os as _os

    _os.environ["CCDASH_DB_PATH"] = db_path

    async def _inner() -> str:
        import aiosqlite
        from backend.db import sqlite_migrations

        try:
            async with aiosqlite.connect(db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL")
                # Safety net: match the busy_timeout set inside run_migrations
                # so WAL conversion contention before the flock is acquired
                # results in a wait rather than an immediate OperationalError.
                await db.execute("PRAGMA busy_timeout = 30000")
                await sqlite_migrations.run_migrations(db)
            return "ok"
        except Exception as exc:
            return f"error:{type(exc).__name__}:{exc}"

    outcome = _aio.run(_inner())
    result_queue.put(outcome)


def _collect_schema(db_path: str) -> tuple[frozenset[str], int, list[int]]:
    """Return (table_names, schema_version, applied_versions) from a SQLite DB."""
    conn = sqlite3.connect(db_path)
    try:
        tables = frozenset(
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        )
        try:
            sv = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0
        except Exception:
            sv = 0
        try:
            avs = sorted(
                row[0]
                for row in conn.execute("SELECT version FROM migrations_applied ORDER BY version").fetchall()
            )
        except Exception:
            avs = []
        return tables, sv, avs
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# T3-001: Concurrent process migration test (AC-005)
# ---------------------------------------------------------------------------


class TestMigrationConcurrency(unittest.TestCase):
    """Two concurrent processes racing on the same fresh SQLite DB.

    Assertions (all must hold):
    - Neither process raises OperationalError or "database is locked" / "schema
      changed" errors.
    - Final schema_version equals SCHEMA_VERSION.
    - No duplicate rows in migrations_applied.
    - Table set is identical to a single-process reference run.
    """

    def _reference_tables(self, db_path: str) -> frozenset[str]:
        """Run migrations single-process and return the resulting table set."""
        import aiosqlite
        from backend.db import sqlite_migrations

        async def _run() -> None:
            async with aiosqlite.connect(db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL")
                await sqlite_migrations.run_migrations(db)

        asyncio.run(_run())
        tables, _, _ = _collect_schema(db_path)
        return tables

    def test_concurrent_processes_do_not_corrupt_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "concurrent_test.db")
            ref_path = str(Path(tmpdir) / "reference.db")

            # Build reference schema
            ref_tables = self._reference_tables(ref_path)
            from backend.db.sqlite_migrations import SCHEMA_VERSION

            # Now race two fresh processes on the real db_path
            queue: multiprocessing.Queue[str] = multiprocessing.Queue()
            p1 = multiprocessing.Process(
                target=_run_migrations_in_subprocess,
                args=(db_path, queue),
            )
            p2 = multiprocessing.Process(
                target=_run_migrations_in_subprocess,
                args=(db_path, queue),
            )

            p1.start()
            p2.start()
            p1.join(timeout=90)
            p2.join(timeout=90)

            results = [queue.get_nowait() for _ in range(2)]

            # Both processes must have exited cleanly
            self.assertEqual(p1.exitcode, 0, f"Process 1 exited with code {p1.exitcode}")
            self.assertEqual(p2.exitcode, 0, f"Process 2 exited with code {p2.exitcode}")

            for outcome in results:
                self.assertEqual(
                    outcome,
                    "ok",
                    f"Process reported error: {outcome}",
                )
                self.assertNotIn(
                    "database is locked",
                    outcome.lower(),
                    f"Got 'database is locked' from concurrent run: {outcome}",
                )
                self.assertNotIn(
                    "schema changed",
                    outcome.lower(),
                    f"Got 'schema changed' from concurrent run: {outcome}",
                )

            # Final schema must match reference
            tables, sv, applied_versions = _collect_schema(db_path)

            self.assertSetEqual(
                tables,
                ref_tables,
                "Concurrent migration produced different table set than reference run",
            )
            self.assertEqual(
                sv,
                SCHEMA_VERSION,
                f"Expected schema_version {SCHEMA_VERSION}, got {sv}",
            )

            # T3-011: No duplicate versions in migrations_applied
            self.assertEqual(
                len(applied_versions),
                len(set(applied_versions)),
                f"Duplicate versions in migrations_applied after concurrent run: {applied_versions}",
            )
            self.assertGreater(
                len(applied_versions),
                0,
                "migrations_applied must have at least one row",
            )


# ---------------------------------------------------------------------------
# T3-003: Idempotency test (AC-007) — SQLite
# ---------------------------------------------------------------------------


class TestMigrationIdempotencySQLite(unittest.IsolatedAsyncioTestCase):
    """Run migrations twice on the same SQLite DB and assert the second is a no-op."""

    async def test_second_run_is_noop_and_schema_is_stable(self) -> None:
        import aiosqlite
        from backend.db import sqlite_migrations
        from backend.db.sqlite_migrations import SCHEMA_VERSION

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "idempotency_test.db")
            os.environ["CCDASH_DB_PATH"] = db_path

            async with aiosqlite.connect(db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL")
                # First run
                await sqlite_migrations.run_migrations(db)

                # Capture sqlite_master state after first run
                async with db.execute(
                    "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
                ) as cur:
                    schema_after_first = await cur.fetchall()

                async with db.execute(
                    "SELECT MAX(version) FROM schema_version"
                ) as cur:
                    row = await cur.fetchone()
                    sv_after_first = row[0] if row else 0

                async with db.execute(
                    "SELECT version FROM migrations_applied ORDER BY version"
                ) as cur:
                    applied_after_first = [r[0] for r in await cur.fetchall()]

            # Second run — must not raise
            async with aiosqlite.connect(db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL")
                await sqlite_migrations.run_migrations(db)

                # Schema must be identical
                async with db.execute(
                    "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
                ) as cur:
                    schema_after_second = await cur.fetchall()

                async with db.execute(
                    "SELECT MAX(version) FROM schema_version"
                ) as cur:
                    row = await cur.fetchone()
                    sv_after_second = row[0] if row else 0

                async with db.execute(
                    "SELECT version FROM migrations_applied ORDER BY version"
                ) as cur:
                    applied_after_second = [r[0] for r in await cur.fetchall()]

            self.assertEqual(
                schema_after_first,
                schema_after_second,
                "sqlite_master changed between first and second migration run (not idempotent)",
            )
            self.assertEqual(
                sv_after_first,
                sv_after_second,
                "schema_version changed on second run",
            )
            self.assertEqual(
                sv_after_second,
                SCHEMA_VERSION,
                f"schema_version should be {SCHEMA_VERSION}, got {sv_after_second}",
            )
            # T3-011: No duplicate version rows after second run
            self.assertEqual(
                len(applied_after_second),
                len(set(applied_after_second)),
                f"Duplicate versions in migrations_applied after second run: {applied_after_second}",
            )
            self.assertEqual(
                applied_after_first,
                applied_after_second,
                "migrations_applied changed on second run (rows added or removed)",
            )


# ---------------------------------------------------------------------------
# T3-003: Idempotency test (AC-007) — Postgres skip variant
# ---------------------------------------------------------------------------

import pytest


@pytest.mark.skipif(
    os.environ.get("CCDASH_DB_BACKEND") != "postgres"
    or not os.environ.get("CCDASH_DATABASE_URL"),
    reason=(
        "Postgres idempotency test requires CCDASH_DB_BACKEND=postgres "
        "and CCDASH_DATABASE_URL pointing to a reachable server"
    ),
)
class TestMigrationIdempotencyPostgres:
    """Run Postgres migrations twice and assert the second call is a no-op.

    Skipped automatically when no Postgres server is available; no fallback
    mock is used because the test validates real DDL idempotency.
    """

    def test_second_run_is_noop_and_schema_stable(self) -> None:
        import asyncio as _aio

        async def _run() -> None:
            try:
                import asyncpg
            except ImportError:
                pytest.skip("asyncpg not installed")

            from backend import config
            from backend.db import postgres_migrations

            pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=2)
            try:
                async with pool.acquire() as conn:
                    # First run
                    await postgres_migrations.run_migrations(conn)

                    sv_first = await conn.fetchval("SELECT MAX(version) FROM schema_version")
                    applied_first = sorted(
                        r["version"]
                        for r in await conn.fetch("SELECT version FROM migrations_applied ORDER BY version")
                    )
                    tables_first = frozenset(
                        r["tablename"]
                        for r in await conn.fetch(
                            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                        )
                    )

                    # Second run — must not raise
                    await postgres_migrations.run_migrations(conn)

                    sv_second = await conn.fetchval("SELECT MAX(version) FROM schema_version")
                    applied_second = sorted(
                        r["version"]
                        for r in await conn.fetch("SELECT version FROM migrations_applied ORDER BY version")
                    )
                    tables_second = frozenset(
                        r["tablename"]
                        for r in await conn.fetch(
                            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                        )
                    )

                assert sv_first == sv_second, (
                    f"schema_version changed on second Postgres run: {sv_first} -> {sv_second}"
                )
                assert tables_first == tables_second, (
                    "Table set changed on second Postgres run"
                )
                assert len(applied_second) == len(set(applied_second)), (
                    f"Duplicate versions in Postgres migrations_applied: {applied_second}"
                )
                assert applied_first == applied_second, (
                    "migrations_applied changed on second Postgres run"
                )
            finally:
                await pool.close()

        _aio.run(_run())
