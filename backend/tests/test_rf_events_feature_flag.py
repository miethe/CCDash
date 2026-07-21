"""Feature flag tests for CCDASH_RF_TELEMETRY_ENABLED (T1-006).

Covers:
  (a) default is True (fail-open)
  (b) dependency raises 404 with a `rf_telemetry_disabled` payload when the
      flag is patched False
  (c) dependency is a no-op (returns None) when the flag is True
  (d) integration: POST /api/v1/ingest/rf-events -> 404 when the flag is off
  (e) integration: POST /api/v1/ingest/rf-events -> 200 when the flag is on
      (default; no explicit patch needed)
  (f) zero effect on any other surface: POST /api/v1/ingest/sessions still
      succeeds normally while CCDASH_RF_TELEMETRY_ENABLED is False

Setup mirrors backend/tests/test_rf_events_ingest_endpoint.py:
  tempfile SQLite DB + build_runtime_app("test") + TestClient context.

Run as a named module:
    backend/.venv/bin/python -m pytest backend/tests/test_rf_events_feature_flag.py -v
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import config
from backend.adapters.auth.context import AuthContext
from backend.adapters.auth.dependency import get_auth_context
from backend.routers import ingest as ingest_router
from backend.runtime.bootstrap import build_runtime_app


def _event_id() -> str:
    return str(uuid.uuid4())


def _make_rf_event(event_id: str | None = None) -> dict:
    eid = event_id or _event_id()
    return {
        "event_id": eid,
        "timestamp": "2026-07-21T10:00:00.000000Z",
        "project": "research-foundry",
        "run_id": f"run-{eid[:8]}",
    }


def _make_session_event(session_id: str) -> dict:
    """Return a dict representing one IngestSessionEvent (wraps a minimal payload)."""
    return {
        "event_id": _event_id(),
        "batch_id": str(uuid.uuid4()),
        "schema_version": "1.0",
        "occurred_at": "2026-07-21T10:00:00.000000Z",
        "payload": {
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
        },
    }


_JSON_HEADERS = {
    "Content-Type": "application/json",
    "x-ccdash-project-id": "test-project",
}
_NDJSON_HEADERS = {
    "Content-Type": "application/x-ndjson",
    "x-ccdash-project-id": "test-project",
}


# ---------------------------------------------------------------------------
# (a)-(c) Unit tests: default value + dependency behaviour, no app needed
# ---------------------------------------------------------------------------


class TestRfTelemetryFlagUnit(unittest.TestCase):
    """Fast, app-free tests for the flag default and its gate dependency."""

    def test_a_default_is_true_fail_open(self) -> None:
        self.assertTrue(config.CCDASH_RF_TELEMETRY_ENABLED)

    def test_b_dependency_raises_404_when_disabled(self) -> None:
        with patch.object(config, "CCDASH_RF_TELEMETRY_ENABLED", False):
            with self.assertRaises(HTTPException) as ctx:
                ingest_router._require_rf_telemetry_enabled()

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("rf_telemetry_disabled", str(ctx.exception.detail))

    def test_c_dependency_is_noop_when_enabled(self) -> None:
        with patch.object(config, "CCDASH_RF_TELEMETRY_ENABLED", True):
            # Should not raise.
            self.assertIsNone(ingest_router._require_rf_telemetry_enabled())


# ---------------------------------------------------------------------------
# (d)-(f) Integration tests: full app + TestClient
# ---------------------------------------------------------------------------


class TestRfTelemetryFlagIntegration(unittest.TestCase):
    """Router-level flag-off/flag-on behavior, and cross-surface isolation."""

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
        ]
        for p in cls._patches:
            p.start()

        cls._app.dependency_overrides[get_auth_context] = lambda: AuthContext.synthesize_local(
            project_id="test-project"
        )

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

    def test_d_flag_off_returns_404(self) -> None:
        event = _make_rf_event()
        with patch.object(config, "CCDASH_RF_TELEMETRY_ENABLED", False):
            resp = self.client.post(
                "/api/v1/ingest/rf-events",
                content=json.dumps(event).encode(),
                headers=_JSON_HEADERS,
            )
        self.assertEqual(resp.status_code, 404, resp.text)
        detail = resp.json().get("detail", {})
        self.assertEqual(detail.get("error"), "rf_telemetry_disabled", detail)

    def test_e_flag_on_returns_200(self) -> None:
        event = _make_rf_event()
        with patch.object(config, "CCDASH_RF_TELEMETRY_ENABLED", True):
            resp = self.client.post(
                "/api/v1/ingest/rf-events",
                content=json.dumps(event).encode(),
                headers=_JSON_HEADERS,
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["accepted"], 1)

    def test_f_disabling_rf_telemetry_has_zero_effect_on_sessions_ingest(self) -> None:
        session_id = f"sess-{_event_id()}"
        session_event = _make_session_event(session_id)
        with patch.object(config, "CCDASH_RF_TELEMETRY_ENABLED", False):
            # RF telemetry route is gone...
            rf_resp = self.client.post(
                "/api/v1/ingest/rf-events",
                content=json.dumps(_make_rf_event()).encode(),
                headers=_JSON_HEADERS,
            )
            self.assertEqual(rf_resp.status_code, 404, rf_resp.text)

            # ...but the pre-existing sessions ingest route is fully unaffected.
            sessions_resp = self.client.post(
                "/api/v1/ingest/sessions",
                content=(json.dumps(session_event) + "\n").encode(),
                headers=_NDJSON_HEADERS,
            )
        self.assertEqual(sessions_resp.status_code, 200, sessions_resp.text)
        self.assertEqual(sessions_resp.json()["accepted"], 1, sessions_resp.json())


if __name__ == "__main__":
    unittest.main()
