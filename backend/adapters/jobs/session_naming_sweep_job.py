"""Worker job wrapper: the default-off derived session-naming sweep (M3, T3-001).

``SessionNamingSweepJob`` is the background-worker half of the derived-naming
milestone (M3) -- it exists to close the remainder of ``sessions.session_name``
rows that M1 (provider-persisted names) and M2 (subagent inheritance, Codex
``git.branch``, Claude Code ``last-prompt``/truncated-first-message) could
not populate deterministically, by eventually calling a naming backend
(Lane A local / Lane B hosted) on the leftover candidates.

THIS MODULE IMPLEMENTS THE T3-004 GUARD LAYER on top of T3-001's scaffold.
It mirrors ``AARReviewSweepJob``'s shape
(``backend/adapters/jobs/aar_review_sweep_job.py``) as closely as the
differing payload allows -- same multi-project fan-out via
``ports.workspace_registry.list_projects()`` (ADR-006), same
``(project_id, trigger)`` coalescing guard, same per-project
try/except-and-continue error isolation, same default-off flag gate re-checked
at the top of ``execute()`` for defense in depth. It does NOT implement
either naming backend's inference call (Lane A local Ollama client = T3-002,
Lane B hosted client = T3-003) -- it only defines the guard flags
(``CCDASH_SESSION_NAMING_ENABLED``/``_QUOTA``/``_WINDOW_HOURS``/
``_SWEEP_INTERVAL_SECONDS``/``_BACKEND``, all in ``backend/config.py``) and a
fail-open call seam (``naming_backend`` ctor param +
``_derive_name_fail_open``) that T3-002/T3-003 plug their backend
implementation into -- they supply an object with an async
``derive_name(candidate) -> str | None`` method; this job supplies the
quota-bounded loop, the try/except wrapper, and the persist-nothing-on-error
guarantee.

Each tick, for every registered project:

  1. Resolves the candidate set via the
     ``list_missing_session_name(project_id)`` repository query
     (``backend/db/repositories/sessions.py`` /
     ``backend/db/repositories/postgres/sessions.py``) -- exactly the rows
     where ``session_name IS NULL``. This predicate IS the idempotency
     contract: a session with a non-null ``session_name`` from ANY source
     (provider-persisted, subagent-inherited, git.branch, last-prompt,
     truncated-first-message, or a prior sweep-tick's own derived write once
     T3-002/T3-003 land) is never selected again, so this job can never
     re-derive or overwrite an existing name.
  2. Bounds the candidate set to at most ``CCDASH_SESSION_NAMING_QUOTA`` rows
     for this tick (a large backlog is worked down gradually across many
     ticks, never in one unbounded pass).
  3. -- SEAM for T3-002/T3-003 -- when a ``naming_backend`` has been injected
     (production wiring is T3-002/T3-003's scope; ``None`` by default, so
     this loop is a structural no-op in production until then), each
     candidate is passed to ``_derive_name_fail_open``, which calls
     ``naming_backend.derive_name(candidate)`` and returns ``None`` on ANY
     exception (logged, never raised) instead of propagating it. This job
     deliberately does NOT persist the derived name itself -- reading from
     the candidate's redacted transcript bundle
     (``session_detail.get_session_detail`` -- never a raw JSONL read, per
     this feature's redaction invariant) and persisting with
     ``session_name_source = derived_model`` is T3-002/T3-003's scope; this
     loop only guarantees that a raising backend can never crash the tick,
     block a later candidate, or block sync.

HARD INVARIANTS this module upholds and later tasks must preserve:
  - Idempotency: ``session_name IS NULL`` is the only candidate predicate.
  - Fail-open: any error resolving a single project's candidates, OR any
    error raised by ``naming_backend.derive_name`` for a single candidate,
    is logged and isolated -- it never aborts the sweep for the rest of the
    registry/candidate set and never blocks sync (mirrors
    ``AARReviewSweepJob``). A failed derivation leaves that session's
    ``session_name`` NULL, never crashes, never blocks the next candidate.
  - Worker-only: constructed for the ``worker``/``worker-watch`` profiles
    only (``backend/runtime/container.py``'s ``_WORKER_JOB_PROFILES`` gate);
    the ``api`` profile never constructs this job.
  - Fail-closed on consent (hosted-llm-anthropic-ica-lane-v1 M2): when
    ``self.naming_backend`` is egress-shaped (``EGRESS = True``), a project
    whose ``llm_egress_consent`` reads false is skipped for the whole tick
    -- no candidate-count query, no transcript fetch, no egress attempt --
    and this is re-evaluated from the FRESH project row returned by
    ``ports.workspace_registry.list_projects()`` every single tick, never
    cached. A local-only backend (``EGRESS`` absent/False) is unaffected by
    this check regardless of any project's consent value.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from backend import config
from backend.observability import otel as observability

logger = logging.getLogger("ccdash.jobs.session_naming_sweep")

__all__ = [
    "SessionNamingSweepJob",
    "SessionNamingSweepRunResult",
    "derive_name_fail_open",
    "resolve_recency_window_since",
]


def resolve_recency_window_since(*, now: datetime | None = None) -> str | None:
    """Resolve the ``since`` bound ``CCDASH_SESSION_NAMING_WINDOW_HOURS`` implies.

    Closes the gap where ``CCDASH_SESSION_NAMING_WINDOW_HOURS`` was documented
    ("T3-002/T3-003 use") but referenced nowhere outside ``config.py`` --
    setting it had zero effect. Returns an ISO-8601 UTC timestamp
    ``now - window_hours`` for ``list_missing_session_name``'s ``since``
    parameter (``created_at >= since``), or ``None`` when the flag is ``<= 0``
    (an explicit "no recency bound -- consider the whole backlog" opt-out,
    since a literal 0-hour window would otherwise select nothing, a footgun
    rather than a useful configuration).

    This is READ-TIME scoping only -- it never changes
    ``list_missing_session_name``'s own ``session_name IS NULL`` predicate,
    which remains the sole idempotency guard (T3-001): a session named from
    any source is never re-selected regardless of this window.

    ``now`` is accepted for deterministic unit testing; production callers
    omit it (defaults to the real current UTC time).
    """
    window_hours = int(getattr(config, "CCDASH_SESSION_NAMING_WINDOW_HOURS", 24))
    if window_hours <= 0:
        return None
    current = now if now is not None else datetime.now(timezone.utc)
    cutoff = current - timedelta(hours=window_hours)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%S")


async def derive_name_fail_open(backend: Any, candidate: dict[str, Any]) -> str | None:
    """Call ``backend.derive_name(candidate)``, never letting an exception escape.

    This is the fail-open primitive T3-002 (Lane A local) / T3-003 (Lane B
    hosted) build their naming backends against: any exception raised by
    ``derive_name`` (a raising client, a timeout, a malformed response) is
    caught, logged at WARNING with the candidate's id, and turned into a
    ``None`` result -- the caller's contract for "leave ``session_name`` NULL
    and log" (T3-004 AC). A ``None``/falsy return from ``derive_name`` itself
    (no exception, backend simply could not produce a name) is passed through
    unchanged -- that is a normal "no name derived" outcome, not a failure.
    """
    candidate_id = str(candidate.get("id") or "") if isinstance(candidate, dict) else ""
    try:
        derived = await backend.derive_name(candidate)
    except Exception:
        logger.warning(
            "session_naming_sweep: naming backend raised for candidate id=%s -- "
            "leaving session_name NULL (fail-open)",
            candidate_id,
            exc_info=True,
        )
        return None
    return str(derived) if derived else None


@dataclass(slots=True)
class SessionNamingSweepRunResult:
    success: bool
    outcome: str
    candidates_found: int = 0
    sessions_named: int = 0
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class SessionNamingSweepJob:
    """Adapt the M3 derived-naming sweep to the runtime job interface.

    Mirrors ``AARReviewSweepJob``'s shape (``execute(trigger=...) ->
    dataclass result``) so ``backend/runtime/container.py`` and
    ``backend/adapters/jobs/runtime.py`` can register/schedule it via the
    identical profile-gated pattern.
    """

    def __init__(
        self,
        *,
        ports: Any,
        project: Any | None = None,
        coalescing_enabled: bool = True,
        naming_backend: Any | None = None,
    ) -> None:
        self.ports = ports
        self.project = project
        self.coalescing_enabled = coalescing_enabled
        # -- SEAM for T3-002 (Lane A local) / T3-003 (Lane B hosted) --
        # ``None`` in production until one of those tasks constructs this
        # job with a real backend object (an async ``derive_name(candidate)
        # -> str | None`` method). Left unset, `_execute_inner` finds every
        # candidate but derives nothing (`sessions_named` stays 0) -- the
        # same structural no-op T3-001's scaffold already guaranteed.
        self.naming_backend = naming_backend
        # (project_id, trigger) coalescing guard -- mirrors
        # AARReviewSweepJob's ``_in_flight`` set exactly.
        self._in_flight: set[tuple[str, str]] = set()
        # hosted-llm-anthropic-ica-lane-v1 M2 (per-tick consent freshness
        # fix): whether THIS tick's ``_resolve_projects_to_sweep()`` call
        # was able to force a fresh registry read before reading any
        # project's ``llm_egress_consent`` -- see that method's docstring.
        # Defaults True (confirmed) so a job never constructed with a
        # consent-gated backend (the common/default case) is unaffected;
        # flipped per-tick by ``_resolve_projects_to_sweep``.
        self._consent_freshness_confirmed: bool = True
        # Log-once (not per-tick) guard for the "this registry cannot be
        # refreshed at all" warning -- a standing configuration fact about
        # which ``workspace_registry`` implementation this job was wired
        # with, not a per-tick event.
        self._registry_reload_missing_warned = False

    async def execute(self, *, trigger: str = "scheduled") -> SessionNamingSweepRunResult:
        if not bool(getattr(config, "CCDASH_SESSION_NAMING_ENABLED", False)):
            return SessionNamingSweepRunResult(success=True, outcome="disabled")

        projects = self._resolve_projects_to_sweep()
        if not projects:
            return SessionNamingSweepRunResult(success=True, outcome="no_project")

        coalescing_enabled = self.coalescing_enabled and bool(
            getattr(config, "SYNC_COALESCING_ENABLED", True)
        )

        # hosted-llm-anthropic-ica-lane-v1 M2: is THIS tick's naming backend
        # egress-shaped? A static fact about which backend
        # ``resolve_naming_backend`` resolved at process start (see that
        # function's own docstring for why per-project consent is
        # deliberately NOT folded in there) -- read once per tick, outside
        # the per-project loop, purely as a cheap gate for whether the
        # per-project consent check below even applies. Local-only backends
        # (``EGRESS`` absent or False) never require per-project consent.
        backend_requires_consent = self.naming_backend is not None and bool(
            getattr(self.naming_backend, "EGRESS", False)
        )

        project_results: dict[str, SessionNamingSweepRunResult] = {}
        for project in projects:
            project_id = str(getattr(project, "id", "") or "")
            if not project_id:
                continue

            # hosted-llm-anthropic-ica-lane-v1 M2: if THIS tick could not
            # confirm the registry was freshly reloaded before
            # `_resolve_projects_to_sweep()` called `list_projects()` (see
            # that method's docstring/DECISION), every project's consent is
            # UNCONFIRMED for an egress-shaped backend this tick -- fail
            # CLOSED rather than trust a flag that might be a stale,
            # process-start snapshot. Distinct outcome from
            # "consent_declined" (an explicit false reading) so operators
            # can tell "we know they said no" apart from "we don't know
            # what they currently say."
            if backend_requires_consent and not self._consent_freshness_confirmed:
                logger.info(
                    "session_naming_sweep: project_id=%s -- consent freshness "
                    "could not be confirmed this tick (egress-shaped backend "
                    "active) -- skipping rather than trusting a possibly-stale "
                    "llm_egress_consent read.",
                    project_id,
                )
                project_results[project_id] = SessionNamingSweepRunResult(
                    success=True, outcome="consent_unconfirmed"
                )
                continue

            # The PER-PROJECT consent gate. ``project`` comes fresh from
            # ``self._resolve_projects_to_sweep()`` -- called once per
            # ``execute()`` invocation, i.e. once per sweep tick -- via
            # ``ports.workspace_registry.list_projects()`` (ADR-006), which
            # that same method now forces to re-read the registry from the
            # DB every tick (the freshness fix above) rather than relying on
            # `list_projects()` alone to do so. `llm_egress_consent` is
            # therefore read fresh here every tick, never cached on ``self``
            # or captured at job construction: a consent flip in the DB
            # between ticks changes this check's outcome on the very next
            # tick, with no restart of this job instance required. A
            # declined project is recorded (never silently dropped -- same
            # "no silent drop" posture as the coalescing branch below) with
            # outcome="consent_declined" and is never touched by
            # ``_execute_inner`` this tick -- no candidate-count query, no
            # transcript fetch, no egress attempt.
            if backend_requires_consent and not bool(
                getattr(project, "llm_egress_consent", False)
            ):
                logger.info(
                    "session_naming_sweep: project_id=%s has not consented to LLM "
                    "egress (llm_egress_consent=false) -- skipping this tick "
                    "(the active naming backend is egress-shaped).",
                    project_id,
                )
                project_results[project_id] = SessionNamingSweepRunResult(
                    success=True, outcome="consent_declined"
                )
                continue

            coal_key = (project_id, trigger or "scheduled")
            if coalescing_enabled:
                if coal_key in self._in_flight:
                    logger.info(
                        "session_naming_sweep coalesced key=%s — in-flight sweep detected; "
                        "returning deduplicated result (no silent drop)",
                        coal_key,
                    )
                    project_results[project_id] = SessionNamingSweepRunResult(
                        success=True, outcome="coalesced"
                    )
                    continue
                self._in_flight.add(coal_key)
            try:
                if backend_requires_consent:
                    # Reaching here means this project consented (the check
                    # above did not skip it) -- per-tick egress
                    # observability AC: log lane/model/project_id, never a
                    # credential/prompt/transcript.
                    observability.log_llm_egress_event(
                        lane=str(getattr(config, "CCDASH_SESSION_NAMING_BACKEND", "") or ""),
                        model=str(getattr(self.naming_backend, "model", "") or "unknown"),
                        project_id=project_id,
                    )
                project_results[project_id] = await self._execute_inner(project, project_id)
            finally:
                if coalescing_enabled:
                    self._in_flight.discard(coal_key)

        return _aggregate_sweep_results(project_results)

    def _resolve_projects_to_sweep(self) -> list[Any]:
        """Resolve the set of projects this tick should sweep.

        Mirrors ``AARReviewSweepJob._resolve_projects_to_sweep`` exactly:
        an explicit single-project pin (``self.project``) is honored
        byte-for-byte; otherwise every registered project is enumerated via
        ``ports.workspace_registry.list_projects()`` (ADR-006), tolerating a
        test/mock registry that does not implement the method.

        hosted-llm-anthropic-ica-lane-v1 M2 (security-review fix): forces a
        fresh registry read BEFORE calling ``list_projects()`` below, and
        records whether that was actually possible in
        ``self._consent_freshness_confirmed`` for ``execute()`` to consult.

        Why this is load-bearing, not decorative: the production
        ``workspace_registry`` (``ProjectManagerWorkspaceRegistry`` wrapping
        ``DbProjectManager``) hydrates an in-memory snapshot on FIRST use
        (``DbProjectManager._ensure_snapshot``'s own docstring: "hydrate on
        first use") and never re-reads the DB again on its own --
        ``list_projects()`` alone would serve that same snapshot for the
        entire lifetime of the worker process. ``projects.llm_egress_consent``
        has no API in this change set; the only way to change it is a direct
        DB write. Without forcing a reload here, a revoked consent would be
        INVISIBLE to a running worker until it is restarted -- egress would
        keep happening after an operator believed they had stopped it. That
        is precisely the silent-fail-open shape this feature's rubric
        forbids, and it is the failing direction that matters most: a
        missed REVOCATION, not a missed grant.

        ``reload_projects()``/``reload()`` (whichever the registry exposes)
        is cheap -- it only invalidates the cached snapshot
        (``_snapshot_loaded = False``); the actual DB hit happens lazily
        inside ``list_projects()`` immediately below, in THIS SAME tick --
        so calling it unconditionally, every tick, is not a meaningfully
        more expensive operation than the tick was already about to perform.

        DECISION (recorded per the plan's own instruction to justify this in
        a comment, not just in code): when the registry exposes NEITHER
        ``reload_projects()`` nor ``reload()`` -- or the call itself raises
        -- this method does NOT silently proceed on whatever
        ``list_projects()`` happens to return. It sets
        ``self._consent_freshness_confirmed = False`` for this tick, which
        ``execute()`` treats as "every project's consent is UNCONFIRMED" and
        skips ALL projects on ticks where the active naming backend is
        egress-shaped (outcome ``"consent_unconfirmed"``), rather than
        trusting a flag it cannot prove is current. The asymmetry driving
        this choice: the cost of being wrong toward fail-CLOSED is a
        consented project's names going undelivered for a tick or two
        (annoying, fully recoverable, never a safety issue); the cost of
        being wrong toward fail-OPEN is transcript-derived content leaving
        the box after an operator revoked permission for exactly that. Those
        two costs are not symmetric, so this function does not treat them as
        if they were. The missing-reload-hook case is logged ONCE (not per
        tick, via ``self._registry_reload_missing_warned``) -- an operator
        should see this as a standing configuration fact, not tick noise.
        """
        if self.project is not None:
            # Test-only / single-project-pinned mode (pre-existing, not
            # changed by this fix): there is no registry to refresh here,
            # so freshness cannot be confirmed either way. This mode is not
            # how `container.py` constructs the production job (it never
            # passes `project=`), so this is a pre-existing, understood
            # limitation of the pinned escape hatch, not a regression.
            self._consent_freshness_confirmed = False
            return [self.project]
        workspace_registry = getattr(self.ports, "workspace_registry", None)
        if workspace_registry is None:
            self._consent_freshness_confirmed = False
            return []
        list_projects = getattr(workspace_registry, "list_projects", None)
        if list_projects is None:
            self._consent_freshness_confirmed = False
            return []

        reload_callable = getattr(workspace_registry, "reload_projects", None) or getattr(
            workspace_registry, "reload", None
        )
        if callable(reload_callable):
            try:
                reload_callable()
                self._consent_freshness_confirmed = True
            except Exception:
                logger.exception(
                    "session_naming_sweep: workspace_registry reload/invalidation "
                    "raised -- this tick's llm_egress_consent reads cannot be "
                    "trusted as fresh; treating consent as unconfirmed for "
                    "egress-shaped backends this tick only."
                )
                self._consent_freshness_confirmed = False
        else:
            self._consent_freshness_confirmed = False
            if not self._registry_reload_missing_warned:
                self._registry_reload_missing_warned = True
                logger.warning(
                    "session_naming_sweep: workspace_registry exposes neither "
                    "reload_projects() nor reload() -- projects.llm_egress_consent "
                    "freshness cannot be guaranteed for this process. Every "
                    "project's consent will be treated as UNCONFIRMED (and "
                    "skipped) on ticks where the active naming backend is "
                    "egress-shaped, until a refreshable registry is wired in. "
                    "This is a one-time warning, not repeated per tick."
                )

        try:
            projects = list(list_projects())
        except Exception:
            logger.exception("session_naming_sweep: workspace_registry.list_projects() failed")
            return []
        return [p for p in projects if str(getattr(p, "id", "") or "")]

    async def _execute_inner(self, project: Any, project_id: str) -> SessionNamingSweepRunResult:
        sessions_repo = self.ports.storage.sessions()

        # `candidates_found` is the FULL backlog size (the idempotency/backlog
        # signal callers rely on) -- always a single COUNT(*) query, never
        # `len(await list_missing_session_name(...))`, so reporting the
        # backlog number never requires loading the backlog itself into
        # memory (see `count_missing_session_name`'s own docstring).
        try:
            candidates_found = await sessions_repo.count_missing_session_name(project_id)
        except Exception as exc:
            logger.exception(
                "session_naming_sweep: count_missing_session_name failed for project_id=%s", project_id
            )
            return SessionNamingSweepRunResult(success=False, outcome="error", error=str(exc))

        # ── SEAM: T3-002 (Lane A local) / T3-003 (Lane B hosted) ─────────────
        # The derive loop only attempts at most CCDASH_SESSION_NAMING_QUOTA
        # candidates per tick so a large backlog is worked down gradually
        # rather than in one unbounded pass -- and, critically, that bound is
        # now pushed into the SQL query itself (`limit=quota`) rather than
        # sliced in Python after loading every candidate row: without a
        # naming_backend injected there is nothing for those rows to do, so
        # `list_missing_session_name` is skipped entirely in that case (a
        # pure perf win over the prior structural no-op, which still paid for
        # the full unbounded read). `since` narrows the same query to the
        # `CCDASH_SESSION_NAMING_WINDOW_HOURS` recency window -- read-time
        # scoping only; it never changes the `session_name IS NULL`
        # idempotency predicate itself. Deriving a name from the candidate's
        # redacted transcript bundle (session_detail.get_session_detail) and
        # persisting it with session_name_source = derived_generative is
        # T3-002/T3-003's scope -- this loop only guarantees the fail-open
        # call contract (T3-004).
        sessions_named = 0
        if self.naming_backend is not None:
            # Reset any per-backend circuit breaker (e.g.
            # LocalOllamaNamingBackend's consecutive-Ollama-failure counter)
            # at the start of THIS tick's derive loop, so a backend outage
            # discovered last tick never permanently disables the naming
            # lane -- each tick gets a fresh, bounded chance to notice the
            # backend has recovered. Duck-typed: a backend without a breaker
            # (e.g. a future/mocked backend) simply has no such method.
            reset_breaker = getattr(self.naming_backend, "reset_circuit_breaker", None)
            if callable(reset_breaker):
                reset_breaker()
            quota = max(0, int(getattr(config, "CCDASH_SESSION_NAMING_QUOTA", 200)))
            since = resolve_recency_window_since()
            if quota > 0:
                try:
                    candidates = await sessions_repo.list_missing_session_name(
                        project_id, limit=quota, since=since
                    )
                except Exception as exc:
                    logger.exception(
                        "session_naming_sweep: list_missing_session_name failed for project_id=%s",
                        project_id,
                    )
                    return SessionNamingSweepRunResult(
                        success=False,
                        outcome="error",
                        error=str(exc),
                        candidates_found=candidates_found,
                    )
                for candidate in candidates:
                    derived_name = await derive_name_fail_open(self.naming_backend, candidate)
                    if derived_name:
                        sessions_named += 1

        return SessionNamingSweepRunResult(
            success=True,
            outcome="success",
            candidates_found=candidates_found,
            sessions_named=sessions_named,
            details={"projectId": project_id},
        )


def _aggregate_sweep_results(
    project_results: dict[str, SessionNamingSweepRunResult],
) -> SessionNamingSweepRunResult:
    """Fold N per-project results into one tick-level result.

    Mirrors ``aar_review_sweep_job._aggregate_sweep_results``'s precedence
    exactly: no projects -> ``"no_project"``; every project coalesced ->
    ``"coalesced"``; any structural failure -> ``"error"`` (all failed) or
    ``"partial_error"`` (some succeeded); otherwise ``"success"``.
    """
    if not project_results:
        return SessionNamingSweepRunResult(success=True, outcome="no_project")

    results = list(project_results.values())
    outcomes = {r.outcome for r in results}
    if outcomes == {"coalesced"}:
        return SessionNamingSweepRunResult(success=True, outcome="coalesced")

    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    if failures and not successes:
        outcome = "error"
    elif failures:
        outcome = "partial_error"
    else:
        outcome = "success"

    errors = {pid: r.error for pid, r in project_results.items() if r.error}

    return SessionNamingSweepRunResult(
        success=not failures,
        outcome=outcome,
        candidates_found=sum(r.candidates_found for r in results),
        sessions_named=sum(r.sessions_named for r in results),
        error="; ".join(f"{pid}: {err}" for pid, err in sorted(errors.items())) or None,
        details={
            "projectCount": len(project_results),
            "projectIds": sorted(project_results.keys()),
            "perProject": {pid: r.details for pid, r in project_results.items()},
        },
    )
