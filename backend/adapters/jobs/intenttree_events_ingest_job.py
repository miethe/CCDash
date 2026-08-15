"""Worker job wrapper: default-off IntentTree lifecycle-event ingestion sweep.

are-we-winning-dashboard-v1 M1 (OQ-3 decision): a dedicated interval-based job,
deliberately NOT hung off the existing filesystem watcher/sync cadence, since
IntentTree's event log is an unrelated HTTP source with its own staleness
tolerance.

Each tick calls ``IntentTreeEventsIngestService.ingest_all()``
(``backend/application/services/ingest/intenttree_events_ingest.py``), which
is itself fail-soft per event type -- this wrapper never raises out of
``execute()``; a failed sweep is reported via the result's ``ok``/``error``
fields for the caller's own observability bookkeeping, mirroring
``RoutingRollupSweepJob``/``AARReviewSweepJob``'s shape.

``backend/adapters/jobs/runtime.py`` and ``backend/runtime/container.py``
registration mirrors those jobs' construction/gating pattern exactly (profile-
gated construction + a defense-in-depth flag re-check inside ``execute()``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend import config

# Deliberately NOT a module-level import: backend.application.services.ingest's
# package __init__ eagerly imports rf_events_ingest -> agent_queries ->
# backend.runtime_ports -> backend.adapters.jobs (this package), so importing
# it at module scope here recreates the exact circular-import chain the other
# job wrappers in this package (routing_rollup_sweep_job.py,
# aar_review_sweep_job.py) avoid by never importing from
# backend.application.services.* at module level. Type-only import guarded by
# TYPE_CHECKING costs nothing at runtime.
if TYPE_CHECKING:
    from backend.application.services.ingest.intenttree_events_ingest import (
        IntentTreeEventsIngestService,
        IntentTreeIngestResult,
    )

logger = logging.getLogger("ccdash.jobs.intenttree_events_ingest")


@dataclass(slots=True)
class IntentTreeEventsIngestJobResult:
    outcome: str  # "success" | "partial_failure" | "disabled"
    rows_written: int = 0
    rows_seen: int = 0
    error: str | None = None


class IntentTreeEventsIngestJob:
    """Sweeps IntentTree's event log into ``intent_tree_events`` on each tick."""

    def __init__(self, service: IntentTreeEventsIngestService) -> None:
        self._service = service

    async def execute(self, *, trigger: str = "scheduled") -> IntentTreeEventsIngestJobResult:
        # Defense in depth: re-check the flag here too, in addition to
        # whatever construction-time gate container.py applies (mirrors
        # RoutingRollupSweepJob.execute()'s own re-check).
        if not bool(getattr(config, "CCDASH_ARE_WE_WINNING_ENABLED", False)):
            return IntentTreeEventsIngestJobResult(outcome="disabled")

        result: IntentTreeIngestResult = await self._service.ingest_all()
        for per_type in result.per_event_type:
            if not per_type.ok:
                logger.warning(
                    "intenttree events ingest job (trigger=%s): event_type=%s "
                    "sweep failed after %d page(s): %s",
                    trigger,
                    per_type.event_type,
                    per_type.pages_fetched,
                    per_type.error,
                )

        if result.ok:
            return IntentTreeEventsIngestJobResult(
                outcome="success",
                rows_written=result.rows_written,
                rows_seen=result.rows_seen,
            )

        first_error = next((r.error for r in result.per_event_type if not r.ok), None)
        return IntentTreeEventsIngestJobResult(
            outcome="partial_failure",
            rows_written=result.rows_written,
            rows_seen=result.rows_seen,
            error=first_error,
        )


__all__ = ["IntentTreeEventsIngestJob", "IntentTreeEventsIngestJobResult"]
