"""hosted-llm-anthropic-ica-lane-v1 (M3) -- ``AnthropicTextCompletionAdapter``.

Covers this leg's required assertions (see the implementation plan's M3 and
the leg brief this file was written against):

  1. Wire shape: POSTs ``{base}/v1/messages``, sends
     ``anthropic-version: 2023-06-01``, sends the credential as the
     ``x-api-key`` header and NEVER in the URL.
  2. Model-id safety: a ``[1m]``-suffixed model id is NEVER sent on the
     wire -- this adapter's design call is to REJECT it at construction
     (raise ``ValueError``) rather than silently strip the suffix; see
     ``AnthropicTextCompletionAdapter.__init__``'s docstring for the
     rationale.
  3. Provenance enforcement: a wrong-provenance envelope is rejected before
     any network call.
  4. No provider error body ever reaches a log (M1 hardening, mirrored from
     ``backend/tests/test_session_naming_hosted_backend.py``'s
     ``ProviderErrorBodyNeverLoggedTests``).
  5. Fail-open degradation: an absent API key returns ``None`` without
     attempting a network call.
  6. Response parsing is generic across a Bedrock-shaped (``msg_bdrk_...``)
     ICA response and a plain Anthropic-direct response -- never asserts on
     an id prefix.

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_anthropic_adapter.py \\
        backend/tests/test_session_naming_hosted_backend.py -v
"""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from backend.adapters.llm.anthropic import (
    ANTHROPIC_VERSION,
    DEFAULT_BASE_URL,
    AnthropicTextCompletionAdapter,
)
from backend.application.ports.llm import (
    PromptEnvelope,
    PromptProvenance,
    envelope_from_aggregate,
    envelope_from_redacted_transcript,
)


def _mock_anthropic_client(
    *,
    response_text: str | None = "A title",
    message_id: str = "msg_01ABCxyz",
    raise_exc: Exception | None = None,
) -> MagicMock:
    mock_client_instance = AsyncMock()
    if raise_exc is not None:
        mock_client_instance.post = AsyncMock(side_effect=raise_exc)
    else:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-4-5",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "content": (
                [{"type": "text", "text": response_text}] if response_text is not None else []
            ),
        }
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    return mock_client_instance


def _mock_anthropic_error_client(status_code: int, body_text: str) -> MagicMock:
    """A mock client whose response's ``raise_for_status()`` raises.

    Carries a distinctive ``body_text`` the adapter must never place in a
    log record (M1: no provider error body may reach a log).
    """
    mock_client_instance = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = body_text
    mock_resp.content = body_text.encode()
    mock_resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            f"{status_code} error", request=MagicMock(), response=mock_resp
        )
    )
    mock_client_instance.post = AsyncMock(return_value=mock_resp)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    return mock_client_instance


class ConstructionRejectsSuffixedModelIdTests(unittest.TestCase):
    """A ``[1m]``-suffixed model id must never reach the wire -- this

    adapter's chosen design is to reject it at construction, loudly, rather
    than silently strip the suffix and send a different id than what was
    configured.
    """

    def test_bare_model_id_constructs_fine(self) -> None:
        adapter = AnthropicTextCompletionAdapter(
            api_key="fake-key", model="claude-haiku-4-5", timeout_seconds=5
        )
        self.assertEqual(adapter._model, "claude-haiku-4-5")  # noqa: SLF001

    def test_one_m_suffixed_model_id_raises_value_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            AnthropicTextCompletionAdapter(
                api_key="fake-key", model="claude-haiku-4-5[1m]", timeout_seconds=5
            )
        self.assertIn("[1m]", str(ctx.exception))

    def test_sonnet_and_opus_suffixed_ids_also_raise(self) -> None:
        for bad_model in ("claude-sonnet-5[1m]", "claude-opus-5[1m]"):
            with self.subTest(bad_model=bad_model):
                with self.assertRaises(ValueError):
                    AnthropicTextCompletionAdapter(
                        api_key="fake-key", model=bad_model, timeout_seconds=5
                    )

    def test_suffixed_model_id_never_reaches_the_wire(self) -> None:
        """End-to-end guarantee: even if a caller only checks for a raise

        in passing, no code path in this adapter can carry a
        ``[1m]``-suffixed id into a request payload -- the constructor
        raises before ``self._model`` is ever assigned, so there is no
        instance carrying the bad value to later POST.
        """
        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient"
        ) as mock_client_cls:
            with self.assertRaises(ValueError):
                AnthropicTextCompletionAdapter(
                    api_key="fake-key", model="claude-sonnet-5[1m]", timeout_seconds=5
                )
        mock_client_cls.assert_not_called()


