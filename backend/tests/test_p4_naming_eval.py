"""P4 (hosted-llm-provider-strategy) -- unit tests for the naming-eval harness.

Covers the pure, no-network pieces of ``backend.scripts.p4_naming_eval``:
mechanical scoring (M1/M2/M3) and the pre-registered decision rule's
conjunctive short-circuit. Deliberately does not exercise ``_run_one``
(network call) or ``run`` (CLI orchestration) -- those require a live
Ollama/Anthropic endpoint and are covered by this leg's actual P4 run
instead of a mocked unit test.

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    python -m pytest backend/tests/test_p4_naming_eval.py -v
"""
from __future__ import annotations

import unittest

from backend.scripts.p4_naming_eval import (
    ArmMetrics,
    ArmSpec,
    CallResult,
    FrozenCase,
    build_frozen_sample,
    evaluate_decision_rule,
    score_arm,
)


class BuildFrozenSampleTests(unittest.TestCase):
    def test_cases_have_distinct_ids_and_nonempty_keywords(self) -> None:
        cases = build_frozen_sample()
        self.assertGreater(len(cases), 0)
        ids = [c.id for c in cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in cases:
            self.assertTrue(case.keywords)
            self.assertTrue(case.transcript_items)


class ScoreArmTests(unittest.TestCase):
    def setUp(self) -> None:
        self.arm = ArmSpec(id="a", kind="ollama", model="m")
        self.cases_by_id = {
            "c1": FrozenCase(id="c1", transcript_items=[], keywords=["fix-null-pointer", "session detail"]),
            "c2": FrozenCase(id="c2", transcript_items=[], keywords=["add-anthropic-adapter", "ica gateway"]),
        }

    def test_all_valid_grounded_unique_titles_scores_high(self) -> None:
        results = [
            CallResult(arm_id="a", case_id="c1", title="Fix Null Pointer Bug", raw="x", latency_s=1.0, error=None, input_chars=10, output_chars=5),
            CallResult(arm_id="a", case_id="c2", title="Add Anthropic Adapter", raw="y", latency_s=1.0, error=None, input_chars=10, output_chars=5),
        ]
        m = score_arm(self.arm, results, self.cases_by_id)
        self.assertEqual(m.m1_validity_rate, 1.0)
        self.assertEqual(m.m2_discriminability, 1.0)
        self.assertEqual(m.m3_keyword_grounding, 1.0)

    def test_degenerate_titles_reduce_discriminability(self) -> None:
        results = [
            CallResult(arm_id="a", case_id="c1", title="Session", raw="x", latency_s=1.0, error=None, input_chars=10, output_chars=5),
            CallResult(arm_id="a", case_id="c2", title="Session", raw="y", latency_s=1.0, error=None, input_chars=10, output_chars=5),
        ]
        m = score_arm(self.arm, results, self.cases_by_id)
        self.assertEqual(m.m1_validity_rate, 1.0)
        self.assertEqual(m.m2_discriminability, 0.0)

    def test_failed_calls_lower_validity_and_are_never_grounded(self) -> None:
        results = [
            CallResult(arm_id="a", case_id="c1", title=None, raw=None, latency_s=1.0, error="TimeoutError: x", input_chars=10, output_chars=0),
            CallResult(arm_id="a", case_id="c2", title="Add Anthropic Adapter", raw="y", latency_s=1.0, error=None, input_chars=10, output_chars=5),
        ]
        m = score_arm(self.arm, results, self.cases_by_id)
        self.assertEqual(m.n_failed, 1)
        self.assertEqual(m.m1_validity_rate, 0.5)
        self.assertEqual(m.m3_keyword_grounding, 1.0)  # only computed over the valid subset

    def test_ungrounded_titles_score_zero_on_m3(self) -> None:
        results = [
            CallResult(arm_id="a", case_id="c1", title="Completely Unrelated Words", raw="x", latency_s=1.0, error=None, input_chars=10, output_chars=5),
        ]
        m = score_arm(self.arm, [results[0]], {"c1": self.cases_by_id["c1"]})
        self.assertEqual(m.m3_keyword_grounding, 0.0)


class EvaluateDecisionRuleTests(unittest.TestCase):
    """Mirrors the SPIKE's pre-registered rule -- conjunctive, short-circuits on gate failure."""

    def _metrics(self, m1: float) -> ArmMetrics:
        return ArmMetrics(
            arm_id="x", n=10, n_failed=0, m1_validity_rate=m1, m2_discriminability=1.0,
            m3_keyword_grounding=1.0, p50_latency_s=1.0, p95_latency_s=1.0, est_cost_usd=0.0,
        )

    def test_gate1_failure_keeps_local_without_needing_m4(self) -> None:
        local = self._metrics(0.90)
        hosted = self._metrics(0.91)  # only +1pp, and not both >=95%
        result = evaluate_decision_rule(local=local, hosted=hosted, cost_ceiling_usd=None, m4_win_rate=None)
        self.assertEqual(result["verdict"], "keep_local")
        self.assertEqual(result["reason"], "gate1_m1_failed")

    def test_gate1_passes_via_ceiling_both_arms_at_95(self) -> None:
        local = self._metrics(0.96)
        hosted = self._metrics(0.97)
        result = evaluate_decision_rule(local=local, hosted=hosted, cost_ceiling_usd=None, m4_win_rate=0.7)
        self.assertTrue(result["gate1"])

    def test_gate3_cost_failure_keeps_local_without_needing_m4(self) -> None:
        local = self._metrics(0.80)
        hosted = self._metrics(0.90)  # +10pp clears gate 1
        hosted.est_cost_usd = 100.0
        result = evaluate_decision_rule(local=local, hosted=hosted, cost_ceiling_usd=1.0, m4_win_rate=None)
        self.assertEqual(result["verdict"], "keep_local")
        self.assertEqual(result["reason"], "gate3_cost_failed")

    def test_gates_1_and_3_pass_but_m4_missing_is_inconclusive(self) -> None:
        local = self._metrics(0.80)
        hosted = self._metrics(0.90)
        result = evaluate_decision_rule(local=local, hosted=hosted, cost_ceiling_usd=None, m4_win_rate=None)
        self.assertEqual(result["verdict"], "inconclusive_pending_m4")

    def test_full_rule_promotes_only_above_60_percent_win_rate(self) -> None:
        local = self._metrics(0.80)
        hosted = self._metrics(0.90)
        below = evaluate_decision_rule(local=local, hosted=hosted, cost_ceiling_usd=None, m4_win_rate=0.55)
        above = evaluate_decision_rule(local=local, hosted=hosted, cost_ceiling_usd=None, m4_win_rate=0.61)
        self.assertEqual(below["verdict"], "keep_local")
        self.assertEqual(above["verdict"], "promote_hosted")


if __name__ == "__main__":
    unittest.main()
