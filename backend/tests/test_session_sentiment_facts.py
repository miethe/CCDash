import unittest

from backend.services.session_sentiment_facts import (
    HEURISTIC_VERSION,
    build_session_sentiment_facts,
)


class SessionSentimentFactsBuilderTests(unittest.TestCase):
    def _session_payload(self) -> dict:
        return {
            "id": "session-1",
            "featureId": "feature-1",
            "rootSessionId": "session-root",
            "threadSessionId": "session-thread",
        }

    def test_negative_user_message_maps_to_negative_label(self) -> None:
        rows = [
            {
                "message_index": 2,
                "message_id": "msg-neg",
                "source_log_id": "log-neg",
                "role": "user",
                "content": "I am blocked, confused, and this is broken.",
                "source_provenance": "claude_code_jsonl",
            }
        ]

        facts = build_session_sentiment_facts(self._session_payload(), rows)

        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertEqual(fact["sentiment_label"], "negative")
        self.assertLess(fact["sentiment_score"], 0.0)
        self.assertEqual(fact["heuristic_version"], HEURISTIC_VERSION)
        self.assertEqual(fact["session_id"], "session-1")
        self.assertEqual(fact["feature_id"], "feature-1")
        self.assertEqual(fact["root_session_id"], "session-root")
        self.assertEqual(fact["thread_session_id"], "session-thread")
        self.assertEqual(fact["source_message_id"], "msg-neg")
        self.assertGreaterEqual(fact["confidence"], 0.6)
        self.assertTrue(fact["evidence_json"]["negativeCues"])

    def test_positive_user_message_maps_to_positive_label(self) -> None:
        rows = [
            {
                "message_index": 1,
                "message_id": "msg-pos",
                "source_log_id": "log-pos",
                "role": "user",
                "content": "Fixed and resolved. It works great now, thanks.",
                "source_provenance": "live_ingest",
            }
        ]

        facts = build_session_sentiment_facts(self._session_payload(), rows)

        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertEqual(fact["sentiment_label"], "positive")
        self.assertGreater(fact["sentiment_score"], 0.0)
        self.assertTrue(fact["evidence_json"]["positiveCues"])
        self.assertEqual(fact["evidence_json"]["sourceProvenance"], "live_ingest")

    def test_neutral_user_message_defaults_to_neutral(self) -> None:
        rows = [
            {
                "message_index": 3,
                "message_id": "msg-neu",
                "source_log_id": "log-neu",
                "role": "user",
                "content": "Can you summarize what happened in this run?",
            }
        ]

        facts = build_session_sentiment_facts(self._session_payload(), rows)

        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertEqual(fact["sentiment_label"], "neutral")
        self.assertEqual(fact["sentiment_score"], 0.0)
        self.assertFalse(fact["evidence_json"]["positiveCues"])
        self.assertFalse(fact["evidence_json"]["negativeCues"])

    def test_mixed_cues_map_to_mixed_label(self) -> None:
        rows = [
            {
                "message_index": 4,
                "message_id": "msg-mixed",
                "source_log_id": "log-mixed",
                "role": "user",
                "content": "Thanks, this is resolved, but I am still blocked by another issue.",
            }
        ]

        facts = build_session_sentiment_facts(self._session_payload(), rows)

        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertEqual(fact["sentiment_label"], "mixed")
        self.assertEqual(fact["sentiment_score"], 0.0)
        self.assertTrue(fact["evidence_json"]["positiveCues"])
        self.assertTrue(fact["evidence_json"]["negativeCues"])

    def test_non_user_messages_are_filtered_out(self) -> None:
        rows = [
            {
                "message_index": 0,
                "message_id": "msg-assistant",
                "source_log_id": "log-assistant",
                "role": "assistant",
                "content": "I am blocked and failing.",
            },
            {
                "message_index": 1,
                "message_id": "msg-tool",
                "source_log_id": "log-tool",
                "role": "tool",
                "content": "error output",
            },
            {
                "message_index": 2,
                "message_id": "msg-user",
                "source_log_id": "log-user",
                "role": "user",
                "content": "Good progress, this works.",
            },
        ]

        facts = build_session_sentiment_facts(self._session_payload(), rows)

        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["source_message_id"], "msg-user")
        self.assertEqual(facts[0]["sentiment_label"], "positive")


if __name__ == "__main__":
    unittest.main()
