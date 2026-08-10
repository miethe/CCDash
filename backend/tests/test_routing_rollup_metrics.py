"""Unit tests for T3-004: ``RoutingRollupQueryService.compute_metrics`` and
``build_response`` -- the D5 metric payload (``sample_count``,
``success_rate``, ``cost_index``, ``regression_rate``, ``confidence``,
``eligible_for_adjustment``, ``window_start``/``window_end``,
``freshness_ts``) plus ``RoutingRollupKeyDTO``/``RoutingRollupResponseDTO``
assembly.

Covers this task's own acceptance criteria (see
``docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1/phase-3-rollup-compute-service.md``,
Task T3-004):

  - Every key in a multi-key fixture carries the full 11-field pinned join
    envelope plus every D5 metric field, verified field-by-field against the
    PRD Sec.6.3 JSON example (contract/taxonomy/mapping identity pulled from
    ``routing_feedback_contract.py`` directly, never hardcoded duplicate
    literals -- drift-proof by construction).
  - A fixture key with ``sample_count=1`` (below the default
    ``MIN_SAMPLE_SIZE=5``) still appears in ``keys[]`` with
    ``eligible_for_adjustment=False`` -- sub-threshold keys are never
    suppressed.
  - Coverage-only rows (``_unclassified``/protected-class,
    ``is_coverage_only=True``) are hardcoded ``eligible_for_adjustment=False``
    independent of ``sample_count`` magnitude (T3-002's hard contract).
  - ``confidence``'s saturating formula is monotonically increasing, never
    exceeds ``1.0``, and is exactly ``0.0`` at ``sample_count == 0``.
  - ``cost_index`` is the fixed PRD-literal baseline (``1.0``) for every row.
    ``success_rate``/``regression_rate`` are ``None`` for every row (no
    genuine per-session outcome signal exists yet -- named v1 design gap).

The ``RoutingRollupKeyDTO``/``RoutingRollupResponseDTO`` plain-``BaseModel``
(not ``AgentQueryEnvelope``) MRO check is T3-005's responsibility, per the
phase file's own AC routing (``test_routing_rollup_determinism.py``) --
deliberately not duplicated here.

Run as a named module (full collection can hang -- see
``docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md`` and
the repo-wide pytest-collection caveat):
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_metrics.py -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest import mock

from backend import config
from backend.application.services.agent_queries import routing_feedback_contract
from backend.application.services.agent_queries.models import (
    RoutingRollupKeyDTO,
    RoutingRollupResponseDTO,
)
from backend.application.services.agent_queries.routing_rollup import (
    UNCLASSIFIED_TASK_CLASS,
    CoverageCounters,
    ProviderRollupRow,
    RoutingRollupQueryService,
)


_FIXED_WINDOW_START = datetime(2026, 6, 29, tzinfo=timezone.utc)
_FIXED_WINDOW_END = datetime(2026, 7, 29, tzinfo=timezone.utc)
_FIXED_FRESHNESS_TS = "2026-07-29T02:00:00+00:00"


def _provider_row(
    *,
    task_class: str = "implementation",
    is_coverage_only: bool = False,
    session_count: int = 68,
    source_skill_name: str = "dev-execution",
    model: str = "claude-sonnet-5",
    project_id: str = "proj-1",
    provider: str | None = None,
    window_start: datetime = _FIXED_WINDOW_START,
    window_end: datetime = _FIXED_WINDOW_END,
    cost_sum: float = 0.0,
    cost_covered_count: int = 0,
    tool_call_sum: int = 0,
    tool_success_sum: int = 0,
    tool_usage_covered_count: int = 0,
) -> ProviderRollupRow:
    return ProviderRollupRow(
        project_id=project_id,
        source_skill_name=source_skill_name,
        model=model,
        session_count=session_count,
        window_start=window_start,
        window_end=window_end,
        task_class=task_class,
        is_coverage_only=is_coverage_only,
        provider=provider if provider is not None else "anthropic",
        cost_sum=cost_sum,
        cost_covered_count=cost_covered_count,
        tool_call_sum=tool_call_sum,
        tool_success_sum=tool_success_sum,
        tool_usage_covered_count=tool_usage_covered_count,
    )


class _ServiceTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RoutingRollupQueryService()


# ---------------------------------------------------------------------------
# AC: full envelope + D5 metric field presence, verified field-by-field
# against the PRD Sec.6.3 JSON example.
# ---------------------------------------------------------------------------


class TestComputeMetricsEnvelopeCompleteness(_ServiceTestBase):
    def test_key_dto_carries_full_pinned_envelope_and_d5_payload(self) -> None:
        row = _provider_row(
            task_class="implementation",
            is_coverage_only=False,
            session_count=68,
            source_skill_name="dev-execution",
            model="claude-sonnet-5",
            provider="anthropic",
        )

        [dto] = self.service.compute_metrics(
            [row], min_sample_size=5, freshness_ts=_FIXED_FRESHNESS_TS
        )

        self.assertIsInstance(dto, RoutingRollupKeyDTO)
        # 11-field pinned join envelope -- pulled from the contract module,
        # never hardcoded duplicate literals.
        self.assertEqual(dto.producer, routing_feedback_contract.PRODUCER)
        self.assertEqual(dto.contract_id, routing_feedback_contract.CONTRACT_ID)
        self.assertEqual(dto.contract_version, routing_feedback_contract.CONTRACT_VERSION)
        self.assertEqual(dto.taxonomy_id, routing_feedback_contract.TAXONOMY_ID)
        self.assertEqual(dto.taxonomy_version, routing_feedback_contract.TAXONOMY_VERSION)
        self.assertEqual(dto.taxonomy_digest, routing_feedback_contract.TAXONOMY_DIGEST)
        self.assertEqual(dto.mapping_id, routing_feedback_contract.MAPPING_ID)
        self.assertEqual(dto.mapping_version, routing_feedback_contract.MAPPING_VERSION)
        self.assertEqual(dto.mapping_digest, routing_feedback_contract.MAPPING_DIGEST)
        self.assertEqual(dto.source_skill_name, "dev-execution")
        self.assertEqual(dto.task_class, "implementation")
        # D5 metric payload.
        self.assertEqual(dto.model, "claude-sonnet-5")
        self.assertEqual(dto.provider, "anthropic")
        self.assertEqual(dto.sample_count, 68)
        self.assertIsNone(dto.success_rate)
        # Zero cost attribution on this fixture row (no cost_sum/
        # cost_covered_count set) -- DI-4a: never a fabricated 1.0.
        self.assertIsNone(dto.cost_index)
        self.assertEqual(dto.cost_coverage_fraction, 0.0)
        self.assertIsNone(dto.regression_rate)
        self.assertGreater(dto.confidence, 0.0)
        self.assertLessEqual(dto.confidence, 1.0)
        self.assertTrue(dto.eligible_for_adjustment)  # 68 >= 5
        self.assertEqual(dto.window_start, _FIXED_WINDOW_START.isoformat())
        self.assertEqual(dto.window_end, _FIXED_WINDOW_END.isoformat())
        self.assertEqual(dto.freshness_ts, _FIXED_FRESHNESS_TS)

    def test_multi_key_fixture_produces_one_dto_per_row_never_collapsed(self) -> None:
        rows = [
            _provider_row(source_skill_name="dev-execution", model="claude-sonnet-5", session_count=68),
            _provider_row(source_skill_name="debugging", model="claude-sonnet-5", session_count=12),
            _provider_row(source_skill_name="dev-execution", model="gpt-5.6-terra", session_count=4),
        ]

        dtos = self.service.compute_metrics(rows, freshness_ts=_FIXED_FRESHNESS_TS)

        self.assertEqual(len(dtos), 3)
        keys = {(dto.source_skill_name, dto.model) for dto in dtos}
        self.assertEqual(
            keys,
            {
                ("dev-execution", "claude-sonnet-5"),
                ("debugging", "claude-sonnet-5"),
                ("dev-execution", "gpt-5.6-terra"),
            },
        )


# ---------------------------------------------------------------------------
# AC: sub-threshold keys are never suppressed; eligible_for_adjustment
# reflects the sample-size threshold for ordinary rows.
# ---------------------------------------------------------------------------


class TestEligibleForAdjustmentThreshold(_ServiceTestBase):
    def test_sub_threshold_key_still_present_with_eligible_false(self) -> None:
        row = _provider_row(session_count=1, is_coverage_only=False)

        dtos = self.service.compute_metrics([row], min_sample_size=5)

        self.assertEqual(len(dtos), 1)
        self.assertEqual(dtos[0].sample_count, 1)
        self.assertFalse(dtos[0].eligible_for_adjustment)

    def test_boundary_below_and_at_threshold(self) -> None:
        below = _provider_row(session_count=4, is_coverage_only=False)
        at = _provider_row(session_count=5, is_coverage_only=False)

        [below_dto, at_dto] = self.service.compute_metrics([below, at], min_sample_size=5)

        self.assertFalse(below_dto.eligible_for_adjustment)
        self.assertTrue(at_dto.eligible_for_adjustment)

    def test_min_sample_size_kwarg_overrides_config_default(self) -> None:
        row = _provider_row(session_count=10, is_coverage_only=False)

        dtos_strict = self.service.compute_metrics([row], min_sample_size=20)
        dtos_lenient = self.service.compute_metrics([row], min_sample_size=1)

        self.assertFalse(dtos_strict[0].eligible_for_adjustment)
        self.assertTrue(dtos_lenient[0].eligible_for_adjustment)

    def test_min_sample_size_defaults_to_config_value(self) -> None:
        row = _provider_row(session_count=config.CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE, is_coverage_only=False)

        [dto] = self.service.compute_metrics([row])

        self.assertTrue(dto.eligible_for_adjustment)


# ---------------------------------------------------------------------------
# AC: coverage-only rows are hardcoded eligible_for_adjustment=False,
# independent of T3-004's own sample-size threshold logic.
# ---------------------------------------------------------------------------


class TestCoverageOnlyRowsHardcodedIneligible(_ServiceTestBase):
    def test_unclassified_row_with_large_sample_count_still_ineligible(self) -> None:
        row = _provider_row(
            task_class=UNCLASSIFIED_TASK_CLASS,
            is_coverage_only=True,
            session_count=50_000,
            source_skill_name="codex",
        )

        [dto] = self.service.compute_metrics([row], min_sample_size=5)

        self.assertFalse(dto.eligible_for_adjustment)
        self.assertEqual(dto.task_class, UNCLASSIFIED_TASK_CLASS)
        self.assertEqual(dto.sample_count, 50_000)

    def test_protected_class_row_with_large_sample_count_still_ineligible(self) -> None:
        row = _provider_row(
            task_class="orchestration",
            is_coverage_only=True,
            session_count=99_999,
            source_skill_name="planning",
        )

        [dto] = self.service.compute_metrics([row], min_sample_size=5)

        self.assertFalse(dto.eligible_for_adjustment)
        self.assertEqual(dto.task_class, "orchestration")


# ---------------------------------------------------------------------------
# AC: confidence is a monotonically-increasing, asymptotic-to-1.0 function
# of sample_count.
# ---------------------------------------------------------------------------


class TestConfidenceSaturationCurve(_ServiceTestBase):
    def test_confidence_zero_at_zero_sample_count(self) -> None:
        row = _provider_row(session_count=0)

        [dto] = self.service.compute_metrics([row])

        self.assertEqual(dto.confidence, 0.0)

    def test_confidence_monotonically_increasing_with_sample_count(self) -> None:
        rows = [_provider_row(session_count=n) for n in (1, 5, 20, 100, 1000)]

        dtos = self.service.compute_metrics(rows)
        confidences = [dto.confidence for dto in dtos]

        self.assertEqual(confidences, sorted(confidences))
        for value in confidences:
            self.assertLessEqual(value, 1.0)

    def test_confidence_never_exceeds_one(self) -> None:
        row = _provider_row(session_count=10_000_000)

        [dto] = self.service.compute_metrics([row])

        self.assertLessEqual(dto.confidence, 1.0)


# ---------------------------------------------------------------------------
# AC4: regression_rate remains None permanently (DI-4b closed, no
# test_results/test_runs signal exists) -- a decided non-goal, never
# revisited by this task, unlike success_rate below.
# ---------------------------------------------------------------------------


class TestRegressionRatePermanentlyNone(_ServiceTestBase):
    def test_regression_rate_is_none_for_every_row_regardless_of_tool_usage(self) -> None:
        rows = [
            _provider_row(
                is_coverage_only=False,
                session_count=68,
                tool_call_sum=100,
                tool_success_sum=90,
                tool_usage_covered_count=68,
            ),
            _provider_row(task_class=UNCLASSIFIED_TASK_CLASS, is_coverage_only=True, session_count=3),
        ]

        dtos = self.service.compute_metrics(rows)

        for dto in dtos:
            self.assertIsNone(dto.regression_rate)


# ---------------------------------------------------------------------------
# AC1/AC2/D-b1/D-b2: DI-4e real per-key success_rate -- call-volume-weighted
# tool-error-rate complement (D-b1), null on zero attribution (D-b2), plus
# its coverage-fraction companion.
# ---------------------------------------------------------------------------


class TestSuccessRateZeroCoverage(_ServiceTestBase):
    """D-b2: a key with zero tool-usage-attributed sessions emits
    success_rate=None, never a fabricated constant."""

    def test_zero_coverage_key_emits_none_never_a_placeholder(self) -> None:
        row = _provider_row(
            session_count=68, tool_call_sum=0, tool_success_sum=0, tool_usage_covered_count=0
        )

        [dto] = self.service.compute_metrics([row])

        self.assertIsNone(dto.success_rate)
        self.assertNotEqual(dto.success_rate, 1.0)
        self.assertNotEqual(dto.success_rate, 0.0)
        self.assertEqual(dto.success_rate_coverage_fraction, 0.0)


class TestSuccessRateFullCoverage(_ServiceTestBase):
    """A fully-covered key emits a real, non-constant success_rate that
    changes when the underlying call/error inputs change (provably derived,
    not a disguised constant)."""

    def test_full_coverage_key_computes_real_rate(self) -> None:
        row = _provider_row(
            session_count=10,
            tool_call_sum=100,
            tool_success_sum=95,
            tool_usage_covered_count=10,
        )

        [dto] = self.service.compute_metrics([row])

        self.assertAlmostEqual(dto.success_rate, 0.95)
        self.assertEqual(dto.success_rate_coverage_fraction, 1.0)

    def test_success_rate_changes_when_underlying_call_error_inputs_change(self) -> None:
        reliable = _provider_row(
            source_skill_name="reliable-skill",
            session_count=10,
            tool_call_sum=100,
            tool_success_sum=99,
            tool_usage_covered_count=10,
        )
        flaky = _provider_row(
            source_skill_name="flaky-skill",
            session_count=10,
            tool_call_sum=100,
            tool_success_sum=60,
            tool_usage_covered_count=10,
        )

        dtos = self.service.compute_metrics([reliable, flaky])
        by_skill = {dto.source_skill_name: dto for dto in dtos}

        self.assertAlmostEqual(by_skill["reliable-skill"].success_rate, 0.99)
        self.assertAlmostEqual(by_skill["flaky-skill"].success_rate, 0.60)
        self.assertNotEqual(
            by_skill["reliable-skill"].success_rate, by_skill["flaky-skill"].success_rate
        )


class TestSuccessRatePartialCoverage(_ServiceTestBase):
    """A partially-covered key's success_rate is computed over the covered
    subset only, and its coverage-fraction signal differs from a
    fully-covered key's."""

    def test_partial_coverage_computed_over_covered_subset_only(self) -> None:
        partial = _provider_row(
            source_skill_name="partial-skill",
            session_count=50,
            tool_call_sum=100,
            tool_success_sum=90,
            tool_usage_covered_count=2,
        )
        full = _provider_row(
            source_skill_name="full-skill",
            session_count=10,
            tool_call_sum=100,
            tool_success_sum=90,
            tool_usage_covered_count=10,
        )

        dtos = self.service.compute_metrics([partial, full])
        by_skill = {dto.source_skill_name: dto for dto in dtos}

        # Identical tool_call_sum/tool_success_sum -> identical success_rate,
        # regardless of how many uncovered sessions dilute session_count.
        self.assertAlmostEqual(by_skill["partial-skill"].success_rate, by_skill["full-skill"].success_rate)

    def test_partial_coverage_fraction_differs_from_full_coverage(self) -> None:
        partial = _provider_row(
            source_skill_name="partial-skill",
            session_count=50,
            tool_call_sum=100,
            tool_success_sum=90,
            tool_usage_covered_count=2,
        )
        full = _provider_row(
            source_skill_name="full-skill",
            session_count=10,
            tool_call_sum=100,
            tool_success_sum=90,
            tool_usage_covered_count=10,
        )

        dtos = self.service.compute_metrics([partial, full])
        by_skill = {dto.source_skill_name: dto for dto in dtos}

        self.assertAlmostEqual(by_skill["partial-skill"].success_rate_coverage_fraction, 2 / 50)
        self.assertEqual(by_skill["full-skill"].success_rate_coverage_fraction, 1.0)
        self.assertNotEqual(
            by_skill["partial-skill"].success_rate_coverage_fraction,
            by_skill["full-skill"].success_rate_coverage_fraction,
        )


