"""Contract tests for POST /api/v1/ingest/sessions.

Covers all seven cases from T3-006:
  (a) happy path — 3-event NDJSON batch → 200 with accepted=3
  (b) dedup — same event_id replayed → second call accepted=1, no duplicate row
  (c) partial failure — mix valid + invalid event → 200 with accepted + rejected
  (d) batch limit — 501 events → 413 with reason "batch_limit_exceeded"
  (e) schema_version forward-compat — unknown top-level field still accepted
  (f) auth — missing/invalid Bearer → 401
  (g) cursor — ingest_cursors row advances to last accepted event_id

Setup mirrors backend/tests/test_client_v1_contract.py:
  tempfile SQLite DB + build_runtime_app("test") + TestClient context.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.adapters.auth import StaticBearerTokenIdentityProvider
from backend.adapters.auth.context import AuthContext
from backend.adapters.auth.dependency import get_auth_context
from backend.application.ports import CorePorts
from backend.runtime.bootstrap import build_runtime_app
from backend.runtime.profiles import get_runtime_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event_id() -> str:
    """Generate a UUID4 string suitable for tests (UUID7 is daemon-side only)."""
    return str(uuid.uuid4())


def _minimal_payload(session_id: str) -> dict:
    """Minimal session payload that passes SqliteSessionRepository.upsert()."""
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
        "sourceFile": "projects/my-proj/session.jsonl",
    }


def _make_event(event_id: str | None = None, session_id: str | None = None, **extra) -> dict:
    """Return a dict representing one IngestSessionEvent."""
    eid = event_id or _event_id()
    sid = session_id or f"sess-{eid[:8]}"
    obj = {
        "event_id": eid,
        "batch_id": str(uuid.uuid4()),
        "schema_version": "1.0",
        "occurred_at": "2026-05-19T10:00:00.000000Z",
        "payload": _minimal_payload(sid),
    }
    obj.update(extra)
    return obj


def _ndjson(*events: dict) -> bytes:
    """Encode a sequence of dicts as NDJSON bytes."""
    return b"\n".join(json.dumps(e).encode() for e in events) + b"\n"


_DEFAULT_HEADERS = {
    "Content-Type": "application/x-ndjson",
    "x-ccdash-project-id": "test-project",
}


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestIngestEndpoint(unittest.TestCase):
    """Integration tests for POST /api/v1/ingest/sessions."""

    # ------------------------------------------------------------------
    # Class-level setup — one app + TestClient shared across all tests
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
            },
        )
        cls._env_patcher.start()

        cls._app = build_runtime_app("test")

        cls._patches = [
            patch("backend.runtime.container.initialize_observability"),
            patch("backend.runtime.container.shutdown_observability"),
            patch(
                "backend.adapters.jobs.runtime.file_watcher.start",
                new_callable=lambda: lambda: AsyncMock(),
            ),
            patch(
                "backend.adapters.jobs.runtime.file_watcher.stop",
                new_callable=lambda: lambda: AsyncMock(),
            ),
            patch(
                "backend.runtime_ports.project_manager.get_active_project",
                return_value=None,
            ),
        ]
        for p in cls._patches:
            p.start()

        cls._app.dependency_overrides[get_auth_context] = lambda: AuthContext.synthesize_local(project_id="test-project")

        cls._tc = TestClient(cls._app, raise_server_exceptions=False)
        cls._tc.__enter__()
        cls.client = cls._tc

    @classmethod
    def tearDownClass(cls) -> None:
        cls._app.dependency_overrides.clear()
        cls._tc.__exit__(None, None, None)
        for p in reversed(cls._patches):
            p.stop()
        cls._env_patcher.stop()
        try:
            os.unlink(cls._tmpdb.name)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Helper: switch app to API-profile bearer auth
    # ------------------------------------------------------------------

    def _api_bearer_auth_enabled(self, token: str = "test-bearer"):
        """Context manager: temporarily enable bearer auth (mirrors client_v1 tests)."""
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            container = self._app.state.runtime_container
            original_profile = container.profile
            original_runtime_profile = self._app.state.runtime_profile
            original_app_ports = self._app.state.core_ports
            original_container_ports = container.ports

            auth_ports = CorePorts(
                identity_provider=StaticBearerTokenIdentityProvider(),
                authorization_policy=original_app_ports.authorization_policy,
                workspace_registry=original_app_ports.workspace_registry,
                storage=original_app_ports.storage,
                job_scheduler=original_app_ports.job_scheduler,
                integration_client=original_app_ports.integration_client,
            )
            container.profile = get_runtime_profile("api")
            self._app.state.runtime_profile = container.profile
            self._app.state.core_ports = auth_ports
            container.ports = auth_ports
            # Temporarily remove the test-profile auth override so real auth runs.
            saved_overrides = dict(self._app.dependency_overrides)
            self._app.dependency_overrides.pop(get_auth_context, None)
            try:
                with patch.dict(os.environ, {"CCDASH_API_BEARER_TOKEN": token}):
                    yield
            finally:
                container.profile = original_profile
                self._app.state.runtime_profile = original_runtime_profile
                self._app.state.core_ports = original_app_ports
                container.ports = original_container_ports
                self._app.dependency_overrides.update(saved_overrides)

        return _ctx()

    # ------------------------------------------------------------------
    # Helpers: sync DB queries against the test SQLite file
    # ------------------------------------------------------------------

    def _count_sessions_by_source_ref(self, source_ref: str) -> int:
        """Count rows where source_ref matches exactly."""
        import sqlite3

        # The app uses CCDASH_DB_PATH env var.  We read it from the connection
        # module that already has it expanded.
        from backend.db.connection import DB_PATH

        conn = sqlite3.connect(str(DB_PATH))
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE source_ref = ?",
                (source_ref,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    def _get_cursor_value(self, project_id: str, workspace_id: str = "default") -> str | None:
        """Return last_cursor from ingest_cursors for (remote_ingest, project_id, workspace_id)."""
        import sqlite3

        from backend.db.connection import DB_PATH

        conn = sqlite3.connect(str(DB_PATH))
        try:
            cur = conn.execute(
                """
                SELECT last_cursor FROM ingest_cursors
                WHERE source_id = 'remote_ingest'
                  AND project_id = ?
                  AND workspace_id = ?
                """,
                (project_id, workspace_id),
            )
            row = cur.fetchone()
            return str(row[0]) if row and row[0] is not None else None
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # (a) Happy path: 3-event batch → 200, accepted=3
    # ------------------------------------------------------------------

    def test_a_happy_path_three_events_accepted(self) -> None:
        events = [_make_event() for _ in range(3)]
        body = _ndjson(*events)

        resp = self.client.post(
            "/api/v1/ingest/sessions",
            content=body,
            headers=_DEFAULT_HEADERS,
        )

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["accepted"], 3, data)
        self.assertEqual(data["rejected"], [], data)
        self.assertEqual(data["dead_lettered"], [], data)

    # ------------------------------------------------------------------
    # (b) Dedup: same event_id replayed → accepted=1, no duplicate row
    # ------------------------------------------------------------------

    def test_b_dedup_same_event_id_not_duplicated(self) -> None:
        event_id = _event_id()
        session_id = f"sess-dedup-{event_id[:8]}"
        event = _make_event(event_id=event_id, session_id=session_id)

        # First POST — should be accepted.
        resp1 = self.client.post(
            "/api/v1/ingest/sessions",
            content=_ndjson(event),
            headers=_DEFAULT_HEADERS,
        )
        self.assertEqual(resp1.status_code, 200, resp1.text)
        data1 = resp1.json()
        self.assertEqual(data1["accepted"], 1, data1)

        # Second POST with identical event — accepted count still 1 (idempotent),
        # but no duplicate session row must exist.
        resp2 = self.client.post(
            "/api/v1/ingest/sessions",
            content=_ndjson(event),
            headers=_DEFAULT_HEADERS,
        )
        self.assertEqual(resp2.status_code, 200, resp2.text)
        data2 = resp2.json()
        self.assertEqual(data2["accepted"], 1, data2)

        # Assert exactly one row with the remote: source_ref for this event_id.
        source_ref = f"remote:{event_id}"
        count = self._count_sessions_by_source_ref(source_ref)
        self.assertEqual(count, 1, f"Expected 1 session row for {source_ref!r}, got {count}")

    # ------------------------------------------------------------------
    # (c) Partial failure: valid + invalid event → 200, accepted + rejected
    # ------------------------------------------------------------------

    def test_c_partial_failure_valid_and_invalid_event(self) -> None:
        valid_event = _make_event()
        invalid_line = b'{"not_an_ingest_event": true, "missing_required_fields": 1}'

        body = json.dumps(valid_event).encode() + b"\n" + invalid_line + b"\n"

        resp = self.client.post(
            "/api/v1/ingest/sessions",
            content=body,
            headers=_DEFAULT_HEADERS,
        )

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["accepted"], 1, data)
        self.assertEqual(len(data["rejected"]), 1, data)
        self.assertEqual(data["rejected"][0]["code"], "invalid_event", data)

    # ------------------------------------------------------------------
    # (d) Batch limit: 501 events → 413 with batch_limit_exceeded
    # ------------------------------------------------------------------

    def test_d_batch_limit_exceeded_returns_413(self) -> None:
        from backend.application.services.ingest.session_ingest import MAX_EVENTS_PER_BATCH

        # Build MAX+1 events.
        events = [_make_event() for _ in range(MAX_EVENTS_PER_BATCH + 1)]
        body = _ndjson(*events)

        resp = self.client.post(
            "/api/v1/ingest/sessions",
            content=body,
            headers=_DEFAULT_HEADERS,
        )

        self.assertEqual(resp.status_code, 413, resp.text)
        data = resp.json()
        self.assertGreaterEqual(data["accepted"], 0, data)
        self.assertEqual(len(data["dead_lettered"]), 1, data)
        self.assertEqual(data["dead_lettered"][0]["code"], "batch_too_large", data)
        self.assertEqual(data["dead_lettered"][0]["reason"], "batch_limit_exceeded", data)

    # ------------------------------------------------------------------
    # (e) Schema_version forward-compat: unknown top-level field accepted
    # ------------------------------------------------------------------

    def test_e_schema_version_forward_compat_unknown_field_accepted(self) -> None:
        event = _make_event()
        event["unknown_top_level_field"] = "from-a-newer-daemon"
        event["another_future_field"] = {"nested": True}

        resp = self.client.post(
            "/api/v1/ingest/sessions",
            content=_ndjson(event),
            headers=_DEFAULT_HEADERS,
        )

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["accepted"], 1, data)
        self.assertEqual(data["rejected"], [], data)

    # ------------------------------------------------------------------
    # (f) Auth: missing/invalid Bearer → 401
    # ------------------------------------------------------------------

    def test_f_auth_missing_bearer_returns_401(self) -> None:
        event = _make_event()
        with self._api_bearer_auth_enabled("secret-token"):
            resp = self.client.post(
                "/api/v1/ingest/sessions",
                content=_ndjson(event),
                headers={
                    "Content-Type": "application/x-ndjson",
                    "x-ccdash-project-id": "test-project",
                    # No Authorization header.
                },
            )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_f_auth_invalid_bearer_returns_401_or_403(self) -> None:
        event = _make_event()
        with self._api_bearer_auth_enabled("secret-token"):
            resp = self.client.post(
                "/api/v1/ingest/sessions",
                content=_ndjson(event),
                headers={
                    "Content-Type": "application/x-ndjson",
                    "x-ccdash-project-id": "test-project",
                    "Authorization": "Bearer wrong-token",
                },
            )
        self.assertIn(resp.status_code, (401, 403), resp.text)

    def test_f_auth_valid_bearer_accepted(self) -> None:
        # The auth dependency is overridden to synthesize a local AuthContext
        # in test profile. Send with a bearer token; auth succeeds via override.
        event = _make_event()
        resp = self.client.post(
            "/api/v1/ingest/sessions",
            content=_ndjson(event),
            headers={
                "Content-Type": "application/x-ndjson",
                "x-ccdash-project-id": "test-project",
                "Authorization": "Bearer valid-token",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["accepted"], 1)

    # ------------------------------------------------------------------
    # (g) Cursor: ingest_cursors row advances to last accepted event_id
    # ------------------------------------------------------------------

    def test_g_cursor_advances_to_last_accepted_event_id(self) -> None:
        # Use a unique project_id so we don't collide with other tests.
        project_id = f"cursor-test-{_event_id()[:8]}"
        events = [_make_event() for _ in range(3)]
        last_event_id = events[-1]["event_id"]

        resp = self.client.post(
            "/api/v1/ingest/sessions",
            content=_ndjson(*events),
            headers={
                "Content-Type": "application/x-ndjson",
                "x-ccdash-project-id": project_id,
            },
        )

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["accepted"], 3, data)

        # The response envelope must carry the last accepted event_id.
        self.assertEqual(data["cursor_advanced_to"], last_event_id, data)

        # The DB row must also reflect the advance.
        db_cursor = self._get_cursor_value(project_id)
        self.assertEqual(db_cursor, last_event_id, f"DB cursor={db_cursor!r}")

    # ------------------------------------------------------------------
    # Content-Type guard
    # ------------------------------------------------------------------

    def test_wrong_content_type_returns_415(self) -> None:
        resp = self.client.post(
            "/api/v1/ingest/sessions",
            content=b'{"event_id": "x"}\n',
            headers={
                "Content-Type": "application/json",
                "x-ccdash-project-id": "test-project",
            },
        )
        self.assertEqual(resp.status_code, 415, resp.text)


if __name__ == "__main__":
    unittest.main()
