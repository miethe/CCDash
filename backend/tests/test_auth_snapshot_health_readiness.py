"""AC3 regression coverage: a fail-closed token snapshot must not be SILENT.

Node: node_01KZVXW3ES7ED0EAS8J0MZHRQY (AC3).

Context — why this file exists
------------------------------
``WorkspaceTokenAuthBackend._reload_snapshot`` loads the argon2id token snapshot
from the DB.  On the Postgres backend it used to use the aiosqlite cursor idiom
against an ``asyncpg.Pool``, which raises; a bare ``except Exception`` swallowed
that, the snapshot stayed empty forever, and EVERY bearer token was rejected
with 401.  The direction was right (fail closed) but the failure was invisible:
the only trace was one log line.  ``grep -c "snapshot refreshed"`` returned 0.

The idiom bug itself was fixed in be420d8 and is covered by
``test_workspace_token_auth.py``.  This file covers the OTHER half: that the
failure now reaches ``/api/health/detail`` and ``/api/health/ready`` instead of
only the log.

The anti-deadlock rule is the subtle part
-----------------------------------------
The snapshot loads LAZILY, on the first authenticated request.  Readiness gates
``compose up --wait``, the container healthcheck and ``/redeploy``'s health
gate — so a naive "fail if the snapshot is not loaded" rule would deadlock:
ready would need a request, and a request would need ready.  Hence the ladder:

    never attempted            -> pass  (nothing is known to be wrong)
    attempted, has succeeded   -> pass
    succeeded before, now failing -> warn (serving last-known-good)
    attempted, NEVER succeeded -> fail  (the broken-on-PG signature)

``test_never_attempted_is_ready`` is the regression guard for that deadlock; if
it ever fails, the api profile can no longer start.
"""
from __future__ import annotations

import json
import types
import unittest
from unittest.mock import patch

from backend import config
from backend.adapters.auth.workspace_token import (
    SnapshotHealth,
    WorkspaceTokenAuthBackend,
    get_snapshot_health,
    reset_snapshot_health,
)
from backend.db import connection
from backend.runtime.bootstrap_api import build_api_app


def _enterprise_storage_profile() -> config.StorageProfileConfig:
    return config.StorageProfileConfig(
        profile="enterprise",
        db_backend="postgres",
        database_url="postgresql://example/test",
        filesystem_source_of_truth=False,
        shared_postgres_enabled=False,
        isolation_mode="dedicated",
        schema_name="ccdash",
    )


def _auth_provider_config() -> config.AuthProviderConfig:
    return config.AuthProviderConfig(
        provider="oidc",
        runtime_profile="api",
        deployment_mode="hosted",
        api_bearer_token="secret-token",
        local_no_auth_enabled=False,
        clerk_publishable_key="pk_test_example",
        clerk_secret_key="sk_test_example",
        clerk_jwt_key="-----BEGIN PUBLIC KEY-----\nexample\n-----END PUBLIC KEY-----",
        oidc_issuer="https://issuer.example.com",
        oidc_audience="ccdash-api",
        oidc_client_id="client-id",
        oidc_client_secret="client-secret",
        oidc_callback_url="https://ccdash.example.com/auth/callback",
        oidc_jwks_url="https://issuer.example.com/.well-known/jwks.json",
    )


def _probe_payload(app: object, path: str) -> tuple[int, dict]:
    route = next(r for r in app.routes if getattr(r, "path", None) == path)
    response = route.endpoint(types.SimpleNamespace(), None)
    return response.status_code, json.loads(response.body.decode("utf-8"))


def _api_app():
    app = build_api_app()
    app.state.runtime_container.storage_profile = _enterprise_storage_profile()
    app.state.runtime_container.migration_status = "applied"
    app.state.runtime_container.auth_config = _auth_provider_config()
    return app


class _BrokenPool:
    """asyncpg-Pool-shaped object whose fetch fails.

    Stands in for the real failure the node measured. It is deliberately NOT an
    ``aiosqlite.Connection``, so ``_reload_snapshot`` takes the asyncpg arm.
    """

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def fetch(self, *_a, **_kw):
        raise self._exc


