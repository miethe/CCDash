"""Tests for CLI timeout plumbing (CLI-006).

Covers resolve_timeout precedence, env-var fallback, invalid-input behaviour,
backward compatibility, build_client timeout propagation, and e2e slow-response
behaviour (TEST-005).

Operator smoke-test procedure (TEST-005)
----------------------------------------
To reproduce the extended-timeout scenario against a live server:

1. Start the backend: ``npm run dev:backend``
2. Invoke a slow endpoint with a generous timeout::

       ccdash --timeout 120 feature list

   Expected: command completes with exit code 0 (no timeout error).

3. Invoke the same endpoint with a timeout shorter than the server's response
   latency (replace <N> with a sub-second value, e.g. 0.001)::

       ccdash --timeout 0.001 feature list

   Expected: non-zero exit code, stderr includes "timed out".

4. Verify the default (30 s) is used when neither flag nor env var is set::

       ccdash feature list

   Expected: completes normally; ``CCDASH_TIMEOUT`` unset.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import httpx
import pytest
import typer
from typer.testing import CliRunner

from ccdash_cli.main import app
from ccdash_cli.runtime import state as app_state
from ccdash_cli.runtime.state import resolve_timeout

runner = CliRunner()

# ---------------------------------------------------------------------------
# Unit tests: resolve_timeout
# ---------------------------------------------------------------------------


class TestResolveTimeout:
    def test_no_flag_no_env_returns_default(self, monkeypatch):
        """No flag, no env var → 30.0 s, source 'default'."""
        monkeypatch.delenv("CCDASH_TIMEOUT", raising=False)
        secs, src = resolve_timeout(None)
        assert secs == 30.0
        assert src == "default"

    def test_flag_overrides_all(self, monkeypatch):
        """--timeout flag → exact value, source 'flag'."""
        monkeypatch.setenv("CCDASH_TIMEOUT", "120")
        secs, src = resolve_timeout(90.5)
        assert secs == 90.5
        assert src == "flag"

    def test_env_used_when_no_flag(self, monkeypatch):
        """CCDASH_TIMEOUT=120, no flag → 120.0, source 'env'."""
        monkeypatch.setenv("CCDASH_TIMEOUT", "120")
        monkeypatch.delenv("CCDASH_TIMEOUT", raising=False)  # ensure clean state
        monkeypatch.setenv("CCDASH_TIMEOUT", "120")
        secs, src = resolve_timeout(None)
        assert secs == 120.0
        assert src == "env"

    def test_flag_wins_over_env(self, monkeypatch):
        """Flag + env both set → flag wins."""
        monkeypatch.setenv("CCDASH_TIMEOUT", "200")
        secs, src = resolve_timeout(60.0)
        assert secs == 60.0
        assert src == "flag"

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        """Non-numeric CCDASH_TIMEOUT → falls back to 30.0 s, source 'default', no crash."""
        monkeypatch.setenv("CCDASH_TIMEOUT", "abc")
        secs, src = resolve_timeout(None)
        assert secs == 30.0
        assert src == "default"

    def test_negative_env_falls_back_to_default(self, monkeypatch):
        """Non-positive CCDASH_TIMEOUT → falls back to 30.0 s."""
        monkeypatch.setenv("CCDASH_TIMEOUT", "-10")
        secs, src = resolve_timeout(None)
        assert secs == 30.0
        assert src == "default"

    def test_zero_env_falls_back_to_default(self, monkeypatch):
        """Zero CCDASH_TIMEOUT → falls back to 30.0 s."""
        monkeypatch.setenv("CCDASH_TIMEOUT", "0")
        secs, src = resolve_timeout(None)
        assert secs == 30.0
        assert src == "default"

    def test_invalid_flag_raises_bad_parameter(self):
        """Negative/zero --timeout flag → typer.BadParameter (hard error)."""
        with pytest.raises(typer.BadParameter):
            resolve_timeout(-5.0)

    def test_zero_flag_raises_bad_parameter(self):
        """Zero --timeout flag → typer.BadParameter."""
        with pytest.raises(typer.BadParameter):
            resolve_timeout(0.0)

    def test_fractional_env_parsed_correctly(self, monkeypatch):
        """CCDASH_TIMEOUT=45.5 (float string) → 45.5, source 'env'."""
        monkeypatch.setenv("CCDASH_TIMEOUT", "45.5")
        secs, src = resolve_timeout(None)
        assert secs == 45.5
        assert src == "env"


# ---------------------------------------------------------------------------
# Integration tests: CLI flag wires through app_state
# ---------------------------------------------------------------------------


class TestCLITimeoutFlag:
    """Verify the --timeout flag propagates into app_state via the callback."""

    def _version_result(self, *extra_args: str) -> tuple[int, float, str]:
        """Invoke ``ccdash [extra_args] version`` and return (exit_code, timeout, source)."""
        result = runner.invoke(app, list(extra_args) + ["version"])
        return result.exit_code, app_state.TIMEOUT_SECONDS, app_state.TIMEOUT_SOURCE

    def test_no_timeout_flag_no_env_default_applied(self, monkeypatch):
        """Backward compat: ccdash version with no timeout flag/env exits 0 with default."""
        monkeypatch.delenv("CCDASH_TIMEOUT", raising=False)
        exit_code, secs, src = self._version_result()
        assert exit_code == 0
        assert secs == 30.0
        assert src == "default"

    def test_timeout_flag_stored_in_app_state(self, monkeypatch):
        """--timeout 90.5 is stored in app_state.TIMEOUT_SECONDS."""
        monkeypatch.delenv("CCDASH_TIMEOUT", raising=False)
        exit_code, secs, src = self._version_result("--timeout", "90.5")
        assert exit_code == 0
        assert secs == 90.5
        assert src == "flag"

    def test_env_timeout_stored_in_app_state(self, monkeypatch):
        """CCDASH_TIMEOUT=120 without flag → stored as 120.0, source 'env'."""
        monkeypatch.setenv("CCDASH_TIMEOUT", "120")
        exit_code, secs, src = self._version_result()
        assert exit_code == 0
        assert secs == 120.0
        assert src == "env"

    def test_flag_beats_env_in_app_state(self, monkeypatch):
        """--timeout 60 with CCDASH_TIMEOUT=200 → 60.0 stored."""
        monkeypatch.setenv("CCDASH_TIMEOUT", "200")
        exit_code, secs, src = self._version_result("--timeout", "60")
        assert exit_code == 0
        assert secs == 60.0
        assert src == "flag"

    def test_negative_timeout_flag_exits_nonzero(self, monkeypatch):
        """--timeout -5 is a hard error → non-zero exit."""
        monkeypatch.delenv("CCDASH_TIMEOUT", raising=False)
        result = runner.invoke(app, ["--timeout", "-5", "version"])
        assert result.exit_code != 0

    def test_invalid_env_does_not_crash_cli(self, monkeypatch):
        """CCDASH_TIMEOUT=abc warns and falls back; CLI still exits 0."""
        monkeypatch.setenv("CCDASH_TIMEOUT", "abc")
        exit_code, secs, src = self._version_result()
        assert exit_code == 0
        assert secs == 30.0
        assert src == "default"


# ---------------------------------------------------------------------------
# build_client uses app_state.TIMEOUT_SECONDS
# ---------------------------------------------------------------------------


class TestBuildClientTimeout:
    """Verify build_client passes the resolved timeout to CCDashClient."""

    def test_build_client_uses_app_state_timeout(self, monkeypatch):
        """build_client(target) constructs CCDashClient with the resolved timeout."""
        from ccdash_cli.runtime.client import build_client, CCDashClient
        from ccdash_cli.runtime.config import TargetConfig

        target = TargetConfig(
            name="local",
            url="http://localhost:8000",
            token=None,
            is_implicit_local=True,
        )

        captured: list[float] = []

        original_init = CCDashClient.__init__

        def _capturing_init(self, base_url, token=None, timeout=30.0):
            captured.append(timeout)
            original_init(self, base_url, token=token, timeout=timeout)

        monkeypatch.setattr(app_state, "TIMEOUT_SECONDS", 75.0)

        with patch.object(CCDashClient, "__init__", _capturing_init):
            client = build_client(target)
            client.close()

        assert captured == [75.0], f"Expected timeout=75.0 but got {captured}"


# ---------------------------------------------------------------------------
# TEST-005: e2e slow-response integration via MockTransport
# ---------------------------------------------------------------------------


def _slow_transport(delay: float) -> httpx.MockTransport:
    """Return a MockTransport that sleeps *delay* seconds then returns 200 JSON."""

    def _handler(request: httpx.Request) -> httpx.Response:
        time.sleep(delay)
        return httpx.Response(
            200,
            json={"status": "ok", "data": {}},
        )

    return httpx.MockTransport(_handler)


def _timeout_transport() -> httpx.MockTransport:
    """Return a MockTransport that always raises TimeoutException."""

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    return httpx.MockTransport(_handler)


class TestSlowResponseTimeout:
    """Verify that CCDashClient honours its timeout against slow HTTP responses.

    Uses httpx.MockTransport to simulate network latency without a real server.
    """

    def _make_client(self, timeout: float, transport: httpx.MockTransport):  # type: ignore[return]
        from ccdash_cli.runtime.client import CCDashClient

        client = CCDashClient.__new__(CCDashClient)
        client._base_url = "http://test-server"
        client._timeout = timeout
        client._client = httpx.Client(
            base_url="http://test-server",
            timeout=timeout,
            transport=transport,
        )
        return client

    def test_extended_timeout_completes_on_slow_response(self):
        """--timeout 120 succeeds even when the mock transport adds 0.05 s delay.

        The transport delay (50 ms) is intentionally well below the configured
        timeout (120 s) to keep the test fast while proving the path works.
        """

        client = self._make_client(timeout=120.0, transport=_slow_transport(0.05))
        try:
            result = client.get("/api/v1/instance")
        finally:
            client.close()

        assert result["status"] == "ok"

    def test_short_timeout_raises_connection_error(self):
        """A transport that always raises TimeoutException maps to ConnectionError.

        This simulates the case where --timeout is shorter than the server's
        response latency and validates the error type/exit-code contract.
        """
        from ccdash_cli.runtime.client import ConnectionError as CLIConnectionError

        client = self._make_client(timeout=0.001, transport=_timeout_transport())
        try:
            with pytest.raises(CLIConnectionError) as exc_info:
                client.get("/api/v1/instance")
        finally:
            client.close()

        assert exc_info.value.exit_code == 4
        assert "timed out" in str(exc_info.value).lower()
