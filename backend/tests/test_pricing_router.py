import unittest
import types
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend.application.context import Principal, RequestContext, TenancyContext, TraceContext, WorkspaceScope
from backend.application.ports import AuthorizationDecision
from backend.routers import pricing as pricing_router


class _AuthorizationPolicy:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[dict] = []

    async def authorize(self, context, *, action: str, resource: str | None = None):
        self.calls.append({"action": action, "resource": resource})
        return AuthorizationDecision(
            allowed=self.allowed,
            code="permission_allowed" if self.allowed else "permission_not_granted",
            reason="test policy",
        )


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
    def _request_context(self) -> RequestContext:
        return RequestContext(
            principal=Principal(subject="test-user", display_name="Test User", auth_mode="local"),
            workspace=WorkspaceScope(workspace_id="workspace-1", root_path=Path("/tmp/workspace")),
            project=None,
            runtime_profile="local",
            trace=TraceContext(request_id="req-1"),
            tenancy=TenancyContext(workspace_id="workspace-1"),
        )

    def _core_ports(self, *, allowed: bool = True):
        return types.SimpleNamespace(authorization_policy=_AuthorizationPolicy(allowed=allowed))

    async def test_catalog_endpoints_delegate_to_pricing_service(self) -> None:
        service = _FakePricingService()
        context = self._request_context()
        core_ports = self._core_ports()
        with patch.object(pricing_router.connection, "get_connection", return_value=object()), patch.object(
            pricing_router, "_service_for_db", return_value=service
        ):
            catalog = await pricing_router.get_pricing_catalog("Claude Code", context, core_ports)
            created = await pricing_router.upsert_pricing_catalog_entry(
                pricing_router.PricingCatalogUpsertRequest(
                    platformType="Claude Code",
                    modelId="claude-sonnet-4-6",
                    inputCostPerMillion=3.0,
                    outputCostPerMillion=15.0,
                ),
                context,
                core_ports,
            )
            synced = await pricing_router.sync_pricing_catalog("Claude Code", context, core_ports)
            reset = await pricing_router.reset_pricing_catalog_entry("Claude Code", "claude-sonnet-4-6", context, core_ports)
            deleted = await pricing_router.delete_pricing_catalog_entry("Claude Code", "claude-sonnet-4-6", context, core_ports)

        self.assertEqual(catalog[0]["projectId"], "__pricing_global__")
        self.assertEqual(created["modelId"], "claude-sonnet-4-6")
        self.assertEqual(synced["updatedEntries"], 2)
        self.assertEqual(reset["entry"]["modelId"], "claude-sonnet-4-6")
        self.assertEqual(deleted["status"], "ok")

    async def test_delete_endpoint_returns_bad_request_for_non_exact_model(self) -> None:
        service = _FakePricingService()
        context = self._request_context()
        core_ports = self._core_ports()
        with patch.object(pricing_router.connection, "get_connection", return_value=object()), patch.object(
            pricing_router, "_service_for_db", return_value=service
        ):
            with self.assertRaises(HTTPException) as raised:
                await pricing_router.delete_pricing_catalog_entry("Claude Code", "family:sonnet", context, core_ports)

        self.assertEqual(raised.exception.status_code, 400)

    async def test_upsert_requires_admin_pricing_update_permission(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await pricing_router.upsert_pricing_catalog_entry(
                pricing_router.PricingCatalogUpsertRequest(
                    platformType="Claude Code",
                    modelId="claude-sonnet-4-6",
                    inputCostPerMillion=3.0,
                    outputCostPerMillion=15.0,
                ),
                self._request_context(),
                self._core_ports(allowed=False),
            )

        self.assertEqual(raised.exception.status_code, 403)
