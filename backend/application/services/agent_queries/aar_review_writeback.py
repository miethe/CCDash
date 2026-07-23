"""Gated escalation/writeback seam for the AAR-review autonomous-triage pipeline.

Phase 6-B (T6-005/T6-007/T6-008, ``ccdash-automated-aar-review-v1``) builds the
SINGLE handoff call site through which a computed AAR-review triage verdict +
evidence bundle may ever leave CCDash toward the external Agentic Operator
(``op``)/ARC pipeline. Hard Invariant #2 (CCDash emits only) is enforced here
by construction, not by convention:

  - This module NEVER imports, calls, or shells out to anything resembling a
    swarm/ARC dispatcher, a SkillMeat catalog mutation, or an autonomous-work
    trigger. The only "emission" this module performs is calling the EXISTING
    log-only ``backend.observability.otel.log_aar_review_candidate`` contract
    (the same P1 event ``aar_review.py``'s read path already emits) -- never
    a new push/queue transport, never a direct call into the swarm. There is
    no HTTP client, subprocess, or socket import anywhere in this module.
  - Per Decision D3 (Phase 6-B, locked): the writeback trigger is EXCLUSIVELY
    an ``op approve``'d run. ``emit_aar_review_writeback`` REQUIRES the caller
    to already hold an ``ApprovedRunReference`` -- there is no parameter shape
    that lets a pending/rejected/missing/unknown run reach the handoff.
    ``assert_run_approved`` is the ONLY function on this module's call path
    that inspects run status, and every public entry point below calls it
    FIRST, before anything else (including the quota check) -- refusal never
    depends on any other state.
  - ``AARReviewSweepJob`` (P6-A, ``backend/adapters/jobs/aar_review_sweep_job.py``)
    NEVER imports this module and has no concept of ``op approve`` at all --
    it structurally cannot reach the handoff here. There is no autonomous
    trigger anywhere in this codebase that constructs an
    ``ApprovedRunReference``; the ONLY way one comes into existence is a
    caller external to CCDash's own worker/sweep passing one in explicitly
    (i.e. a human/CLI flow downstream of a real ``op approve``). This is
    enforced by a static-import-boundary test
    (``test_aar_review_writeback_gate.py``), mirroring this feature's
    existing ``test_aar_review_no_llm_imports.py`` precedent.

Guard 3 -- escalation quota (T6-005, OQ-4/T6-002 locked decision)
-------------------------------------------------------------------
Per-project (never global), count-based, rolling-window gate:
``CCDASH_AAR_ESCALATION_QUOTA`` (default 5) approved escalations per project
per ``CCDASH_AAR_ESCALATION_WINDOW_HOURS`` (default 24). ``check_escalation_
quota``/``count_recent_approved_escalations`` are pure functions over an
already-fetched escalation-history sequence -- mirroring this feature's
existing Guard 1/Guard 2 shape (``aar_review_sweep_guards.py``) exactly: this
module performs no I/O of its own to build that history; the caller supplies
it. Over-quota refuses the handoff deterministically; the refusal log records
the COUNT only, never any escalation payload (mirrors ``log_aar_review_
candidate``'s existing "ids and flag names only" redaction posture).

Hard Invariant #1 (unchanged): every check on this module's path is a plain
identity/threshold/count comparison -- there is no model/LLM call anywhere
here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from backend import config
from backend.observability.otel import log_aar_review_candidate

logger = logging.getLogger("ccdash.aar_review.writeback")

__all__ = [
    "ApprovedRunReference",
    "RunNotApprovedError",
    "EscalationQuotaExceededError",
    "EscalationRecord",
    "assert_run_approved",
    "count_recent_approved_escalations",
    "check_escalation_quota",
    "AARReviewWritebackResult",
    "emit_aar_review_writeback",
]


class RunNotApprovedError(RuntimeError):
    """Raised when the writeback seam is invoked without an approved run reference.

    Covers ALL non-approved states uniformly: missing (``None``), pending,
    rejected, and unknown/unrecognized status strings.
    """


class EscalationQuotaExceededError(RuntimeError):
    """Raised when a project has exceeded its rolling per-project escalation quota (Guard 3)."""


@dataclass(slots=True, frozen=True)
class ApprovedRunReference:
    """The caller-supplied reference to an externally ``op approve``'d run.

    CCDash never queries ``op``'s own run store -- per Hard Invariant #2 this
    module has no outbound call to the Agentic Operator at all. The CALLER
    (a human/CLI flow downstream of a real ``op approve`` invocation, never
    CCDash's own worker/sweep) is responsible for constructing this from
    whatever already-approved run record it holds and passing it in
    explicitly.

    ``status`` is intentionally a plain string (not an enum): a value this
    module has never seen (e.g. an unrecognized future status) refuses safely
    via ``assert_run_approved``'s exact-match check rather than raising a
    lookup/KeyError -- "unknown status" is a contract state (refuse), not a
    bug.
    """

    run_id: str
    status: str
    project_id: str
    approved_at: str | None = None


def assert_run_approved(run: ApprovedRunReference | None) -> ApprovedRunReference:
    """Guard: REQUIRE *run* to be a non-``None`` reference with ``status == "approved"``.

    This is the ONLY function on this module's call path that inspects run
    status. Refuses (raises ``RunNotApprovedError``) on:

      - ``run is None`` -- "missing" (no run reference supplied at all).
      - ``run.status != "approved"`` (exact, case-sensitive match) -- covers
        ``"pending"``, ``"rejected"``, and any other/unknown string
        uniformly. Fail-closed: only the literal string ``"approved"``
        passes.

    Never logs anything beyond the run's own ``run_id``/``status`` fields on
    refusal -- never a payload (evidence/verdict/session content).
    """
    if run is None:
        logger.warning("aar_review_writeback refused: no run reference supplied (missing)")
        raise RunNotApprovedError(
            "aar_review_writeback requires an approved run reference; none was supplied"
        )
    if run.status != "approved":
        logger.warning(
            "aar_review_writeback refused: run_id=%s status=%s (not approved)",
            run.run_id,
            run.status,
        )
        raise RunNotApprovedError(
            f"aar_review_writeback requires status == 'approved'; got "
            f"run_id={run.run_id!r} status={run.status!r}"
        )
    return run


@dataclass(slots=True, frozen=True)
class EscalationRecord:
    """One prior approved-escalation event for a project, as already fetched by the caller.

    Pure data -- this module never derives this itself (no DB/HTTP read
    lives here); whatever calls ``check_escalation_quota``/
    ``emit_aar_review_writeback`` is responsible for assembling the history
    sequence from wherever prior approved escalations are tracked.
    """

    project_id: str
    approved_at: datetime


def count_recent_approved_escalations(
    project_id: str,
    history: Iterable[EscalationRecord],
    *,
    window_hours: int,
    now: datetime | None = None,
) -> int:
    """Guard 3 (pure): count *history* entries for *project_id* within the rolling window.

    Pure over an already-fetched sequence -- mirrors
    ``aar_review_sweep_guards.build_triaged_pair_ledger``'s "no I/O of its
    own" shape. ``now`` defaults to the current UTC time; tests pass it
    explicitly for determinism. A naive (tz-unaware) ``approved_at`` is
    treated as UTC.
    """
    reference_now = now or datetime.now(timezone.utc)
    window_start = reference_now - timedelta(hours=window_hours)
    count = 0
    for record in history:
        if record.project_id != project_id:
            continue
        approved_at = record.approved_at
        if approved_at.tzinfo is None:
            approved_at = approved_at.replace(tzinfo=timezone.utc)
        if approved_at >= window_start:
            count += 1
    return count


def check_escalation_quota(
    project_id: str,
    history: Sequence[EscalationRecord],
    *,
    quota: int | None = None,
    window_hours: int | None = None,
    now: datetime | None = None,
) -> int:
    """Guard 3: refuse (raise ``EscalationQuotaExceededError``) when *project_id* is at/over quota.

    Returns the current in-window count on success (informational only).
    Env-configured per PRD §8.1 Guard 3 (OQ-4/T6-002 locked decision):
    ``CCDASH_AAR_ESCALATION_QUOTA`` (default 5), ``CCDASH_AAR_ESCALATION_
    WINDOW_HOURS`` (default 24) -- PER-PROJECT, never global. Logs the COUNT
    only on refusal -- never any escalation payload.
    """
    resolved_quota = quota if quota is not None else int(config.CCDASH_AAR_ESCALATION_QUOTA)
    resolved_window = (
        window_hours if window_hours is not None else int(config.CCDASH_AAR_ESCALATION_WINDOW_HOURS)
    )
    count = count_recent_approved_escalations(
        project_id, history, window_hours=resolved_window, now=now,
    )
    if count >= resolved_quota:
        logger.warning(
            "aar_review_writeback refused: project_id=%s escalation quota exceeded "
            "(count=%d, quota=%d, window_hours=%d)",
            project_id,
            count,
            resolved_quota,
            resolved_window,
        )
        raise EscalationQuotaExceededError(
            f"project {project_id!r} has {count} approved escalation(s) in the last "
            f"{resolved_window}h, at/over quota {resolved_quota}"
        )
    return count


@dataclass(slots=True, frozen=True)
class AARReviewWritebackResult:
    """Return shape of a successfully-accepted handoff (T6-007, AC-P6.1)."""

    accepted: bool
    run_id: str
    project_id: str
    document_id: str
    escalation_count_in_window: int


def emit_aar_review_writeback(
    run: ApprovedRunReference | None,
    *,
    document_id: str,
    session_refs: list[str] | None = None,
    verdict: str | None = None,
    triggered_flags: list[str] | None = None,
    escalation_history: Sequence[EscalationRecord] = (),
    quota: int | None = None,
    window_hours: int | None = None,
    now: datetime | None = None,
) -> AARReviewWritebackResult:
    """The SINGLE gated handoff call site (T6-007, AC-P6.1).

    Order of gates (both fail-closed; both must pass):

      1. ``assert_run_approved`` -- REQUIRES an ``ApprovedRunReference`` with
         ``status == "approved"``; refuses on missing/pending/rejected/
         unknown BEFORE anything else runs, including the quota check below
         (a rejected run must never be able to "pass" by virtue of being
         under quota).
      2. ``check_escalation_quota`` (Guard 3) -- refuses when the approved
         run's OWN project is already at/over its rolling per-project quota.

    Only once BOTH gates pass does this function "emit" -- and per Hard
    Invariant #2, emission here means EXACTLY the existing log-only
    ``log_aar_review_candidate`` contract (the identical event shape the
    ``aar_review.py`` read path already calls on every ``get_review``). This
    function never calls anything resembling a swarm/ARC dispatch, an
    autonomous-work trigger, or a SkillMeat/skills/agents mutation -- there
    is no such import anywhere in this module (see the static-import-
    boundary test, ``test_aar_review_writeback_gate.py``).
    """
    approved_run = assert_run_approved(run)
    escalation_count = check_escalation_quota(
        approved_run.project_id,
        escalation_history,
        quota=quota,
        window_hours=window_hours,
        now=now,
    )

    try:
        log_aar_review_candidate(
            document_id=document_id,
            session_refs=session_refs,
            verdict=verdict,
            triggered_flags=triggered_flags,
        )
    except Exception:  # never let observability break an otherwise-accepted handoff
        logger.debug("aar_review_writeback: log emission failed", exc_info=True)

    logger.info(
        "aar_review_writeback accepted: run_id=%s project_id=%s document_id=%s",
        approved_run.run_id,
        approved_run.project_id,
        document_id,
    )
    return AARReviewWritebackResult(
        accepted=True,
        run_id=approved_run.run_id,
        project_id=approved_run.project_id,
        document_id=document_id,
        escalation_count_in_window=escalation_count,
    )
