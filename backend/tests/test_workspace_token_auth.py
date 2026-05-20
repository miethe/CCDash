"""Tests for WorkspaceTokenAuthBackend and AuthContext.

Coverage:
- Valid bearer returns AuthContext with correct fields.
- Unknown bearer -> None (mapped to 401 invalid_token by dependency layer).
- Revoked token -> None (cache eviction path).
- x-ccdash-project-id matching token's project -> passes equality assertion.
- x-ccdash-project-id mismatching -> 403 workspace_project_mismatch.
- LRU cache: first call argon2-verifies; second call within TTL skips argon2.
- Revoking between two calls invalidates the cache entry.
- last_used_at is updated asynchronously.
- AuthContext.synthesize_local produces the expected sentinel values.
- argon2 verify cost sanity check (marked @pytest.mark.slow).
"""
from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from argon2 import PasswordHasher

from backend.adapters.auth.context import AuthContext
from backend.adapters.auth.workspace_token import WorkspaceTokenAuthBackend, _fingerprint


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


async def _make_db_with_tokens(tokens: list[dict]) -> aiosqlite.Connection:
    """Create an in-memory SQLite DB with workspace_tokens rows."""
    db = await aiosqlite.connect(":memory:")
    await db.execute(
        """
        CREATE TABLE workspace_tokens (
            token_id     TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            project_id   TEXT NOT NULL,
            hashed_token TEXT NOT NULL UNIQUE,
            scope        TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            last_used_at TEXT,
            revoked_at   TEXT,
            description  TEXT
        )
        """
    )
    ph = PasswordHasher()
    for t in tokens:
        hashed = ph.hash(t["secret"])
        await db.execute(
            """
            INSERT INTO workspace_tokens
                (token_id, workspace_id, project_id, hashed_token, scope, created_at, revoked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                t["token_id"],
                t["workspace_id"],
                t["project_id"],
                hashed,
                t.get("scope", "admin"),
                "2026-01-01T00:00:00Z",
                t.get("revoked_at", None),
            ),
        )
    await db.commit()
    return db


def _make_backend(db: aiosqlite.Connection) -> WorkspaceTokenAuthBackend:
    async def get_db():
        return db

    return WorkspaceTokenAuthBackend(get_db=get_db)


# --------------------------------------------------------------------------- #
# AuthContext unit tests                                                        #
# --------------------------------------------------------------------------- #


class TestAuthContextSynthesizeLocal(unittest.TestCase):
    def test_synthesize_local_returns_correct_fields(self) -> None:
        ctx = AuthContext.synthesize_local("my-project")
        self.assertEqual(ctx.workspace_id, "default-local")
        self.assertEqual(ctx.project_id, "my-project")
        self.assertEqual(ctx.token_id, "local-bearer")
        self.assertEqual(ctx.scope, "admin")

    def test_synthesize_local_is_hashable(self) -> None:
        ctx = AuthContext.synthesize_local("proj-1")
        # frozen dataclass is hashable
        _ = {ctx}

    def test_synthesize_local_is_frozen(self) -> None:
        ctx = AuthContext.synthesize_local("proj-1")
        with self.assertRaises((AttributeError, TypeError)):
            ctx.workspace_id = "other"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# WorkspaceTokenAuthBackend async tests                                         #
# --------------------------------------------------------------------------- #


class TestWorkspaceTokenAuthBackend(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self) -> None:
        self.db = await _make_db_with_tokens(
            [
                {
                    "token_id": "tok-alpha",
                    "workspace_id": "ws-alpha",
                    "project_id": "proj-alpha",
                    "secret": "secret-alpha",
                    "scope": "admin",
                },
                {
                    "token_id": "tok-beta",
                    "workspace_id": "ws-beta",
                    "project_id": "proj-beta",
                    "secret": "secret-beta",
                    "scope": "ingest_write",
                },
            ]
        )
        self.backend = _make_backend(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # --- Valid token -------------------------------------------------------- #

    async def test_valid_bearer_returns_correct_auth_context(self) -> None:
        ctx = await self.backend.verify("secret-alpha")
        self.assertIsNotNone(ctx)
        assert ctx is not None
        self.assertEqual(ctx.workspace_id, "ws-alpha")
        self.assertEqual(ctx.project_id, "proj-alpha")
        self.assertEqual(ctx.token_id, "tok-alpha")
        self.assertEqual(ctx.scope, "admin")

    async def test_valid_bearer_second_token_returns_correct_auth_context(self) -> None:
        ctx = await self.backend.verify("secret-beta")
        self.assertIsNotNone(ctx)
        assert ctx is not None
        self.assertEqual(ctx.workspace_id, "ws-beta")
        self.assertEqual(ctx.token_id, "tok-beta")
        self.assertEqual(ctx.scope, "ingest_write")

    # --- Unknown token ------------------------------------------------------ #

    async def test_unknown_bearer_returns_none(self) -> None:
        ctx = await self.backend.verify("completely-unknown-secret")
        self.assertIsNone(ctx)

    async def test_empty_bearer_returns_none(self) -> None:
        ctx = await self.backend.verify("")
        self.assertIsNone(ctx)

    # --- Revoked token ------------------------------------------------------- #

    async def test_revoked_token_returns_none(self) -> None:
        """A token whose revoked_at is set should return None."""
        db = await _make_db_with_tokens(
            [
                {
                    "token_id": "tok-revoked",
                    "workspace_id": "ws-x",
                    "project_id": "proj-x",
                    "secret": "secret-revoked",
                    "scope": "admin",
                    "revoked_at": "2026-01-02T00:00:00Z",
                }
            ]
        )
        backend = _make_backend(db)
        ctx = await backend.verify("secret-revoked")
        self.assertIsNone(ctx)
        await db.close()

    async def test_revoke_between_two_calls_invalidates_cache(self) -> None:
        """Verify call 1 succeeds; revoke token; call 2 should return None."""
        # First call: should succeed and populate LRU.
        ctx1 = await self.backend.verify("secret-alpha")
        self.assertIsNotNone(ctx1)

        # Revoke the token in the DB.
        await self.db.execute(
            "UPDATE workspace_tokens SET revoked_at = datetime('now') WHERE token_id = 'tok-alpha'"
        )
        await self.db.commit()

        # Second call: LRU hit but revocation re-check must catch the revocation.
        ctx2 = await self.backend.verify("secret-alpha")
        self.assertIsNone(ctx2)

    # --- LRU cache ---------------------------------------------------------- #

    async def test_lru_cache_skip_argon2_on_second_call(self) -> None:
        """Second verify call within TTL should not re-invoke argon2 verify."""
        ph_mock = MagicMock(spec=PasswordHasher)
        ph_mock.verify.return_value = True

        # First call: populate cache.
        ctx1 = await self.backend.verify("secret-alpha")
        self.assertIsNotNone(ctx1)

        # Patch the PasswordHasher on the backend AFTER the first call.
        original_ph = self.backend._ph
        self.backend._ph = ph_mock

        # Second call: should hit LRU and not call ph.verify.
        ctx2 = await self.backend.verify("secret-alpha")
        self.assertIsNotNone(ctx2)
        self.assertEqual(ctx1, ctx2)
        ph_mock.verify.assert_not_called()

        # Restore.
        self.backend._ph = original_ph

    # --- last_used_at ------------------------------------------------------- #

    async def test_last_used_at_is_updated_after_verify(self) -> None:
        """last_used_at is updated asynchronously; assert via asyncio.sleep."""
        ctx = await self.backend.verify("secret-alpha")
        self.assertIsNotNone(ctx)

        # Allow the fire-and-forget task to complete.
        await asyncio.sleep(0.05)

        async with self.db.execute(
            "SELECT last_used_at FROM workspace_tokens WHERE token_id = 'tok-alpha'"
        ) as cur:
            row = await cur.fetchone()

        self.assertIsNotNone(row)
        self.assertIsNotNone(row[0], "last_used_at should be set after a successful verify")

    # --- invalidate / invalidate_token -------------------------------------- #

    async def test_invalidate_clears_lru_and_forces_snapshot_reload(self) -> None:
        # Warm the cache.
        ctx1 = await self.backend.verify("secret-alpha")
        self.assertIsNotNone(ctx1)
        fp = _fingerprint("secret-alpha")
        self.assertIn(fp, self.backend._lru)

        # Invalidate.
        self.backend.invalidate()
        self.assertNotIn(fp, self.backend._lru)
        # snapshot_loaded_at should be reset.
        self.assertEqual(self.backend._snapshot_loaded_at, 0.0)

    async def test_invalidate_token_evicts_only_target(self) -> None:
        await self.backend.verify("secret-alpha")
        await self.backend.verify("secret-beta")
        fp_a = _fingerprint("secret-alpha")
        fp_b = _fingerprint("secret-beta")

        self.backend.invalidate_token("tok-alpha")

        self.assertNotIn(fp_a, self.backend._lru)
        self.assertIn(fp_b, self.backend._lru)


# --------------------------------------------------------------------------- #
# x-ccdash-project-id assertion tests (via dependency layer)                   #
# --------------------------------------------------------------------------- #


class TestAuthContextProjectIdAssertion(unittest.IsolatedAsyncioTestCase):
    """Tests for the dependency-level project-id header assertion.

    These tests exercise get_auth_context directly by constructing a mock
    Request and wiring a WorkspaceTokenAuthBackend via manual dependency
    injection.
    """

    async def asyncSetUp(self) -> None:
        self.db = await _make_db_with_tokens(
            [
                {
                    "token_id": "tok-proj-a",
                    "workspace_id": "ws-a",
                    "project_id": "proj-a",
                    "secret": "secret-proj-a",
                    "scope": "admin",
                },
            ]
        )
        self.backend = _make_backend(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_matching_project_id_header_passes(self) -> None:
        """x-ccdash-project-id == token's project_id: should not raise."""
        from fastapi import HTTPException
        from backend.adapters.auth.dependency import get_auth_context

        request = MagicMock()
        request.state = MagicMock()
        request.state.auth_context = None
        type(request.state).auth_context = property(lambda s: None, lambda s, v: None)
        # Simulate attribute access returning None for the cached context.
        object.__setattr__(request, "state", type("State", (), {"auth_context": None})())
        request.headers = {
            "authorization": "Bearer secret-proj-a",
            "x-ccdash-project-id": "proj-a",
        }

        ctx = await get_auth_context(request=request, backend=self.backend)
        self.assertEqual(ctx.project_id, "proj-a")

    async def test_mismatching_project_id_header_raises_403(self) -> None:
        """x-ccdash-project-id != token's project_id: 403 workspace_project_mismatch."""
        from fastapi import HTTPException
        from backend.adapters.auth.dependency import get_auth_context

        request = MagicMock()
        object.__setattr__(request, "state", type("State", (), {"auth_context": None})())
        request.headers = {
            "authorization": "Bearer secret-proj-a",
            "x-ccdash-project-id": "proj-OTHER",
        }

        with self.assertRaises(HTTPException) as cm:
            await get_auth_context(request=request, backend=self.backend)

        exc = cm.exception
        self.assertEqual(exc.status_code, 403)
        self.assertEqual(exc.detail["code"], "workspace_project_mismatch")

    async def test_missing_bearer_raises_401_invalid_token(self) -> None:
        from fastapi import HTTPException
        from backend.adapters.auth.dependency import get_auth_context

        request = MagicMock()
        object.__setattr__(request, "state", type("State", (), {"auth_context": None})())
        request.headers = {}

        with self.assertRaises(HTTPException) as cm:
            await get_auth_context(request=request, backend=self.backend)

        exc = cm.exception
        self.assertEqual(exc.status_code, 401)
        self.assertEqual(exc.detail["code"], "invalid_token")


# --------------------------------------------------------------------------- #
# Argon2 verify cost sanity benchmark                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.slow
class TestArgon2VerifyCostSanity(unittest.IsolatedAsyncioTestCase):
    """Argon2 verify cost sanity benchmark.

    Marked @pytest.mark.slow so CI can gate on this separately.
    This is a sanity check, not a hard gate.  With default argon2id parameters
    (~100-300ms per verify) and 10 tokens (worst-case = all 10 checked), the
    total should stay under 5s on any reasonably modern machine.
    """

    async def test_argon2_verify_cost_with_10_tokens(self) -> None:
        """Verifying 10 tokens stays under 5s (generous upper bound)."""
        tokens = [
            {
                "token_id": f"tok-{i}",
                "workspace_id": f"ws-{i}",
                "project_id": f"proj-{i}",
                "secret": f"secret-{i}",
                "scope": "admin",
            }
            for i in range(10)
        ]
        # Put the matching token last (worst case).
        target_secret = "secret-9"

        db = await _make_db_with_tokens(tokens)
        backend = _make_backend(db)

        start = time.perf_counter()
        ctx = await backend.verify(target_secret)
        elapsed = time.perf_counter() - start

        await db.close()

        self.assertIsNotNone(ctx, "Should have found a matching token")
        assert ctx is not None
        self.assertEqual(ctx.token_id, "tok-9")
        self.assertLess(
            elapsed,
            5.0,
            f"argon2 verify over 10 tokens took {elapsed:.2f}s (>5s)",
        )
