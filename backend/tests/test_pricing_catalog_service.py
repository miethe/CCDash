import unittest
from unittest.mock import patch

import aiosqlite

from backend.db.repositories.pricing import SqlitePricingCatalogRepository
from backend.db.sqlite_migrations import run_migrations
from backend.services.pricing_catalog import GLOBAL_PRICING_PROJECT_ID, PricingCatalogService


class _FakeSessionRepository:
    def __init__(self, rows=None) -> None:
        self.rows = rows or []

    async def get_model_facets(self, project_id, include_subagents=True):
        return list(self.rows)


class PricingCatalogServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.session_repo = _FakeSessionRepository()
        self.service = PricingCatalogService(
            SqlitePricingCatalogRepository(self.db),
            self.session_repo,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_list_entries_includes_platform_and_family_defaults_when_repo_empty(self) -> None:
        entries = await self.service.list_entries("project-1", "Claude Code")
        model_ids = {entry["modelId"] for entry in entries}
        self.assertIn("", model_ids)
        self.assertIn("family:sonnet", model_ids)
        self.assertIn("family:opus", model_ids)
        self.assertIn("family:haiku", model_ids)

    async def test_list_catalog_entries_adds_detected_models_with_family_fallback(self) -> None:
        self.session_repo.rows = [
            {"model": "claude-sonnet-4-6-20260301", "count": 3},
            {"model": "gpt-5.2-codex-20260301", "count": 1},
        ]

        claude_entries = await self.service.list_catalog_entries("Claude Code")
        sonnet = next(entry for entry in claude_entries if entry["modelId"] == "claude-sonnet-4-6")
        self.assertTrue(sonnet["isDetected"])
        self.assertEqual(sonnet["derivedFrom"], "claude-sonnet-4-6")
        self.assertEqual(sonnet["inputCostPerMillion"], 3.0)

        codex_entries = await self.service.list_catalog_entries("Codex")
        codex = next(entry for entry in codex_entries if entry["modelId"] == "gpt-5.2-codex")
        self.assertTrue(codex["isDetected"])
        self.assertEqual(codex["derivedFrom"], "gpt-5.2-codex")
        self.assertEqual(codex["inputCostPerMillion"], 1.75)

    async def test_sync_catalog_entries_persists_exact_fetched_models_and_updates_family_defaults(self) -> None:
        fetched = [
            {
                "platformType": "Claude Code",
                "modelId": "claude-sonnet-4-6",
                "inputCostPerMillion": 3.2,
                "outputCostPerMillion": 15.8,
                "cacheCreationCostPerMillion": 4.0,
                "cacheReadCostPerMillion": 0.32,
            },
            {
                "platformType": "Claude Code",
                "modelId": "claude-opus-4-6",
                "inputCostPerMillion": 5.1,
                "outputCostPerMillion": 25.2,
                "cacheCreationCostPerMillion": 6.4,
                "cacheReadCostPerMillion": 0.52,
            },
            {
                "platformType": "Claude Code",
                "modelId": "claude-haiku-4-5",
                "inputCostPerMillion": 1.1,
                "outputCostPerMillion": 5.3,
                "cacheCreationCostPerMillion": 1.4,
                "cacheReadCostPerMillion": 0.11,
            },
        ]

        with patch("backend.services.pricing_catalog.fetch_anthropic_pricing", return_value=fetched):
            payload = await self.service.sync_catalog_entries("Claude Code")

        self.assertEqual(payload["projectId"], GLOBAL_PRICING_PROJECT_ID)
        self.assertGreaterEqual(payload["updatedEntries"], 7)

        entries = await self.service.list_catalog_entries("Claude Code")
        exact = next(entry for entry in entries if entry["modelId"] == "claude-sonnet-4-6")
        family = next(entry for entry in entries if entry["modelId"] == "family:sonnet")
        self.assertTrue(exact["isPersisted"])
        self.assertEqual(exact["sourceType"], "fetched")
        self.assertFalse(exact["canDelete"])
        self.assertAlmostEqual(exact["inputCostPerMillion"], 3.2)
        self.assertAlmostEqual(family["inputCostPerMillion"], 3.2)
        self.assertEqual(family["sourceType"], "fetched")

    async def test_sync_preserves_locked_manual_override(self) -> None:
        await self.service.upsert_entry(
            "project-1",
            {
                "platformType": "Claude Code",
                "modelId": "family:sonnet",
                "inputCostPerMillion": 4.0,
                "outputCostPerMillion": 20.0,
                "sourceType": "manual",
                "overrideLocked": True,
            },
        )

        with patch("backend.services.pricing_catalog.fetch_anthropic_pricing", return_value=[]):
            payload = await self.service.sync_entries("project-1", "Claude Code")

        self.assertGreaterEqual(payload["updatedEntries"], 1)
        self.assertTrue(payload["warnings"])

        entries = await self.service.list_entries("project-1", "Claude Code")
        sonnet = next(entry for entry in entries if entry["modelId"] == "family:sonnet")
        self.assertEqual(sonnet["inputCostPerMillion"], 4.0)
        self.assertEqual(sonnet["sourceType"], "manual")

    async def test_delete_catalog_entry_removes_manual_exact_override(self) -> None:
        saved = await self.service.upsert_catalog_entry(
            {
                "platformType": "Claude Code",
                "modelId": "claude-sonnet-4-6",
                "inputCostPerMillion": 3.4,
                "outputCostPerMillion": 16.0,
            }
        )
        self.assertTrue(saved["canDelete"])

        await self.service.delete_catalog_entry("Claude Code", "claude-sonnet-4-6")

        entries = await self.service.list_catalog_entries("Claude Code")
        self.assertFalse(any(entry["modelId"] == "claude-sonnet-4-6" for entry in entries))

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

    async def test_hydrate_session_observability_falls_back_to_estimated_for_unsupported_model(self) -> None:
        enriched = await self.service.hydrate_session_observability(
            "project-1",
            {
                "platformType": "Claude Code",
                "model": "claude-unknown-9-9",
                "tokensIn": 1000,
                "tokensOut": 500,
                "totalCost": 0.123,
            },
            {
                "current_context_tokens": 0,
                "context_window_size": 0,
                "context_utilization_pct": 0.0,
                "reported_cost_usd": None,
                "recalculated_cost_usd": None,
                "display_cost_usd": None,
                "cost_provenance": "unknown",
                "cost_confidence": 0.0,
                "cost_mismatch_pct": None,
                "pricing_model_source": "",
            },
        )

        self.assertIsNone(enriched["recalculated_cost_usd"])
        self.assertEqual(enriched["display_cost_usd"], 0.123)
        self.assertEqual(enriched["cost_provenance"], "estimated")
        self.assertAlmostEqual(enriched["cost_confidence"], 0.45)
        self.assertEqual(enriched["pricing_model_source"], "")

    async def test_hydrate_session_observability_applies_fast_speed_multiplier_when_all_usage_is_fast(self) -> None:
        await self.service.upsert_entry(
            "project-1",
            {
                "platformType": "Claude Code",
                "modelId": "claude-sonnet-4-5",
                "inputCostPerMillion": 3.0,
                "outputCostPerMillion": 15.0,
                "cacheCreationCostPerMillion": 3.75,
                "cacheReadCostPerMillion": 0.3,
                "speedMultiplierFast": 2.0,
                "sourceType": "manual",
            },
        )

        enriched = await self.service.hydrate_session_observability(
            "project-1",
            {
                "platformType": "Claude Code",
                "model": "claude-sonnet-4-5-20260101",
                "tokensIn": 1000,
                "tokensOut": 1000,
                "cacheCreationInputTokens": 0,
                "cacheReadInputTokens": 0,
                "totalCost": 0.0,
                "sessionForensics": {
                    "usageSummary": {
                        "speedCounts": {"fast": 2},
                    }
                },
            },
            {
                "reported_cost_usd": None,
                "recalculated_cost_usd": None,
                "display_cost_usd": None,
                "cost_provenance": "unknown",
                "cost_confidence": 0.0,
                "cost_mismatch_pct": None,
                "pricing_model_source": "",
            },
        )

        self.assertAlmostEqual(enriched["recalculated_cost_usd"], 0.036)
        self.assertEqual(enriched["cost_provenance"], "recalculated")
