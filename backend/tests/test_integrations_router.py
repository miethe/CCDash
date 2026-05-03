import types
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
from fastapi import HTTPException

from backend.application.context import (
    AuthProviderMetadata,
    Principal,
    PrincipalSubject,
    ProjectScope,
    RequestContext,
    ScopeBinding,
    TenancyContext,
    TraceContext,
    WorkspaceScope,
)
from backend.application.ports import AuthorizationDecision
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
from backend.runtime_ports import build_core_ports
from backend.services.integrations.github_settings_store import GitHubSettingsStore
from backend.services.integrations.skillmeat_client import SkillMeatClient, SkillMeatClientError


class _DenyAuthorizationPolicy:
    def __init__(self, denied_action: str) -> None:
        self.denied_action = denied_action
        self.calls: list[dict[str, str | None]] = []

    async def authorize(self, context, *, action, resource=None):
        _ = context
        self.calls.append({"action": action, "resource": resource})
        if action == self.denied_action:
            return AuthorizationDecision(
                allowed=False,
                code="permission_not_granted",
                reason=f"{action} denied in test",
            )
        return AuthorizationDecision(allowed=True, code="permission_allowed")


class _TestWorkspaceRegistry:
    def __init__(self, active_project):
        self.projects = {active_project.id: active_project}
        self.active_project_id = active_project.id

    def get_project(self, project_id: str):
        return self.projects.get(project_id)

    def get_active_project(self):
        return self.projects.get(self.active_project_id)

    def resolve_scope(self, project_id: str | None = None):
        project = self.get_project(project_id) if project_id else self.get_active_project()
        if project is None:
            return None, None
        root_path = Path(getattr(project, "path", ".")).resolve(strict=False)
        return (
            WorkspaceScope(workspace_id="test-workspace", root_path=root_path),
            ProjectScope(
                project_id=str(project.id),
                project_name=str(getattr(project, "name", project.id)),
                root_path=root_path,
                sessions_dir=root_path / ".claude" / "sessions",
                docs_dir=root_path / "docs",
                progress_dir=root_path / ".claude" / "progress",
            ),
        )


class IntegrationsRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.project = types.SimpleNamespace(
            id="project-1",
            name="Project One",
            path=str(Path.cwd()),
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
        self.workspace_registry = _TestWorkspaceRegistry(self.project)
        self.core_ports = build_core_ports(self.db, workspace_registry=self.workspace_registry)
        self.request_context = RequestContext(
            principal=Principal(subject="test-user", display_name="Test User", auth_mode="local"),
            workspace=WorkspaceScope(workspace_id="test-workspace", root_path=Path.cwd()),
            project=ProjectScope(
                project_id=self.project.id,
                project_name=self.project.name,
                root_path=Path.cwd(),
                sessions_dir=Path.cwd() / ".claude" / "sessions",
                docs_dir=Path.cwd() / "docs",
                progress_dir=Path.cwd() / ".claude" / "progress",
            ),
            runtime_profile="local",
            trace=TraceContext(request_id="test-request", correlation_id="test-request", path="", method="TEST"),
            tenancy=TenancyContext(workspace_id="test-workspace", project_id=self.project.id),
        )
        self.project_patch = patch.object(
            integrations_router.project_manager,
            "get_active_project",
            return_value=self.project,
        )
        self.project_patch.start()

    async def asyncTearDown(self) -> None:
        self.project_patch.stop()
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
            payload = await integrations_router.sync_skillmeat(
                SkillMeatSyncRequest(),
                request_context=self.request_context,
                core_ports=self.core_ports,
            )

        definitions = await integrations_router.list_skillmeat_definitions(
            definition_type=None,
            limit=500,
            offset=0,
            request_context=self.request_context,
            core_ports=self.core_ports,
        )
        workflow_definitions = await integrations_router.list_skillmeat_definitions(
            definition_type="workflow",
            limit=500,
            offset=0,
            request_context=self.request_context,
            core_ports=self.core_ports,
        )

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

    async def test_sync_denies_without_skillmeat_sync_permission(self) -> None:
        policy = _DenyAuthorizationPolicy("integration.skillmeat:sync")
        denied_ports = replace(self.core_ports, authorization_policy=policy)

        with self.assertRaises(HTTPException) as ctx:
            await integrations_router.sync_skillmeat(
                SkillMeatSyncRequest(),
                request_context=self.request_context,
                core_ports=denied_ports,
            )

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail["action"], "integration.skillmeat:sync")
        self.assertEqual(ctx.exception.detail["resource"], "project:project-1")
        self.assertEqual(
            policy.calls,
            [{"action": "integration.skillmeat:sync", "resource": "project:project-1"}],
        )

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

        definitions = await integrations_router.list_skillmeat_definitions(
            definition_type=None,
            limit=500,
            offset=0,
            request_context=self.request_context,
            core_ports=self.core_ports,
        )
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
                ),
                request_context=self.request_context,
                core_ports=self.core_ports,
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
                ),
                request_context=self.request_context,
                core_ports=self.core_ports,
            )

        self.assertEqual(payload.baseUrl.state, "success")
        self.assertEqual(payload.projectMapping.state, "warning")

    async def test_validate_config_accepts_hosted_trust_metadata_without_api_key(self) -> None:
        hosted_context = RequestContext(
            principal=Principal(
                subject="oidc:user-1",
                display_name="Hosted User",
                auth_mode="oidc",
                provider=AuthProviderMetadata(
                    provider_id="oidc",
                    issuer="https://issuer.example.test",
                    audience="ccdash-api",
                    tenant_id="ent-1",
                    hosted=True,
                ),
                normalized_subject=PrincipalSubject(
                    subject="user-1",
                    provider_id="oidc",
                    issuer="https://issuer.example.test",
                ),
                scopes=("integration.skillmeat:sync",),
            ),
            workspace=self.request_context.workspace,
            project=self.request_context.project,
            runtime_profile="api",
            trace=TraceContext(request_id="req-hosted"),
            scope_bindings=(
                ScopeBinding(scope_type="enterprise", scope_id="ent-1", role="EA"),
                ScopeBinding(scope_type="project", scope_id="project-1", role="PM"),
            ),
            tenancy=TenancyContext(
                enterprise_id="ent-1",
                workspace_id="test-workspace",
                project_id="project-1",
            ),
        )
        with (
            patch.object(SkillMeatClient, "validate_base_url", AsyncMock(return_value={"items": []})),
            patch.object(SkillMeatClient, "get_project", AsyncMock(return_value={"id": "sm-project"})),
        ):
            payload = await integrations_router.validate_skillmeat_config(
                SkillMeatConfigValidationRequest(
                    baseUrl="http://skillmeat.local",
                    projectId="sm-project",
                    aaaEnabled=True,
                    apiKey="",
                    requestTimeoutSeconds=2.0,
                ),
                request_context=hosted_context,
                core_ports=self.core_ports,
            )

        self.assertEqual(payload.auth.state, "success")
        self.assertIn("Hosted trust metadata", payload.auth.message)

    async def test_refresh_runs_combined_pipeline_for_requested_project(self) -> None:
        other_project = types.SimpleNamespace(
            id="project-2",
            name="Project Two",
            path=str(Path.cwd()),
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
        self.workspace_registry.projects[other_project.id] = other_project
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
            patch.object(
                integrations_router.skillmeat_application_service,
                "refresh",
                AsyncMock(return_value=payload),
            ) as refresh_mock,
        ):
            response = await integrations_router.refresh_skillmeat(
                SkillMeatSyncRequest(projectId="project-2"),
                request_context=self.request_context,
                core_ports=self.core_ports,
            )

        refresh_mock.assert_awaited_once()
        self.assertEqual(response.projectId, "project-2")
        self.assertEqual(response.sync.totalDefinitions, 3)
        self.assertIsNotNone(response.backfill)
        self.assertEqual(response.backfill.observationsStored, 4)

    async def test_list_observations_returns_empty_without_backfill(self) -> None:
        observations = await integrations_router.list_skillmeat_observations(
            limit=200,
            offset=0,
            request_context=self.request_context,
            core_ports=self.core_ports,
        )

        self.assertEqual(observations, [])

    async def test_sync_returns_503_when_global_integration_disabled(self) -> None:
        with patch.object(
            integrations_router,
            "require_skillmeat_integration_enabled",
            side_effect=integrations_router.HTTPException(status_code=503, detail="disabled"),
        ):
            with self.assertRaises(integrations_router.HTTPException) as ctx:
                await integrations_router.sync_skillmeat(
                    SkillMeatSyncRequest(),
                    request_context=self.request_context,
                    core_ports=self.core_ports,
                )

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
                    ),
                    request_context=self.request_context,
                    core_ports=self.core_ports,
                )
                fetched = await integrations_router.get_github_settings(
                    request_context=self.request_context,
                    core_ports=self.core_ports,
                )

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
                    ),
                    request_context=self.request_context,
                    core_ports=self.core_ports,
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
                    ),
                    request_context=self.request_context,
                    core_ports=self.core_ports,
                )

        self.assertTrue(payload.canWrite)
        self.assertEqual(payload.status.state, "success")


if __name__ == "__main__":
    unittest.main()
