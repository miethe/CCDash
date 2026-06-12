"""External API contract tests for /api/v1 — Phase 10 (T10-006).

Pins the shapes of:
  - Capability endpoint  → ``CapabilityV1 {api_version, capabilities, instance_id, server_time}``
  - List envelope        → ``{status, data: [], meta: {total, limit, offset, has_more, ...}}``
  - Transcript envelope  → ``SessionTranscriptPageV1 {items, cursor, limit, nextCursor}``
  - 400 on missing project_id for cross-project endpoints (T10-002)
  - Auth: no-op when CCDASH_API_TOKEN is unset; 401/403 when set (T10-004)

These tests FAIL on any field add/remove/rename in the contract shapes.  They
use a TestClient with a throw-away SQLite DB and do NOT depend on a live server
or real session data.

Running:
    backend/.venv/bin/python -m pytest backend/tests/test_external_api_contract.py -v
"""
from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from ccdash_contracts import (
    CapabilityV1,
    ClientV1Envelope,
    ClientV1PaginatedEnvelope,
    SessionTranscriptPageV1,
)
from backend.runtime.bootstrap import build_runtime_app


# ---------------------------------------------------------------------------
# Shared test infrastructure
# ---------------------------------------------------------------------------

def _make_app_and_client():
    """Build a throw-away test app + TestClient (used by setUpClass)."""
    tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmpdb.close()
    return tmpdb.name, build_runtime_app("test")


def _standard_patches():
    return [
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
        patch(
            "backend.runtime_ports.db_project_manager.get_active_project",
            return_value=None,
        ),
    ]


@contextmanager
def _api_token_set(client_config_ref, token: str = "secret-test-token"):
    """Temporarily activate CCDASH_API_TOKEN on the require_v1_auth dependency."""
    import backend.config as _cfg
    original = getattr(_cfg, "CCDASH_API_TOKEN", "")
    _cfg.CCDASH_API_TOKEN = token
    try:
        yield token
    finally:
        _cfg.CCDASH_API_TOKEN = original


# ---------------------------------------------------------------------------
# T10-001 / T10-006: Capability endpoint contract
# ---------------------------------------------------------------------------

