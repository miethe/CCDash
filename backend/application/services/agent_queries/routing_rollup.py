"""Deterministic ``(project_id, source_skill_name, model)``-grain rollup
aggregation for the Proof -> Routing Feedback Loop producer surface (BP-6).

HARD INVARIANT (AOS Constraint 4): this module -- and every module it
(transitively, statically) imports under ``backend/`` -- MUST NEVER import a
model/LLM client library (``anthropic``, ``openai``, ``litellm``,
``langchain``, ``google.generativeai``) and MUST NEVER reference a
Task/Agent-dispatch helper symbol. Every computation here is pure SQL
aggregation plus threshold/arithmetic -- a reviewer should be able to grep
this file (and everything it imports) for any LLM/agent-invocation symbol and
find none. CI-enforced by
``backend/tests/test_routing_rollup_no_llm_imports.py`` (T3-005, not yet
built as of this task).

── T3-001 (this task): raw aggregation skeleton ────────────────────────────

``RoutingRollupQueryService.fetch_raw_rows`` issues exactly ONE pure-SQL
``GROUP BY project_id, source_skill_name, model`` query against the
``sessions`` table, bounded by a rolling window
(``config.CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS``, default 30). It returns
``RawRollupRow`` objects -- the raw per-key session count -- and deliberately
stops there: no mapping (``task_class``), no ``provider`` derivation, and no
D5 metric payload (``success_rate``, ``cost_index``, ``regression_rate``,
``confidence``, ``eligible_for_adjustment``) live in this task. Those are
layered on top, strictly bottom-up, by later Phase 3 tasks:

  - T3-002 applies the pinned ``skill_name -> task_class`` mapping and the
    ``_unclassified``/protected-class emission policy.
  - T3-003 derives ``provider`` (via ``backend.model_identity.derive_model_identity``)
    and computes the ``mapped_count``/``unclassified_count``/
    ``distinct_unmapped_skill_names`` coverage counters.
  - T3-004 computes the full D5 metric payload and adds
    ``RoutingRollupKeyDTO``/``RoutingRollupResponseDTO`` to ``models.py``.

See ``docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1/phase-3-rollup-compute-service.md``
for the full task breakdown.

Clones the query-shape conventions of two existing worker-primed rollup
precedents in this directory: ``aar_review.py`` (module-docstring no-LLM
invariant statement, direct ``aiosqlite`` queries, no ORM) and
``system_metrics.py::_fetch_model_family_tokens`` (dual SQLite/PostgreSQL
``GROUP BY`` aggregation, single statement, zero N+1).

── T3-002 (this task): pinned mapping + protected-class policy ────────────

``RoutingRollupQueryService.apply_mapping`` extends every ``RawRollupRow``
with a write-time-derived ``task_class`` (D3/FR-6 -- never the raw
``source_skill_name`` string) looked up via the pinned v1
``skill_name -> task_class`` mapping (``routing_feedback_contract.py`` +
vendored ``routing_task_map_v1.json``, Phase 1 output; read-only here, never
re-parsed or re-vendored). Two independent coverage-only emission gates
apply to the *resolved* ``task_class`` value -- never to whether a mapping
entry was found:

  - ``_unclassified`` (no entry found, OR an entry exists and explicitly
    resolves to ``_unclassified`` -- e.g. the executor-identity names
    ``codex``/``claude-api``/``ica-delegate``) is ALWAYS emitted,
    unconditionally of ``CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS``
    (FR-7).
  - Protected classes (``orchestration``, ``mode_d``) are emitted only when
    ``CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS`` resolves ``True``.

Both categories are policy-identical in one respect: ``is_coverage_only``
is set ``True`` on the emitted ``MappedRollupRow``, which T3-004 MUST use to
hardcode ``eligible_for_adjustment=False`` for these rows, independent of
its own sample-size threshold logic.

── T3-003 (this task): provider derivation + coverage counters ───────────

``RoutingRollupQueryService.apply_provider`` attaches ``provider`` to every
``MappedRollupRow`` by calling the EXISTING
``backend.model_identity.derive_model_identity(model)["modelProvider"]`` --
never an independently parsed or keyed value. This module never re-derives
provider identity on its own.

``RoutingRollupQueryService.compute_coverage_counters`` computes the three
FR-7 response-level coverage counters mandated by the PRD (``mapped_count``,
``unclassified_count``, ``distinct_unmapped_skill_names``) ONCE per response
-- session-level totals summed across the whole window, never per-key
figures (PRD Sec 6.3's ``mapped_count: 767`` / ``unclassified_count: 13632``
example -- magnitudes far larger than any single key's ``sample_count``).
Both counters are keyed strictly off the *resolved* ``task_class`` value
(never off whether a mapping entry was found): a row lands in
``unclassified_count`` iff ``task_class == UNCLASSIFIED_TASK_CLASS`` --
covering BOTH "no mapping entry" and "entry exists but resolves to
``_unclassified``" (the executor-identity case, e.g.
``codex``/``claude-api``/``ica-delegate``) -- and in ``mapped_count``
otherwise (this includes protected-class rows, which are still "mapped" for
counter purposes even though ``is_coverage_only`` gates their
``eligible_for_adjustment`` value). Every row lands in exactly one bucket,
so ``mapped_count + unclassified_count`` always equals the summed
``session_count`` of the input row list exactly.

── T3-004 (this task): D5 metric payload + DTO assembly ───────────────────

``RoutingRollupQueryService.compute_metrics`` is the terminal transform in
this bottom-up pipeline: it consumes ``ProviderRollupRow`` (T3-003's output)
and produces ``RoutingRollupKeyDTO`` (``models.py``) -- the full D5 metric
payload per PRD Sec.6.3's literal JSON example (``sample_count``,
``success_rate``, ``cost_index``, ``regression_rate``, ``confidence``,
``eligible_for_adjustment``, ``window_start``/``window_end``,
``freshness_ts``), plus the pinned join envelope carried verbatim from
``routing_feedback_contract.py``. ``RoutingRollupQueryService.build_response``
wraps that per-key list with the top-level ``RoutingRollupResponseDTO``
envelope (contract/taxonomy/mapping identity + T3-003's coverage counters).

Sub-threshold keys are NEVER suppressed (AC-5) -- every row handed to
``compute_metrics`` produces exactly one output DTO; only
``eligible_for_adjustment`` flips to ``False``.

``success_rate``/``regression_rate`` are emitted ``None`` in this v1: no
genuine per-session success/failure/regression signal exists yet in
``sessions`` for this module to compute from (``status`` only ever carries
``'active'``/``'completed'`` in this codebase, never an outcome judgment) --
fabricating one from a non-signal would be actively misleading to a
consuming router. Both are named, documented v1 design gaps for D9
socialization, never bugs -- see ``compute_metrics``'s docstring for the
full rationale.

── DI-4a (this task): real per-key ``cost_index`` ─────────────────────────

``cost_index`` was the fixed PRD-literal baseline (``1.0``) through the v1
Phase 3 build. DI-4a (feature contract
``docs/project_plans/feature_contracts/routing-feedback-cost-index-v1.md``)
replaces that placeholder with a real per-``(source_skill_name x model)``
cost signal derived from ``sessions.display_cost_usd``/``total_cost`` --
aggregated in the SAME single query ``fetch_raw_rows`` already issues (no
second DB round-trip). ``compute_metrics`` normalizes each key's mean
cost-per-covered-session against its own ``task_class``'s mean (D-a1) --
never a single global baseline, since a mechanical key's cost and an
orchestration key's cost are not comparable on the same scale. A key (or an
entire ``task_class``) with zero cost-attributed sessions emits
``cost_index=None`` (D-a2) -- the same null-over-fabrication principle
``success_rate``/``regression_rate`` already codify, extended to this third
field. ``cost_coverage_fraction`` (D-a3) is the additive companion signal so
a consuming router can discount a ``cost_index`` computed from a small
covered subset. Outlier suppression (D-a4) is deliberately NOT implemented
here -- the existing ``min_sample_size``/``eligible_for_adjustment`` gate is
relied on to exclude low-sample keys from adjustment; see
``compute_metrics``'s docstring for the full rationale.

── DI-4e (this task): real per-key ``success_rate`` ───────────────────────

``success_rate`` was the permanent ``None`` v1 design gap (no genuine
per-session outcome signal existed). DI-4d (Codex tool-error detection fix,
main ``b51de27``) and DI-4f (skill-attribution NO-GO, closed) together
cleared the two preconditions this task depended on: the per-family error
signal is no longer categorically skewed toward zero for Codex/GPT, and the
``(project_id, source_skill_name, model)`` key is confirmed to stay as-is.
DI-4e (feature contract
``docs/project_plans/feature_contracts/enhancements/di-4e-routing-success-rate.md``)
replaces the placeholder with a real per-key tool-error-rate complement,
aggregated in the SAME single query ``fetch_raw_rows`` already issues (a
``LEFT JOIN`` against a per-``(project_id, session_id)`` pre-aggregate of
``session_tool_usage`` -- a genuine second table, unlike the cost/effort
columns which live directly on ``sessions``, so this join is scoped by BOTH
``project_id`` AND ``session_id`` together, never ``session_id`` alone --
``sessions``' own primary key is the composite ``(project_id, id)``, so a
bare ``session_id`` join risks silently fusing two different projects'
sessions that happen to share an id string).

``success_rate = 1 - (sum(tool_errors) / sum(tool_calls))`` is
call-volume-weighted across every tool-usage-attributed session in the key
(D-b1) -- algebraically ``tool_success_sum / tool_call_sum`` since
``tool_errors = tool_call_sum - tool_success_sum`` -- never an unweighted
mean of each session's own error rate, which would let a 2-call session and
a 200-call session contribute equally. A key with zero tool-usage-attributed
sessions emits ``success_rate=None`` (D-b2) -- the same null-over-fabrication
principle ``cost_index`` already codifies (D-a2), extended to this field.
``success_rate_coverage_fraction`` is the per-key coverage companion,
mirroring ``cost_coverage_fraction``'s shape -- **but it is compute-layer/
response-DTO only, never persisted** (this contract adds no column/
migration; see the feature contract's Sec.6 "Storage implications: None"),
so it always reads back ``None`` on the persisted-table read path
(``_client_v1_routing_rollup.py``) -- a documented v1 limitation, not a bug.

Retry/recovery blindness (D-b5) is a named, documented limitation, not
fixed here: raw error-rate cannot distinguish "failed then recovered" from
"failed and stayed broken" (95.2% of tool-failure sessions still reach
``completed``, per the DI-4d re-measurement's own finding) -- the schema has
no retry linkage and building one is out of scope.

``regression_rate`` remains permanently ``None`` -- CLOSED per DI-4b (no
``test_results``/``test_runs`` signal exists anywhere in this schema); this
is not a deferred gap, it is a decided non-goal (see ``compute_metrics``'s
own comment at the assignment site).

Skill-dimension coverage (D-b3): the response envelope additionally gains
``skill_attributed_key_count``/``skill_unattributed_key_count`` -- computed
once per response over the SAME ``min_sample_size``-clearing population the
routing-key-skill-attribution feasibility brief's ~40-45% figure describes
(every row with ``session_count >= min_sample_size``, regardless of
``is_coverage_only`` -- that population is defined at the raw
``(project_id, source_skill_name, model)`` grain, before ``task_class``
mapping is even applied), so a consumer can tell a genuinely skill-aware key
(non-empty ``source_skill_name``) from a ``(project_id x model)`` key
wearing a three-part key's clothes without inspecting ``source_skill_name``
per row.

── DI-4e fix-cycle-2 (this task): the D-b4 HALT gate, made mechanical ──────

Fix cycle 1 RAN the D-b4 live verification query and recorded a HALT
determination (the gpt/codex-family's ``session_tool_usage`` window is still
measurably dominated by stale pre-b51de27 rows) -- but left the already-
implemented ``success_rate`` computation unconditional, with no code
mechanism actually withholding it for that family. This cycle closes that
gap: ``config.CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS``
(default ``("openai",)``) is threaded into ``_success_rate_and_coverage``
(compute time -- so no future worker sweep persists a stale-family value)
AND into ``_client_v1_routing_rollup.py::_row_to_key_dto`` (read time -- so
an already-persisted row is never served with one either). A row whose
``provider`` matches, case-insensitively, has ``success_rate``/
``success_rate_coverage_fraction`` forced to ``(None, 0.0)`` unconditionally
-- independent of ``CCDASH_ROUTING_FEEDBACK_ENABLED``/``live_consumption_disabled``
(DI-1, both stay untouched) and independent of how much genuine tool-usage
coverage the row actually has. This flag is the only sanctioned way to lift
the gate: only once the Codex ``session_tool_usage`` backfill/resync
precondition has run AND the D-b4 query has been re-run and shown clean.
"""
from __future__ import annotations

