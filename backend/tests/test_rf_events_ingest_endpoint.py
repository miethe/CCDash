"""Contract tests for POST /api/v1/ingest/rf-events (T1-003).

Covers:
  (a) single JSON happy path -> 200, accepted=1, row persisted
  (b) NDJSON batch of 2 -> 200, accepted=2
  (c) dedup -> re-POST of the same event_id -> exactly one row (AC-1)
  (d) missing optional fields (human_review, output_artifacts, metrics) ->
      row persists with those columns null, never a 422/error (AC-1 resilience)
  (e) Layer 1 redaction scan fires BEFORE persistence (FR-14) -- a
      secret-shaped string embedded in an optional field is redacted in the
      stored raw_payload_json
  (f) wrong Content-Type -> 415
  (g) malformed single JSON -> 200 with rejected[] (never a 5xx)

Setup mirrors backend/tests/test_ingest_endpoint.py:
  tempfile SQLite DB + build_runtime_app("test") + TestClient context.

Run as a named module:
    backend/.venv/bin/python -m pytest backend/tests/test_rf_events_ingest_endpoint.py -v
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.adapters.auth.context import AuthContext
from backend.adapters.auth.dependency import get_auth_context
from backend.runtime.bootstrap import build_runtime_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event_id() -> str:
    return str(uuid.uuid4())


def _make_event(event_id: str | None = None, **extra) -> dict:
    """Return a dict shaped like RF's ccdash_event payload (schema §required)."""
    eid = event_id or _event_id()
    obj = {
        "event_id": eid,
        "timestamp": "2026-07-21T10:00:00.000000Z",
        "project": "research-foundry",
        "run_id": f"run-{eid[:8]}",
        "metrics": {
            "claims_total": 10,
            "claims_supported": 8,
            "verification_passed": True,
            "cost_estimated_usd": 0.42,
            "quality_score": "high",
        },
        "governance": {
            "sensitivity": "public",
            "policy_passed": True,
        },
        "reuse": {
            "skillbom_candidate": True,
        },
    }
    obj.update(extra)
    return obj


def _ndjson(*events: dict) -> bytes:
    return b"\n".join(json.dumps(e).encode() for e in events) + b"\n"


_DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "x-ccdash-project-id": "test-project",
}
_NDJSON_HEADERS = {
    "Content-Type": "application/x-ndjson",
    "x-ccdash-project-id": "test-project",
}


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestRfEventsIngestEndpoint(unittest.TestCase):
    """Integration tests for POST /api/v1/ingest/rf-events."""

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

    # ------------------------------------------------------------------
    # Helper: read rf_events rows directly from the test SQLite file
    # ------------------------------------------------------------------

    def _fetch_row(self, event_id: str) -> sqlite3.Row | None:
        from backend.db.connection import _resolve_db_path

        conn = sqlite3.connect(str(_resolve_db_path()))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute("SELECT * FROM rf_events WHERE event_id = ?", (event_id,))
            return cur.fetchone()
        finally:
            conn.close()

    def _count_rows(self, event_id: str) -> int:
        from backend.db.connection import _resolve_db_path

        conn = sqlite3.connect(str(_resolve_db_path()))
        try:
            cur = conn.execute("SELECT COUNT(*) FROM rf_events WHERE event_id = ?", (event_id,))
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # (a) Single JSON happy path
    # ------------------------------------------------------------------

    def test_a_single_json_happy_path(self) -> None:
        event = _make_event()
        resp = self.client.post(
            "/api/v1/ingest/rf-events",
            content=json.dumps(event).encode(),
            headers=_DEFAULT_HEADERS,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["accepted"], 1, data)
        self.assertEqual(data["rejected"], [], data)
        self.assertEqual(data["cursor_advanced_to"], event["event_id"], data)

        row = self._fetch_row(event["event_id"])
        self.assertIsNotNone(row)
        self.assertEqual(row["project_id"], "test-project")
        self.assertEqual(row["workspace_id"], "default-local")
        self.assertEqual(row["rf_project"], "research-foundry")
        self.assertEqual(row["run_id"], event["run_id"])
        self.assertEqual(row["metric_claims_total"], 10)
        self.assertEqual(row["metric_verification_passed"], 1)
        self.assertEqual(row["metric_quality_score"], "high")
        self.assertEqual(row["governance_sensitivity"], "public")
        self.assertEqual(row["reuse_skillbom_candidate"], 1)

    # ------------------------------------------------------------------
    # (b) NDJSON batch of 2
    # ------------------------------------------------------------------

    def test_b_ndjson_batch_of_two_accepted(self) -> None:
        events = [_make_event(), _make_event()]
        resp = self.client.post(
            "/api/v1/ingest/rf-events",
            content=_ndjson(*events),
            headers=_NDJSON_HEADERS,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["accepted"], 2, data)
        self.assertEqual(data["rejected"], [], data)
        for event in events:
            self.assertEqual(self._count_rows(event["event_id"]), 1)

    # ------------------------------------------------------------------
    # (c) Dedup: same event_id re-POSTed -> exactly one row
    # ------------------------------------------------------------------

    def test_c_dedup_same_event_id_not_duplicated(self) -> None:
        event = _make_event()

        resp1 = self.client.post(
            "/api/v1/ingest/rf-events",
            content=json.dumps(event).encode(),
            headers=_DEFAULT_HEADERS,
        )
        self.assertEqual(resp1.status_code, 200, resp1.text)
        self.assertEqual(resp1.json()["accepted"], 1)

        # Re-POST the identical event.
        resp2 = self.client.post(
            "/api/v1/ingest/rf-events",
            content=json.dumps(event).encode(),
            headers=_DEFAULT_HEADERS,
        )
        self.assertEqual(resp2.status_code, 200, resp2.text)
        # The endpoint still reports it as "accepted" (idempotent), but the
        # DB must carry exactly one row for this event_id.
        self.assertEqual(resp2.json()["accepted"], 1, resp2.json())
        self.assertEqual(self._count_rows(event["event_id"]), 1)

    # ------------------------------------------------------------------
    # (d) Missing optional fields -> row persists, columns null, never a 422
    # ------------------------------------------------------------------

    def test_d_missing_optional_fields_persists_with_nulls(self) -> None:
        event_id = _event_id()
        minimal_event = {
            "event_id": event_id,
            "timestamp": "2026-07-21T10:05:00.000000Z",
            "project": "research-foundry",
        }
        resp = self.client.post(
            "/api/v1/ingest/rf-events",
            content=json.dumps(minimal_event).encode(),
            headers=_DEFAULT_HEADERS,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["accepted"], 1, data)
        self.assertEqual(data["rejected"], [], data)

        row = self._fetch_row(event_id)
        self.assertIsNotNone(row)
        self.assertIsNone(row["run_id"])
        self.assertIsNone(row["human_review_required"])
        self.assertIsNone(row["human_review_status"])
        self.assertIsNone(row["output_artifacts_json"])
        self.assertIsNone(row["metric_claims_total"])
        self.assertIsNone(row["governance_sensitivity"])

    # ------------------------------------------------------------------
    # (e) Layer 1 redaction scan fires BEFORE persistence (FR-14)
    # ------------------------------------------------------------------

    def test_e_layer1_redaction_scan_fires_before_persistence(self) -> None:
        event = _make_event(
            intent_id="api_key=ABCDEF1234567890ABCDEF1234567890",
        )
        resp = self.client.post(
            "/api/v1/ingest/rf-events",
            content=json.dumps(event).encode(),
            headers=_DEFAULT_HEADERS,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["accepted"], 1)

        row = self._fetch_row(event["event_id"])
        self.assertIsNotNone(row)
        self.assertNotIn("ABCDEF1234567890ABCDEF1234567890", row["intent_id"])
        self.assertIn("[REDACTED]", row["intent_id"])
        raw_payload = json.loads(row["raw_payload_json"])
        self.assertNotIn("ABCDEF1234567890ABCDEF1234567890", raw_payload["intent_id"])

    # ------------------------------------------------------------------
    # (f) Wrong Content-Type -> 415
    # ------------------------------------------------------------------

    def test_f_wrong_content_type_returns_415(self) -> None:
        resp = self.client.post(
            "/api/v1/ingest/rf-events",
            content=b'{"event_id": "x"}',
            headers={
                "Content-Type": "text/plain",
                "x-ccdash-project-id": "test-project",
            },
        )
        self.assertEqual(resp.status_code, 415, resp.text)

    # ------------------------------------------------------------------
    # (g) Malformed single JSON -> 200 with rejected[], never a 5xx
    # ------------------------------------------------------------------

    def test_g_malformed_json_rejected_not_5xx(self) -> None:
        resp = self.client.post(
            "/api/v1/ingest/rf-events",
            content=b'{"missing_required_fields": true}',
            headers=_DEFAULT_HEADERS,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["accepted"], 0, data)
        self.assertEqual(len(data["rejected"]), 1, data)
        self.assertEqual(data["rejected"][0]["code"], "invalid_event", data)


if __name__ == "__main__":
    unittest.main()