class TestSuccessRateCallVolumeWeighted(_ServiceTestBase):
    """D-b1: success_rate is call-volume-weighted (sum of errors over sum of
    calls) across the key's covered sessions -- never a mean-of-per-session
    error rates. Synthetic case where the two methods provably disagree: one
    200-call session with 1 error (0.5% error rate) and one 2-call session
    with 1 error (50% error rate) -- a per-session mean would average those
    two rates to 25.25% error (74.75% success); the call-volume-weighted
    answer pools 2 errors over 202 calls = ~0.99% error (~99.01% success)."""

    def test_call_volume_weighted_not_mean_of_per_session_rates(self) -> None:
        # This module aggregates at the (project_id, source_skill_name,
        # model) key grain, not per-session -- so this fixture represents
        # the KEY's already-summed tool_call_sum/tool_success_sum, as if
        # the SQL aggregate had already pooled the two sessions' raw
        # session_tool_usage rows (200+2=202 calls, (200-1)+(2-1)=200
        # successes).
        row = _provider_row(session_count=2, tool_call_sum=202, tool_success_sum=200, tool_usage_covered_count=2)

        [dto] = self.service.compute_metrics([row])

        call_volume_weighted_success_rate = 200 / 202
        per_session_mean_success_rate = ((199 / 200) + (1 / 2)) / 2  # would be ~0.7475

        self.assertAlmostEqual(dto.success_rate, call_volume_weighted_success_rate)
        self.assertNotAlmostEqual(dto.success_rate, per_session_mean_success_rate, places=2)


