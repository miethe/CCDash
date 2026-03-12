import types
import unittest
from unittest.mock import patch

from backend.routers import pricing as pricing_router


class _FakePricingService:
    async def list_entries(self, project_id: str, platform_type: str | None = None):
        return [{"projectId": project_id, "platformType": platform_type or "Claude Code", "modelId": ""}]

    async def upsert_entry(self, project_id: str, entry_data: dict):
        return {"projectId": project_id, **entry_data}

    async def sync_entries(self, project_id: str, platform_type: str):
        return {
            "projectId": project_id,
            "platformType": platform_type,
            "syncedAt": "2026-03-12T12:00:00Z",
            "updatedEntries": 2,
            "warnings": [],
            "entries": [],
        }

    async def reset_entry(self, project_id: str, platform_type: str, model_id: str = ""):
        return {"projectId": project_id, "platformType": platform_type, "modelId": model_id}


class PricingRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_endpoints_delegate_to_pricing_service(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        service = _FakePricingService()
        with patch.object(pricing_router.project_manager, "get_active_project", return_value=project), patch.object(pricing_router.connection, "get_connection", return_value=object()), patch.object(pricing_router, "_service_for_db", return_value=service):
            catalog = await pricing_router.get_pricing_catalog("Claude Code")
            created = await pricing_router.upsert_pricing_catalog_entry(
                pricing_router.PricingCatalogUpsertRequest(
                    platformType="Claude Code",
                    modelId="claude-sonnet-4-5",
                    inputCostPerMillion=3.0,
                    outputCostPerMillion=15.0,
                )
            )
            synced = await pricing_router.sync_pricing_catalog("Claude Code")
            reset = await pricing_router.reset_pricing_catalog_entry("Claude Code", "claude-sonnet-4-5")

        self.assertEqual(catalog[0]["projectId"], "project-1")
        self.assertEqual(created["modelId"], "claude-sonnet-4-5")
        self.assertEqual(synced["updatedEntries"], 2)
        self.assertEqual(reset["entry"]["modelId"], "claude-sonnet-4-5")
