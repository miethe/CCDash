"""Single-event ingest service for POST /api/v1/ingest/rf-events (T1-003).

Processes one :class:`RfEventPayload` at a time; the router
(``backend/routers/ingest.py``) drives the NDJSON/single-JSON batch loop.

Pipeline per event:
  1. Layer 1 known-secret pattern scan over the *entire* payload (FR-14) —
     runs BEFORE persistence, defensively, even though RF events carry query
     text and cost/quality metrics rather than transcripts.
  2. Map the (redacted) payload onto the ``rf_events`` column contract
     (``backend/db/repositories/rf_events.py::RF_EVENTS_COLUMNS``) — known
     fields land in dedicated columns; the full redacted payload is always
     also persisted verbatim to ``raw_payload_json`` as the forward-compat
     safety net (the RF schema declares ``additionalProperties: true`` at
     every level).
  3. Idempotent insert (``event_id`` PK) wrapped in ``retry_on_locked``
     (ADR-007) — a re-POST of the same ``event_id`` is a silent no-op, never
     a duplicate row and never a 5xx.
  4. On a genuinely NEW insert only: derive/upsert the ``research_runs``
     rollup row and run<->session correlation (Phase 2) — see "Derived-rollup
     + correlation wiring" below.

Cursor-watermark bookkeeping (T1-004) piggybacks on the same
``ingest_cursors`` table and ``IngestCursorRepository`` port used by
``RemoteSessionIngestService`` (``backend/application/services/ingest/session_ingest.py``),
scoped to a dedicated ``source_id='rf'`` row so RF's watermark is tracked
independently of the filesystem/remote-session sources (ADR-009). Dead-letter
classification (T1-004) is the router's responsibility
(``backend/routers/ingest.py``): a :class:`RfEventProcessingError` raised out
of :meth:`RfEventsIngestService.process` represents a *permanent* failure
(the insert failed even after ``retry_on_locked`` exhausted its retries, or
raised a non-lock error) and the router routes it into
``IngestBatchResponse.dead_lettered``, not ``rejected`` — the existing
dead-letter contract per ``docs/guides/remote-ingest-operator-guide.md``
(malformed-schema validation failures caught by the router before
``process()`` is ever called remain in ``rejected``, unchanged from T1-003).

Derived-rollup + correlation wiring (Phase 2, PRD §10 "Technical Architecture")
================================================================================
Once a genuinely NEW ``rf_events`` row has been persisted (``was_new`` is
``True`` — a re-POST of an already-seen ``event_id`` never re-derives, since
``research_runs``' merge semantics SUM several columns per fold and re-folding
an already-folded event would double-count them), this service:

  1. Upserts the derived ``research_runs`` rollup row for that event via
     ``research_runs_repo.upsert_from_event`` (``backend/db/repositories/
     research_runs.py``, T2-001).
  2. Re-reads the just-upserted row and runs run<->session correlation via
     ``entity_link_repo.correlate_research_run`` (``backend/db/repositories/
     entity_graph.py`` / ``backend/db/repositories/postgres/entity_graph.py``,
     T2-006) so an ``entity_links`` row is written whenever a correlated
     session is discoverable.

Both steps are optional (``research_runs_repo``/``entity_link_repo`` default
to ``None``) so existing unit tests that construct this service with only
``repo``/``cursor_repo`` keep working unchanged, and both are best-effort —
mirroring the cursor-bookkeeping helpers below, a failure here is logged and
swallowed rather than raised. The primary ``rf_events`` persistence (AC-1)
must never be blocked by a rollup/correlation failure; the ``research_runs``
row is always safely re-derivable later from the raw ``rf_events`` log via
``backfill_from_rf_events`` (T2-001) regardless of a transient failure here.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.application.models.ingest import RfEventPayload
from backend.application.services.agent_queries.redaction import redact_json_payload_layer1
from backend.db.repositories.base import DEFAULT_WORKSPACE_ID, retry_on_locked

logger = logging.getLogger("ccdash.ingest.rf_events")

# ── Batch-level limits (enforced by the router; exported for tests) ──────────
# Mirrors backend/application/services/ingest/session_ingest.py::MAX_EVENTS_PER_BATCH.

MAX_EVENTS_PER_BATCH: int = 500

# ── Cursor source identity (T1-004) ───────────────────────────────────────────
#
# Dedicated source_id for the ingest_cursors watermark row so RF's progress
# is tracked independently of 'remote_ingest' (filesystem/remote-session
# ingest) and any other registered source (ADR-009).

SOURCE_ID: str = "rf"


# ── Exceptions ───────────────────────────────────────────────────────────────


class RfEventProcessingError(Exception):
    """Raised when a single RF event cannot be persisted.

    The router catches this, appends a ``RejectedEvent``, and continues with
    the rest of the batch.
    """

    def __init__(self, reason: str, code: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


# ── Field-mapping tables (RF payload key → rf_events column suffix) ─────────
#
# additionalProperties: true at every nesting level in the RF schema means an
# unmapped key is never an error — it simply isn't promoted to a dedicated
# column and instead rides along in raw_payload_json (T1-001 forward-compat
# safety net). Adding a new dedicated column later is additive, never breaking.

_METRIC_KEYS: tuple[str, ...] = (
    "source_cards_created",
    "claims_total",
    "claims_supported",
    "claims_mixed",
    "claims_contradicted",
    "claims_inference",
    "claims_speculation",
    "unsupported_claims",
    "verification_passed",
    "tokens_estimated",
    "cost_estimated_usd",
    "latency_minutes",
    "rework_count",
    "drift_score",
    "quality_score",
    "queries_executed",
    "urls_extracted",
    "useful_source_count",
    "duplicate_rate",
    "extraction_failure_rate",
    "citation_coverage",
    "estimated_cost_usd",
    "latency_ms",
)

_GOVERNANCE_KEYS: tuple[str, ...] = (
    "sensitivity",
    "key_profile_used",
    "key_fingerprint",
    "policy_passed",
)

_REUSE_KEYS: tuple[str, ...] = (
    "meatywiki_writeback_candidate",
    "skillbom_candidate",
    "reusable_source_pack_candidate",
)

_HUMAN_REVIEW_KEYS: tuple[str, ...] = (
    "required",
    "status",
    "reviewer",
)


def _coerce_metric_quality_score(value: Any) -> str | None:
    """``metrics.quality_score`` is typed ``[string, number]`` in the RF schema.

    The column is TEXT — coerce a numeric score to its string form so a
    number-typed quality_score never trips a type error at the DB layer.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value) if isinstance(value, (dict, list)) else str(value)


