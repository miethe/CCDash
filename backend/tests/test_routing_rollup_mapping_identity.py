"""Mapping-identity certification coverage for ``_client_v1_routing_rollup.py``.

Regression protection for the mixed-identity bug: ``mapping_version`` is the
only one of the three mapping-identity fields persisted per ``routing_rollup``
row, while ``mapping_id``/``mapping_digest`` are always supplied from the
current in-code ``routing_feedback_contract`` constants. Before the read-path
withhold, a row persisted under a superseded mapping was served as
``(old mapping_version, current mapping_digest)`` -- an identity triple that
never existed at any point in time. The external delegation-router join
validator requires all three to match its pinned producer contract, so it
rejected such rows as ``mapping_mismatch`` and the feedback channel went
silently inert.

There is no historical-digest table, so a stale row's true digest is
unrecoverable. ``_row_certifiable`` therefore withholds it entirely: it
contributes to nothing -- not ``keys``, not the FR-7 counters, not
``generated_at`` -- exactly as if it had not been swept yet.

Style/imports mirror ``backend/tests/test_client_v1_routing_rollup.py`` (whose
``_make_row`` fixture shape this module reuses).

Run as a named module:
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_mapping_identity.py -v
"""
from __future__ import annotations

import unittest
from typing import Any

from backend.application.services.agent_queries import routing_feedback_contract
from backend.application.services.agent_queries.routing_feedback_contract import (
    CONTRACT_VERSION,
    MAPPING_DIGEST,
    MAPPING_ID,
    MAPPING_VERSION,
    TAXONOMY_VERSION,
)
from backend.application.services.agent_queries.routing_rollup import UNCLASSIFIED_TASK_CLASS
from backend.db.repositories.routing_rollup import ROUTING_ROLLUP_COLUMNS
from backend.routers._client_v1_routing_rollup import (
    _build_response_from_rows,
    _row_certifiable,
)

_PROJECT_ID = "test-project-routing-rollup-mapping-identity"

# A concrete superseded version. The bug was measured with rows persisted under
# 1.1.0 after the constant was bumped to 1.2.0; the assertions below only rely
# on it differing from the current constant, so they survive the next bump.
_STALE_MAPPING_VERSION = "1.1.0"


def _make_row(**overrides: Any) -> dict[str, Any]:
    """Return a ``ROUTING_ROLLUP_COLUMNS``-shaped dict -- the exact row shape
    ``_build_response_from_rows`` consumes, mirroring
    ``test_client_v1_routing_rollup.py``'s fixture.
    """
    row: dict[str, Any] = {
        "project_id": _PROJECT_ID,
        "source_skill_name": "planning",
        "model": "claude-sonnet-5",
        "window_start": "2026-08-01T00:00:00+00:00",
        "window_end": "2026-08-08T00:00:00+00:00",
        "task_class": "orchestration",
        "provider": "anthropic",
        "sample_count": 12,
        "success_rate": None,
        "cost_index": 0.42,
        "cost_coverage_fraction": 0.94,
        "regression_rate": None,
        "effort_tier": "high",
        "effort_tier_source": "codex_payload_effort",
        "authoritative_effort_fraction": 0.75,
        "confidence": 0.8,
        "eligible_for_adjustment": 1,
        "freshness_ts": "2026-08-08T00:00:00+00:00",
        "contract_version": CONTRACT_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "mapping_version": MAPPING_VERSION,
    }
    row.update(overrides)
    assert set(row) == set(ROUTING_ROLLUP_COLUMNS)
    return row


def _stale_row(**overrides: Any) -> dict[str, Any]:
    """A row persisted under a superseded mapping."""
    return _make_row(mapping_version=_STALE_MAPPING_VERSION, **overrides)


class MappingVersionSanityTests(unittest.TestCase):
    """The fixture premise: the stale marker really is superseded."""

    def test_stale_marker_differs_from_the_current_constant(self) -> None:
        self.assertNotEqual(_STALE_MAPPING_VERSION, MAPPING_VERSION)


class RowCertifiableTests(unittest.TestCase):
    """``_row_certifiable``: the per-row certification predicate."""

    def test_current_mapping_version_certifies(self) -> None:
        self.assertTrue(_row_certifiable(_make_row()))

    def test_superseded_mapping_version_does_not_certify(self) -> None:
        self.assertFalse(_row_certifiable(_stale_row()))

    def test_empty_mapping_version_does_not_certify(self) -> None:
        """An empty column carries no evidence of which mapping produced the
        row; ``_row_to_key_dto``'s fallback would silently restamp it current.
        """
        self.assertFalse(_row_certifiable(_make_row(mapping_version="")))
        self.assertFalse(_row_certifiable(_make_row(mapping_version=None)))