import functools
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from backend import config
from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.model_identity import derive_model_identity
from backend.parsers.effort_provenance import AUTHORITATIVE_EFFORT_SOURCES

from . import routing_feedback_contract
from ._filters import resolve_time_window
from .models import RoutingRollupKeyDTO, RoutingRollupResponseDTO

logger = logging.getLogger("ccdash.agent_queries.routing_rollup")

# --- T3-002: pinned mapping + protected-class policy constants -------------

#: Sentinel ``task_class`` emitted for a row whose ``source_skill_name`` has
#: no mapping entry OR whose mapping entry explicitly resolves to this same
#: value (executor-identity names -- see module docstring). Never
#: config-gated: always emitted per FR-7.
UNCLASSIFIED_TASK_CLASS = "_unclassified"

#: ``task_class`` values the pinned v1 mapping designates as protected
#: (never addressable as a routing key). Emission of rows resolving to one
#: of these is gated by ``config.CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS``
#: -- unlike ``UNCLASSIFIED_TASK_CLASS``, which bypasses that gate entirely.
PROTECTED_TASK_CLASSES: frozenset[str] = frozenset({"orchestration", "mode_d"})

# --- T3-004 / DI-4a: D5 metric payload constants ----------------------------

#: Saturation constant for ``_confidence_for_sample_count``. Fixed and
#: deliberately independent of ``config.CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE``
#: -- confidence's curve shape must not silently reshape itself if an
#: operator retunes the eligibility threshold; PRD Sec.6.3 lists
#: ``confidence`` and ``eligible_for_adjustment`` as two separate,
#: independently-designed fields.
_CONFIDENCE_SATURATION_K = 5.0


def _confidence_for_sample_count(sample_count: int) -> float:
    """Simple, documented, monotonically-increasing saturating curve.

    ``confidence = sample_count / (sample_count + k)`` -- asymptotically
    approaches but never reaches/exceeds ``1.0``, and is exactly ``0.0`` at
    ``sample_count == 0``. This is this task's own design surface (D5 is
    unspecified by the cross-repo contract); phase-3's Implementation Notes
    explicitly suggest this exact formula shape as an acceptable v1 choice
    -- deliberately not gold-plated into a tunable model.
    """
    if sample_count <= 0:
        return 0.0
    return min(1.0, sample_count / (sample_count + _CONFIDENCE_SATURATION_K))


