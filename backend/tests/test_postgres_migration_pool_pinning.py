"""Startup migrations must pin ONE connection when handed an asyncpg Pool.

node_01M268RE15A6AR73W8856F0DF0: api + worker both ran the idempotent
column/index checks concurrently and hung ~40h behind an 'idle in transaction'
INSERT on sessions.  Root cause: ``run_migrations`` received an
``asyncpg.Pool``; ``Pool.execute`` acquires/releases per statement and the
release reset query runs ``pg_advisory_unlock_all(); RESET ALL;`` -- so the
advisory lock (serialization) and ``lock_timeout`` (bounded failure) were both
dropped one statement after being set.

The unit tests model that reset semantics with a fake pool.  The integration
test (skipped without a reachable Postgres) holds an open transaction on
``sessions`` and asserts startup migrations fail within a bounded time.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import asyncpg
import pytest

from backend.db import postgres_migrations as pm


class _FakeConn:
    def __init__(self, pool: "_FakePool", ident: int) -> None:
        self.pool = pool
        self.ident = ident
        self.lock_timeout = "0"
        self.holds_advisory = False

    def _record(self, sql: str) -> None:
        self.pool.log.append((self.ident, self.lock_timeout, self.holds_advisory, sql))
        s = sql.strip()
        if s.startswith("SET lock_timeout"):
            self.lock_timeout = s.split("=", 1)[1].strip().strip("'")
        elif "pg_advisory_lock" in s:
            self.holds_advisory = True
        elif "pg_advisory_unlock" in s:
            self.holds_advisory = False

    async def execute(self, sql: str, *args: Any) -> str:
        self._record(sql)
        return "OK"

    async def fetchrow(self, sql: str, *args: Any) -> Any:
        self._record(sql)
        if "MAX(version)" in sql:
            return (pm.SCHEMA_VERSION,)
        return (1,)  # every column/constraint/index "exists"

    async def fetchval(self, sql: str, *args: Any) -> Any:
        self._record(sql)
        return "text"

    async def fetch(self, sql: str, *args: Any) -> list:
        self._record(sql)
        return []

    def reset(self) -> None:
        # asyncpg Connection.get_reset_query(): pg_advisory_unlock_all(); RESET ALL;
        self.lock_timeout = "0"
        self.holds_advisory = False


class _Acquire:
    def __init__(self, pool: "_FakePool") -> None:
        self.pool = pool
        self.conn: _FakeConn | None = None

    async def __aenter__(self) -> _FakeConn:
        self.pool.counter += 1
        self.conn = _FakeConn(self.pool, self.pool.counter)
        return self.conn

    async def __aexit__(self, *exc: Any) -> None:
        assert self.conn is not None
        self.conn.reset()


class _FakePool(asyncpg.Pool):  # isinstance(db, asyncpg.Pool) must hold
    def __init__(self) -> None:  # do not call Pool.__init__
        self.counter = 0
        self.log: list[tuple[int, str, bool, str]] = []

    def acquire(self, *a: Any, **k: Any) -> _Acquire:  # type: ignore[override]
        return _Acquire(self)

    async def _one(self, name: str, sql: str, *args: Any) -> Any:
        async with self.acquire() as conn:
            return await getattr(conn, name)(sql, *args)

    async def execute(self, sql: str, *args: Any, **k: Any) -> Any:  # type: ignore[override]
        return await self._one("execute", sql, *args)

    async def fetchrow(self, sql: str, *args: Any, **k: Any) -> Any:  # type: ignore[override]
        return await self._one("fetchrow", sql, *args)

    async def fetchval(self, sql: str, *args: Any, **k: Any) -> Any:  # type: ignore[override]
        return await self._one("fetchval", sql, *args)

    async def fetch(self, sql: str, *args: Any, **k: Any) -> Any:  # type: ignore[override]
        return await self._one("fetch", sql, *args)

    def __del__(self) -> None:  # Pool.__del__ expects real internals
        pass


def _ddl(log: list[tuple[int, str, bool, str]]) -> list[tuple[int, str, bool, str]]:
    return [r for r in log if r[3].lstrip().upper().startswith(("CREATE", "ALTER"))]


def test_pool_run_pins_single_connection_with_lock_and_timeout() -> None:
    pool = _FakePool()
    asyncio.run(pm.run_migrations(pool))

    idents = {r[0] for r in pool.log}
    assert idents == {1}, f"migrations spread across {len(idents)} pooled connections"
    ddl = _ddl(pool.log)
    assert ddl, "expected idempotent CREATE INDEX / ALTER checks to execute"
    assert any("idx_sessions_root" in r[3] for r in ddl), (
        "idx_sessions_root check (the 2026-09-10 hang) not exercised"
    )
    for _ident, lock_timeout, holds_advisory, sql in ddl:
        assert holds_advisory, f"DDL ran without the migration advisory lock: {sql[:80]}"
        assert lock_timeout == "5s", f"DDL ran with lock_timeout={lock_timeout}: {sql[:80]}"


def test_pool_run_surfaces_lock_timeout_as_failure() -> None:
    pool = _FakePool()
    original = _FakeConn.execute

    async def _blocked(self: _FakeConn, sql: str, *args: Any) -> str:
        if "idx_sessions_root" in sql:
            raise asyncpg.exceptions.LockNotAvailableError("canceling statement due to lock timeout")
        return await original(self, sql, *args)

    _FakeConn.execute = _blocked  # type: ignore[method-assign]
    try:
        with pytest.raises(asyncpg.exceptions.LockNotAvailableError):
            asyncio.run(pm.run_migrations(pool))
    finally:
        _FakeConn.execute = original  # type: ignore[method-assign]
    # Advisory lock released and timeout reset on the pinned connection.
    tail = [r[3] for r in pool.log[-2:]]
    assert "SET lock_timeout = 0" in tail[0]
    assert "pg_advisory_unlock" in tail[1]
    assert {r[0] for r in pool.log} == {1}


@pytest.mark.skipif(
    os.environ.get("CCDASH_DB_BACKEND") != "postgres"
    or not os.environ.get("CCDASH_DATABASE_URL"),
    reason="requires CCDASH_DB_BACKEND=postgres and a reachable CCDASH_DATABASE_URL",
)
def test_open_transaction_on_sessions_fails_startup_migration_bounded() -> None:
    from backend import config

    async def _run() -> float:
        pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=4)
        holder = await asyncpg.connect(config.DATABASE_URL)
        try:
            await pm.run_migrations(pool)  # ensure schema exists
            async with pool.acquire() as c:
                await c.execute("DROP INDEX IF EXISTS idx_sessions_root")
            tx = holder.transaction()
            await tx.start()
            # Same lock the 2026-09-10 idle-in-transaction INSERT held.
            await holder.execute("LOCK TABLE sessions IN ROW EXCLUSIVE MODE")
            started = time.monotonic()
            with pytest.raises(asyncpg.exceptions.LockNotAvailableError):
                await asyncio.wait_for(pm.run_migrations(pool), timeout=60)
            elapsed = time.monotonic() - started
            await tx.rollback()
            await pm.run_migrations(pool)  # recovers once the holder is gone
            return elapsed
        finally:
            await holder.close()
            await pool.close()

    assert asyncio.run(_run()) < 30
