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

import httpx

from backend.application.ports.llm import PromptEnvelope

__all__ = ["GeminiTextCompletionAdapter"]

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiTextCompletionAdapter:
    """``TextCompletionPort`` adapter for the Gemini REST ``generateContent`` endpoint."""

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
        """
        url = f"{self._base_url}/{self._model}:generateContent?key={self._api_key}"
        payload = {"contents": [{"parts": [{"text": envelope.text}]}]}

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
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
