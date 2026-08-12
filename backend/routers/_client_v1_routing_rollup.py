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

DI-4e fix-cycle-2 success_rate HALT gate
-----------------------------------------
``_row_to_key_dto`` withholds ``success_rate`` (forces ``None``) for any
persisted row whose ``provider`` matches, case-insensitively,
``config.CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS`` (default
``("openai",)``) -- the D-b4 live-verification gate's mechanism, per
``docs/project_plans/feature_contracts/enhancements/di-4e-routing-success-rate.md``
AC2. This is a read-time backstop on top of the compute-time gate in
``routing_rollup.py::_success_rate_and_coverage`` -- it never trusts the
persisted column's value for a gated provider, regardless of when or by
which binary that row was written.

Mapping-identity certification (read-path withhold)
---------------------------------------------------
``mapping_version`` is the ONLY one of the three mapping-identity fields that
is persisted per row; ``mapping_id`` and ``mapping_digest`` are always supplied
from the current in-code constants. So the moment ``MAPPING_VERSION`` /
``MAPPING_DIGEST`` are bumped in code, any row persisted under the previous
mapping would be served as ``(old mapping_version, new mapping_digest)`` -- an
identity triple that never existed at any point in time. The external
delegation-router join validator requires ``mapping_id`` + ``mapping_version``
+ ``mapping_digest`` to ALL match its pinned producer contract, so such rows
are rejected as ``mapping_mismatch`` and the feedback channel goes silently
inert.

There is no historical-digest table, so a stale row's true digest is
unrecoverable -- the row cannot be served honestly under either identity.
``_row_certifiable`` therefore withholds it from the read path entirely
(``_build_response_from_rows`` partitions before doing anything else), so a
superseded-mapping row contributes to nothing -- not ``keys``, not the FR-7
counters, not ``generated_at`` -- exactly as if it had not been swept yet. The
next sweep recomputes it under the current mapping and it returns naturally.
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