class WireShapeTests(unittest.IsolatedAsyncioTestCase):
    """POST target, required headers, and credential placement."""

    async def test_posts_to_v1_messages_under_the_configured_base_url(self) -> None:
        mock_client = _mock_anthropic_client(response_text="Fix the login bug")
        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient", return_value=mock_client
        ):
            adapter = AnthropicTextCompletionAdapter(
                api_key="fake-key",
                model="claude-haiku-4-5",
                timeout_seconds=5,
                base_url="https://api.nextgen-beta.ica.ibm.com/ica",
            )
            await adapter.complete(envelope_from_aggregate("hello"))

        called_url = mock_client.post.await_args.args[0]
        self.assertEqual(called_url, "https://api.nextgen-beta.ica.ibm.com/ica/v1/messages")

    async def test_default_base_url_is_anthropic_direct(self) -> None:
        self.assertEqual(DEFAULT_BASE_URL, "https://api.anthropic.com")
        mock_client = _mock_anthropic_client(response_text="A title")
        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient", return_value=mock_client
        ):
            adapter = AnthropicTextCompletionAdapter(
                api_key="fake-key", model="claude-haiku-4-5", timeout_seconds=5
            )
            await adapter.complete(envelope_from_aggregate("hello"))

        called_url = mock_client.post.await_args.args[0]
        self.assertEqual(called_url, "https://api.anthropic.com/v1/messages")

    async def test_sends_anthropic_version_header(self) -> None:
        self.assertEqual(ANTHROPIC_VERSION, "2023-06-01")
        mock_client = _mock_anthropic_client(response_text="A title")
        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient", return_value=mock_client
        ):
            adapter = AnthropicTextCompletionAdapter(
                api_key="fake-key", model="claude-haiku-4-5", timeout_seconds=5
            )
            await adapter.complete(envelope_from_aggregate("hello"))

        headers = mock_client.post.await_args.kwargs.get("headers", {})
        self.assertEqual(headers.get("anthropic-version"), "2023-06-01")

    async def test_credential_travels_as_x_api_key_header_never_in_url(self) -> None:
        mock_client = _mock_anthropic_client(response_text="A title")
        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient", return_value=mock_client
        ):
            adapter = AnthropicTextCompletionAdapter(
                api_key="super-secret-key-123",
                model="claude-haiku-4-5",
                timeout_seconds=5,
            )
            await adapter.complete(envelope_from_aggregate("hello"))

        called_url = mock_client.post.await_args.args[0]
        headers = mock_client.post.await_args.kwargs.get("headers", {})
        self.assertNotIn("super-secret-key-123", called_url)
        self.assertNotIn("key=", called_url)
        self.assertEqual(headers.get("x-api-key"), "super-secret-key-123")
        self.assertNotIn("Authorization", headers)

    async def test_sends_only_documented_top_level_fields(self) -> None:
        """ICA silently accepts unknown top-level fields (200) where

        Anthropic direct 400s on the same request -- so a typo here would
        pass on ICA and only break on the paid lane. Only ``model``,
        ``max_tokens``, and ``messages`` may appear.
        """
        mock_client = _mock_anthropic_client(response_text="A title")
        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient", return_value=mock_client
        ):
            adapter = AnthropicTextCompletionAdapter(
                api_key="fake-key", model="claude-haiku-4-5", timeout_seconds=5
            )
            await adapter.complete(envelope_from_aggregate("hello"))

        payload = mock_client.post.await_args.kwargs.get("json")
        self.assertEqual(set(payload.keys()), {"model", "max_tokens", "messages"})
        self.assertEqual(payload["model"], "claude-haiku-4-5")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "hello"}])


class ProvenanceEnforcementTests(unittest.IsolatedAsyncioTestCase):
    """Fail-closed provenance gate -- checked before any network call."""

    async def test_wrong_provenance_envelope_is_rejected_before_any_network_call(
        self,
    ) -> None:
        adapter = AnthropicTextCompletionAdapter(
            api_key="fake-key", model="claude-haiku-4-5", timeout_seconds=5
        )
        bad_envelope = PromptEnvelope(text="hello", provenance="raw_transcript")  # type: ignore[arg-type]

        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient"
        ) as mock_client_cls:
            with self.assertRaises(ValueError):
                await adapter.complete(bad_envelope)

        mock_client_cls.assert_not_called()

    async def test_both_allowed_provenance_values_reach_the_network_call(self) -> None:
        adapter = AnthropicTextCompletionAdapter(
            api_key="fake-key", model="claude-haiku-4-5", timeout_seconds=5
        )
        for envelope in (
            envelope_from_aggregate("hello"),
            envelope_from_redacted_transcript("hello", redaction_events=0),
        ):
            with self.subTest(provenance=envelope.provenance):
                self.assertIn(
                    envelope.provenance,
                    (PromptProvenance.AGGREGATE, PromptProvenance.TRANSCRIPT_REDACTED),
                )
                mock_client = _mock_anthropic_client(response_text="A title")
                with patch(
                    "backend.adapters.llm.anthropic.httpx.AsyncClient",
                    return_value=mock_client,
                ):
                    result = await adapter.complete(envelope)
                self.assertEqual(result, "A title")

    def test_adapter_is_marked_egress(self) -> None:
        self.assertTrue(AnthropicTextCompletionAdapter.EGRESS)


