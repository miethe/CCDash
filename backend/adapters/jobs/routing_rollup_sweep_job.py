"""Worker job wrapper: the default-off Proof -> Routing Feedback Loop sweep
(``proof-to-routing-loop-v1`` Phase 4, T4-001).

``RoutingRollupSweepJob`` is a near-exact structural clone of the shipped
``AARReviewSweepJob`` (``backend/adapters/jobs/aar_review_sweep_job.py``) --
same multi-project fan-out, same in-process watermark bookkeeping, same
``(project_id, trigger)`` coalescing guard, same double-gated flag check, and
the same per-project try/except-and-continue error isolation. It is the
background-worker persistence half of the on-demand routing-feedback rollup
compute service (``backend/application/services/agent_queries/routing_rollup.py``
``RoutingRollupQueryService``, Phase 3).

Each periodic tick sweeps EVERY registered project
(``_resolve_projects_to_sweep`` -- ``ports.workspace_registry.list_projects()``,
ADR-006; the same registry-driven enumeration the watcher fan-out, the
AAR-review sweep, and the periodic analytics-snapshot/cache-warming tasks
already use), never just the single project the worker's sync engine happens
to be bound to. For each project:

  1. Calls Phase 3's ``RoutingRollupQueryService`` end to end
     (``fetch_raw_rows`` -> ``apply_mapping`` -> ``apply_provider`` ->
     ``compute_metrics``) to compute the full
     ``(project_id, source_skill_name, model)``-grain rollup for that
     project's current rolling window -- ZERO aggregation, mapping
     application, provider derivation, or metric-payload arithmetic happens
     in this module; every value persisted below was already computed by
     Phase 3.
  2. Pairs each computed ``RoutingRollupKeyDTO`` with the ``ProviderRollupRow``
     that produced it (by list index -- see ``_build_routing_rollup_row``'s
     docstring for why this is safe) to recover ``project_id``, which
     ``RoutingRollupKeyDTO`` deliberately does not carry (its row grain is
     ``(source_skill_name, model)`` only).
  3. Upserts every resulting row via the existing
     ``backend.db.repositories.routing_rollup`` repository (ADR-007
     ``retry_on_locked``-wrapped writes, unchanged) -- re-upserting the same
     ``(project_id, source_skill_name, model)`` key updates the row in place;
     it never grows the table on a repeat tick over an unchanged window
     (idempotent by construction, delegated entirely to the repository's own
     ``ON CONFLICT`` clause).

Unlike ``AARReviewSweepJob``, this job's "incremental" watermark
(``self._watermarks: dict[str, str]``) is purely observational/structural
parity with the AAR-review anchor's shape -- it records the newest
``window_end`` seen per project for status/debugging visibility, but it is
NEVER read back to scope a query. Phase 3's ``fetch_raw_rows`` always
aggregates the full rolling window (``config.CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS``)
fresh on every call; there is no "only new/changed rows since last tick"
concept here the way there is for AAR-review's per-document triage (a rolling
aggregate has no notion of "already seen", only "current value of the
window"). Losing the watermark across a worker restart is therefore
completely inert -- the repository's idempotent upsert is what actually
makes repeat sweeps safe, not this dict.

Cache invalidation on write (T4-003): on any project's tick that actually
wrote at least one row (``rows_written > 0``), ``_execute_inner`` busts that
project's routing-rollup read cache via ``aclear_project_cache(project_id)``
(a local, call-time import alongside this module's other deferred imports,
for the same import-cycle reason) -- mirrors
``aar_review_sweep_job.py``'s own ``aar_review_list`` cache-invalidation
hook exactly. A no-op tick (``rows_written == 0``, e.g. a project with no
in-window sessions, or the whole sweep body skipped by the disabled-flag
short-circuit below) never fires the invalidation -- there is nothing stale
to clear. ``backend/tests/test_routing_rollup_sweep_job.py`` is this task's
accompanying test battery (multi-project sweep, flag-off no-op, flag-flip
reversibility -- AC-7).

``backend/adapters/jobs/runtime.py`` and ``backend/runtime/container.py``
registration is T4-002.

HARD INVARIANTS (unchanged from the rest of this feature):
  #1 zero LLM/model calls anywhere on this module's compute path -- every
     value persisted was already computed by ``routing_rollup.py``; this
     module performs no derivation of its own (mirrors that module's own
     module-docstring invariant statement verbatim).
  D7 (reversibility): ``CCDASH_ROUTING_FEEDBACK_ENABLED`` is re-checked at
     the top of ``execute()`` (defense in depth, in addition to whatever
     construction-time flag gate Phase 4's T4-002 adds in ``container.py``)
     -- when ``False``, the sweep body is skipped entirely: zero projects are
     resolved, zero calls are made into ``RoutingRollupQueryService``, and
     zero writes occur.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import aiosqlite

from backend import config
from backend.db.repositories.routing_rollup import (
    PostgresRoutingRollupRepository,
    SqliteRoutingRollupRepository,
)

logger = logging.getLogger("ccdash.jobs.routing_rollup_sweep")

__all__ = [
    "RoutingRollupSweepJob",
    "RoutingRollupSweepRunResult",
]


def _routing_rollup_repo(
    db: Any,
) -> "SqliteRoutingRollupRepository | PostgresRoutingRollupRepository":
    """Dispatch to the concrete ``routing_rollup`` repository for *db*.

    Mirrors ``aar_review_sweep_job.py``'s own ``_aar_reviews_repo`` dispatch
    helper exactly (same isinstance-on-``aiosqlite.Connection`` branch).
    """
    if isinstance(db, aiosqlite.Connection):
        return SqliteRoutingRollupRepository(db)
    return PostgresRoutingRollupRepository(db)


def _build_routing_rollup_row(provider_row: Any, key_dto: Any) -> dict[str, Any]:
    """Zip one matched (``ProviderRollupRow``, ``RoutingRollupKeyDTO``) pair
    into a ``ROUTING_ROLLUP_COLUMNS``-shaped persistable row dict.

    *provider_row* and *key_dto* MUST be the pair produced at the SAME list
    index by the SAME ``RoutingRollupQueryService.compute_metrics()`` call --
    that method's own docstring guarantees strict index-for-index 1:1
    correspondence with its input list ("every row in *rows* produces
    exactly one output DTO"; never a filtering or reordering transform),
    which is what makes pairing by index safe here. ``project_id`` is taken
    from *provider_row* because ``RoutingRollupKeyDTO`` deliberately omits it
    (its row grain is ``(source_skill_name, model)`` only -- see that
    class's own docstring); every other field is copied verbatim from
    *key_dto*, Phase 3's terminal, already-computed value -- zero derivation
    happens here.

    ``eligible_for_adjustment`` is cast ``bool`` -> ``int`` because both
    SQLite and PostgreSQL DDL declare the column ``INTEGER`` -- deliberately
    NOT a native boolean type (see
    ``backend/tests/test_routing_rollup_repo.py``'s documented column-parity
    rationale) -- so the value written must already be an int, not a bool,
    to match the fixtures that test module exercises against the same
    columns.
    """
    return {
        "project_id": provider_row.project_id,
        "source_skill_name": key_dto.source_skill_name,
        "model": key_dto.model,
        "window_start": key_dto.window_start,
        "window_end": key_dto.window_end,
        "task_class": key_dto.task_class,
        "provider": key_dto.provider,
        "sample_count": key_dto.sample_count,
        "success_rate": key_dto.success_rate,
        "cost_index": key_dto.cost_index,
        "regression_rate": key_dto.regression_rate,
        # DI-4c: copied verbatim from the terminal DTO like every other metric
        # field -- the unambiguous-or-null resolution and the authoritative
        # fraction are both already computed in compute_metrics(). Zero
        # derivation here, same as cost_index.
        "effort_tier": key_dto.effort_tier,
        "effort_tier_source": key_dto.effort_tier_source,
        "authoritative_effort_fraction": key_dto.authoritative_effort_fraction,
        "confidence": key_dto.confidence,
        "eligible_for_adjustment": int(bool(key_dto.eligible_for_adjustment)),
        "freshness_ts": key_dto.freshness_ts,
        "contract_version": key_dto.contract_version,
        "taxonomy_version": key_dto.taxonomy_version,
        "mapping_version": key_dto.mapping_version,
    }


@dataclass(slots=True)
class RoutingRollupSweepRunResult:
    """One tick's outcome -- mirrors ``AARReviewSweepRunResult``'s shape
    (``success``, ``outcome``, per-tick counters, ``error``, ``details``),
    adapted to this feature's own counters (``keys_computed``/
    ``rows_written`` in place of AAR-review's document/pair/session
    counters, which have no analogue here).
    """

    success: bool
    outcome: str
    keys_computed: int = 0
    rows_written: int = 0
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class RoutingRollupSweepJob:
    """Adapt the Proof -> Routing Feedback Loop rollup sweep to the runtime
    job interface.

    Mirrors ``AARReviewSweepJob``/``ArtifactRollupExportJob``/
    ``TelemetryExporterJob``'s shape (``execute(trigger=...) -> dataclass
    result``) exactly, so ``backend/runtime/container.py`` and
    ``backend/adapters/jobs/runtime.py`` can register/schedule it via the
    identical profile-gated pattern (Phase 4's T4-002, not this task).
    """

    def __init__(self, *, ports: Any, project: Any | None, coalescing_enabled: bool = True) -> None:
        self.ports = ports
        self.project = project
        self.coalescing_enabled = coalescing_enabled
        # (project_id, trigger) coalescing guard -- byte-for-byte the same
        # key shape and check-then-add-is-atomic-in-asyncio reasoning as
        # ``AARReviewSweepJob._in_flight`` / ``sync_engine.py``'s
        # ``_sync_in_flight``. Duplicated rather than shared because this
        # job has its own independent dispatch path (its own periodic loop
        # task, wired separately in Phase 4's T4-002).
        self._in_flight: set[tuple[str, str]] = set()
        # Per-project watermark: OBSERVATIONAL ONLY -- see module docstring.
        # Never read back to scope a query; Phase 3's rolling-window
        # aggregation and this repository's idempotent upsert are what
        # actually make repeat sweeps safe, not this dict.
        self._watermarks: dict[str, str] = {}

    async def execute(self, *, trigger: str = "scheduled") -> RoutingRollupSweepRunResult:
        if not bool(getattr(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", False)):
            return RoutingRollupSweepRunResult(success=True, outcome="disabled")

        projects = self._resolve_projects_to_sweep()
        if not projects:
            return RoutingRollupSweepRunResult(success=True, outcome="no_project")

        # ── (project_id, trigger) coalescing guard ──────────────────────────
        # Reuses the exact semantics of sync_engine.py's Phase 7 coalescing
        # guard (CCDASH_SYNC_COALESCING_ENABLED) and AARReviewSweepJob's own
        # copy of it: the set-membership check and the add are both
        # synchronous (no await between them), so the check-then-add is
        # atomic in asyncio's cooperative single-threaded event loop. A
        # second concurrent dispatch for the same (project_id, trigger) key
        # coalesces rather than running a duplicate sweep for THAT project --
        # keyed per-project so one project's in-flight sweep never blocks
        # another project's tick.
        coalescing_enabled = self.coalescing_enabled and bool(
            getattr(config, "SYNC_COALESCING_ENABLED", True)
        )

        project_results: dict[str, RoutingRollupSweepRunResult] = {}
        for project in projects:
            project_id = str(getattr(project, "id", "") or "")
            if not project_id:
                continue

            coal_key = (project_id, trigger or "scheduled")
            if coalescing_enabled:
                if coal_key in self._in_flight:
                    logger.info(
                        "routing_rollup_sweep coalesced key=%s — in-flight sweep detected; "
                        "returning deduplicated result (no silent drop)",
                        coal_key,
                    )
                    project_results[project_id] = RoutingRollupSweepRunResult(
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

        Byte-for-byte the same shape as ``AARReviewSweepJob._resolve_projects_to_sweep``:
        when constructed with an explicit ``project`` (a single-project pin
        -- used by unit tests and any future explicit scoping), sweep JUST
        that project. Otherwise enumerate EVERY registered project via
        ``ports.workspace_registry.list_projects()`` -- the SAME
        DB-authoritative, registry-driven enumeration helper the watcher
        fan-out, the AAR-review sweep, and the periodic
        analytics-snapshot/cache-warming tasks already use (ADR-006: the
        registry is the single source of truth for "which projects exist").
        Container wiring (Phase 4's T4-002) always constructs this job with
        ``project=None`` -- this is a cross-project rollup, not scoped to
        whichever single project the worker's sync engine happens to be
        bound to.

        ``getattr(..., "list_projects", None)`` mirrors the exact defensive
        pattern already used at every ``list_projects()`` call site in
        ``runtime.py`` and in ``AARReviewSweepJob`` -- tolerates a test/mock
        registry that does not implement the method, degrading to "no
        projects" rather than raising.
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
            logger.exception("routing_rollup_sweep: workspace_registry.list_projects() failed")
            return []
        return [p for p in projects if str(getattr(p, "id", "") or "")]

    async def _execute_inner(self, project: Any, project_id: str) -> RoutingRollupSweepRunResult:
        # Local imports: backend.application.services.{common,agent_queries}
        # transitively import backend.runtime_ports, which imports
        # backend.adapters.jobs (for InProcessJobScheduler) -- importing them
        # at THIS module's top level would create an import cycle through
        # backend/adapters/jobs/runtime.py's eager
        # `from backend.adapters.jobs.routing_rollup_sweep_job import RoutingRollupSweepJob`
        # (added by Phase 4's T4-002). Deferring to call time (mirrors the
        # existing local-import pattern in
        # aar_review_sweep_job.py::AARReviewSweepJob._execute_inner,
        # backend/runtime/container.py's _start_cache_warming_task, and
        # backend/adapters/jobs/runtime.py's _maybe_start_drain_loop) breaks
        # the cycle with zero behavior change.
        from backend.application.services.agent_queries import (  # noqa: PLC0415
            aclear_project_cache,
        )
        from backend.application.services.agent_queries.routing_rollup import (  # noqa: PLC0415
            RoutingRollupQueryService,
        )
        from backend.application.services.common import resolve_application_request  # noqa: PLC0415

        try:
            app_request = await resolve_application_request(
                None, self.ports, self.ports.storage.db, requested_project_id=project_id,
            )
        except Exception as exc:
            logger.exception(
                "routing_rollup_sweep: failed to resolve application request for project_id=%s",
                project_id,
            )
            return RoutingRollupSweepRunResult(success=False, outcome="error", error=str(exc))
        context, ports = app_request.context, app_request.ports

        # ── Zero re-derivation: every aggregation/mapping/provider/metric
        # step below is Phase 3's RoutingRollupQueryService, called exactly
        # as it is documented to be called (fetch_raw_rows -> apply_mapping
        # -> apply_provider -> compute_metrics). This job never computes a
        # task_class, a provider, or a D5 metric value itself.
        rollup_service = RoutingRollupQueryService()
        try:
            raw_rows = await rollup_service.fetch_raw_rows(
                context, ports, project_ids=[project_id],
            )
        except Exception as exc:
            logger.exception(
                "routing_rollup_sweep: fetch_raw_rows failed for project_id=%s", project_id
            )
            return RoutingRollupSweepRunResult(success=False, outcome="error", error=str(exc))

        mapped_rows = rollup_service.apply_mapping(raw_rows)
        provider_rows = rollup_service.apply_provider(mapped_rows)
        key_dtos = rollup_service.compute_metrics(provider_rows)

        rollup_repo = _routing_rollup_repo(ports.storage.db)
        rows_written = 0
        for provider_row, key_dto in zip(provider_rows, key_dtos, strict=True):
            row = _build_routing_rollup_row(provider_row, key_dto)
            try:
                await rollup_repo.upsert(row)
            except Exception:
                logger.exception(
                    "routing_rollup_sweep: upsert failed for project_id=%s key=(%s, %s)",
                    project_id,
                    row.get("source_skill_name"),
                    row.get("model"),
                )
                continue
            rows_written += 1

        # ── Cache-invalidation hook (T4-003) ─────────────────────────────────
        # routing_rollup's read surfaces (Phase 5) memoize per-project reads
        # the same way aar_review_list does (see aar_review_sweep_job.py's
        # own docstring) -- explicitly bust the project's cache on any write
        # so a live sweep's rows are never masked by a stale cached read for
        # up to the TTL. Row-count-gated: a no-op tick (rows_written == 0,
        # e.g. a project with no in-window sessions) must never invalidate a
        # cache that has nothing stale to clear.
        if rows_written > 0:
            try:
                await aclear_project_cache(project_id)
            except Exception:
                logger.exception(
                    "routing_rollup_sweep: cache invalidation failed for project_id=%s", project_id
                )

        # ── Observational watermark only (see module docstring) — never
        # read back to scope the NEXT tick's fetch_raw_rows call.
        newest_window_end = max((dto.window_end for dto in key_dtos), default="")
        if newest_window_end:
            self._watermarks[project_id] = newest_window_end

        return RoutingRollupSweepRunResult(
            success=True,
            outcome="success",
            keys_computed=len(key_dtos),
            rows_written=rows_written,
            details={
                "projectId": project_id,
                "watermark": self._watermarks.get(project_id, ""),
            },
        )


def _aggregate_sweep_results(
    project_results: dict[str, RoutingRollupSweepRunResult],
) -> RoutingRollupSweepRunResult:
    """Fold N per-project ``RoutingRollupSweepRunResult`` rows into one
    tick-level result.

    Byte-for-byte the same outcome-precedence rules as
    ``aar_review_sweep_job.py::_aggregate_sweep_results`` (chosen there to
    preserve the exact single-project outcome values pre-multi-project when
    there is only one project in *project_results*):

    - No projects at all -> ``"no_project"`` (mirrors the pre-fan-out no-op).
    - Every project coalesced -> ``"coalesced"``.
    - Any project failed structurally (``success=False``) -> overall
      ``success=False``; ``outcome="error"`` only when EVERY project failed,
      ``"partial_error"`` when some succeeded and some failed -- one
      project's structural failure must never mask another project's
      successful sweep, and must never be silently swallowed either.
    - Otherwise -> ``"success"``.
    """
    if not project_results:
        return RoutingRollupSweepRunResult(success=True, outcome="no_project")

    results = list(project_results.values())
    outcomes = {r.outcome for r in results}
    if outcomes == {"coalesced"}:
        return RoutingRollupSweepRunResult(success=True, outcome="coalesced")

    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    if failures and not successes:
        outcome = "error"
    elif failures:
        outcome = "partial_error"
    else:
        outcome = "success"

    errors = {pid: r.error for pid, r in project_results.items() if r.error}

    return RoutingRollupSweepRunResult(
        success=not failures,
        outcome=outcome,
        keys_computed=sum(r.keys_computed for r in results),
        rows_written=sum(r.rows_written for r in results),
        error="; ".join(f"{pid}: {err}" for pid, err in sorted(errors.items())) or None,
        details={
            "projectCount": len(project_results),
            "projectIds": sorted(project_results.keys()),
            "perProject": {pid: r.details for pid, r in project_results.items()},
        },
    )
