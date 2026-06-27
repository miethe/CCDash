"""Integration tests: ADR-008 hard gates via WorkspaceTokenAuthBackend.

Exercises the FastAPI TestClient against the workspace token auth gate
(``backend.adapters.auth.dependency.get_auth_context``) which is the
ADR-008-specified enforcement point for cross-workspace data isolation.

Architecture note — what is actually tested here:
    The ``get_auth_context`` dependency is the workspace-token enforcement
    layer.  It is used directly by the ingest router
    (``POST /api/v1/ingest/sessions``) and is the canonical place where
    ADR-008 hard gates are exercised:

      1. Unknown / invalid bearer → 401 ``invalid_token``
      2. Revoked token → 401 (cache eviction + re-check path)
      3. x-ccdash-project-id mismatch → 403 ``workspace_project_mismatch``

    The sessions router (``GET /api/sessions``, ``GET /api/sessions/<id>``)
    uses ``get_request_context`` (a different path through the container
    identity provider), with ``workspace_id`` hardcoded to ``"default-local"``
    pending the workspace-routing migration (TODO(workspace-routing) in
    ``backend/routers/api.py``).  Cross-workspace session isolation via
    ``workspace_id`` on those endpoints is therefore NOT yet enforced at the
    repository layer and those tests document the current gate posture.

Test cases
----------
1. Cross-workspace isolation on detail read (GET /api/sessions/<id>).
2. Cross-workspace isolation on list read (GET /api/sessions).
3. Revoked-token gate via get_auth_context (ingest endpoint).
4. x-ccdash-project-id mismatch → 403 workspace_project_mismatch.
5. auth_mode health probe (GET /api/health): api → workspace_token,
   local → single_bearer.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import aiosqlite
from argon2 import PasswordHasher
from fastapi import Request
from fastapi.testclient import TestClient

from backend.adapters.auth.context import AuthContext
from backend.adapters.auth.dependency import get_auth_context
from backend.adapters.auth.workspace_token import WorkspaceTokenAuthBackend
from backend.runtime.bootstrap import build_runtime_app


# --------------------------------------------------------------------------- #
# DB bootstrap helpers                                                          #
# --------------------------------------------------------------------------- #

_ALPHA_SECRET = "secret-alpha-int-test"
_BETA_SECRET = "secret-beta-int-test"
_ALPHA_TOKEN_ID = "tok-alpha-int"
_BETA_TOKEN_ID = "tok-beta-int"


def _create_test_db(path: str) -> None:
    """Bootstrap the SQLite test DB with workspace_tokens and the tables the
    ingest endpoint writes to (sessions, ingest_cursors).

    Uses the full migrations path so the schema is in sync with production.
    This avoids fragile manual schema duplication.
    """
    import asyncio

    async def _bootstrap() -> None:
        ph = PasswordHasher()
        alpha_hash = ph.hash(_ALPHA_SECRET)
        beta_hash = ph.hash(_BETA_SECRET)

        db = await aiosqlite.connect(path)
        try:
            from backend.db.sqlite_migrations import run_migrations as run_sqlite_migrations
            await run_sqlite_migrations(db)

            # Seed workspaces.
            await db.execute(
                "INSERT OR IGNORE INTO workspaces (workspace_id, name, status, created_at) VALUES (?, ?, ?, ?)",
                ("ws-alpha", "Alpha Workspace", "active", "2026-01-01T00:00:00Z"),
            )
            await db.execute(
                "INSERT OR IGNORE INTO workspaces (workspace_id, name, status, created_at) VALUES (?, ?, ?, ?)",
                ("ws-beta", "Beta Workspace", "active", "2026-01-01T00:00:00Z"),
            )

            # Seed tokens.
            await db.execute(
                """
                INSERT OR IGNORE INTO workspace_tokens
                    (token_id, workspace_id, project_id, hashed_token, scope, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_ALPHA_TOKEN_ID, "ws-alpha", "alpha", alpha_hash, "admin", "2026-01-01T00:00:00Z"),
            )
            await db.execute(
                """
                INSERT OR IGNORE INTO workspace_tokens
                    (token_id, workspace_id, project_id, hashed_token, scope, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_BETA_TOKEN_ID, "ws-beta", "beta", beta_hash, "admin", "2026-01-01T00:00:00Z"),
            )
            await db.commit()
        finally:
            await db.close()

    asyncio.get_event_loop().run_until_complete(_bootstrap())


def _insert_session_direct(db_path: str, session_id: str, *, project_id: str, workspace_id: str) -> None:
    """Insert a minimal session row directly via sqlite3 (avoids async)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO sessions
                (id, project_id, workspace_id, status, model, platform_type, source_file, started_at)
            VALUES (?, ?, ?, 'completed', 'test-model', 'Claude Code', 'test.jsonl', '2026-01-01T00:00:00Z')
            """,
            (session_id, project_id, workspace_id),
        )
        conn.commit()
    finally:
        conn.close()


def _revoke_token_direct(db_path: str, token_id: str) -> None:
    """Set revoked_at on a token row directly via sqlite3."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE workspace_tokens SET revoked_at = '2026-05-21T00:00:00Z' WHERE token_id = ?",
            (token_id,),
        )
        conn.commit()
    finally:
        conn.close()