class TestCapabilityContract(unittest.TestCase):
    """Pin the /api/v1/capabilities response shape."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()
        cls._env_patcher = patch.dict(
            os.environ,
            {"CCDASH_DB_PATH": cls._tmpdb.name, "CCDASH_DB_BACKEND": "sqlite"},
        )
        cls._env_patcher.start()
        cls._app = build_runtime_app("test")
        cls._patches = _standard_patches()
        for p in cls._patches:
            p.start()
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

    def test_capabilities_returns_200(self) -> None:
        self.assertEqual(self.client.get("/api/v1/capabilities").status_code, 200)

    def test_capabilities_envelope_has_status_data_meta(self) -> None:
        body = self.client.get("/api/v1/capabilities").json()
        for f in ("status", "data", "meta"):
            self.assertIn(f, body, f"envelope missing: {f}")
        self.assertEqual(body["status"], "ok")

    def test_capabilities_data_has_required_fields(self) -> None:
        """Pinned: CapabilityV1 must expose api_version, capabilities, instance_id, server_time."""
        data = self.client.get("/api/v1/capabilities").json()["data"]
        for f in ("api_version", "capabilities", "instance_id", "server_time"):
            self.assertIn(f, data, f"CapabilityV1 data missing field: {f}")

    def test_capabilities_api_version_is_string_1(self) -> None:
        data = self.client.get("/api/v1/capabilities").json()["data"]
        self.assertEqual(data["api_version"], "1")

    def test_capabilities_includes_cross_project(self) -> None:
        data = self.client.get("/api/v1/capabilities").json()["data"]
        self.assertIn("sessions:cross-project", data["capabilities"])

    def test_capabilities_includes_sessions_detail(self) -> None:
        data = self.client.get("/api/v1/capabilities").json()["data"]
        self.assertIn("sessions:detail", data["capabilities"])

    def test_capabilities_validates_against_contract_type(self) -> None:
        """TypeAdapter must accept the response under CapabilityV1 without error."""
        body = self.client.get("/api/v1/capabilities").json()
        parsed = TypeAdapter(ClientV1Envelope[CapabilityV1]).validate_python(body)
        self.assertIsInstance(parsed.data.capabilities, list)
        self.assertGreater(len(parsed.data.capabilities), 0)

    def test_capabilities_data_no_extra_fields(self) -> None:
        """Contract guardrail: no undocumented top-level keys in the data block."""
        data = self.client.get("/api/v1/capabilities").json()["data"]
        allowed = {"api_version", "capabilities", "instance_id", "server_time"}
        extra = set(data.keys()) - allowed
        self.assertFalse(extra, f"Unexpected extra fields: {extra}")

    def test_capabilities_meta_standard_fields(self) -> None:
        meta = self.client.get("/api/v1/capabilities").json()["meta"]
        for f in ("generated_at", "instance_id", "request_id"):
            self.assertIn(f, meta, f"meta missing: {f}")

    def test_capabilities_path_in_openapi_schema(self) -> None:
        self.assertIn("/api/v1/capabilities", self._app.openapi()["paths"])


# ---------------------------------------------------------------------------
# T10-006: Paginated list envelope contract (sessions)
# ---------------------------------------------------------------------------

class TestSessionListEnvelopeContract(unittest.TestCase):
    """Pin {status, data: [], meta: {total, limit, offset, has_more}} for the sessions list."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()
        cls._env_patcher = patch.dict(
            os.environ,
            {"CCDASH_DB_PATH": cls._tmpdb.name, "CCDASH_DB_BACKEND": "sqlite"},
        )
        cls._env_patcher.start()
        cls._app = build_runtime_app("test")
        cls._patches = _standard_patches()
        for p in cls._patches:
            p.start()
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

    def test_sessions_list_200(self) -> None:
        self.assertEqual(self.client.get("/api/v1/sessions?limit=10").status_code, 200)

    def test_sessions_list_top_level_fields(self) -> None:
        body = self.client.get("/api/v1/sessions?limit=10").json()
        for f in ("status", "data", "meta"):
            self.assertIn(f, body, f"envelope missing: {f}")

    def test_sessions_list_data_is_list(self) -> None:
        body = self.client.get("/api/v1/sessions?limit=10").json()
        self.assertIsInstance(body["data"], list)

    def test_sessions_list_meta_pagination_fields(self) -> None:
        """Pinned: meta must expose {total, limit, offset, has_more}."""
        meta = self.client.get("/api/v1/sessions?limit=10").json()["meta"]
        for f in ("total", "limit", "offset", "has_more"):
            self.assertIn(f, meta, f"paginated meta missing: {f}")

    def test_sessions_list_meta_reflects_query(self) -> None:
        meta = self.client.get("/api/v1/sessions?limit=7&offset=3").json()["meta"]
        self.assertEqual(meta["limit"], 7)
        self.assertEqual(meta["offset"], 3)

    def test_sessions_list_validates_against_paginated_envelope(self) -> None:
        from backend.models import SessionIntelligenceSessionRollup
        body = self.client.get("/api/v1/sessions?limit=10").json()
        TypeAdapter(
            ClientV1PaginatedEnvelope[SessionIntelligenceSessionRollup]
        ).validate_python(body)  # raises if shape is wrong


# ---------------------------------------------------------------------------
# T10-002 / T10-006: Cross-project contract — project_id required for detail
# ---------------------------------------------------------------------------

class TestCrossProjectContract(unittest.TestCase):
    """Confirm /detail and /transcript require project_id (400 absent, 404 present+unknown)."""

    _FAKE_SID = "nonexistent-session-id-zzz-contract"

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()
        cls._env_patcher = patch.dict(
            os.environ,
            {"CCDASH_DB_PATH": cls._tmpdb.name, "CCDASH_DB_BACKEND": "sqlite"},
        )
        cls._env_patcher.start()
        cls._app = build_runtime_app("test")
        cls._patches = _standard_patches()
        for p in cls._patches:
            p.start()
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

    def test_detail_missing_project_id_returns_400(self) -> None:
        resp = self.client.get(f"/api/v1/sessions/{self._FAKE_SID}/detail")
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_transcript_missing_project_id_returns_400(self) -> None:
        resp = self.client.get(f"/api/v1/sessions/{self._FAKE_SID}/transcript")
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_detail_400_mentions_project_id(self) -> None:
        body = self.client.get(f"/api/v1/sessions/{self._FAKE_SID}/detail").json()
        self.assertIn("project_id", str(body.get("detail", "")).lower())

    def test_transcript_400_mentions_project_id(self) -> None:
        body = self.client.get(f"/api/v1/sessions/{self._FAKE_SID}/transcript").json()
        self.assertIn("project_id", str(body.get("detail", "")).lower())

    def test_detail_with_project_id_gives_404_not_400(self) -> None:
        """project_id present → unknown session → 404, NOT 400 (no active-project fallback)."""
        resp = self.client.get(
            f"/api/v1/sessions/{self._FAKE_SID}/detail?project_id=some-project"
        )
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_transcript_with_project_id_gives_404_not_400(self) -> None:
        resp = self.client.get(
            f"/api/v1/sessions/{self._FAKE_SID}/transcript?project_id=some-project"
        )
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_transcript_page_model_has_cursor_envelope_fields(self) -> None:
        """Pinned: SessionTranscriptPageV1 must have {items, cursor, limit, nextCursor}."""
        fields = SessionTranscriptPageV1.model_fields
        for f in ("items", "cursor", "limit", "nextCursor"):
            self.assertIn(f, fields, f"SessionTranscriptPageV1 missing field: {f}")

    def test_transcript_nextcursor_is_optional(self) -> None:
        """nextCursor must be None-able (last page indicator)."""
        page = SessionTranscriptPageV1(
            sessionId="s1", projectId="p1",
            items=[], cursor="", limit=10,
            nextCursor=None, redactedFieldCount=0,
        )
        self.assertIsNone(page.nextCursor)


