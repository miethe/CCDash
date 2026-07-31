"""Fixture tests for T6-005: sparse-key visibility (AC-5) and protected-class
/``_unclassified`` coverage-only handling (AC-6).

Covers PRD Sec.11's AC-5 and AC-6 against a single 40-key density fixture
ported from the value-findings SPIKE
(``docs/project_plans/exploration/proof-to-routing-loop/spikes/value-findings.md``,
Section 3's ``(skill_name, model)`` per-key density table): 40 distinct keys,
21 clearing ``sample_count >= 5`` (52.5%, matches the spike's own
``21 (52.5%)`` figure) and 14 clearing ``sample_count >= 10`` (35.0%, matches
the spike's own ``14 (35.0%)`` figure). The top 15 entries are the spike's
own named ``(skill_name, model, count)`` tuples verbatim; the remaining 25
are a deterministic, density-matching extension of the spike's own
description ("remaining 25 keys tail off from 8 down to 1") -- the spike
does not enumerate those 25 individually, so they are reconstructed here to
land the fixture's aggregate ratios exactly on the spike's reported figures,
never as a synthetic all-dense or all-sparse fixture (AC-5's own bullet on
this point).

The fixture is run through the REAL pinned ``routing_task_map_v1.json``
mapping (via ``RoutingRollupQueryService.apply_mapping`` ->
``apply_provider`` -> ``compute_metrics``), not a mocked mapping -- several
of the spike's own named skills (``planning`` -> ``orchestration``,
``release`` -> ``mode_d``, ``ica-delegate`` -> ``_unclassified``) are
protected/coverage-only classes under the real mapping, which is exactly why
this one real-world-derived fixture exercises both AC-5 (ordinary sparse
keys) and AC-6 (protected-class/``_unclassified`` coverage-only rows) without
needing two independent synthetic fixtures.

T3-002 (``test_routing_rollup_mapping.py``) and T3-004
(``test_routing_rollup_metrics.py``) already unit-test the underlying
mechanisms (mapping emission gates, per-row eligibility hardcode) with
single-row/small fixtures. This file's job is different: prove those
mechanisms hold across a *realistic, density-matched* multi-key fixture, and
prove the AC-6 hardcode survives an adversarial ("config-knob-immunity")
attempt to override it via the feature's own config knobs
(``CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS``,
``CCDASH_ROUTING_FEEDBACK_MIN_SAMPLE_SIZE``).

Run as a named module (full collection can hang -- see
``docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md`` and
the repo-wide pytest-collection caveat):
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_sparse_protected.py -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest import mock

from backend import config
from backend.application.services.agent_queries.models import RoutingRollupKeyDTO
from backend.application.services.agent_queries.routing_rollup import (
    PROTECTED_TASK_CLASSES,
    UNCLASSIFIED_TASK_CLASS,
    RawRollupRow,
    RoutingRollupQueryService,
)

_FIXED_FRESHNESS_TS = "2026-07-31T00:00:00+00:00"

# ---------------------------------------------------------------------------
# The 40-key density fixture, ported from the value-findings SPIKE.
#
# Rows 1-15: the spike's own named "Top keys" table (Section 3), verbatim
#   (skill_name, model, count). All 14 of these clear N>=10; the 15th
#   ("release") is the spike's own explicitly-called-out N-in-[5,9] example
#   ("below N=10, above N=5").
# Rows 16-21: 6 additional N-in-[5,9] keys, extending the spike's own
#   "remaining 25 keys tail off from 8 down to 1" description, sized so the
#   fixture's overall N>=5 count lands exactly on the spike's reported
#   21/40 (52.5%).
# Rows 22-40: 19 remaining N<5 keys completing the tail and the fixture's
#   total of 40 distinct keys (matches the spike's implied "48% below
#   threshold" remainder).
#
# Several rows deliberately reuse skill names the pinned
# routing_task_map_v1.json maps to protected classes (`planning` ->
# `orchestration`, `release` -> `mode_d`, `enterprise-demo-deploy` ->
# `mode_d`) or to `_unclassified` (`ica-delegate`, `codex`, `claude-api`,
# both via an explicit executor-identity mapping rule) -- plus two entries
# with NO mapping rule at all (`totally-unmapped-tail-skill-a/b`), covering
# both `_unclassified` emission paths (T3-002's "missing entry OR resolves
# to _unclassified" policy) inside the same density-realistic fixture.
# ---------------------------------------------------------------------------
_FIXTURE_ROWS: tuple[tuple[str, str, int], ...] = (
    # --- rows 1-15: spike's own named top-key table, verbatim -------------
    ("symbols", "claude-haiku-4-5-20251001", 145),
    ("skillmeat-cli", "claude-sonnet-4-6", 114),
    ("skillmeat-cli", "claude-sonnet-5", 71),
    ("dev-execution", "claude-opus-4-8", 68),
    ("planning", "claude-sonnet-4-6", 52),
    ("planning", "claude-opus-4-8", 39),
    ("frontend-design", "claude-sonnet-5", 34),
    ("dev-execution", "claude-sonnet-5", 33),
    ("dev-execution", "claude-sonnet-4-6", 28),
    ("frontend-design", "claude-sonnet-4-6", 28),
    ("debugging", "claude-opus-4-8", 25),
    ("planning", "claude-sonnet-5", 17),
    ("skillmeat-cli", "claude-opus-4-8", 14),
    ("ica-delegate", "claude-opus-4-8", 11),
    ("release", "claude-opus-4-8", 8),
    # --- rows 16-21: additional N-in-[5,9] keys -----------------------------
    ("artifact-tracking", "claude-sonnet-5", 9),
    ("changelog-sync", "claude-haiku-4-5-20251001", 7),
    ("plan-status", "claude-sonnet-4-6", 7),
    ("workflow-authoring", "claude-sonnet-5", 6),
    ("debug", "claude-opus-4-8", 6),
    ("firecrawl-scrape", "claude-sonnet-5", 5),
    # --- rows 22-40: N<5 tail, completing the 40-key total ------------------
    ("enterprise-demo-deploy", "claude-opus-4-8", 4),
    ("dev-execution", "gpt-5.6-terra", 4),
    ("debugging", "claude-sonnet-5", 3),
    ("frontend-design", "claude-opus-4-8", 3),
    ("symbols", "claude-sonnet-5", 3),
    ("skillmeat-cli", "gpt-5.6-terra", 2),
    ("planning", "gpt-5.6-terra", 2),
    ("ica-delegate", "claude-sonnet-4-6", 2),
    ("codex", "claude-opus-4-8", 2),
    ("claude-api", "claude-sonnet-5", 1),
    ("release", "claude-sonnet-5", 1),
    ("artifact-tracking", "claude-opus-4-8", 1),
    ("changelog-sync", "claude-sonnet-5", 1),
    ("plan-status", "claude-opus-4-8", 1),
    ("workflow-authoring", "claude-opus-4-8", 1),
    ("firecrawl-scrape", "claude-opus-4-8", 1),
    ("debug", "claude-sonnet-4-6", 1),
    ("totally-unmapped-tail-skill-a", "claude-sonnet-5", 1),
    ("totally-unmapped-tail-skill-b", "claude-opus-4-8", 1),
)


def _raw_rows(fixture: tuple[tuple[str, str, int], ...] = _FIXTURE_ROWS) -> list[RawRollupRow]:
    now = datetime.now(timezone.utc)
    return [
        RawRollupRow(
            project_id="proj-1",
            source_skill_name=skill_name,
            model=model,
            session_count=session_count,
            window_start=now,
            window_end=now,
        )
        for skill_name, model, session_count in fixture
    ]


def _dtos_from_fixture(
    *,
    fixture: tuple[tuple[str, str, int], ...] = _FIXTURE_ROWS,
    include_protected_rows: bool | None = None,
    min_sample_size: int | None = None,
) -> list[RoutingRollupKeyDTO]:
    """Drive the fixture through the REAL apply_mapping -> apply_provider ->
    compute_metrics pipeline -- never a mocked mapping or a hand-built DTO
    list -- so this test exercises the same pinned contract artifact T3-002
    consumes in production.
    """
    service = RoutingRollupQueryService()
    mapped = service.apply_mapping(_raw_rows(fixture), include_protected_rows=include_protected_rows)
    provided = service.apply_provider(mapped)
    return service.compute_metrics(
        provided, min_sample_size=min_sample_size, freshness_ts=_FIXED_FRESHNESS_TS
    )


# ---------------------------------------------------------------------------
# Fixture self-check: the fixture itself must reproduce the value-findings
# spike's own reported density ratios, not a synthetic all-dense or
# all-sparse shape (AC-5's own bullet on this point). Guards against a
# future edit silently drifting the fixture's shape away from the profile
# this feature was sized against.
# ---------------------------------------------------------------------------


class TestFixtureReproducesValueFindingsDensityProfile(unittest.TestCase):
    def test_fixture_has_forty_distinct_keys(self) -> None:
        keys = {(skill_name, model) for skill_name, model, _ in _FIXTURE_ROWS}
        self.assertEqual(len(_FIXTURE_ROWS), 40, "fixture must declare exactly 40 rows")
        self.assertEqual(len(keys), 40, "every (skill_name, model) pair must be distinct -- no duplicate keys")

    def test_fixture_matches_spike_n_gte_5_ratio(self) -> None:
        n_gte_5 = sum(1 for _, _, count in _FIXTURE_ROWS if count >= 5)
        self.assertEqual(n_gte_5, 21, "spike reports 21/40 (52.5%) keys clearing N>=5")

    def test_fixture_matches_spike_n_gte_10_ratio(self) -> None:
        n_gte_10 = sum(1 for _, _, count in _FIXTURE_ROWS if count >= 10)
        self.assertEqual(n_gte_10, 14, "spike reports 14/40 (35.0%) keys clearing N>=10")

    def test_fixture_is_not_uniformly_dense_or_sparse(self) -> None:
        counts = [count for _, _, count in _FIXTURE_ROWS]
        self.assertGreater(min(counts), 0)
        self.assertLess(min(counts), 5, "fixture must include genuinely sub-threshold keys")
        self.assertGreaterEqual(max(counts), 10, "fixture must include genuinely dense keys")


# ---------------------------------------------------------------------------
# AC-5: every emitted key carries sample_count + eligible_for_adjustment
# regardless of threshold; sub-threshold keys are NEVER suppressed.
# ---------------------------------------------------------------------------


class TestSparseKeyVisibility(unittest.TestCase):
    def test_all_forty_keys_survive_to_the_response_none_suppressed(self) -> None:
        dtos = _dtos_from_fixture(include_protected_rows=True, min_sample_size=5)

        self.assertEqual(len(dtos), len(_FIXTURE_ROWS), "no key -- dense or sparse -- may be dropped")

    def test_every_key_carries_sample_count_and_eligible_for_adjustment_fields(self) -> None:
        dtos = _dtos_from_fixture(include_protected_rows=True, min_sample_size=5)

        for dto in dtos:
            with self.subTest(source_skill_name=dto.source_skill_name, model=dto.model):
                self.assertIsInstance(dto.sample_count, int)
                self.assertIsInstance(dto.eligible_for_adjustment, bool)

    def test_sub_threshold_keys_are_present_with_sample_count_and_ineligible(self) -> None:
        dtos = _dtos_from_fixture(include_protected_rows=True, min_sample_size=5)
        sub_threshold = [dto for dto in dtos if dto.sample_count < 5]

        expected_sub_threshold_count = sum(1 for _, _, count in _FIXTURE_ROWS if count < 5)
        self.assertEqual(len(sub_threshold), expected_sub_threshold_count)
        for dto in sub_threshold:
            with self.subTest(source_skill_name=dto.source_skill_name, model=dto.model):
                # Never suppressed -- sample_count is the real raw count,
                # not zeroed/omitted, and eligible_for_adjustment is present
                # (False), never a missing/None sentinel.
                self.assertGreater(dto.sample_count, 0)
                self.assertFalse(dto.eligible_for_adjustment)

    def test_ordinary_keys_at_or_above_threshold_are_eligible(self) -> None:
        dtos = _dtos_from_fixture(include_protected_rows=True, min_sample_size=5)

        ordinary_dense = [
            dto
            for dto in dtos
            if dto.task_class not in PROTECTED_TASK_CLASSES
            and dto.task_class != UNCLASSIFIED_TASK_CLASS
            and dto.sample_count >= 5
        ]

        # From the fixture: 21 keys clear N>=5, 5 of which resolve to a
        # protected class (planning x4, release x1) -- leaving 16 ordinary
        # dense keys.
        self.assertEqual(len(ordinary_dense), 16)
        for dto in ordinary_dense:
            with self.subTest(source_skill_name=dto.source_skill_name, model=dto.model):
                self.assertTrue(dto.eligible_for_adjustment)


# ---------------------------------------------------------------------------
# AC-6: rows resolving to _unclassified or a protected class
# (orchestration/mode_d) ALWAYS carry a hardcoded, non-overridable
# eligible_for_adjustment=False -- independent of sample_count and
# independent of any config knob.
# ---------------------------------------------------------------------------


class TestProtectedClassCoverageOnlyHardcodedIneligible(unittest.TestCase):
    def test_every_coverage_only_row_is_ineligible_regardless_of_sample_count(self) -> None:
        dtos = _dtos_from_fixture(include_protected_rows=True, min_sample_size=5)

        coverage_only = [
            dto
            for dto in dtos
            if dto.task_class in PROTECTED_TASK_CLASSES or dto.task_class == UNCLASSIFIED_TASK_CLASS
        ]

        # 7 protected rows (planning x4, release x2, enterprise-demo-deploy
        # x1) + 6 _unclassified rows (ica-delegate x2, codex x1,
        # claude-api x1, totally-unmapped-tail-skill-a/b x2) = 13.
        self.assertEqual(len(coverage_only), 13)
        for dto in coverage_only:
            with self.subTest(source_skill_name=dto.source_skill_name, model=dto.model, sample_count=dto.sample_count):
                self.assertFalse(dto.eligible_for_adjustment)

    def test_dense_protected_rows_are_still_ineligible_despite_clearing_threshold(self) -> None:
        """planning|claude-sonnet-4-6 (52) and planning|claude-opus-4-8 (39)
        both clear N>=5 by a wide margin -- proves the hardcode is not a
        coincidence of these particular rows happening to be sparse.
        """
        dtos = _dtos_from_fixture(include_protected_rows=True, min_sample_size=5)
        dense_protected = [
            dto for dto in dtos if dto.task_class == "orchestration" and dto.sample_count >= 5
        ]

        self.assertEqual(len(dense_protected), 3)  # 52, 39, 17
        for dto in dense_protected:
            self.assertFalse(dto.eligible_for_adjustment)

    def test_unclassified_present_via_missing_entry_and_via_explicit_resolution(self) -> None:
        dtos = _dtos_from_fixture(include_protected_rows=True, min_sample_size=5)
        unclassified = {dto.source_skill_name for dto in dtos if dto.task_class == UNCLASSIFIED_TASK_CLASS}

        # Explicit executor-identity mapping-rule resolution:
        self.assertIn("ica-delegate", unclassified)
        self.assertIn("codex", unclassified)
        self.assertIn("claude-api", unclassified)
        # No mapping entry at all:
        self.assertIn("totally-unmapped-tail-skill-a", unclassified)
        self.assertIn("totally-unmapped-tail-skill-b", unclassified)

    # -- config-knob-immunity ------------------------------------------------

    def test_min_sample_size_zero_does_not_flip_coverage_only_rows_eligible(self) -> None:
        """The most adversarial possible min_sample_size (0) makes every
        ORDINARY row eligible (sample_count >= 0 is always true) -- but
        coverage-only rows must remain ineligible regardless, proving the
        hardcode is independent of the sample-size knob rather than merely
        surviving by coincidence at the default threshold.
        """
        dtos = _dtos_from_fixture(include_protected_rows=True, min_sample_size=0)

        ordinary = [
            dto
            for dto in dtos
            if dto.task_class not in PROTECTED_TASK_CLASSES and dto.task_class != UNCLASSIFIED_TASK_CLASS
        ]
        coverage_only = [
            dto
            for dto in dtos
            if dto.task_class in PROTECTED_TASK_CLASSES or dto.task_class == UNCLASSIFIED_TASK_CLASS
        ]

        for dto in ordinary:
            with self.subTest(source_skill_name=dto.source_skill_name, model=dto.model):
                self.assertTrue(dto.eligible_for_adjustment, "min_sample_size=0 must make every ordinary row eligible")
        for dto in coverage_only:
            with self.subTest(source_skill_name=dto.source_skill_name, model=dto.model):
                self.assertFalse(
                    dto.eligible_for_adjustment,
                    "coverage-only hardcode must survive even the most lenient possible threshold",
                )

    def test_include_protected_rows_flag_never_makes_an_emitted_protected_row_eligible(self) -> None:
        for flag_value in (True, False):
            with self.subTest(include_protected_rows=flag_value):
                dtos = _dtos_from_fixture(include_protected_rows=flag_value, min_sample_size=5)
                emitted_protected = [dto for dto in dtos if dto.task_class in PROTECTED_TASK_CLASSES]

                if flag_value:
                    self.assertGreater(len(emitted_protected), 0, "flag True must emit the protected rows")
                else:
                    self.assertEqual(len(emitted_protected), 0, "flag False must omit protected rows entirely")

                # Whichever the flag's value, any protected row that IS
                # emitted is ineligible -- the flag only ever controls
                # presence, never eligibility.
                for dto in emitted_protected:
                    self.assertFalse(dto.eligible_for_adjustment)

    def test_include_protected_rows_flag_defaults_from_config_and_still_hardcodes_ineligible(self) -> None:
        with mock.patch.object(config, "CCDASH_ROUTING_FEEDBACK_INCLUDE_PROTECTED_ROWS", True):
            dtos = _dtos_from_fixture(min_sample_size=5)

        emitted_protected = [dto for dto in dtos if dto.task_class in PROTECTED_TASK_CLASSES]
        self.assertGreater(len(emitted_protected), 0)
        for dto in emitted_protected:
            self.assertFalse(dto.eligible_for_adjustment)

    def test_unclassified_rows_ineligible_regardless_of_protected_rows_flag(self) -> None:
        for flag_value in (True, False):
            with self.subTest(include_protected_rows=flag_value):
                dtos = _dtos_from_fixture(include_protected_rows=flag_value, min_sample_size=5)
                unclassified = [dto for dto in dtos if dto.task_class == UNCLASSIFIED_TASK_CLASS]

                # _unclassified is always emitted, unconditionally of the
                # protected-rows flag (T3-002/FR-7) -- present in both runs.
                self.assertGreater(len(unclassified), 0)
                for dto in unclassified:
                    self.assertFalse(dto.eligible_for_adjustment)


if __name__ == "__main__":
    unittest.main()
