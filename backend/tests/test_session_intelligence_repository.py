import unittest

import aiosqlite

from backend.db.factory import get_session_intelligence_repository, get_session_repository
from backend.db.sqlite_migrations import run_migrations


class SessionIntelligenceRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.session_repo = get_session_repository(self.db)
        self.repo = get_session_intelligence_repository(self.db)
        await self.session_repo.upsert(
            {
                "id": "session-1",
                "status": "completed",
                "model": "gpt-5",
                "createdAt": "2026-04-02T00:00:00Z",
                "updatedAt": "2026-04-02T00:00:00Z",
            },
            "project-1",
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_replace_session_sentiment_facts_replaces_existing_rows(self) -> None:
        await self.repo.replace_session_sentiment_facts(
            "session-1",
            [
                {
                    "feature_id": "feature-1",
                    "root_session_id": "session-1",
                    "thread_session_id": "session-1",
                    "source_message_id": "msg-1",
                    "source_log_id": "log-1",
                    "message_index": 0,
                    "sentiment_label": "negative",
                    "sentiment_score": -0.7,
                    "confidence": 0.8,
                    "heuristic_version": "v1",
                    "evidence_json": {"cue": "blocked"},
                }
            ],
        )
        await self.repo.replace_session_sentiment_facts(
            "session-1",
            [
                {
                    "feature_id": "feature-1",
                    "root_session_id": "session-1",
                    "thread_session_id": "session-1",
                    "source_message_id": "msg-2",
                    "source_log_id": "log-2",
                    "message_index": 1,
                    "sentiment_label": "positive",
                    "sentiment_score": 0.7,
                    "confidence": 0.9,
                    "heuristic_version": "v1",
                    "evidence_json": {"cue": "fixed"},
                }
            ],
        )
        rows = await self.repo.list_session_sentiment_facts("session-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_message_id"], "msg-2")
        self.assertEqual(rows[0]["evidence_json"]["cue"], "fixed")

    async def test_replace_session_code_churn_facts_round_trips(self) -> None:
        await self.repo.replace_session_code_churn_facts(
            "session-1",
            [
                {
                    "feature_id": "feature-1",
                    "root_session_id": "session-1",
                    "thread_session_id": "session-1",
                    "file_path": "backend/service.py",
                    "first_source_log_id": "log-1",
                    "last_source_log_id": "log-2",
                    "first_message_index": 1,
                    "last_message_index": 4,
                    "touch_count": 3,
                    "distinct_edit_turn_count": 2,
                    "repeat_touch_count": 2,
                    "rewrite_pass_count": 1,
                    "additions_total": 10,
                    "deletions_total": 8,
                    "net_diff_total": 2,
                    "churn_score": 0.7,
                    "progress_score": 0.4,
                    "low_progress_loop": True,
                    "confidence": 0.85,
                    "heuristic_version": "v1",
                    "evidence_json": {"updates": 3},
                }
            ],
        )
        rows = await self.repo.list_session_code_churn_facts("session-1")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["low_progress_loop"])
        self.assertEqual(rows[0]["evidence_json"]["updates"], 3)

    async def test_replace_session_scope_drift_facts_round_trips(self) -> None:
        await self.repo.replace_session_scope_drift_facts(
            "session-1",
            [
                {
                    "feature_id": "feature-1",
                    "root_session_id": "session-1",
                    "thread_session_id": "session-1",
                    "planned_path_count": 2,
                    "actual_path_count": 3,
                    "matched_path_count": 2,
                    "out_of_scope_path_count": 1,
                    "drift_ratio": 0.3333,
                    "adherence_score": 0.6667,
                    "confidence": 0.85,
                    "heuristic_version": "v1",
                    "evidence_json": {"outOfScopePaths": ["docs/extra.md"]},
                }
            ],
        )
        rows = await self.repo.list_session_scope_drift_facts("session-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["feature_id"], "feature-1")
        self.assertEqual(rows[0]["evidence_json"]["outOfScopePaths"], ["docs/extra.md"])


if __name__ == "__main__":
    unittest.main()
