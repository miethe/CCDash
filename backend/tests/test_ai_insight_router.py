"""Tests for POST /api/ai/insight.

Covers:
  - key-set path: mocked httpx call returns a Gemini-shaped payload
  - key-unset / disabled path: returns {disabled: true, text: "", error: ""}

Uses unittest.mock to patch httpx.AsyncClient.post so no real network calls
are made.  The FastAPI TestClient drives the router layer end-to-end.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.ai import ai_router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(ai_router)
    return app


class TestAIInsightRouterKeyUnset(unittest.TestCase):
    """When CCDASH_GEMINI_API_KEY is unset the endpoint returns disabled=True."""

    def setUp(self) -> None:
        self.app = _make_app()
        self.client = TestClient(self.app, raise_server_exceptions=True)

    def test_disabled_when_no_key(self) -> None:
        with patch("backend.config.CCDASH_GEMINI_API_KEY", ""):
            resp = self.client.post(
                "/api/ai/insight",
                json={"metrics": [], "tasks": []},
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["disabled"])
        self.assertEqual(data["text"], "")
        self.assertEqual(data["error"], "")

    def test_disabled_ignores_payload(self) -> None:
        payload = {
            "metrics": [{"name": "cost", "value": 1.5}],
            "tasks": [{"title": "Auth", "status": "active", "cost": 1.5}],
        }
        with patch("backend.config.CCDASH_GEMINI_API_KEY", ""):
            resp = self.client.post("/api/ai/insight", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["disabled"])


class TestAIInsightRouterKeySet(unittest.TestCase):
    """When CCDASH_GEMINI_API_KEY is set the service calls Gemini and returns text."""

    def setUp(self) -> None:
        self.app = _make_app()
        self.client = TestClient(self.app, raise_server_exceptions=True)

    def _mock_gemini_response(self, text: str) -> MagicMock:
        """Build a mock httpx.Response that looks like a Gemini generateContent reply."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": text}],
                    }
                }
            ]
        }
        return mock_resp

    def test_returns_gemini_text(self) -> None:
        expected_text = "Project health: good. Main risk: token cost on Auth task."
        mock_resp = self._mock_gemini_response(expected_text)

        mock_post = AsyncMock(return_value=mock_resp)
        mock_client_instance = AsyncMock()
        mock_client_instance.post = mock_post
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.config.CCDASH_GEMINI_API_KEY", "test-key-123"), \
             patch("backend.services.ai_insight.httpx.AsyncClient", return_value=mock_client_instance):
            resp = self.client.post(
                "/api/ai/insight",
                json={
                    "metrics": [{"name": "cost", "value": 2.0}],
                    "tasks": [{"title": "Auth", "status": "active", "cost": 2.0}],
                },
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["disabled"])
        self.assertEqual(data["error"], "")
        self.assertEqual(data["text"], expected_text)

    def test_empty_response_returns_fallback_text(self) -> None:
        """An empty Gemini candidates list returns the fallback string, not an error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"candidates": []}

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.config.CCDASH_GEMINI_API_KEY", "test-key-456"), \
             patch("backend.services.ai_insight.httpx.AsyncClient", return_value=mock_client_instance):
            resp = self.client.post("/api/ai/insight", json={"metrics": [], "tasks": []})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["disabled"])
        self.assertEqual(data["error"], "")
        self.assertEqual(data["text"], "Could not generate insight.")

    def test_http_error_returns_error_field(self) -> None:
        """An HTTP 4xx/5xx from Gemini surfaces in the error field, not a 500."""
        import httpx as _httpx

        mock_http_err_resp = MagicMock()
        mock_http_err_resp.status_code = 429
        mock_http_err_resp.text = "quota exceeded"
        exc = _httpx.HTTPStatusError(
            "quota exceeded",
            request=MagicMock(),
            response=mock_http_err_resp,
        )

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(side_effect=exc)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.config.CCDASH_GEMINI_API_KEY", "test-key-789"), \
             patch("backend.services.ai_insight.httpx.AsyncClient", return_value=mock_client_instance):
            resp = self.client.post("/api/ai/insight", json={"metrics": [], "tasks": []})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["disabled"])
        self.assertIn("429", data["error"])

    def test_network_error_returns_error_field(self) -> None:
        """A network-level exception surfaces in error, not a 500."""
        import httpx as _httpx

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(
            side_effect=_httpx.ConnectError("connection refused")
        )
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.config.CCDASH_GEMINI_API_KEY", "test-key-999"), \
             patch("backend.services.ai_insight.httpx.AsyncClient", return_value=mock_client_instance):
            resp = self.client.post("/api/ai/insight", json={"metrics": [], "tasks": []})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["disabled"])
        self.assertIn("Error connecting", data["error"])


class TestAIInsightRouterErrorBodyNeverLogged(unittest.TestCase):
    """M1 (hosted-llm-anthropic-ica-lane-v1, egress-path hardening): a

    provider error-response body must never reach a log record -- only the
    status code plus a fixed message. Mirrors the
    ``ProviderErrorBodyNeverLoggedTests`` shape added for the gemini adapter
    in ``test_session_naming_hosted_backend.py``.
    """

    def setUp(self) -> None:
        self.app = _make_app()
        self.client = TestClient(self.app, raise_server_exceptions=True)

    def test_http_error_body_is_absent_from_every_log_record(self) -> None:
        import httpx as _httpx

        secret_marker = "UPSTREAM_ERROR_BODY_MARKER_ai_insight_9f31"
        mock_http_err_resp = MagicMock()
        mock_http_err_resp.status_code = 503
        mock_http_err_resp.text = secret_marker
        exc = _httpx.HTTPStatusError(
            secret_marker,
            request=MagicMock(),
            response=mock_http_err_resp,
        )

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(side_effect=exc)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.config.CCDASH_GEMINI_API_KEY", "test-key-000"), \
             patch(
                 "backend.services.ai_insight.httpx.AsyncClient",
                 return_value=mock_client_instance,
             ), \
             self.assertLogs("backend.services.ai_insight", level="WARNING") as captured:
            resp = self.client.post("/api/ai/insight", json={"metrics": [], "tasks": []})

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["disabled"])
        self.assertIn("503", data["error"])

        joined = "\n".join(captured.output)
        self.assertNotIn(secret_marker, joined)
        # The status code IS expected to be present -- "fixed message plus
        # status code," not a blanket "log nothing."
        self.assertIn("503", joined)


class TestAIInsightRouterAuth(unittest.TestCase):
    """``/api/ai`` is gated by the SAME ``require_v1_auth`` dependency as /api/v1.

    Before this gate the endpoint was an unauthenticated LLM proxy on any
    non-loopback deployment.  Parity with /api/v1 is the contract: no-op when
    CCDASH_API_TOKEN is unset, 401 on a missing bearer, 403 on a wrong one.
    """

    def setUp(self) -> None:
        self.app = _make_app()
        self.client = TestClient(self.app, raise_server_exceptions=True)

    def test_allows_unauthenticated_when_token_unset(self) -> None:
        """Local-trust default: no token configured => no credential required."""
        with patch("backend.config.CCDASH_API_TOKEN", ""), \
             patch("backend.config.CCDASH_GEMINI_API_KEY", ""):
            resp = self.client.post("/api/ai/insight", json={"metrics": [], "tasks": []})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["disabled"])

    def test_rejects_unauthenticated_when_token_set(self) -> None:
        """The defect this test pins: an unauthenticated POST must be rejected."""
        with patch("backend.config.CCDASH_API_TOKEN", "secret-test-token"), \
             patch("backend.config.CCDASH_GEMINI_API_KEY", "test-key-should-never-be-used"):
            resp = self.client.post("/api/ai/insight", json={"metrics": [], "tasks": []})
        self.assertEqual(resp.status_code, 401)

    def test_rejects_wrong_token(self) -> None:
        with patch("backend.config.CCDASH_API_TOKEN", "secret-test-token"), \
             patch("backend.config.CCDASH_GEMINI_API_KEY", "test-key-should-never-be-used"):
            resp = self.client.post(
                "/api/ai/insight",
                json={"metrics": [], "tasks": []},
                headers={"Authorization": "Bearer wrong-token"},
            )
        self.assertEqual(resp.status_code, 403)

    def test_accepts_correct_token_and_preserves_disabled_path(self) -> None:
        """A valid bearer passes the gate; the disabled contract state survives it."""
        with patch("backend.config.CCDASH_API_TOKEN", "secret-test-token"), \
             patch("backend.config.CCDASH_GEMINI_API_KEY", ""):
            resp = self.client.post(
                "/api/ai/insight",
                json={"metrics": [], "tasks": []},
                headers={"Authorization": "Bearer secret-test-token"},
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["disabled"])
        self.assertEqual(data["error"], "")


if __name__ == "__main__":
    unittest.main()
