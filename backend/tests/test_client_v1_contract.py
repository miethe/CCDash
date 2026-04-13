"""Contract tests for the versioned client API v1 endpoints.

Verifies JSON envelope shape, paginated envelope fields, 404 behaviour for
unknown IDs, and validation rejection for malformed query params.  All tests
are designed to pass with an empty database — they check structure, not data.

Setup: the test runtime is bootstrapped with a throw-away SQLite DB via a
temp file so the app lifecycle (migrations, ports, job adapter) can run fully
without depending on any existing data on disk.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.runtime.bootstrap import build_runtime_app


class TestClientV1Contract(unittest.TestCase):
    """Verify JSON shape and envelope contracts for /api/v1/ endpoints."""

    # ------------------------------------------------------------------
    # Class-level setup — one app instance shared across all tests
    # ------------------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        # Create a throwaway SQLite file so the full lifespan (migrations,
        # core ports, job adapter) can complete without touching real data.
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
            patch("backend.adapters.jobs.runtime.file_watcher.start", new_callable=lambda: lambda: AsyncMock()),
            patch("backend.adapters.jobs.runtime.file_watcher.stop", new_callable=lambda: lambda: AsyncMock()),
            patch("backend.runtime_ports.project_manager.get_active_project", return_value=None),
        ]
        for p in cls._patches:
            p.start()

        # Enter the TestClient context once; this triggers the app lifespan.
        cls._tc = TestClient(cls._app, raise_server_exceptions=False)
        cls._tc.__enter__()
        cls.client = cls._tc

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tc.__exit__(None, None, None)
        for p in reversed(cls._patches):
            p.stop()
        cls._env_patcher.stop()
        try:
            os.unlink(cls._tmpdb.name)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _assert_base_envelope(self, body: dict) -> None:
        """All standard envelopes must have status, data, and meta."""
        self.assertIn("status", body)
        self.assertIn("data", body)
        self.assertIn("meta", body)

    def _assert_meta_fields(self, meta: dict) -> None:
        """Standard meta block must include generated_at, instance_id, request_id."""
        for field in ("generated_at", "instance_id", "request_id"):
            self.assertIn(field, meta, f"meta missing required field: {field}")

    def _assert_paginated_meta_fields(self, meta: dict) -> None:
        """Paginated meta must include the standard pagination fields."""
        self._assert_meta_fields(meta)
        for field in ("total", "offset", "limit", "has_more"):
            self.assertIn(field, meta, f"paginated meta missing required field: {field}")

    # ------------------------------------------------------------------
    # Instance
    # ------------------------------------------------------------------

    def test_instance_returns_ok_status(self) -> None:
        resp = self.client.get("/api/v1/instance")
        self.assertEqual(resp.status_code, 200)

    def test_instance_envelope_has_required_top_level_fields(self) -> None:
        body = self.client.get("/api/v1/instance").json()
        self._assert_base_envelope(body)
        self.assertEqual(body["status"], "ok")

    def test_instance_data_contains_required_dto_fields(self) -> None:
        body = self.client.get("/api/v1/instance").json()
        data = body["data"]
        for field in ("instance_id", "version", "environment", "db_backend", "capabilities", "server_time"):
            self.assertIn(field, data, f"InstanceMetaDTO missing field: {field}")

    def test_instance_capabilities_is_a_list(self) -> None:
        body = self.client.get("/api/v1/instance").json()
        self.assertIsInstance(body["data"]["capabilities"], list)

    def test_instance_meta_contains_required_fields(self) -> None:
        body = self.client.get("/api/v1/instance").json()
        self._assert_meta_fields(body["meta"])

    # ------------------------------------------------------------------
    # Project status
    # ------------------------------------------------------------------

    def test_project_status_returns_200(self) -> None:
        resp = self.client.get("/api/v1/project/status")
        self.assertEqual(resp.status_code, 200)

    def test_project_status_envelope_has_required_fields(self) -> None:
        body = self.client.get("/api/v1/project/status").json()
        self._assert_base_envelope(body)

    def test_project_status_meta_has_required_fields(self) -> None:
        body = self.client.get("/api/v1/project/status").json()
        self._assert_meta_fields(body["meta"])

    # ------------------------------------------------------------------
    # Workflow failures
    # ------------------------------------------------------------------

    def test_workflow_failures_returns_200(self) -> None:
        resp = self.client.get("/api/v1/workflows/failures")
        self.assertEqual(resp.status_code, 200)

    def test_workflow_failures_envelope_has_required_fields(self) -> None:
        body = self.client.get("/api/v1/workflows/failures").json()
        self._assert_base_envelope(body)

    def test_workflow_failures_meta_has_required_fields(self) -> None:
        body = self.client.get("/api/v1/workflows/failures").json()
        self._assert_meta_fields(body["meta"])

    # ------------------------------------------------------------------
    # Features list
    # ------------------------------------------------------------------

    def test_features_list_returns_200(self) -> None:
        resp = self.client.get("/api/v1/features?limit=10&offset=0")
        self.assertEqual(resp.status_code, 200)

    def test_features_list_data_is_a_list(self) -> None:
        body = self.client.get("/api/v1/features?limit=10&offset=0").json()
        self.assertIsInstance(body["data"], list)

    def test_features_list_paginated_meta_fields(self) -> None:
        body = self.client.get("/api/v1/features?limit=10&offset=0").json()
        self._assert_paginated_meta_fields(body["meta"])

    def test_features_list_meta_reflects_requested_limit_and_offset(self) -> None:
        body = self.client.get("/api/v1/features?limit=7&offset=3").json()
        self.assertEqual(body["meta"]["limit"], 7)
        self.assertEqual(body["meta"]["offset"], 3)

    # ------------------------------------------------------------------
    # Feature detail — not found
    # ------------------------------------------------------------------

    def test_feature_detail_returns_404_for_unknown_id(self) -> None:
        resp = self.client.get("/api/v1/features/NONEXISTENT-FEATURE-ID-ZZZZZ")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # Feature sessions — not found
    # ------------------------------------------------------------------

    def test_feature_sessions_returns_404_for_unknown_feature(self) -> None:
        resp = self.client.get("/api/v1/features/NONEXISTENT-FEATURE-ID-ZZZZZ/sessions")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # Feature documents — not found
    # ------------------------------------------------------------------

    def test_feature_documents_returns_404_for_unknown_feature(self) -> None:
        resp = self.client.get("/api/v1/features/NONEXISTENT-FEATURE-ID-ZZZZZ/documents")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # Sessions list
    # ------------------------------------------------------------------

    def test_sessions_list_returns_200(self) -> None:
        resp = self.client.get("/api/v1/sessions?limit=10&offset=0")
        self.assertEqual(resp.status_code, 200)

    def test_sessions_list_data_is_a_list(self) -> None:
        body = self.client.get("/api/v1/sessions?limit=10&offset=0").json()
        self.assertIsInstance(body["data"], list)

    def test_sessions_list_paginated_meta_fields(self) -> None:
        body = self.client.get("/api/v1/sessions?limit=10&offset=0").json()
        self._assert_paginated_meta_fields(body["meta"])

    def test_sessions_list_meta_reflects_requested_limit_and_offset(self) -> None:
        body = self.client.get("/api/v1/sessions?limit=5&offset=0").json()
        self.assertEqual(body["meta"]["limit"], 5)
        self.assertEqual(body["meta"]["offset"], 0)

    # ------------------------------------------------------------------
    # Session detail — not found
    # ------------------------------------------------------------------

    def test_session_detail_returns_404_for_unknown_id(self) -> None:
        resp = self.client.get("/api/v1/sessions/NONEXISTENT-SESSION-ID-ZZZZZ")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # Session search — validation rejection
    # ------------------------------------------------------------------

    def test_session_search_rejects_query_shorter_than_min_length(self) -> None:
        resp = self.client.get("/api/v1/sessions/search?q=x")
        self.assertEqual(resp.status_code, 422)

    def test_session_search_accepts_valid_query_and_returns_200(self) -> None:
        resp = self.client.get("/api/v1/sessions/search?q=test+query")
        self.assertEqual(resp.status_code, 200)

    def test_session_search_returns_envelope_with_data_and_meta(self) -> None:
        body = self.client.get("/api/v1/sessions/search?q=test+query").json()
        self.assertIn("data", body)
        self.assertIn("meta", body)

    def test_session_search_data_contains_items_field(self) -> None:
        # The search endpoint wraps a SessionSemanticSearchResponse DTO in
        # data — not a bare list.  Verify the items field is present.
        body = self.client.get("/api/v1/sessions/search?q=test+query").json()
        data = body["data"]
        self.assertIn("items", data, "search data DTO must have an 'items' field")
        self.assertIsInstance(data["items"], list)

    # ------------------------------------------------------------------
    # Session drilldown — not found
    # ------------------------------------------------------------------

    def test_session_drilldown_returns_404_for_unknown_session(self) -> None:
        resp = self.client.get("/api/v1/sessions/NONEXISTENT-SESSION-ID-ZZZZZ/drilldown?concern=sentiment")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # Session family — not found
    # ------------------------------------------------------------------

    def test_session_family_returns_404_for_unknown_session(self) -> None:
        resp = self.client.get("/api/v1/sessions/NONEXISTENT-SESSION-ID-ZZZZZ/family")
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # AAR report
    # ------------------------------------------------------------------

    def test_aar_report_with_unknown_feature_returns_parseable_json(self) -> None:
        resp = self.client.post("/api/v1/reports/aar?feature_id=NONEXISTENT-FEATURE-ID-ZZZZZ")
        # Must not raise — response body must be parseable JSON.
        body = resp.json()
        self.assertIsNotNone(body)

    def test_aar_report_response_contains_status_field(self) -> None:
        resp = self.client.post("/api/v1/reports/aar?feature_id=NONEXISTENT-FEATURE-ID-ZZZZZ")
        body = resp.json()
        # Graceful data return (200 with error status) or 404 — either way
        # the top-level status field must be present.
        self.assertIn("status", body)

    # ------------------------------------------------------------------
    # Router registration sanity check
    # ------------------------------------------------------------------

    def test_openapi_schema_exposes_all_expected_v1_paths(self) -> None:
        paths = self._app.openapi()["paths"]
        expected = [
            "/api/v1/instance",
            "/api/v1/project/status",
            "/api/v1/workflows/failures",
            "/api/v1/features",
            "/api/v1/features/{feature_id}",
            "/api/v1/features/{feature_id}/sessions",
            "/api/v1/features/{feature_id}/documents",
            "/api/v1/sessions/search",
            "/api/v1/sessions",
            "/api/v1/sessions/{session_id}",
            "/api/v1/sessions/{session_id}/drilldown",
            "/api/v1/sessions/{session_id}/family",
            "/api/v1/reports/aar",
        ]
        for path in expected:
            self.assertIn(path, paths, f"Expected path not in OpenAPI schema: {path}")


if __name__ == "__main__":
    unittest.main()