def _task_class_cost_baselines(rows: list[ProviderRollupRow]) -> dict[str, float | None]:
    """Per-``task_class`` mean cost-per-covered-session baseline (DI-4a, D-a1).

    Ratified choice: **per-task_class mean**, never a single global mean and
    never a cheapest-key-as-baseline. Comparing an orchestration key's cost
    against a mechanical key's cost is meaningless -- the two task classes
    have structurally different expected cost profiles, so a global mean
    would flag every orchestration key as "expensive" regardless of whether
    it is well-routed within its own class. Grouping is by ``task_class``
    exactly (the value already resolved by ``apply_mapping``), including
    coverage-only classes (``_unclassified``/protected) -- they get their
    own baseline too, computed the same way, even though their rows'
    ``eligible_for_adjustment`` is hardcoded ``False`` independent of this.

    Only the COVERED subset contributes to either side of the mean (never
    diluted by treating an uncovered session as zero-cost, per D-a3) --
    ``sum(row.cost_sum for row in class) / sum(row.cost_covered_count for
    row in class)``. A ``task_class`` with zero covered sessions across ALL
    of its rows gets a ``None`` baseline, which in turn forces
    ``cost_index=None`` for every row in that class (D-a2) -- there is
    nothing to normalize against.
    """
    cost_sums: dict[str, float] = {}
    covered_counts: dict[str, int] = {}
    for row in rows:
        cost_sums[row.task_class] = cost_sums.get(row.task_class, 0.0) + row.cost_sum
        covered_counts[row.task_class] = (
            covered_counts.get(row.task_class, 0) + row.cost_covered_count
        )

    baselines: dict[str, float | None] = {}
    for task_class, covered_count in covered_counts.items():
        baselines[task_class] = (
            (cost_sums[task_class] / covered_count) if covered_count > 0 else None
        )
    return baselines


def _cost_index_and_coverage(
    row: ProviderRollupRow, baseline: float | None
) -> tuple[float | None, float]:
    """Compute one row's ``(cost_index, cost_coverage_fraction)`` pair (DI-4a).

    ``cost_coverage_fraction`` is always a float (``0.0`` when
    ``session_count`` is ``0``, never a ``ZeroDivisionError``) --
    ``cost_covered_count / session_count``, so a router can discount a
    ``cost_index`` derived from a small covered subset (D-a3).

    ``cost_index`` is ``None`` (D-a2, never a fabricated placeholder) when
    EITHER: (a) this row itself has zero covered sessions, or (b) its
    ``task_class``'s baseline could not be established (no covered sessions
    anywhere in the class). Otherwise it is the row's own mean
    cost-per-covered-session divided by its ``task_class`` baseline (D-a1) --
    a key at its class's baseline reads ``~1.0``; a key twice as expensive
    as baseline reads ``~2.0`` -- the same 1.0-centered scale the router's
    ratified merge clamp (``penalty_for_cost = max(cost_index - 1.0, 0.0)``,
    routing-feedback-router-merge-handoff.md Sec.2.2) depends on.

    Outlier handling (D-a4): deliberately NOT implemented here. A low-sample
    key with one dominant expensive session is left to the existing
    ``eligible_for_adjustment``/``min_sample_size`` gate -- a key too small
    to be adjustment-eligible does not need its cost math separately
    robustified, since the router will not act on an ineligible row anyway.
    Adding trimmed means/winsorization here would be scope creep relative to
    this contract; see the feature contract's D-a4 decision record.
    """
    coverage_fraction = (
        row.cost_covered_count / row.session_count if row.session_count > 0 else 0.0
    )
    if row.cost_covered_count <= 0 or baseline is None or baseline <= 0:
        return None, coverage_fraction
    key_mean_cost = row.cost_sum / row.cost_covered_count
    return key_mean_cost / baseline, coverage_fraction


def _success_rate_and_coverage(
    row: ProviderRollupRow, stale_providers: frozenset[str] = frozenset()
) -> tuple[float | None, float]:
    """Compute one row's ``(success_rate, success_rate_coverage_fraction)``
    pair (DI-4e).

    ``success_rate_coverage_fraction`` is always a float (``0.0`` when
    ``session_count`` is ``0``, never a ``ZeroDivisionError``) --
    ``tool_usage_covered_count / session_count`` -- so a consumer can
    discount a ``success_rate`` derived from a small covered subset. This
    field is compute-layer/response-DTO only (never persisted -- see the
    module docstring's DI-4e section); the persisted-table read path always
    reads it back ``None``.

    ``success_rate`` is ``None`` (D-b2, never a fabricated constant) when
    this row has zero tool-usage-covered sessions OR zero total tool calls
    across its covered subset (a session can appear in ``session_tool_usage``
    with rows that sum to ``call_count=0`` -- treated identically to "no
    attribution", since there is nothing to divide by). Otherwise it is the
    call-volume-weighted success fraction (D-b1):
    ``tool_success_sum / tool_call_sum`` -- algebraically identical to
    ``1 - (tool_errors / tool_calls)`` since ``tool_errors = tool_call_sum -
    tool_success_sum``, but expressed without an intermediate subtraction.

    DI-4e fix-cycle-2 (reviewer finding #1): before computing anything, a row
    whose ``provider`` (case-insensitively) is in *stale_providers* has
    ``success_rate`` withheld unconditionally -- returned ``None`` with a
    forced ``0.0`` coverage fraction, the same "nothing to report" shape as
    zero-attribution, REGARDLESS of how much genuine tool-usage coverage the
    row actually has. This is the D-b4 HALT gate: the live verification
    query (AC2) found the gpt/codex-family's ``session_tool_usage`` window
    still measurably dominated by stale pre-b51de27 rows, and the contract's
    own D-b4 ratification is a hard "do not ship" for that family until a
    backfill/resync precondition lands and this gate re-verifies clean.
    *stale_providers* defaults to empty here (this helper never reads
    ``config`` itself, mirroring every other pure helper in this module) --
    ``compute_metrics`` is the sole caller and always threads
    ``config.CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS`` through.
    """
    coverage_fraction = (
        row.tool_usage_covered_count / row.session_count if row.session_count > 0 else 0.0
    )
    if row.provider.strip().lower() in stale_providers:
        return None, 0.0
    if row.tool_usage_covered_count <= 0 or row.tool_call_sum <= 0:
        return None, coverage_fraction
    return row.tool_success_sum / row.tool_call_sum, coverage_fraction


def _skill_dimension_coverage(
    rows: list[ProviderRollupRow], min_sample_size: int
) -> tuple[int, int]:
    """Compute the two D-b3 response-level skill-dimension coverage counters.

    Scoped to the SAME ``min_sample_size``-clearing population the
    routing-key-skill-attribution feasibility brief's ~40-45% coverage
    figure describes -- every row with ``session_count >= min_sample_size``,
    evaluated at the raw ``(project_id, source_skill_name, model)`` grain
    (i.e. regardless of ``is_coverage_only``/``task_class``, since that
    population is defined BEFORE the pinned mapping is applied). A row
    counts as skill-attributed iff its ``source_skill_name`` is non-empty
    after stripping whitespace -- the same "blank is absent, not a distinct
    tier" rule ``_unambiguous_or_none`` already applies elsewhere in this
    module. Returns ``(skill_attributed_key_count, skill_unattributed_key_count)``;
    a row below the threshold contributes to neither counter (deliberately
    NOT the same population as ``eligible_for_adjustment``, which also
    excludes coverage-only rows -- this counter answers "how much of the key
    space clearing the sample bar is genuinely skill-aware", not "how much of
    it is adjustment-eligible").
    """
    attributed = 0
    unattributed = 0
    for row in rows:
        if row.session_count < min_sample_size:
            continue
        if row.source_skill_name.strip():
            attributed += 1
        else:
            unattributed += 1
    return attributed, unattributed


