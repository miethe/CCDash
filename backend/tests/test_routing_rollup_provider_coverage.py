"""Unit tests for T3-003: ``RoutingRollupQueryService.apply_provider`` and
``compute_coverage_counters`` -- derived ``provider`` field + the three FR-7
response-level coverage counters (``mapped_count``, ``unclassified_count``,
``distinct_unmapped_skill_names``).

Covers this task's own acceptance criteria (see
``docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1/phase-3-rollup-compute-service.md``,
Task T3-003):

  - ``mapped_count`` (rows with ``task_class != "_unclassified"``) and
    ``unclassified_count`` (rows with ``task_class == "_unclassified"``) each
    independently match a hand-computed value against a fixture --
    session-level totals (summed ``session_count``), not per-key sums.
  - ``mapped_count + unclassified_count == total_rows`` holds exactly against
    a fixture that includes ``codex``, ``claude-api``, and ``ica-delegate``
    as skill names WITH mapping entries that resolve to
    ``task_class == "_unclassified"`` (executor-identity names, not "no
    entry found") -- proves the counters never double-count a row that has
    both a mapping entry AND an ``_unclassified`` resolution.
  - ``distinct_unmapped_skill_names`` is deduplicated and returned in a
    deterministic (alphabetically sorted) order.
  - ``provider`` on every key is byte-identical to
    ``derive_model_identity(model)["modelProvider"]`` for that model -- a
    unit test asserts this equality directly, never a hardcoded or
    re-derived value.

Uses the REAL pinned ``routing_task_map_v1.json`` mapping (via
``RoutingRollupQueryService.apply_mapping``, T3-002) to build
``MappedRollupRow`` fixtures -- this task is a pure consumer of T3-002's
output, so its own tests exercise the real mapped-row shape rather than
hand-constructing ``MappedRollupRow`` instances that could drift from what
``apply_mapping`` actually emits.

T3-001/T3-002's own contracts are covered by
``test_routing_rollup_aggregation.py`` / ``test_routing_rollup_mapping.py``;
T3-005 (not yet built as of this test file) owns the dedicated determinism
and no-LLM-import-guard test files. This file covers only T3-003's own
provider + coverage-counter contract.

Run as a named module (full collection can hang -- see
``docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md`` and
the repo-wide pytest-collection caveat):
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_provider_coverage.py -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.application.services.agent_queries.routing_rollup import (
    UNCLASSIFIED_TASK_CLASS,
    CoverageCounters,
    MappedRollupRow,
    ProviderRollupRow,
    RawRollupRow,
    RoutingRollupQueryService,
)
from backend.model_identity import derive_model_identity


def _row(
    *,
    source_skill_name: str,
    session_count: int = 3,
    project_id: str = "proj-1",
    model: str = "claude-sonnet-5",
) -> RawRollupRow:
    now = datetime.now(timezone.utc)
    return RawRollupRow(
        project_id=project_id,
        source_skill_name=source_skill_name,
        model=model,
        session_count=session_count,
        window_start=now,
        window_end=now,
    )


def _mapped_row(
    *,
    task_class: str,
    is_coverage_only: bool,
    session_count: int = 3,
    source_skill_name: str = "some-skill",
    model: str = "claude-sonnet-5",
    project_id: str = "proj-1",
) -> MappedRollupRow:
    now = datetime.now(timezone.utc)
    return MappedRollupRow(
        project_id=project_id,
        source_skill_name=source_skill_name,
        model=model,
        session_count=session_count,
        window_start=now,
        window_end=now,
        task_class=task_class,
        is_coverage_only=is_coverage_only,
    )


class _ServiceTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RoutingRollupQueryService()


# ---------------------------------------------------------------------------
# AC: provider is byte-identical to derive_model_identity(model)["modelProvider"].
# ---------------------------------------------------------------------------

class TestApplyProviderDelegatesToModelIdentity(_ServiceTestBase):
    def test_provider_matches_derive_model_identity_for_each_model(self) -> None:
        models = ["claude-sonnet-5", "gpt-5.6-terra", "gemini-3.5-flash", "unknown-model-xyz", ""]
        mapped_rows = [
            _mapped_row(task_class="implementation", is_coverage_only=False, model=model)
            for model in models
        ]

        provider_rows = self.service.apply_provider(mapped_rows)

        self.assertEqual(len(provider_rows), len(models))
        for provider_row, model in zip(provider_rows, models):
            expected = str(derive_model_identity(model).get("modelProvider") or "")
            self.assertIsInstance(provider_row, ProviderRollupRow)
            self.assertEqual(provider_row.provider, expected)
            self.assertEqual(provider_row.model, model)

    def test_apply_provider_never_mutates_input_list(self) -> None:
        mapped_rows = [_mapped_row(task_class="implementation", is_coverage_only=False)]
        original_len = len(mapped_rows)

        self.service.apply_provider(mapped_rows)

        self.assertEqual(len(mapped_rows), original_len)
        for row in mapped_rows:
            self.assertIsInstance(row, MappedRollupRow)
            self.assertFalse(hasattr(row, "provider"))

    def test_apply_provider_preserves_non_provider_fields(self) -> None:
        mapped = _mapped_row(
            task_class=UNCLASSIFIED_TASK_CLASS,
            is_coverage_only=True,
            session_count=42,
            source_skill_name="codex",
            project_id="proj-x",
        )

        provider_rows = self.service.apply_provider([mapped])

        self.assertEqual(len(provider_rows), 1)
        result = provider_rows[0]
        self.assertEqual(result.project_id, mapped.project_id)
        self.assertEqual(result.source_skill_name, mapped.source_skill_name)
        self.assertEqual(result.session_count, mapped.session_count)
        self.assertEqual(result.task_class, mapped.task_class)
        self.assertEqual(result.is_coverage_only, mapped.is_coverage_only)
        self.assertEqual(result.window_start, mapped.window_start)
        self.assertEqual(result.window_end, mapped.window_end)


# ---------------------------------------------------------------------------
# AC: mapped_count / unclassified_count are session-level totals that sum
# exactly to total_rows, keyed off resolved task_class only.
# ---------------------------------------------------------------------------

class TestCoverageCountersArithmetic(_ServiceTestBase):
    def test_counters_match_hand_computed_fixture(self) -> None:
        rows = [
            _mapped_row(task_class="implementation", is_coverage_only=False, session_count=10),
            _mapped_row(task_class="debugging_class", is_coverage_only=False, session_count=5),
            _mapped_row(task_class=UNCLASSIFIED_TASK_CLASS, is_coverage_only=True, session_count=7,
                        source_skill_name="totally-unmapped-a"),
            _mapped_row(task_class=UNCLASSIFIED_TASK_CLASS, is_coverage_only=True, session_count=3,
                        source_skill_name="totally-unmapped-b"),
        ]

        counters = self.service.compute_coverage_counters(rows)

        self.assertIsInstance(counters, CoverageCounters)
        self.assertEqual(counters.mapped_count, 15)  # 10 + 5
        self.assertEqual(counters.unclassified_count, 10)  # 7 + 3
        total_rows = sum(row.session_count for row in rows)
        self.assertEqual(counters.mapped_count + counters.unclassified_count, total_rows)

    def test_protected_class_rows_count_toward_mapped_not_unclassified(self) -> None:
        rows = [
            _mapped_row(task_class="orchestration", is_coverage_only=True, session_count=8,
                        source_skill_name="planning"),
            _mapped_row(task_class="mode_d", is_coverage_only=True, session_count=4,
                        source_skill_name="release"),
            _mapped_row(task_class=UNCLASSIFIED_TASK_CLASS, is_coverage_only=True, session_count=6,
                        source_skill_name="codex"),
        ]

        counters = self.service.compute_coverage_counters(rows)

        # Protected rows (is_coverage_only=True) are still "mapped" for
        # counter purposes -- only task_class == _unclassified routes to
        # unclassified_count.
        self.assertEqual(counters.mapped_count, 12)  # 8 + 4
        self.assertEqual(counters.unclassified_count, 6)
        self.assertEqual(counters.mapped_count + counters.unclassified_count, 18)

    def test_executor_identity_rows_with_mapping_entries_land_in_unclassified_not_mapped(self) -> None:
        """codex/claude-api/ica-delegate HAVE real mapping entries (built via
        the actual apply_mapping pipeline, not a hand-built MappedRollupRow)
        that resolve to _unclassified -- proves the counters key off the
        resolved task_class value, never off mapping-entry presence, and
        never double-count a row in both buckets.
        """
        raw_rows = [
            RawRollupRow(
                project_id="proj-1",
                source_skill_name=name,
                model="claude-sonnet-5",
                session_count=count,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
            )
            for name, count in [("codex", 11), ("claude-api", 4), ("ica-delegate", 2)]
        ]
        raw_rows.append(
            RawRollupRow(
                project_id="proj-1",
                source_skill_name="debugging",
                model="claude-sonnet-5",
                session_count=9,
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
            )
        )

        mapped_rows = self.service.apply_mapping(raw_rows, include_protected_rows=True)
        counters = self.service.compute_coverage_counters(mapped_rows)

        total_rows = sum(row.session_count for row in raw_rows)
        self.assertEqual(total_rows, 26)
        # codex/claude-api/ica-delegate (11+4+2=17) -> unclassified_count;
        # debugging (9) -> mapped_count. Never both, never neither.
        self.assertEqual(counters.unclassified_count, 17)
        self.assertEqual(counters.mapped_count, 9)
        self.assertEqual(counters.mapped_count + counters.unclassified_count, total_rows)
        self.assertEqual(counters.distinct_unmapped_skill_names, ["claude-api", "codex", "ica-delegate"])

    def test_no_unclassified_rows_yields_empty_distinct_unmapped_list(self) -> None:
        rows = [_mapped_row(task_class="implementation", is_coverage_only=False)]

        counters = self.service.compute_coverage_counters(rows)

        self.assertEqual(counters.unclassified_count, 0)
        self.assertEqual(counters.mapped_count, 3)
        self.assertEqual(counters.distinct_unmapped_skill_names, [])

    def test_empty_input_yields_zero_counters(self) -> None:
        counters = self.service.compute_coverage_counters([])

        self.assertEqual(counters.mapped_count, 0)
        self.assertEqual(counters.unclassified_count, 0)
        self.assertEqual(counters.distinct_unmapped_skill_names, [])


# ---------------------------------------------------------------------------
# AC: distinct_unmapped_skill_names is deduplicated and deterministically
# (alphabetically) sorted.
# ---------------------------------------------------------------------------

class TestDistinctUnmappedSkillNamesDedupAndSort(_ServiceTestBase):
    def test_duplicate_skill_names_across_multiple_keys_are_deduplicated(self) -> None:
        rows = [
            _mapped_row(task_class=UNCLASSIFIED_TASK_CLASS, is_coverage_only=True,
                        source_skill_name="zeta-unmapped", model="claude-sonnet-5", session_count=2),
            _mapped_row(task_class=UNCLASSIFIED_TASK_CLASS, is_coverage_only=True,
                        source_skill_name="zeta-unmapped", model="gpt-5.6-terra", session_count=5),
            _mapped_row(task_class=UNCLASSIFIED_TASK_CLASS, is_coverage_only=True,
                        source_skill_name="alpha-unmapped", model="claude-sonnet-5", session_count=1),
        ]

        counters = self.service.compute_coverage_counters(rows)

        self.assertEqual(counters.distinct_unmapped_skill_names, ["alpha-unmapped", "zeta-unmapped"])
        self.assertEqual(counters.unclassified_count, 8)  # 2 + 5 + 1

    def test_sort_order_is_alphabetical_regardless_of_input_order(self) -> None:
        rows = [
            _mapped_row(task_class=UNCLASSIFIED_TASK_CLASS, is_coverage_only=True,
                        source_skill_name=name)
            for name in ["yankee", "alpha", "mike", "bravo"]
        ]

        counters = self.service.compute_coverage_counters(rows)

        self.assertEqual(counters.distinct_unmapped_skill_names, ["alpha", "bravo", "mike", "yankee"])


if __name__ == "__main__":
    unittest.main()
