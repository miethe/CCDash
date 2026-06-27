"""Contract tests for the Phase 2 /api/v1/sessions/{id}/detail and
/api/v1/sessions/{id}/transcript endpoints.

Verifies:
  - HTTP 400 when project_id is absent (no active-project fallback).
  - HTTP 404 for an unknown session_id (with a valid project_id).
  - Correct envelope shape (status/data/meta) and data field presence.
  - TranscriptPageV1 cursor-pagination envelope ({items,cursor,limit,nextCursor}).
  - Pydantic contract validation using the contracts-package models.
  - Redaction: a known secret (AWS key pattern) injected into a mocked
    transcript is ABSENT from the HTTP response body (redaction inherited
    from the Phase 1 service, not re-implemented here).
  - Both new paths appear in the OpenAPI schema.

Test runtime: build_runtime_app("test") with a throwaway SQLite DB, same
pattern as test_client_v1_contract.py.  No real filesystem is touched.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from ccdash_contracts import (
    ClientV1Envelope,
    SessionDetailV1,
    SessionTranscriptPageV1,
    TranscriptPageV1,
)

from backend.runtime.bootstrap import build_runtime_app

# ---------------------------------------------------------------------------
# Fake session row returned by mocked SqliteSessionRepository.get_by_id.
# project_id is empty string so the service's mismatch guard is skipped for
# any project_id passed in the request.
# ---------------------------------------------------------------------------

_FAKE_SESSION_ROW: dict = {
    "id": "sess-phase2-test-001",
    "project_id": "",  # empty → mismatch guard skipped (any project_id accepted)
    "task_id": "",
    "status": "completed",
    "model": "claude-3-5-sonnet-20241022",
    "root_session_id": "sess-phase2-test-001",
    "parent_session_id": None,
    "started_at": "2024-06-01T10:00:00Z",
    "ended_at": "2024-06-01T11:00:00Z",
    "tokens_in": 1000,
    "tokens_out": 500,
    "model_io_tokens": 1500,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    "cache_input_tokens": 0,
    "observed_tokens": 1500,
    "tool_reported_tokens": 0,
    "total_cost": 0.0075,
    "duration_seconds": 3600.0,
    # Phase 5 detection fields (must be present; do NOT break Phase 5 fields)
    "model_slug": "claude-3-5-sonnet",
    "workflow_id": None,
    "subagent_parent_id": None,
    "skill_name": None,
    "context_window": None,
}

# ---------------------------------------------------------------------------
# AWS Access Key ID that matches the Layer-1 redaction pattern:
#   \b(AKIA[0-9A-Z]{16})\b  (AKIA + 16 uppercase alphanumeric chars)
# ---------------------------------------------------------------------------
_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"

_TRANSCRIPT_WITH_SECRET: list[dict] = [
    {
        "type": "text",
        "role": "assistant",
        "content": f"Here is the key: {_AWS_KEY} — please rotate it.",
        "index": 0,
    }
]

_TRANSCRIPT_EMPTY: list[dict] = []


class TestSessionDetailV1Endpoints(unittest.TestCase):
    """Contract + redaction tests for Phase 2 session detail endpoints."""

    # ------------------------------------------------------------------
    # Class-level setup — one app instance shared across all tests
    # ------------------------------------------------------------------

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
            patch(
                "backend.runtime_ports.db_project_manager.get_active_project",
                return_value=None,
            ),
        ]
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _assert_base_envelope(self, body: dict) -> None:
        for field in ("status", "data", "meta"):
            self.assertIn(field, body, f"envelope missing required field: {field}")

    def _assert_meta_fields(self, meta: dict) -> None:
        for field in ("generated_at", "instance_id", "request_id"):
            self.assertIn(field, meta, f"meta missing required field: {field}")

    def _session_detail_mock_context(self, transcript_data=None):
        """Return a context-manager stack that mocks session + transcript repos."""
        if transcript_data is None:
            transcript_data = _TRANSCRIPT_EMPTY
        return (
            patch(
                "backend.db.repositories.sessions.SqliteSessionRepository.get_by_id",
                new_callable=AsyncMock,
                return_value=_FAKE_SESSION_ROW,
            ),
            patch(
                "backend.application.services.agent_queries.session_detail"
                "._transcript_service.list_session_logs",
                new_callable=AsyncMock,
                return_value=transcript_data,
            ),
        )

    # ------------------------------------------------------------------
    # T2-003: project_id required (400 on missing)
    # ------------------------------------------------------------------

    def test_detail_missing_project_id_returns_400(self) -> None:
        resp = self.client.get("/api/v1/sessions/sess-any/detail")
        self.assertEqual(
            resp.status_code,
            400,
            f"Expected 400 for missing project_id, got {resp.status_code}: {resp.text}",
        )

    def test_transcript_missing_project_id_returns_400(self) -> None:
        resp = self.client.get("/api/v1/sessions/sess-any/transcript")
        self.assertEqual(
            resp.status_code,
            400,
            f"Expected 400 for missing project_id, got {resp.status_code}: {resp.text}",
        )

    def test_detail_400_response_contains_actionable_message(self) -> None:
        body = self.client.get("/api/v1/sessions/sess-any/detail").json()
        detail = str(body.get("detail", ""))
        self.assertIn("project_id", detail.lower())

    def test_transcript_400_response_contains_actionable_message(self) -> None:
        body = self.client.get("/api/v1/sessions/sess-any/transcript").json()
        detail = str(body.get("detail", ""))
        self.assertIn("project_id", detail.lower())

    # ------------------------------------------------------------------
    # T2-002: 404 for unknown session_id
    # ------------------------------------------------------------------

    def test_detail_unknown_session_returns_404(self) -> None:
        resp = self.client.get(
            "/api/v1/sessions/NONEXISTENT-SESSION-ZZZZZ/detail?project_id=proj-test"
        )
        self.assertEqual(resp.status_code, 404)

    def test_transcript_unknown_session_returns_404(self) -> None:
        resp = self.client.get(
            "/api/v1/sessions/NONEXISTENT-SESSION-ZZZZZ/transcript?project_id=proj-test"
        )
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # T2-001 / T2-002: envelope shape — detail endpoint
    # ------------------------------------------------------------------

    def test_detail_returns_200_with_mocked_session(self) -> None:
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            resp = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/detail"
                "?project_id=proj-test-001&include=transcript"
            )
        self.assertEqual(resp.status_code, 200)

    def test_detail_envelope_has_required_top_level_fields(self) -> None:
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/detail"
                "?project_id=proj-test-001&include=transcript"
            ).json()
        self._assert_base_envelope(body)
        self.assertEqual(body["status"], "ok")

    def test_detail_meta_has_required_fields(self) -> None:
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/detail"
                "?project_id=proj-test-001&include=transcript"
            ).json()
        self._assert_meta_fields(body["meta"])

    def test_detail_data_has_session_detail_v1_contract_fields(self) -> None:
        """Data must contain sessionId, projectId, session, redactedFieldCount."""
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/detail"
                "?project_id=proj-test-001&include=transcript"
            ).json()
        data = body["data"]
        for field in ("sessionId", "projectId", "session", "redactedFieldCount"):
            self.assertIn(field, data, f"SessionDetailV1 data missing field: {field}")

    def test_detail_data_session_field_is_a_dict(self) -> None:
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/detail"
                "?project_id=proj-test-001&include=transcript"
            ).json()
        self.assertIsInstance(body["data"]["session"], dict)

    def test_detail_transcript_segment_has_cursor_envelope_fields(self) -> None:
        """Transcript must include items, cursor, limit, nextCursor when requested."""
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/detail"
                "?project_id=proj-test-001&include=transcript"
            ).json()
        transcript = body["data"].get("transcript")
        self.assertIsNotNone(
            transcript, "transcript segment must be present when include=transcript"
        )
        for field in ("items", "cursor", "limit", "nextCursor"):
            self.assertIn(field, transcript, f"transcript missing cursor-envelope field: {field}")

    def test_detail_transcript_items_is_a_list(self) -> None:
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/detail"
                "?project_id=proj-test-001&include=transcript"
            ).json()
        self.assertIsInstance(body["data"]["transcript"]["items"], list)

    def test_detail_validates_against_contracts_package_model(self) -> None:
        """The response must parse against ClientV1Envelope[SessionDetailV1]."""
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/detail"
                "?project_id=proj-test-001&include=transcript"
            ).json()
        parsed = TypeAdapter(ClientV1Envelope[SessionDetailV1]).validate_python(body)
        self.assertEqual(parsed.status, "ok")
        self.assertIsInstance(parsed.data, SessionDetailV1)

    # ------------------------------------------------------------------
    # T2-001 / T2-002: envelope shape — transcript endpoint
    # ------------------------------------------------------------------

    def test_transcript_returns_200_with_mocked_session(self) -> None:
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            resp = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/transcript"
                "?project_id=proj-test-001"
            )
        self.assertEqual(resp.status_code, 200)

    def test_transcript_envelope_has_required_top_level_fields(self) -> None:
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/transcript"
                "?project_id=proj-test-001"
            ).json()
        self._assert_base_envelope(body)

    def test_transcript_meta_has_required_fields(self) -> None:
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/transcript"
                "?project_id=proj-test-001"
            ).json()
        self._assert_meta_fields(body["meta"])

    def test_transcript_data_has_page_envelope_fields(self) -> None:
        """Transcript data must contain items, cursor, limit, nextCursor."""
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/transcript"
                "?project_id=proj-test-001"
            ).json()
        data = body["data"]
        for field in ("items", "cursor", "limit", "nextCursor"):
            self.assertIn(field, data, f"SessionTranscriptPageV1 missing field: {field}")

    def test_transcript_data_items_is_a_list(self) -> None:
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/transcript"
                "?project_id=proj-test-001"
            ).json()
        self.assertIsInstance(body["data"]["items"], list)

    def test_transcript_data_has_session_identity_fields(self) -> None:
        """Transcript endpoint must include sessionId and projectId in data."""
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/transcript"
                "?project_id=proj-test-001"
            ).json()
        data = body["data"]
        self.assertIn("sessionId", data)
        self.assertIn("projectId", data)

    def test_transcript_validates_against_contracts_package_model(self) -> None:
        """The response must parse against ClientV1Envelope[SessionTranscriptPageV1]."""
        mock_repo, mock_ts = self._session_detail_mock_context()
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/transcript"
                "?project_id=proj-test-001"
            ).json()
        parsed = TypeAdapter(ClientV1Envelope[SessionTranscriptPageV1]).validate_python(body)
        self.assertEqual(parsed.status, "ok")
        self.assertIsInstance(parsed.data, SessionTranscriptPageV1)

    # ------------------------------------------------------------------
    # T2-004: redaction — known secret ABSENT from HTTP response body
    # ------------------------------------------------------------------

    def test_redaction_aws_key_absent_from_detail_response(self) -> None:
        """AWS Access Key ID injected into a mocked transcript must be redacted.

        The Phase 1 service applies Layer-1 pattern scan before returning the
        transcript page.  The API handler must NOT bypass or re-read the
        transcript, so the secret must be absent from the serialised response.
        """
        mock_repo, mock_ts = self._session_detail_mock_context(
            transcript_data=_TRANSCRIPT_WITH_SECRET
        )
        with mock_repo, mock_ts:
            resp = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/detail"
                "?project_id=proj-test-001&include=transcript"
            )

        self.assertEqual(
            resp.status_code,
            200,
            f"Expected 200 from detail endpoint, got {resp.status_code}: {resp.text}",
        )
        self.assertNotIn(
            _AWS_KEY,
            resp.text,
            f"AWS key '{_AWS_KEY}' must be redacted but was found in the HTTP response body",
        )

    def test_redaction_aws_key_absent_from_transcript_response(self) -> None:
        """Same redaction assertion for the dedicated /transcript endpoint."""
        mock_repo, mock_ts = self._session_detail_mock_context(
            transcript_data=_TRANSCRIPT_WITH_SECRET
        )
        with mock_repo, mock_ts:
            resp = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/transcript"
                "?project_id=proj-test-001"
            )

        self.assertEqual(
            resp.status_code,
            200,
            f"Expected 200 from transcript endpoint, got {resp.status_code}: {resp.text}",
        )
        self.assertNotIn(
            _AWS_KEY,
            resp.text,
            f"AWS key '{_AWS_KEY}' must be redacted but was found in the HTTP response body",
        )

    def test_redacted_field_count_non_negative_in_detail(self) -> None:
        """redactedFieldCount must be a non-negative integer."""
        mock_repo, mock_ts = self._session_detail_mock_context(
            transcript_data=_TRANSCRIPT_WITH_SECRET
        )
        with mock_repo, mock_ts:
            body = self.client.get(
                "/api/v1/sessions/sess-phase2-test-001/detail"
                "?project_id=proj-test-001&include=transcript"
            ).json()
        count = body["data"].get("redactedFieldCount", -1)
        self.assertGreaterEqual(count, 0)

    # ------------------------------------------------------------------
    # OpenAPI schema: new paths must be registered
    # ------------------------------------------------------------------

    def test_openapi_schema_exposes_detail_path(self) -> None:
        paths = self._app.openapi()["paths"]
        self.assertIn(
            "/api/v1/sessions/{session_id}/detail",
            paths,
            "GET /api/v1/sessions/{session_id}/detail not found in OpenAPI schema",
        )

    def test_openapi_schema_exposes_transcript_path(self) -> None:
        paths = self._app.openapi()["paths"]
        self.assertIn(
            "/api/v1/sessions/{session_id}/transcript",
            paths,
            "GET /api/v1/sessions/{session_id}/transcript not found in OpenAPI schema",
        )

    def test_openapi_schema_detail_path_has_get_method(self) -> None:
        paths = self._app.openapi()["paths"]
        detail_path = paths.get("/api/v1/sessions/{session_id}/detail", {})
        self.assertIn("get", detail_path)

    def test_openapi_schema_transcript_path_has_get_method(self) -> None:
        paths = self._app.openapi()["paths"]
        transcript_path = paths.get("/api/v1/sessions/{session_id}/transcript", {})
        self.assertIn("get", transcript_path)

    # ------------------------------------------------------------------
    # Contracts package: importable models
    # ------------------------------------------------------------------

    def test_session_detail_v1_importable_from_contracts_package(self) -> None:
        from ccdash_contracts import SessionDetailV1 as _SD  # noqa: F401
        self.assertTrue(hasattr(_SD, "model_fields"))

    def test_transcript_page_v1_importable_from_contracts_package(self) -> None:
        from ccdash_contracts import TranscriptPageV1 as _TP  # noqa: F401
        self.assertTrue(hasattr(_TP, "model_fields"))

    def test_session_transcript_page_v1_importable_from_contracts_package(self) -> None:
        from ccdash_contracts import SessionTranscriptPageV1 as _STP  # noqa: F401
        self.assertTrue(hasattr(_STP, "model_fields"))

    def test_transcript_page_v1_has_cursor_envelope_fields(self) -> None:
        from ccdash_contracts import TranscriptPageV1
        fields = set(TranscriptPageV1.model_fields.keys())
        for f in ("items", "cursor", "limit", "nextCursor"):
            self.assertIn(f, fields, f"TranscriptPageV1 missing model_field: {f}")

    def test_session_detail_v1_has_bundle_fields(self) -> None:
        from ccdash_contracts import SessionDetailV1
        fields = set(SessionDetailV1.model_fields.keys())
        for f in ("sessionId", "projectId", "session", "transcript", "subagents",
                  "tokens", "artifacts", "links", "redactedFieldCount"):
            self.assertIn(f, fields, f"SessionDetailV1 missing model_field: {f}")

    def test_session_transcript_page_v1_has_all_fields(self) -> None:
        from ccdash_contracts import SessionTranscriptPageV1
        fields = set(SessionTranscriptPageV1.model_fields.keys())
        for f in ("sessionId", "projectId", "items", "cursor", "limit",
                  "nextCursor", "redactedFieldCount"):
            self.assertIn(f, fields, f"SessionTranscriptPageV1 missing model_field: {f}")


if __name__ == "__main__":
    unittest.main()