class TestSuccessRateDeterminism(_ServiceTestBase):
    """Two invocations over a frozen fixture row-set produce field-identical
    success_rate/coverage output."""

    def test_two_invocations_produce_identical_success_rate_and_coverage(self) -> None:
        rows = [
            _provider_row(
                source_skill_name="dev-execution",
                session_count=68,
                tool_call_sum=340,
                tool_success_sum=330,
                tool_usage_covered_count=60,
            ),
            _provider_row(
                source_skill_name="debugging",
                session_count=12,
                tool_call_sum=0,
                tool_success_sum=0,
                tool_usage_covered_count=0,
            ),
        ]

        dtos_first = self.service.compute_metrics(rows, freshness_ts=_FIXED_FRESHNESS_TS)
        dtos_second = self.service.compute_metrics(rows, freshness_ts=_FIXED_FRESHNESS_TS)

        first_pairs = [(dto.success_rate, dto.success_rate_coverage_fraction) for dto in dtos_first]
        second_pairs = [(dto.success_rate, dto.success_rate_coverage_fraction) for dto in dtos_second]
        self.assertEqual(first_pairs, second_pairs)


# ---------------------------------------------------------------------------
# AC3/D-b3: skill-dimension coverage counters -- response-level, scoped to
# the min_sample_size-clearing population.
# ---------------------------------------------------------------------------