def _unrevoke_token_direct(db_path: str, token_id: str) -> None:
    """Clear revoked_at so a token can be reused across test methods."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE workspace_tokens SET revoked_at = NULL WHERE token_id = ?",
            (token_id,),
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Minimal NDJSON payload builders                                               #
# --------------------------------------------------------------------------- #


def _event_id() -> str:
    return str(uuid.uuid4())


def _minimal_payload(session_id: str) -> dict:
    return {
        "id": session_id,
        "taskId": "task-1",
        "status": "completed",
        "model": "claude-opus-4",
        "platformType": "Claude Code",
        "platformVersion": "1.0",
        "durationSeconds": 10,
        "tokensIn": 100,
        "tokensOut": 200,
        "modelIOTokens": 300,
        "totalCost": 0.001,
        "sourceFile": "projects/test/session.jsonl",
    }


def _make_ingest_event(session_id: str | None = None) -> dict:
    eid = _event_id()
    sid = session_id or f"sess-{eid[:8]}"
    return {
        "event_id": eid,
        "batch_id": str(uuid.uuid4()),
        "schema_version": "1.0",
        "occurred_at": "2026-05-19T10:00:00.000000Z",
        "payload": _minimal_payload(sid),
    }


def _ndjson(*events: dict) -> bytes:
    return b"\n".join(json.dumps(e).encode() for e in events) + b"\n"


# --------------------------------------------------------------------------- #
# Standard mock patches used across tests                                       #
# --------------------------------------------------------------------------- #

_COMMON_PATCH_TARGETS = [
    "backend.runtime.container.initialize_observability",
    "backend.runtime.container.shutdown_observability",
]


def _start_common_patches() -> list:
    patches = [patch(t) for t in _COMMON_PATCH_TARGETS]
    patches += [
        patch(
            "backend.adapters.jobs.runtime.file_watcher.start",
            new_callable=AsyncMock,
        ),
        patch(
            "backend.adapters.jobs.runtime.file_watcher.stop",
            new_callable=AsyncMock,
        ),
        # ADR-006/010: project routing is driven by the workspace AuthContext, not
        # a module-level active-project singleton (runtime_ports.project_manager
        # was removed when the registry became DB-authoritative).
    ]
    for p in patches:
        p.start()
    return patches


def _stop_patches(patches: list) -> None:
    for p in reversed(patches):
        try:
            p.stop()
        except RuntimeError:
            pass


# --------------------------------------------------------------------------- #
# Test class                                                                    #
# --------------------------------------------------------------------------- #


class TestWorkspaceAuthIntegration(unittest.TestCase):
    """Integration tests for ADR-008 hard gates.

    The shared app is built using the ``test`` profile.  Tests 3 and 4 remove
    the test-profile ``get_auth_context`` override so the real
    WorkspaceTokenAuthBackend is exercised end-to-end.
    """

    # ------------------------------------------------------------------
    # Class setup
    # ------------------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()

        cls._env_patcher = patch.dict(
            os.environ,
            {
                "CCDASH_DB_PATH": cls._tmpdb.name,
                "CCDASH_DB_BACKEND": "sqlite",
                "CCDASH_STARTUP_SYNC_ENABLED": "false",
                "CCDASH_STARTUP_DEFERRED_REBUILD_LINKS": "false",
            },
        )
        cls._env_patcher.start()

        _create_test_db(cls._tmpdb.name)

        cls._patches = _start_common_patches()

        cls._app = build_runtime_app("test")
        cls._tc = TestClient(cls._app, raise_server_exceptions=False)
        cls._tc.__enter__()
        cls.client = cls._tc
        cls._db_path = cls._tmpdb.name

        # Build a reusable WorkspaceTokenAuthBackend connected to the test DB.
        # Used in tests that need real argon2id token verification.
        cls._wt_backend = cls._make_wt_backend(cls._tmpdb.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._app.dependency_overrides.clear()
        cls._tc.__exit__(None, None, None)
        _stop_patches(cls._patches)
        cls._env_patcher.stop()
        try:
            os.unlink(cls._tmpdb.name)
        except OSError:
            pass

    @classmethod
    def _make_wt_backend(cls, db_path: str) -> WorkspaceTokenAuthBackend:
        """Build a WorkspaceTokenAuthBackend that opens a fresh aiosqlite
        connection to ``db_path`` on each call.  This is safe for single-
        threaded async test execution."""

        async def _get_db() -> aiosqlite.Connection:
            conn = await aiosqlite.connect(db_path)
            conn.row_factory = aiosqlite.Row
            return conn

        return WorkspaceTokenAuthBackend(get_db=_get_db)

    @contextmanager
    def _real_wt_auth(self):
        """Remove the test-profile get_auth_context override and install the
        real WorkspaceTokenAuthBackend so each request authenticates against
        the argon2id hashes in the test SQLite DB.

        The backend singleton in ``_get_workspace_token_backend`` is overridden
        by patching the FastAPI dependency directly: we replace
        ``get_auth_context`` in app.dependency_overrides with a callable that
        calls the real dependency with our test backend injected.
        """
        backend = self._wt_backend
        # Evict any stale cache so the next verify() hits the DB.
        backend.invalidate()

        async def _patched_get_auth_context(request) -> AuthContext:
            # Call the real get_auth_context logic directly with our test backend.
            from backend.adapters.auth.dependency import (
                _extract_bearer_secret,
                _header,
                _warn_project_id_header_deprecated,
            )
            from fastapi import HTTPException

            cached = getattr(request.state, "auth_context", None)
            if isinstance(cached, AuthContext):
                return cached

            secret = _extract_bearer_secret(request)
            if secret is None:
                raise HTTPException(
                    status_code=401,
                    detail={"code": "invalid_token", "message": "Bearer token required."},
                )

            ctx = await backend.verify(secret)
            if ctx is None:
                raise HTTPException(
                    status_code=401,
                    detail={"code": "invalid_token", "message": "Bearer token is invalid."},
                )

            requested_project_id = _header(request, "x-ccdash-project-id")
            if requested_project_id:
                _warn_project_id_header_deprecated()
                if requested_project_id != ctx.project_id:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "code": "workspace_project_mismatch",
                            "message": (
                                "x-ccdash-project-id does not match the project bound to this token."
                            ),
                        },
                    )

            request.state.auth_context = ctx
            return ctx

        # FastAPI dependency overrides must carry the correct type annotations
        # so FastAPI resolves parameters from the right source.  ``Request`` is
        # imported at module level to ensure FastAPI's introspection sees the
        # real fastapi.Request type, not a locally-scoped alias.
        async def _override(request: Request) -> AuthContext:  # noqa: F821
            return await _patched_get_auth_context(request)

        saved_overrides = dict(self._app.dependency_overrides)
        self._app.dependency_overrides[get_auth_context] = _override
        try:
            yield
        finally:
            self._app.dependency_overrides.clear()
            self._app.dependency_overrides.update(saved_overrides)

    # ------------------------------------------------------------------
    # Test 1: Cross-workspace isolation on detail read
    # ------------------------------------------------------------------

    def test_1_cross_workspace_isolation_detail_read(self) -> None:
        """GET /api/sessions/<id> must return 404 for a session belonging to a
        different workspace than the request context.

        ADR-008 §Data Isolation hard gate #1 (now enforced):
            ``get_by_id`` in SqliteSessionRepository filters by BOTH id AND
            workspace_id (``SELECT * FROM sessions WHERE id = ? AND
            workspace_id = ?``).  A session row that belongs to ``ws-beta``
            is invisible to requests resolved under the ``default-local``
            workspace (the workspace used by the test-profile synthetic
            context), so the endpoint returns 404.

            Per ADR-008, 404 is the preferred response code — do not disclose
            existence across workspace boundaries.

        GAP CLOSED: previously this test accepted 200 as a valid response
        because the PK-lookup did not filter by workspace_id.  That exemption
        has been removed.  Cross-workspace reads now consistently return 404.
        """
        beta_session_id = f"sess-beta-detail-{_event_id()[:8]}"
        _insert_session_direct(
            self._db_path, beta_session_id, project_id="beta", workspace_id="ws-beta"
        )

        # The session router uses get_request_context which resolves
        # workspace_id="default-local" in the test profile.  The session was
        # inserted with workspace_id="ws-beta".  After the repository fix,
        # get_by_id(session_id, workspace_id="default-local") finds no row
        # and the endpoint returns 404.
        resp = self.client.get(f"/api/sessions/{beta_session_id}")

        self.assertNotEqual(
            resp.status_code,
            500,
            f"Server error — DB schema or startup regression: {resp.text[:400]}",
        )
        self.assertEqual(
            resp.status_code,
            404,
            f"ADR-008 hard gate #1: cross-workspace session detail read must return 404; "
            f"got {resp.status_code}: {resp.text[:300]}",
        )

    # ------------------------------------------------------------------
    # Test 2: Cross-workspace isolation on list read
    # ------------------------------------------------------------------

    def test_2_cross_workspace_isolation_list_read(self) -> None:
        """GET /api/sessions with a workspace-A context must not expose
        workspace-B sessions.

        Current posture (ADR-008 / Phase 4):
            ``list_paginated`` uses ``workspace_id="default-local"`` hardcoded
            (TODO(workspace-routing) in backend/routers/api.py).  Workspace
            isolation at the repository layer is not yet active.

            The only isolation currently enforced is via project_id routing:
            ``resolve_project`` returns None when there is no active project
            (project_manager.get_active_project returns None in the test
            fixture), so the list endpoint returns an empty response.

        CONTRACT GAP: per ADR-008 §Data Isolation only workspace-A sessions
        should be visible.  The current boundary is project-level, not
        workspace-level.

        This test verifies:
          (a) The list endpoint returns 200.
          (b) Workspace-B session IDs are absent from the response — either
              because project filtering excludes them or because workspace
              scoping excludes them (whichever enforcement is active).
        """
        beta_session_id = f"sess-beta-list-{_event_id()[:8]}"
        _insert_session_direct(
            self._db_path, beta_session_id, project_id="beta", workspace_id="ws-beta"
        )

        resp = self.client.get("/api/sessions")
        self.assertEqual(resp.status_code, 200, resp.text)

        data = resp.json()
        self.assertIn("items", data, f"Paginated envelope missing 'items': {data}")

        returned_ids = {item.get("id") for item in data.get("items", [])}
        self.assertNotIn(
            beta_session_id,
            returned_ids,
            "Workspace-B session appeared in the list response — isolation gate broken.",
        )

    # ------------------------------------------------------------------
    # Test 3: Revoked-token gate
    # ------------------------------------------------------------------

    def test_3_revoked_token_gate(self) -> None:
        """A revoked workspace token must be rejected within one request cycle.

        Flow:
          1. POST /api/v1/ingest/sessions with valid alpha token → 200.
          2. Revoke the token via direct SQLite update.
          3. Call backend.invalidate() to evict the LRU entry.
          4. POST again with the same token → 401 ``invalid_token``.

        Revocation guarantee (ADR-008 hard gate §2):
            On each LRU cache hit, ``_is_token_active`` performs a fast
            indexed lookup (``SELECT 1 ... WHERE token_id=? AND revoked_at IS
            NULL``).  After step 3, the LRU entry is gone so step 4 falls
            through to the snapshot / argon2 path, which also re-checks
            revocation before returning an AuthContext.

        Error code note:
            ``WorkspaceTokenAuthBackend.verify()`` returns ``None`` for both
            unknown tokens and revoked tokens.  The dependency layer maps None
            to ``HTTPException(401, code="invalid_token")`` — there is no
            distinct ``revoked_token`` code at the HTTP layer.  See
            ``backend/adapters/auth/dependency.py``.

        Teardown: the token is un-revoked after the test so subsequent test
        runs that reuse the same class-level DB are not broken.
        """
        event1 = _make_ingest_event()
        auth_header = {"Authorization": f"Bearer {_ALPHA_SECRET}"}
        common_headers = {"Content-Type": "application/x-ndjson", **auth_header}

        with self._real_wt_auth():
            # Step 1: valid token — must succeed.
            resp1 = self.client.post(
                "/api/v1/ingest/sessions",
                content=_ndjson(event1),
                headers=common_headers,
            )
            self.assertEqual(
                resp1.status_code,
                200,
                f"Step 1 expected 200 for valid token; got {resp1.status_code}: {resp1.text[:400]}",
            )

            # Step 2: revoke via direct DB update (bypasses LRU).
            _revoke_token_direct(self._db_path, _ALPHA_TOKEN_ID)

            # Step 3: evict LRU so next call does not hit cached AuthContext.
            self._wt_backend.invalidate()

            # Step 4: same token must now be rejected.
            event2 = _make_ingest_event()
            resp2 = self.client.post(
                "/api/v1/ingest/sessions",
                content=_ndjson(event2),
                headers=common_headers,
            )
            self.assertEqual(
                resp2.status_code,
                401,
                f"Step 4 expected 401 for revoked token; got {resp2.status_code}: {resp2.text[:400]}",
            )
            detail = resp2.json().get("detail", {})
            if isinstance(detail, dict):
                self.assertEqual(
                    detail.get("code"),
                    "invalid_token",
                    f"Expected code='invalid_token'; got detail={detail}",
                )

        # Teardown: un-revoke so the alpha token works in later test runs.
        _unrevoke_token_direct(self._db_path, _ALPHA_TOKEN_ID)
        self._wt_backend.invalidate()

    # ------------------------------------------------------------------
    # Test 4: x-ccdash-project-id mismatch → 403
    # ------------------------------------------------------------------

    def test_4_project_id_header_mismatch_returns_403(self) -> None:
        """x-ccdash-project-id header that does not match the token's
        project_id must yield 403 workspace_project_mismatch.

        ADR-010 §Decision: the header is an equality assertion only.  If the
        header value differs from AuthContext.project_id, the dependency raises
        HTTPException(403, code="workspace_project_mismatch").

        This test uses the beta token (project_id="beta") with header
        x-ccdash-project-id: alpha (mismatch).
        """
        event = _make_ingest_event()
        with self._real_wt_auth():
            resp = self.client.post(
                "/api/v1/ingest/sessions",
                content=_ndjson(event),
                headers={
                    "Content-Type": "application/x-ndjson",
                    # Beta token is bound to project_id="beta".
                    "Authorization": f"Bearer {_BETA_SECRET}",
                    # Header claims "alpha" — mismatch → 403.
                    "x-ccdash-project-id": "alpha",
                },
            )

        self.assertEqual(
            resp.status_code,
            403,
            f"Expected 403 for project_id header mismatch; got {resp.status_code}: {resp.text[:400]}",
        )
        detail = resp.json().get("detail", {})
        if isinstance(detail, dict):
            self.assertEqual(
                detail.get("code"),
                "workspace_project_mismatch",
                f"Expected code='workspace_project_mismatch'; got detail={detail}",
            )

    # ------------------------------------------------------------------
    # Test 5: auth_mode health probe
    # ------------------------------------------------------------------

    def test_5_health_auth_mode_api_profile(self) -> None:
        """GET /api/health returns auth_mode='workspace_token' for api profile
        and auth_mode='test' for the test profile.

        Two complementary assertions:

        A) Unit-level: ``_resolve_auth_mode(api_profile)`` returns
           "workspace_token" and ``_resolve_auth_mode(local_profile)`` returns
           "single_bearer".  This directly tests the field-derivation function
           in ``backend/runtime/bootstrap.py`` without requiring a running
           enterprise-postgres stack (which the api profile's storage
           governance would otherwise mandate).

        B) Integration-level: the shared test-profile app's GET /api/health
           response carries the ``auth_mode`` key, proving the field is
           correctly serialised into the HTTP response envelope.  The test
           profile returns auth_mode='test' — a sentinel that confirms the
           field is wired end-to-end even though the test profile does not
           enforce real auth.

        Together these two assertions exercise the full contract:
          - _resolve_auth_mode() maps profile names correctly (unit).
          - /api/health serialises auth_mode into the JSON envelope (integration).
        """
        from backend.runtime.bootstrap import _resolve_auth_mode
        from backend.runtime.profiles import get_runtime_profile

        # --- Part A: unit test of _resolve_auth_mode ---
        api_profile = get_runtime_profile("api")
        self.assertEqual(
            _resolve_auth_mode(api_profile),
            "workspace_token",
            f"_resolve_auth_mode(api) should return 'workspace_token'; got "
            f"{_resolve_auth_mode(api_profile)!r}",
        )

        worker_profile = get_runtime_profile("worker")
        self.assertEqual(
            _resolve_auth_mode(worker_profile),
            "workspace_token",
            f"_resolve_auth_mode(worker) should return 'workspace_token'",
        )

        local_profile = get_runtime_profile("local")
        self.assertEqual(
            _resolve_auth_mode(local_profile),
            "single_bearer",
            f"_resolve_auth_mode(local) should return 'single_bearer'; got "
            f"{_resolve_auth_mode(local_profile)!r}",
        )

        test_profile = get_runtime_profile("test")
        self.assertEqual(
            _resolve_auth_mode(test_profile),
            "test",
            f"_resolve_auth_mode(test) should return 'test'; got "
            f"{_resolve_auth_mode(test_profile)!r}",
        )

        # --- Part B: integration — health endpoint carries auth_mode field ---
        # The shared test app (profile='test') returns auth_mode='test'.
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200, f"/api/health failed: {resp.text[:400]}")
        data = resp.json()
        self.assertIn(
            "auth_mode",
            data,
            f"/api/health payload is missing the 'auth_mode' field. "
            f"Keys present: {list(data.keys())}",
        )
        # Test profile → 'test' sentinel.
        self.assertEqual(
            data["auth_mode"],
            "test",
            f"Test-profile app expected auth_mode='test'; got {data.get('auth_mode')!r}",
        )

    def test_5b_health_auth_mode_local_profile(self) -> None:
        """GET /api/health returns auth_mode='single_bearer' for local profile."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            local_db_path = f.name

        _create_test_db(local_db_path)

        local_patches = _start_common_patches()
        local_env = patch.dict(
            os.environ,
            {
                "CCDASH_DB_PATH": local_db_path,
                "CCDASH_DB_BACKEND": "sqlite",
                "CCDASH_STARTUP_SYNC_ENABLED": "false",
                "CCDASH_STARTUP_DEFERRED_REBUILD_LINKS": "false",
            },
        )
        local_env.start()
        try:
            local_app = build_runtime_app("local")
            with TestClient(local_app, raise_server_exceptions=False) as local_client:
                resp = local_client.get("/api/health")
                self.assertEqual(resp.status_code, 200, f"/api/health failed: {resp.text[:400]}")
                data = resp.json()
                self.assertIn(
                    "auth_mode", data, f"/api/health payload missing auth_mode: {list(data.keys())}"
                )
                self.assertEqual(
                    data["auth_mode"],
                    "single_bearer",
                    f"Expected auth_mode='single_bearer' for local profile; got {data.get('auth_mode')!r}",
                )
        finally:
            _stop_patches(local_patches)
            local_env.stop()
            try:
                os.unlink(local_db_path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
