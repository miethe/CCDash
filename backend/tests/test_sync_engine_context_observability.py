import unittest

import aiosqlite

from backend.db.sqlite_migrations import run_migrations
from backend.db.sync_engine import SyncEngine


class SyncEngineContextObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.sync_engine = SyncEngine(self.db)
        await self.sync_engine.session_repo.upsert(
            {
                "id": "S-ctx-1",
                "taskId": "",
                "status": "completed",
                "model": "claude-sonnet-4-5-20260101",
                "platformType": "Claude Code",
                "platformVersion": "2.1.52",
                "platformVersions": ["2.1.52"],
                "platformVersionTransitions": [],
                "durationSeconds": 60,
                "tokensIn": 100000,
                "tokensOut": 25000,
                "totalCost": 0.675,
                "startedAt": "2026-03-12T12:00:00Z",
                "endedAt": "2026-03-12T12:01:00Z",
                "sourceFile": "/tmp/session.jsonl",
            },
            "project-1",
        )
        await self.sync_engine.session_repo.upsert_logs(
            "S-ctx-1",
            [
                {
                    "id": "log-1",
                    "timestamp": "2026-03-12T12:01:00Z",
                    "speaker": "agent",
                    "type": "message",
                    "content": "Latest usage snapshot",
                    "metadata": {
                        "inputTokens": 90,
                        "cacheCreationInputTokens": 30,
                        "cacheReadInputTokens": 20,
                    },
                }
            ],
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_backfill_session_observability_fields_derives_context_from_logs(self) -> None:
        stats = await self.sync_engine._backfill_session_observability_fields_for_project("project-1")
        self.assertEqual(stats, {"sessions": 1})

        row = await self.sync_engine.session_repo.get_by_id("S-ctx-1")
        assert row is not None
        self.assertEqual(row["current_context_tokens"], 140)
        self.assertEqual(row["context_window_size"], 200000)
        self.assertAlmostEqual(row["context_utilization_pct"], 0.07)
        self.assertEqual(row["context_measurement_source"], "transcript_latest_assistant_usage")
        self.assertEqual(row["context_measured_at"], "2026-03-12T12:01:00Z")
        self.assertAlmostEqual(row["recalculated_cost_usd"], 0.675)
        self.assertAlmostEqual(row["display_cost_usd"], 0.675)
        self.assertEqual(row["cost_provenance"], "recalculated")
        self.assertEqual(row["pricing_model_source"], "claude-sonnet-4-5")
        self.assertAlmostEqual(row["total_cost"], 0.675)

        repeat_stats = await self.sync_engine._backfill_session_observability_fields_for_project("project-1")
        self.assertEqual(repeat_stats, {"sessions": 0})
