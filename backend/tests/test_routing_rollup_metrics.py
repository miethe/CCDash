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
        self.assertEqual(dto.cost_index, 1.0)
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
# AC: cost_index / success_rate / regression_rate v1 design-gap values.
# ---------------------------------------------------------------------------


class TestCostIndexAndUnavailableSignals(_ServiceTestBase):
    def test_cost_index_is_fixed_baseline_for_every_row(self) -> None:
        rows = [
            _provider_row(model="claude-sonnet-5", session_count=1),
            _provider_row(model="gpt-5.6-terra", session_count=500),
            _provider_row(task_class=UNCLASSIFIED_TASK_CLASS, is_coverage_only=True, session_count=9),
        ]

        dtos = self.service.compute_metrics(rows)

        for dto in dtos:
            self.assertEqual(dto.cost_index, 1.0)

    def test_success_rate_and_regression_rate_are_none_for_every_row(self) -> None:
        rows = [
            _provider_row(is_coverage_only=False, session_count=68),
            _provider_row(task_class=UNCLASSIFIED_TASK_CLASS, is_coverage_only=True, session_count=3),
        ]

        dtos = self.service.compute_metrics(rows)

        for dto in dtos:
            self.assertIsNone(dto.success_rate)
            self.assertIsNone(dto.regression_rate)


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