class TestSkillDimensionCoverageCounters(_ServiceTestBase):
    def test_attributed_and_unattributed_counts_over_eligible_population(self) -> None:
        rows = [
            # Clears min_sample_size=5, non-empty source_skill_name -> attributed.
            _provider_row(source_skill_name="dev-execution", session_count=68),
            # Clears min_sample_size=5, empty source_skill_name -> unattributed.
            _provider_row(source_skill_name="", session_count=20, task_class=UNCLASSIFIED_TASK_CLASS, is_coverage_only=True),
            # Below min_sample_size=5 -- excluded from BOTH counters, regardless
            # of source_skill_name.
            _provider_row(source_skill_name="dev-execution", session_count=2),
            _provider_row(source_skill_name="", session_count=1, task_class=UNCLASSIFIED_TASK_CLASS, is_coverage_only=True),
        ]
        coverage = CoverageCounters(mapped_count=70, unclassified_count=21, distinct_unmapped_skill_names=[""])

        response = self.service.build_response(rows, coverage, min_sample_size=5)

        self.assertEqual(response.skill_attributed_key_count, 1)
        self.assertEqual(response.skill_unattributed_key_count, 1)


# ---------------------------------------------------------------------------
# AC: DI-4a real per-key cost_index (feature contract
# routing-feedback-cost-index-v1.md) -- D-a1 baseline, D-a2 zero-coverage
# null, D-a3 partial-coverage + coverage-fraction signal, D-a4 outlier
# reliance on the existing min_sample_size gate.
# ---------------------------------------------------------------------------


