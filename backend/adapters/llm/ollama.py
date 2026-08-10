"""Ollama ``TextCompletionPort`` adapter -- local, zero-egress HTTP client.

Extracted verbatim (P1, zero behaviour change) from
``LocalOllamaNamingBackend._call_ollama``
(``backend/services/session_naming_local_backend.py``, pre-P1). Same URL
(``{base_url}/api/generate``), same payload shape, same
raise-on-transport/HTTP-error semantics -- the caller still owns the
fail-open wrapping.
"""
from __future__ import annotations

import logging

import httpx

from backend.application.ports.llm import PromptEnvelope

__all__ = ["OllamaTextCompletionAdapter"]

logger = logging.getLogger("ccdash.adapters.llm.ollama")


class OllamaTextCompletionAdapter:
    """``TextCompletionPort`` adapter for a local Ollama ``/api/generate`` endpoint."""

    def __init__(self, *, base_url: str, model: str, timeout_seconds: float) -> None:
        self._base_url = base_url
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def complete(self, envelope: PromptEnvelope) -> str | None:
        """POST ``envelope.text`` to Ollama; return the raw completion.

        Raises on any transport/HTTP error -- the caller is responsible for
        the fail-open wrapping (see the port module's docstring).
        """
        payload = {
            "model": self._model,
            "prompt": envelope.text,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            try:
                resp = await client.post(f"{self._base_url}/api/generate", json=payload)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Log the status code only -- never ``exc.response.text`` /
                # ``.content`` / a parsed body.
                logger.warning(
                    "ollama adapter: provider returned a non-2xx response "
                    "(status=%s)",
                    exc.response.status_code,
                )
                raise
            except httpx.HTTPError:
                logger.warning("ollama adapter: transport error calling provider")
                raise
            data = resp.json()
        response_text = data.get("response") if isinstance(data, dict) else None
        return str(response_text) if response_text else None
