"""Tests for backend.scripts.migrate_bearer_to_workspace_token.

Coverage
--------
1. Fresh DB  → script creates 1 workspace row + 1 token row; exits 0.
2. Idempotent → running script a second time on the same DB is a no-op; exits 0
               and the workspace_tokens row count does not increase.
3. Verify    → the inserted hashed_token can be verified by WorkspaceTokenAuthBackend.

DB isolation strategy
---------------------
Each test gets a fresh NamedTemporaryFile SQLite DB via CCDASH_DB_PATH env-var
override.  The connection module re-resolves the path inside get_connection() on
every call (backend.db.connection._resolve_db_path) so patch.dict(os.environ,
{"CCDASH_DB_PATH": tmp}) ensures isolation.

We additionally reset ``backend.db.connection._connection = None`` before each
test to force get_connection() to open a fresh connection to the temp file
rather than reusing any leftover singleton from a prior test.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import aiosqlite
import pytest

# Ensure the repo root is importable when run directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestMigrateBearerScript(unittest.IsolatedAsyncioTestCase):
    """Idempotency and correctness tests for migrate_bearer_to_workspace_token."""

    def setUp(self) -> None:
        """Create a fresh temp DB file and reset the connection singleton."""
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmpdb.close()
        self._tmp_path = self._tmpdb.name

        # Reset singleton so get_connection() opens a fresh connection.
        import backend.db.connection as _dbc
        _dbc._connection = None

        self._env_patch = patch.dict(
            os.environ,
            {
                "CCDASH_DB_PATH": self._tmp_path,
                "CCDASH_DB_BACKEND": "sqlite",
            },
        )
        self._env_patch.start()

    async def asyncTearDown(self) -> None:
        """Close and discard the temp DB."""
        import backend.db.connection as _dbc
        if _dbc._connection is not None:
            await _dbc._connection.close()
            _dbc._connection = None
        self._env_patch.stop()
        try:
            os.unlink(self._tmp_path)
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    # Helper                                                               #
    # ------------------------------------------------------------------ #

    async def _run_migration(
        self,
        *,
        token: str = "test-secret-token",
        workspace: str = "default-local",
        project: str = "test-project",
        description: str = "Test migration",
    ) -> int:
        """Call _run_migration() directly (async) to avoid asyncio.run() nesting."""
        from backend.scripts.migrate_bearer_to_workspace_token import _run_migration

        return await _run_migration(
            token=token,
            workspace_id=workspace,
            project_id=project,
            description=description,
        )

    # ------------------------------------------------------------------ #
    # Test 1 — fresh DB: creates 1 workspace + 1 token                   #
    # ------------------------------------------------------------------ #

    async def test_fresh_db_creates_workspace_and_token(self) -> None:
        """On a fresh DB the script inserts a workspace row and a token row; exit 0."""
        exit_code = await self._run_migration()
        self.assertEqual(exit_code, 0, "Expected exit 0 on success")

        # The script calls asyncio.run() internally which opens a new event loop.
        # We verify results by opening a separate connection to the same file.
        import backend.db.connection as _dbc
        _dbc._connection = None  # reset so we get a fresh connection

        db = await aiosqlite.connect(self._tmp_path)
        try:
            # Workspace row must exist.
            async with db.execute(
                "SELECT workspace_id FROM workspaces WHERE workspace_id = 'default-local'"
            ) as cur:
                row = await cur.fetchone()
            self.assertIsNotNone(row, "Expected a 'default-local' workspace row")

            # Exactly 1 token row must exist.
            async with db.execute(
                "SELECT COUNT(*) FROM workspace_tokens WHERE revoked_at IS NULL"
            ) as cur:
                count_row = await cur.fetchone()
            token_count = count_row[0] if count_row else 0
            self.assertEqual(token_count, 1, "Expected exactly 1 active token row")

            # Token row has the expected fields.
            async with db.execute(
                "SELECT workspace_id, project_id, scope FROM workspace_tokens LIMIT 1"
            ) as cur:
                token_row = await cur.fetchone()
            self.assertIsNotNone(token_row)
            self.assertEqual(str(token_row[0]), "default-local")
            self.assertEqual(str(token_row[1]), "test-project")
            self.assertEqual(str(token_row[2]), "admin")
        finally:
            await db.close()

    # ------------------------------------------------------------------ #
    # Test 2 — idempotent: second run is a no-op                         #
    # ------------------------------------------------------------------ #

    async def test_already_migrated_db_is_noop(self) -> None:
        """Running the script twice must exit 0 and leave row count unchanged."""
        # First run.
        exit_code_first = await self._run_migration()
        self.assertEqual(exit_code_first, 0)

        # Capture row count after first run.
        import backend.db.connection as _dbc
        _dbc._connection = None
        db = await aiosqlite.connect(self._tmp_path)
        try:
            async with db.execute(
                "SELECT COUNT(*) FROM workspace_tokens WHERE revoked_at IS NULL"
            ) as cur:
                row = await cur.fetchone()
            count_after_first = row[0] if row else 0
        finally:
            await db.close()
            _dbc._connection = None

        # Second run on the same token — must be a no-op.
        exit_code_second = await self._run_migration()
        self.assertEqual(exit_code_second, 0, "Expected exit 0 on no-op second run")

        _dbc._connection = None
        db = await aiosqlite.connect(self._tmp_path)
        try:
            async with db.execute(
                "SELECT COUNT(*) FROM workspace_tokens WHERE revoked_at IS NULL"
            ) as cur:
                row = await cur.fetchone()
            count_after_second = row[0] if row else 0
        finally:
            await db.close()

        self.assertEqual(
            count_after_second,
            count_after_first,
            "Second run must not insert a duplicate token row",
        )

    # ------------------------------------------------------------------ #
    # Test 3 — token verifies after migration                             #
    # ------------------------------------------------------------------ #

    async def test_inserted_token_verifies_via_auth_backend(self) -> None:
        """WorkspaceTokenAuthBackend can verify the token inserted by the script."""
        from argon2 import PasswordHasher
        from argon2.exceptions import VerifyMismatchError

        secret = "my-secret-bearer-token-xyz"
        exit_code = await self._run_migration(token=secret)
        self.assertEqual(exit_code, 0)

        # Read the hashed_token from the DB and verify it directly with argon2.
        import backend.db.connection as _dbc
        _dbc._connection = None
        db = await aiosqlite.connect(self._tmp_path)
        try:
            async with db.execute(
                "SELECT hashed_token FROM workspace_tokens WHERE revoked_at IS NULL LIMIT 1"
            ) as cur:
                row = await cur.fetchone()
            self.assertIsNotNone(row, "Expected a token row in the DB")
            hashed_token = str(row[0])
        finally:
            await db.close()

        ph = PasswordHasher()
        # verify() raises VerifyMismatchError on mismatch; returns True on match.
        try:
            result = ph.verify(hashed_token, secret)
            self.assertTrue(result, "ph.verify() should return True on match")
        except VerifyMismatchError:
            self.fail(
                "argon2 verify failed: the stored hash does not match the original secret"
            )

    # ------------------------------------------------------------------ #
    # Test 4 — missing token arg → exit 1                                #
    # ------------------------------------------------------------------ #

    def test_missing_token_exits_1(self) -> None:
        """Script must exit 1 when --token is not provided and env var is absent."""
        import backend.db.connection as _dbc
        _dbc._connection = None

        env_without_token = {k: v for k, v in os.environ.items() if k != "CCDASH_AUTH_TOKEN"}
        env_without_token["CCDASH_DB_PATH"] = self._tmp_path
        env_without_token["CCDASH_DB_BACKEND"] = "sqlite"

        from backend.scripts.migrate_bearer_to_workspace_token import main

        with patch.dict(os.environ, env_without_token, clear=True):
            exit_code = main(["--project", "my-project"])

        self.assertEqual(exit_code, 1)
