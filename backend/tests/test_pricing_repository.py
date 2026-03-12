import unittest

import aiosqlite

from backend.db.repositories.pricing import SqlitePricingCatalogRepository
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations


class PricingCatalogRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.pricing_repo = SqlitePricingCatalogRepository(self.db)
        self.session_repo = SqliteSessionRepository(self.db)
        await self.session_repo.upsert(
            {
                "id": "S-1",
                "taskId": "",
                "status": "completed",
                "model": "claude-sonnet-4-5-20260101",
                "platformType": "Claude Code",
                "platformVersion": "2.1.52",
                "platformVersions": ["2.1.52"],
                "platformVersionTransitions": [],
                "durationSeconds": 60,
                "tokensIn": 100,
                "tokensOut": 50,
                "totalCost": 0.0,
                "startedAt": "2026-03-12T12:00:00Z",
                "endedAt": "2026-03-12T12:01:00Z",
                "sourceFile": "/tmp/session.jsonl",
            },
            "project-1",
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_pricing_catalog_entry_round_trips(self) -> None:
        saved = await self.pricing_repo.upsert_entry(
            {
                "platformType": "Claude Code",
                "modelId": "claude-sonnet-4-5",
                "contextWindowSize": 200000,
                "inputCostPerMillion": 3.0,
                "outputCostPerMillion": 15.0,
                "cacheCreationCostPerMillion": 3.75,
                "cacheReadCostPerMillion": 0.3,
                "speedMultiplierFast": 1.0,
                "sourceType": "manual",
                "overrideLocked": True,
                "syncStatus": "manual",
            },
            "project-1",
        )
        self.assertEqual(saved["project_id"], "project-1")
        self.assertEqual(saved["platform_type"], "Claude Code")
        self.assertEqual(saved["model_id"], "claude-sonnet-4-5")
        self.assertEqual(saved["context_window_size"], 200000)
        self.assertEqual(saved["input_cost_per_million"], 3.0)
        self.assertEqual(saved["output_cost_per_million"], 15.0)
        self.assertEqual(saved["override_locked"], 1)

        rows = await self.pricing_repo.list_entries("project-1", "Claude Code")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["model_id"], "claude-sonnet-4-5")

        await self.pricing_repo.delete_entry("project-1", "Claude Code", "claude-sonnet-4-5")
        rows = await self.pricing_repo.list_entries("project-1", "Claude Code")
        self.assertEqual(rows, [])

    async def test_session_observability_fields_update_round_trips(self) -> None:
        await self.session_repo.update_observability_fields(
            "S-1",
            {
                "current_context_tokens": 120,
                "context_window_size": 200000,
                "context_utilization_pct": 0.06,
                "context_measurement_source": "transcript_latest_assistant_usage",
                "context_measured_at": "2026-03-12T12:01:00Z",
                "reported_cost_usd": 0.42,
                "recalculated_cost_usd": 0.39,
                "display_cost_usd": 0.42,
                "cost_provenance": "reported",
                "cost_confidence": 0.97,
                "cost_mismatch_pct": 0.0769,
                "pricing_model_source": "claude-sonnet-4-5",
                "total_cost": 0.42,
            },
        )
        row = await self.session_repo.get_by_id("S-1")
        assert row is not None
        self.assertEqual(row["current_context_tokens"], 120)
        self.assertEqual(row["context_window_size"], 200000)
        self.assertAlmostEqual(row["context_utilization_pct"], 0.06)
        self.assertEqual(row["context_measurement_source"], "transcript_latest_assistant_usage")
        self.assertEqual(row["reported_cost_usd"], 0.42)
        self.assertEqual(row["recalculated_cost_usd"], 0.39)
        self.assertEqual(row["display_cost_usd"], 0.42)
        self.assertEqual(row["cost_provenance"], "reported")
        self.assertAlmostEqual(row["cost_confidence"], 0.97)
        self.assertAlmostEqual(row["cost_mismatch_pct"], 0.0769)
        self.assertEqual(row["pricing_model_source"], "claude-sonnet-4-5")
        self.assertEqual(row["total_cost"], 0.42)
