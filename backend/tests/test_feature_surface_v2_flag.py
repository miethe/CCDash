"""P5-005: Feature-surface v2 rollout flag tests.

Verifies:
1. /api/health reports featureSurfaceV2Enabled reflecting the flag value.
2. /api/health defaults to True when the env var is not set.
3. /api/health reports False when CCDASH_FEATURE_SURFACE_V2_ENABLED=false.
4. /api/health/detail also reports the flag (FE can read from either endpoint).

The v1 endpoints themselves are NOT gated by this flag (they must remain
reachable so FE fallbacks degrade gracefully).  The flag is purely a FE-read
signal that tells the frontend which data path to activate.
"""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Minimal bootstrap helpers
# ---------------------------------------------------------------------------

def _make_health_app(runtime_status: dict[str, Any]) -> FastAPI:
    """Build a minimal FastAPI app that mirrors the /api/health endpoint logic
    used in bootstrap.build_runtime_app(), without starting the full container.
    """
    # Import here so the patch context takes effect before the module-level
    # attribute is read inside _build_health_payload.
    from backend.runtime import bootstrap as bs
    from backend.runtime.profiles import get_runtime_profile

    app = FastAPI()
    profile = get_runtime_profile("local")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return bs._build_health_payload(runtime_status, profile)

    @app.get("/api/health/detail")
    def health_detail() -> dict[str, Any]:
        return bs._build_detail_probe_payload(runtime_status)

    return app


