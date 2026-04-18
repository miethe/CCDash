"""PCP-603: Planning control plane staged rollout flag tests.

Verifies:
1. All four /agent/planning/* endpoints return HTTP 503 with error="planning_disabled"
   when CCDASH_PLANNING_CONTROL_PLANE_ENABLED is False.
2. Endpoints pass through normally (do not 503) when the flag is True.
3. /execution/launch/capabilities includes planningEnabled field reflecting the flag.
"""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.request_scope import get_core_ports, get_request_context
from backend.routers.agent import agent_router
from backend.routers.execution import execution_router


# ---------------------------------------------------------------------------
# Shared test client factory
# ---------------------------------------------------------------------------


def _make_agent_client(raise_server_exceptions: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(agent_router)
    app.dependency_overrides[get_request_context] = lambda: object()
    app.dependency_overrides[get_core_ports] = lambda: object()
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _make_execution_client() -> TestClient:
    app = FastAPI()
    app.include_router(execution_router)
    app.dependency_overrides[get_request_context] = lambda: object()
    app.dependency_overrides[get_core_ports] = lambda: object()
    return TestClient(app)


# ---------------------------------------------------------------------------
# 503 gate tests (flag=False)
# ---------------------------------------------------------------------------


class PlanningRolloutFlagDisabledTests(unittest.TestCase):
    """All /agent/planning/* endpoints must return 503 when flag is False."""

    def _assert_planning_disabled(self, response) -> None:
        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertEqual(detail["error"], "planning_disabled")
        self.assertIn("Planning control plane is disabled", detail["message"])

    def test_summary_returns_503_when_disabled(self) -> None:
        with patch("backend.routers.agent.config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED", False):
            client = _make_agent_client()
            response = client.get("/api/agent/planning/summary")
        self._assert_planning_disabled(response)

    def test_graph_returns_503_when_disabled(self) -> None:
        with patch("backend.routers.agent.config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED", False):
            client = _make_agent_client()
            response = client.get("/api/agent/planning/graph")
        self._assert_planning_disabled(response)

    def test_feature_context_returns_503_when_disabled(self) -> None:
        with patch("backend.routers.agent.config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED", False):
            client = _make_agent_client()
            response = client.get("/api/agent/planning/features/FEAT-1")
        self._assert_planning_disabled(response)

    def test_phase_operations_returns_503_when_disabled(self) -> None:
        with patch("backend.routers.agent.config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED", False):
            client = _make_agent_client()
            response = client.get("/api/agent/planning/features/FEAT-1/phases/1")
        self._assert_planning_disabled(response)


# ---------------------------------------------------------------------------
# Normal-path tests (flag=True): dependency guard must not block the request.
# We only check that the guard itself does not return 503; the full response
# requires a real DB context so we allow any non-503 status here.
# ---------------------------------------------------------------------------


class PlanningRolloutFlagEnabledTests(unittest.TestCase):
    """When flag is True the guard must not raise 503.

    The endpoint handlers will raise 500/422 after the guard passes because the
    dependency-overridden ``object()`` stubs lack the real port interface.
    We use raise_server_exceptions=False so the TestClient returns a 500 response
    rather than re-raising, then assert the status is NOT 503 to prove the guard
    did not fire.
    """

    def test_summary_not_gated_when_enabled(self) -> None:
        with patch("backend.routers.agent.config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED", True):
            client = _make_agent_client(raise_server_exceptions=False)
            response = client.get("/api/agent/planning/summary")
        # 503 would mean the disabled guard fired; any other status is acceptable.
        self.assertNotEqual(response.status_code, 503)

    def test_graph_not_gated_when_enabled(self) -> None:
        with patch("backend.routers.agent.config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED", True):
            client = _make_agent_client(raise_server_exceptions=False)
            response = client.get("/api/agent/planning/graph")
        self.assertNotEqual(response.status_code, 503)

    def test_feature_context_not_gated_when_enabled(self) -> None:
        with patch("backend.routers.agent.config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED", True):
            client = _make_agent_client(raise_server_exceptions=False)
            response = client.get("/api/agent/planning/features/FEAT-1")
        self.assertNotEqual(response.status_code, 503)

    def test_phase_operations_not_gated_when_enabled(self) -> None:
        with patch("backend.routers.agent.config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED", True):
            client = _make_agent_client(raise_server_exceptions=False)
            response = client.get("/api/agent/planning/features/FEAT-1/phases/1")
        self.assertNotEqual(response.status_code, 503)


# ---------------------------------------------------------------------------
# planningEnabled in /execution/launch/capabilities
# ---------------------------------------------------------------------------


class PlanningEnabledCapabilityFieldTests(unittest.TestCase):
    """Capabilities endpoint must expose planningEnabled reflecting the config flag."""

    def test_planning_enabled_true_by_default(self) -> None:
        with patch("backend.routers.execution.config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED", True):
            client = _make_execution_client()
            response = client.get("/api/execution/launch/capabilities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("planningEnabled", body)
        self.assertTrue(body["planningEnabled"])

    def test_planning_enabled_false_when_flag_off(self) -> None:
        with patch("backend.routers.execution.config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED", False):
            client = _make_execution_client()
            response = client.get("/api/execution/launch/capabilities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("planningEnabled", body)
        self.assertFalse(body["planningEnabled"])

    def test_planning_enabled_independent_of_launch_flag(self) -> None:
        """planningEnabled and enabled are independent flags."""
        with (
            patch("backend.routers.execution.config.CCDASH_LAUNCH_PREP_ENABLED", False),
            patch("backend.routers.execution.config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED", True),
        ):
            client = _make_execution_client()
            response = client.get("/api/execution/launch/capabilities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["enabled"])
        self.assertTrue(body["planningEnabled"])


if __name__ == "__main__":
    unittest.main()