# ---------------------------------------------------------------------------
# T10-004 / T10-006: Auth dependency contract — CCDASH_API_TOKEN
# ---------------------------------------------------------------------------

class TestApiTokenAuthContract(unittest.TestCase):
    """Verify require_v1_auth behaviour across set/unset CCDASH_API_TOKEN (T10-004)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()
        cls._env_patcher = patch.dict(
            os.environ,
            {"CCDASH_DB_PATH": cls._tmpdb.name, "CCDASH_DB_BACKEND": "sqlite"},
        )
        cls._env_patcher.start()
        cls._app = build_runtime_app("test")
        cls._patches = _standard_patches()
        for p in cls._patches:
            p.start()
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

    def test_no_token_allows_all_requests(self) -> None:
        """Default (token unset): local-trust, every /api/v1 request passes through."""
        self.assertEqual(self.client.get("/api/v1/capabilities").status_code, 200)

    def test_token_set_no_header_returns_401(self) -> None:
        with _api_token_set(self, "my-secret"):
            resp = self.client.get("/api/v1/capabilities")
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_token_set_wrong_bearer_returns_403(self) -> None:
        with _api_token_set(self, "my-secret"):
            resp = self.client.get(
                "/api/v1/capabilities",
                headers={"Authorization": "Bearer wrong"},
            )
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_token_set_correct_bearer_returns_200(self) -> None:
        with _api_token_set(self, "my-secret"):
            resp = self.client.get(
                "/api/v1/capabilities",
                headers={"Authorization": "Bearer my-secret"},
            )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_401_mentions_bearer_token(self) -> None:
        with _api_token_set(self, "tok"):
            body = self.client.get("/api/v1/capabilities").json()
        self.assertIn("Bearer token", body.get("detail", ""))

    def test_403_mentions_rejected(self) -> None:
        with _api_token_set(self, "tok"):
            body = self.client.get(
                "/api/v1/capabilities",
                headers={"Authorization": "Bearer bad"},
            ).json()
        self.assertIn("rejected", body.get("detail", "").lower())

    def test_auth_is_router_level_gates_sessions_list(self) -> None:
        """require_v1_auth is at router level — applies to every /api/v1 route."""
        with _api_token_set(self, "tok"):
            resp = self.client.get("/api/v1/sessions?limit=5")
        self.assertEqual(resp.status_code, 401)

    def test_auth_is_router_level_gates_instance(self) -> None:
        with _api_token_set(self, "tok"):
            resp = self.client.get("/api/v1/instance")
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# T10-006: OpenAPI schema paths
# ---------------------------------------------------------------------------

class TestOpenAPISchemaContract(unittest.TestCase):
    """Ensure key /api/v1 paths appear in the generated OpenAPI schema."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()
        cls._env_patcher = patch.dict(
            os.environ,
            {"CCDASH_DB_PATH": cls._tmpdb.name, "CCDASH_DB_BACKEND": "sqlite"},
        )
        cls._env_patcher.start()
        cls._app = build_runtime_app("test")
        cls._patches = _standard_patches()
        for p in cls._patches:
            p.start()
        cls._tc = TestClient(cls._app, raise_server_exceptions=False)
        cls._tc.__enter__()

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

    def test_capabilities_in_openapi(self) -> None:
        self.assertIn("/api/v1/capabilities", self._app.openapi()["paths"])

    def test_sessions_in_openapi(self) -> None:
        self.assertIn("/api/v1/sessions", self._app.openapi()["paths"])

    def test_sessions_detail_in_openapi(self) -> None:
        self.assertIn("/api/v1/sessions/{session_id}/detail", self._app.openapi()["paths"])

    def test_sessions_transcript_in_openapi(self) -> None:
        self.assertIn("/api/v1/sessions/{session_id}/transcript", self._app.openapi()["paths"])

    def test_instance_in_openapi(self) -> None:
        self.assertIn("/api/v1/instance", self._app.openapi()["paths"])


if __name__ == "__main__":
    unittest.main()
