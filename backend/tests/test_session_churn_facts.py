import unittest

from backend.services.session_churn_facts import (
    HEURISTIC_VERSION,
    build_session_code_churn_facts,
)


class SessionChurnFactsBuilderTests(unittest.TestCase):
    def test_ordinary_iterative_edits_do_not_flag_low_progress_loop(self) -> None:
        session_payload = {
            "id": "session-iterative",
            "featureId": "feature-a",
            "rootSessionId": "root-1",
            "threadSessionId": "thread-1",
        }
        canonical_rows = [
            {"source_log_id": "log-1", "message_index": 1},
            {"source_log_id": "log-2", "message_index": 2},
            {"source_log_id": "log-3", "message_index": 3},
        ]
        file_updates = [
            {"filePath": "src/main.ts", "source_log_id": "log-1", "action": "update", "additions": 6, "deletions": 1},
            {"filePath": "src/main.ts", "source_log_id": "log-2", "action": "update", "additions": 4, "deletions": 1},
            {"filePath": "src/main.ts", "source_log_id": "log-3", "action": "update", "additions": 3, "deletions": 0},
        ]

        facts = build_session_code_churn_facts(session_payload, canonical_rows, file_updates)

        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertEqual(fact["session_id"], "session-iterative")
        self.assertEqual(fact["feature_id"], "feature-a")
        self.assertEqual(fact["file_path"], "src/main.ts")
        self.assertEqual(fact["touch_count"], 3)
        self.assertEqual(fact["repeat_touch_count"], 2)
        self.assertEqual(fact["rewrite_pass_count"], 0)
        self.assertFalse(fact["low_progress_loop"])
        self.assertGreater(fact["progress_score"], 0.55)
        self.assertLess(fact["churn_score"], 0.6)
        self.assertEqual(fact["heuristic_version"], HEURISTIC_VERSION)

    def test_true_churn_loop_is_flagged(self) -> None:
        session_payload = {
            "id": "session-loop",
            "rootSessionId": "root-loop",
            "threadSessionId": "thread-loop",
        }
        canonical_rows = [
            {"source_log_id": "log-1", "message_index": 1},
            {"source_log_id": "log-2", "message_index": 2},
            {"source_log_id": "log-3", "message_index": 3},
            {"source_log_id": "log-4", "message_index": 4},
            {"source_log_id": "log-5", "message_index": 5},
        ]
        file_updates = [
            {"filePath": "src/churn.ts", "source_log_id": "log-1", "action": "rewrite", "additions": 5, "deletions": 5},
            {"filePath": "src/churn.ts", "source_log_id": "log-2", "action": "replace", "additions": 4, "deletions": 4},
            {"filePath": "src/churn.ts", "source_log_id": "log-3", "action": "rewrite", "additions": 3, "deletions": 3},
            {"filePath": "src/churn.ts", "source_log_id": "log-4", "action": "replace", "additions": 6, "deletions": 6},
            {"filePath": "src/churn.ts", "source_log_id": "log-5", "action": "rewrite", "additions": 2, "deletions": 2},
        ]

        facts = build_session_code_churn_facts(session_payload, canonical_rows, file_updates)

        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertEqual(fact["touch_count"], 5)
        self.assertEqual(fact["repeat_touch_count"], 4)
        self.assertEqual(fact["rewrite_pass_count"], 5)
        self.assertTrue(fact["low_progress_loop"])
        self.assertGreaterEqual(fact["churn_score"], 0.65)
        self.assertLessEqual(fact["progress_score"], 0.45)
        self.assertGreaterEqual(fact["confidence"], 0.8)

    def test_transcript_order_tie_breaking_uses_canonical_source_log_mapping(self) -> None:
        session_payload = {"id": "session-order"}
        canonical_rows = [
            {"source_log_id": "log-b", "message_index": 2},
            {"source_log_id": "log-a", "message_index": 1},
        ]
        file_updates = [
            {"filePath": "src/order.ts", "source_log_id": "log-b", "action": "update", "additions": 1, "deletions": 0},
            {"filePath": "src/order.ts", "source_log_id": "log-a", "action": "update", "additions": 1, "deletions": 0},
        ]

        facts = build_session_code_churn_facts(session_payload, canonical_rows, file_updates)

        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertEqual(fact["first_source_log_id"], "log-a")
        self.assertEqual(fact["last_source_log_id"], "log-b")
        self.assertEqual(fact["first_message_index"], 1)
        self.assertEqual(fact["last_message_index"], 2)
        self.assertEqual(fact["evidence_json"]["touchedMessageIndexes"], [1, 2])

    def test_multi_file_sessions_and_evidence_payload(self) -> None:
        session_payload = {"id": "session-multi", "featureId": "feature-z"}
        canonical_rows = [
            {"source_log_id": "log-1", "message_index": 1},
            {"source_log_id": "log-2", "message_index": 2},
            {"source_log_id": "log-3", "message_index": 3},
        ]
        file_updates = [
            {"filePath": "src/a.ts", "source_log_id": "log-1", "action": "update", "additions": 3, "deletions": 1},
            {"filePath": "src/a.ts", "source_log_id": "log-2", "action": "rewrite", "additions": 2, "deletions": 2},
            {"filePath": "src/b.ts", "source_log_id": "log-2", "action": "update", "additions": 5, "deletions": 0},
            {"filePath": "src/b.ts", "source_log_id": "log-3", "action": "update", "additions": 1, "deletions": 0},
        ]

        facts = build_session_code_churn_facts(session_payload, canonical_rows, file_updates)

        self.assertEqual(len(facts), 2)
        self.assertEqual([fact["file_path"] for fact in facts], ["src/a.ts", "src/b.ts"])

        fact_a = facts[0]
        evidence_a = fact_a["evidence_json"]
        self.assertIn("updateSummary", evidence_a)
        self.assertIn("touchedSourceLogIds", evidence_a)
        self.assertIn("loopSignals", evidence_a)
        self.assertEqual(evidence_a["touchedSourceLogIds"], ["log-1", "log-2"])
        self.assertEqual(evidence_a["loopSignals"]["touchCount"], 2)
        self.assertEqual(evidence_a["loopSignals"]["distinctEditTurnCount"], 2)
        self.assertEqual(evidence_a["updateSummary"][0]["sourceLogId"], "log-1")
        self.assertEqual(evidence_a["updateSummary"][1]["sourceLogId"], "log-2")

        fact_b = facts[1]
        self.assertEqual(fact_b["touch_count"], 2)
        self.assertFalse(fact_b["low_progress_loop"])


if __name__ == "__main__":
    unittest.main()