def _now_iso() -> str:
    """Wall-clock ``freshness_ts``/``generated_at`` source, isolated into its
    own function so T3-005's determinism test can freeze it via
    ``unittest.mock.patch`` -- mirrors ``aar_review.py``'s own ``_now_iso()``
    convention exactly (module-level function, timezone-aware UTC
    ``.isoformat()``).
    """
    return datetime.now(timezone.utc).isoformat()


def _iso8601(value: datetime) -> str:
    """Render *value* as a timezone-aware ISO-8601 string for DTO-facing
    fields (``window_start``/``window_end``).

    Distinct in purpose from this module's ``_iso()`` helper (used inside
    ``_fetch_raw_aggregate_rows``), which renders the NAIVE
    ``YYYY-MM-DDTHH:MM:SS`` form used only for ``sessions.updated_at`` SQL
    string comparisons -- never reuse ``_iso()`` for a DTO-facing field, and
    never reuse this helper for a SQL parameter.
    """
    return value.isoformat()


def _unambiguous_or_none(distinct_count: Any, candidate: Any) -> str | None:
    """Resolve a DI-4c unambiguous-or-null effort field.

    Returns *candidate* only when the key's sessions carry EXACTLY ONE distinct
    non-null value for the field (``distinct_count == 1``, where the SQL
    ``COUNT(DISTINCT ...)`` already excluded NULLs). Any other count means the
    key either mixes values or carries none, and the honest answer is ``None``
    -- never a mode with a tiebreak, which would fabricate a winner exactly as
    a fabricated ``cost_index`` of ``1.0`` would (D-a2).

    Empty/whitespace-only *candidate* also resolves to ``None``: a blank string
    is an absent value, not a distinct tier.
    """
    if int(distinct_count or 0) != 1:
        return None
    text = str(candidate or "").strip()
    return text or None


def _authoritative_effort_fraction(
    authoritative_count: int, session_count: int
) -> float | None:
    """Fraction of a key's sessions whose ``effort_tier_source`` is
    harness-authoritative (DI-4c).

    ``None`` only when *session_count* is ``0`` -- there is nothing to
    characterize, and ``0.0`` would read as "we checked and none were
    authoritative". Otherwise always a real float, including a genuine ``0.0``
    (every session's provenance was stale/derived/unknown), which is the signal
    a router needs to discount the accompanying ``effort_tier``.

    Deliberately asymmetric with DI-4a's ``cost_coverage_fraction`` (always a
    float, never ``None``): that field's ``0.0`` is unambiguous because its
    companion ``cost_index`` is itself ``None`` at zero coverage, whereas an
    ``effort_tier`` can be perfectly well-defined while resting entirely on
    non-authoritative provenance.
    """
    if session_count <= 0:
        return None
    return authoritative_count / session_count


@dataclass(frozen=True, slots=True)
class RawRollupRow:
    """One raw aggregated ``(project_id, source_skill_name, model)`` key.

    Frozen at T3-001 -- the read contract Phase 4's ``RoutingRollupSweepJob``
    and this phase's later tasks (T3-002..T3-004) build on. Carries only the
    raw session count for the key over the resolved window; ``task_class``,
    ``provider``, and every D5 metric field are added by later tasks, never
    here.

    ``cost_sum``/``cost_covered_count`` (DI-4a) are the exception: they are
    per-session COST aggregates, not derived metric fields, and are cheapest
    to compute in the SAME single ``GROUP BY`` query ``fetch_raw_rows``
    already issues -- adding them here avoids a second DB round-trip in a
    later stage. ``cost_covered_count`` is the count of sessions in this key
    whose ``COALESCE(display_cost_usd, total_cost, 0) > 0`` (the same
    "has cost attribution" criterion the DI-4a feature contract's signal-
    source audit used); ``cost_sum`` is the sum of that same COALESCEd value
    over exactly those covered sessions (uncovered sessions contribute
    nothing to either aggregate -- never diluted by treating them as
    zero-cost, per D-a3).
    """

    project_id: str
    source_skill_name: str
    model: str
    session_count: int
    window_start: datetime
    window_end: datetime
    cost_sum: float = 0.0
    cost_covered_count: int = 0
    effort_tier: str | None = None
    effort_tier_source: str | None = None
    effort_authoritative_count: int = 0
    #: DI-4e: sum of ``session_tool_usage.call_count`` across every session
    #: in this key that has at least one tool-usage row, joined scoped by
    #: BOTH ``project_id`` AND ``session_id`` (never ``session_id`` alone --
    #: see module docstring's DI-4e section for why).
    tool_call_sum: int = 0
    #: DI-4e: sum of ``session_tool_usage.success_count`` over the same
    #: covered sessions as ``tool_call_sum``.
    tool_success_sum: int = 0
    #: DI-4e: count of sessions in this key with >=1 ``session_tool_usage``
    #: row (i.e. "has tool-usage attribution") -- the numerator of
    #: ``success_rate_coverage_fraction``.
    tool_usage_covered_count: int = 0


@dataclass(frozen=True, slots=True)
class MappedRollupRow:
    """A ``RawRollupRow`` extended with the write-time-derived ``task_class``
    (T3-002) -- the raw ``source_skill_name`` string is never copied into
    ``task_class`` unless the pinned mapping coincidentally maps a name to an
    identical string (D3/FR-6; not a false negative -- see phase-3 test
    notes).

    ``is_coverage_only`` is ``True`` whenever ``task_class`` is
    ``UNCLASSIFIED_TASK_CLASS`` or a member of ``PROTECTED_TASK_CLASSES``.
    T3-004 MUST hardcode ``eligible_for_adjustment=False`` for every row
    where this flag is ``True``, independent of its own sample-size
    threshold logic -- this flag is the single source of truth for that
    invariant; T3-004 must not re-derive coverage-only status by re-checking
    ``task_class`` membership itself.

    ``provider`` and every D5 metric field (``success_rate``, ``cost_index``,
    ``regression_rate``, ``confidence``, ``eligible_for_adjustment``, ...)
    are still absent here -- those are T3-003/T3-004's job.
    """

    project_id: str
    source_skill_name: str
    model: str
    session_count: int
    window_start: datetime
    window_end: datetime
    task_class: str
    is_coverage_only: bool
    cost_sum: float = 0.0
    cost_covered_count: int = 0
    effort_tier: str | None = None
    effort_tier_source: str | None = None
    effort_authoritative_count: int = 0
    tool_call_sum: int = 0
    tool_success_sum: int = 0
    tool_usage_covered_count: int = 0


@dataclass(frozen=True, slots=True)
class ProviderRollupRow:
    """A ``MappedRollupRow`` extended with the derived ``provider`` field
    (T3-003).

    ``provider`` is ALWAYS ``derive_model_identity(model)["modelProvider"]``
    -- never independently parsed or keyed in this module, even as a "quick"
    fallback for an edge-case model string (phase-3 Implementation Notes:
    "Do not add a new provider-derivation code path 'for efficiency' --
    always call through derive_model_identity(), even if it means one extra
    function call per row.").

    Every other D5 metric field (``success_rate``, ``cost_index``,
    ``regression_rate``, ``confidence``, ``eligible_for_adjustment``, ...)
    is still absent here -- those, plus the ``RoutingRollupKeyDTO``/
    ``RoutingRollupResponseDTO`` assembly, are T3-004's job.
    """

    project_id: str
    source_skill_name: str
    model: str
    session_count: int
    window_start: datetime
    window_end: datetime
    task_class: str
    is_coverage_only: bool
    provider: str
    cost_sum: float = 0.0
    cost_covered_count: int = 0
    effort_tier: str | None = None
    effort_tier_source: str | None = None
    effort_authoritative_count: int = 0
    tool_call_sum: int = 0
    tool_success_sum: int = 0
    tool_usage_covered_count: int = 0