def _payload_to_row(
    payload: dict[str, Any],
    *,
    project_id: str,
    workspace_id: str,
) -> dict[str, Any]:
    """Map a (redacted) RF ``ccdash_event`` payload dict onto the rf_events row shape.

    ``payload`` is expected to already be the redacted, JSON-mode dict form of
    an :class:`RfEventPayload` (i.e. ``model_dump(mode="json")``).
    """
    metrics = payload.get("metrics") or {}
    governance = payload.get("governance") or {}
    reuse = payload.get("reuse") or {}
    human_review = payload.get("human_review") or {}

    row: dict[str, Any] = {
        "event_id": payload["event_id"],
        "workspace_id": workspace_id or DEFAULT_WORKSPACE_ID,
        "project_id": project_id,
        "event_timestamp": payload["timestamp"],
        "rf_project": payload["project"],
        "run_id": payload.get("run_id"),
        "intent_id": payload.get("intent_id"),
        "task_node_id": payload.get("task_node_id"),
        "agent_postures_json": _json_or_none(payload.get("agent_postures")),
        "skillbom_ids_json": _json_or_none(payload.get("skillbom_ids")),
        "tools_json": _json_or_none(payload.get("tools")),
        "input_artifacts_json": _json_or_none(payload.get("input_artifacts")),
        "output_artifacts_json": _json_or_none(payload.get("output_artifacts")),
        "governance_violations_json": _json_or_none(governance.get("violations")),
        "reuse_meatywiki_writeback_candidate": reuse.get("meatywiki_writeback_candidate"),
        "reuse_skillbom_candidate": reuse.get("skillbom_candidate"),
        "reuse_reusable_source_pack_candidate": reuse.get("reusable_source_pack_candidate"),
        "human_review_required": human_review.get("required"),
        "human_review_status": human_review.get("status"),
        "human_review_reviewer": human_review.get("reviewer"),
        "raw_payload_json": json.dumps(payload),
    }

    for key in _METRIC_KEYS:
        col = f"metric_{key}"
        value = metrics.get(key)
        row[col] = _coerce_metric_quality_score(value) if key == "quality_score" else value

    for key in _GOVERNANCE_KEYS:
        row[f"governance_{key}"] = governance.get(key)

    return row


def _json_or_none(value: Any) -> str | None:
    return json.dumps(value) if value is not None else None