class ProviderErrorBodyNeverLoggedTests(unittest.IsolatedAsyncioTestCase):
    """M1 hardening -- a non-2xx provider response's body must never reach a log."""

    async def test_non_2xx_response_body_is_absent_from_every_log_record(self) -> None:
        secret_marker = "UPSTREAM_ERROR_BODY_MARKER_9f31a2"
        mock_client = _mock_anthropic_error_client(status_code=403, body_text=secret_marker)
        adapter = AnthropicTextCompletionAdapter(
            api_key="fake-key", model="claude-haiku-4-5", timeout_seconds=5
        )

        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient", return_value=mock_client
        ), self.assertLogs("ccdash.adapters.llm.anthropic", level="WARNING") as captured:
            with self.assertRaises(httpx.HTTPStatusError):
                await adapter.complete(envelope_from_aggregate("hello"))

        joined = "\n".join(captured.output)
        self.assertNotIn(secret_marker, joined)
        # The status code IS expected -- "fixed message plus status code",
        # not a blanket "log nothing."
        self.assertIn("403", joined)

    async def test_transport_error_logs_only_a_fixed_message(self) -> None:
        adapter = AnthropicTextCompletionAdapter(
            api_key="fake-key", model="claude-haiku-4-5", timeout_seconds=5
        )
        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient",
            return_value=_mock_anthropic_client(raise_exc=httpx.ConnectError("Connection refused")),
        ), self.assertLogs("ccdash.adapters.llm.anthropic", level="WARNING") as captured:
            with self.assertRaises(httpx.HTTPError):
                await adapter.complete(envelope_from_aggregate("hello"))

        joined = "\n".join(captured.output)
        self.assertNotIn("Connection refused", joined)
        self.assertIn("transport error", joined.lower())


class FailOpenDegradationTests(unittest.IsolatedAsyncioTestCase):
    """Absent key degrades to ``None`` without attempting a network call."""

    async def test_missing_api_key_returns_none_without_a_network_call(self) -> None:
        adapter = AnthropicTextCompletionAdapter(
            api_key=None, model="claude-haiku-4-5", timeout_seconds=5
        )
        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient"
        ) as mock_client_cls:
            result = await adapter.complete(envelope_from_aggregate("hello"))

        self.assertIsNone(result)
        mock_client_cls.assert_not_called()

    async def test_empty_string_api_key_also_degrades(self) -> None:
        adapter = AnthropicTextCompletionAdapter(
            api_key="", model="claude-haiku-4-5", timeout_seconds=5
        )
        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient"
        ) as mock_client_cls:
            result = await adapter.complete(envelope_from_aggregate("hello"))

        self.assertIsNone(result)
        mock_client_cls.assert_not_called()


class ResponseParsingTests(unittest.IsolatedAsyncioTestCase):
    """Generic Messages-envelope parsing -- never asserts on an id prefix."""

    async def test_bedrock_shaped_ica_response_parses_the_same_as_a_plain_one(self) -> None:
        adapter = AnthropicTextCompletionAdapter(
            api_key="fake-key", model="claude-haiku-4-5", timeout_seconds=5
        )
        mock_client = _mock_anthropic_client(
            response_text="Fix the login bug", message_id="msg_bdrk_01ABCxyz"
        )
        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient", return_value=mock_client
        ):
            result = await adapter.complete(envelope_from_aggregate("hello"))
        self.assertEqual(result, "Fix the login bug")

    async def test_empty_content_array_returns_none(self) -> None:
        adapter = AnthropicTextCompletionAdapter(
            api_key="fake-key", model="claude-haiku-4-5", timeout_seconds=5
        )
        mock_client = _mock_anthropic_client(response_text=None)
        with patch(
            "backend.adapters.llm.anthropic.httpx.AsyncClient", return_value=mock_client
        ):
            result = await adapter.complete(envelope_from_aggregate("hello"))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
