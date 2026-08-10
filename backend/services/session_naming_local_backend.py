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

hosted-llm-anthropic-ica-lane-v1 M3-B
--------------------------------------
This module also houses :func:`resolve_naming_backend`, the SHARED selector
for every naming lane (not only Lane A) -- so it is also where M3-B wires in
the third, Anthropic/ICA lane (:class:`AnthropicNamingBackend`) alongside
the existing local/hosted(Gemini) lanes, gated behind the SAME
``CCDASH_LLM_EGRESS_CONSENT`` switch the hosted lane already proved in M2.
See :func:`resolve_naming_backend`'s own docstring for the full gating
story, and ``backend/config.py``'s ``CCDASH_LLM_*`` block for the config
surface (``CCDASH_LLM_SESSION_NAMING_LANE``, ``CCDASH_LLM_ANTHROPIC_BASE_URL``
/ ``_API_KEY`` / ``_MODEL``).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx  # noqa: F401 -- re-exported so tests can patch
# ``backend.services.session_naming_local_backend.httpx.AsyncClient``; the
# actual call now lives in ``OllamaTextCompletionAdapter``
# (``backend/adapters/llm/ollama.py``), but ``httpx`` is a single shared
# module object, so patching the attribute here mutates the same object the
# adapter's own ``import httpx`` resolves to.

from backend import config
from backend.adapters.llm.ollama import OllamaTextCompletionAdapter
from backend.application.ports.llm import (
    PromptEnvelope,
    PromptProvenance,
    envelope_from_redacted_transcript,
)
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
    "AnthropicNamingBackend",
    "resolve_naming_backend",
]

# hosted-llm-anthropic-ica-lane-v1 M3-B: per-call HTTP timeout for the
# anthropic lane's adapter. Not part of this leg's CCDASH_LLM_* config
# surface (only CCDASH_LLM_ANTHROPIC_BASE_URL/API_KEY/MODEL were asked
# for) -- mirrors HostedGeminiNamingBackend's own hardcoded
# `_TIMEOUT_SECONDS = 30` module constant rather than inventing a new env
# var this task's scope did not request.
_ANTHROPIC_TIMEOUT_SECONDS = 30

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
        self._adapter = OllamaTextCompletionAdapter(
            base_url=self.base_url,
            model=self.model,
            timeout_seconds=self.timeout_seconds,
        )

    @property
    def EGRESS(self) -> bool:
        """Whether a call from this backend can leave the box.

        hosted-llm-anthropic-ica-lane-v1 M2: delegates to
        ``self._adapter.EGRESS`` -- the adapter is the single source of
        truth (``OllamaTextCompletionAdapter.EGRESS = False``); this
        property exists purely so ``SessionNamingSweepJob``'s per-project
        consent gate can check ``getattr(naming_backend, "EGRESS", False)``
        on the backend object it actually holds, without reaching into a
        private ``_adapter`` attribute.
        """
        return bool(getattr(self._adapter, "EGRESS", False))

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

        instruction = (
            "You generate short titles for software development session "
            "transcripts. Read the excerpt below and respond with ONLY a "
            "concise title (3-8 words, no quotation marks, no trailing "
            "punctuation, no explanation) describing what the session was "
            "about.\n\n"
            f"Transcript excerpt:\n{prompt_text}\n\nTitle:"
        )
        # ``redaction_events`` is not currently threaded through
        # ``get_session_detail``'s returned bundle -- passing 0 rather than
        # fabricating a count (P2/P3 territory per the contract's Risk
        # Areas; see the Completion Report's follow-up recommendation).
        #
        # This lane builds the envelope directly (not via
        # ``envelope_from_redacted_transcript``'s fail-closed factory)
        # deliberately: that factory's redaction-gate check exists to guard
        # the off-box EGRESS boundary (Lane B/Gemini), and this lane never
        # checked that flag before P1 (it is loopback-only, zero-egress by
        # construction -- see the class docstring). Gating it here would be
        # a genuine, untested behaviour change, not a preserved one.
        envelope = PromptEnvelope(
            text=instruction,
            provenance=PromptProvenance.TRANSCRIPT_REDACTED,
            redaction_events=0,
        )

        try:
            raw_title = await self._adapter.complete(envelope)
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

    # ``_call_ollama`` (the raw httpx POST to Ollama's ``/api/generate``)
    # moved to ``OllamaTextCompletionAdapter`` (``backend/adapters/llm/ollama.py``,
    # P1 TextCompletionPort seam) -- ``derive_name`` now calls
    # ``self._adapter.complete(envelope)`` instead. Same URL, same payload
    # shape, same raise-on-transport/HTTP-error semantics.