class TestCostIndexZeroCoverage(_ServiceTestBase):
    """D-a2: a key with zero cost-attributed sessions emits cost_index=None,
    never a fabricated placeholder."""

    def test_zero_coverage_key_emits_none_never_a_placeholder(self) -> None:
        row = _provider_row(session_count=68, cost_sum=0.0, cost_covered_count=0)

        [dto] = self.service.compute_metrics([row])

        self.assertIsNone(dto.cost_index)
        self.assertNotEqual(dto.cost_index, 1.0)
        self.assertNotEqual(dto.cost_index, 0.0)
        self.assertEqual(dto.cost_coverage_fraction, 0.0)

    def test_entire_task_class_with_no_covered_sessions_emits_none(self) -> None:
        """Even a row with SOME nominal cost data emits None if its whole
        task_class's baseline cannot be established (defensive: this
        fixture keeps the row itself uncovered too, since a covered row
        with an uncovered class is impossible by construction -- the row's
        own coverage always contributes to its class's baseline)."""
        rows = [
            _provider_row(task_class="mechanical", session_count=10, cost_sum=0.0, cost_covered_count=0),
            _provider_row(
                task_class="mechanical",
                source_skill_name="other-skill",
                session_count=5,
                cost_sum=0.0,
                cost_covered_count=0,
            ),
        ]

        dtos = self.service.compute_metrics(rows)

        for dto in dtos:
            self.assertIsNone(dto.cost_index)