class _LegacyPool:
    """A Pool-shaped object with NO ``fetch`` at all.

    Reproduces the shape of the original bug from the other direction: if the
    code ever regressed to the aiosqlite idiom, ``async with pool.execute(...)``
    would raise TypeError here rather than silently working.
    """

    async def execute(self, *_a, **_kw):  # pragma: no cover - shape only
        return "SELECT 0"


class SnapshotHealthRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_snapshot_health()

    def tearDown(self) -> None:
        reset_snapshot_health()

    def test_fresh_record_reports_nothing_attempted(self) -> None:
        h = SnapshotHealth()
        self.assertFalse(h.ever_loaded)
        self.assertIsNone(h.last_attempt_at)
        self.assertIsNone(h.last_error_class)
        self.assertEqual(h.consecutive_failures, 0)
        self.assertIsNone(h.active_token_count)

    def test_failure_records_exception_CLASS_and_never_the_message(self) -> None:
        """A DSN/password can appear in a driver's exception text; this record is
        serialised into an HTTP health payload, so only the class name is kept."""
        secret_ish = (
            "connection failed: postgresql://ccdash:SUPERSECRETPW@10.0.0.1:5432/db"
        )
        h = SnapshotHealth()
        h.record_failure(RuntimeError(secret_ish))

        self.assertEqual(h.last_error_class, "RuntimeError")
        serialised = json.dumps(h.as_dict())
        self.assertNotIn("SUPERSECRETPW", serialised)
        self.assertNotIn("postgresql://", serialised)
        self.assertNotIn(secret_ish, serialised)

    def test_consecutive_failures_accumulate_then_reset_on_success(self) -> None:
        h = SnapshotHealth()
        h.record_failure(TypeError("x"))
        h.record_failure(TypeError("x"))
        self.assertEqual(h.consecutive_failures, 2)
        self.assertFalse(h.ever_loaded)

        h.record_success(4)
        self.assertEqual(h.consecutive_failures, 0)
        self.assertTrue(h.ever_loaded)
        self.assertEqual(h.active_token_count, 4)
        self.assertIsNone(h.last_error_class)

    def test_success_then_failure_keeps_ever_loaded_true(self) -> None:
        """The last-known-good distinction: a later failure must not erase the
        fact that the snapshot HAS worked, because that is what separates
        'degraded, serving stale' (warn) from 'never worked' (fail)."""
        h = SnapshotHealth()
        h.record_success(2)
        h.record_failure(TypeError("boom"))
        self.assertTrue(h.ever_loaded)
        self.assertEqual(h.last_error_class, "TypeError")
        self.assertEqual(h.consecutive_failures, 1)


class ReloadSnapshotRecordsHealthTests(unittest.IsolatedAsyncioTestCase):
    """Integration: the real _reload_snapshot must feed the health record."""

    def setUp(self) -> None:
        reset_snapshot_health()

    def tearDown(self) -> None:
        reset_snapshot_health()

    async def test_asyncpg_fetch_failure_is_recorded_not_swallowed_silently(self) -> None:
        pool = _BrokenPool(TypeError("'coroutine' object is not an async CM"))
        backend = WorkspaceTokenAuthBackend(get_db=lambda: _aw(pool))

        await backend._reload_snapshot()

        h = get_snapshot_health()
        self.assertEqual(h.last_error_class, "TypeError")
        self.assertEqual(h.consecutive_failures, 1)
        self.assertFalse(h.ever_loaded)
        self.assertIsNotNone(h.last_attempt_at)

    async def test_missing_fetch_attribute_is_also_recorded(self) -> None:
        backend = WorkspaceTokenAuthBackend(get_db=lambda: _aw(_LegacyPool()))

        await backend._reload_snapshot()

        h = get_snapshot_health()
        self.assertIsNotNone(h.last_error_class)
        self.assertFalse(h.ever_loaded)

    async def test_successful_load_records_token_count(self) -> None:
        class _OkPool:
            async def fetch(self, *_a, **_kw):
                return [("ws", "tid", "proj", "admin", "$argon2id$fake")]

        backend = WorkspaceTokenAuthBackend(get_db=lambda: _aw(_OkPool()))
        await backend._reload_snapshot()

        h = get_snapshot_health()
        self.assertTrue(h.ever_loaded)
        self.assertEqual(h.active_token_count, 1)
        self.assertIsNone(h.last_error_class)


