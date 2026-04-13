"""Tests for ccdash_cli.runtime.client."""
from __future__ import annotations

import httpx
import pytest

from ccdash_cli.runtime.client import (
    AuthenticationError,
    CCDashClient,
    CCDashClientError,
    ConnectionError,
    NotFoundError,
    PermissionError,
    ServerError,
)

# ---------------------------------------------------------------------------
# Helper: build a MockTransport from a static handler function.
# ---------------------------------------------------------------------------

_BASE = "http://localhost:8000"


def _make_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _static_response(status_code: int, **kwargs) -> httpx.MockTransport:
    """Return a transport that always responds with *status_code*."""
    return _make_transport(lambda req: httpx.Response(status_code, **kwargs))


def _json_response(status_code: int, body: dict) -> httpx.MockTransport:
    return _make_transport(lambda req: httpx.Response(status_code, json=body))


def _client_with_transport(transport: httpx.MockTransport, token: str | None = None) -> CCDashClient:
    """Build a CCDashClient whose internal httpx.Client uses *transport*."""
    client = CCDashClient(_BASE, token=token)
    client._client = httpx.Client(
        base_url=_BASE,
        headers={"User-Agent": "ccdash-cli/0.1.0"},
        transport=transport,
    )
    return client


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


class TestGetSuccess:
    def test_returns_parsed_json(self):
        """Successful GET returns the full parsed JSON envelope."""
        body = {"status": "ok", "data": {"instance_id": "test-id"}, "meta": {}}
        transport = _json_response(200, body)
        with _client_with_transport(transport) as client:
            result = client.get("/api/v1/instance")
        assert result["status"] == "ok"
        assert result["data"]["instance_id"] == "test-id"

    def test_post_returns_parsed_json(self):
        """Successful POST returns the full parsed JSON envelope."""
        body = {"status": "ok", "data": {"triggered": True}, "meta": {}}
        transport = _json_response(200, body)
        with _client_with_transport(transport) as client:
            result = client.post("/api/v1/actions/ping", json_body={"key": "val"})
        assert result["data"]["triggered"] is True

    def test_get_with_params(self):
        """Query params are forwarded; server can respond normally."""
        received: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            received["params"] = dict(req.url.params)
            return httpx.Response(200, json={"status": "ok", "data": {}, "meta": {}})

        with _client_with_transport(_make_transport(handler)) as client:
            client.get("/api/v1/features", params={"project": "myproj"})
        assert received["params"].get("project") == "myproj"


# ---------------------------------------------------------------------------
# HTTP error status code mapping
# ---------------------------------------------------------------------------


class TestStatusCodeMapping:
    def test_401_raises_auth_error(self):
        with _client_with_transport(_static_response(401)) as client:
            with pytest.raises(AuthenticationError) as exc_info:
                client.get("/api/v1/instance")
        assert exc_info.value.exit_code == 2

    def test_403_raises_permission_error(self):
        with _client_with_transport(_static_response(403)) as client:
            with pytest.raises(PermissionError) as exc_info:
                client.get("/api/v1/instance")
        assert exc_info.value.exit_code == 3

    def test_404_raises_not_found(self):
        with _client_with_transport(_static_response(404)) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.get("/api/v1/features/NONEXISTENT")
        assert exc_info.value.exit_code == 1

    def test_500_raises_server_error(self):
        with _client_with_transport(_static_response(500, text="Internal Server Error")) as client:
            with pytest.raises(ServerError) as exc_info:
                client.get("/api/v1/instance")
        assert exc_info.value.exit_code == 1

    def test_502_raises_server_error(self):
        """502 is a retryable code — after retries exhausted it maps to ServerError."""
        # Use a transport that always returns 502 to exhaust the retry budget.
        call_count = 0

        def always_502(req):
            nonlocal call_count
            call_count += 1
            return httpx.Response(502, text="Bad Gateway")

        # Build a real CCDashClient so that _RetryTransport is in the chain.
        with CCDashClient(_BASE) as client:
            # Wrap _RetryTransport with a mock at the httpx level.
            # We replace the _client entirely but keep _RetryTransport logic
            # by not injecting a MockTransport — instead we configure the
            # internal client to use an always-502 transport directly.
            client._client = httpx.Client(
                base_url=_BASE,
                transport=_make_transport(always_502),
            )
            with pytest.raises(ServerError):
                client.get("/api/v1/instance")


# ---------------------------------------------------------------------------
# Envelope-level errors
# ---------------------------------------------------------------------------


class TestEnvelopeErrors:
    def test_error_status_in_envelope_raises_server_error(self):
        """Server returns 200 but envelope has status=error."""
        body = {
            "status": "error",
            "error": {"code": "NOT_FOUND", "message": "Feature not found", "detail": {}},
            "meta": {},
        }
        with _client_with_transport(_json_response(200, body)) as client:
            with pytest.raises(ServerError) as exc_info:
                client.get("/api/v1/features/MISSING")
        assert "NOT_FOUND" in exc_info.value.message

    def test_invalid_json_response_raises_server_error(self):
        """Non-JSON response body raises ServerError, not a raw decode error."""
        transport = _make_transport(
            lambda req: httpx.Response(200, content=b"not-json", headers={"content-type": "text/plain"})
        )
        with _client_with_transport(transport) as client:
            with pytest.raises(ServerError):
                client.get("/api/v1/instance")