class TestCostIndexFullCoverage(_ServiceTestBase):
    """A fully-covered key emits a real, non-constant cost_index that
    changes when the underlying per-session cost inputs change."""

    def test_full_coverage_key_at_class_baseline_reads_one(self) -> None:
        row = _provider_row(session_count=10, cost_sum=100.0, cost_covered_count=10)

        [dto] = self.service.compute_metrics([row])

        # Sole row in its task_class -- its own mean IS the class baseline.
        self.assertAlmostEqual(dto.cost_index, 1.0)
        self.assertEqual(dto.cost_coverage_fraction, 1.0)

    def test_cost_index_changes_when_underlying_cost_input_changes(self) -> None:
        cheap = _provider_row(
            task_class="implementation", source_skill_name="cheap-skill",
            session_count=10, cost_sum=10.0, cost_covered_count=10,
        )
        expensive = _provider_row(
            task_class="implementation", source_skill_name="expensive-skill",
            session_count=10, cost_sum=90.0, cost_covered_count=10,
        )

        dtos = self.service.compute_metrics([cheap, expensive])
        by_skill = {dto.source_skill_name: dto for dto in dtos}

        # class baseline = (10 + 90) / (10 + 10) = 5.0 per covered session
        self.assertAlmostEqual(by_skill["cheap-skill"].cost_index, 1.0 / 5.0)
        self.assertAlmostEqual(by_skill["expensive-skill"].cost_index, 9.0 / 5.0)
        self.assertNotEqual(
            by_skill["cheap-skill"].cost_index, by_skill["expensive-skill"].cost_index
        )

    def test_cost_index_is_not_a_disguised_constant_across_varying_inputs(self) -> None:
        rows = [
            _provider_row(
                task_class="implementation", source_skill_name=f"skill-{n}",
                session_count=10, cost_sum=float(n) * 10.0, cost_covered_count=10,
            )
            for n in (1, 2, 3, 4)
        ]

        dtos = self.service.compute_metrics(rows)
        cost_indices = {dto.cost_index for dto in dtos}

        self.assertEqual(len(cost_indices), 4, "distinct cost inputs must produce distinct cost_index values")


class TestCostIndexPartialCoverage(_ServiceTestBase):
    """D-a3: a partially-covered key's cost_index is computed over the
    covered subset only, and its coverage-fraction signal differs from a
    fully-covered key with the same nominal per-covered-session cost."""

    def test_partial_coverage_key_computes_over_covered_subset_only(self) -> None:
        # 2 of 50 sessions carry cost data, summing to 20.0 -> mean 10.0.
        partial = _provider_row(
            task_class="implementation", source_skill_name="partial-skill",
            session_count=50, cost_sum=20.0, cost_covered_count=2,
        )
        full = _provider_row(
            task_class="implementation", source_skill_name="full-skill",
            session_count=10, cost_sum=100.0, cost_covered_count=10,
        )

        dtos = self.service.compute_metrics([partial, full])
        by_skill = {dto.source_skill_name: dto for dto in dtos}

        # Both keys have an identical mean cost-per-covered-session (10.0),
        # so their cost_index values are equal -- proving the partial key's
        # index was computed over its 2 covered sessions, not diluted by
        # its 48 uncovered ones (which would drag the mean toward 0.4).
        self.assertAlmostEqual(by_skill["partial-skill"].cost_index, by_skill["full-skill"].cost_index)

    def test_partial_coverage_fraction_differs_from_full_coverage(self) -> None:
        partial = _provider_row(
            task_class="implementation", source_skill_name="partial-skill",
            session_count=50, cost_sum=20.0, cost_covered_count=2,
        )
        full = _provider_row(
            task_class="implementation", source_skill_name="full-skill",
            session_count=10, cost_sum=100.0, cost_covered_count=10,
        )

        dtos = self.service.compute_metrics([partial, full])
        by_skill = {dto.source_skill_name: dto for dto in dtos}

        self.assertAlmostEqual(by_skill["partial-skill"].cost_coverage_fraction, 2 / 50)
        self.assertEqual(by_skill["full-skill"].cost_coverage_fraction, 1.0)
        self.assertNotEqual(
            by_skill["partial-skill"].cost_coverage_fraction,
            by_skill["full-skill"].cost_coverage_fraction,
        )


