"""
Phase 6 pricing-correctness regression fixture.

Verifies:
  - Known slug (claude-sonnet-4-5) → real priced cost, not unpriced.
  - Fable slug (claude-fable-4-5) → Fable-tier cost, NOT Sonnet rates, NOT null.
  - Novel claude-<family> slug (claude-nova-3) → cost_pricing_status="unpriced",
    display_cost_usd=None; no Sonnet-default leakage.
  - cost_pricing_status is present in every hydrate_session_observability response.
  - No Sonnet-default leakage: novel slug total_cost is 0.0, not a Sonnet estimate.

AC covered: AC-6.1 (T6-004).
"""
from __future__ import annotations

import unittest

import aiosqlite

from backend.db.repositories.pricing import SqlitePricingCatalogRepository
from backend.db.sqlite_migrations import run_migrations
from backend.services.pricing_catalog import PricingCatalogService

_SONNET_INPUT_RATE = 3.0   # per million – bundled family:sonnet rate
_SONNET_OUTPUT_RATE = 15.0
_FABLE_INPUT_RATE = 2.0    # per million – bundled family:fable rate (distinct from Sonnet)
_FABLE_OUTPUT_RATE = 10.0

# Base observability fields supplied to hydrate_session_observability
_EMPTY_OBS = {
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
}