class AnthropicNamingBackend:
    """hosted-llm-anthropic-ica-lane-v1 M3-B -- the Anthropic/ICA naming lane.

    Constructed by :func:`resolve_naming_backend` ONLY when BOTH
    ``CCDASH_LLM_EGRESS_CONSENT`` and ``CCDASH_REDACTION_PATTERNS_ENABLED``
    are true -- the exact SAME two structural gates that already guard
    :class:`~backend.services.session_naming_hosted_backend.HostedGeminiNamingBackend`
    (see that resolver's own docstring); this class is never constructed
    any other way, and never re-checks consent itself (there is nothing
    left to re-check -- consent is deployment-wide, read once at process
    start, same as every other flag in ``backend/config.py``).

    This class is the SECOND line of defense, deferring two further,
    genuinely explicit degrade-not-fail preconditions to :meth:`derive_name`
    -- mirroring ``HostedGeminiNamingBackend``'s own "``CCDASH_GEMINI_API_KEY``
    unset -> disabled" precedent exactly:

      - ``CCDASH_LLM_ANTHROPIC_API_KEY`` unset -> lane disabled (leaves
        ``session_name`` NULL, logs, never sends, never raises).
      - ``CCDASH_LLM_ANTHROPIC_MODEL`` unset -> lane ALSO disabled, the
        exact same way. This var deliberately has NO config-level default
        (see ``config.CCDASH_LLM_ANTHROPIC_MODEL``'s own comment) -- an
        absent model is this feature's intended failure mode, not a bug to
        paper over with a guessed default.

    A THIRD failure mode -- the provider being unreachable (network error,
    non-2xx, timeout, or even a construction-time adapter mismatch --
    caught by :func:`resolve_naming_backend` itself before this class is
    ever built) -- also degrades to ``None`` from :meth:`derive_name`. So
    "no consent" (this class is never constructed), "not configured"
    (constructed, but key/model absent), and "provider down" (constructed,
    configured, the call itself failed) are three genuinely distinguishable
    log lines -- never collapsed into one generic failure, per this leg's
    own degradation contract.

    ``adapter`` is INJECTED by the resolver (constructed there from the
    lazily-imported ``AnthropicTextCompletionAdapter`` -- see
    :func:`resolve_naming_backend`) rather than imported by this class
    itself, so this module never imports ``backend.adapters.llm.anthropic``
    at any level, at any time -- the one lazy import lives solely in the
    resolver branch that is only ever reached once both gates above have
    already passed.
    """

    def __init__(
        self,
        *,
        ports: Any,
        adapter: Any,
        api_key: str,
        model: str,
    ) -> None:
        self.ports = ports
        self._adapter = adapter
        self._api_key = api_key
        self.model = model

    @property
    def EGRESS(self) -> bool:
        """Delegates to the injected adapter -- see the sibling backends'

        identical property (``LocalOllamaNamingBackend.EGRESS``,
        ``HostedGeminiNamingBackend.EGRESS``) for the shared rationale:
        ``SessionNamingSweepJob``'s per-project consent gate checks this on
        whichever backend object it actually holds, without reaching into a
        private ``_adapter`` attribute.
        """
        return bool(getattr(self._adapter, "EGRESS", False))

    async def derive_name(self, candidate: dict[str, Any]) -> str | None:
        """Derive and persist a name for ``candidate``, or return ``None``.

        See the class docstring for the "not configured" / "provider down"
        degrade states this method owns; "no consent" never reaches this
        class at all. This method never raises, mirroring every other
        ``naming_backend.derive_name`` implementation in this module.
        """
        if not self._api_key:
            logger.debug(
                "session_naming_local_backend: CCDASH_LLM_ANTHROPIC_API_KEY is "
                "unset -- the anthropic naming lane is disabled; leaving "
                "session_name NULL (not configured, never a crash)."
            )
            return None

        if not self.model:
            logger.debug(
                "session_naming_local_backend: CCDASH_LLM_ANTHROPIC_MODEL is "
                "unset -- the anthropic naming lane is disabled; leaving "
                "session_name NULL (not configured, never a crash). This var "
                "has no default by design -- see config.CCDASH_LLM_ANTHROPIC_MODEL."
            )
            return None

        # Defense-in-depth re-check (mirrors HostedGeminiNamingBackend): the
        # resolver already refused to construct this class unless this gate
        # was on at construction time; this re-check covers the flag
        # flipping off afterward, so every outbound prompt is provably
        # gated at the moment it is actually sent.
        if not redaction_patterns_enabled():
            logger.info(
                "session_naming_local_backend: CCDASH_REDACTION_PATTERNS_ENABLED "
                "is off -- the anthropic naming lane is unreachable; leaving "
                "session_name NULL (fail-closed, never sends unredacted)."
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
                "session_naming_local_backend: get_session_detail failed for "
                "session_id=%s project_id=%s (anthropic lane) -- leaving "
                "session_name NULL",
                session_id,
                project_id,
                exc_info=True,
            )
            return None

        if bundle is None or bundle.transcript is None:
            return None

        # ``bundle.transcript.items`` has already been through
        # ``redact_entries`` inside ``get_session_detail`` -- this is the
        # text this lane's prompt is built from; nothing raw is read here.
        prompt_text = _build_prompt_text(bundle.transcript.items)
        if not prompt_text:
            return None

        instruction = (
            "You generate short titles for software development session "
            "transcripts. Read the excerpt below and respond with ONLY a "
            "concise title (3-8 words, no quotation marks, no trailing "
            "punctuation, no explanation) describing what the session was "
            "about.\n\n"
            f"Transcript excerpt:\n{prompt_text}\n\nTitle:"
        )
        try:
            # The fail-closed factory (not the manual PromptEnvelope(...)
            # construction Lane A uses) -- this IS an egress lane, so the
            # envelope must carry TRANSCRIPT_REDACTED provenance and refuse
            # to build at all while redaction is off, matching
            # HostedGeminiNamingBackend's identical choice.
            envelope = envelope_from_redacted_transcript(instruction, redaction_events=0)
        except RuntimeError:
            # The factory's own fail-closed check refused (redaction
            # flipped off between the re-check above and here) -- same
            # fail-closed outcome, not a new failure path.
            return None

        try:
            raw_title = await self._adapter.complete(envelope)
        except Exception:
            # Fail-open: network error, non-2xx, timeout, malformed
            # response -- the "provider down" degrade state (see class
            # docstring), never a crash.
            logger.info(
                "session_naming_local_backend: anthropic lane call failed for "
                "session_id=%s (model=%s) -- leaving session_name NULL "
                "(fail-open no-op, provider unreachable)",
                session_id,
                self.model,
            )
            return None

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
                "session_id=%s project_id=%s (anthropic lane)",
                session_id,
                project_id,
                exc_info=True,
            )
            return None

        return title if written else None


