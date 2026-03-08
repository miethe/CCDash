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
        def fake_request(endpoint: str, query: dict[str, str] | None, **_kwargs):
            if endpoint == "/api/v1/artifacts":
                return {"items": [{"id": "artifact:build-docs", "title": "Build Docs"}], "page_info": {"has_next_page": False, "end_cursor": None}}
            if endpoint == "/api/v1/workflows":
                if query.get("project_id") == "sm-project":
                    return [{"id": "wf_project", "name": "Phase Execution", "project_id": "sm-project"}]
                return [{"id": "wf_global", "name": "Phase Execution", "project_id": None}]
            if endpoint == "/api/v1/workflows/wf_project":
                return {
                    "id": "wf_project",
                    "name": "Phase Execution",
                    "project_id": "sm-project",
                    "definition": "name: Phase Execution\nstages:\n  - id: planning\n    type: agent\n    agent: agent:planner\n  - id: implementation\n    type: fan_out\n    depends_on: [planning]\n    stages:\n      - id: backend\n        type: agent\n        agent: skill:symbols\n      - id: context\n        type: agent\n        memory: ctx:planning\n",
                }
            if endpoint == "/api/v1/workflows/wf_project/plan":
                return {
                    "estimated_batches": 2,
                    "estimated_stages": 3,
                    "has_gates": False,
                    "execution_order": [
                        {"batch_index": 0, "stages": [{"stage_id": "planning", "stage_type": "agent", "depends_on": []}]},
                        {"batch_index": 1, "stages": [{"stage_id": "backend", "stage_type": "agent", "depends_on": ["planning"]}]},
                    ],
                }
            if endpoint == "/api/v1/workflows/wf_global":
                return {
                    "id": "wf_global",
                    "name": "Phase Execution",
                    "project_id": None,
                    "definition": "name: Phase Execution\nstages:\n  - id: planning\n    type: agent\n    agent: agent:planner\n",
                }
            if endpoint == "/api/v1/workflow-executions":
                if query.get("workflow_id") == "wf_project":
                    return [
                        {
                            "id": "exec_1",
                            "workflow_id": "wf_project",
                            "status": "completed",
                            "started_at": "2026-03-07T14:00:00Z",
                            "completed_at": "2026-03-07T15:23:00Z",
                        }
                    ]
                return []
            if endpoint == "/api/v1/workflow-executions/exec_1":
                return {
                    "id": "exec_1",
                    "workflow_id": "wf_project",
                    "status": "completed",
                    "started_at": "2026-03-07T14:00:00Z",
                    "completed_at": "2026-03-07T15:23:00Z",
                    "steps": [
                        {"id": "step_1", "stage_id": "planning", "stage_type": "agent", "status": "completed"},
                        {"id": "step_2", "stage_id": "approval", "stage_type": "gate", "status": "completed"},
                    ],
                }
            if endpoint == "/api/v1/context-modules":
                return {"items": [{"id": "cm_1", "name": "planning"}], "next_cursor": None, "has_more": False}
            if endpoint == "/api/v1/context-packs/preview":
                return {
                    "items": [
                        {"id": "mi_1", "type": "decision", "estimated_tokens": 45},
                        {"id": "mi_2", "type": "gotcha", "estimated_tokens": 52},
                    ],
                    "total_items": 2,
                    "total_estimated_tokens": 97,
                    "budget_tokens": 4000,
                    "budget_remaining": 3903,
                }
            if endpoint == "/api/v1/bundles":
                return {"bundles": [{"bundle_id": "bundle_python", "name": "Python Essentials", "description": "Python bundle", "author": "system", "created_at": "2026-03-08T00:00:00Z", "artifact_count": 1, "total_size_bytes": 10, "source": "created"}], "total": 1}
            if endpoint == "/api/v1/bundles/bundle_python":
                return {"bundle_id": "bundle_python", "metadata": {"name": "Python Essentials", "version": "1.0.0"}, "artifacts": [{"type": "skill", "name": "symbols"}], "bundle_hash": "sha256:abc", "total_size_bytes": 10, "total_files": 1, "source": "created"}
            return []

        with patch.object(SkillMeatClient, "_request_json", side_effect=fake_request):
            payload = await integrations_router.sync_skillmeat(SkillMeatSyncRequest())

        definitions = await integrations_router.list_skillmeat_definitions(definition_type=None, limit=500, offset=0)
        workflow_definitions = await integrations_router.list_skillmeat_definitions(definition_type="workflow", limit=500, offset=0)

        self.assertEqual(payload.totalDefinitions, 5)
        self.assertEqual(payload.countsByType["artifact"], 1)
        self.assertEqual(payload.countsByType["bundle"], 1)
        self.assertEqual(len(definitions), 5)
        self.assertEqual(definitions[0].projectId, "project-1")
        self.assertEqual(len(workflow_definitions), 2)
        effective = next(item for item in workflow_definitions if item.externalId == "wf_project")
        overridden = next(item for item in workflow_definitions if item.externalId == "wf_global")
        self.assertTrue(effective.resolutionMetadata["isEffective"])
        self.assertFalse(overridden.resolutionMetadata["isEffective"])
        self.assertEqual(effective.resolutionMetadata["effectiveWorkflowId"], "wf_project")
        self.assertIn("skill:symbols", effective.resolutionMetadata["swdlSummary"]["artifactRefs"])
        self.assertIn("ctx:planning", effective.resolutionMetadata["swdlSummary"]["contextRefs"])
        self.assertEqual(effective.resolutionMetadata["planSummary"]["batchCount"], 2)
        self.assertEqual(effective.resolutionMetadata["contextSummary"]["resolved"], 1)
        self.assertEqual(effective.resolutionMetadata["resolvedContextModules"][0]["moduleId"], "cm_1")
        self.assertEqual(effective.resolutionMetadata["resolvedContextModules"][0]["previewSummary"]["totalTokens"], 97)
        self.assertEqual(effective.resolutionMetadata["executionSummary"]["count"], 1)
        self.assertEqual(effective.resolutionMetadata["recentExecutions"][0]["gateStepCount"], 1)
        bundle = next(item for item in definitions if item.definitionType == "bundle")
        self.assertEqual(bundle.resolutionMetadata["bundleSummary"]["artifactRefs"], ["skill:symbols"])

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
