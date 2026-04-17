"""Tests for the launch capabilities endpoint and feature-flag guardrail (PCP-505)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.request_scope import get_core_ports, get_request_context
from backend.routers.execution import execution_router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(execution_router)
    # Stub request-scope deps so the 503 gate runs before any real runtime context.
    app.dependency_overrides[get_request_context] = lambda: object()
    app.dependency_overrides[get_core_ports] = lambda: object()
    return TestClient(app)


class LaunchCapabilitiesTests(unittest.TestCase):
    def test_capabilities_reports_disabled_by_default(self) -> None:
        with patch("backend.routers.execution.config.CCDASH_LAUNCH_PREP_ENABLED", False):
            client = _make_client()
            response = client.get("/api/execution/launch/capabilities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["enabled"])
        self.assertIn("CCDASH_LAUNCH_PREP_ENABLED", body["disabledReason"])
        self.assertEqual(body["providers"], [])

    def test_capabilities_reports_enabled_with_providers(self) -> None:
        with patch("backend.routers.execution.config.CCDASH_LAUNCH_PREP_ENABLED", True):
            client = _make_client()
            response = client.get("/api/execution/launch/capabilities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["enabled"])
        self.assertEqual(body["disabledReason"], "")
        providers = body["providers"]
        self.assertTrue(any(p["provider"] == "local" for p in providers))
        local = next(p for p in providers if p["provider"] == "local")
        self.assertTrue(local["supported"])

    def test_prepare_launch_returns_503_when_disabled(self) -> None:
        with patch("backend.routers.execution.config.CCDASH_LAUNCH_PREP_ENABLED", False):
            client = _make_client()
            response = client.post(
                "/api/execution/launch/prepare",
                json={
                    "projectId": "proj",
                    "featureId": "FEAT-1",
                    "phaseNumber": 1,
                    "batchId": "batch-a",
                },
            )
        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertEqual(detail["error"], "launch_disabled")

    def test_start_launch_returns_503_when_disabled(self) -> None:
        with patch("backend.routers.execution.config.CCDASH_LAUNCH_PREP_ENABLED", False):
            client = _make_client()
            response = client.post(
                "/api/execution/launch/start",
                json={
                    "projectId": "proj",
                    "featureId": "FEAT-1",
                    "phaseNumber": 1,
                    "batchId": "batch-a",
                    "provider": "local",
                    "worktree": {
                        "worktreeContextId": "",
                        "createIfMissing": True,
                        "branch": "",
                        "worktreePath": "",
                        "baseBranch": "",
                        "notes": "",
                    },
                },
            )
        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertEqual(detail["error"], "launch_disabled")


if __name__ == "__main__":
    unittest.main()
