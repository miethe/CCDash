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
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from backend import config

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

    async def execute(self, *, trigger: str = "scheduled") -> SessionNamingSweepRunResult:
        if not bool(getattr(config, "CCDASH_SESSION_NAMING_ENABLED", False)):
            return SessionNamingSweepRunResult(success=True, outcome="disabled")

        projects = self._resolve_projects_to_sweep()
        if not projects:
            return SessionNamingSweepRunResult(success=True, outcome="no_project")

        coalescing_enabled = self.coalescing_enabled and bool(
            getattr(config, "SYNC_COALESCING_ENABLED", True)
        )

        project_results: dict[str, SessionNamingSweepRunResult] = {}
        for project in projects:
            project_id = str(getattr(project, "id", "") or "")
            if not project_id:
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
        """
        if self.project is not None:
            return [self.project]
        workspace_registry = getattr(self.ports, "workspace_registry", None)
        if workspace_registry is None:
            return []
        list_projects = getattr(workspace_registry, "list_projects", None)
        if list_projects is None:
            return []
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
