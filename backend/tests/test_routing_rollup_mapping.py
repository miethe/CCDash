"""Unit tests for T3-002: ``RoutingRollupQueryService.apply_mapping`` --
pinned ``skill_name -> task_class`` mapping + protected-class policy.

Covers this task's own acceptance criteria (see
``docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1/phase-3-rollup-compute-service.md``,
Task T3-002):

  - ``_unclassified`` is ALWAYS emitted -- both for a ``source_skill_name``
    with NO mapping entry, and for one whose mapping entry EXISTS but
    explicitly resolves to ``_unclassified`` (executor-identity names:
    ``codex``, ``claude-api``, ``ica-delegate``) -- independent of
    ``CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS``.
  - Protected classes (``orchestration``, ``mode_d``) are present only when
    the flag is ``True``, absent when ``False``; ``_unclassified`` rows in
    the same fixture are unaffected by the flag either way.
  - Every protected/``_unclassified`` row carries ``is_coverage_only=True``
    -- the flag T3-004 MUST consume to hardcode
    ``eligible_for_adjustment=False`` -- independent of session_count size
    (i.e. this task's own row-shape has no sample-size concept at all yet;
    the invariant holds even for a very large ``session_count``).
  - ``task_class`` is never the literal raw ``source_skill_name`` value
    unless the pinned mapping coincidentally maps a name to an identical
    string (documented as a non-issue here, not a false negative).

Uses the REAL pinned ``routing_task_map_v1.json`` mapping directly (not a
mocked fixture) -- this task is a pure consumer of that frozen contract
artifact, so its own tests exercise the actual vendored rules
(``codex``/``claude-api``/``ica-delegate`` -> ``_unclassified``,
``planning`` -> ``orchestration``, ``release`` -> ``mode_d``,
``debugging`` -> ``implementation``).

T3-001's own raw-aggregation contract is covered by
``test_routing_rollup_aggregation.py``; T3-005 (not yet built as of this
test file) owns the dedicated determinism and no-LLM-import-guard test
files. This file covers only T3-002's own mapping/policy contract.

Run as a named module (full collection can hang -- see
``docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md`` and
the repo-wide pytest-collection caveat):
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_mapping.py -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from backend import config
from backend.application.services.agent_queries.routing_rollup import (
    PROTECTED_TASK_CLASSES,
    UNCLASSIFIED_TASK_CLASS,
    MappedRollupRow,
    RawRollupRow,
    RoutingRollupQueryService,
)


def _row(
    *,
    source_skill_name: str,
    session_count: int = 3,
    project_id: str = "proj-1",
    model: str = "sonnet-5",
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


class _MappingTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RoutingRollupQueryService()


# ---------------------------------------------------------------------------
# AC: _unclassified always emitted, independent of the protected-rows flag.
# ---------------------------------------------------------------------------

class TestUnclassifiedAlwaysEmitted(_MappingTestBase):
    def test_no_mapping_entry_resolves_unclassified_flag_true(self) -> None:
        rows = [_row(source_skill_name="totally-unmapped-skill-zzz")]

        mapped = self.service.apply_mapping(rows, include_protected_rows=True)

        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0].task_class, UNCLASSIFIED_TASK_CLASS)
        self.assertTrue(mapped[0].is_coverage_only)

    def test_no_mapping_entry_resolves_unclassified_flag_false(self) -> None:
        rows = [_row(source_skill_name="totally-unmapped-skill-zzz")]

        mapped = self.service.apply_mapping(rows, include_protected_rows=False)

        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0].task_class, UNCLASSIFIED_TASK_CLASS)
        self.assertTrue(mapped[0].is_coverage_only)

    def test_executor_identity_entries_resolve_unclassified_both_flag_values(self) -> None:
        """codex/claude-api/ica-delegate HAVE mapping entries, but those
        entries explicitly resolve to _unclassified -- proves the defining
        test is the resolved task_class value, never mapping-entry presence.
        """
        executor_identity_names = ["codex", "claude-api", "ica-delegate"]
        rows = [_row(source_skill_name=name) for name in executor_identity_names]

        for flag_value in (True, False):
            with self.subTest(include_protected_rows=flag_value):
                mapped = self.service.apply_mapping(rows, include_protected_rows=flag_value)
                self.assertEqual(len(mapped), len(executor_identity_names))
                for mapped_row in mapped:
                    self.assertEqual(mapped_row.task_class, UNCLASSIFIED_TASK_CLASS)
                    self.assertTrue(mapped_row.is_coverage_only)


# ---------------------------------------------------------------------------
# AC: protected classes gated by the flag; _unclassified rows unaffected.
# ---------------------------------------------------------------------------

class TestProtectedClassGating(_MappingTestBase):
    def _mixed_fixture(self) -> list[RawRollupRow]:
        return [
            _row(source_skill_name="planning"),  # -> orchestration (protected)
            _row(source_skill_name="release"),  # -> mode_d (protected)
            _row(source_skill_name="codex"),  # -> _unclassified (always emitted)
            _row(source_skill_name="debugging"),  # -> implementation (normal)
        ]

    def test_protected_rows_present_when_flag_true(self) -> None:
        mapped = self.service.apply_mapping(self._mixed_fixture(), include_protected_rows=True)

        task_classes = {row.task_class for row in mapped}
        self.assertIn("orchestration", task_classes)
        self.assertIn("mode_d", task_classes)
        self.assertIn(UNCLASSIFIED_TASK_CLASS, task_classes)
        self.assertIn("implementation", task_classes)
        self.assertEqual(len(mapped), 4, "all four fixture rows present when flag is True")

    def test_protected_rows_absent_when_flag_false(self) -> None:
        mapped = self.service.apply_mapping(self._mixed_fixture(), include_protected_rows=False)

        task_classes = {row.task_class for row in mapped}
        self.assertNotIn("orchestration", task_classes)
        self.assertNotIn("mode_d", task_classes)
        # _unclassified is unaffected by the flag.
        self.assertIn(UNCLASSIFIED_TASK_CLASS, task_classes)
        self.assertIn("implementation", task_classes)
        self.assertEqual(len(mapped), 2, "only the non-protected rows survive when flag is False")

    def test_flag_defaults_from_config_when_kwarg_omitted(self) -> None:
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS", False):
            mapped = self.service.apply_mapping(self._mixed_fixture())
        task_classes = {row.task_class for row in mapped}
        self.assertNotIn("orchestration", task_classes)
        self.assertNotIn("mode_d", task_classes)

        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS", True):
            mapped = self.service.apply_mapping(self._mixed_fixture())
        task_classes = {row.task_class for row in mapped}
        self.assertIn("orchestration", task_classes)
        self.assertIn("mode_d", task_classes)


# ---------------------------------------------------------------------------
# AC: is_coverage_only hardcoded True for protected/_unclassified rows,
# independent of session_count magnitude (T3-004's sample-size logic).
# ---------------------------------------------------------------------------

class TestCoverageOnlyIndependentOfSampleSize(_MappingTestBase):
    def test_large_session_count_does_not_flip_coverage_only_false(self) -> None:
        rows = [
            _row(source_skill_name="planning", session_count=50_000),  # protected
            _row(source_skill_name="codex", session_count=50_000),  # _unclassified
        ]

        mapped = self.service.apply_mapping(rows, include_protected_rows=True)

        self.assertEqual(len(mapped), 2)
        for mapped_row in mapped:
            self.assertTrue(
                mapped_row.is_coverage_only,
                "is_coverage_only must stay True regardless of session_count -- "
                "T3-004 consumes this flag to hardcode eligible_for_adjustment=False "
                "independent of any sample-size threshold check",
            )

    def test_normal_class_is_not_coverage_only_regardless_of_sample_size(self) -> None:
        rows = [_row(source_skill_name="debugging", session_count=1)]

        mapped = self.service.apply_mapping(rows, include_protected_rows=True)

        self.assertEqual(len(mapped), 1)
        self.assertFalse(mapped[0].is_coverage_only)
        self.assertEqual(mapped[0].task_class, "implementation")


# ---------------------------------------------------------------------------
# AC: task_class is a derived column -- never the raw skill_name (D3/FR-6).
# ---------------------------------------------------------------------------

class TestTaskClassNeverRawSkillNameLeak(_MappingTestBase):
    def test_mapped_row_task_class_differs_from_raw_skill_name(self) -> None:
        rows = [_row(source_skill_name="debugging")]

        mapped = self.service.apply_mapping(rows, include_protected_rows=True)

        self.assertEqual(mapped[0].source_skill_name, "debugging")
        self.assertEqual(mapped[0].task_class, "implementation")
        self.assertNotEqual(mapped[0].task_class, mapped[0].source_skill_name)

    def test_unclassified_row_task_class_differs_from_raw_skill_name(self) -> None:
        rows = [_row(source_skill_name="totally-unmapped-skill-zzz")]

        mapped = self.service.apply_mapping(rows, include_protected_rows=True)

        self.assertNotEqual(mapped[0].task_class, mapped[0].source_skill_name)
        self.assertEqual(mapped[0].task_class, UNCLASSIFIED_TASK_CLASS)


# ---------------------------------------------------------------------------
# AC: raw fields (project_id, model, session_count, window) pass through
# unmodified -- apply_mapping strictly extends, never mutates, the raw row.
# ---------------------------------------------------------------------------

class TestFieldPassthroughFidelity(_MappingTestBase):
    def test_non_task_class_fields_are_unmodified(self) -> None:
        raw = _row(source_skill_name="debugging", project_id="proj-x", model="opus-5", session_count=42)

        mapped = self.service.apply_mapping([raw], include_protected_rows=True)

        self.assertEqual(len(mapped), 1)
        result = mapped[0]
        self.assertIsInstance(result, MappedRollupRow)
        self.assertEqual(result.project_id, raw.project_id)
        self.assertEqual(result.model, raw.model)
        self.assertEqual(result.session_count, raw.session_count)
        self.assertEqual(result.window_start, raw.window_start)
        self.assertEqual(result.window_end, raw.window_end)

    def test_apply_mapping_does_not_mutate_input_list(self) -> None:
        raw_rows = [_row(source_skill_name="debugging"), _row(source_skill_name="planning")]
        original_len = len(raw_rows)

        self.service.apply_mapping(raw_rows, include_protected_rows=True)

        self.assertEqual(len(raw_rows), original_len)
        for row in raw_rows:
            self.assertIsInstance(row, RawRollupRow)
            self.assertFalse(hasattr(row, "task_class"))


# ---------------------------------------------------------------------------
# Sanity: PROTECTED_TASK_CLASSES / UNCLASSIFIED_TASK_CLASS module constants.
# ---------------------------------------------------------------------------

class TestModuleConstants(unittest.TestCase):
    def test_protected_task_classes_are_exactly_orchestration_and_mode_d(self) -> None:
        self.assertEqual(PROTECTED_TASK_CLASSES, frozenset({"orchestration", "mode_d"}))

    def test_unclassified_sentinel_matches_the_pinned_mapping_policy(self) -> None:
        self.assertEqual(UNCLASSIFIED_TASK_CLASS, "_unclassified")


if __name__ == "__main__":
    unittest.main()
