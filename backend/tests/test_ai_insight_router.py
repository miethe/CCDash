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
  - the PER-PROJECT egress consent gate
    (``TestAIInsightPerProjectConsentGate``): this lane honours the named
    project's ``projects.llm_egress_consent`` too, so consent here is
    two-dimensional exactly as it is for the session-naming sweep. A request
    naming no project is REFUSED by decision, not fallen back to the global
    flag alone — that is pinned by test, since a fallback would quietly
    restore the old one-dimension behaviour.

Because both gates now apply, every send-asserting test needs BOTH satisfied:
the helpers ``_consenting_app()`` (wires a consenting project into
``app.state.core_ports``) and ``_insight_body()`` (names it on the body) exist
so each test's own patches stay focused on the one variable it is about.

Uses unittest.mock to patch httpx.AsyncClient.post so no real network calls
are made.  The FastAPI TestClient drives the router layer end-to-end.
"""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.application.ports import CorePorts
from backend.routers.ai import ai_router


_CONSENTING_PROJECT_ID = "proj-consenting"


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(ai_router)
    return app


def _wire_ports(app: FastAPI, project: object | None) -> MagicMock:
    """Attach a real ``CorePorts`` whose registry returns ``project``.

    ``_resolve_project_consent`` gates on ``isinstance(ports, CorePorts)``, so a
    bare MagicMock in ``app.state.core_ports`` would be treated as "ports
    unavailable" and silently refuse -- which would make every positive test
    below pass for the WRONG reason. Hence a genuine frozen ``CorePorts`` with
    a stub registry, and MagicMocks for the five ports this route never calls.

    Returns the registry mock so tests can assert on ``get_project`` calls.
    """
    registry = MagicMock()
    registry.get_project = MagicMock(return_value=project)
    app.state.core_ports = CorePorts(
        identity_provider=MagicMock(),
        authorization_policy=MagicMock(),
        workspace_registry=registry,
        storage=MagicMock(),
        job_scheduler=MagicMock(),
        integration_client=MagicMock(),
    )
    return registry


def _consenting_app() -> FastAPI:
    """An app whose ``_CONSENTING_PROJECT_ID`` has granted egress consent."""
    app = _make_app()
    _wire_ports(app, SimpleNamespace(id=_CONSENTING_PROJECT_ID, llm_egress_consent=True))
    return app


def _insight_body(**overrides: object) -> dict[str, object]:
    """A request body that satisfies the per-project consent gate by default.

    Every pre-existing test in this file posted ``{metrics, tasks}`` only. Once
    the insight lane gained its per-project gate those bodies REFUSE (no
    project id => fail closed by decision), so the send-asserting tests route
    through this helper to keep exercising what they were written to exercise.
    """
    body: dict[str, object] = {
        "metrics": [],
        "tasks": [],
        "project_id": _CONSENTING_PROJECT_ID,
    }
    body.update(overrides)
    return body


class TestAIInsightRouterKeyUnset(unittest.TestCase):
    """When CCDASH_GEMINI_API_KEY is unset the endpoint returns disabled=True.

    Uses a CONSENTING project so the refusal under test is attributable to the
    missing credential specifically, not to the per-project consent gate.
    """

    def setUp(self) -> None:
        self.app = _consenting_app()
        self.client = TestClient(self.app, raise_server_exceptions=True)

    def test_disabled_when_no_key(self) -> None:
        with patch("backend.config.CCDASH_GEMINI_API_KEY", ""), \
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True):
            resp = self.client.post(
                "/api/ai/insight",
                json=_insight_body(),
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["disabled"])
        self.assertEqual(data["text"], "")
        self.assertEqual(data["error"], "")

    def test_disabled_ignores_payload(self) -> None:
        payload = _insight_body(
            metrics=[{"name": "cost", "value": 1.5}],
            tasks=[{"title": "Auth", "status": "active", "cost": 1.5}],
        )
        with patch("backend.config.CCDASH_GEMINI_API_KEY", ""), \
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True):
            resp = self.client.post("/api/ai/insight", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["disabled"])


class TestAIInsightRouterKeySet(unittest.TestCase):
    """When CCDASH_GEMINI_API_KEY is set the service calls Gemini and returns text.

    Every test here drives a real send, so all of them need BOTH consent
    dimensions satisfied: the global flag patched True and a consenting project
    named on the body (see ``_consenting_app`` / ``_insight_body``).
    """

    def setUp(self) -> None:
        self.app = _consenting_app()
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
                json=_insight_body(
                    metrics=[{"name": "cost", "value": 2.0}],
                    tasks=[{"title": "Auth", "status": "active", "cost": 2.0}],
                ),
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
            resp = self.client.post("/api/ai/insight", json=_insight_body())

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
            resp = self.client.post("/api/ai/insight", json=_insight_body())

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
            resp = self.client.post("/api/ai/insight", json=_insight_body())

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
        self.app = _consenting_app()
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
            resp = self.client.post("/api/ai/insight", json=_insight_body())

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

    SCOPE: this class covers the GLOBAL dimension only. The per-project
    dimension -- ``projects.llm_egress_consent``, which this lane now also
    honours -- is covered by ``TestAIInsightPerProjectConsentGate`` below.
    Every test here names a CONSENTING project so that the global flag is the
    ONLY variable: a refusal observed here is attributable to the global gate
    and cannot be an artefact of the per-project one.
    """

    def setUp(self) -> None:
        self.app = _consenting_app()
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
                json=_insight_body(
                    metrics=[{"name": "cost", "value": 3.0}],
                    tasks=[{"title": "Auth", "status": "active", "cost": 3.0}],
                ),
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
            resp = self.client.post("/api/ai/insight", json=_insight_body())

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
                json=_insight_body(
                    metrics=[{"name": "cost", "value": 3.0}],
                    tasks=[{"title": "Auth", "status": "active", "cost": 3.0}],
                ),
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
            resp = self.client.post("/api/ai/insight", json=_insight_body())

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["disabled"])