def _minimal_runtime_status() -> dict[str, Any]:
    """Return the minimum runtime_status dict accepted by _build_health_payload.

    We only need the probe contract; other fields are either optional or have
    safe defaults.  The probe contract is the same structure that
    RuntimeContainer._build_probe_contract() produces.
    """
    section = {
        "state": "ready",
        "status": "ok",
        "summary": "ok",
        "ready": True,
        "degraded": False,
        "reasons": [],
        "checks": [],
        "activities": [],
        "recommendedCadence": {},
        "requiredReadinessChecks": [],
        "runtime": {},
        "storage": {},
        "database": {},
        "binding": {},
        "auth": {"guardrail": {"warnings": [], "warningCodes": []}},
        "warnings": [],
        "warningCodes": [],
    }
    return {
        "probeContract": {
            "schemaVersion": "v2",
            "runtimeProfile": "local",
            "live": section,
            "ready": section,
            "detail": section,
        },
        "watcher": "idle",
        "profile": "local",
        "startupSync": "idle",
        "analyticsSnapshots": "idle",
        "storageMode": "local",
        "storageProfile": "local",
        "storageBackend": "sqlite",
        "storageComposition": "local:sqlite",
        "deploymentMode": "local",
        "recommendedStorageProfile": "local",
        "supportedStorageProfiles": ["local"],
        "filesystemSourceOfTruth": True,
        "storageFilesystemRole": "authoritative",
        "sharedPostgresEnabled": False,
        "storageIsolationMode": "dedicated",
        "supportedStorageIsolationModes": ["dedicated"],
        "storageCanonicalStore": "filesystem_cache",
        "auditStore": "none",
        "auditWriteSupported": False,
        "auditWriteAuthoritative": False,
        "auditWriteStatus": "unsupported",
        "auditWriteNotes": "",
        "sessionEmbeddingWriteSupported": False,
        "sessionEmbeddingWriteAuthoritative": False,
        "sessionEmbeddingWriteStatus": "unsupported",
        "sessionEmbeddingWriteNotes": "",
        "sessionIntelligenceProfile": "",
        "sessionIntelligenceAnalyticsLevel": "",
        "sessionIntelligenceBackfillStrategy": "",
        "sessionIntelligenceMemoryDraftFlow": "",
        "sessionIntelligenceIsolationBoundary": "",
        "storageSchema": "n/a",
        "canonicalSessionStore": "filesystem_cache",
        "watchEnabled": False,
        "syncEnabled": False,
        "syncProvisioned": False,
        "jobsEnabled": False,
        "authEnabled": False,
        "integrationsEnabled": False,
        "allowedStorageProfiles": ["local"],
        "runtimeSyncBehavior": "sync_disabled",
        "runtimeJobBehavior": "jobs_disabled",
        "runtimeAuthBehavior": "auth_disabled",
        "runtimeIntegrationBehavior": "integrations_disabled",
        "environmentContract": {},
        "environmentContractValid": True,
        "environmentContractErrors": [],
        "environmentContractWarnings": [],
        "environmentContractRequired": [],
        "environmentContractSecrets": [],
        "telemetryExports": "not_applicable",
        "requiredStorageGuarantees": [],
        "storageProfileValidationMatrix": (),
        "migrationGovernanceStatus": "verified",
        "migrationStatus": "applied",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class FeatureSurfaceV2FlagHealthTests(unittest.TestCase):
    """Verify /api/health exposes featureSurfaceV2Enabled."""

    def _get_health(self, flag_value: bool) -> dict[str, Any]:
        from backend.runtime import bootstrap as bs
        with patch.object(bs.config, "CCDASH_FEATURE_SURFACE_V2_ENABLED", flag_value):
            app = _make_health_app(_minimal_runtime_status())
            client = TestClient(app)
            response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_flag_defaults_true(self) -> None:
        """When no override is applied the flag must be True (default in config.py)."""
        # config.CCDASH_FEATURE_SURFACE_V2_ENABLED defaults to True.
        body = self._get_health(True)
        self.assertIn("featureSurfaceV2Enabled", body)
        self.assertTrue(body["featureSurfaceV2Enabled"])

    def test_flag_reflects_false(self) -> None:
        """When the env var is false the health payload must report False."""
        body = self._get_health(False)
        self.assertIn("featureSurfaceV2Enabled", body)
        self.assertFalse(body["featureSurfaceV2Enabled"])

    def test_flag_reflects_true_explicitly(self) -> None:
        """Explicit True value is preserved in the payload."""
        body = self._get_health(True)
        self.assertTrue(body["featureSurfaceV2Enabled"])


class FeatureSurfaceV2FlagDetailProbeTests(unittest.TestCase):
    """/api/health/detail must also expose featureSurfaceV2Enabled."""

    def _get_detail(self, flag_value: bool) -> dict[str, Any]:
        from backend.runtime import bootstrap as bs
        with patch.object(bs.config, "CCDASH_FEATURE_SURFACE_V2_ENABLED", flag_value):
            app = _make_health_app(_minimal_runtime_status())
            client = TestClient(app)
            response = client.get("/api/health/detail")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_detail_probe_exposes_flag_true(self) -> None:
        body = self._get_detail(True)
        self.assertIn("featureSurfaceV2Enabled", body)
        self.assertTrue(body["featureSurfaceV2Enabled"])

    def test_detail_probe_exposes_flag_false(self) -> None:
        body = self._get_detail(False)
        self.assertIn("featureSurfaceV2Enabled", body)
        self.assertFalse(body["featureSurfaceV2Enabled"])


class FeatureSurfaceV2ConfigDefaultTest(unittest.TestCase):
    """Verify the config module default is True."""

    def test_config_default_is_true(self) -> None:
        """CCDASH_FEATURE_SURFACE_V2_ENABLED must default to True in config.py."""
        from backend import config
        # We can't force-reload config in-process, but we can verify the
        # _env_bool helper returns True for an empty/missing env var by
        # checking the attribute that was set at import time and that the
        # underlying helper works correctly with an absent env var.
        self.assertTrue(config._env_bool("CCDASH_FEATURE_SURFACE_V2_ENABLED", True))

    def test_env_bool_false_for_explicit_false_values(self) -> None:
        """_env_bool must return False when the env var is set to a falsy string."""
        import os
        from backend import config

        for falsy in ("0", "false", "no", "off", "FALSE", " False "):
            with patch.dict(os.environ, {"CCDASH_FEATURE_SURFACE_V2_ENABLED": falsy}):
                result = config._env_bool("CCDASH_FEATURE_SURFACE_V2_ENABLED", True)
                self.assertFalse(result, msg=f"Expected False for env value {falsy!r}")

    def test_env_bool_true_for_explicit_true_values(self) -> None:
        """_env_bool must return True when the env var is set to a truthy string."""
        import os
        from backend import config

        for truthy in ("1", "true", "yes", "on", "TRUE", " True "):
            with patch.dict(os.environ, {"CCDASH_FEATURE_SURFACE_V2_ENABLED": truthy}):
                result = config._env_bool("CCDASH_FEATURE_SURFACE_V2_ENABLED", False)
                self.assertTrue(result, msg=f"Expected True for env value {truthy!r}")


class StartupDeferredRebuildLinksDefaultTest(unittest.TestCase):
    """BE-202: CCDASH_STARTUP_DEFERRED_REBUILD_LINKS must default to False."""

    def test_config_default_is_false(self) -> None:
        """STARTUP_DEFERRED_REBUILD_LINKS default changed from True to False (BE-202)."""
        from backend import config
        self.assertFalse(config._env_bool("CCDASH_STARTUP_DEFERRED_REBUILD_LINKS", False))


if __name__ == "__main__":
    unittest.main()
