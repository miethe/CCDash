import unittest

import aiosqlite

from backend.db.repositories.pricing import SqlitePricingCatalogRepository
from backend.db.sqlite_migrations import run_migrations
from backend.services.pricing_catalog import PricingCatalogService


class PricingCatalogServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.service = PricingCatalogService(SqlitePricingCatalogRepository(self.db))

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_list_entries_includes_bundled_defaults_when_repo_empty(self) -> None:
        entries = await self.service.list_entries("project-1", "Claude Code")
        model_ids = {entry["modelId"] for entry in entries}
        self.assertIn("", model_ids)
        self.assertIn("claude-sonnet-4-5", model_ids)

    async def test_sync_preserves_locked_manual_override(self) -> None:
        await self.service.upsert_entry(
            "project-1",
            {
                "platformType": "Claude Code",
                "modelId": "claude-sonnet-4-5",
                "inputCostPerMillion": 4.0,
                "outputCostPerMillion": 20.0,
                "sourceType": "manual",
                "overrideLocked": True,
            },
        )

        payload = await self.service.sync_entries("project-1", "Claude Code")
        self.assertGreaterEqual(payload["updatedEntries"], 1)
        self.assertTrue(payload["warnings"])

        entries = await self.service.list_entries("project-1", "Claude Code")
        sonnet = next(entry for entry in entries if entry["modelId"] == "claude-sonnet-4-5")
        self.assertEqual(sonnet["inputCostPerMillion"], 4.0)
        self.assertEqual(sonnet["sourceType"], "manual")

    async def test_hydrate_session_observability_applies_recalculated_and_reported_costs(self) -> None:
        enriched = await self.service.hydrate_session_observability(
            "project-1",
            {
                "platformType": "Claude Code",
                "model": "claude-sonnet-4-5-20260101",
                "tokensIn": 100000,
                "tokensOut": 50000,
                "cacheCreationInputTokens": 20000,
                "cacheReadInputTokens": 10000,
                "totalCost": 1.0,
            },
            {
                "current_context_tokens": 100000,
                "context_window_size": 0,
                "context_utilization_pct": 0.0,
                "context_measurement_source": "transcript_latest_assistant_usage",
                "context_measured_at": "2026-03-12T12:00:00Z",
                "reported_cost_usd": 1.2,
                "recalculated_cost_usd": None,
                "display_cost_usd": None,
                "cost_provenance": "unknown",
                "cost_confidence": 0.0,
                "cost_mismatch_pct": None,
                "pricing_model_source": "",
                "total_cost": 1.0,
            },
        )

        self.assertEqual(enriched["context_window_size"], 200000)
        self.assertAlmostEqual(enriched["context_utilization_pct"], 50.0)
        self.assertAlmostEqual(enriched["recalculated_cost_usd"], 1.128)
        self.assertEqual(enriched["display_cost_usd"], 1.2)
        self.assertEqual(enriched["cost_provenance"], "reported")
        self.assertAlmostEqual(enriched["cost_mismatch_pct"], 0.06)
        self.assertEqual(enriched["pricing_model_source"], "claude-sonnet-4-5")
