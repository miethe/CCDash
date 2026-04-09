import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.db.sqlite_migrations import run_migrations
from backend.models import SessionMemoryDraftGenerateRequest, SessionMemoryDraftPublishRequest, SessionMemoryDraftReviewRequest
from backend.routers import integrations as integrations_router


class _FakeIdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test:operator", display_name="Test Operator", auth_mode="test")


class _FakeAuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _FakeWorkspaceRegistry:
    def __init__(self, project) -> None:
        self.project = project

    def get_project(self, project_id):
        if getattr(self.project, "id", "") == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project


class _FakeJobScheduler:
    def schedule(self, job, *, name=None):
        _ = name
        return job


class _FakeIntegrationClient:
    async def invoke(self, integration, operation, payload=None):
        _ = integration, operation, payload
        return {}


def _request_context(project_id: str = "project-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test:operator", display_name="Test Operator", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Project 1",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/sessions"),
            docs_dir=Path("/tmp/docs"),
            progress_dir=Path("/tmp/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-memory-drafts"),
    )


def _core_ports(storage, project) -> CorePorts:
    return CorePorts(
        identity_provider=_FakeIdentityProvider(),
        authorization_policy=_FakeAuthorizationPolicy(),
        workspace_registry=_FakeWorkspaceRegistry(project),
        storage=storage,
        job_scheduler=_FakeJobScheduler(),
        integration_client=_FakeIntegrationClient(),
    )


class SkillMeatMemoryDraftRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.storage = LocalStorageUnitOfWork(self.db)
        self.project = types.SimpleNamespace(
            id="project-1",
            name="Project 1",
            skillMeat=types.SimpleNamespace(
                enabled=True,
                baseUrl="http://skillmeat.local",
                projectId="sm-project",
                aaaEnabled=False,
                apiKey="",
                requestTimeoutSeconds=2.0,
            ),
        )
        self.ports = _core_ports(self.storage, self.project)
        self.context = _request_context()

        await self.storage.sessions().upsert(
            {
                "id": "session-1",
                "taskId": "feature-a",
                "status": "completed",
                "model": "gpt-5",
                "createdAt": "2026-04-03T10:00:00Z",
                "updatedAt": "2026-04-03T10:05:00Z",
            },
            "project-1",
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_generate_list_review_and_publish_memory_drafts(self) -> None:
        generated_row = await self.storage.agentic_intelligence().upsert_session_memory_draft(
            {
                "project_id": "project-1",
                "session_id": "session-1",
                "title": "Scope reminder",
                "memory_type": "constraint",
                "module_name": "Workflow feature-a memory",
                "module_description": "Generated from successful sessions.",
                "content": "Keep the changes inside the planned scope.",
                "content_hash": "hash-1",
                "evidence": {"source": "session_scope_drift_facts"},
            }
        )

        with patch.object(
            integrations_router.skillmeat_application_service,
            "generate_memory_drafts",
            AsyncMock(
                return_value={
                    "projectId": "project-1",
                    "generatedAt": "2026-04-04T12:00:00Z",
                    "sessionsConsidered": 1,
                    "draftsCreated": 1,
                    "draftsUpdated": 0,
                    "draftsSkipped": 0,
                    "items": [generated_row],
                }
            ),
        ):
            generated = await integrations_router.generate_skillmeat_memory_drafts(
                SessionMemoryDraftGenerateRequest(sessionId="session-1", limit=25, actor="system"),
                project_id="project-1",
                request_context=self.context,
                core_ports=self.ports,
            )

        listed = await integrations_router.list_skillmeat_memory_drafts(
            project_id="project-1",
            session_id="session-1",
            status=None,
            limit=25,
            offset=0,
            request_context=self.context,
            core_ports=self.ports,
        )
        reviewed = await integrations_router.review_skillmeat_memory_draft(
            int(generated_row["id"]),
            SessionMemoryDraftReviewRequest(decision="approved", actor="operator", notes="Ship it"),
            project_id="project-1",
            request_context=self.context,
            core_ports=self.ports,
        )
        with (
            patch("backend.application.services.integrations.SkillMeatClient.list_context_modules", AsyncMock(return_value=[])),
            patch(
                "backend.application.services.integrations.SkillMeatClient.create_context_module",
                AsyncMock(return_value={"id": "cm_1", "name": "Workflow feature-a memory"}),
            ),
            patch(
                "backend.application.services.integrations.SkillMeatClient.add_context_module_memory",
                AsyncMock(return_value={"id": "mem_1", "url": "http://skillmeat.local/memories/mem_1"}),
            ),
        ):
            published = await integrations_router.publish_skillmeat_memory_draft(
                int(generated_row["id"]),
                SessionMemoryDraftPublishRequest(actor="operator", notes="Approved for publish"),
                project_id="project-1",
                request_context=self.context,
                core_ports=self.ports,
            )

        self.assertEqual(generated.draftsCreated, 1)
        self.assertEqual(listed.total, 1)
        self.assertEqual(reviewed.status, "approved")
        self.assertEqual(published.status, "published")
        self.assertEqual(published.publishedModuleId, "cm_1")
        self.assertEqual(published.publishedMemoryId, "mem_1")
