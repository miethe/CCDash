"""Regression tests for FeatureForensicsDTO alias fields and telemetry_available indicator."""
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.feature_forensics import FeatureForensicsQueryService


# ---------------------------------------------------------------------------
# Shared test infrastructure (mirrors test_agent_queries_feature_forensics.py)
# ---------------------------------------------------------------------------


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
        self._session_messages_repo = types.SimpleNamespace(list_by_session=AsyncMock(return_value=[]))

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

    def session_messages(self):
        return self._session_messages_repo


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class FeatureForensicsAliasTests(unittest.IsolatedAsyncioTestCase):
    async def test_name_populated(self) -> None:
        """dto.name resolves to the canonical feature name from the row."""
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={
                    "id": "feature-1",
                    "name": "My Feature",
                    "status": "in_progress",
                    "updated_at": "2026-04-14T10:00:00+00:00",
                }
            )
        )
        ports = _ports(features=features_repo)

        with patch(
            "backend.application.services.agent_queries.feature_forensics.SessionIntelligenceReadService.list_sessions",
            new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
        ):
            result = await FeatureForensicsQueryService().get_forensics(_context(), ports, "feature-1")

        self.assertTrue(result.name, "name must be non-empty")
        self.assertEqual(result.name, "My Feature")

    async def test_name_falls_back_to_feature_slug(self) -> None:
        """dto.name falls back to feature_slug when name/title are absent."""
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={
                    "id": "feature-2",
                    "feature_slug": "my-feature-slug",
                    "status": "active",
                    "updated_at": "2026-04-14T10:00:00+00:00",
                }
            )
        )
        ports = _ports(features=features_repo)

        with patch(
            "backend.application.services.agent_queries.feature_forensics.SessionIntelligenceReadService.list_sessions",
            new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
        ):
            result = await FeatureForensicsQueryService().get_forensics(_context(), ports, "feature-2")

        self.assertEqual(result.name, "my-feature-slug")

    async def test_telemetry_available_reflects_arrays(self) -> None:
        """telemetry_available mirrors presence of sessions/tasks; absent documents → False."""
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={"id": "feature-1", "name": "Feature 1", "status": "active", "updated_at": "2026-04-14T10:00:00+00:00"}
            )
        )
        sessions_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={
                    "id": "session-1",
                    "status": "completed",
                    "started_at": "2026-04-14T09:00:00+00:00",
                    "ended_at": "2026-04-14T09:30:00+00:00",
                    "total_cost": 1.0,
                    "observed_tokens": 100,
                }
            )
        )
        documents_repo = types.SimpleNamespace(list_paginated=AsyncMock(return_value=[]))
        tasks_repo = types.SimpleNamespace(
            list_by_feature=AsyncMock(
                return_value=[{"id": "task-1", "title": "Task", "status": "pending", "updated_at": "2026-04-14T09:00:00+00:00"}]
            )
        )
        links_repo = types.SimpleNamespace(
            get_links_for=AsyncMock(
                return_value=[{"source_type": "feature", "source_id": "feature-1", "target_type": "session", "target_id": "session-1"}]
            )
        )
        ports = _ports(features=features_repo, sessions=sessions_repo, documents=documents_repo, tasks=tasks_repo, links=links_repo)

        with patch(
            "backend.application.services.agent_queries.feature_forensics.SessionTranscriptService.list_session_logs",
            new=AsyncMock(return_value=[]),
        ):
            result = await FeatureForensicsQueryService().get_forensics(_context(), ports, "feature-1")

        self.assertTrue(result.telemetry_available.sessions)
        self.assertFalse(result.telemetry_available.documents)
        self.assertTrue(result.telemetry_available.tasks)

    async def test_empty_feature_yields_all_false(self) -> None:
        """A feature with no sessions, docs, or tasks has all telemetry_available flags False."""
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={"id": "feature-empty", "name": "Empty Feature", "status": "planned", "updated_at": "2026-04-14T10:00:00+00:00"}
            )
        )
        ports = _ports(features=features_repo)

        with patch(
            "backend.application.services.agent_queries.feature_forensics.SessionIntelligenceReadService.list_sessions",
            new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
        ):
            result = await FeatureForensicsQueryService().get_forensics(_context(), ports, "feature-empty")

        self.assertFalse(result.telemetry_available.sessions)
        self.assertFalse(result.telemetry_available.documents)
        self.assertFalse(result.telemetry_available.tasks)

    async def test_error_dto_has_safe_defaults(self) -> None:
        """Feature-not-found early return yields name==feature_id and all telemetry flags False."""
        result = await FeatureForensicsQueryService().get_forensics(_context(), _ports(), "missing-feature")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.name, "missing-feature")
        self.assertFalse(result.telemetry_available.sessions)
        self.assertFalse(result.telemetry_available.documents)
        self.assertFalse(result.telemetry_available.tasks)