# ── Service ───────────────────────────────────────────────────────────────────


class RfEventsIngestService:
    """Process a single RfEventPayload: redact → map → idempotent insert.

    Instantiate once per application process (mirrors
    ``RemoteSessionIngestService``'s process-wide singleton pattern via the
    ``RuntimeContainer``).

    Parameters
    ----------
    repo:
        A ``SqliteRfEventsRepository`` or ``PostgresRfEventsRepository`` (or
        any duck-typed equivalent) exposing
        ``async insert_if_not_exists(row: dict) -> bool``.
    cursor_repo:
        Optional ``SqliteIngestCursorRepository`` / ``PostgresIngestCursorRepository``
        (or any duck-typed equivalent implementing the ``IngestCursorRepository``
        shape: ``get_or_create``/``advance``/``record_error``). When omitted,
        cursor bookkeeping is skipped entirely (used by unit tests that only
        care about the persistence path). Cursor bookkeeping is always
        best-effort: a failure here is logged and swallowed — it must never
        block persistence of the underlying ``rf_events`` row (AC-1 takes
        priority over watermark telemetry).
    research_runs_repo:
        Optional ``SqliteResearchRunsRepository`` / ``PostgresResearchRunsRepository``
        (or any duck-typed equivalent exposing ``upsert_from_event`` and
        ``get_by_run_id``). When supplied, every genuinely new ``rf_events``
        row is folded into the derived ``research_runs`` rollup (T2-001) as
        part of the live ingest path — see module docstring "Derived-rollup +
        correlation wiring". Omitted by default so existing tests that only
        exercise the ``rf_events`` persistence path are unaffected.
    entity_link_repo:
        Optional ``SqliteEntityLinkRepository`` / ``PostgresEntityLinkRepository``
        (or any duck-typed equivalent exposing ``correlate_research_run``).
        Only used when *research_runs_repo* is also supplied — run<->session
        correlation (T2-006) needs a fully-upserted ``research_runs`` row to
        correlate against.
    """

    def __init__(
        self,
        repo: Any,
        cursor_repo: Any | None = None,
        *,
        research_runs_repo: Any | None = None,
        entity_link_repo: Any | None = None,
    ) -> None:
        self._repo = repo
        self._cursor_repo = cursor_repo
        self._research_runs_repo = research_runs_repo
        self._entity_link_repo = entity_link_repo

    async def process(
        self,
        event: RfEventPayload,
        *,
        project_id: str,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> tuple[bool, str]:
        """Process one RF event.

        Returns
        -------
        (was_new_insert, event_id)
            ``was_new_insert`` is False when the event_id already existed
            (idempotent duplicate); True when a new row was written.

        Raises
        ------
        RfEventProcessingError
            When the underlying insert fails after retry_on_locked exhausts
            its retries, or raises a non-lock error.
        """
        raw_payload = event.model_dump(mode="json")

        # ── Layer 1 redaction scan — BEFORE persistence (FR-14) ────────────────
        redacted_payload, redacted_count = redact_json_payload_layer1(raw_payload)
        if redacted_count:
            logger.info(
                "rf_events ingest: redacted %d field(s) for event_id=%s project_id=%s "
                "(payload contents never logged)",
                redacted_count,
                event.event_id,
                project_id,
            )

        row = _payload_to_row(
            redacted_payload,
            project_id=project_id,
            workspace_id=workspace_id,
        )

        # ── Idempotent cursor enqueue (T1-004) ──────────────────────────────────
        # Ensures the source_id='rf' watermark row exists before the first
        # insert for this (project, workspace) pair. INSERT OR IGNORE / ON
        # CONFLICT DO NOTHING at the repository layer makes this idempotent
        # across concurrent requests; retry_on_locked handles SQLite lock
        # contention (ADR-007). Best-effort: never blocks persistence.
        await self._cursor_get_or_create(project_id=project_id, workspace_id=workspace_id)

        try:
            was_new = await retry_on_locked(
                lambda: self._repo.insert_if_not_exists(row),
                repo="rf_events",
            )
        except Exception as exc:
            logger.warning(
                "rf_events ingest: insert failed for event_id=%s project_id=%s: %s",
                event.event_id,
                project_id,
                exc,
            )
            # Permanent failure — record on the cursor row (best-effort) and
            # raise so the router dead-letters this event (T1-004).
            await self._cursor_record_error(
                project_id=project_id,
                workspace_id=workspace_id,
                error_message=str(exc),
            )
            raise RfEventProcessingError(reason=str(exc), code="insert_failed") from exc

        if was_new:
            await self._cursor_advance(
                project_id=project_id,
                workspace_id=workspace_id,
                cursor_value=event.event_id,
                occurred_at=event.timestamp,
            )
            # ── Derive research_runs + run<->session correlation (Phase 2) ──
            # Only for genuinely NEW events -- see module docstring for why a
            # re-processed duplicate must never re-fold into the SUMMED
            # research_runs columns.
            await self._derive_research_run(row, project_id=project_id, workspace_id=workspace_id)

        return was_new, event.event_id

    # ── Derived-rollup + correlation helpers (Phase 2) ──────────────────────
    #
    # Both best-effort: a failure here is logged and swallowed, never raised
    # -- the rf_events row (AC-1) has already been durably persisted by the
    # time either of these runs, and both are safely re-derivable later via
    # ResearchRunsRepository.backfill_from_rf_events (T2-001).

    async def _derive_research_run(
        self,
        row: dict[str, Any],
        *,
        project_id: str,
        workspace_id: str,
    ) -> None:
        if self._research_runs_repo is None:
            return
        try:
            canonical_run_id = await retry_on_locked(
                lambda: self._research_runs_repo.upsert_from_event(
                    row, workspace_id=workspace_id, project_id=project_id
                ),
                repo="research_runs",
            )
        except Exception as exc:
            logger.warning(
                "rf_events ingest: research_runs upsert failed for project_id=%s run_id=%s: %s",
                project_id,
                row.get("run_id"),
                exc,
            )
            return

        if not canonical_run_id:
            # event carried no run_id -- nothing to roll up (build_research_run_delta
            # contract: None means "no run identity", not an error).
            return

        await self._correlate_research_run(canonical_run_id, workspace_id=workspace_id)

    async def _correlate_research_run(self, run_id: str, *, workspace_id: str) -> None:
        if self._entity_link_repo is None:
            return
        try:
            run = await self._research_runs_repo.get_by_run_id(run_id)
            if run is None:
                return
            await self._entity_link_repo.correlate_research_run(run, workspace_id=workspace_id)
        except Exception as exc:
            logger.warning(
                "rf_events ingest: run<->session correlation failed for run_id=%s: %s",
                run_id,
                exc,
            )

    # ── Cursor bookkeeping helpers (T1-004) ─────────────────────────────────────
    #
    # Each helper is a no-op when no cursor_repo was injected, and swallows any
    # exception after logging — watermark bookkeeping is secondary telemetry
    # and must never fail the primary rf_events persistence path.

    async def _cursor_get_or_create(self, *, project_id: str, workspace_id: str) -> None:
        if self._cursor_repo is None:
            return
        try:
            await retry_on_locked(
                lambda: self._cursor_repo.get_or_create(
                    source_id=SOURCE_ID,
                    project_id=project_id,
                    workspace_id=workspace_id,
                ),
                repo="ingest_cursors",
            )
        except Exception as exc:
            logger.warning(
                "rf_events ingest: cursor get_or_create failed for project_id=%s: %s",
                project_id,
                exc,
            )

    async def _cursor_advance(
        self,
        *,
        project_id: str,
        workspace_id: str,
        cursor_value: str,
        occurred_at: str,
    ) -> None:
        if self._cursor_repo is None:
            return
        try:
            await retry_on_locked(
                lambda: self._cursor_repo.advance(
                    source_id=SOURCE_ID,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    cursor_value=cursor_value,
                    occurred_at=occurred_at,
                ),
                repo="ingest_cursors",
            )
        except Exception as exc:
            logger.warning(
                "rf_events ingest: cursor advance failed for project_id=%s event_id=%s: %s",
                project_id,
                cursor_value,
                exc,
            )

    async def _cursor_record_error(
        self,
        *,
        project_id: str,
        workspace_id: str,
        error_message: str,
    ) -> None:
        if self._cursor_repo is None:
            return
        try:
            await retry_on_locked(
                lambda: self._cursor_repo.record_error(
                    source_id=SOURCE_ID,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    error_message=error_message,
                ),
                repo="ingest_cursors",
            )
        except Exception as exc:
            logger.warning(
                "rf_events ingest: cursor record_error failed for project_id=%s: %s",
                project_id,
                exc,
            )


__all__ = [
    "RfEventsIngestService",
    "RfEventProcessingError",
    "MAX_EVENTS_PER_BATCH",
    "SOURCE_ID",
]