@dataclass(frozen=True, slots=True)
class CoverageCounters:
    """The three FR-7 response-level coverage counters (T3-003) --
    ``mapped_count``, ``unclassified_count``, and ``distinct_unmapped_skill_names``.

    Computed ONCE per response as session-level totals summed across the
    whole window -- never as per-key figures (PRD Sec 6.3's
    ``mapped_count: 767`` / ``unclassified_count: 13632`` example, magnitudes
    far larger than any single key's ``sample_count``, confirms these are
    aggregate window totals). ``mapped_count`` and ``unclassified_count`` are
    keyed strictly off the *resolved* ``task_class`` value on each input row
    -- never off whether a mapping entry existed for its
    ``source_skill_name`` -- so ``mapped_count + unclassified_count`` always
    equals the summed ``session_count`` of the input rows exactly; a row is
    counted in exactly one of the two buckets, never both and never neither.
    ``distinct_unmapped_skill_names`` is a deduplicated, deterministically
    sorted list of the raw ``source_skill_name`` values that resolved to
    ``UNCLASSIFIED_TASK_CLASS`` -- sorted order is required for T3-005's
    downstream determinism guarantee.
    """

    mapped_count: int
    unclassified_count: int
    distinct_unmapped_skill_names: list[str]


@functools.lru_cache(maxsize=1)
def _load_skill_to_task_class_mapping() -> dict[str, str]:
    """Load and cache the pinned ``skill_name -> task_class`` mapping.

    Reads ONLY ``routing_feedback_contract.MAPPING_JSON_PATH`` -- this
    function is a pure consumer of the Phase 1 contract, it never re-parses
    a second copy of the mapping file or re-vendors the mapping data. Cached
    at module scope because the vendored file is a frozen, version-pinned
    contract artifact (``routing_feedback_contract.MAPPING_VERSION``) that
    never changes at runtime; ``test_routing_feedback_contract_parity.py``
    (T1-005) is the CI guard against silent byte-level drift of the file
    this cache reads exactly once per process.
    """
    raw = json.loads(routing_feedback_contract.MAPPING_JSON_PATH.read_text(encoding="utf-8"))
    return {
        str(rule["source_skill_name"]): str(rule["task_class"])
        for rule in raw.get("rules", [])
    }


def _resolve_task_class(source_skill_name: str, mapping: dict[str, str]) -> str:
    """Exact dict lookup only -- never fuzzy-matched (phase-3 risk
    mitigation table: "Mapping is applied via exact dict lookup ... never
    fuzzy-matched").

    Missing entry AND an entry that itself resolves to
    ``UNCLASSIFIED_TASK_CLASS`` (executor-identity names, e.g. ``codex``,
    ``claude-api``, ``ica-delegate``) are policy-identical outcomes -- the
    caller must never distinguish "no entry" from "entry resolves to
    _unclassified" (D3/FR-7); both paths return ``UNCLASSIFIED_TASK_CLASS``
    from this single lookup.
    """
    resolved = mapping.get(source_skill_name)
    return resolved or UNCLASSIFIED_TASK_CLASS


def _iso(value: datetime) -> str:
    """Render *value* to the naive ``YYYY-MM-DDTHH:MM:SS`` form used for
    ``sessions.updated_at`` string comparisons elsewhere in this package
    (see ``system_metrics.py::_query_max_updated_at`` and its test fixtures).
    """
    return value.strftime("%Y-%m-%dT%H:%M:%S")


