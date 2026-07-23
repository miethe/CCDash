"""Contract test pinning ``AARReviewDTO`` to the PRD §7.2 canonical shape (AC-P1.2).

Covers (ccdash-automated-aar-review-v1, T1-003/T1-004):

- The nested ``correlation`` object (``strategy``/``confidence``/``session_ids``/
  ``feature_id``) and the 3-value ``triage_verdict`` enum are present, and the
  DTO's ``schema_version`` has been bumped past the Tier-1-MVP's implicit ``1``.
- The pre-§7.2 flat fields (``session_refs``, ``correlation_confidence``,
  ``correlation_strategy``, ``verdict``) are still present as deprecated
  aliases and stay byte-for-byte consistent with the nested values -- old
  consumers must not silently start reading stale/diverged data.
- The verdict decision table (OQ-2 resolution) end to end: null confidence,
  sub-floor confidence, high-confidence+escalate-flags, high-confidence+no
  flags, and an ambiguous two-hop tie -- each mapped to the exact verdict the
  locked decision requires.

No LLM/model client is imported anywhere in this file or in ``aar_review.py``
(the hard invariant this feature is built on) -- these are pure/unit-level
checks over already-constructed DTOs and the deterministic ``compute_verdict``
combinator; no DB, no I/O.
"""
from __future__ import annotations

import unittest

from backend.application.services.agent_queries.aar_review import compute_verdict, evaluate_context_ballooning
from backend.application.services.agent_queries.models import AARReviewCorrelation, AARReviewDTO, AARReviewFlag


def _escalate_flag() -> AARReviewFlag:
    """A triggered flag -- the MVP's existing "any triggered flag -> escalate" signal."""
    return evaluate_context_ballooning(
        [{"id": "session-1", "context_window_size": 200000, "context_utilization_pct": 95.0}],
        threshold_pct=85.0,
    )


def _quiet_flag() -> AARReviewFlag:
    """A flag that does not trigger -- the "no-escalate" signal."""
    return evaluate_context_ballooning(
        [{"id": "session-1", "context_window_size": 200000, "context_utilization_pct": 10.0}],
        threshold_pct=85.0,
    )


class DTOShapeContractTests(unittest.TestCase):
    """Pins the exact §7.2 field shape: nested correlation + 3-value triage_verdict."""

    def test_schema_version_is_bumped_past_tier1_mvp(self) -> None:
        dto = AARReviewDTO(document_id="doc-1")
        self.assertGreater(dto.schema_version, 1)
        self.assertEqual(dto.schema_version, 2)

    def test_correlation_is_a_nested_object_with_the_prd_fields(self) -> None:
        dto = AARReviewDTO(
            document_id="doc-1",
            correlation=AARReviewCorrelation(
                strategy="two_hop_doc_feature_session",
                confidence=0.74,
                session_ids=["session-1"],
                feature_id="feature-1",
            ),
        )
        self.assertIsInstance(dto.correlation, AARReviewCorrelation)
        self.assertEqual(dto.correlation.strategy, "two_hop_doc_feature_session")
        self.assertEqual(dto.correlation.confidence, 0.74)
        self.assertEqual(dto.correlation.session_ids, ["session-1"])
        self.assertEqual(dto.correlation.feature_id, "feature-1")

    def test_correlation_confidence_and_feature_id_default_to_null(self) -> None:
        dto = AARReviewDTO(document_id="doc-1")
        self.assertIsNone(dto.correlation.confidence)
        self.assertIsNone(dto.correlation.feature_id)
        self.assertEqual(dto.correlation.session_ids, [])

    def test_triage_verdict_accepts_all_three_enum_values(self) -> None:
        for value in ("surface_only", "deep_review_recommended", "human_triage_required"):
            dto = AARReviewDTO(document_id="doc-1", triage_verdict=value)
            self.assertEqual(dto.triage_verdict, value)

    def test_triage_verdict_rejects_values_outside_the_three_value_enum(self) -> None:
        with self.assertRaises(Exception):
            AARReviewDTO(document_id="doc-1", triage_verdict="needs_more_data")  # type: ignore[arg-type]  # intentional invalid value — asserts DTO rejects it


