"""Lane B -- hosted, opt-in derived session-naming backend (M3, T3-003).

``HostedGeminiNamingBackend`` is the ``naming_backend`` plugged into
``SessionNamingSweepJob`` (``backend/adapters/jobs/session_naming_sweep_job.py``)
ONLY when BOTH of the following hold -- enforced at the resolver, not here
(see ``session_naming_local_backend.resolve_naming_backend``, this backend's
sole construction site):

  1. ``CCDASH_SESSION_NAMING_BACKEND=hosted`` (explicit opt-in; defaults to
     ``"local"``).
  2. ``CCDASH_REDACTION_PATTERNS_ENABLED`` is on (defaults ``True`` -- see the
     SECURITY-REVIEW NOTE in ``resolve_naming_backend``'s own docstring:
     because this flag is on by default, condition 1 alone is sufficient to
     make this class reachable on an unmodified deployment. This is safe
     because the SAME flag governs the redaction scrub actually applied to
     the outbound payload below, not merely a reachability check -- but it
     means "BOTH conditions" should not be read as "an operator must take
     two deliberate configuration actions.").

Either flag absent means this class is never constructed, and
``SessionNamingSweepJob`` no-ops (leaves every candidate's ``session_name``
NULL) rather than silently falling back to sending anything.
``CCDASH_GEMINI_API_KEY`` being unset is a THIRD, genuinely explicit
(default-empty) precondition for an actual send -- see :meth:`derive_name`.
This is this feature's THE egress boundary: per the implementation plan's
``decisions``, ``backend/services/ai_insight.py`` sends only aggregated
dashboard metrics off-box today -- Lane B, once opted into, would be
CCDash's FIRST transcript-content egress. The failure mode this module
exists to prevent is "a config default flipped later silently starts
sending transcript prose off-box" -- so every guard here fails CLOSED
(toward "leave NULL and log"), never toward "send it anyway."

Transport
---------
Reuses ``ai_insight.py``'s existing httpx transport pattern (a plain
``httpx.AsyncClient`` POST to the Gemini REST ``generateContent`` endpoint,
keyed by ``CCDASH_GEMINI_API_KEY``) rather than introducing a second HTTP
client idiom or a provider SDK. Unlike ``ai_insight.py`` (which sends only
aggregated metrics/task summaries), the payload here is transcript-derived
excerpt text -- which is why the redaction-gate check above is load-bearing,
not decorative.

Input path -- CRITICAL invariant (same as Lane A)
---------------------------------------------------
Prompt material is read **exclusively** via
``session_detail.get_session_detail`` (``backend/application/services/agent_queries/
session_detail.py``), which runs every transcript entry through
``agent_queries.redaction.redact_entries`` before returning it -- this module
never reads a raw JSONL file and never bypasses that redaction gate.
:meth:`HostedGeminiNamingBackend.derive_name` additionally re-checks
``CCDASH_REDACTION_PATTERNS_ENABLED`` itself, immediately before fetching
that bundle, as defense-in-depth against the flag changing between resolver
construction and this call (mirrors ``SessionNamingSweepJob.execute``'s own
"re-checked at the top ... for defense in depth" pattern for its kill
switch) -- so every outbound Lane B prompt provably passed
``redact_entries`` with patterns enabled, not merely "the resolver checked
once."

Fail-open contract
-------------------
Missing API key, network/timeout errors, non-2xx responses, and
non-conforming output all return ``None`` -- "leave ``session_name`` NULL
and log," never a crash, mirroring
``LocalOllamaNamingBackend.derive_name``'s contract exactly (and
``ai_insight.generate_dashboard_insight``'s own DISABLED-on-missing-key
precedent).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from backend import config
from backend.application.services.agent_queries.redaction import (
    redaction_patterns_enabled,
)
from backend.application.services.agent_queries.session_detail import (
    INCLUDE_TRANSCRIPT,
    get_session_detail,
)
from backend.parsers.session_name_provenance import SESSION_NAME_SOURCE_DERIVED_GENERATIVE
from backend.services.session_naming_prompt import build_prompt_text, sanitize_title

__all__ = ["HostedGeminiNamingBackend"]

logger = logging.getLogger("ccdash.services.session_naming_hosted_backend")

# Mirrors ai_insight.py's own base-URL/model/timeout constants -- same
# provider, same REST surface, same httpx transport idiom. Kept as a
# separate literal (not imported from ai_insight) so this egress boundary's
# request shape does not silently drift if ai_insight.py's own prompt/model
# choice changes for its unrelated (aggregated-metrics-only) use case.
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_GEMINI_MODEL = "gemini-2.0-flash"
_TIMEOUT_SECONDS = 30

_NAMING_INSTRUCTION = (
    "You generate short titles for software development session "
    "transcripts. Read the excerpt below and respond with ONLY a concise "
    "title (3-8 words, no quotation marks, no trailing punctuation, no "
    "explanation) describing what the session was about.\n\n"
    "Transcript excerpt:\n{prompt_text}\n\nTitle:"
)


class HostedGeminiNamingBackend:
    """Opt-in, redaction-gated naming backend: a hosted Gemini REST client.

    Constructed with the ``CorePorts`` bundle so it can both read a
    candidate's redacted transcript (``session_detail.get_session_detail``)
    and persist the derived name
    (``ports.storage.sessions().set_derived_session_name``) -- persistence
    is this backend's own responsibility, same division of labor as
    ``LocalOllamaNamingBackend`` (the sweep job's loop never persists
    anything itself; see ``session_naming_sweep_job``'s module docstring).
    """

    def __init__(
        self,
        *,
        ports: Any,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.ports = ports
        self._api_key = api_key if api_key is not None else config.CCDASH_GEMINI_API_KEY
        self.model = model or _GEMINI_MODEL
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else _TIMEOUT_SECONDS
        )

    async def derive_name(self, candidate: dict[str, Any]) -> str | None:
        """Derive and persist a name for ``candidate``, or return ``None``.

        ``candidate`` is a raw ``sessions`` row (as returned by
        ``list_missing_session_name``) -- at minimum ``id`` and
        ``project_id`` are used. Every failure mode (redaction gate off,
        missing API key, missing ids, transcript fetch failure, Gemini
        unreachable/non-2xx/timeout, non-conforming output, persistence
        refused by the rank gate) returns ``None`` -- this method never
        raises, so it satisfies the ``naming_backend.derive_name`` contract
        (``SessionNamingSweepJob``/``derive_name_fail_open``) even without
        that outer wrapper.
        """
        # Defense-in-depth re-check: the resolver
        # (``session_naming_local_backend.resolve_naming_backend``) already
        # refuses to construct this class unless the redaction gate was on
        # at construction time; this re-check covers the flag flipping off
        # afterward, so every outbound prompt is provably gated at the
        # moment it is actually sent, not merely at some earlier moment.
        if not redaction_patterns_enabled():
            logger.info(
                "session_naming_hosted_backend: CCDASH_REDACTION_PATTERNS_ENABLED "
                "is off -- Lane B is unreachable; leaving session_name NULL "
                "(fail-closed, never sends unredacted)."
            )
            return None

        if not self._api_key:
            logger.debug(
                "session_naming_hosted_backend: CCDASH_GEMINI_API_KEY is unset -- "
                "hosted naming backend is disabled; leaving session_name NULL."
            )
            return None

        project_id = str(candidate.get("project_id") or "") if isinstance(candidate, dict) else ""
        session_id = str(candidate.get("id") or "") if isinstance(candidate, dict) else ""
        if not project_id or not session_id:
            return None

        try:
            bundle = await get_session_detail(
                project_id,
                session_id,
                self.ports,
                include={INCLUDE_TRANSCRIPT},
            )
        except Exception:
            logger.warning(
                "session_naming_hosted_backend: get_session_detail failed for "
                "session_id=%s project_id=%s -- leaving session_name NULL",
                session_id,
                project_id,
                exc_info=True,
            )
            return None

        if bundle is None or bundle.transcript is None:
            return None

        # ``bundle.transcript.items`` has already been through
        # ``redact_entries`` inside ``get_session_detail`` -- this is the
        # text this Lane B prompt is built from; nothing raw is read here.
        prompt_text = build_prompt_text(bundle.transcript.items)
        if not prompt_text:
            return None

        try:
            raw_title = await self._call_gemini(prompt_text)
        except Exception:
            # Fail-open: network error, non-2xx, timeout, malformed
            # response -- this is the expected no-op path for a deployment
            # that opted in but has a transient/misconfigured hosted
            # endpoint.
            logger.info(
                "session_naming_hosted_backend: hosted Gemini call failed for "
                "session_id=%s (model=%s) -- leaving session_name NULL "
                "(fail-open no-op)",
                session_id,
                self.model,
            )
            return None

        title = sanitize_title(raw_title)
        if not title:
            return None

        try:
            written = await self.ports.storage.sessions().set_derived_session_name(
                project_id,
                session_id,
                title,
                SESSION_NAME_SOURCE_DERIVED_GENERATIVE,
            )
        except Exception:
            logger.warning(
                "session_naming_hosted_backend: persisting derived name failed for "
                "session_id=%s project_id=%s",
                session_id,
                project_id,
                exc_info=True,
            )
            return None

        if written:
            # Security-review note (T3-006): `session_name_source` persists
            # the SAME `derived_generative` token Lane A (local) also writes
            # -- a row alone cannot answer "did this specific name cross the
            # egress boundary?" (see the provenance-token deviation entry in
            # implementation-notes.md, accepted rather than fixed by a
            # schema/token split). This INFO log is the compensating audit
            # trail: every successful Lane B write is independently
            # observable in the worker's own log stream by session_id +
            # project_id, without requiring a `session_name_source` change.
            logger.info(
                "session_naming_hosted_backend: derived and persisted a name via "
                "the hosted (Gemini) lane for session_id=%s project_id=%s",
                session_id,
                project_id,
            )

        return title if written else None

    async def _call_gemini(self, prompt_text: str) -> str | None:
        """POST to the Gemini ``generateContent`` REST endpoint; return the raw completion.

        Raises on any transport/HTTP error -- the caller (:meth:`derive_name`)
        is responsible for the fail-open wrapping, matching this codebase's
        convention of separating "the call" from "the fail-open guarantee"
        (mirrors ``ai_insight.generate_dashboard_insight``'s own
        try/except-at-the-call-site shape, and
        ``LocalOllamaNamingBackend._call_ollama``'s identical division of
        labor for Lane A).
        """
        instruction = _NAMING_INSTRUCTION.format(prompt_text=prompt_text)
        url = f"{_GEMINI_BASE_URL}/{self.model}:generateContent?key={self._api_key}"
        payload = {"contents": [{"parts": [{"text": instruction}]}]}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
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
