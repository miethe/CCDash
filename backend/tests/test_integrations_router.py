import types
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.db.factory import get_agentic_intelligence_repository
from backend.db.sqlite_migrations import run_migrations
from backend.models import (
    GitHubIntegrationSettingsUpdateRequest,
    GitHubPathValidationRequest,
    GitHubWriteCapabilityRequest,
    ProjectPathReference,
    SkillMeatConfigValidationRequest,
    SkillMeatProjectConfig,
    SkillMeatSyncRequest,
)
from backend.routers import integrations as integrations_router
from backend.services.integrations.github_settings_store import GitHubSettingsStore
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
                baseUrl="http://skillmeat.local/api/v1",
                webBaseUrl="http://skillmeat-web.local:3000",
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
        artifact = next(item for item in definitions if item.definitionType == "artifact" and item.externalId == "artifact:build-docs")
        self.assertEqual(
            artifact.sourceUrl,
            "http://skillmeat-web.local:3000/collection?collection=default&artifact=artifact%3Abuild-docs",
        )
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
        self.assertEqual(effective.sourceUrl, "http://skillmeat-web.local:3000/workflows/wf_project")
        self.assertEqual(
            effective.resolutionMetadata["resolvedContextModules"][0]["sourceUrl"],
            "http://skillmeat-web.local:3000/projects/sm-project/memory",
        )
        self.assertEqual(
            effective.resolutionMetadata["executionSummary"]["sourceUrl"],
            "http://skillmeat-web.local:3000/workflows/executions?workflow_id=wf_project",
        )
        bundle = next(item for item in definitions if item.definitionType == "bundle")
        self.assertEqual(bundle.resolutionMetadata["bundleSummary"]["artifactRefs"], ["skill:symbols"])
        self.assertEqual(bundle.sourceUrl, "http://skillmeat-web.local:3000/collection?collection=default")

    async def test_list_definitions_hides_links_when_web_app_url_is_unset(self) -> None:
        self.project.skillMeat.webBaseUrl = ""
        repo = get_agentic_intelligence_repository(self.db)
        source = await repo.upsert_definition_source(
            {
                "project_id": "project-1",
                "source_kind": "skillmeat",
                "enabled": True,
                "base_url": "http://skillmeat.local/api/v1",
                "project_mapping": {"projectId": "sm-project", "collectionId": "default"},
            }
        )
        await repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "workflow",
                "external_id": "wf_project",
                "display_name": "Phase Execution",
                "source_url": "http://old-skillmeat-web.local/workflows/wf_project",
                "resolution_metadata": {
                    "executionSummary": {
                        "count": 1,
                        "sourceUrl": "http://old-skillmeat-web.local/workflows/executions?workflow_id=wf_project",
                    },
                },
                "fetched_at": "2026-03-07T00:00:00Z",
            }
        )

        definitions = await integrations_router.list_skillmeat_definitions(definition_type=None, limit=500, offset=0)
        workflow = next(item for item in definitions if item.definitionType == "workflow")

        self.assertEqual(workflow.sourceUrl, "")
        self.assertEqual(workflow.resolutionMetadata["executionSummary"]["sourceUrl"], "")

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

    async def test_refresh_runs_combined_pipeline_for_requested_project(self) -> None:
        other_project = types.SimpleNamespace(
            id="project-2",
            skillMeat=SkillMeatProjectConfig(
                enabled=True,
                baseUrl="http://skillmeat-2.local",
                projectId="sm-project-2",
                collectionId="default",
                aaaEnabled=False,
                apiKey="",
                requestTimeoutSeconds=2.0,
            ),
        )
        payload = {
            "sync": {
                "projectId": "project-2",
                "source": {
                    "id": 7,
                    "project_id": "project-2",
                    "source_kind": "skillmeat",
                    "enabled": True,
                    "base_url": "http://skillmeat-2.local",
                    "project_mapping_json": {"projectId": "sm-project-2", "collectionId": "default"},
                    "feature_flags_json": {},
                    "last_synced_at": "2026-03-09T12:00:00Z",
                    "last_sync_status": "completed",
                    "last_sync_error": "",
                    "created_at": "2026-03-09T12:00:00Z",
                    "updated_at": "2026-03-09T12:00:00Z",
                },
                "totalDefinitions": 3,
                "countsByType": {"artifact": 1, "workflow": 1, "bundle": 1},
                "fetchedAt": "2026-03-09T12:00:00Z",
                "warnings": [],
            },
            "backfill": {
                "projectId": "project-2",
                "sessionsProcessed": 4,
                "observationsStored": 4,
                "skippedSessions": 0,
                "resolvedComponents": 9,
                "unresolvedComponents": 2,
                "generatedAt": "2026-03-09T12:02:00Z",
                "warnings": [],
            },
        }

        with (
            patch.object(integrations_router.project_manager, "get_project", return_value=other_project),
            patch.object(integrations_router, "refresh_skillmeat_cache", AsyncMock(return_value=payload)) as refresh_mock,
        ):
            response = await integrations_router.refresh_skillmeat(
                SkillMeatSyncRequest(projectId="project-2")
            )

        refresh_mock.assert_awaited_once()
        self.assertEqual(response.projectId, "project-2")
        self.assertEqual(response.sync.totalDefinitions, 3)
        self.assertIsNotNone(response.backfill)
        self.assertEqual(response.backfill.observationsStored, 4)

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

    async def test_github_settings_roundtrip_masks_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = GitHubSettingsStore(Path(tmpdir) / "integrations.json")
            with patch.object(integrations_router, "github_settings_store", store):
                payload = await integrations_router.update_github_settings(
                    GitHubIntegrationSettingsUpdateRequest(
                        enabled=True,
                        baseUrl="https://github.com",
                        username="git",
                        token="ghp_secret_123456",
                        cacheRoot=str(Path(tmpdir) / "cache"),
                        writeEnabled=True,
                    )
                )
                fetched = await integrations_router.get_github_settings()

        self.assertTrue(payload.tokenConfigured)
        self.assertNotIn("secret", payload.maskedToken.lower())
        self.assertTrue(fetched.tokenConfigured)
        self.assertEqual(fetched.cacheRoot, str(Path(tmpdir) / "cache"))

    async def test_validate_github_path_uses_workspace_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = GitHubSettingsStore(Path(tmpdir) / "integrations.json")
            store.save(
                GitHubIntegrationSettingsUpdateRequest(
                    enabled=True,
                    baseUrl="https://github.com",
                    username="git",
                    token="secret-token",
                    cacheRoot=str(Path(tmpdir) / "cache"),
                    writeEnabled=True,
                )
            )
            workspace_root = Path(tmpdir) / "workspace"
            (workspace_root / "plans").mkdir(parents=True)

            manager = types.SimpleNamespace(ensure_workspace=lambda *args, **kwargs: workspace_root)
            with (
                patch.object(integrations_router, "github_settings_store", store),
                patch.object(integrations_router, "_workspace_manager_for_settings", return_value=manager),
            ):
                payload = await integrations_router.validate_github_path(
                    GitHubPathValidationRequest(
                        reference=ProjectPathReference.model_validate(
                            {
                                "field": "root",
                                "sourceKind": "github_repo",
                                "repoRef": {
                                    "provider": "github",
                                    "repoUrl": "https://github.com/acme/repo",
                                    "repoSlug": "acme/repo",
                                    "branch": "main",
                                    "repoSubpath": "plans",
                                    "writeEnabled": True,
                                },
                            }
                        )
                    )
                )

        self.assertEqual(payload.status.state, "success")
        self.assertEqual(payload.resolvedLocalPath, str((workspace_root / "plans").resolve(strict=False)))

    async def test_check_github_write_capability_requires_flags_and_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = GitHubSettingsStore(Path(tmpdir) / "integrations.json")
            store.save(
                GitHubIntegrationSettingsUpdateRequest(
                    enabled=True,
                    baseUrl="https://github.com",
                    username="git",
                    token="secret-token",
                    cacheRoot=str(Path(tmpdir) / "cache"),
                    writeEnabled=True,
                )
            )
            with patch.object(integrations_router, "github_settings_store", store):
                payload = await integrations_router.check_github_write_capability(
                    GitHubWriteCapabilityRequest(
                        reference=ProjectPathReference.model_validate(
                            {
                                "field": "root",
                                "sourceKind": "github_repo",
                                "repoRef": {
                                    "provider": "github",
                                    "repoUrl": "https://github.com/acme/repo",
                                    "repoSlug": "acme/repo",
                                    "branch": "main",
                                    "repoSubpath": "",
                                    "writeEnabled": True,
                                },
                            }
                        )
                    )
                )

        self.assertTrue(payload.canWrite)
        self.assertEqual(payload.status.state, "success")


if __name__ == "__main__":
    unittest.main()