def resolve_naming_backend(ports: Any) -> Any | None:
    """Select the ``naming_backend`` object for ``SessionNamingSweepJob``.

    ``"local"`` -- the default, and ANY unrecognized value (fail toward
    zero egress, never toward an unintended hosted call, per
    ``CCDASH_SESSION_NAMING_BACKEND``'s own module-level contract in
    ``backend/config.py``) -- constructs :class:`LocalOllamaNamingBackend`.

    The effective lane name comes from ``config.resolve_session_naming_lane()``
    -- a thin wrapper over ``config.resolve_with_legacy_fallback``
    (hosted-llm-anthropic-ica-lane-v1 M3, Named Risk #4's ONE shared fallback
    helper): the PREFERRED ``CCDASH_LLM_SESSION_NAMING_LANE`` wins when set;
    otherwise the legacy ``CCDASH_SESSION_NAMING_BACKEND`` (whose existing
    ``"local"``/``"hosted"`` values keep meaning exactly what they meant
    before); otherwise ``"local"``. Both attributes are re-read on EVERY call
    (never cached into a module-level constant) so that patching EITHER one --
    the new attribute or the legacy one -- is honored, which is what lets the
    pre-existing test suite keep patching
    ``config.CCDASH_SESSION_NAMING_BACKEND`` directly, unmodified, while a
    new test can instead patch ``config.CCDASH_LLM_SESSION_NAMING_LANE``.

    That resolution lives in ``config`` rather than inline here because this
    resolver is not its only consumer: ``SessionNamingSweepJob``'s per-tick
    egress AUDIT event must REPORT the same lane this function RESOLVED, and
    the two are wired to the identical call so they cannot drift (see that
    function's docstring for the drift this closed).

    ``"hosted"`` (T3-003, Lane B / Gemini) and ``"anthropic"`` (M3-B, Lane
    C) are both EGRESS-shaped lanes and are reachable ONLY when ALL of the
    following hold, checked here (not inside either backend itself, so an
    unreachable path never even gets constructed):

      1. The effective lane (above) resolves to ``"hosted"`` or
         ``"anthropic"``.
      2. ``CCDASH_LLM_EGRESS_CONSENT`` reads ``True`` (hosted-llm-anthropic-
         ica-lane-v1 M2 -- the GLOBAL egress consent switch, defaults
         ``False``/fail-closed; checked FIRST, before condition 3, and
         before either lane's backend module is even imported). This is the
         SAME gate for both lanes -- M3 adds no second gate for the new
         provider.
      3. ``CCDASH_REDACTION_PATTERNS_ENABLED`` reads ``True`` (checked via
         :func:`redaction.redaction_patterns_enabled`, the exact same
         env-parsing logic ``redact_entries`` uses internally -- never a
         re-derived duplicate).

    A per-project gate (``projects.llm_egress_consent``) composes with all
    three of the above but is deliberately NOT checked here -- this
    function resolves one backend object for the whole process, while
    per-project consent must be re-evaluated every sweep tick against
    whichever project the tick is currently processing (see
    ``SessionNamingSweepJob.execute``'s fan-out loop,
    ``backend/adapters/jobs/session_naming_sweep_job.py``). Folding it in
    here would capture a single project's consent at construction time,
    which is exactly the asymmetry this feature's rubric forbids.

    SECURITY-REVIEW NOTE (M3 T3-006, 2026-08-05) -- read this before treating
    "ALL conditions" as "an operator must take several deliberate actions."
    ``CCDASH_REDACTION_PATTERNS_ENABLED`` defaults ``True``
    (``agent_queries/redaction.py``'s fail-closed default, shared with every
    OTHER read path's Layer-1 secret scrub -- it is not a flag introduced by
    this feature). In practice this means condition 3 above is satisfied by
    doing NOTHING: setting the lane to ``"hosted"`` or ``"anthropic"`` ALONE
    is sufficient to make that backend reachable on a default deployment
    (once consent is also true). This is safe in outcome, not by accident:
    the redaction scrub this condition gates is the SAME mechanism that
    actually strips secrets from the outbound payload (``get_session_detail``
    -> ``redact_entries``, re-checked a second time inside each backend's own
    ``derive_name``) -- so "reachable" never means "sends unredacted"; it is
    fail-closed (default True = scrub is ON) rather than fail-open. Deriving
    a name from a live candidate on either egress lane ALSO still requires
    that lane's own credential (``CCDASH_GEMINI_API_KEY`` for hosted,
    ``CCDASH_LLM_ANTHROPIC_API_KEY`` **and** ``CCDASH_LLM_ANTHROPIC_MODEL``
    for anthropic) to be set (``derive_name`` returns ``None`` immediately
    without it) -- a genuinely explicit, default-empty precondition, distinct
    from the redaction flag. Reviewed and accepted: inverting the redaction
    default (making it opt-in rather than opt-out) would weaken every other
    read path's secret scrub for the sake of this messaging; the fix here is
    this docstring plus the reachability WARNING logged below, not a changed
    default.

    Any condition absent makes the requested egress lane unreachable, and
    this resolver returns ``None`` -- the SAME structural no-op
    ``SessionNamingSweepJob`` already treats as "no backend injected" (its
    derive loop is skipped entirely; ``sessions_named`` stays 0;
    ``candidates_found`` is still reported). This is a deliberate no-op,
    never a silent fallback to sending.
    """
    backend_name = config.resolve_session_naming_lane()
    if backend_name in ("hosted", "anthropic"):
        # hosted-llm-anthropic-ica-lane-v1 M2: the GLOBAL egress consent
        # gate, checked FIRST and structurally -- this `if not ...: return
        # None` runs before the redaction check below, and both run before
        # EITHER lane's lazy backend import a few lines down. A reviewer can
        # see, by reading this function alone (no call-site tracing
        # required), that false consent makes it IMPOSSIBLE to reach either
        # lane's constructor call at the bottom -- the import itself is
        # never executed, let alone the construction. Defaults False
        # (fail-closed): an operator must set CCDASH_LLM_EGRESS_CONSENT=true
        # explicitly; there is no fallback to any other flag that could
        # accidentally satisfy this condition.
        if not bool(getattr(config, "CCDASH_LLM_EGRESS_CONSENT", False)):
            logger.info(
                "session_naming: lane=%s requested but CCDASH_LLM_EGRESS_CONSENT "
                "is off -- this egress backend is unreachable; naming sweep "
                "will no-op (never falls back to sending).",
                backend_name,
            )
            return None
        if not redaction_patterns_enabled():
            logger.info(
                "session_naming: lane=%s requested but "
                "CCDASH_REDACTION_PATTERNS_ENABLED is off -- this backend is "
                "unreachable; naming sweep will no-op (never falls back to sending).",
                backend_name,
            )
            return None

        if backend_name == "hosted":
            # Local import: avoids a module-load-time cycle (the hosted
            # module does not import this one, so this is a one-way lazy
            # edge purely to keep Lane A importable/testable in isolation
            # with zero Lane-B dependency surface, mirroring how
            # `LocalOllamaNamingBackend` is never imported by the hosted
            # module either).
            from backend.services.session_naming_hosted_backend import (
                HostedGeminiNamingBackend,
            )

            # Reachability WARNING (security review, T3-006): logged once
            # per construction (container startup, worker-profile-only) at
            # WARNING -- not the routine INFO/DEBUG level the rest of this
            # module uses -- specifically so "this deployment's naming sweep
            # can send transcript-derived text off-box" is a loud,
            # discoverable line in the worker's own log stream, not
            # something only visible by reading config.
            # CCDASH_GEMINI_API_KEY absence still fails this closed at the
            # first `derive_name` call, but a missing key can be added
            # later without this backend being re-constructed, so this line
            # does not promise egress has actually happened -- only that it
            # is reachable.
            logger.warning(
                "session_naming: CCDASH_SESSION_NAMING_BACKEND=hosted -- Lane B "
                "(hosted Gemini) derived-naming backend is now REACHABLE for "
                "this process. Off-box transcript-derived text may be sent once "
                "CCDASH_GEMINI_API_KEY is also set. Redaction "
                "(CCDASH_REDACTION_PATTERNS_ENABLED) is ON, so outbound prompts "
                "are scrubbed before send."
            )
            return HostedGeminiNamingBackend(ports=ports)

        # backend_name == "anthropic" -- hosted-llm-anthropic-ica-lane-v1
        # M3-B. Lazy import, mirroring the hosted branch immediately above
        # (never at module top level): this is the ONLY place
        # `backend.adapters.llm.anthropic` is ever imported by this module,
        # and it is only ever reached once both structural gates above have
        # already passed.
        from backend.adapters.llm.anthropic import AnthropicTextCompletionAdapter

        try:
            adapter = AnthropicTextCompletionAdapter(
                base_url=config.CCDASH_LLM_ANTHROPIC_BASE_URL,
                api_key=config.CCDASH_LLM_ANTHROPIC_API_KEY,
                model=config.CCDASH_LLM_ANTHROPIC_MODEL,
                timeout_seconds=_ANTHROPIC_TIMEOUT_SECONDS,
            )
        except Exception:
            # Degrade, never crash the surface: a construction-time failure
            # is treated the same as any other "provider unreachable"
            # outcome elsewhere in this module (see the plan's Named Risk
            # that a silent fail-OPEN is the whole risk here -- this is the
            # mirror-image guard against a fail-CRASH on the same egress
            # boundary, e.g. if the adapter's constructor signature drifts).
            logger.warning(
                "session_naming: failed to construct the anthropic adapter -- "
                "the anthropic naming lane will no-op for this process "
                "(base_url=%s).",
                config.CCDASH_LLM_ANTHROPIC_BASE_URL,
                exc_info=True,
            )
            return None

        backend = AnthropicNamingBackend(
            ports=ports,
            adapter=adapter,
            api_key=config.CCDASH_LLM_ANTHROPIC_API_KEY,
            model=config.CCDASH_LLM_ANTHROPIC_MODEL,
        )

        # Reachability WARNING (mirrors the hosted branch's identical T3-006
        # fix): logged once per construction, at WARNING, only AFTER the
        # adapter/backend were built successfully -- so this line is never
        # emitted for a construction that actually failed above.
        # CCDASH_LLM_ANTHROPIC_API_KEY / CCDASH_LLM_ANTHROPIC_MODEL absence
        # still fails this closed at the first `derive_name` call (see that
        # class), so this line does not promise egress has actually
        # happened -- only that it is reachable.
        logger.warning(
            "session_naming: CCDASH_LLM_SESSION_NAMING_LANE=anthropic -- the "
            "Anthropic/ICA derived-naming backend is now REACHABLE for this "
            "process. Off-box transcript-derived text may be sent once "
            "CCDASH_LLM_ANTHROPIC_API_KEY and CCDASH_LLM_ANTHROPIC_MODEL are "
            "also set. Redaction (CCDASH_REDACTION_PATTERNS_ENABLED) is ON, "
            "so outbound prompts are scrubbed before send."
        )
        return backend

    return LocalOllamaNamingBackend(ports=ports)