async def _aw(value):
    return value


class TokenSnapshotReadinessProbeTests(unittest.TestCase):
    """The probe ladder, exercised through the real /api/health endpoints."""

    def setUp(self) -> None:
        reset_snapshot_health()

    def tearDown(self) -> None:
        reset_snapshot_health()

    def test_token_snapshot_is_a_required_check_on_the_api_profile(self) -> None:
        app = _api_app()
        with patch.object(connection, "_connection", object()):
            _, payload = _probe_payload(app, "/api/health/ready")
        self.assertIn("token_snapshot", payload["requiredReadinessChecks"])

    def test_never_attempted_is_ready(self) -> None:
        """ANTI-DEADLOCK GUARD. The snapshot loads on the first authenticated
        request, and readiness gates `compose up --wait`. If this test fails the
        api profile cannot start at all."""
        app = _api_app()
        with patch.object(connection, "_connection", object()):
            status_code, payload = _probe_payload(app, "/api/health/ready")

        self.assertEqual(status_code, 200)
        checks = {c["code"]: c for c in payload["checks"]}
        self.assertEqual(checks["token_snapshot"]["status"], "pass")
        self.assertIn("has not been loaded yet", checks["token_snapshot"]["summary"])

    def test_attempted_and_never_succeeded_fails_readiness_503(self) -> None:
        """The broken-on-PG signature: this is the state the node was filed for."""
        get_snapshot_health().record_failure(TypeError("asyncpg idiom"))

        app = _api_app()
        with patch.object(connection, "_connection", object()):
            status_code, payload = _probe_payload(app, "/api/health/ready")

        self.assertEqual(status_code, 503)
        self.assertEqual(payload["status"], "fail")
        self.assertFalse(payload["ready"])
        self.assertIn("token_snapshot", payload["reasonCodes"])
        check = {c["code"]: c for c in payload["checks"]}["token_snapshot"]
        self.assertEqual(check["status"], "fail")
        self.assertIn("NEVER loaded successfully", check["summary"])
        self.assertEqual(check["data"]["lastErrorClass"], "TypeError")

    def test_loaded_then_failing_warns_and_stays_ready(self) -> None:
        """Serving a last-known-good snapshot is degraded, not dead — a
        transient DB blip must not 503 a working API."""
        h = get_snapshot_health()
        h.record_success(3)
        h.record_failure(TimeoutError("blip"))

        app = _api_app()
        with patch.object(connection, "_connection", object()):
            status_code, payload = _probe_payload(app, "/api/health/ready")

        self.assertEqual(status_code, 200)
        check = {c["code"]: c for c in payload["checks"]}["token_snapshot"]
        self.assertEqual(check["status"], "warn")
        self.assertIn("last-known-good", check["summary"])

    def test_zero_tokens_passes_but_says_every_request_will_401(self) -> None:
        """0 rows is a legitimate state, NOT an error — but it is also exactly
        what the swallowed bug looked like from outside, so it is reported
        distinctly rather than conflated."""
        get_snapshot_health().record_success(0)

        app = _api_app()
        with patch.object(connection, "_connection", object()):
            status_code, payload = _probe_payload(app, "/api/health/ready")

        self.assertEqual(status_code, 200)
        check = {c["code"]: c for c in payload["checks"]}["token_snapshot"]
        self.assertEqual(check["status"], "pass")
        self.assertEqual(check["data"]["activeTokenCount"], 0)
        self.assertIn("401", check["detail"])

    def test_health_detail_exposes_token_snapshot_section(self) -> None:
        h = get_snapshot_health()
        h.record_success(2)

        app = _api_app()
        with patch.object(connection, "_connection", object()):
            status_code, payload = _probe_payload(app, "/api/health/detail")

        self.assertEqual(status_code, 200)
        snap = payload["detail"]["auth"]["tokenSnapshot"]
        self.assertTrue(snap["everLoaded"])
        self.assertEqual(snap["activeTokenCount"], 2)
        self.assertIsNone(snap["lastErrorClass"])
        self.assertEqual(snap["consecutiveFailures"], 0)


if __name__ == "__main__":
    unittest.main()