class StaleRowWithholdingTests(unittest.TestCase):
    """``_build_response_from_rows``: superseded rows contribute to nothing."""

    def test_stale_row_is_absent_from_keys(self) -> None:
        response = _build_response_from_rows([_stale_row(source_skill_name="planning")])
        self.assertEqual(response.keys, [])

    def test_every_served_key_carries_the_current_mapping_version(self) -> None:
        """THE CORE REGRESSION. For an arbitrary mix of stale and current rows,
        no served key may pair a persisted ``mapping_version`` with the
        constant ``mapping_digest``/``mapping_id`` beside it -- the mixed
        identity triple the delegation-router validator rejects.
        """
        rows = [
            _make_row(source_skill_name="planning", sample_count=10),
            _stale_row(source_skill_name="codex", model="gpt-5.6", sample_count=7),
            _make_row(source_skill_name="release", task_class="mode_d", sample_count=3),
            _stale_row(
                source_skill_name="ica-delegate",
                task_class=UNCLASSIFIED_TASK_CLASS,
                sample_count=5,
            ),
            _make_row(mapping_version="", source_skill_name="orphan", sample_count=99),
        ]
        response = _build_response_from_rows(rows)

        self.assertTrue(response.keys, "expected the current-mapping rows to be served")
        for key in response.keys:
            self.assertEqual(key.mapping_version, MAPPING_VERSION)
            self.assertEqual(key.mapping_version, routing_feedback_contract.MAPPING_VERSION)
            self.assertEqual(key.mapping_id, MAPPING_ID)
            self.assertEqual(key.mapping_digest, MAPPING_DIGEST)

    def test_stale_and_current_mix_serves_only_the_current_rows(self) -> None:
        rows = [
            _make_row(source_skill_name="planning", sample_count=10),
            _stale_row(source_skill_name="codex", model="gpt-5.6", sample_count=7),
        ]
        response = _build_response_from_rows(rows)
        self.assertEqual(
            [key.source_skill_name for key in response.keys], ["planning"]
        )

    def test_counters_sum_over_the_certified_population_only(self) -> None:
        """A stale row's ``sample_count`` is counted NOWHERE -- neither
        ``mapped_count`` nor ``unclassified_count`` -- exactly as if it had not
        been swept yet. The FR-7 counter-sum invariant therefore holds over the
        certified population, not over all persisted rows.
        """
        rows = [
            _make_row(source_skill_name="planning", task_class="orchestration", sample_count=10),
            _make_row(
                source_skill_name="codex",
                model="gpt-5.6",
                task_class=UNCLASSIFIED_TASK_CLASS,
                sample_count=4,
            ),
            # Superseded rows, one of each partition -- neither may register.
            _stale_row(source_skill_name="release", task_class="mode_d", sample_count=100),
            _stale_row(
                source_skill_name="stale-only-skill",
                task_class=UNCLASSIFIED_TASK_CLASS,
                sample_count=200,
            ),
        ]
        response = _build_response_from_rows(rows)

        self.assertEqual(response.mapped_count, 10)
        self.assertEqual(response.unclassified_count, 4)
        self.assertEqual(
            response.mapped_count + response.unclassified_count,
            sum(int(r["sample_count"]) for r in rows if _row_certifiable(r)),
        )
        # A skill seen ONLY on a withheld unclassified row must not surface in
        # the unmapped-skill-name coverage list either.
        self.assertEqual(response.distinct_unmapped_skill_names, ["codex"])

    def test_generated_at_ignores_stale_row_freshness(self) -> None:
        """``generated_at`` is the max ``freshness_ts`` of the CERTIFIED rows --
        a withheld row must not make the envelope look fresher than the data it
        actually serves.
        """
        rows = [
            _make_row(freshness_ts="2026-08-05T00:00:00+00:00"),
            _stale_row(source_skill_name="codex", freshness_ts="2026-08-09T00:00:00+00:00"),
        ]
        response = _build_response_from_rows(rows)
        self.assertEqual(response.generated_at, "2026-08-05T00:00:00+00:00")

    def test_skill_dimension_counts_ignore_stale_rows(self) -> None:
        """DI-4e/D-b3's per-row skill-attribution counts are computed over the
        certified population too -- a withheld row inflates neither side.
        """
        rows = [
            _make_row(source_skill_name="planning", sample_count=50),
            _stale_row(source_skill_name="codex", sample_count=50),
            _stale_row(source_skill_name="", sample_count=50),
        ]
        response = _build_response_from_rows(rows)
        self.assertEqual(response.skill_attributed_key_count, 1)
        self.assertEqual(response.skill_unattributed_key_count, 0)


class AllStaleDegradationTests(unittest.TestCase):
    """Non-empty input where nothing certifies -> the documented empty shape."""

    def test_all_stale_rows_return_the_enabled_degradation_envelope(self) -> None:
        rows = [
            _stale_row(source_skill_name="planning", sample_count=10),
            _stale_row(
                source_skill_name="codex",
                model="gpt-5.6",
                task_class=UNCLASSIFIED_TASK_CLASS,
                sample_count=4,
            ),
        ]
        response = _build_response_from_rows(rows)

        self.assertTrue(response.enabled)
        self.assertIsNone(response.generated_at)
        self.assertEqual(response.mapped_count, 0)
        self.assertEqual(response.unclassified_count, 0)
        self.assertEqual(response.distinct_unmapped_skill_names, [])
        self.assertEqual(response.keys, [])

    def test_all_stale_envelope_is_identical_to_the_no_rows_envelope(self) -> None:
        """"Nothing certifies" must reuse the existing documented degradation
        shape, never a new envelope variant.
        """
        self.assertEqual(
            _build_response_from_rows([_stale_row()]),
            _build_response_from_rows([]),
        )


class EnvelopeIdentityFieldsTests(unittest.TestCase):
    """Envelope-level mapping identity is ALWAYS the current constants, in every
    partition case -- the withhold changes which rows are served, never the
    envelope's declared identity.
    """

    def _assert_envelope_identity(self, rows: list[dict[str, Any]]) -> None:
        response = _build_response_from_rows(rows)
        self.assertEqual(response.mapping_id, MAPPING_ID)
        self.assertEqual(response.mapping_version, MAPPING_VERSION)
        self.assertEqual(response.mapping_digest, MAPPING_DIGEST)

    def test_all_current_rows(self) -> None:
        self._assert_envelope_identity([_make_row()])

    def test_mixed_rows(self) -> None:
        self._assert_envelope_identity([_make_row(), _stale_row(source_skill_name="codex")])

    def test_all_stale_rows(self) -> None:
        self._assert_envelope_identity([_stale_row()])

    def test_no_rows(self) -> None:
        self._assert_envelope_identity([])


if __name__ == "__main__":
    unittest.main()
