"""Tests for POST /api/observability/poll-teardown (OBS-402).

Uses a minimal FastAPI app with dependency overrides so no DB connection is
needed — the same pattern used by test_planning_rollout_flag.py.

Verifies:
- 202 response with correct ``recorded`` field
- ``record_frontend_poll_teardown`` is called once per event
- Default (empty body) records exactly 1 event
- events=5 records exactly 5 events
- Boundary value events=100 is accepted
- Values outside [1, 100] are rejected with 422
"""
from __future__ import annotations

import unittest
from unittest.mock import call, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.request_scope import get_request_context
from backend.routers.observability import observability_router

_TARGET = "backend.observability.otel.record_frontend_poll_teardown"


def _client() -> TestClient:
    """Minimal app including only the observability router with mocked deps."""
    app = FastAPI()
    app.include_router(observability_router)
    # Override the request-context dependency so no DB lifespan is needed.
    app.dependency_overrides[get_request_context] = lambda: object()
    return TestClient(app, raise_server_exceptions=True)


class PollTeardownEndpointTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # Happy-path: default body (no ``events`` key → Pydantic default=1)
    # ------------------------------------------------------------------

    def test_empty_body_returns_202_recorded_1(self) -> None:
        with patch(_TARGET) as mock_record:
            client = _client()
            resp = client.post(
                "/api/observability/poll-teardown",
                json={},
                headers={"Content-Type": "application/json"},
            )
        self.assertEqual(resp.status_code, 202)
        payload = resp.json()
        self.assertEqual(payload.get("recorded"), 1)
        mock_record.assert_called_once()

    def test_explicit_events_1_calls_record_once(self) -> None:
        with patch(_TARGET) as mock_record:
            client = _client()
            resp = client.post(
                "/api/observability/poll-teardown",
                json={"events": 1},
            )
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json()["recorded"], 1)
        mock_record.assert_called_once()

    def test_events_5_calls_record_five_times(self) -> None:
        with patch(_TARGET) as mock_record:
            client = _client()
            resp = client.post(
                "/api/observability/poll-teardown",
                json={"events": 5},
            )
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json()["recorded"], 5)
        self.assertEqual(mock_record.call_count, 5)
        mock_record.assert_has_calls([call()] * 5)

    def test_events_100_boundary_accepted(self) -> None:
        with patch(_TARGET) as mock_record:
            client = _client()
            resp = client.post(
                "/api/observability/poll-teardown",
                json={"events": 100},
            )
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json()["recorded"], 100)
        self.assertEqual(mock_record.call_count, 100)

    # ------------------------------------------------------------------
    # Validation: values outside [1, 100] must be rejected with 422
    # ------------------------------------------------------------------

    def test_events_0_rejected(self) -> None:
        with patch(_TARGET):
            client = _client()
            resp = client.post(
                "/api/observability/poll-teardown",
                json={"events": 0},
            )
        self.assertEqual(resp.status_code, 422)

    def test_events_101_rejected(self) -> None:
        with patch(_TARGET):
            client = _client()
            resp = client.post(
                "/api/observability/poll-teardown",
                json={"events": 101},
            )
        self.assertEqual(resp.status_code, 422)

    def test_events_negative_rejected(self) -> None:
        with patch(_TARGET):
            client = _client()
            resp = client.post(
                "/api/observability/poll-teardown",
                json={"events": -1},
            )
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