def _row_certifiable(row: Mapping[str, Any]) -> bool:
    """Can this persisted row be certified under the CURRENT mapping contract?

    True iff the row's persisted ``mapping_version`` equals
    ``routing_feedback_contract.MAPPING_VERSION``.

    A row whose persisted ``mapping_version`` differs was computed under a
    superseded mapping, so its ``task_class`` cannot be certified under the
    current contract -- and because ``mapping_digest`` is never persisted
    per-row, that row's TRUE digest is unrecoverable. Serving it would force a
    choice between two lies: pairing its old ``mapping_version`` with the
    current ``mapping_digest`` constant (fabricating an identity triple that
    never existed -- the bug this predicate closes) or restamping it with the
    current version (asserting stale data is current). Withholding is the only
    honest option; the next sweep recomputes the row under the current mapping.

    A row with an EMPTY ``mapping_version`` is likewise not certifiable: it
    carries no evidence of which mapping produced it, and ``_row_to_key_dto``'s
    empty-column fallback would silently restamp it as current.
    """
    return str(row.get("mapping_version") or "") == routing_feedback_contract.MAPPING_VERSION


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

    The verbatim ``mapping_version`` read is now provably CONSISTENT with the
    ``mapping_id``/``mapping_digest`` constants beside it: only rows that pass
    ``_row_certifiable`` reach this function via ``_build_response_from_rows``,
    and passing that predicate means the persisted value already equals
    ``MAPPING_VERSION``. The mixed-identity triple is structurally unreachable
    on the served path rather than merely unlikely. (Called directly -- as unit
    tests do -- this function still echoes whatever the row holds; the
    certification guarantee belongs to the reassembly entrypoint.)
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
        # DI-4e fix-cycle-2 (reviewer finding #1): the D-b4 HALT gate applies
        # on this read path too, not only at compute time -- a row whose
        # persisted `provider` matches (case-insensitively)
        # `config.CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS` has
        # `success_rate` withheld unconditionally, regardless of what value
        # is already sitting in the persisted column. This is the backstop
        # that makes the gate real for REST/MCP/CLI: even a row a stale-gate
        # worker sweep already wrote (or a future sweep run with an
        # unpatched binary) is never served with a stale-family value.
        success_rate=(
            None
            if str(row.get("provider") or "").strip().lower()
            in config.CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS
            else row.get("success_rate")
        ),
        # DI-4e: success_rate_coverage_fraction is compute-layer/response-DTO
        # ONLY -- this task adds no persisted column (see RoutingRollupKeyDTO's
        # docstring). Always None on this read path; recoverable only from a
        # live RoutingRollupQueryService.compute_metrics() call, never from a
        # persisted row.
        success_rate_coverage_fraction=None,
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
    so the two counters always sum to the total ``sample_count`` of the
    CERTIFIED population -- see the mapping-identity note below. The
    counter-sum invariant holds over certified rows, NOT over all persisted
    rows: a superseded-mapping row's ``sample_count`` is absent from both
    counters by design, the same way a not-yet-swept key's is.

    Mapping-identity certification (see the module docstring): rows are
    partitioned through ``_row_certifiable`` FIRST, before any other work.
    Rows carrying a superseded ``mapping_version`` are withheld entirely --
    they contribute to no field of the response (not ``keys``, not the FR-7
    counters, not the skill-dimension counts, not ``generated_at``). If nothing
    certifies, the documented degradation envelope is returned, identical to
    the "no persisted rows yet" shape.

    DI-4e/D-b3: also reassembles ``skill_attributed_key_count``/
    ``skill_unattributed_key_count`` from the persisted rows -- a row (not a
    session total, unlike ``mapped_count``/``unclassified_count`` above)
    counts iff its persisted ``sample_count >= CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE``,
    mirroring ``routing_rollup.py::_skill_dimension_coverage``'s population
    definition exactly (every key at the raw grain clearing the sample-size
    bar, regardless of ``task_class``).
    """
    if not rows:
        return _empty_response(enabled=True, generated_at=None)

    # Mapping-identity partition -- FIRST, before any counter or DTO work, so
    # a superseded-mapping row can never leak into any served field.
    certified_rows = [row for row in rows if _row_certifiable(row)]
    withheld_count = len(rows) - len(certified_rows)
    if withheld_count:
        logger.warning(
            "routing_rollup: withheld %d persisted row(s) whose mapping_version "
            "does not match the current MAPPING_VERSION=%s -- they were computed "
            "under a superseded mapping and their true mapping_digest is "
            "unrecoverable; awaiting the next sweep",
            withheld_count,
            routing_feedback_contract.MAPPING_VERSION,
        )
    if not certified_rows:
        # Everything on hand is superseded -- report the documented "nothing to
        # report yet" degradation shape rather than a new envelope variant.
        return _empty_response(enabled=True, generated_at=None)

    rows = certified_rows

    key_dtos = [_row_to_key_dto(row) for row in rows]

    mapped_count = 0
    unclassified_count = 0
    unmapped_skill_names: set[str] = set()
    skill_attributed_key_count = 0
    skill_unattributed_key_count = 0
    min_sample_size = int(config.CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE)
    freshness_values: list[str] = []
    for row in rows:
        sample_count = int(row.get("sample_count") or 0)
        task_class = str(row.get("task_class") or "")
        source_skill_name = str(row.get("source_skill_name") or "")
        if task_class == UNCLASSIFIED_TASK_CLASS:
            unclassified_count += sample_count
            unmapped_skill_names.add(source_skill_name)
        else:
            mapped_count += sample_count
        if sample_count >= min_sample_size:
            if source_skill_name.strip():
                skill_attributed_key_count += 1
            else:
                skill_unattributed_key_count += 1
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
        skill_attributed_key_count=skill_attributed_key_count,
        skill_unattributed_key_count=skill_unattributed_key_count,
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
