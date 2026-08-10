"""Tests for POST /api/ai/insight.

Covers:
  - key-set path: mocked httpx call returns a Gemini-shaped payload
  - key-unset / disabled path: returns {disabled: true, text: "", error: ""}
  - the GLOBAL egress consent gate (``TestAIInsightEgressConsentGate``):
    two-sided, with a negative-construction proof that no EGRESS adapter is
    constructed when ``CCDASH_LLM_EGRESS_CONSENT`` is false. Note that every
    test which drives a real send now patches that flag True as well as the
    API key — with consent at its false default those paths correctly
    short-circuit to the disabled contract state.

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
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True), \
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
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True), \
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
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True), \
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
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True), \
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
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True), \
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


class TestAIInsightEgressConsentGate(unittest.TestCase):
    """The GLOBAL egress consent gate on the insight lane.

    ``POST /api/ai/insight`` constructs ``GeminiTextCompletionAdapter``
    (``EGRESS = True``) and sends the assembled prompt off-box. Before this
    gate it was reachable on ``CCDASH_GEMINI_API_KEY`` ALONE, so a
    deployment with a Gemini key and ``CCDASH_LLM_EGRESS_CONSENT=false``
    still egressed from this route -- falsifying the unqualified acceptance
    criterion "with CCDASH_LLM_EGRESS_CONSENT false, no egress adapter is
    constructed."

    Deliberately TWO-SIDED: the negative test proves non-construction and
    the positive test proves the gate still lets a consented, credentialed
    call through -- so a gate that always refused would fail here rather
    than look like a pass.

    SCOPE: this lane has ONE consent dimension. The per-project
    ``projects.llm_egress_consent`` column applies to the session-naming
    sweep (which has a project per unit of work); this request carries no
    project id, so the global flag is the whole gate. See
    ``generate_dashboard_insight``'s docstring.
    """

    def setUp(self) -> None:
        self.app = _make_app()
        self.client = TestClient(self.app, raise_server_exceptions=True)

    def test_consent_defaults_false(self) -> None:
        """Fail-closed by default: nothing needs to be set to be safe."""
        from backend import config

        self.assertFalse(config.CCDASH_LLM_EGRESS_CONSENT)

    def test_negative_construction_adapter_never_constructed_when_consent_false(
        self,
    ) -> None:
        """Structural guard, mirrors the naming-resolver technique in

        ``test_session_naming_local_backend.py`` -- the patched constructor
        RAISES, so this fails LOUDLY (with a named cause) if the request path
        EVER reaches ``GeminiTextCompletionAdapter(...)`` while global
        consent is false, rather than quietly passing on an empty result. A
        key IS set and the payload IS non-empty -- every other precondition
        is wide open -- so only the consent gate stands between this call and
        construction.

        Note the service imports the adapter lazily, below the gate, so
        under false consent this patch target is never even resolved; the
        patch exists to make the "would have constructed" case observable.
        """

        def _explode(**kwargs: object) -> None:
            raise AssertionError(
                "GeminiTextCompletionAdapter was constructed while "
                "CCDASH_LLM_EGRESS_CONSENT was false -- the global egress "
                "consent gate on POST /api/ai/insight has a "
                "silent-fail-open regression."
            )

        with patch("backend.config.CCDASH_GEMINI_API_KEY", "test-key-consent-false"), \
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", False), \
             patch(
                 "backend.adapters.llm.gemini.GeminiTextCompletionAdapter",
                 _explode,
             ):
            resp = self.client.post(
                "/api/ai/insight",
                json={
                    "metrics": [{"name": "cost", "value": 3.0}],
                    "tasks": [{"title": "Auth", "status": "active", "cost": 3.0}],
                },
            )

        # The EXISTING contract on refusal -- no API shape change, no new
        # exception type: the route's usual 200 + disabled degrade. Asserted
        # as well as the raising constructor above so the property still
        # holds if a future refactor moved construction inside the service's
        # broad ``except Exception`` (which would swallow the AssertionError).
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["disabled"])
        self.assertEqual(data["text"], "")
        self.assertEqual(data["error"], "")

    def test_no_outbound_http_attempted_when_consent_false(self) -> None:
        """Belt-and-braces: the httpx client is never even instantiated."""
        mock_client_factory = MagicMock(
            side_effect=AssertionError(
                "httpx.AsyncClient was instantiated while "
                "CCDASH_LLM_EGRESS_CONSENT was false."
            )
        )
        with patch("backend.config.CCDASH_GEMINI_API_KEY", "test-key-consent-false-2"), \
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", False), \
             patch(
                 "backend.services.ai_insight.httpx.AsyncClient",
                 mock_client_factory,
             ):
            resp = self.client.post("/api/ai/insight", json={"metrics": [], "tasks": []})

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["disabled"])
        mock_client_factory.assert_not_called()

    def test_consent_true_with_key_reaches_the_adapter(self) -> None:
        """The other side of the gate: a consented, credentialed call still

        constructs the REAL adapter and returns provider text. Without this,
        a gate that refused unconditionally would pass the negative test and
        look correct.
        """
        expected_text = "Health: steady. Risk: Auth task token cost."
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": expected_text}]}}]
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.config.CCDASH_GEMINI_API_KEY", "test-key-consent-true"), \
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True), \
             patch(
                 "backend.services.ai_insight.httpx.AsyncClient",
                 return_value=mock_client_instance,
             ):
            resp = self.client.post(
                "/api/ai/insight",
                json={
                    "metrics": [{"name": "cost", "value": 3.0}],
                    "tasks": [{"title": "Auth", "status": "active", "cost": 3.0}],
                },
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["disabled"])
        self.assertEqual(data["error"], "")
        self.assertEqual(data["text"], expected_text)
        mock_client_instance.post.assert_awaited_once()

    def test_consent_true_without_key_still_disabled(self) -> None:
        """Consent alone is not sufficient -- the credential gate survives."""
        with patch("backend.config.CCDASH_GEMINI_API_KEY", ""), \
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True):
            resp = self.client.post("/api/ai/insight", json={"metrics": [], "tasks": []})

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["disabled"])


if __name__ == "__main__":
    unittest.main()
