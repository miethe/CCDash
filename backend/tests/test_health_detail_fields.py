"""T2-003: Integration tests for /api/health/detail extended fields + /api/health regression.

Verifies:
1. /api/health/detail (via _build_detail_probe_payload) exposes registry, db, retention
   with correct types and sub-keys.
2. After a warm start with a seeded test DB: registry.project_count matches row count,
   db.size_bytes > 0, retention.enabled is a bool.
3. A sub-builder failure (monkeypatched to raise) yields null fields on /api/health/detail,
   not a 500.
4. /api/health legacy "db" key is a STRING ("connected"/"disconnected"), not a dict.
"""
from __future__ import annotations

import sqlite3
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared runtime_status builder
# ---------------------------------------------------------------------------

def _minimal_runtime_status() -> dict[str, Any]:
    """Return the minimum runtime_status dict accepted by both payload builders."""
    section: dict[str, Any] = {
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
# App helpers
# ---------------------------------------------------------------------------

def _make_detail_app(runtime_status: dict[str, Any]):
    """Build a minimal FastAPI app exposing /api/health/detail via the real builder."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from backend.runtime import bootstrap as bs

    app = FastAPI()

    @app.get("/api/health/detail")
    def health_detail() -> JSONResponse:
        return JSONResponse(bs._build_detail_probe_payload(runtime_status))

    return app


def _make_health_app(runtime_status: dict[str, Any]):
    """Build a minimal FastAPI app exposing /api/health via the real builder."""
    from fastapi import FastAPI
    from backend.runtime import bootstrap as bs
    from backend.runtime.profiles import get_runtime_profile

    app = FastAPI()
    profile = get_runtime_profile("local")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return bs._build_health_payload(runtime_status, profile)

    return app


# ---------------------------------------------------------------------------
# DB seed helper
# ---------------------------------------------------------------------------

def _seed_projects_db(db_path: str, n: int) -> None:
    """Insert *n* fake project rows into a SQLite test DB."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            description TEXT,
            repo_url TEXT,
            agent_platforms_json TEXT,
            plan_docs_path TEXT,
            sessions_path TEXT,
            progress_path TEXT,
            path_config_json TEXT,
            test_config_json TEXT,
            skillmeat_json TEXT,
            display_json TEXT,
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    for i in range(n):
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, path, is_active) VALUES (?, ?, ?, 0)",
            (f"proj-{i}", f"Project {i}", f"/tmp/proj-{i}"),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Helper: call _build_detail_probe_payload directly with patched config
# ---------------------------------------------------------------------------

def _detail_payload(**config_overrides: Any) -> dict[str, Any]:
    from backend.runtime import bootstrap as bs

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "ccdash_cache.db"
        patches = {
            "DB_PATH": db_path,
            "DB_BACKEND": "sqlite",
            "RETENTION_PRUNE_ENABLED": False,
        }
        patches.update(config_overrides)
        with patch.multiple(bs.config, **patches):
            return bs._build_detail_probe_payload(_minimal_runtime_status())


# ---------------------------------------------------------------------------
# Tests: /api/health/detail key presence and types
# ---------------------------------------------------------------------------

class HealthDetailFieldsPresenceTests(unittest.TestCase):
    """T2-003: registry/db/retention top-level keys present in /api/health/detail."""

    def test_registry_key_present(self) -> None:
        self.assertIn("registry", _detail_payload())

    def test_db_key_present(self) -> None:
        self.assertIn("db", _detail_payload())

    def test_retention_key_present(self) -> None:
        self.assertIn("retention", _detail_payload())

    def test_registry_sub_keys(self) -> None:
        reg = _detail_payload()["registry"]
        self.assertIn("project_count", reg)
        self.assertIn("last_flush_status", reg)

    def test_db_sub_keys(self) -> None:
        db = _detail_payload()["db"]
        self.assertIn("size_bytes", db)
        self.assertIn("freelist_bytes", db)
        self.assertIn("backend", db)

    def test_retention_sub_keys(self) -> None:
        ret = _detail_payload()["retention"]
        self.assertIn("last_run", ret)
        self.assertIn("enabled", ret)

    def test_registry_project_count_is_int_or_null(self) -> None:
        count = _detail_payload()["registry"]["project_count"]
        self.assertTrue(count is None or isinstance(count, int))

    def test_db_backend_field_is_sqlite(self) -> None:
        self.assertEqual(_detail_payload()["db"]["backend"], "sqlite")

    def test_retention_enabled_is_bool(self) -> None:
        self.assertIsInstance(_detail_payload()["retention"]["enabled"], bool)

    def test_retention_enabled_reflects_config(self) -> None:
        self.assertFalse(_detail_payload(RETENTION_PRUNE_ENABLED=False)["retention"]["enabled"])
        self.assertTrue(_detail_payload(RETENTION_PRUNE_ENABLED=True)["retention"]["enabled"])


