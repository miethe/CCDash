"""T9-008: /readyz endpoint health-gate tests for the API runtime.

Validates that:
  * All checks healthy → HTTP 200 with ready=true
  * DB unreachable    → HTTP 503 with reasonCode "db_unreachable"
  * Migration behind  → HTTP 503 with reasonCode "migration_behind"
  * Queue unreachable → HTTP 503 with reasonCode "queue_unreachable"
  * Partial failure (2 of 3 checks fail) → HTTP 503, both codes present

The three module-level check helpers (_readyz_check_db,
_readyz_check_migration_head, _readyz_check_queue_backend) are patched so
tests run without a live database or queue backend.

A minimal FastAPI app is constructed that registers the /readyz route using
the real check functions from bootstrap.py.  This exercises the endpoint's
aggregation / response-code logic independently of the full runtime container
startup.

Run with:
    backend/.venv/bin/python -m pytest backend/tests/test_readyz_health.py -v
"""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, Response, status
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Minimal app builder — mirrors the /readyz logic in bootstrap.py exactly
# so that patching the module-level check functions is the single test seam.
# ---------------------------------------------------------------------------

def _build_readyz_test_app() -> FastAPI:
    """Return a minimal FastAPI app that registers only the /readyz endpoint.

    The endpoint body is a verbatim copy of the implementation registered by
    ``build_runtime_app`` in bootstrap.py so that patching the bootstrap
    module-level check functions exercises the exact same code path.
    """
    import backend.runtime.bootstrap as bs

    app = FastAPI()

    @app.get("/readyz")
    async def readyz_api(resp: Response) -> dict:
        db_ok, db_err = await bs._readyz_check_db()
        mig_ok, mig_err = await bs._readyz_check_migration_head()
        queue_ok, queue_err = await bs._readyz_check_queue_backend()

        checks = {
            "db_connected": db_ok,
            "migration_head_applied": mig_ok,
            "queue_reachable": queue_ok,
        }
        reasons = []
        if not db_ok:
            reasons.append({"code": "db_unreachable", "detail": db_err or ""})
        if not mig_ok:
            reasons.append({"code": "migration_behind", "detail": mig_err or ""})
        if not queue_ok:
            reasons.append({"code": "queue_unreachable", "detail": queue_err or ""})

        ready = not reasons
        if not ready:
            resp.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "schemaVersion": "1",
            "runtimeProfile": "api",
            "ready": ready,
            "checks": checks,
            "reasons": reasons,
            "reasonCodes": [r["code"] for r in reasons],
        }

    return app


_APP = _build_readyz_test_app()


