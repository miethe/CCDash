import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.reporting import ReportingQueryService


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
    def __init__(self, *, features_repo, sessions_repo, documents_repo, tasks_repo, links_repo):
        self.db = object()
        self._features_repo = features_repo
        self._sessions_repo = sessions_repo
        self._documents_repo = documents_repo
        self._tasks_repo = tasks_repo
        self._links_repo = links_repo

    def features(self):
        return self._features_repo

    def sessions(self):
        return self._sessions_repo

    def documents(self):
        return self._documents_repo

    def tasks(self):
        return self._tasks_repo

    def entity_links(self):
        return self._links_repo


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


def _ports(*, features=None, sessions=None, documents=None, tasks=None, links=None) -> CorePorts:
    project = types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_Storage(
            features_repo=features or types.SimpleNamespace(get_by_id=AsyncMock(return_value=None)),
            sessions_repo=sessions or types.SimpleNamespace(get_by_id=AsyncMock(return_value=None)),
            documents_repo=documents or types.SimpleNamespace(list_paginated=AsyncMock(return_value=[])),
            tasks_repo=tasks or types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[])),
            links_repo=links or types.SimpleNamespace(get_links_for=AsyncMock(return_value=[])),
        ),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


class ReportingQueryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_aar_returns_ok_payload(self) -> None:
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value={"id": "feature-1", "name": "Feature 1", "updated_at": "2026-04-11T10:00:00+00:00"})
        )
        sessions_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={
                    "id": "session-1",
                    "status": "completed",
                    "started_at": "2026-04-11T09:00:00+00:00",
                    "ended_at": "2026-04-11T09:30:00+00:00",
                    "total_cost": 1.5,
                    "observed_tokens": 400,
                }
            )
        )
        documents_repo = types.SimpleNamespace(
            list_paginated=AsyncMock(return_value=[{"id": "doc-1", "title": "Plan", "file_path": "docs/plan.md", "updated_at": "2026-04-11T09:20:00+00:00"}])
        )
        tasks_repo = types.SimpleNamespace(
            list_by_feature=AsyncMock(return_value=[{"id": "task-1", "title": "Implement", "status": "done", "updated_at": "2026-04-11T09:25:00+00:00"}])
        )
        links_repo = types.SimpleNamespace(
            get_links_for=AsyncMock(return_value=[{"source_type": "feature", "source_id": "feature-1", "target_type": "session", "target_id": "session-1"}])
        )
        ports = _ports(features=features_repo, sessions=sessions_repo, documents=documents_repo, tasks=tasks_repo, links=links_repo)

        with patch(
            "backend.application.services.agent_queries.reporting.get_workflow_effectiveness",
            new=AsyncMock(return_value={"items": [{"scopeType": "workflow", "scopeId": "wf-1", "scopeLabel": "Phase Execution", "sampleSize": 1, "successScore": 0.9}], "generatedAt": "2026-04-11T10:01:00+00:00"}),
        ), patch(
            "backend.application.services.agent_queries.reporting.detect_failure_patterns",
            new=AsyncMock(return_value={"items": [{"title": "Retry Loop", "averageRiskScore": 0.7, "sessionIds": ["session-1"]}], "generatedAt": "2026-04-11T10:02:00+00:00"}),
        ):
            result = await ReportingQueryService().generate_aar(_context(), ports, "feature-1")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.key_metrics.total_cost, 1.5)
        self.assertEqual(result.timeline.started_at, "2026-04-11T09:00:00+00:00")
        self.assertTrue(result.turning_points)
        self.assertIn("session-1", result.evidence_links)

    async def test_generate_aar_returns_partial_when_supporting_source_fails(self) -> None:
        features_repo = types.SimpleNamespace(get_by_id=AsyncMock(return_value={"id": "feature-1", "name": "Feature 1"}))
        sessions_repo = types.SimpleNamespace(get_by_id=AsyncMock(return_value=None))
        documents_repo = types.SimpleNamespace(list_paginated=AsyncMock(side_effect=RuntimeError("boom")))
        tasks_repo = types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[]))
        links_repo = types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))
        ports = _ports(features=features_repo, sessions=sessions_repo, documents=documents_repo, tasks=tasks_repo, links=links_repo)

        with patch(
            "backend.application.services.agent_queries.reporting.get_workflow_effectiveness",
            new=AsyncMock(return_value={"items": [], "generatedAt": "2026-04-11T10:01:00+00:00"}),
        ), patch(
            "backend.application.services.agent_queries.reporting.detect_failure_patterns",
            new=AsyncMock(return_value={"items": [], "generatedAt": "2026-04-11T10:02:00+00:00"}),
        ), patch(
            "backend.application.services.agent_queries.feature_forensics.SessionIntelligenceReadService.list_sessions",
            new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
        ):
            result = await ReportingQueryService().generate_aar(_context(), ports, "feature-1")

        self.assertEqual(result.status, "partial")

    async def test_generate_aar_returns_error_when_feature_missing(self) -> None:
        result = await ReportingQueryService().generate_aar(_context(), _ports(), "missing-feature")
        self.assertEqual(result.status, "error")
