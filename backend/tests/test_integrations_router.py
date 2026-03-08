import types
import unittest
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.db.sqlite_migrations import run_migrations
from backend.models import SkillMeatProjectConfig, SkillMeatSyncRequest
from backend.routers import integrations as integrations_router
from backend.services.integrations.skillmeat_client import SkillMeatClient


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
                workspaceId="default",
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
            if endpoint == "/api/artifacts":
                return {"artifacts": [{"id": "artifact:build-docs", "title": "Build Docs"}]}
            if endpoint == "/api/workflows":
                return {"workflows": [{"id": "phase-execution", "title": "Phase Execution"}]}
            if endpoint == "/api/context-modules":
                return {"contextModules": [{"name": "planning"}]}
            return []

        with patch.object(SkillMeatClient, "_request_json", side_effect=fake_request):
            payload = await integrations_router.sync_skillmeat(SkillMeatSyncRequest())

        definitions = await integrations_router.list_skillmeat_definitions(definition_type=None, limit=500, offset=0)

        self.assertEqual(payload.totalDefinitions, 3)
        self.assertEqual(payload.countsByType["artifact"], 1)
        self.assertEqual(len(definitions), 3)
        self.assertEqual(definitions[0].projectId, "project-1")

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
