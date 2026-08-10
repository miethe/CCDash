"""AI insight service — proxies Gemini REST API server-side.

This is an EGRESS path: the assembled prompt leaves the box. It is gated on
the GLOBAL ``CCDASH_LLM_EGRESS_CONSENT`` flag (default false, fail-closed)
in addition to the credential ``CCDASH_GEMINI_API_KEY``. With either absent
the service returns a graceful DISABLED result instead of raising — and
under false consent no egress adapter is constructed at all (the adapter
import itself is below the gate). Uses httpx (already a project dependency)
— no new Python SDK is added.
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
from backend.application.ports.llm import envelope_from_aggregate

# NOTE: ``GeminiTextCompletionAdapter`` is deliberately NOT imported at module
# scope -- it is an EGRESS-marked adapter (``EGRESS = True``) and its import
# lives inside ``generate_dashboard_insight`` BELOW the consent gate, so false
# consent never executes the import, let alone the constructor. Mirrors
# ``resolve_naming_backend`` (``backend/services/session_naming_local_backend.py``),
# which uses the same lazy-import-after-gate posture for the same reason. Do
# not hoist it back up here.

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

    Returns a DISABLED result -- never a 500, never a new exception type --
    when EITHER precondition is absent:

      1. ``CCDASH_LLM_EGRESS_CONSENT`` reads True. This endpoint constructs
         an EGRESS-marked adapter (``GeminiTextCompletionAdapter.EGRESS is
         True``) that sends the assembled prompt off-box, so it sits behind
         the same GLOBAL consent flag as the hosted naming lanes -- not a
         second, weaker gate. Defaults False (fail-closed): an absent or
         unparseable value is False (``config._env_bool``), and the
         ``getattr(..., False)`` default below covers the flag being absent
         from the module entirely. There is no fallback to any other flag
         that could accidentally satisfy it.
      2. ``CCDASH_GEMINI_API_KEY`` is set.

    SCOPE, stated exactly: this lane has ONE consent dimension, not two.
    The per-project ``projects.llm_egress_consent`` column composes with the
    global flag only for the session-naming sweep, which fans out over
    registered projects and therefore HAS a project to consult per unit of
    work. This endpoint's request carries no project id (see
    ``AIInsightRequest`` -- ``metrics`` and ``tasks`` only), so there is no
    project whose consent could be read here; the global flag is the whole
    gate. Do not describe this path as "opt in twice".
    """
    # hosted-llm-anthropic-ica-lane-v1: the GLOBAL egress consent gate,
    # checked FIRST and structurally -- this plain `if not ...: return` runs
    # before the credential read, before the prompt is assembled, and before
    # the adapter module is even IMPORTED further down. A reviewer can see,
    # by reading this function alone (no call-site tracing required), that
    # false consent makes it IMPOSSIBLE to reach the adapter constructor.
    # Same shape as resolve_naming_backend's gate
    # (backend/services/session_naming_local_backend.py) so the two egress
    # entry points fail closed identically.
    if not bool(getattr(config, "CCDASH_LLM_EGRESS_CONSENT", False)):
        logger.info(
            "ai_insight: CCDASH_LLM_EGRESS_CONSENT is off -- the hosted "
            "insight lane is unreachable; returning the DISABLED contract "
            "state (never falls back to sending)."
        )
        return AIInsightResult(disabled=True)

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

    # Lazy import, positioned AFTER the consent gate above -- see the
    # module-scope NOTE. Construction is also deliberately OUTSIDE the
    # try/except below: a constructor failure must propagate, not be folded
    # into the generic "Error connecting" branch.
    from backend.adapters.llm.gemini import GeminiTextCompletionAdapter

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
        # Log the status code plus a fixed message only -- never
        # ``exc.response.text`` / ``.content`` / a parsed body, which may
        # echo request/provider diagnostic detail into the log stream (M1,
        # hosted-llm-anthropic-ica-lane-v1).
        logger.warning(
            "Gemini API HTTP error: provider returned a non-2xx response "
            "(status=%s)",
            exc.response.status_code,
        )
        return AIInsightResult(error=f"Gemini API error: {exc.response.status_code}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini API call failed: %s", exc)
        return AIInsightResult(error="Error connecting to AI insight service.")
