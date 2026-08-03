"""Routing-feedback rollup read handler for the v1 client router (T5-001).

Serves the persisted ``routing_rollup`` table (``backend/db/repositories/
routing_rollup.py``) computed offline by the deterministic Rollup Compute
Service (``backend/application/services/agent_queries/routing_rollup.py::
RoutingRollupQueryService``) via Phase 4's worker sweep
(``backend/adapters/jobs/routing_rollup_sweep_job.py``). This module
performs **zero live aggregation** against ``sessions`` -- no ad-hoc SQL,
no in-request ``GROUP BY``. It only:

  1. Deserialises already-persisted per-key rows into the frozen
     ``aos.routing.feedback`` v1 ``RoutingRollupKeyDTO`` shape, verbatim.
  2. Sums each row's already-computed ``sample_count``/``task_class``
     fields in-memory to reproduce the three FR-7 response-level coverage
     counters (``mapped_count``, ``unclassified_count``,
     ``distinct_unmapped_skill_names``) -- mirroring
     ``RoutingRollupQueryService.compute_coverage_counters``'s policy
     exactly, but over already-persisted rows instead of a live aggregate
     query. The ``routing_rollup`` table does not persist these
     response-level counters itself (they are summed across the whole
     project, not per-key), so this reassembly step is unavoidable here --
     it is response-shaping over already-computed values, never a new
     derivation of ``task_class``/``provider``/metric fields.

``cost_coverage_fraction`` (v47)
---------------------------------
As of schema v47 this field IS persisted (``routing_rollup.cost_coverage_fraction``)
and is read back verbatim by ``_row_to_key_dto`` below -- no longer the
always-``0.0`` computed-not-persisted placeholder. A ``NULL`` column value
(a row written before v47, or never re-swept since) reads back as ``None``,
kept distinguishable from a genuinely computed ``0.0``.

Disabled state (D6/FR-10)
-------------------------
When ``config.CCDASH_ROUTING_FEEDBACK_ENABLED`` is false, this module
short-circuits to the deterministic disabled envelope (``enabled: false``,
``generated_at: null``, zero counters, empty ``keys``) *before* touching
the ``routing_rollup`` table at all. HTTP 200, never 404 -- capability
presence (``"routing:feedback"`` in ``_V1_CAPABILITIES``) signals feature
existence independent of the enabled/disabled runtime state.

Caching note
------------
``memoized_query``'s data-version fingerprint does NOT track the
``routing_rollup`` table, so cached rollups do not self-invalidate on a raw
row write. Freshness is instead handled at the write site: the P4 sweep
worker (``backend/adapters/jobs/routing_rollup_sweep_job.py``) calls
``aclear_project_cache`` whenever it persists rows -- mirrors
``_client_v1_aar_review.py``'s identical caching note.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

import aiosqlite

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.agent_queries import routing_feedback_contract
from backend.application.services.agent_queries._filters import resolve_project_scope
from backend.application.services.agent_queries.cache import memoized_query
from backend.application.services.agent_queries.models import (
    RoutingRollupKeyDTO,
    RoutingRollupResponseDTO,
)
from backend.application.services.agent_queries.routing_rollup import UNCLASSIFIED_TASK_CLASS
from backend.db.repositories.routing_rollup import (
    PostgresRoutingRollupRepository,
    SqliteRoutingRollupRepository,
)
from backend.observability import otel
from backend.routers.client_v1_models import ClientV1Envelope, build_client_v1_meta

logger = logging.getLogger("ccdash.routers.client_v1_routing_rollup")


def _get_instance_id() -> str:
    """Return a stable instance identifier, falling back to a default label."""
    return getattr(config, "INSTANCE_ID", "") or "ccdash-local"


# ---------------------------------------------------------------------------
# Envelope construction -- shared by the disabled short-circuit and the
# "no persisted rows yet" / read-failure degradation paths (AC-8: identity
# fields are populated from the frozen contract constants on every
# response, enabled or disabled).
# ---------------------------------------------------------------------------


def _empty_response(*, enabled: bool, generated_at: str | None) -> RoutingRollupResponseDTO:
    """Zero-count, empty-``keys`` envelope. Used for both the deterministic
    disabled shape (``enabled=False``) and the resilience degradation shape
    (``enabled=True`` when the flag is on but there is nothing to report
    yet -- no persisted rows, no resolvable project, or a read failure).
    """
    return RoutingRollupResponseDTO(
        enabled=enabled,
        generated_at=generated_at,
        contract_id=routing_feedback_contract.CONTRACT_ID,
        contract_version=routing_feedback_contract.CONTRACT_VERSION,
        taxonomy_id=routing_feedback_contract.TAXONOMY_ID,
        taxonomy_version=routing_feedback_contract.TAXONOMY_VERSION,
        taxonomy_digest=routing_feedback_contract.TAXONOMY_DIGEST,
        mapping_id=routing_feedback_contract.MAPPING_ID,
        mapping_version=routing_feedback_contract.MAPPING_VERSION,
        mapping_digest=routing_feedback_contract.MAPPING_DIGEST,
        mapped_count=0,
        unclassified_count=0,
        distinct_unmapped_skill_names=[],
        keys=[],
    )


def _disabled_envelope() -> RoutingRollupResponseDTO:
    """The deterministic disabled envelope (D6/FR-10) -- byte-identical
    across REST/MCP/CLI when ``CCDASH_ROUTING_FEEDBACK_ENABLED`` is false.
    """
    return _empty_response(enabled=False, generated_at=None)


def _row_to_key_dto(row: Mapping[str, Any]) -> RoutingRollupKeyDTO:
    """Deserialise one persisted ``routing_rollup`` row into a
    ``RoutingRollupKeyDTO``, verbatim.

    Identity fields never persisted per-row (``contract_id``/
    ``taxonomy_id``/``taxonomy_digest``/``mapping_id``/``mapping_digest``)
    are supplied from the frozen ``routing_feedback_contract`` constants.
    The three version fields that ARE persisted per-row
    (``contract_version``/``taxonomy_version``/``mapping_version``) are
    read verbatim from the row -- never re-derived -- so a response
    faithfully reflects the contract version in effect when the row was
    written, falling back to the current constants only if a column is
    unexpectedly empty.
    """
    return RoutingRollupKeyDTO(
        producer=routing_feedback_contract.PRODUCER,
        contract_id=routing_feedback_contract.CONTRACT_ID,
        contract_version=str(row.get("contract_version") or routing_feedback_contract.CONTRACT_VERSION),
        taxonomy_id=routing_feedback_contract.TAXONOMY_ID,
        taxonomy_version=str(row.get("taxonomy_version") or routing_feedback_contract.TAXONOMY_VERSION),
        taxonomy_digest=routing_feedback_contract.TAXONOMY_DIGEST,
        mapping_id=routing_feedback_contract.MAPPING_ID,
        mapping_version=str(row.get("mapping_version") or routing_feedback_contract.MAPPING_VERSION),
        mapping_digest=routing_feedback_contract.MAPPING_DIGEST,
        source_skill_name=str(row.get("source_skill_name") or ""),
        task_class=str(row.get("task_class") or ""),
        model=str(row.get("model") or ""),
        provider=str(row.get("provider") or ""),
        sample_count=int(row.get("sample_count") or 0),
        success_rate=row.get("success_rate"),
        # DI-4a: never fabricate a baseline for a persisted NULL -- a
        # zero-coverage key means it, per the same null-over-fabrication
        # principle success_rate/regression_rate already honor below. A
        # fabricated 1.0 here would silently reintroduce the exact
        # placeholder DI-4a exists to remove.
        cost_index=(
            float(row["cost_index"]) if row.get("cost_index") is not None else None
        ),
        # v47: now persisted (see RoutingRollupKeyDTO's docstring) -- read
        # back verbatim, never coerced. A NULL means "no column value yet"
        # (a row written before this column existed, or never re-swept),
        # kept distinguishable from a genuinely computed 0.0 -- the same
        # null-over-fabrication discipline `cost_index` already codifies
        # (D-a2), extended to its own coverage companion.
        cost_coverage_fraction=(
            float(row["cost_coverage_fraction"])
            if row.get("cost_coverage_fraction") is not None
            else None
        ),
        regression_rate=row.get("regression_rate"),
        # DI-4c: all three ARE persisted (as of v47, cost_coverage_fraction
        # also is), so they survive this read path intact. A NULL is never
        # coerced to a value: null effort_tier/effort_tier_source means "no session carried
        # one, or the key mixes several, or the rows predate v44" -- never
        # "low effort" -- and a null authoritative_effort_fraction means zero
        # samples, distinct from a genuine 0.0 ("checked, none authoritative").
        effort_tier=(str(row["effort_tier"]) if row.get("effort_tier") else None),
        effort_tier_source=(
            str(row["effort_tier_source"]) if row.get("effort_tier_source") else None
        ),
        authoritative_effort_fraction=(
            float(row["authoritative_effort_fraction"])
            if row.get("authoritative_effort_fraction") is not None
            else None
        ),
        confidence=float(row.get("confidence") if row.get("confidence") is not None else 0.0),
        eligible_for_adjustment=bool(row.get("eligible_for_adjustment")),
        window_start=str(row.get("window_start") or ""),
        window_end=str(row.get("window_end") or ""),
        freshness_ts=str(row.get("freshness_ts") or ""),
    )


def _build_response_from_rows(rows: list[Mapping[str, Any]]) -> RoutingRollupResponseDTO:
    """Reassemble the ``RoutingRollupResponseDTO`` envelope from already-
    persisted per-key rows.

    Pure Python arithmetic over rows already fetched from the
    ``routing_rollup`` table -- zero live SQL aggregation against
    ``sessions``. Every row lands in exactly one of ``mapped_count`` /
    ``unclassified_count`` (keyed strictly off the row's persisted
    ``task_class``, mirroring ``compute_coverage_counters``'s FR-7 policy),
    so the two counters always sum to the total persisted ``sample_count``.
    """
    if not rows:
        return _empty_response(enabled=True, generated_at=None)

    key_dtos = [_row_to_key_dto(row) for row in rows]

    mapped_count = 0
    unclassified_count = 0
    unmapped_skill_names: set[str] = set()
    freshness_values: list[str] = []
    for row in rows:
        sample_count = int(row.get("sample_count") or 0)
        task_class = str(row.get("task_class") or "")
        if task_class == UNCLASSIFIED_TASK_CLASS:
            unclassified_count += sample_count
            unmapped_skill_names.add(str(row.get("source_skill_name") or ""))
        else:
            mapped_count += sample_count
        freshness_ts = row.get("freshness_ts")
        if freshness_ts:
            freshness_values.append(str(freshness_ts))

    generated_at = max(freshness_values) if freshness_values else None

    return RoutingRollupResponseDTO(
        enabled=True,
        generated_at=generated_at,
        contract_id=routing_feedback_contract.CONTRACT_ID,
        contract_version=routing_feedback_contract.CONTRACT_VERSION,
        taxonomy_id=routing_feedback_contract.TAXONOMY_ID,
        taxonomy_version=routing_feedback_contract.TAXONOMY_VERSION,
        taxonomy_digest=routing_feedback_contract.TAXONOMY_DIGEST,
        mapping_id=routing_feedback_contract.MAPPING_ID,
        mapping_version=routing_feedback_contract.MAPPING_VERSION,
        mapping_digest=routing_feedback_contract.MAPPING_DIGEST,
        mapped_count=mapped_count,
        unclassified_count=unclassified_count,
        distinct_unmapped_skill_names=sorted(unmapped_skill_names),
        keys=key_dtos,
    )


# ---------------------------------------------------------------------------
# Cache param extractor + memoized fetch
# ---------------------------------------------------------------------------


def _routing_rollup_params(
    context: RequestContext,
    ports: CorePorts,
    *,
    project_id_override: str | None = None,
    bypass_cache: bool = False,  # noqa: ARG001 - consumed by the decorator
) -> dict[str, Any]:
    return {"project_id": project_id_override or ""}


@memoized_query("routing_rollup", param_extractor=_routing_rollup_params)
async def _fetch_routing_rollup(
    context: RequestContext,
    ports: CorePorts,
    *,
    project_id_override: str | None = None,
    bypass_cache: bool = False,  # noqa: ARG001 - consumed by the decorator; kept for REST parity
) -> RoutingRollupResponseDTO:
    """Fetch and deserialise the persisted ``routing_rollup`` rows for a project.

    Short-circuits to the deterministic disabled envelope (D6/FR-10) when
    ``CCDASH_ROUTING_FEEDBACK_ENABLED`` is false -- read fresh off
    ``config`` on every call (never cached at import time) so a runtime
    flag flip takes effect immediately.
    """
    if not bool(getattr(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", False)):
        return _disabled_envelope()

    scope = resolve_project_scope(context, ports, project_id_override)
    if scope is None:
        # No resolvable project -- normalized empty payload, never an error.
        return _empty_response(enabled=True, generated_at=None)

    project_id = scope.project.id

    with otel.start_span("routing_rollup.list", {"project_id": project_id}):
        try:
            db = ports.storage.db
            repo: Any = (
                SqliteRoutingRollupRepository(db)
                if isinstance(db, aiosqlite.Connection)
                else PostgresRoutingRollupRepository(db)
            )
            rows = await repo.get_by_project(project_id)
        except Exception:
            logger.exception(
                "routing_rollup: get_by_project failed project_id=%s", project_id
            )
            # Resilience: a read failure degrades to an empty payload, not
            # an HTTP error -- contract state, not a bug.
            return _empty_response(enabled=True, generated_at=None)

        return _build_response_from_rows(rows)


# ---------------------------------------------------------------------------
# Public handler (registered on client_v1_router by client_v1.py)
# ---------------------------------------------------------------------------


async def get_routing_rollup_v1(
    project_id: str | None,
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    bypass_cache: bool = False,
) -> ClientV1Envelope[RoutingRollupResponseDTO]:
    """Return the persisted routing-feedback rollup for a project, wrapped in a v1 envelope."""
    result = await _fetch_routing_rollup(
        request_context,
        core_ports,
        project_id_override=project_id,
        bypass_cache=bypass_cache,
    )
    return ClientV1Envelope(
        data=result,
        meta=build_client_v1_meta(instance_id=_get_instance_id()),
    )
