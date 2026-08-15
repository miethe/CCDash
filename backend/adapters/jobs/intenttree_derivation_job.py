"""Worker job wrapper: default-off IntentTree reopened + self-caught derivation sweep.

are-we-winning-dashboard-v1 M2 scheduler wiring: M2 part B
(``backend/application/services/ingest/intenttree_reopened_derivation.py`` /
``intenttree_self_caught_derivation.py``) shipped fully implemented and
tested but was never registered with the periodic scheduler -- this wrapper
is that registration's job-object half, mirroring
``IntentTreeEventsIngestJob``'s shape exactly.

Ordering vs. ingestion
-----------------------
Both derivations read the ``intent_tree_events`` cache that
``IntentTreeEventsIngestJob`` (M1) populates. This job runs on its OWN
interval (``CCDASH_INTENTTREE_DERIVE_INTERVAL_SECONDS``), not sequenced
inside the ingestion job's tick -- deliberately, because both derivation
services already tolerate an empty/partial cache as a normal, non-error,
zero-work pass: their candidate sets are computed live each call via
``distinct_node_ids_for_event_type``, and an empty candidate set simply
short-circuits their per-node loop and returns ``ok=True`` with zero
processed (see both services' ``derive_all()``). A derivation tick that
lands before the first ingestion sweep, or between two ingestion ticks, is
therefore harmless -- it derives whatever candidate set exists at that
moment and the next tick picks up anything new. This keeps the two jobs
decoupled (a stalled ingestion sweep never blocks or delays derivation
ticks, and vice versa) at the cost of no *hard* ordering guarantee -- judged
acceptable because the services' own fail-soft/idempotent contract already
absorbs it.

Each tick calls both services' ``derive_all()`` in sequence (reopened, then
self-caught -- an arbitrary but fixed order; the two are independent and
never share a fail-soft short-circuit). Each service is itself fail-soft
per node (see their own docstrings); this wrapper never raises out of
``execute()`` either -- a failed sweep is reported via the result's
``ok``/``error`` fields, mirroring ``IntentTreeEventsIngestJob``'s contract.

``backend/adapters/jobs/runtime.py`` and ``backend/runtime/container.py``
registration mirrors ``IntentTreeEventsIngestJob``'s construction/gating
pattern exactly (profile-gated construction + a defense-in-depth flag
re-check inside ``execute()``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend import config

# Deliberately NOT a module-level import -- same circular-import chain
# IntentTreeEventsIngestJob avoids (backend.application.services.ingest's
# package __init__ eagerly imports rf_events_ingest -> agent_queries ->
# backend.runtime_ports -> backend.adapters.jobs, this package). Type-only
# import guarded by TYPE_CHECKING costs nothing at runtime.
if TYPE_CHECKING:
    from backend.application.services.ingest.intenttree_reopened_derivation import (
        IntentTreeReopenedDerivationService,
        ReopenedDerivationResult,
    )
    from backend.application.services.ingest.intenttree_self_caught_derivation import (
        IntentTreeSelfCaughtDerivationService,
        SelfCaughtDerivationResult,
    )

logger = logging.getLogger("ccdash.jobs.intenttree_derivation")


@dataclass(slots=True)
class IntentTreeDerivationJobResult:
    outcome: str  # "success" | "partial_failure" | "disabled"
    reopens_written: int = 0
    self_caught_processed: int = 0
    error: str | None = None


class IntentTreeDerivationJob:
    """Sweeps both reopened + self-caught derivations on each tick."""

    def __init__(
        self,
        reopened_service: IntentTreeReopenedDerivationService,
        self_caught_service: IntentTreeSelfCaughtDerivationService,
    ) -> None:
        self._reopened_service = reopened_service
        self._self_caught_service = self_caught_service

    async def execute(self, *, trigger: str = "scheduled") -> IntentTreeDerivationJobResult:
        # Defense in depth: re-check the flag here too, in addition to
        # whatever construction-time gate container.py applies (mirrors
        # IntentTreeEventsIngestJob.execute()'s own re-check).
        if not bool(getattr(config, "CCDASH_ARE_WE_WINNING_ENABLED", False)):
            return IntentTreeDerivationJobResult(outcome="disabled")

        reopened_result: ReopenedDerivationResult = await self._reopened_service.derive_all()
        if not reopened_result.ok:
            logger.warning(
                "intenttree derivation job (trigger=%s): reopened derivation failed after "
                "%d/%d candidate node(s) processed (reopens_written=%d so far, not rolled "
                "back): %s",
                trigger,
                reopened_result.nodes_processed,
                len(reopened_result.candidate_node_ids),
                reopened_result.reopens_written,
                reopened_result.error,
            )

        self_caught_result: SelfCaughtDerivationResult = await self._self_caught_service.derive_all()
        if not self_caught_result.ok:
            logger.warning(
                "intenttree derivation job (trigger=%s): self-caught derivation failed after "
                "%d/%d candidate node(s) processed (not rolled back): %s",
                trigger,
                self_caught_result.nodes_processed,
                len(self_caught_result.candidate_node_ids),
                self_caught_result.error,
            )

        if reopened_result.ok and self_caught_result.ok:
            return IntentTreeDerivationJobResult(
                outcome="success",
                reopens_written=reopened_result.reopens_written,
                self_caught_processed=self_caught_result.nodes_processed,
            )

        first_error = reopened_result.error if not reopened_result.ok else self_caught_result.error
        return IntentTreeDerivationJobResult(
            outcome="partial_failure",
            reopens_written=reopened_result.reopens_written,
            self_caught_processed=self_caught_result.nodes_processed,
            error=first_error,
        )


__all__ = ["IntentTreeDerivationJob", "IntentTreeDerivationJobResult"]
