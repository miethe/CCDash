import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.project_status import ProjectStatusQueryService


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def __init__(self, project):
        self.project = project

    def get_project(self, project_id):
        if self.project and getattr(self.project, "id", "") == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project

    def resolve_scope(self, project_id=None):
        if self.project is None:
            return None, None
        resolved_id = project_id or self.project.id
        return None, ProjectScope(
            project_id=resolved_id,
            project_name=self.project.name,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


class _Storage:
    def __init__(self, *, features_repo, sessions_repo, sync_repo):
        self.db = object()
        self._features_repo = features_repo
        self._sessions_repo = sessions_repo
        self._sync_repo = sync_repo

    def features(self):
        return self._features_repo

    def sessions(self):
        return self._sessions_repo

    def sync_state(self):
        return self._sync_repo


def _context(project_id: str = "project-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Project 1",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


def _ports(*, project=None, features=None, sessions=None, sync=None) -> CorePorts:
    resolved_project = project if project is not None else types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(resolved_project),
        storage=_Storage(
            features_repo=features or types.SimpleNamespace(list_all=AsyncMock(return_value=[])),
            sessions_repo=sessions or types.SimpleNamespace(list_paginated=AsyncMock(return_value=[])),
            sync_repo=sync or types.SimpleNamespace(list_all=AsyncMock(return_value=[])),
        ),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


class _Rollup:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return dict(self._payload)


class ProjectStatusQueryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_status_returns_aggregated_ok_payload(self) -> None:
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(
                return_value=[
                    {"id": "feature-1", "status": "blocked", "updated_at": "2026-04-11T10:00:00+00:00"},
                    {"id": "feature-2", "status": "done", "updated_at": "2026-04-11T09:00:00+00:00"},
                ]
            )
        )
        sessions_repo = types.SimpleNamespace(
            list_paginated=AsyncMock(return_value=[]),
            get_project_stats=AsyncMock(return_value={"count": 2, "cost": 3.2, "tokens": 1200, "duration": 100.0}),
        )
        sync_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[{"last_synced": "2026-04-11T10:05:00+00:00"}])
        )
        ports = _ports(features=features_repo, sessions=sessions_repo, sync=sync_repo)
        response = types.SimpleNamespace(
            items=[_Rollup({"sessionId": "session-1", "startedAt": "2026-04-11T10:01:00+00:00", "status": "completed"})]
        )

        with patch(
            "backend.application.services.agent_queries.project_status.SessionIntelligenceReadService.list_sessions",
            new=AsyncMock(return_value=response),
        ), patch(
            "backend.application.services.agent_queries.project_status.AnalyticsOverviewService.get_overview",
            new=AsyncMock(return_value={"kpis": {"sessionCost": 3.2, "sessionTokens": 1200}, "generatedAt": "2026-04-11T10:04:00+00:00"}),
        ), patch(
            "backend.application.services.agent_queries.project_status.list_workflow_registry",
            new=AsyncMock(
                return_value={
                    "items": [
                        {
                            "id": "workflow:phase-execution",
                            "identity": {"displayLabel": "Phase Execution", "registryId": "workflow:phase-execution"},
                            "sampleSize": 4,
                            "effectiveness": {"successScore": 0.75},
                            "lastObservedAt": "2026-04-11T10:03:00+00:00",
                        }
                    ]
                }
            ),
        ):
            result = await ProjectStatusQueryService().get_status(_context(), ports)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.project_id, "project-1")
        self.assertEqual(result.feature_counts["blocked"], 1)
        self.assertEqual(result.blocked_features, ["feature-1"])
        self.assertEqual(result.recent_sessions[0].session_id, "session-1")
        self.assertEqual(result.top_workflows[0].workflow_name, "Phase Execution")
        self.assertIn("project-1", result.source_refs)

    async def test_get_status_returns_partial_when_supporting_source_fails(self) -> None:
        features_repo = types.SimpleNamespace(list_all=AsyncMock(return_value=[{"id": "feature-1", "status": "todo"}]))
        sessions_repo = types.SimpleNamespace(list_paginated=AsyncMock(side_effect=RuntimeError("boom")))
        sync_repo = types.SimpleNamespace(list_all=AsyncMock(return_value=[]))
        ports = _ports(features=features_repo, sessions=sessions_repo, sync=sync_repo)

        with patch(
            "backend.application.services.agent_queries.project_status.SessionIntelligenceReadService.list_sessions",
            new=AsyncMock(side_effect=RuntimeError("unavailable")),
        ), patch(
            "backend.application.services.agent_queries.project_status.AnalyticsOverviewService.get_overview",
            new=AsyncMock(return_value={"kpis": {}, "generatedAt": "2026-04-11T10:04:00+00:00"}),
        ), patch(
            "backend.application.services.agent_queries.project_status.list_workflow_registry",
            new=AsyncMock(side_effect=RuntimeError("registry down")),
        ):
            result = await ProjectStatusQueryService().get_status(_context(), ports)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.feature_counts["todo"], 1)

    async def test_get_status_returns_error_when_project_unresolved(self) -> None:
        ports = _ports(project=None)
        result = await ProjectStatusQueryService().get_status(_context("missing-project"), ports, "missing-project")
        self.assertEqual(result.status, "error")
        self.assertEqual(result.project_id, "missing-project")