async def _fetch_raw_aggregate_rows(
    db: Any,
    *,
    project_ids: list[str] | None,
    window_start: datetime,
    window_end: datetime,
) -> list[RawRollupRow]:
    """Issue exactly one ``GROUP BY`` aggregate query against ``sessions``.

    Dual-path for SQLite (``aiosqlite``) and PostgreSQL (``asyncpg``),
    mirroring ``system_metrics.py::_fetch_model_family_tokens``. Zero N+1: a
    single SQL statement services the whole call regardless of how many
    distinct ``(project_id, source_skill_name, model)`` keys exist in the
    window. No ORM lazy-loading anywhere on this path.

    DI-4a: the same statement additionally aggregates ``cost_sum``/
    ``cost_covered_count`` (see ``RawRollupRow``'s docstring for the exact
    "has cost attribution" criterion) -- ``COALESCE(display_cost_usd,
    total_cost, 0) > 0``, mirroring the existing
    ``feature_rollup.py::COALESCE(s.display_cost_usd, s.total_cost, 0)``
    precedent for "the canonical per-session displayed cost" in this
    codebase.

    DI-4e: the same statement additionally ``LEFT JOIN``s a
    per-``(project_id, session_id)`` pre-aggregate of ``session_tool_usage``
    (``tool_call_sum``/``tool_success_sum``/``tool_usage_covered_count`` --
    see ``RawRollupRow``'s docstring). The join is scoped by BOTH
    ``project_id`` AND ``session_id`` together -- ``sessions``' own primary
    key is the composite ``(project_id, id)``, so joining on ``session_id``
    alone risks silently fusing two different projects' sessions that happen
    to share an id string (the known gotcha the feature contract's
    Implementation Notes flags explicitly). Still exactly one query -- the
    join is folded into the same ``GROUP BY`` this function already issues,
    no second DB round-trip.
    """
    window_start_iso = _iso(window_start)
    window_end_iso = _iso(window_end)

    _COST_EXPR = "COALESCE(display_cost_usd, total_cost, 0)"
    # DI-4e: pre-aggregate session_tool_usage to (project_id, session_id)
    # grain BEFORE joining to sessions -- session_tool_usage's own PK is
    # (session_id, tool_name), so a naive join would fan out one row per
    # tool_name and double-count session_count in the outer GROUP BY. The
    # CTE collapses that fan-out to exactly one row per covered session.
    _TOOL_USAGE_CTE = """
        tool_usage_per_session AS (
            SELECT project_id, session_id,
                   SUM(call_count) AS calls,
                   SUM(success_count) AS successes
            FROM session_tool_usage
            GROUP BY project_id, session_id
        )"""
    # DI-4c: inlined rather than parameterized because these are OUR OWN module
    # constants (backend/parsers/effort_provenance.py), never user input -- the
    # same reasoning that lets _COST_EXPR be inlined. sorted() keeps the emitted
    # SQL byte-stable across runs (frozenset iteration order is not), which the
    # determinism test depends on.
    _AUTHORITATIVE_LIST = ", ".join(
        f"'{token}'" for token in sorted(AUTHORITATIVE_EFFORT_SOURCES)
    )
    # Unambiguous-or-null needs two aggregates per field: a distinct-value count
    # (COUNT(DISTINCT x) ignores NULLs in both dialects) and any one non-null
    # value. When the count is exactly 1, MIN() *is* the single agreed value;
    # any other count means "mixed" (or "none") and the caller resolves to None.
    _EFFORT_AGGREGATES = f"""
                COUNT(DISTINCT effort_tier) AS effort_tier_distinct_count,
                MIN(effort_tier) AS effort_tier_any,
                COUNT(DISTINCT effort_tier_source) AS effort_source_distinct_count,
                MIN(effort_tier_source) AS effort_source_any,
                SUM(CASE WHEN effort_tier_source IN ({_AUTHORITATIVE_LIST})
                         THEN 1 ELSE 0 END) AS effort_authoritative_count"""

    # DI-4e: tool_usage_per_session.calls/.successes are NULL for a session
    # with no session_tool_usage rows at all (LEFT JOIN, no match) --
    # COALESCE(..., 0) folds that into the sums cleanly, while
    # tool_usage_covered_count's CASE explicitly tests the pre-COALESCE
    # NULL-ness of `.calls` so a genuinely-covered session whose calls sum
    # to 0 is never confused with "no attribution" at this row-construction
    # layer (see _success_rate_and_coverage for where that distinction is
    # actually consumed).
    _TOOL_AGGREGATES = """,
                COALESCE(SUM(tu.calls), 0) AS tool_call_sum,
                COALESCE(SUM(tu.successes), 0) AS tool_success_sum,
                SUM(CASE WHEN tu.calls IS NOT NULL THEN 1 ELSE 0 END) AS tool_usage_covered_count"""

    if isinstance(db, aiosqlite.Connection):
        params: list[Any] = [window_start_iso, window_end_iso]
        project_filter_sql = ""
        if project_ids:
            project_filter_sql = f" AND s.project_id IN ({','.join('?' * len(project_ids))})"
            params.extend(project_ids)

        sql = f"""
            WITH {_TOOL_USAGE_CTE}
            SELECT
                s.project_id AS project_id,
                s.skill_name AS source_skill_name,
                s.model AS model,
                COUNT(*) AS session_count,
                SUM(CASE WHEN {_COST_EXPR} > 0 THEN {_COST_EXPR} ELSE 0 END) AS cost_sum,
                SUM(CASE WHEN {_COST_EXPR} > 0 THEN 1 ELSE 0 END) AS cost_covered_count,{_EFFORT_AGGREGATES}{_TOOL_AGGREGATES}
            FROM sessions s
            LEFT JOIN tool_usage_per_session tu
                ON tu.session_id = s.id AND tu.project_id = s.project_id
            WHERE s.updated_at >= ? AND s.updated_at <= ?
              {project_filter_sql}
            GROUP BY s.project_id, s.skill_name, s.model
        """  # noqa: S608
        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        raw_rows = [dict(row) for row in rows]
    else:
        params = [window_start_iso, window_end_iso]
        project_filter_sql = ""
        if project_ids:
            placeholders = ",".join(f"${i}" for i in range(3, 3 + len(project_ids)))
            project_filter_sql = f" AND s.project_id = ANY(ARRAY[{placeholders}]::text[])"
            params.extend(project_ids)

        sql = f"""
            WITH {_TOOL_USAGE_CTE}
            SELECT
                s.project_id AS project_id,
                s.skill_name AS source_skill_name,
                s.model AS model,
                COUNT(*) AS session_count,
                SUM(CASE WHEN {_COST_EXPR} > 0 THEN {_COST_EXPR} ELSE 0 END) AS cost_sum,
                SUM(CASE WHEN {_COST_EXPR} > 0 THEN 1 ELSE 0 END) AS cost_covered_count,{_EFFORT_AGGREGATES}{_TOOL_AGGREGATES}
            FROM sessions s
            LEFT JOIN tool_usage_per_session tu
                ON tu.session_id = s.id AND tu.project_id = s.project_id
            WHERE s.updated_at >= $1 AND s.updated_at <= $2
              {project_filter_sql}
            GROUP BY s.project_id, s.skill_name, s.model
        """  # noqa: S608
        pg_rows = await db.fetch(sql, *params)
        raw_rows = [dict(row) for row in pg_rows]

    return [
        RawRollupRow(
            project_id=str(row["project_id"] or ""),
            source_skill_name=str(row["source_skill_name"] or ""),
            model=str(row["model"] or ""),
            session_count=int(row["session_count"] or 0),
            window_start=window_start,
            window_end=window_end,
            cost_sum=float(row.get("cost_sum") or 0.0),
            cost_covered_count=int(row.get("cost_covered_count") or 0),
            effort_tier=_unambiguous_or_none(
                row.get("effort_tier_distinct_count"), row.get("effort_tier_any")
            ),
            effort_tier_source=_unambiguous_or_none(
                row.get("effort_source_distinct_count"), row.get("effort_source_any")
            ),
            effort_authoritative_count=int(row.get("effort_authoritative_count") or 0),
            tool_call_sum=int(row.get("tool_call_sum") or 0),
            tool_success_sum=int(row.get("tool_success_sum") or 0),
            tool_usage_covered_count=int(row.get("tool_usage_covered_count") or 0),
        )
        for row in raw_rows
    ]


