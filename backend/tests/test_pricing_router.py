import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.routers import pricing as pricing_router


class _FakePricingService:
    async def list_catalog_entries(self, platform_type: str | None = None):
        return [{"projectId": "__pricing_global__", "platformType": platform_type or "Claude Code", "modelId": ""}]

    async def upsert_catalog_entry(self, entry_data: dict):
        return {"projectId": "__pricing_global__", **entry_data}

    async def sync_catalog_entries(self, platform_type: str):
        return {
            "projectId": "__pricing_global__",
            "platformType": platform_type,
            "syncedAt": "2026-03-12T12:00:00Z",
            "updatedEntries": 2,
            "warnings": [],
            "entries": [],
        }

    async def reset_catalog_entry(self, platform_type: str, model_id: str = ""):
        return {"projectId": "__pricing_global__", "platformType": platform_type, "modelId": model_id}

    async def delete_catalog_entry(self, platform_type: str, model_id: str):
        if model_id == "family:sonnet":
            raise ValueError("Only exact model overrides can be deleted.")


class PricingRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_endpoints_delegate_to_pricing_service(self) -> None:
        service = _FakePricingService()
        with patch.object(pricing_router.connection, "get_connection", return_value=object()), patch.object(
            pricing_router, "_service_for_db", return_value=service
        ):
            catalog = await pricing_router.get_pricing_catalog("Claude Code")
            created = await pricing_router.upsert_pricing_catalog_entry(
                pricing_router.PricingCatalogUpsertRequest(
                    platformType="Claude Code",
                    modelId="claude-sonnet-4-6",
                    inputCostPerMillion=3.0,
                    outputCostPerMillion=15.0,
                )
            )
            synced = await pricing_router.sync_pricing_catalog("Claude Code")
            reset = await pricing_router.reset_pricing_catalog_entry("Claude Code", "claude-sonnet-4-6")
            deleted = await pricing_router.delete_pricing_catalog_entry("Claude Code", "claude-sonnet-4-6")

        self.assertEqual(catalog[0]["projectId"], "__pricing_global__")
        self.assertEqual(created["modelId"], "claude-sonnet-4-6")
        self.assertEqual(synced["updatedEntries"], 2)
        self.assertEqual(reset["entry"]["modelId"], "claude-sonnet-4-6")
        self.assertEqual(deleted["status"], "ok")

    async def test_delete_endpoint_returns_bad_request_for_non_exact_model(self) -> None:
        service = _FakePricingService()
        with patch.object(pricing_router.connection, "get_connection", return_value=object()), patch.object(
            pricing_router, "_service_for_db", return_value=service
        ):
            with self.assertRaises(HTTPException) as raised:
                await pricing_router.delete_pricing_catalog_entry("Claude Code", "family:sonnet")

        self.assertEqual(raised.exception.status_code, 400)