class TestCostIndexBaselineIsPerTaskClass(_ServiceTestBase):
    """D-a1: the baseline is a per-task_class mean, not a single global
    mean -- two keys in different task_class buckets with different
    absolute costs but the same RELATIVE standing within their own bucket
    must produce the same relative cost_index, never a cross-class-skewed
    one."""

    def test_same_relative_standing_within_bucket_yields_equal_cost_index(self) -> None:
        # "orchestration" bucket: baseline mean = (200 + 600) / 2 = 400.
        # "mechanical" bucket:    baseline mean = (20 + 60) / 2 = 40.
        # Both "cheap" keys sit at 0.5x their own bucket's baseline; both
        # "pricey" keys sit at 1.5x their own bucket's baseline -- despite
        # the orchestration bucket being an order of magnitude more
        # expensive in absolute terms.
        rows = [
            _provider_row(
                task_class="orchestration", source_skill_name="orchestration-cheap",
                session_count=1, cost_sum=200.0, cost_covered_count=1,
            ),
            _provider_row(
                task_class="orchestration", source_skill_name="orchestration-pricey",
                session_count=1, cost_sum=600.0, cost_covered_count=1,
            ),
            _provider_row(
                task_class="mechanical", source_skill_name="mechanical-cheap",
                session_count=1, cost_sum=20.0, cost_covered_count=1,
            ),
            _provider_row(
                task_class="mechanical", source_skill_name="mechanical-pricey",
                session_count=1, cost_sum=60.0, cost_covered_count=1,
            ),
        ]

        dtos = self.service.compute_metrics(rows)
        by_skill = {dto.source_skill_name: dto for dto in dtos}

        self.assertAlmostEqual(
            by_skill["orchestration-cheap"].cost_index, by_skill["mechanical-cheap"].cost_index
        )
        self.assertAlmostEqual(
            by_skill["orchestration-pricey"].cost_index, by_skill["mechanical-pricey"].cost_index
        )
        self.assertAlmostEqual(by_skill["orchestration-cheap"].cost_index, 0.5)
        self.assertAlmostEqual(by_skill["orchestration-pricey"].cost_index, 1.5)

    def test_global_mean_would_have_skewed_but_per_class_mean_does_not(self) -> None:
        """A single global mean across both buckets would flag the cheap
        mechanical key as far-below-baseline and the pricey orchestration
        key as far-above -- proving this is NOT what the implementation
        does; the per-class mean instead keeps each key's index anchored
        to its own class."""
        rows = [
            _provider_row(
                task_class="orchestration", source_skill_name="orchestration-key",
                session_count=1, cost_sum=500.0, cost_covered_count=1,
            ),
            _provider_row(
                task_class="mechanical", source_skill_name="mechanical-key",
                session_count=1, cost_sum=5.0, cost_covered_count=1,
            ),
        ]

        dtos = self.service.compute_metrics(rows)
        by_skill = {dto.source_skill_name: dto for dto in dtos}

        # Each key is the SOLE row in its own class, so its class baseline
        # IS its own mean -- cost_index must read exactly 1.0 for both,
        # never skewed by the other class's wildly different absolute cost.
        self.assertAlmostEqual(by_skill["orchestration-key"].cost_index, 1.0)
        self.assertAlmostEqual(by_skill["mechanical-key"].cost_index, 1.0)