class RoutingRollupQueryService:
    """Aggregation entry point for the Proof -> Routing Feedback Loop.

    T3-001 shipped ``fetch_raw_rows`` -- the single-query, pure-SQL
    aggregation freezing the raw-row shape. T3-002 extended this class with
    ``apply_mapping`` -- pinned ``skill_name -> task_class`` derivation plus
    the ``_unclassified``/protected-class coverage-only policy. T3-003 (this
    task) further extends it with ``apply_provider`` (derived ``provider``
    per row, always via ``derive_model_identity()``) and
    ``compute_coverage_counters`` (the ``mapped_count``/``unclassified_count``/
    ``distinct_unmapped_skill_names`` FR-7 counters). T3-004 (this task)
    further extends it with ``compute_metrics`` (the D5 metric payload,
    terminal ``RoutingRollupKeyDTO`` assembly) and ``build_response`` (the
    top-level ``RoutingRollupResponseDTO`` envelope).
    """

    async def fetch_raw_rows(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        project_ids: list[str] | None = None,
        window_days: int | None = None,
    ) -> list[RawRollupRow]:
        """Return one ``RawRollupRow`` per distinct ``(project_id,
        source_skill_name, model)`` key present in ``sessions`` over the
        rolling window.

        Issues exactly one aggregate SQL statement (zero N+1) via
        ``_fetch_raw_aggregate_rows``. The window defaults to
        ``config.CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS`` (never hardcoded);
        pass *window_days* to override (test/worker convenience only).

        *context* is accepted for calling-convention parity with this
        directory's other query-service entry points
        (``aar_review.py::AARReviewQueryService.get_review``,
        ``system_metrics.py::SystemMetricsQueryService.get_system_token_rollup``)
        -- it is not yet consumed at this skeleton stage.
        """
        _ = context  # unused at this skeleton stage; kept for signature parity
        default_days = window_days if window_days is not None else config.CCDASH_ROUTING_FEEDBACK_WINDOW_DAYS
        window_start, window_end = resolve_time_window(default_days=default_days)

        db = ports.storage.db
        rows = await _fetch_raw_aggregate_rows(
            db,
            project_ids=project_ids,
            window_start=window_start,
            window_end=window_end,
        )
        logger.debug(
            "routing_rollup: fetched %d raw row(s) window=[%s, %s] project_ids=%s",
            len(rows),
            window_start.isoformat(),
            window_end.isoformat(),
            project_ids,
        )
        return rows

    def apply_mapping(
        self,
        rows: list[RawRollupRow],
        *,
        include_protected_rows: bool | None = None,
    ) -> list[MappedRollupRow]:
        """Derive ``task_class`` for every raw row via the pinned v1 mapping
        and apply the two independent coverage-only emission gates (T3-002).

        Pure in-memory transform -- no I/O beyond the cached, one-time
        mapping-file read (``_load_skill_to_task_class_mapping``). Never
        mutates *rows*; returns a new list.

        Emission policy (both gates evaluated against the *resolved*
        ``task_class``, never against whether a mapping entry was found):

          - ``task_class == UNCLASSIFIED_TASK_CLASS`` -- ALWAYS emitted,
            unconditionally of *include_protected_rows* (FR-7). This covers
            BOTH "no mapping entry for source_skill_name" and "a mapping
            entry exists and explicitly resolves to
            ``UNCLASSIFIED_TASK_CLASS``" (executor-identity names).
          - ``task_class in PROTECTED_TASK_CLASSES`` -- emitted only when
            *include_protected_rows* resolves ``True``. Defaults to
            ``config.CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS`` when
            the kwarg is left ``None`` (test/worker override point, mirrors
            ``fetch_raw_rows``'s ``window_days`` convention).
          - Any other resolved ``task_class`` -- always emitted, proceeds to
            T3-003/T3-004 as an ordinary routing key.

        Every emitted row carries ``is_coverage_only=True`` iff it matched
        either of the first two branches above -- T3-004 MUST consume that
        flag to hardcode ``eligible_for_adjustment=False``, never
        re-deriving coverage-only status by re-checking ``task_class``
        membership itself.
        """
        resolved_include_protected = (
            include_protected_rows
            if include_protected_rows is not None
            else config.CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS
        )
        mapping = _load_skill_to_task_class_mapping()

        mapped_rows: list[MappedRollupRow] = []
        for row in rows:
            task_class = _resolve_task_class(row.source_skill_name, mapping)
            is_unclassified = task_class == UNCLASSIFIED_TASK_CLASS
            is_protected = task_class in PROTECTED_TASK_CLASSES

            if is_protected and not resolved_include_protected:
                # Gated out entirely -- _unclassified rows never reach this
                # branch (is_protected is always False for them).
                continue

            mapped_rows.append(
                MappedRollupRow(
                    project_id=row.project_id,
                    source_skill_name=row.source_skill_name,
                    model=row.model,
                    session_count=row.session_count,
                    window_start=row.window_start,
                    window_end=row.window_end,
                    task_class=task_class,
                    is_coverage_only=is_unclassified or is_protected,
                    cost_sum=row.cost_sum,
                    cost_covered_count=row.cost_covered_count,
                    effort_tier=row.effort_tier,
                    effort_tier_source=row.effort_tier_source,
                    effort_authoritative_count=row.effort_authoritative_count,
                    tool_call_sum=row.tool_call_sum,
                    tool_success_sum=row.tool_success_sum,
                    tool_usage_covered_count=row.tool_usage_covered_count,
                )
            )
        return mapped_rows

    def apply_provider(self, rows: list[MappedRollupRow]) -> list[ProviderRollupRow]:
        """Attach the derived ``provider`` field to every mapped row (T3-003).

        ``provider`` is ALWAYS
        ``derive_model_identity(row.model)["modelProvider"]`` -- never an
        independently parsed or keyed value in this module. Pure in-memory
        transform, zero I/O; never mutates *rows*, returns a new list.
        """
        provider_rows: list[ProviderRollupRow] = []
        for row in rows:
            provider = str(derive_model_identity(row.model).get("modelProvider") or "")
            provider_rows.append(
                ProviderRollupRow(
                    project_id=row.project_id,
                    source_skill_name=row.source_skill_name,
                    model=row.model,
                    session_count=row.session_count,
                    window_start=row.window_start,
                    window_end=row.window_end,
                    task_class=row.task_class,
                    is_coverage_only=row.is_coverage_only,
                    provider=provider,
                    cost_sum=row.cost_sum,
                    cost_covered_count=row.cost_covered_count,
                    effort_tier=row.effort_tier,
                    effort_tier_source=row.effort_tier_source,
                    effort_authoritative_count=row.effort_authoritative_count,
                    tool_call_sum=row.tool_call_sum,
                    tool_success_sum=row.tool_success_sum,
                    tool_usage_covered_count=row.tool_usage_covered_count,
                )
            )
        return provider_rows

    def compute_coverage_counters(self, rows: list[MappedRollupRow]) -> CoverageCounters:
        """Compute the three FR-7 response-level coverage counters (T3-003).

        Keyed strictly off each row's *resolved* ``task_class`` value --
        never off whether a mapping entry was found for its
        ``source_skill_name`` (T3-002's executor-identity case --
        ``codex``/``claude-api``/``ica-delegate`` have mapping entries that
        themselves resolve to ``UNCLASSIFIED_TASK_CLASS`` -- lands in
        ``unclassified_count``, never ``mapped_count``, proving the counters
        never double-count a row that has both a mapping entry AND an
        ``_unclassified`` resolution).

        ``mapped_count`` and ``unclassified_count`` are session-level totals
        (summed ``session_count``) across every row in *rows* -- not counts
        of distinct rows and not per-key figures -- so
        ``mapped_count + unclassified_count`` always equals the summed
        ``session_count`` of *rows* exactly. ``distinct_unmapped_skill_names``
        is deduplicated and returned in deterministic (alphabetically sorted)
        order, required for T3-005's downstream determinism guarantee.
        """
        mapped_count = 0
        unclassified_count = 0
        unmapped_skill_names: set[str] = set()

        for row in rows:
            if row.task_class == UNCLASSIFIED_TASK_CLASS:
                unclassified_count += row.session_count
                unmapped_skill_names.add(row.source_skill_name)
            else:
                # Includes protected-class rows (`orchestration`, `mode_d`)
                # -- still "mapped" for counter purposes even though
                # `is_coverage_only` gates their `eligible_for_adjustment`.
                mapped_count += row.session_count

        return CoverageCounters(
            mapped_count=mapped_count,
            unclassified_count=unclassified_count,
            distinct_unmapped_skill_names=sorted(unmapped_skill_names),
        )

    def compute_metrics(
        self,
        rows: list[ProviderRollupRow],
        *,
        min_sample_size: int | None = None,
        freshness_ts: str | None = None,
        stale_providers: frozenset[str] | None = None,
    ) -> list[RoutingRollupKeyDTO]:
        """Compute the full D5 metric payload for every row and assemble the
        terminal ``RoutingRollupKeyDTO`` (T3-004) -- the last transform in
        the T3-001..T3-004 pipeline; no further processing stage follows
        this one.

        ``eligible_for_adjustment`` is
        ``sample_count >= min_sample_size`` -- but ONLY when
        ``row.is_coverage_only`` is ``False``. Coverage-only rows
        (``_unclassified``/protected-class, T3-002) are hardcoded
        ``eligible_for_adjustment=False`` regardless of ``sample_count``,
        honoring T3-002's documented hard contract
        (``MappedRollupRow.is_coverage_only`` is the single source of truth
        for this; this method never re-derives coverage-only status by
        re-checking ``task_class`` membership itself). Sub-threshold keys
        are NEVER suppressed (AC-5) -- every row in *rows* produces exactly
        one output DTO; only ``eligible_for_adjustment`` flips to ``False``.

        *min_sample_size* defaults to
        ``config.CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE`` (test/worker
        override point, mirrors ``fetch_raw_rows``'s ``window_days``
        convention). *freshness_ts* defaults to ``_now_iso()``, computed
        ONCE for the whole call so every row in one response shares an
        identical freshness timestamp -- also a test override point for
        T3-005's determinism guard (freeze this to prove field-identical
        output across two invocations).

        ``success_rate``/``success_rate_coverage_fraction`` (DI-4e) are
        computed via ``_success_rate_and_coverage`` -- see that helper's
        docstring for the full D-b1/D-b2 rationale (call-volume-weighted,
        ``None`` on zero tool-usage attribution) AND the DI-4e fix-cycle-2
        D-b4 HALT gate (``stale_providers``, below) it also enforces.

        *stale_providers* defaults to
        ``config.CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS`` (test
        override point, same convention as *min_sample_size*) -- a row whose
        ``provider`` matches (case-insensitively) has ``success_rate``
        withheld unconditionally, independent of how much genuine tool-usage
        coverage it has. This is the mechanism the D-b4 live-verification
        gate (AC2) requires: the gpt/codex-family's confirmed-stale
        ``session_tool_usage`` window must not be served through REST/MCP/
        CLI until a backfill/resync precondition lands and the gate
        re-verifies clean.

        ``regression_rate`` remains permanently ``None`` -- CLOSED per DI-4b:
        no ``test_results``/``test_runs`` signal exists anywhere in this
        schema for a regression judgment to be derived from. This is a
        decided non-goal, not a deferred gap (unlike ``success_rate`` before
        DI-4e) -- the ``routing_rollup`` DDL (Phase 2) declares the column
        nullable for exactly this reason, and it stays that way indefinitely.

        ``cost_index``/``cost_coverage_fraction`` (DI-4a) are computed via
        ``_task_class_cost_baselines``/``_cost_index_and_coverage`` -- see
        those helpers' docstrings for the full D-a1/D-a2/D-a3/D-a4
        rationale. The baseline map is computed ONCE per call over *rows*
        (never per-row) since it is a ``task_class``-level aggregate shared
        by every row in that class.
        """
        resolved_min_sample_size = (
            min_sample_size
            if min_sample_size is not None
            else config.CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE
        )
        resolved_freshness_ts = freshness_ts if freshness_ts is not None else _now_iso()
        resolved_stale_providers = (
            stale_providers
            if stale_providers is not None
            else frozenset(config.CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS)
        )
        cost_baselines = _task_class_cost_baselines(rows)

        key_dtos: list[RoutingRollupKeyDTO] = []
        for row in rows:
            eligible_for_adjustment = (
                not row.is_coverage_only and row.session_count >= resolved_min_sample_size
            )
            cost_index, cost_coverage_fraction = _cost_index_and_coverage(
                row, cost_baselines.get(row.task_class)
            )
            success_rate, success_rate_coverage_fraction = _success_rate_and_coverage(
                row, resolved_stale_providers
            )
            key_dtos.append(
                RoutingRollupKeyDTO(
                    producer=routing_feedback_contract.PRODUCER,
                    contract_id=routing_feedback_contract.CONTRACT_ID,
                    contract_version=routing_feedback_contract.CONTRACT_VERSION,
                    taxonomy_id=routing_feedback_contract.TAXONOMY_ID,
                    taxonomy_version=routing_feedback_contract.TAXONOMY_VERSION,
                    taxonomy_digest=routing_feedback_contract.TAXONOMY_DIGEST,
                    mapping_id=routing_feedback_contract.MAPPING_ID,
                    mapping_version=routing_feedback_contract.MAPPING_VERSION,
                    mapping_digest=routing_feedback_contract.MAPPING_DIGEST,
                    source_skill_name=row.source_skill_name,
                    task_class=row.task_class,
                    model=row.model,
                    provider=row.provider,
                    sample_count=row.session_count,
                    success_rate=success_rate,
                    success_rate_coverage_fraction=success_rate_coverage_fraction,
                    cost_index=cost_index,
                    cost_coverage_fraction=cost_coverage_fraction,
                    # DI-4b (closed): no test_results/test_runs signal exists
                    # anywhere in this schema for a regression judgment to be
                    # derived from -- regression_rate stays None permanently,
                    # a decided non-goal, never revisited by this task.
                    regression_rate=None,
                    effort_tier=row.effort_tier,
                    effort_tier_source=row.effort_tier_source,
                    authoritative_effort_fraction=_authoritative_effort_fraction(
                        row.effort_authoritative_count, row.session_count
                    ),
                    confidence=_confidence_for_sample_count(row.session_count),
                    eligible_for_adjustment=eligible_for_adjustment,
                    window_start=_iso8601(row.window_start),
                    window_end=_iso8601(row.window_end),
                    freshness_ts=resolved_freshness_ts,
                )
            )
        return key_dtos

    def build_response(
        self,
        rows: list[ProviderRollupRow],
        coverage: CoverageCounters,
        *,
        min_sample_size: int | None = None,
        freshness_ts: str | None = None,
    ) -> RoutingRollupResponseDTO:
        """Assemble the full top-level ``RoutingRollupResponseDTO`` envelope
        (T3-004) -- the single convenient entry point Phase 4's worker and
        Phase 5's transports call after running raw rows through
        ``fetch_raw_rows`` -> ``apply_mapping`` -> ``apply_provider`` (to
        produce *rows*) and ``apply_mapping``'s output through
        ``compute_coverage_counters`` (to produce *coverage*).

        Always assembles the ENABLED shape (``enabled=True``,
        ``generated_at`` set to *freshness_ts* or ``_now_iso()``). The
        deterministic DISABLED envelope
        (``CCDASH_ROUTING_FEEDBACK_ENABLED=False`` -> ``enabled=False``,
        ``generated_at=None``, zero counters, empty ``keys``) is a
        transport/worker-level short-circuit (D6) -- deliberately NOT built
        here; this compute service has no opinion on the flag and always
        computes real rows when called.

        DI-4e/D-b3: also computes the two response-level skill-dimension
        coverage counters (``skill_attributed_key_count``/
        ``skill_unattributed_key_count``) via ``_skill_dimension_coverage``
        -- scoped to the SAME resolved ``min_sample_size`` used by
        ``compute_metrics``'s ``eligible_for_adjustment`` gate, computed over
        *rows* directly (not *coverage*, which is keyed off already-resolved
        ``task_class`` and has no notion of sample-size thresholds).
        """
        resolved_min_sample_size = (
            min_sample_size
            if min_sample_size is not None
            else config.CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE
        )
        resolved_freshness_ts = freshness_ts if freshness_ts is not None else _now_iso()
        key_dtos = self.compute_metrics(
            rows,
            min_sample_size=resolved_min_sample_size,
            freshness_ts=resolved_freshness_ts,
        )
        skill_attributed_key_count, skill_unattributed_key_count = _skill_dimension_coverage(
            rows, resolved_min_sample_size
        )
        return RoutingRollupResponseDTO(
            enabled=True,
            generated_at=resolved_freshness_ts,
            contract_id=routing_feedback_contract.CONTRACT_ID,
            contract_version=routing_feedback_contract.CONTRACT_VERSION,
            taxonomy_id=routing_feedback_contract.TAXONOMY_ID,
            taxonomy_version=routing_feedback_contract.TAXONOMY_VERSION,
            taxonomy_digest=routing_feedback_contract.TAXONOMY_DIGEST,
            mapping_id=routing_feedback_contract.MAPPING_ID,
            mapping_version=routing_feedback_contract.MAPPING_VERSION,
            mapping_digest=routing_feedback_contract.MAPPING_DIGEST,
            mapped_count=coverage.mapped_count,
            unclassified_count=coverage.unclassified_count,
            distinct_unmapped_skill_names=list(coverage.distinct_unmapped_skill_names),
            skill_attributed_key_count=skill_attributed_key_count,
            skill_unattributed_key_count=skill_unattributed_key_count,
            keys=key_dtos,
        )


__all__ = [
    "PROTECTED_TASK_CLASSES",
    "UNCLASSIFIED_TASK_CLASS",
    "CoverageCounters",
    "MappedRollupRow",
    "ProviderRollupRow",
    "RawRollupRow",
    "RoutingRollupQueryService",
]
