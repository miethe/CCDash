import types
import unittest
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.db.sqlite_migrations import run_migrations
from backend.models import SkillMeatConfigValidationRequest, SkillMeatProjectConfig, SkillMeatSyncRequest
from backend.routers import integrations as integrations_router
from backend.services.integrations.skillmeat_client import SkillMeatClient, SkillMeatClientError


class IntegrationsRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.project = types.SimpleNamespace(
            id="project-1",
            skillMeat=SkillMeatProjectConfig(
                enabled=True,
                baseUrl="http://skillmeat.local",
                projectId="sm-project",
                collectionId="default",
                aaaEnabled=False,
                apiKey="",
                requestTimeoutSeconds=2.0,
            ),
        )
        self.project_patch = patch.object(
            integrations_router.project_manager,
            "get_active_project",
            return_value=self.project,
        )
        self.conn_patch = patch.object(
            integrations_router.connection,
            "get_connection",
            new=AsyncMock(return_value=self.db),
        )
        self.project_patch.start()
        self.conn_patch.start()

    async def asyncTearDown(self) -> None:
        self.project_patch.stop()
        self.conn_patch.stop()
        await self.db.close()

    async def test_sync_and_list_definitions(self) -> None:
        def fake_request(endpoint: str, _query: dict[str, str]):
            if endpoint == "/api/v1/artifacts":
                return {"items": [{"id": "artifact:build-docs", "title": "Build Docs"}], "page_info": {"has_next_page": False, "end_cursor": None}}
            if endpoint == "/api/v1/workflows":
                return [{"id": "wf_1", "name": "Phase Execution"}]
            if endpoint == "/api/v1/context-modules":
                return {"items": [{"id": "cm_1", "name": "planning"}], "next_cursor": None, "has_more": False}
            return []

        with patch.object(SkillMeatClient, "_request_json", side_effect=fake_request):
            payload = await integrations_router.sync_skillmeat(SkillMeatSyncRequest())

        definitions = await integrations_router.list_skillmeat_definitions(definition_type=None, limit=500, offset=0)

        self.assertEqual(payload.totalDefinitions, 3)
        self.assertEqual(payload.countsByType["artifact"], 1)
        self.assertEqual(len(definitions), 3)
        self.assertEqual(definitions[0].projectId, "project-1")

    async def test_validate_config_reports_connection_and_project_status(self) -> None:
        with (
            patch.object(SkillMeatClient, "validate_base_url", AsyncMock(return_value={"items": []})),
            patch.object(SkillMeatClient, "get_project", AsyncMock(return_value={"id": "sm-project"})),
        ):
            payload = await integrations_router.validate_skillmeat_config(
                SkillMeatConfigValidationRequest(
                    baseUrl="http://skillmeat.local",
                    projectId="sm-project",
                    aaaEnabled=True,
                    apiKey="secret-token",
                    requestTimeoutSeconds=2.0,
                )
            )

        self.assertEqual(payload.baseUrl.state, "success")
        self.assertEqual(payload.projectMapping.state, "success")
        self.assertEqual(payload.auth.state, "success")

    async def test_validate_config_returns_warning_for_missing_project(self) -> None:
        with (
            patch.object(SkillMeatClient, "validate_base_url", AsyncMock(return_value={"items": []})),
            patch.object(
                SkillMeatClient,
                "get_project",
                AsyncMock(side_effect=SkillMeatClientError("missing", status_code=404, detail="Project not found")),
            ),
        ):
            payload = await integrations_router.validate_skillmeat_config(
                SkillMeatConfigValidationRequest(
                    baseUrl="http://skillmeat.local",
                    projectId="missing-project",
                    requestTimeoutSeconds=2.0,
                )
            )

        self.assertEqual(payload.baseUrl.state, "success")
        self.assertEqual(payload.projectMapping.state, "warning")

    async def test_list_observations_returns_empty_without_backfill(self) -> None:
        observations = await integrations_router.list_skillmeat_observations(limit=200, offset=0)

        self.assertEqual(observations, [])

    async def test_sync_returns_503_when_global_integration_disabled(self) -> None:
        with patch.object(
            integrations_router,
            "require_skillmeat_integration_enabled",
            side_effect=integrations_router.HTTPException(status_code=503, detail="disabled"),
        ):
            with self.assertRaises(integrations_router.HTTPException) as ctx:
                await integrations_router.sync_skillmeat(SkillMeatSyncRequest())

        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