class TestAIInsightPerProjectConsentGate(unittest.TestCase):
    """The PER-PROJECT egress consent gate on the insight lane.

    This lane used to have ONE consent dimension (the global flag) because
    ``AIInsightRequest`` carried no project id, so there was no project whose
    ``llm_egress_consent`` could be read. It now carries one and honours it,
    making every hosted-LLM egress path in the codebase two-level consented.

    In EVERY test here the global flag is patched TRUE and a key IS set, so the
    per-project dimension is the only thing standing between the request and
    construction -- a refusal observed here cannot be the global gate's doing.
    Negative cases use a RAISING patched constructor (same technique as the
    global-gate class above) so a fail-open regression fails loudly with a named
    cause rather than passing quietly on an empty result.
    """

    def _explode(self, reason: str):
        def _boom(**kwargs: object) -> None:
            raise AssertionError(
                f"GeminiTextCompletionAdapter was constructed although {reason} "
                "-- the PER-PROJECT egress consent gate on POST /api/ai/insight "
                "has a silent-fail-open regression."
            )

        return _boom

    def _post(self, app: FastAPI, body: dict[str, object], reason: str):
        client = TestClient(app, raise_server_exceptions=True)
        with patch("backend.config.CCDASH_GEMINI_API_KEY", "key-per-project-gate"), \
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True), \
             patch(
                 "backend.adapters.llm.gemini.GeminiTextCompletionAdapter",
                 self._explode(reason),
             ):
            return client.post("/api/ai/insight", json=body)

    def _assert_refused(self, resp) -> None:
        """Refusal is the route's usual 200 + disabled -- never a 4xx/5xx."""
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["disabled"])
        self.assertEqual(data["text"], "")
        self.assertEqual(data["error"], "")

    def test_absent_project_id_is_refused_not_globally_fallen_back(self) -> None:
        """The decided behaviour: no project named => REFUSE.

        This is the whole point of the decision recorded on this node. A
        global-only fallback here would reintroduce the one-dimension lane
        through a side door, so it is pinned by a test.
        """
        app = _consenting_app()
        resp = self._post(app, {"metrics": [], "tasks": []}, "no project_id was supplied")
        self._assert_refused(resp)

    def test_explicit_null_project_id_is_refused(self) -> None:
        """An explicit ``project_id: null`` refuses identically to omitting it."""
        app = _consenting_app()
        resp = self._post(
            app,
            {"metrics": [], "tasks": [], "project_id": None},
            "project_id was explicitly null",
        )
        self._assert_refused(resp)

    def test_project_that_declined_is_refused(self) -> None:
        """``llm_egress_consent = False`` on the named project refuses."""
        app = _make_app()
        _wire_ports(app, SimpleNamespace(id="proj-declined", llm_egress_consent=False))
        resp = self._post(
            app,
            _insight_body(project_id="proj-declined"),
            "the named project's llm_egress_consent is False",
        )
        self._assert_refused(resp)

    def test_unknown_project_is_refused_and_is_not_a_404(self) -> None:
        """An unregistered project refuses -- and NOT via a 404.

        The route's contract is always-200 + ``disabled``; turning an unknown
        project into a 404 would break it for a caller that only checks the
        flag. Unknown is never an implicit consent.
        """
        app = _make_app()
        _wire_ports(app, None)  # registry.get_project -> None
        resp = self._post(
            app,
            _insight_body(project_id="proj-does-not-exist"),
            "the named project is not registered",
        )
        self.assertNotEqual(resp.status_code, 404)
        self._assert_refused(resp)

    def test_unavailable_runtime_ports_refuse_rather_than_500(self) -> None:
        """Consent-unconfirmable degrades to refusal, never to a server error.

        ``get_core_ports`` raises HTTP 500 when ports are missing, which is why
        this route resolves them defensively instead. A 500 here would both
        break the always-200 contract and turn a consent question into an
        outage.
        """
        app = _make_app()  # no core_ports on app.state at all
        resp = self._post(
            app,
            _insight_body(),
            "runtime ports were unavailable so consent was unconfirmable",
        )
        self.assertEqual(resp.status_code, 200)
        self._assert_refused(resp)

    def test_ports_resolved_from_the_runtime_container_fallback(self) -> None:
        """The second lookup site must actually work, not be dead code.

        ``_resolve_project_consent`` mirrors ``get_core_ports``: it tries
        ``app.state.core_ports`` and then the runtime container's ``ports``. The
        container attribute is ``runtime_container`` -- an earlier draft looked
        up ``container``, which silently never matched. That typo is invisible in
        the primary path (``core_ports`` is set in the real app) and would only
        show up as a total refusal in a deployment that relies on the fallback,
        so it is pinned here.
        """
        expected_text = "Reached via the container fallback."
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

        app = _make_app()
        registry = MagicMock()
        registry.get_project = MagicMock(
            return_value=SimpleNamespace(
                id=_CONSENTING_PROJECT_ID, llm_egress_consent=True
            )
        )
        ports = CorePorts(
            identity_provider=MagicMock(),
            authorization_policy=MagicMock(),
            workspace_registry=registry,
            storage=MagicMock(),
            job_scheduler=MagicMock(),
            integration_client=MagicMock(),
        )
        # Deliberately NOT app.state.core_ports -- only the container carries it.
        app.state.runtime_container = SimpleNamespace(ports=ports)

        client = TestClient(app, raise_server_exceptions=True)
        with patch("backend.config.CCDASH_GEMINI_API_KEY", "key-container-fallback"), \
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True), \
             patch(
                 "backend.services.ai_insight.httpx.AsyncClient",
                 return_value=mock_client_instance,
             ):
            resp = client.post("/api/ai/insight", json=_insight_body())

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(
            data["disabled"],
            "consent was not resolved via the runtime-container fallback -- the "
            "second lookup site is dead code again",
        )
        self.assertEqual(data["text"], expected_text)
        registry.get_project.assert_called_once_with(_CONSENTING_PROJECT_ID)

    def test_registry_raising_is_refused_rather_than_500(self) -> None:
        """A registry read that throws refuses instead of propagating."""
        app = _make_app()
        registry = _wire_ports(app, None)
        registry.get_project = MagicMock(side_effect=RuntimeError("registry down"))
        resp = self._post(
            app,
            _insight_body(),
            "the llm_egress_consent read raised",
        )
        self.assertEqual(resp.status_code, 200)
        self._assert_refused(resp)

    def test_consenting_project_reaches_the_adapter(self) -> None:
        """The other side of the gate -- without this, an always-refusing gate

        would pass every negative test above and look correct.
        """
        expected_text = "Health: fine. Risk: none material."
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

        app = _consenting_app()
        client = TestClient(app, raise_server_exceptions=True)
        with patch("backend.config.CCDASH_GEMINI_API_KEY", "key-per-project-ok"), \
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True), \
             patch(
                 "backend.services.ai_insight.httpx.AsyncClient",
                 return_value=mock_client_instance,
             ):
            resp = client.post("/api/ai/insight", json=_insight_body())

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["disabled"])
        self.assertEqual(data["error"], "")
        self.assertEqual(data["text"], expected_text)
        mock_client_instance.post.assert_awaited_once()

    def test_the_named_project_is_the_one_consulted(self) -> None:
        """The consent read must use the request's project id, not any default."""
        app = _make_app()
        registry = _wire_ports(
            app, SimpleNamespace(id="proj-x", llm_egress_consent=False)
        )
        resp = self._post(
            app,
            _insight_body(project_id="proj-x"),
            "the named project declined",
        )
        self._assert_refused(resp)
        registry.get_project.assert_called_once_with("proj-x")

    def test_service_defaults_are_fail_closed(self) -> None:
        """A caller that never learned about the new params must NOT send.

        Pins the defaults on ``generate_dashboard_insight`` itself: an
        un-updated caller degrades to DISABLED rather than to egress.
        """
        import asyncio

        from backend.services.ai_insight import generate_dashboard_insight

        with patch("backend.config.CCDASH_GEMINI_API_KEY", "key-defaults"), \
             patch("backend.config.CCDASH_LLM_EGRESS_CONSENT", True), \
             patch(
                 "backend.adapters.llm.gemini.GeminiTextCompletionAdapter",
                 self._explode("the service was called with default consent args"),
             ):
            result = asyncio.run(
                generate_dashboard_insight(metrics=[], tasks=[])
            )

        self.assertTrue(result.disabled)
        self.assertEqual(result.text, "")


if __name__ == "__main__":
    unittest.main()
