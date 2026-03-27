"""Unit tests for SAMTelemetryClient."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import aiohttp

from backend.models import ExecutionOutcomePayload
from backend.services.integrations.sam_telemetry_client import SAMTelemetryClient


def _make_payload() -> ExecutionOutcomePayload:
    return ExecutionOutcomePayload(
        event_id=uuid4(),
        project_slug="test-project",
        session_id=uuid4(),
        model_family="Opus",
        token_input=100,
        token_output=50,
        cost_usd=0.01,
        tool_call_count=5,
        duration_seconds=60,
        message_count=10,
        outcome_status="completed",
        timestamp=datetime.now(timezone.utc),
        ccdash_version="1.0.0",
    )


def _make_client(**kwargs) -> SAMTelemetryClient:
    defaults = {
        "endpoint_url": "https://sam.example.com/api/v1/analytics/execution-outcomes",
        "api_key": "test-key-xyz",
        "timeout_seconds": 30,
        "allow_insecure": False,
    }
    defaults.update(kwargs)
    return SAMTelemetryClient(**defaults)


def _mock_http_response(status: int, body: str = "") -> MagicMock:
    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value=body)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


def _mock_http_session(response: MagicMock) -> MagicMock:
    session = MagicMock()
    session.post = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


class SAMTelemetryClientConstructorTests(unittest.TestCase):
    def test_valid_https_endpoint_succeeds(self) -> None:
        client = _make_client()
        self.assertEqual(client.endpoint_url, "https://sam.example.com/api/v1/analytics/execution-outcomes")
        self.assertEqual(client.timeout_seconds, 30)

    def test_empty_endpoint_raises(self) -> None:
        with self.assertRaises(ValueError):
            _make_client(endpoint_url="")

    def test_empty_api_key_raises(self) -> None:
        with self.assertRaises(ValueError):
            _make_client(api_key="")

    def test_http_endpoint_raises_by_default(self) -> None:
        with self.assertRaises(ValueError):
            _make_client(endpoint_url="http://sam.example.com/api/v1/analytics/execution-outcomes")

    def test_http_endpoint_allowed_when_insecure_flag_set(self) -> None:
        client = _make_client(
            endpoint_url="http://sam.example.com/api/v1/analytics/execution-outcomes",
            allow_insecure=True,
        )
        self.assertTrue(client.allow_insecure)

    def test_timeout_clamped_to_minimum_one(self) -> None:
        client = _make_client(timeout_seconds=0)
        self.assertEqual(client.timeout_seconds, 1)


class SAMTelemetryClientPushBatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = _make_client()
        self.events = [_make_payload()]

    async def _push_with_status(self, status: int, body: str = "") -> tuple[bool, str | None]:
        response = _mock_http_response(status, body)
        session = _mock_http_session(response)
        with patch("aiohttp.ClientSession", return_value=session):
            return await self.client.push_batch(self.events)

    async def test_status_200_returns_success(self) -> None:
        ok, err = await self._push_with_status(200)
        self.assertTrue(ok)
        self.assertIsNone(err)

    async def test_status_202_returns_success(self) -> None:
        ok, err = await self._push_with_status(202)
        self.assertTrue(ok)
        self.assertIsNone(err)

    async def test_status_429_returns_rate_limited(self) -> None:
        ok, err = await self._push_with_status(429, body="Too Many Requests")
        self.assertFalse(ok)
        self.assertEqual(err, "rate_limited")

    async def test_status_400_returns_abandoned(self) -> None:
        ok, err = await self._push_with_status(400, body="bad payload")
        self.assertFalse(ok)
        self.assertEqual(err, "abandoned:bad payload")

    async def test_status_404_returns_abandoned_with_fallback_body(self) -> None:
        ok, err = await self._push_with_status(404, body="")
        self.assertFalse(ok)
        self.assertEqual(err, "abandoned:HTTP 404")

    async def test_status_500_returns_retry_error(self) -> None:
        ok, err = await self._push_with_status(500, body="Internal Server Error")
        self.assertFalse(ok)
        self.assertEqual(err, "Internal Server Error")

    async def test_status_502_empty_body_falls_back_to_http_label(self) -> None:
        ok, err = await self._push_with_status(502, body="")
        self.assertFalse(ok)
        self.assertEqual(err, "HTTP 502")

    async def test_aiohttp_client_error_returns_retry_error(self) -> None:
        with patch("aiohttp.ClientSession", side_effect=aiohttp.ClientConnectionError("connection refused")):
            ok, err = await self.client.push_batch(self.events)
        self.assertFalse(ok)
        self.assertIn("connection refused", (err or ""))

    async def test_timeout_error_returns_retry_error(self) -> None:
        with patch("aiohttp.ClientSession", side_effect=aiohttp.ServerTimeoutError()):
            ok, err = await self.client.push_batch(self.events)
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    async def test_empty_events_returns_success_without_http_call(self) -> None:
        with patch("aiohttp.ClientSession") as mock_cls:
            ok, err = await self.client.push_batch([])
        mock_cls.assert_not_called()
        self.assertTrue(ok)
        self.assertIsNone(err)

    async def test_push_sends_schema_version_and_events_array(self) -> None:
        response = _mock_http_response(200)
        session = _mock_http_session(response)
        with patch("aiohttp.ClientSession", return_value=session):
            await self.client.push_batch(self.events)

        session.post.assert_called_once()
        posted_json = session.post.call_args[1].get("json", {})
        self.assertEqual(posted_json.get("schema_version"), "1")
        self.assertEqual(len(posted_json.get("events", [])), 1)

    async def test_bearer_token_injected_in_request_headers(self) -> None:
        response = _mock_http_response(200)
        session = _mock_http_session(response)
        with patch("aiohttp.ClientSession", return_value=session):
            await self.client.push_batch(self.events)

        headers = session.post.call_args[1]["headers"]
        self.assertEqual(headers.get("Authorization"), "Bearer test-key-xyz")

    async def test_ssl_override_omitted_for_standard_https(self) -> None:
        response = _mock_http_response(200)
        session = _mock_http_session(response)
        with patch("aiohttp.ClientSession", return_value=session):
            await self.client.push_batch(self.events)

        self.assertNotIn("ssl", session.post.call_args[1])


if __name__ == "__main__":
    unittest.main()
