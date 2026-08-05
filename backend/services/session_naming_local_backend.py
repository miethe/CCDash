"""Lane A -- local, zero-egress derived session-naming backend (M3, T3-002).

``LocalOllamaNamingBackend`` is the DEFAULT ``naming_backend`` plugged into
``SessionNamingSweepJob`` (``backend/adapters/jobs/session_naming_sweep_job.py``)
when ``CCDASH_SESSION_NAMING_BACKEND`` resolves to ``"local"`` (the default --
see :func:`resolve_naming_backend`). It talks only to a local Ollama daemon
(``CCDASH_OLLAMA_BASE_URL``, default ``http://localhost:11434`` -- a loopback
address, never a third-party endpoint) so the default deployment performs
**zero off-box egress**, per this feature's headline AC.

Input path -- CRITICAL invariant
---------------------------------
Prompt material is read **exclusively** via
``session_detail.get_session_detail`` (``backend/application/services/agent_queries/
session_detail.py``), which already runs every transcript entry through
``agent_queries.redaction.redact_entries`` before returning it. This module
never reads a raw JSONL file and never bypasses that redaction gate -- the
gate must be on the path even for the local backend (secrets scrubbed before
a session's content is ever turned into a model prompt, even a local one).

Fail-open contract
-------------------
Ollama not being installed or not running (the common case for most
deployments -- this is an opt-in-by-usage worker feature, not a hard
dependency) must never crash the sweep tick. Every network call, every
malformed-response path, and every persistence call in
:meth:`LocalOllamaNamingBackend.derive_name` is wrapped so an exception is
logged and turned into a ``None`` return -- "leave ``session_name`` NULL and
log," never a crash. ``SessionNamingSweepJob`` itself wraps every backend
call in a second fail-open layer (``derive_name_fail_open``); this module's
own internal fail-open handling is defense-in-depth, not a substitute for a
backend that could otherwise raise.

Output validation
------------------
A local model's raw completion is untrusted free text: it may be empty,
multi-line, wrapped in quotes, or (rarely) a hallucinated essay far longer
than a title. :func:`_sanitize_title` enforces a hard length bound and
**rejects** (returns ``None`` -- never truncates-and-stores) any output that
is wildly non-conforming, rather than persisting raw model output verbatim.
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
from backend.services.session_naming_prompt import build_prompt_text as _build_prompt_text
from backend.services.session_naming_prompt import sanitize_title as _sanitize_title

__all__ = [
    "LocalOllamaNamingBackend",
    "resolve_naming_backend",
]

logger = logging.getLogger("ccdash.services.session_naming_local_backend")

# ``_build_prompt_text``/``_sanitize_title`` are re-exported (unchanged names,
# for backward compatibility with T3-002's existing test imports) from
# ``session_naming_prompt`` -- the shared, backend-agnostic implementation
# both this module (Lane A) and ``session_naming_hosted_backend`` (Lane B,
# T3-003) build their prompt/output-validation on, rather than each carrying
# its own near-duplicate copy.


class LocalOllamaNamingBackend:
    """Zero-egress naming backend: a local Ollama HTTP client.

    Constructed with the ``CorePorts`` bundle so it can both read a
    candidate's redacted transcript (``session_detail.get_session_detail``)
    and persist the derived name
    (``ports.storage.sessions().set_derived_session_name``) -- persistence is
    this backend's own responsibility (see
    ``session_naming_sweep_job``'s module docstring: the sweep job's loop
    does not persist anything itself).

    Consecutive-failure circuit breaker
    -------------------------------------
    A deployment with no Ollama daemon installed is the COMMON case (this is
    an opt-in-by-usage worker feature, not a hard dependency) -- without a
    breaker, every tick would fetch the full redacted transcript
    (``get_session_detail``) for up to ``CCDASH_SESSION_NAMING_QUOTA``
    candidates BEFORE discovering Ollama is unreachable for each one,
    forever, naming nothing: wasted transcript-parse + redaction work,
    repeated every tick, with no way to short-circuit it. Once
    ``_CONSECUTIVE_FAILURE_THRESHOLD`` Ollama calls in a row have failed (this
    instance's own counter, reset on any success), the breaker "opens":
    :meth:`derive_name` returns ``None`` immediately for every subsequent
    candidate in the SAME and later ticks -- skipping the transcript fetch
    entirely -- until a call succeeds again. This is instance-scoped state,
    not a config flag: it self-heals the moment Ollama becomes reachable
    again (the next successful call resets the counter to 0), with no
    operator action required either to open or to close it.
    """

    #: Consecutive Ollama-call failures (this instance's own counter) before
    #: the breaker opens and skips the transcript fetch for later candidates.
    #: Small and fixed rather than configurable -- this is a wasted-work
    #: guard, not a tunable reliability policy; three failures in a row is
    #: already ample evidence Ollama is down for the rest of this tick.
    _CONSECUTIVE_FAILURE_THRESHOLD = 3

    def __init__(
        self,
        *,
        ports: Any,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.ports = ports
        self.base_url = (base_url or config.CCDASH_OLLAMA_BASE_URL).rstrip("/")
        self.model = model or config.CCDASH_OLLAMA_MODEL
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else config.CCDASH_OLLAMA_TIMEOUT_SECONDS
        )
        self._consecutive_ollama_failures = 0

    async def derive_name(self, candidate: dict[str, Any]) -> str | None:
        """Derive and persist a name for ``candidate``, or return ``None``.

        ``candidate`` is a raw ``sessions`` row (as returned by
        ``list_missing_session_name``) -- at minimum ``id`` and
        ``project_id`` are used. Every failure mode (missing ids, transcript
        fetch failure, Ollama unreachable/timeout, non-conforming output,
        persistence refused by the rank gate) returns ``None`` -- this
        method never raises, so it satisfies the
        ``naming_backend.derive_name`` contract
        (``SessionNamingSweepJob``/``derive_name_fail_open``) even without
        that outer wrapper.

        The circuit breaker is checked FIRST, before the transcript fetch --
        see the class docstring. A tripped breaker is not itself an error:
        it returns ``None`` the same as any other "could not derive a name"
        outcome.
        """
        project_id = str(candidate.get("project_id") or "") if isinstance(candidate, dict) else ""
        session_id = str(candidate.get("id") or "") if isinstance(candidate, dict) else ""
        if not project_id or not session_id:
            return None

        if self._consecutive_ollama_failures >= self._CONSECUTIVE_FAILURE_THRESHOLD:
            # Breaker open: skip the transcript fetch entirely -- the whole
            # point is to avoid paying for get_session_detail (full
            # transcript-parse + redaction pass) when Ollama has already
            # demonstrated it is unreachable for the last N candidates in a
            # row. Logged at INFO once per skipped candidate (mirrors the
            # fail-open logging level below) rather than crashing or raising.
            logger.info(
                "session_naming_local_backend: circuit breaker open "
                "(%d consecutive Ollama failures) -- skipping transcript "
                "fetch for session_id=%s (base_url=%s)",
                self._consecutive_ollama_failures,
                session_id,
                self.base_url,
            )
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
                "session_naming_local_backend: get_session_detail failed for "
                "session_id=%s project_id=%s -- leaving session_name NULL",
                session_id,
                project_id,
                exc_info=True,
            )
            return None

        if bundle is None or bundle.transcript is None:
            return None

        prompt_text = _build_prompt_text(bundle.transcript.items)
        if not prompt_text:
            return None

        try:
            raw_title = await self._call_ollama(prompt_text)
        except Exception:
            # Fail-open: Ollama not installed/running, connection refused,
            # timeout, or any other transport error -- this is the expected,
            # common no-op path for a deployment that hasn't set up Ollama.
            self._consecutive_ollama_failures += 1
            logger.info(
                "session_naming_local_backend: local Ollama call failed/unavailable "
                "for session_id=%s (base_url=%s, model=%s) -- leaving session_name "
                "NULL (fail-open no-op) [consecutive_failures=%d]",
                session_id,
                self.base_url,
                self.model,
                self._consecutive_ollama_failures,
            )
            if self._consecutive_ollama_failures == self._CONSECUTIVE_FAILURE_THRESHOLD:
                logger.warning(
                    "session_naming_local_backend: circuit breaker opening after "
                    "%d consecutive Ollama failures (base_url=%s) -- remaining "
                    "candidates this tick (and until the next successful call) "
                    "will skip the transcript fetch",
                    self._consecutive_ollama_failures,
                    self.base_url,
                )
            return None

        # A successful call closes the breaker -- Ollama has demonstrably
        # recovered, so later candidates should resume paying for the
        # transcript fetch rather than staying short-circuited.
        self._consecutive_ollama_failures = 0

        title = _sanitize_title(raw_title)
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
                "session_naming_local_backend: persisting derived name failed for "
                "session_id=%s project_id=%s",
                session_id,
                project_id,
                exc_info=True,
            )
            return None

        return title if written else None

    def reset_circuit_breaker(self) -> None:
        """Reset the consecutive-failure counter to 0.

        Called once per sweep tick by ``SessionNamingSweepJob._execute_inner``
        (duck-typed -- callers check ``hasattr``/``callable`` rather than
        importing this class, so a future backend without a breaker is
        unaffected) BEFORE the derive loop starts. The breaker's job is to
        abort the REMAINDER of a tick once Ollama has demonstrated it is down
        for that tick -- not to keep this naming lane permanently disabled
        across every future tick once it has ever failed three times in a
        row. Each tick therefore gets a fresh, bounded (at most
        ``_CONSECUTIVE_FAILURE_THRESHOLD`` wasted transcript fetches) chance
        to discover Ollama has come back up.
        """
        self._consecutive_ollama_failures = 0

    async def _call_ollama(self, prompt_text: str) -> str | None:
        """POST to the local Ollama ``/api/generate`` endpoint; return the raw completion.

        Raises on any transport/HTTP error -- the caller (:meth:`derive_name`)
        is responsible for the fail-open wrapping, matching this codebase's
        convention of separating "the call" from "the fail-open guarantee"
        (mirrors ``ai_insight.generate_dashboard_insight``'s
        try/except-at-the-call-site shape, and
        ``session_naming_sweep_job.derive_name_fail_open``'s own separation
        of concerns).
        """
        instruction = (
            "You generate short titles for software development session "
            "transcripts. Read the excerpt below and respond with ONLY a "
            "concise title (3-8 words, no quotation marks, no trailing "
            "punctuation, no explanation) describing what the session was "
            "about.\n\n"
            f"Transcript excerpt:\n{prompt_text}\n\nTitle:"
        )
        payload = {
            "model": self.model,
            "prompt": instruction,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
        response_text = data.get("response") if isinstance(data, dict) else None
        return str(response_text) if response_text else None


def resolve_naming_backend(ports: Any) -> Any | None:
    """Select the ``naming_backend`` object for ``SessionNamingSweepJob``.

    ``"local"`` -- the default, and ANY unrecognized value (fail toward
    zero egress, never toward an unintended hosted call, per
    ``CCDASH_SESSION_NAMING_BACKEND``'s own module-level contract in
    ``backend/config.py``) -- constructs :class:`LocalOllamaNamingBackend`.

    ``"hosted"`` (T3-003, Lane B) is reachable ONLY when BOTH of the
    following hold, checked here (not inside the hosted backend itself, so
    an unreachable path never even gets constructed):

      1. ``CCDASH_SESSION_NAMING_BACKEND`` resolves to ``"hosted"`` (this
         function's own selector, above).
      2. ``CCDASH_REDACTION_PATTERNS_ENABLED`` reads ``True`` (checked via
         :func:`redaction.redaction_patterns_enabled`, the exact same
         env-parsing logic ``redact_entries`` uses internally -- never a
         re-derived duplicate).

    SECURITY-REVIEW NOTE (M3 T3-006, 2026-08-05) -- read this before treating
    "BOTH conditions" as "an operator must take two deliberate actions."
    ``CCDASH_REDACTION_PATTERNS_ENABLED`` defaults ``True``
    (``agent_queries/redaction.py``'s fail-closed default, shared with every
    OTHER read path's Layer-1 secret scrub -- it is not a flag introduced by
    this feature). In practice this means condition 2 above is satisfied by
    doing NOTHING: setting ``CCDASH_SESSION_NAMING_BACKEND=hosted`` ALONE is
    sufficient to make ``HostedGeminiNamingBackend`` reachable on a default
    deployment. This is safe in outcome, not by accident: the redaction scrub
    this condition gates is the SAME mechanism that actually strips secrets
    from the outbound Gemini payload (``get_session_detail`` ->
    ``redact_entries``, re-checked a second time inside
    ``HostedGeminiNamingBackend.derive_name`` itself) -- so "reachable" never
    means "sends unredacted"; it is fail-closed (default True = scrub is ON)
    rather than fail-open. Deriving a name from a live candidate ALSO still
    requires ``CCDASH_GEMINI_API_KEY`` to be set (``derive_name`` returns
    ``None`` immediately without it) -- a genuinely explicit, default-empty
    precondition, distinct from the redaction flag. Reviewed and accepted:
    inverting the redaction default (making it opt-in rather than opt-out)
    would weaken every other read path's secret scrub for the sake of this
    one lane's messaging; the fix here is this corrected docstring plus the
    reachability WARNING logged below, not a changed default.

    Either condition absent makes the hosted path unreachable, and this
    resolver returns ``None`` -- the SAME structural no-op
    ``SessionNamingSweepJob`` already treats as "no backend injected" (its
    derive loop is skipped entirely; ``sessions_named`` stays 0;
    ``candidates_found`` is still reported). This is a deliberate no-op,
    never a silent fallback to sending.
    """
    backend_name = str(getattr(config, "CCDASH_SESSION_NAMING_BACKEND", "local") or "local").strip().lower()
    if backend_name == "hosted":
        if not redaction_patterns_enabled():
            logger.info(
                "session_naming: CCDASH_SESSION_NAMING_BACKEND=hosted requested but "
                "CCDASH_REDACTION_PATTERNS_ENABLED is off -- hosted backend is "
                "unreachable; naming sweep will no-op (never falls back to sending)."
            )
            return None
        # Local import: avoids a module-load-time cycle (the hosted module
        # does not import this one, so this is a one-way lazy edge purely to
        # keep Lane A importable/testable in isolation with zero Lane-B
        # dependency surface, mirroring how `LocalOllamaNamingBackend` is
        # never imported by the hosted module either).
        from backend.services.session_naming_hosted_backend import (
            HostedGeminiNamingBackend,
        )

        # Reachability WARNING (security review, T3-006): logged once per
        # construction (container startup, worker-profile-only) at WARNING
        # -- not the routine INFO/DEBUG level the rest of this module uses --
        # specifically so "this deployment's naming sweep can send
        # transcript-derived text off-box" is a loud, discoverable line in
        # the worker's own log stream, not something only visible by reading
        # config. CCDASH_GEMINI_API_KEY absence still fails this closed at
        # the first `derive_name` call, but a missing key can be added later
        # without this backend being re-constructed, so this line does not
        # promise egress has actually happened -- only that it is reachable.
        logger.warning(
            "session_naming: CCDASH_SESSION_NAMING_BACKEND=hosted -- Lane B "
            "(hosted Gemini) derived-naming backend is now REACHABLE for "
            "this process. Off-box transcript-derived text may be sent once "
            "CCDASH_GEMINI_API_KEY is also set. Redaction "
            "(CCDASH_REDACTION_PATTERNS_ENABLED) is ON, so outbound prompts "
            "are scrubbed before send."
        )
        return HostedGeminiNamingBackend(ports=ports)
    return LocalOllamaNamingBackend(ports=ports)