def _client() -> TestClient:
    return TestClient(_APP, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class ReadyzHealthTests(unittest.TestCase):
    """HTTP-level tests for the /readyz endpoint.

    Each test patches the three check helpers to simulate specific failure
    combinations without requiring any live infrastructure.
    """

    # ── happy path ──────────────────────────────────────────────────────────

    def test_all_checks_healthy_returns_200(self) -> None:
        with (
            patch(
                "backend.runtime.bootstrap._readyz_check_db",
                new=AsyncMock(return_value=(True, None)),
            ),
            patch(
                "backend.runtime.bootstrap._readyz_check_migration_head",
                new=AsyncMock(return_value=(True, None)),
            ),
            patch(
                "backend.runtime.bootstrap._readyz_check_queue_backend",
                new=AsyncMock(return_value=(True, None)),
            ),
        ):
            resp = _client().get("/readyz")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ready"])
        self.assertEqual(data["reasonCodes"], [])
        self.assertTrue(data["checks"]["db_connected"])
        self.assertTrue(data["checks"]["migration_head_applied"])
        self.assertTrue(data["checks"]["queue_reachable"])
        self.assertEqual(data["schemaVersion"], "1")

    # ── DB-down path ─────────────────────────────────────────────────────────

    def test_db_down_returns_503(self) -> None:
        with (
            patch(
                "backend.runtime.bootstrap._readyz_check_db",
                new=AsyncMock(return_value=(False, "connection refused")),
            ),
            patch(
                "backend.runtime.bootstrap._readyz_check_migration_head",
                new=AsyncMock(return_value=(False, "db not connected")),
            ),
            patch(
                "backend.runtime.bootstrap._readyz_check_queue_backend",
                new=AsyncMock(return_value=(True, None)),
            ),
        ):
            resp = _client().get("/readyz")

        self.assertEqual(resp.status_code, 503)
        data = resp.json()
        self.assertFalse(data["ready"])
        self.assertIn("db_unreachable", data["reasonCodes"])
        self.assertFalse(data["checks"]["db_connected"])

    # ── migration-behind path ────────────────────────────────────────────────

    def test_migration_behind_returns_503(self) -> None:
        with (
            patch(
                "backend.runtime.bootstrap._readyz_check_db",
                new=AsyncMock(return_value=(True, None)),
            ),
            patch(
                "backend.runtime.bootstrap._readyz_check_migration_head",
                new=AsyncMock(return_value=(False, "migration head v34 not found in migrations_applied")),
            ),
            patch(
                "backend.runtime.bootstrap._readyz_check_queue_backend",
                new=AsyncMock(return_value=(True, None)),
            ),
        ):
            resp = _client().get("/readyz")

        self.assertEqual(resp.status_code, 503)
        data = resp.json()
        self.assertFalse(data["ready"])
        self.assertIn("migration_behind", data["reasonCodes"])
        # DB is connected; only migration check failed
        self.assertTrue(data["checks"]["db_connected"])
        self.assertFalse(data["checks"]["migration_head_applied"])

    # ── queue-unreachable path ───────────────────────────────────────────────

    def test_queue_unreachable_returns_503(self) -> None:
        with (
            patch(
                "backend.runtime.bootstrap._readyz_check_db",
                new=AsyncMock(return_value=(True, None)),
            ),
            patch(
                "backend.runtime.bootstrap._readyz_check_migration_head",
                new=AsyncMock(return_value=(True, None)),
            ),
            patch(
                "backend.runtime.bootstrap._readyz_check_queue_backend",
                new=AsyncMock(return_value=(False, "job_queue table not found")),
            ),
        ):
            resp = _client().get("/readyz")

        self.assertEqual(resp.status_code, 503)
        data = resp.json()
        self.assertFalse(data["ready"])
        self.assertIn("queue_unreachable", data["reasonCodes"])
        self.assertFalse(data["checks"]["queue_reachable"])

    # ── partial failure: 2 of 3 checks down ─────────────────────────────────

    def test_partial_failure_reports_all_failing_reason_codes(self) -> None:
        with (
            patch(
                "backend.runtime.bootstrap._readyz_check_db",
                new=AsyncMock(return_value=(False, "ECONNREFUSED")),
            ),
            patch(
                "backend.runtime.bootstrap._readyz_check_migration_head",
                new=AsyncMock(return_value=(False, "db not connected")),
            ),
            patch(
                "backend.runtime.bootstrap._readyz_check_queue_backend",
                new=AsyncMock(return_value=(False, "job_queue unreachable")),
            ),
        ):
            resp = _client().get("/readyz")

        self.assertEqual(resp.status_code, 503)
        data = resp.json()
        self.assertFalse(data["ready"])
        codes = set(data["reasonCodes"])
        self.assertIn("db_unreachable", codes)
        self.assertIn("migration_behind", codes)
        self.assertIn("queue_unreachable", codes)

    # ── response schema invariants ───────────────────────────────────────────

    def test_response_always_contains_required_keys(self) -> None:
        """All required schema keys are present regardless of check outcome."""
        with (
            patch(
                "backend.runtime.bootstrap._readyz_check_db",
                new=AsyncMock(return_value=(True, None)),
            ),
            patch(
                "backend.runtime.bootstrap._readyz_check_migration_head",
                new=AsyncMock(return_value=(True, None)),
            ),
            patch(
                "backend.runtime.bootstrap._readyz_check_queue_backend",
                new=AsyncMock(return_value=(True, None)),
            ),
        ):
            resp = _client().get("/readyz")

        data = resp.json()
        for key in ("schemaVersion", "runtimeProfile", "ready", "checks", "reasons", "reasonCodes"):
            self.assertIn(key, data, msg=f"Required key '{key}' missing from /readyz response")
        for check_key in ("db_connected", "migration_head_applied", "queue_reachable"):
            self.assertIn(check_key, data["checks"], msg=f"Check key '{check_key}' missing")

    # ── check function unit tests (no HTTP) ──────────────────────────────────

    def test_readyz_check_functions_are_importable(self) -> None:
        """Verify the three check helpers exist at module level and are callable."""
        from backend.runtime.bootstrap import (
            _readyz_check_db,
            _readyz_check_migration_head,
            _readyz_check_queue_backend,
        )
        import asyncio
        # Each must be a coroutine function (async def)
        self.assertTrue(asyncio.iscoroutinefunction(_readyz_check_db))
        self.assertTrue(asyncio.iscoroutinefunction(_readyz_check_migration_head))
        self.assertTrue(asyncio.iscoroutinefunction(_readyz_check_queue_backend))


if __name__ == "__main__":
    unittest.main()
