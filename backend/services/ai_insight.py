"""AI insight service — proxies Gemini REST API server-side.

The API key is read from config (CCDASH_GEMINI_API_KEY). When the key is
unset the service returns a graceful DISABLED result instead of raising.
Uses httpx (already a project dependency) — no new Python SDK is added.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx  # noqa: F401 -- re-exported so tests can patch
# ``backend.services.ai_insight.httpx.AsyncClient`` (and used below for the
# ``httpx.HTTPStatusError`` exception type); the actual POST now lives in
# ``GeminiTextCompletionAdapter`` (``backend/adapters/llm/gemini.py``), but
# ``httpx`` is a single shared module object, so patching the attribute here
# mutates the same object the adapter's own ``import httpx`` resolves to.

from backend import config
from backend.adapters.llm.gemini import GeminiTextCompletionAdapter
from backend.application.ports.llm import envelope_from_aggregate

logger = logging.getLogger(__name__)

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_GEMINI_MODEL = "gemini-2.0-flash"
_TIMEOUT_SECONDS = 30


class AIInsightResult:
    """Value object returned by the insight service."""

    __slots__ = ("text", "disabled", "error")

    def __init__(
        self,
        *,
        text: str = "",
        disabled: bool = False,
        error: str = "",
    ) -> None:
        self.text = text
        self.disabled = disabled
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "disabled": self.disabled,
            "error": self.error,
        }


async def generate_dashboard_insight(
    *,
    metrics: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> AIInsightResult:
    """Call the Gemini REST API and return an insight string.

    Returns a DISABLED result when CCDASH_GEMINI_API_KEY is unset so the
    caller never receives a 500.
    """
    api_key = config.CCDASH_GEMINI_API_KEY
    if not api_key:
        logger.debug("CCDASH_GEMINI_API_KEY is unset — AI insight is disabled")
        return AIInsightResult(disabled=True)

    tasks_summary = ", ".join(
        f"{t.get('title', '?')} ({t.get('status', '?')}, Cost: ${t.get('cost', 0)})"
        for t in tasks
    )
    metrics_summary = str(metrics[-3:]) if metrics else "[]"

    prompt = (
        "Act as a senior technical project manager. Analyze the following project data for 'CCDash'.\n\n"
        f"Recent Metrics (Last 3 days): {metrics_summary}\n"
        f"Active Tasks: {tasks_summary}\n\n"
        "Provide a concise, 2-sentence executive summary of project health, identifying the biggest "
        "risk or the biggest win. Focus on cost vs. delivery velocity."
    )

    envelope = envelope_from_aggregate(prompt)
    adapter = GeminiTextCompletionAdapter(
        api_key=api_key,
        model=_GEMINI_MODEL,
        timeout_seconds=_TIMEOUT_SECONDS,
        base_url=_GEMINI_BASE_URL,
    )

    try:
        text = await adapter.complete(envelope)
        return AIInsightResult(text=text or "Could not generate insight.")
    except httpx.HTTPStatusError as exc:
        logger.warning("Gemini API HTTP error: %s %s", exc.response.status_code, exc.response.text)
        return AIInsightResult(error=f"Gemini API error: {exc.response.status_code}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini API call failed: %s", exc)
        return AIInsightResult(error="Error connecting to AI insight service.")
