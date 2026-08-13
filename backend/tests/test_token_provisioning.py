"""Tests for backend.application.services.auth.token_provisioning.

Node: node_01KZVXWY2CR9V2GG04PQNFZ1EM.

Coverage maps to the node's ACs:
  AC1/AC3 — provisioning runs on BOTH backends and creates a verifiable row.
            SQLite is exercised against a real temp DB; Postgres against a
            faithful fake asyncpg Pool (the repo's established no-live-PG
            pattern — see be420d8's _FakeAsyncpgPool and
            test_remote_session_ingest_asyncpg_path.py). The fake enforces the
            two things the old SQLite-only code got wrong on PG: fetch/execute
            are plain coroutines (NOT async context managers), and placeholders
            are $1-style, not '?'.
  AC2     — a failed schema read ABORTS (SchemaNotReadyError); migrations are
            never run and the version is never silently assumed to be 0.
  AC4     — a second run with the same plaintext token is a no-op on both
            backends (argon2id dedup by verify).
"""
from __future__ import annotations

import os
import re
import tempfile
import unittest

import aiosqlite

from backend.application.services.auth.token_provisioning import (
    SchemaNotReadyError,
    provision_workspace_token,
)


# --------------------------------------------------------------------------- #
# Fake asyncpg Pool — deliberately does NOT support the aiosqlite cursor idiom  #
# --------------------------------------------------------------------------- #
class _FakeAsyncpgPool:
    """Minimal asyncpg.Pool stand-in backed by an in-memory workspace_tokens list.

    Enforces the asyncpg contract that broke the old code:
      * fetch()/fetchrow()/execute() are plain coroutines returning values —
        there is NO ``async with pool.execute(...) as cur`` cursor idiom, so a
        regression to the aiosqlite form raises AttributeError here.
      * placeholders are ``$1``-style; a stray ``?`` is asserted against.

    It implements only the handful of statements token_provisioning issues.
    ``schema_ready=False`` makes the probe SELECT raise, standing in for a
    Postgres deployment whose workspace_tokens table is absent.
    """

    def __init__(self, *, schema_ready: bool = True) -> None:
        self.schema_ready = schema_ready
        self.workspaces: set[str] = set()
        # rows: list of dicts with token_id/workspace_id/project_id/hashed_token/...
        self.tokens: list[dict] = []

    @staticmethod
    def _assert_pg_placeholders(query: str) -> None:
        assert "?" not in query, f"SQLite '?' placeholder leaked onto the PG arm: {query!r}"

    async def fetch(self, query: str, *args):
        self._assert_pg_placeholders(query)
        q = " ".join(query.split())
        if q.startswith("SELECT 1 FROM workspace_tokens"):
            if not self.schema_ready:
                raise RuntimeError('relation "workspace_tokens" does not exist')
            return []
        if q.startswith("SELECT token_id, hashed_token FROM workspace_tokens"):
            ws, proj = args
            return [
                (r["token_id"], r["hashed_token"])
                for r in self.tokens
                if r["workspace_id"] == ws
                and r["project_id"] == proj
                and r["revoked_at"] is None
            ]
        raise AssertionError(f"unexpected fetch: {q!r}")

    async def execute(self, query: str, *args):
        self._assert_pg_placeholders(query)
        q = " ".join(query.split())
        if q.startswith("INSERT INTO workspaces"):
            # ON CONFLICT DO NOTHING
            self.workspaces.add(args[0])
            return "INSERT 0 1"
        if q.startswith("INSERT INTO workspace_tokens"):
            token_id, ws, proj, hashed, scope, desc, created = args
            self.tokens.append(
                {
                    "token_id": token_id,
                    "workspace_id": ws,
                    "project_id": proj,
                    "hashed_token": hashed,
                    "scope": scope,
                    "description": desc,
                    "created_at": created,
                    "revoked_at": None,
                }
            )
            return "INSERT 0 1"
        raise AssertionError(f"unexpected execute: {q!r}")


_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class SqliteProvisioningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = await aiosqlite.connect(self._tmp.name)
        self.db.row_factory = aiosqlite.Row
        from backend.db.sqlite_migrations import run_migrations

        await run_migrations(self.db)
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    async def _count(self) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM workspace_tokens WHERE revoked_at IS NULL"
        ) as cur:
            return (await cur.fetchone())[0]

    async def test_fresh_creates_one_verifiable_row(self) -> None:  # AC1
        res = await provision_workspace_token(
            self.db, token="sekret", project_id="proj-a"
        )
        self.assertTrue(res.created)
        self.assertTrue(_UUID_RE.match(res.token_id))
        self.assertEqual(res.workspace_id, "default-local")
        self.assertEqual(await self._count(), 1)

        # verifiable via the real auth backend
        from backend.adapters.auth.workspace_token import WorkspaceTokenAuthBackend

        backend = WorkspaceTokenAuthBackend(get_db=self._aw)
        ctx = await backend.verify("sekret")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.project_id, "proj-a")

    async def _aw(self):
        return self.db

    async def test_second_run_same_token_is_noop(self) -> None:  # AC4
        first = await provision_workspace_token(self.db, token="dup", project_id="p")
        second = await provision_workspace_token(self.db, token="dup", project_id="p")
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.token_id, second.token_id)
        self.assertEqual(await self._count(), 1)

    async def test_empty_token_and_project_raise(self) -> None:
        with self.assertRaises(ValueError):
            await provision_workspace_token(self.db, token="", project_id="p")
        with self.assertRaises(ValueError):
            await provision_workspace_token(self.db, token="t", project_id="")


class PostgresBackendProvisioningTests(unittest.IsolatedAsyncioTestCase):
    """AC1/AC3/AC4 on the Postgres backend, via a faithful fake asyncpg Pool."""

    async def test_fresh_creates_one_row_on_pg_arm(self) -> None:  # AC1/AC3
        pool = _FakeAsyncpgPool(schema_ready=True)
        res = await provision_workspace_token(pool, token="pgtok", project_id="pg-proj")
        self.assertTrue(res.created)
        self.assertEqual(len(pool.tokens), 1)
        self.assertEqual(pool.tokens[0]["project_id"], "pg-proj")
        self.assertIn("default-local", pool.workspaces)

    async def test_second_run_same_token_is_noop_on_pg_arm(self) -> None:  # AC4
        pool = _FakeAsyncpgPool(schema_ready=True)
        first = await provision_workspace_token(pool, token="dup", project_id="p")
        second = await provision_workspace_token(pool, token="dup", project_id="p")
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.token_id, second.token_id)
        self.assertEqual(len(pool.tokens), 1)

    async def test_unprovisioned_schema_aborts_and_runs_no_migration(self) -> None:  # AC2
        pool = _FakeAsyncpgPool(schema_ready=False)
        with self.assertRaises(SchemaNotReadyError) as ctx:
            await provision_workspace_token(pool, token="t", project_id="p")
        # No token was written — provisioning aborted rather than "assuming 0"
        # and running migrations.
        self.assertEqual(len(pool.tokens), 0)
        # The message must be actionable and must NOT claim to have migrated.
        msg = str(ctx.exception)
        self.assertIn("not provisioned", msg)
        self.assertIn("will NOT run migrations", msg)


if __name__ == "__main__":
    unittest.main()