# ---------------------------------------------------------------------------
# Tests: warm-start assertions
# ---------------------------------------------------------------------------

class HealthDetailFieldsWarmStartTests(unittest.TestCase):
    """T2-003: warm-start — count/size match real DB state."""

    def test_project_count_matches_db_rows(self) -> None:
        from backend.runtime import bootstrap as bs

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ccdash_cache.db"
            _seed_projects_db(str(db_path), 3)
            with patch.multiple(
                bs.config,
                DB_PATH=db_path,
                DB_BACKEND="sqlite",
                RETENTION_PRUNE_ENABLED=False,
            ):
                payload = bs._build_detail_probe_payload(_minimal_runtime_status())

        self.assertEqual(payload["registry"]["project_count"], 3)
        self.assertEqual(payload["registry"]["last_flush_status"], "ok")

    def test_db_size_bytes_positive_after_write(self) -> None:
        from backend.runtime import bootstrap as bs

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ccdash_cache.db"
            _seed_projects_db(str(db_path), 1)
            with patch.multiple(
                bs.config,
                DB_PATH=db_path,
                DB_BACKEND="sqlite",
                RETENTION_PRUNE_ENABLED=False,
            ):
                payload = bs._build_detail_probe_payload(_minimal_runtime_status())

        size = payload["db"]["size_bytes"]
        self.assertIsNotNone(size)
        assert isinstance(size, int)
        self.assertGreater(size, 0)


# ---------------------------------------------------------------------------
# Tests: sub-builder failure isolation (null-on-failure, not 500)
# ---------------------------------------------------------------------------

class HealthDetailFieldsFailureIsolationTests(unittest.TestCase):
    """T2-003: sub-call failure → null fields on /api/health/detail, not 500."""

    def test_registry_failure_yields_null_count(self) -> None:
        from backend.runtime import bootstrap as bs
        from backend.db.repositories import projects as projects_module

        def _boom(self: Any) -> int:
            raise RuntimeError("injected registry failure")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ccdash_cache.db"
            # Seed the projects table so ensure_table() passes its guard and
            # the injected count() failure is what triggers "failed" status.
            _seed_projects_db(str(db_path), 0)
            with patch.multiple(
                bs.config,
                DB_PATH=db_path,
                DB_BACKEND="sqlite",
                RETENTION_PRUNE_ENABLED=False,
            ):
                with patch.object(projects_module.SqliteProjectRepository, "count", _boom):
                    payload = bs._build_detail_probe_payload(_minimal_runtime_status())

        self.assertIsNone(payload["registry"]["project_count"])
        self.assertEqual(payload["registry"]["last_flush_status"], "failed")

    def test_db_size_failure_yields_null(self) -> None:
        from backend.runtime import bootstrap as bs

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ccdash_cache.db"
            with patch.multiple(
                bs.config,
                DB_PATH=db_path,
                DB_BACKEND="sqlite",
                RETENTION_PRUNE_ENABLED=False,
            ):
                with patch("os.path.getsize", side_effect=OSError("injected getsize failure")):
                    with patch("sqlite3.connect", side_effect=RuntimeError("injected connect failure")):
                        payload = bs._build_detail_probe_payload(_minimal_runtime_status())

        self.assertIsNone(payload["db"]["size_bytes"])
        self.assertIsNone(payload["db"]["freelist_bytes"])
        self.assertEqual(payload["db"]["backend"], "sqlite")

    def test_detail_endpoint_returns_200_when_registry_fails(self) -> None:
        from backend.runtime import bootstrap as bs
        from backend.db.repositories import projects as projects_module

        def _boom(self: Any) -> int:
            raise RuntimeError("injected registry failure for HTTP test")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ccdash_cache.db"
            # Seed the projects table so ensure_table() passes its guard and
            # the injected count() failure is what causes the 200-with-nulls response.
            _seed_projects_db(str(db_path), 0)
            with patch.multiple(
                bs.config,
                DB_PATH=db_path,
                DB_BACKEND="sqlite",
                RETENTION_PRUNE_ENABLED=False,
            ):
                with patch.object(projects_module.SqliteProjectRepository, "count", _boom):
                    app = _make_detail_app(_minimal_runtime_status())
                    client = TestClient(app)
                    response = client.get("/api/health/detail")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["registry"]["project_count"])

    def test_retention_last_run_null_when_never_ran(self) -> None:
        payload = _detail_payload(RETENTION_PRUNE_ENABLED=True)
        self.assertIsNone(payload["retention"]["last_run"])
        self.assertTrue(payload["retention"]["enabled"])