class DeprecatedAliasConsistencyTests(unittest.TestCase):
    """The old flat fields are still present, and always mirror the nested values."""

    def _build(
        self,
        *,
        strategy: str | None,
        confidence: float | None,
        session_ids: list[str],
        feature_id: str | None,
        triage_verdict: str | None,
    ) -> AARReviewDTO:
        return AARReviewDTO(
            document_id="doc-1",
            correlation=AARReviewCorrelation(
                strategy=strategy, confidence=confidence, session_ids=session_ids, feature_id=feature_id,
            ),
            triage_verdict=triage_verdict,
        )

    def test_deprecated_flat_fields_are_present_on_the_model(self) -> None:
        fields = AARReviewDTO.model_fields
        for name in ("session_refs", "correlation_confidence", "correlation_strategy", "verdict"):
            self.assertIn(name, fields, f"deprecated alias field {name!r} must not be removed")

    def test_deprecated_aliases_mirror_nested_values_when_populated(self) -> None:
        dto = self._build(
            strategy="explicit_session_ref",
            confidence=1.0,
            session_ids=["session-1", "session-2"],
            feature_id=None,
            triage_verdict="deep_review_recommended",
        )
        self.assertEqual(dto.session_refs, dto.correlation.session_ids)
        self.assertEqual(dto.correlation_confidence, dto.correlation.confidence)
        self.assertEqual(dto.correlation_strategy, dto.correlation.strategy)
        self.assertEqual(dto.verdict, dto.triage_verdict)

    def test_deprecated_aliases_mirror_nested_values_when_null(self) -> None:
        dto = self._build(
            strategy=None, confidence=None, session_ids=[], feature_id=None, triage_verdict="human_triage_required",
        )
        self.assertEqual(dto.session_refs, [])
        self.assertIsNone(dto.correlation_confidence)
        self.assertIsNone(dto.correlation_strategy)
        self.assertEqual(dto.verdict, "human_triage_required")

    def test_deprecated_aliases_cannot_be_set_to_diverge_from_nested_values(self) -> None:
        # Even if a caller passes stale/conflicting flat values directly, the
        # post-construction validator is the single source of truth -- the
        # aliases always end up consistent with `correlation`/`triage_verdict`.
        dto = AARReviewDTO(
            document_id="doc-1",
            correlation=AARReviewCorrelation(strategy="explicit_session_ref", confidence=1.0, session_ids=["s1"]),
            triage_verdict="surface_only",
            session_refs=["stale-session"],
            correlation_confidence=0.1,
            correlation_strategy="stale_strategy",
            verdict="deep_review_recommended",
        )
        self.assertEqual(dto.session_refs, ["s1"])
        self.assertEqual(dto.correlation_confidence, 1.0)
        self.assertEqual(dto.correlation_strategy, "explicit_session_ref")
        self.assertEqual(dto.verdict, "surface_only")


class VerdictDecisionTableTests(unittest.TestCase):
    """Explicit end-to-end cases for the locked OQ-2 verdict decision table."""

    def test_null_confidence_requires_human_triage(self) -> None:
        verdict, reasons = compute_verdict(None, [], None, [], 0.64)
        self.assertEqual(verdict, "human_triage_required")
        self.assertTrue(any("missing" in reason or "null" in reason for reason in reasons))

    def test_confidence_below_floor_requires_human_triage(self) -> None:
        verdict, reasons = compute_verdict(0.5, ["session-1"], "task_session_ref", [_escalate_flag()], 0.64)
        self.assertEqual(verdict, "human_triage_required")
        self.assertTrue(any("below the floor" in reason for reason in reasons))

    def test_unambiguous_high_confidence_with_escalate_flags_is_deep_review_recommended(self) -> None:
        verdict, reasons = compute_verdict(0.9, ["session-1"], "explicit_session_ref", [_escalate_flag()], 0.64)
        self.assertEqual(verdict, "deep_review_recommended")
        self.assertTrue(reasons)

    def test_unambiguous_high_confidence_with_no_escalate_flags_is_surface_only(self) -> None:
        verdict, reasons = compute_verdict(0.9, ["session-1"], "explicit_session_ref", [_quiet_flag()], 0.64)
        self.assertEqual(verdict, "surface_only")
        self.assertIn("no flags triggered", reasons)

    def test_ambiguous_two_hop_multi_session_tie_requires_human_triage(self) -> None:
        verdict, reasons = compute_verdict(
            0.9, ["session-1", "session-2"], "two_hop_doc_feature_session", [_escalate_flag()], 0.64,
        )
        self.assertEqual(verdict, "human_triage_required")
        self.assertTrue(any("ambiguous" in reason for reason in reasons))

    def test_confidence_exactly_at_floor_is_not_below_floor(self) -> None:
        # 0.64 is the floor per tech-findings.md ("0.64-1.0"); the decision
        # table's "< 0.64" rule must not treat the boundary value itself as
        # sub-floor.
        verdict, _reasons = compute_verdict(0.64, ["session-1"], "explicit_session_ref", [_quiet_flag()], 0.64)
        self.assertEqual(verdict, "surface_only")

    def test_strategy_alone_never_forces_human_triage(self) -> None:
        # Two-hop is the dominant real-world path; strategy alone (absent
        # ambiguity or a confidence issue) must never force human triage.
        verdict, _reasons = compute_verdict(
            0.9, ["session-1"], "two_hop_doc_feature_session", [_quiet_flag()], 0.64,
        )
        self.assertEqual(verdict, "surface_only")


if __name__ == "__main__":
    unittest.main()