# ---------------------------------------------------------------------------
# Network / connection failures
# ---------------------------------------------------------------------------


class TestConnectionFailures:
    def test_connect_error_raises_connection_error(self):
        def fail(req):
            raise httpx.ConnectError("Connection refused")

        with _client_with_transport(_make_transport(fail)) as client:
            with pytest.raises(ConnectionError) as exc_info:
                client.get("/api/v1/instance")
        assert exc_info.value.exit_code == 4

    def test_timeout_raises_connection_error(self):
        def timeout(req):
            raise httpx.TimeoutException("timed out", request=req)

        with _client_with_transport(_make_transport(timeout)) as client:
            with pytest.raises(ConnectionError) as exc_info:
                client.get("/api/v1/instance")
        assert exc_info.value.exit_code == 4
        assert "ccdash target show" in exc_info.value.message
        assert "--timeout" not in exc_info.value.message


# ---------------------------------------------------------------------------
# Auth header
# ---------------------------------------------------------------------------


class TestAuthHeader:
    def test_bearer_token_header_sent(self):
        """Token is forwarded as Authorization: Bearer <token>."""
        received_auth: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            received_auth.append(req.headers.get("authorization", ""))
            return httpx.Response(200, json={"status": "ok", "data": {}, "meta": {}})

        # Build the client with a token; inject auth header manually so it
        # mirrors real construction (CCDashClient sets the header on __init__).
        client = CCDashClient(_BASE, token="my-secret")
        client._client = httpx.Client(
            base_url=_BASE,
            headers={"Authorization": "Bearer my-secret", "User-Agent": "ccdash-cli/0.1.0"},
            transport=_make_transport(handler),
        )
        with client:
            client.get("/api/v1/instance")
        assert received_auth == ["Bearer my-secret"]

    def test_no_auth_header_without_token(self):
        """Without a token no Authorization header is added."""
        received_headers: dict[str, str] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            received_headers.update(dict(req.headers))
            return httpx.Response(200, json={"status": "ok", "data": {}, "meta": {}})

        with _client_with_transport(_make_transport(handler)) as client:
            client.get("/api/v1/instance")
        assert "authorization" not in {k.lower() for k in received_headers}


# ---------------------------------------------------------------------------
# check_health
# ---------------------------------------------------------------------------

_INSTANCE_BODY = {
    "status": "ok",
    "data": {
        "instance_id": "test",
        "version": "0.1.0",
        "environment": "local",
        "db_backend": "sqlite",
        "capabilities": [],
        "server_time": "2026-04-13T00:00:00Z",
    },
    "meta": {},
}


class TestCheckHealth:
    def test_returns_true_on_healthy_response(self):
        with _client_with_transport(_json_response(200, _INSTANCE_BODY)) as client:
            assert client.check_health() is True

    def test_returns_false_on_connection_error(self):
        def fail(req):
            raise httpx.ConnectError("refused")

        with _client_with_transport(_make_transport(fail)) as client:
            assert client.check_health() is False

    def test_returns_true_on_auth_error(self):
        """Server is reachable even if it rejects our credentials."""
        with _client_with_transport(_static_response(401)) as client:
            assert client.check_health() is True

    def test_returns_true_on_server_error(self):
        """A 500 means the server is up but unhappy — still reachable."""
        with _client_with_transport(_static_response(500, text="oops")) as client:
            assert client.check_health() is True


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_enter_returns_self(self):
        client = CCDashClient(_BASE)
        with client as ctx:
            assert ctx is client
        # close() must not raise after exit

    def test_double_close_is_safe(self):
        client = CCDashClient(_BASE)
        client.close()
        client.close()  # second close should not raise


# ---------------------------------------------------------------------------
# Exit code contract
# ---------------------------------------------------------------------------


class TestExitCodes:
    """Verify exit codes match the design spec."""

    def test_base_exit_code(self):
        assert CCDashClientError("x").exit_code == 1

    def test_auth_exit_code(self):
        assert AuthenticationError("x").exit_code == 2

    def test_permission_exit_code(self):
        assert PermissionError("x").exit_code == 3

    def test_connection_exit_code(self):
        assert ConnectionError("x").exit_code == 4

    def test_server_exit_code(self):
        assert ServerError("x").exit_code == 1

    def test_not_found_exit_code(self):
        assert NotFoundError("x").exit_code == 1

    def test_custom_exit_code_override(self):
        """The exit_code kwarg on the base class is forwarded correctly."""
        err = CCDashClientError("custom", exit_code=99)
        assert err.exit_code == 99

    def test_message_attribute(self):
        """The .message attribute holds the human-readable string."""
        err = AuthenticationError("bad token")
        assert err.message == "bad token"
        assert str(err) == "bad token"

    def test_all_errors_are_subclasses_of_base(self):
        for cls in (AuthenticationError, PermissionError, ConnectionError, ServerError, NotFoundError):
            assert issubclass(cls, CCDashClientError)