# ---------------------------------------------------------------------------
# Tests: /api/health/detail endpoint via TestClient (SC-3 smoke)
# ---------------------------------------------------------------------------

class HealthDetailEndpointFieldsTests(unittest.TestCase):
    """SC-3 / T2-003: /api/health/detail HTTP endpoint must expose registry, db, retention."""

    def _get_detail_response(self, **config_overrides: Any) -> dict[str, Any]:
        from backend.runtime import bootstrap as bs

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ccdash_cache.db"
            patches = {
                "DB_PATH": db_path,
                "DB_BACKEND": "sqlite",
                "RETENTION_PRUNE_ENABLED": False,
            }
            patches.update(config_overrides)
            with patch.multiple(bs.config, **patches):
                app = _make_detail_app(_minimal_runtime_status())
                client = TestClient(app)
                response = client.get("/api/health/detail")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_detail_endpoint_has_registry_key(self) -> None:
        self.assertIn("registry", self._get_detail_response())

    def test_detail_endpoint_has_db_key(self) -> None:
        self.assertIn("db", self._get_detail_response())

    def test_detail_endpoint_has_retention_key(self) -> None:
        self.assertIn("retention", self._get_detail_response())

    def test_detail_endpoint_registry_sub_fields(self) -> None:
        reg = self._get_detail_response()["registry"]
        self.assertIn("project_count", reg)
        self.assertIn("last_flush_status", reg)

    def test_detail_endpoint_db_sub_fields(self) -> None:
        db = self._get_detail_response()["db"]
        self.assertIn("size_bytes", db)
        self.assertIn("freelist_bytes", db)
        self.assertIn("backend", db)
        self.assertEqual(db["backend"], "sqlite")

    def test_detail_endpoint_retention_sub_fields(self) -> None:
        ret = self._get_detail_response()["retention"]
        self.assertIn("last_run", ret)
        self.assertIn("enabled", ret)
        self.assertIsInstance(ret["enabled"], bool)


# ---------------------------------------------------------------------------
# Regression: /api/health legacy "db" key must remain a string
# ---------------------------------------------------------------------------

class HealthLegacyDbKeyRegressionTests(unittest.TestCase):
    """Regression: /api/health 'db' key must be a string, not a dict (FE contract)."""

    def test_health_db_key_is_string_not_dict(self) -> None:
        from backend.runtime import bootstrap as bs

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ccdash_cache.db"
            with patch.multiple(
                bs.config,
                DB_PATH=db_path,
                DB_BACKEND="sqlite",
                RETENTION_PRUNE_ENABLED=False,
            ):
                app = _make_health_app(_minimal_runtime_status())
                client = TestClient(app)
                response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        db_val = response.json()["db"]
        self.assertIsInstance(db_val, str, f"Expected string, got {type(db_val)}: {db_val!r}")
        self.assertIn(db_val, ("connected", "disconnected"))

    def test_health_does_not_expose_new_detail_keys(self) -> None:
        """/api/health must not contain registry or retention (detail-only keys)."""
        from backend.runtime import bootstrap as bs

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ccdash_cache.db"
            with patch.multiple(
                bs.config,
                DB_PATH=db_path,
                DB_BACKEND="sqlite",
                RETENTION_PRUNE_ENABLED=False,
            ):
                app = _make_health_app(_minimal_runtime_status())
                client = TestClient(app)
                response = client.get("/api/health")

        body = response.json()
        self.assertNotIn("registry", body)
        self.assertNotIn("retention", body)


if __name__ == "__main__":
    unittest.main()