class TestCostIndexOutlierHandling(_ServiceTestBase):
    """D-a4: no separate outlier-suppression logic in cost_index itself --
    a low-sample key with one dominant high-cost session produces the
    "overstated" index its raw mean implies, and reliance on the existing
    min_sample_size/eligible_for_adjustment gate is the documented,
    deliberate mitigation (not a bug)."""

    def test_low_sample_dominant_outlier_produces_overstated_index_but_is_ineligible(self) -> None:
        # 1 session of the 2 in this key's covered subset costs 990 of the
        # 1000 total -- a dominant outlier. No winsorization/trimmed-mean
        # logic suppresses this; the raw mean is used as-is.
        outlier_row = _provider_row(
            task_class="implementation", source_skill_name="low-sample-outlier",
            session_count=2, cost_sum=1000.0, cost_covered_count=2,
        )
        baseline_row = _provider_row(
            task_class="implementation", source_skill_name="steady-baseline",
            session_count=100, cost_sum=1000.0, cost_covered_count=100,
        )

        dtos = self.service.compute_metrics([outlier_row, baseline_row], min_sample_size=5)
        by_skill = {dto.source_skill_name: dto for dto in dtos}

        outlier_dto = by_skill["low-sample-outlier"]
        # class baseline = (1000 + 1000) / (2 + 100) = ~19.6 per session
        # outlier key's own mean = 1000 / 2 = 500 -> heavily overstated
        # relative to the class baseline -- no suppression applied.
        self.assertGreater(outlier_dto.cost_index, 10.0)
        # But the existing sample-size gate already excludes it from
        # adjustment -- the documented mitigation for exactly this case.
        self.assertFalse(outlier_dto.eligible_for_adjustment)


# ---------------------------------------------------------------------------
# AC: freshness_ts defaults to _now_iso() and is shared identically across
# every row in one call; overridable for deterministic test fixtures.
# ---------------------------------------------------------------------------


class TestFreshnessTimestamp(_ServiceTestBase):
    def test_freshness_ts_override_applies_to_every_row(self) -> None:
        rows = [_provider_row(session_count=n) for n in (1, 2, 3)]

        dtos = self.service.compute_metrics(rows, freshness_ts=_FIXED_FRESHNESS_TS)

        for dto in dtos:
            self.assertEqual(dto.freshness_ts, _FIXED_FRESHNESS_TS)

    def test_freshness_ts_defaults_to_now_iso_when_omitted(self) -> None:
        row = _provider_row(session_count=5)
        sentinel = "2099-01-01T00:00:00+00:00"

        with mock.patch(
            "backend.application.services.agent_queries.routing_rollup._now_iso",
            return_value=sentinel,
        ):
            [dto] = self.service.compute_metrics([row])

        self.assertEqual(dto.freshness_ts, sentinel)


# ---------------------------------------------------------------------------
# AC: build_response assembles the full top-level envelope from
# compute_metrics + T3-003's coverage counters.
# ---------------------------------------------------------------------------


class TestBuildResponse(_ServiceTestBase):
    def test_build_response_assembles_full_envelope(self) -> None:
        rows = [
            _provider_row(source_skill_name="dev-execution", model="claude-sonnet-5", session_count=68),
            _provider_row(
                task_class=UNCLASSIFIED_TASK_CLASS,
                is_coverage_only=True,
                source_skill_name="codex",
                session_count=17,
            ),
        ]
        coverage = CoverageCounters(
            mapped_count=68,
            unclassified_count=17,
            distinct_unmapped_skill_names=["codex"],
        )

        response = self.service.build_response(rows, coverage, freshness_ts=_FIXED_FRESHNESS_TS)

        self.assertIsInstance(response, RoutingRollupResponseDTO)
        self.assertTrue(response.enabled)
        self.assertEqual(response.generated_at, _FIXED_FRESHNESS_TS)
        self.assertEqual(response.contract_id, routing_feedback_contract.CONTRACT_ID)
        self.assertEqual(response.contract_version, routing_feedback_contract.CONTRACT_VERSION)
        self.assertEqual(response.taxonomy_id, routing_feedback_contract.TAXONOMY_ID)
        self.assertEqual(response.taxonomy_version, routing_feedback_contract.TAXONOMY_VERSION)
        self.assertEqual(response.taxonomy_digest, routing_feedback_contract.TAXONOMY_DIGEST)
        self.assertEqual(response.mapping_id, routing_feedback_contract.MAPPING_ID)
        self.assertEqual(response.mapping_version, routing_feedback_contract.MAPPING_VERSION)
        self.assertEqual(response.mapping_digest, routing_feedback_contract.MAPPING_DIGEST)
        self.assertEqual(response.mapped_count, 68)
        self.assertEqual(response.unclassified_count, 17)
        self.assertEqual(response.distinct_unmapped_skill_names, ["codex"])
        self.assertEqual(len(response.keys), 2)

    def test_build_response_never_suppresses_any_input_row(self) -> None:
        rows = [_provider_row(session_count=n, source_skill_name=f"skill-{n}") for n in (1, 2, 3, 4, 5, 6)]
        coverage = CoverageCounters(mapped_count=21, unclassified_count=0, distinct_unmapped_skill_names=[])

        response = self.service.build_response(rows, coverage)

        self.assertEqual(len(response.keys), len(rows))


if __name__ == "__main__":
    unittest.main()
