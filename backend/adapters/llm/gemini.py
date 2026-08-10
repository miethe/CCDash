"""Gemini ``TextCompletionPort`` adapter -- REST ``generateContent`` HTTP client.

Extracted verbatim (P1, zero behaviour change) from
``HostedGeminiNamingBackend._call_gemini``
(``backend/services/session_naming_hosted_backend.py``, pre-P1) and
``ai_insight.generate_dashboard_insight``'s own inline httpx block
(``backend/services/ai_insight.py``, pre-P1) -- both call sites shared the
same REST surface/payload shape already; this adapter is the single place
that shape now lives. Same URL, same payload shape, same
raise-on-transport/HTTP-error semantics -- the caller still owns the
fail-open wrapping and its own response-shape handling
(``AIInsightResult``/derived-name persistence).
"""
from __future__ import annotations

import logging

import httpx

from backend.application.ports.llm import PromptEnvelope, enforce_egress_provenance

__all__ = ["GeminiTextCompletionAdapter"]

logger = logging.getLogger("ccdash.adapters.llm.gemini")

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiTextCompletionAdapter:
    """``TextCompletionPort`` adapter for the Gemini REST ``generateContent`` endpoint.

    hosted-llm-anthropic-ica-lane-v1 M2: this is an EGRESS adapter -- a
    successful call sends ``envelope.text`` to a third-party host over the
    network. ``EGRESS = True`` is the explicit, checkable marker other
    modules (``SessionNamingSweepJob``'s per-project consent gate) use to
    tell this apart from a local-loopback adapter (``OllamaTextCompletionAdapter``,
    ``EGRESS = False``) without inspecting behaviour or guessing from the
    class name.
    """

    EGRESS: bool = True

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url

    async def complete(self, envelope: PromptEnvelope) -> str | None:
        """POST ``envelope.text`` to Gemini; return the raw completion.

        Raises on any transport/HTTP error (including
        ``httpx.HTTPStatusError``) -- the caller is responsible for the
        fail-open wrapping and any error-message formatting (see the port
        module's docstring).

        The API key travels as the ``x-goog-api-key`` request header (Google
        supports this header as an alternative to the ``?key=`` query-string
        form) -- never in the URL, which would otherwise land the credential
        in access logs, proxy logs, and browser history. See
        ``docs/project_plans/implementation_plans/features/hosted-llm-anthropic-ica-lane-v1.md``
        M1.
        """
        # Provenance gate FIRST, before any URL/payload construction or
        # connection -- see ``enforce_egress_provenance``'s own docstring.
        # A wrong-provenance envelope never gets far enough to be sent.
        enforce_egress_provenance(envelope)

        url = f"{self._base_url}/{self._model}:generateContent"
        headers = {"x-goog-api-key": self._api_key}
        payload = {"contents": [{"parts": [{"text": envelope.text}]}]}

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Log the status code only -- never ``exc.response.text`` /
                # ``.content`` / a parsed body, which may echo the request
                # (including the credential-bearing header) or provider-side
                # diagnostic detail back into the log stream.
                logger.warning(
                    "gemini adapter: provider returned a non-2xx response "
                    "(status=%s)",
                    exc.response.status_code,
                )
                raise
            except httpx.HTTPError:
                logger.warning("gemini adapter: transport error calling provider")
                raise
            data = resp.json()

        candidates = data.get("candidates") or [] if isinstance(data, dict) else []
        if not candidates:
            return None
        text = (
            candidates[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        return str(text) if text else None