class PricingP6RegressionTests(unittest.IsolatedAsyncioTestCase):
    """Regression fixture for Phase 6 pricing-correctness remediation."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.service = PricingCatalogService(
            SqlitePricingCatalogRepository(self.db),
            session_repo=None,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # ------------------------------------------------------------------
    # T6-001 / AC-6.1: unknown slug → unpriced, never Sonnet default
    # ------------------------------------------------------------------

    async def test_novel_claude_family_is_unpriced(self) -> None:
        """Novel claude-<family> slug must surface as cost_pricing_status='unpriced' with
        null display_cost_usd.  The parser-level Sonnet fallback ($0.123) must NOT appear."""
        enriched = await self.service.hydrate_session_observability(
            "project-1",
            {
                "platformType": "Claude Code",
                "model": "claude-nova-3-20260601",
                # Simulates a parser-level Sonnet-defaulted cost that must NOT leak through.
                "tokensIn": 10_000,
                "tokensOut": 5_000,
                "totalCost": 0.105,  # Sonnet-estimated value from parser (_estimate_cost fallback)
            },
            dict(_EMPTY_OBS),
        )

        self.assertEqual(
            enriched["cost_pricing_status"],
            "unpriced",
            "Novel claude-nova-3 must be flagged unpriced",
        )
        self.assertIsNone(
            enriched["display_cost_usd"],
            "display_cost_usd must be None for unpriced model (no Sonnet-default leakage)",
        )
        self.assertIsNone(
            enriched["recalculated_cost_usd"],
            "recalculated_cost_usd must be None for unpriced model",
        )
        self.assertEqual(
            enriched["cost_provenance"],
            "unpriced",
            "cost_provenance must be 'unpriced', not 'estimated'",
        )
        self.assertEqual(enriched["cost_confidence"], 0.0)
        self.assertEqual(enriched["pricing_model_source"], "")
        # total_cost must not inherit the Sonnet-estimated value
        self.assertEqual(
            enriched["total_cost"],
            0.0,
            "total_cost must be 0.0 for unpriced model, not the Sonnet-estimated value",
        )

    async def test_novel_slug_with_reported_cost_surfaces_reported_not_estimated(self) -> None:
        """If a novel slug HAS a reported_cost_usd (Anthropic-charged amount), that should
        be displayed.  cost_pricing_status is still 'unpriced' (catalog cannot verify)."""
        enriched = await self.service.hydrate_session_observability(
            "project-1",
            {
                "platformType": "Claude Code",
                "model": "claude-galaxy-1-20260601",
                "tokensIn": 5_000,
                "tokensOut": 2_000,
                "totalCost": 0.999,  # Sonnet-fallback from parser — must NOT be used
            },
            {
                **_EMPTY_OBS,
                "reported_cost_usd": 0.042,  # actual Anthropic charge
            },
        )

        self.assertEqual(enriched["cost_pricing_status"], "unpriced")
        self.assertAlmostEqual(enriched["display_cost_usd"], 0.042)
        self.assertEqual(enriched["cost_provenance"], "reported")
        self.assertEqual(enriched["pricing_model_source"], "")

    # ------------------------------------------------------------------
    # T6-002 / AC-6.1: Fable in catalog with correct tier
    # ------------------------------------------------------------------

    async def test_fable_uses_fable_tier_not_sonnet(self) -> None:
        """Fable model must resolve to family:fable with Fable-tier rates ($2.0/$10.0),
        which are different from Sonnet rates ($3.0/$15.0).
        Regression: Fable cost != Sonnet cost and != null."""
        tokens_in = 1_000_000
        tokens_out = 1_000_000

        fable_enriched = await self.service.hydrate_session_observability(
            "project-1",
            {
                "platformType": "Claude Code",
                "model": "claude-fable-4-5-20260601",
                "tokensIn": tokens_in,
                "tokensOut": tokens_out,
                "totalCost": 0.0,
            },
            dict(_EMPTY_OBS),
        )

        sonnet_enriched = await self.service.hydrate_session_observability(
            "project-1",
            {
                "platformType": "Claude Code",
                "model": "claude-sonnet-4-5-20260601",
                "tokensIn": tokens_in,
                "tokensOut": tokens_out,
                "totalCost": 0.0,
            },
            dict(_EMPTY_OBS),
        )

        # Fable must be priced (not unpriced)
        self.assertEqual(
            fable_enriched["cost_pricing_status"],
            "priced",
            "Fable model must be 'priced' (catalog entry exists)",
        )
        self.assertIsNotNone(
            fable_enriched["recalculated_cost_usd"],
            "Fable model must have a recalculated cost",
        )

        # Fable rates: $2.0 in + $10.0 out per million → $12.0 for 1M+1M
        expected_fable_cost = (tokens_in / 1e6 * _FABLE_INPUT_RATE) + (tokens_out / 1e6 * _FABLE_OUTPUT_RATE)
        self.assertAlmostEqual(
            fable_enriched["recalculated_cost_usd"],
            expected_fable_cost,
            places=4,
            msg=f"Fable cost should be ${expected_fable_cost} (Fable tier), not Sonnet",
        )

        # Sonnet rates: $3.0 in + $15.0 out per million → $18.0 for 1M+1M
        expected_sonnet_cost = (tokens_in / 1e6 * _SONNET_INPUT_RATE) + (tokens_out / 1e6 * _SONNET_OUTPUT_RATE)

        # Core regression: Fable cost != Sonnet cost
        self.assertNotAlmostEqual(
            fable_enriched["recalculated_cost_usd"],
            expected_sonnet_cost,
            places=4,
            msg="Fable cost must differ from Sonnet cost — no Sonnet-default leakage",
        )

        # Sonnet also priced
        self.assertEqual(sonnet_enriched["cost_pricing_status"], "priced")
        self.assertAlmostEqual(
            sonnet_enriched["recalculated_cost_usd"],
            expected_sonnet_cost,
            places=4,
        )

    # ------------------------------------------------------------------
    # AC-6.1: cost_pricing_status field always present
    # ------------------------------------------------------------------

    async def test_cost_pricing_status_always_present_in_response(self) -> None:
        """hydrate_session_observability must always include cost_pricing_status."""
        for model, expected_status in [
            ("claude-sonnet-4-6", "priced"),
            ("claude-fable-4-5", "priced"),
            ("claude-nova-9-9", "unpriced"),
        ]:
            with self.subTest(model=model):
                enriched = await self.service.hydrate_session_observability(
                    "project-1",
                    {
                        "platformType": "Claude Code",
                        "model": model,
                        "tokensIn": 100,
                        "tokensOut": 50,
                        "totalCost": 0.0,
                    },
                    dict(_EMPTY_OBS),
                )
                self.assertIn(
                    "cost_pricing_status",
                    enriched,
                    f"cost_pricing_status must be present for model={model}",
                )
                self.assertEqual(
                    enriched["cost_pricing_status"],
                    expected_status,
                    f"Expected {expected_status} for model={model}",
                )

    # ------------------------------------------------------------------
    # AC-6.1: No Sonnet-default leakage — comprehensive check
    # ------------------------------------------------------------------

    async def test_no_sonnet_default_leakage_for_arbitrary_novel_slug(self) -> None:
        """For any novel claude-X slug with a parser-injected totalCost (Sonnet fallback),
        total_cost in the enriched output must be 0.0, not the parser's estimate."""
        novel_models = [
            ("claude-omni-3-20260101", 0.105),
            ("claude-ultra-2", 0.200),
            ("claude-custom-family-9-9-9", 1.234),
        ]
        for model_raw, parser_estimate in novel_models:
            with self.subTest(model=model_raw):
                enriched = await self.service.hydrate_session_observability(
                    "project-x",
                    {
                        "platformType": "Claude Code",
                        "model": model_raw,
                        "tokensIn": 10_000,
                        "tokensOut": 5_000,
                        "totalCost": parser_estimate,
                    },
                    dict(_EMPTY_OBS),
                )
                self.assertEqual(
                    enriched["cost_pricing_status"],
                    "unpriced",
                    f"Novel model {model_raw!r} must be unpriced",
                )
                self.assertEqual(
                    enriched["total_cost"],
                    0.0,
                    f"Parser Sonnet-estimate {parser_estimate} must NOT leak into total_cost for {model_raw!r}",
                )
                self.assertIsNone(
                    enriched["display_cost_usd"],
                    f"display_cost_usd must be None for unpriced {model_raw!r}",
                )
