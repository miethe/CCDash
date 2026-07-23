"""Worker job wrapper: the default-off AAR-review autonomous sweep (Phase 6, T6-006).

``AARReviewSweepJob`` is the background counterpart of the on-demand
``AARReviewQueryService.get_review`` read path (``backend/application/
services/agent_queries/aar_review.py``) and the one-time
``backfill_aar_reviews_for_project`` script
(``backend/scripts/aar_reviews_backfill.py``). Each periodic tick:

  1. Discovers candidate AAR documents already synced into the ``documents``
     table (the same filename heuristic the backfill script uses --
     duplicated here rather than imported, matching this feature's existing
     "no production module imports from ``backend.scripts.*``" convention;
     see ``aar_review.py``'s own duplicated-not-shared ``_aar_reviews_repository``
     helper for the precedent).
  2. Scopes those candidates to only NEW/CHANGED documents since this
     project's last sweep tick (``select_incremental_documents`` --
     mirrors the ``CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`` "scoped, not
     full-scan" pattern).
  3. For each scoped candidate, calls the EXISTING, already-shipped
     deterministic triage service (``AARReviewQueryService.get_review``) to
     compute its ``(correlation, flags, verdict)`` -- zero re-derivation.
  4. Applies Guard 1 (provenance self-exclusion,
     ``aar_review_sweep_guards.filter_self_referential_session_ids``) to the
     computed session set BEFORE persisting -- a session whose OWN
     ``skill_name``/``workflow_id`` columns mark it as aar-review-originated
     is dropped from the triage INPUT unconditionally. FAIL CLOSED (karen P6
     hardening): a session whose provenance row could not be fetched at all
     (missing / lookup failure) is ALSO excluded -- undeterminable provenance
     is treated as a potential self-reference, never allowed through.
  5. Applies Guard 2 (idempotent dedup ledger,
     ``aar_review_sweep_guards.filter_untriaged_pairs``) against a ledger
     read FRESH from the ``aar_reviews`` repository at the top of every tick
     -- an already-triaged ``(aar_document_id, session_id)`` pair is never
     re-persisted, including across a worker restart (the ledger is never
     held only in process memory).
  6. Upserts every surviving row via the existing
     ``backend.db.repositories.aar_reviews`` repository (ADR-007
     ``retry_on_locked``-wrapped writes, unchanged).
  7. On any row written, invalidates the ``aar_review_list`` v1-endpoint
     cache for the project via ``aclear_project_cache`` -- the P4/karen
     carry-forward documented in
     ``backend/routers/_client_v1_aar_review.py``'s module docstring
     ("Caching note (P3 carry-forward)").

HARD INVARIANTS (unchanged from the rest of this feature):
  #1 zero LLM/model calls anywhere on this module's compute path -- every
     value persisted was already computed by ``aar_review.py``; this module
     performs no derivation of its own.
  #2 CCDash emits only -- this job PERSISTS ``aar_reviews`` rows and may
     emit the existing log-only ``log_aar_review_candidate`` event (already
     called internally by ``get_review``); it NEVER dispatches ARC/swarm and
     NEVER mutates SkillMeat/skills/agents. Escalation/handoff is explicitly
     OUT of this job's scope (a follow-up phase).
  #4 redaction-passed ``session_detail`` only -- this job never reads a raw
     session JSONL; every session-derived string on a persisted row was
     already produced by ``get_review`` via the redaction-applied
     ``session_detail.get_session_detail`` bundle.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite

from backend import config
from backend.db.repositories.aar_reviews import (
    PostgresAarReviewsRepository,
    SqliteAarReviewsRepository,
    build_aar_review_row,
)

from .aar_review_sweep_guards import (
    build_triaged_pair_ledger,
    filter_self_referential_session_ids,
    filter_untriaged_pairs,
    select_incremental_documents,
)

logger = logging.getLogger("ccdash.jobs.aar_review_sweep")

__all__ = ["AARReviewSweepJob", "AARReviewSweepRunResult", "looks_like_aar_document"]


# ── AAR-document discovery heuristic ─────────────────────────────────────────
#
# Duplicated (rather than imported) from
# ``backend.scripts.aar_reviews_backfill.looks_like_aar_document`` -- this
# feature's established convention is that production/runtime modules never
# depend on a top-level ``backend.scripts.*`` module (see ``aar_review.py``'s
# own ``_aar_reviews_repository`` docstring for the precedent). Deterministic
# string matching only -- never a semantic/model judgment (Hard Invariant #1).

_AAR_STEM_INFIX = "-aar-"
_AAR_STEM_SUFFIX = "-aar"
_AAR_STEM_PREFIX = "aar-"
_AAR_STEM_EXACT = "aar"


def looks_like_aar_document(doc_row: dict[str, Any]) -> bool:
    """Return True when *doc_row* (a ``documents`` table row) looks like an AAR.

    Byte-for-byte identical logic to
    ``backend.scripts.aar_reviews_backfill.looks_like_aar_document``.
    """
    stem = str(doc_row.get("file_stem") or "").strip().lower()
    if not stem:
        raw_path = str(doc_row.get("canonical_path") or doc_row.get("file_path") or "")
        stem = Path(raw_path).stem.lower()
    if not stem:
        return False
    return (
        stem == _AAR_STEM_EXACT
        or _AAR_STEM_INFIX in stem
        or stem.endswith(_AAR_STEM_SUFFIX)
        or stem.startswith(_AAR_STEM_PREFIX)
    )


def _aar_reviews_repo(db: Any) -> "SqliteAarReviewsRepository | PostgresAarReviewsRepository":
    """Dispatch to the concrete ``aar_reviews`` repository for *db*.

    Duplicated from ``aar_review.py``'s ``_aar_reviews_repository`` (same
    reasoning: no cross-module private-helper sharing).
    """
    if isinstance(db, aiosqlite.Connection):
        return SqliteAarReviewsRepository(db)
    return PostgresAarReviewsRepository(db)


@dataclass(slots=True)
class AARReviewSweepRunResult:
    success: bool
    outcome: str
    documents_scanned: int = 0
    documents_processed: int = 0
    pairs_written: int = 0
    pairs_already_triaged: int = 0
    sessions_excluded_self_referential: int = 0
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class AARReviewSweepJob:
    """Adapt the AAR-review autonomous sweep to the runtime job interface.

    Mirrors ``ArtifactRollupExportJob``/``TelemetryExporterJob``'s shape
    (``execute(trigger=...) -> dataclass result``) exactly, so
    ``backend/runtime/container.py`` and ``backend/adapters/jobs/runtime.py``
    can register/schedule it via the identical profile-gated pattern.
    """

    def __init__(self, *, ports: Any, project: Any | None, coalescing_enabled: bool = True) -> None:
        self.ports = ports
        self.project = project
        self.coalescing_enabled = coalescing_enabled
        # (project_id, trigger) coalescing guard -- mirrors sync_engine.py's
        # ``_sync_in_flight`` set exactly (same key shape, same
        # check-then-add-is-atomic-in-asyncio reasoning). Duplicated rather
        # than shared because the sync engine's guard is private to
        # ``SyncEngine.sync_project`` and this job has its own independent
        # dispatch path (its own periodic loop task).
        self._in_flight: set[tuple[str, str]] = set()
        # Per-project incremental watermark (T6-006): the newest observed
        # document ``updated_at``/``created_at`` stamp from the previous
        # tick.  In-process only -- losing it across a worker restart just
        # means the NEXT tick re-scans every AAR document for that project
        # (a superset, never a missed one); Guard 2's DB-backed dedup ledger
        # is what actually prevents duplicate WRITES across that boundary,
        # not this watermark.
        self._watermarks: dict[str, str] = {}

    async def execute(self, *, trigger: str = "scheduled") -> AARReviewSweepRunResult:
        if not bool(getattr(config, "CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED", False)):
            return AARReviewSweepRunResult(success=True, outcome="disabled")
        project = self.project
        if project is None:
            return AARReviewSweepRunResult(success=True, outcome="no_project")
        project_id = str(getattr(project, "id", "") or "")
        if not project_id:
            return AARReviewSweepRunResult(success=True, outcome="no_project")

        # ── (project_id, trigger) coalescing guard ──────────────────────────
        # Reuses the exact semantics of sync_engine.py's Phase 7 coalescing
        # guard (CCDASH_SYNC_COALESCING_ENABLED): the set-membership check and
        # the add are both synchronous (no await between them), so the
        # check-then-add is atomic in asyncio's cooperative single-threaded
        # event loop. A second concurrent dispatch for the same key coalesces
        # rather than running a duplicate sweep.
        coalescing_enabled = self.coalescing_enabled and bool(
            getattr(config, "SYNC_COALESCING_ENABLED", True)
        )
        coal_key = (project_id, trigger or "scheduled")
        if coalescing_enabled:
            if coal_key in self._in_flight:
                logger.info(
                    "aar_review_sweep coalesced key=%s — in-flight sweep detected; "
                    "returning deduplicated result (no silent drop)",
                    coal_key,
                )
                return AARReviewSweepRunResult(success=True, outcome="coalesced")
            self._in_flight.add(coal_key)
        try:
            return await self._execute_inner(project, project_id)
        finally:
            if coalescing_enabled:
                self._in_flight.discard(coal_key)

    async def _execute_inner(self, project: Any, project_id: str) -> AARReviewSweepRunResult:
        # Local imports: backend.application.services.{common,agent_queries}
        # transitively import backend.runtime_ports, which imports
        # backend.adapters.jobs (for InProcessJobScheduler) -- importing them
        # at THIS module's top level would create an import cycle through
        # backend/adapters/jobs/runtime.py's eager
        # `from backend.adapters.jobs.aar_review_sweep_job import AARReviewSweepJob`.
        # Deferring to call time (mirrors the existing local-import pattern in
        # backend/runtime/container.py's _start_cache_warming_task and
        # backend/adapters/jobs/runtime.py's _maybe_start_drain_loop) breaks
        # the cycle with zero behavior change.
        from backend.application.services.agent_queries import aclear_project_cache  # noqa: PLC0415
        from backend.application.services.agent_queries.aar_review import AARReviewQueryService  # noqa: PLC0415
        from backend.application.services.common import resolve_application_request  # noqa: PLC0415

        try:
            app_request = await resolve_application_request(
                None, self.ports, self.ports.storage.db, requested_project_id=project_id,
            )
        except Exception as exc:
            logger.exception(
                "aar_review_sweep: failed to resolve application request for project_id=%s", project_id
            )
            return AARReviewSweepRunResult(success=False, outcome="error", error=str(exc))
        context, ports = app_request.context, app_request.ports

        documents_repo = ports.storage.documents()
        try:
            doc_rows = await documents_repo.list_all(project_id)
        except Exception as exc:
            logger.exception(
                "aar_review_sweep: documents().list_all failed for project_id=%s", project_id
            )
            return AARReviewSweepRunResult(success=False, outcome="error", error=str(exc))

        candidates = [row for row in doc_rows if looks_like_aar_document(row)]

        # ── T6-006 INCREMENTAL scoping: only new/changed AAR docs this tick ──
        watermark = self._watermarks.get(project_id, "")
        incremental_candidates = select_incremental_documents(candidates, watermark)

        reviews_repo = _aar_reviews_repo(ports.storage.db)
        # ── Guard 2 ledger: read FRESH from the DB every tick (never held
        # only in process memory) -- this is what makes the dedup guard
        # survive a worker restart, not the watermark above.
        try:
            ledger_rows = await reviews_repo.list_document_session_pairs(project_id)
        except Exception:
            logger.exception(
                "aar_review_sweep: dedup-ledger read failed for project_id=%s — "
                "treating as an empty ledger this tick (never blocks the sweep)",
                project_id,
            )
            ledger_rows = []
        ledger = build_triaged_pair_ledger(ledger_rows)

        review_service = AARReviewQueryService()
        sessions_repo = ports.storage.sessions()

        documents_processed = 0
        pairs_written = 0
        pairs_already_triaged = 0
        sessions_excluded = 0
        newest_stamp = watermark

        for doc_row in incremental_candidates:
            document_id = str(doc_row.get("id") or "")
            if not document_id:
                continue
            stamp = str(doc_row.get("updated_at") or doc_row.get("created_at") or "")
            if stamp > newest_stamp:
                newest_stamp = stamp

            try:
                dto = await review_service.get_review(context, ports, document_id, bypass_cache=True)
            except Exception:
                logger.exception("aar_review_sweep: get_review failed for document_id=%s", document_id)
                continue
            documents_processed += 1
            if dto.status != "ok" or not dto.correlation.session_ids:
                continue

            # ── Guard 1: provenance self-exclusion ───────────────────────────
            session_rows_by_id: dict[str, dict[str, Any]] = {}
            for session_id in dto.correlation.session_ids:
                try:
                    row = await sessions_repo.get_by_id(
                        session_id, project_id, workspace_id="default-local"  # TODO(workspace-routing)
                    )
                except Exception:
                    row = None
                if row is not None:
                    session_rows_by_id[session_id] = row

            allowed_session_ids, excluded_session_ids = filter_self_referential_session_ids(
                dto.correlation.session_ids, session_rows_by_id,
            )
            if excluded_session_ids:
                sessions_excluded += len(excluded_session_ids)
                logger.info(
                    "aar_review_sweep: Guard 1 excluded %d self-referential session(s) "
                    "for document_id=%s: %s",
                    len(excluded_session_ids),
                    document_id,
                    excluded_session_ids,
                )

            # ── Guard 2: idempotent dedup ledger ──────────────────────────────
            candidate_pairs = [(document_id, session_id) for session_id in allowed_session_ids]
            new_pairs, already_triaged_pairs = filter_untriaged_pairs(candidate_pairs, ledger)
            pairs_already_triaged += len(already_triaged_pairs)

            if not new_pairs:
                continue

            aar_document_path = str(doc_row.get("canonical_path") or doc_row.get("file_path") or "")
            for _doc_id, session_id in new_pairs:
                row = build_aar_review_row(
                    dto, session_id, project_id=project_id, aar_document_path=aar_document_path,
                )
                try:
                    await reviews_repo.upsert(row)
                except Exception:
                    logger.exception(
                        "aar_review_sweep: upsert failed for (document_id=%s, session_id=%s)",
                        document_id,
                        session_id,
                    )
                    continue
                # Keep the in-memory ledger current for the rest of THIS
                # tick (e.g. the same session correlating to a second
                # document later in the loop) -- the next tick re-reads the
                # ledger from the DB regardless, so this is an optimisation,
                # not a correctness dependency.
                ledger.add((document_id, session_id))
                pairs_written += 1

        # ── Cache-invalidation hook (P4/karen carry-forward) ─────────────────
        # aar_review_list's memoized_query fingerprint does not track
        # aar_reviews (see _client_v1_aar_review.py's module docstring) --
        # explicitly bust the project's cache on any write so the v1 endpoint
        # never serves a stale verdict for up to the TTL after a live sweep.
        if pairs_written > 0:
            try:
                await aclear_project_cache(project_id)
            except Exception:
                logger.exception(
                    "aar_review_sweep: cache invalidation failed for project_id=%s", project_id
                )

        self._watermarks[project_id] = newest_stamp

        return AARReviewSweepRunResult(
            success=True,
            outcome="success",
            documents_scanned=len(candidates),
            documents_processed=documents_processed,
            pairs_written=pairs_written,
            pairs_already_triaged=pairs_already_triaged,
            sessions_excluded_self_referential=sessions_excluded,
            details={
                "projectId": project_id,
                "incrementalCandidateCount": len(incremental_candidates),
                "watermark": newest_stamp,
            },
        )
