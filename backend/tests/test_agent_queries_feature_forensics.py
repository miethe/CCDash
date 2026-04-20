import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.feature_forensics import FeatureForensicsQueryService


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


class FeatureForensicsQueryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_forensics_returns_ok_payload(self) -> None:
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value={"id": "feature-1", "name": "Feature 1", "status": "in_progress", "updated_at": "2026-04-11T10:00:00+00:00"})
        )
        sessions_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={
                    "id": "session-1",
                    "status": "completed",
                    "started_at": "2026-04-11T09:00:00+00:00",
                    "ended_at": "2026-04-11T09:30:00+00:00",
                    "total_cost": 2.5,
                    "observed_tokens": 500,
                }
            )
        )
        documents_repo = types.SimpleNamespace(
            list_paginated=AsyncMock(return_value=[{"id": "doc-1", "title": "Plan", "file_path": "docs/plan.md", "updated_at": "2026-04-11T09:20:00+00:00"}])
        )
        tasks_repo = types.SimpleNamespace(
            list_by_feature=AsyncMock(return_value=[{"id": "task-1", "title": "Implement", "status": "in_progress", "updated_at": "2026-04-11T09:25:00+00:00"}])
        )
        links_repo = types.SimpleNamespace(
            get_links_for=AsyncMock(return_value=[{"source_type": "feature", "source_id": "feature-1", "target_type": "session", "target_id": "session-1"}])
        )
        ports = _ports(features=features_repo, sessions=sessions_repo, documents=documents_repo, tasks=tasks_repo, links=links_repo)

        with patch(
            "backend.application.services.agent_queries.feature_forensics.SessionTranscriptService.list_session_logs",
            new=AsyncMock(return_value=[{"content": "/dev:execute-phase docs/plan.md", "toolCall": {"name": "rg", "isError": False}}]),
        ):
            result = await FeatureForensicsQueryService().get_forensics(_context(), ports, "feature-1")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.feature_id, "feature-1")
        self.assertEqual(result.total_cost, 2.5)
        self.assertEqual(result.iteration_count, 1)
        self.assertIn("session-1", result.source_refs)
        self.assertTrue(result.summary_narrative.startswith("Feature"))

    async def test_get_forensics_returns_partial_when_supporting_source_fails(self) -> None:
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value={"id": "feature-1", "name": "Feature 1", "status": "in_progress"})
        )
        sessions_repo = types.SimpleNamespace(get_by_id=AsyncMock(return_value=None))
        documents_repo = types.SimpleNamespace(list_paginated=AsyncMock(side_effect=RuntimeError("boom")))
        tasks_repo = types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[]))
        links_repo = types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))
        ports = _ports(features=features_repo, sessions=sessions_repo, documents=documents_repo, tasks=tasks_repo, links=links_repo)

        with patch(
            "backend.application.services.agent_queries.feature_forensics.SessionIntelligenceReadService.list_sessions",
            new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
        ):
            result = await FeatureForensicsQueryService().get_forensics(_context(), ports, "feature-1")

        self.assertEqual(result.status, "partial")

    async def test_get_forensics_returns_error_when_feature_missing(self) -> None:
        result = await FeatureForensicsQueryService().get_forensics(_context(), _ports(), "missing-feature")
        self.assertEqual(result.status, "error")
        self.assertEqual(result.feature_id, "missing-feature")

    async def test_get_forensics_ok_result_carries_sessions_note(self) -> None:
        """TEST-002.5 criterion 2 — sessions_note must be present and reference eventual-consistency."""
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value={"id": "feature-1", "name": "Feature 1", "status": "in_progress", "updated_at": "2026-04-11T10:00:00+00:00"})
        )
        sessions_repo = types.SimpleNamespace(get_by_id=AsyncMock(return_value=None))
        documents_repo = types.SimpleNamespace(list_paginated=AsyncMock(return_value=[]))
        tasks_repo = types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[]))
        links_repo = types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))
        ports = _ports(features=features_repo, sessions=sessions_repo, documents=documents_repo, tasks=tasks_repo, links=links_repo)

        result = await FeatureForensicsQueryService().get_forensics(_context(), ports, "feature-1")

        # Accept ok or partial — both are non-error success states; partial can occur
        # when ancillary data (e.g. freshness markers) is unavailable in the test env.
        self.assertIn(result.status, {"ok", "partial"})
        self.assertTrue(
            hasattr(result, "sessions_note"),
            "FeatureForensicsDTO must expose a sessions_note field",
        )
        self.assertIn("eventually-consistent", result.sessions_note)
        self.assertIn("canonical", result.sessions_note.lower())

    async def test_get_forensics_sessions_note_present_in_mcp_envelope(self) -> None:
        """TEST-002.5 criterion 2 — sessions_note must appear in build_envelope(result).data."""
        from backend.mcp.tools import build_envelope

        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value={"id": "feature-env-1", "name": "Env Feature", "status": "in_progress", "updated_at": "2026-04-11T10:00:00+00:00"})
        )
        sessions_repo = types.SimpleNamespace(get_by_id=AsyncMock(return_value=None))
        documents_repo = types.SimpleNamespace(list_paginated=AsyncMock(return_value=[]))
        tasks_repo = types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[]))
        links_repo = types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))
        ports = _ports(features=features_repo, sessions=sessions_repo, documents=documents_repo, tasks=tasks_repo, links=links_repo)

        result = await FeatureForensicsQueryService().get_forensics(_context(), ports, "feature-env-1")
        envelope = build_envelope(result)

        self.assertIn("sessions_note", envelope["data"])
        self.assertIn("eventually-consistent", envelope["data"]["sessions_note"])

    async def test_get_forensics_exposes_token_usage_by_model_rollup(self) -> None:
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={
                    "id": "feature-rollup",
                    "name": "Rollup Feature",
                    "status": "in_progress",
                    "updated_at": "2026-04-11T10:00:00+00:00",
                }
            )
        )
        session_rows = {
            "session-opus": {
                "id": "session-opus",
                "status": "completed",
                "model": "claude-opus-4-1-20260101",
                "observed_tokens": 120,
                "started_at": "2026-04-11T09:00:00+00:00",
                "ended_at": "2026-04-11T09:10:00+00:00",
            },
            "session-sonnet": {
                "id": "session-sonnet",
                "status": "completed",
                "model": "claude-sonnet-4-5-20260101",
                "observed_tokens": 80,
                "started_at": "2026-04-11T09:10:00+00:00",
                "ended_at": "2026-04-11T09:20:00+00:00",
            },
            "session-haiku": {
                "id": "session-haiku",
                "status": "completed",
                "model": "claude-haiku-3-5-20260101",
                "observed_tokens": 40,
                "started_at": "2026-04-11T09:20:00+00:00",
                "ended_at": "2026-04-11T09:30:00+00:00",
            },
            "session-other": {
                "id": "session-other",
                "status": "completed",
                "model": "gpt-5",
                "observed_tokens": 25,
                "started_at": "2026-04-11T09:30:00+00:00",
                "ended_at": "2026-04-11T09:40:00+00:00",
            },
        }
        sessions_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(side_effect=lambda session_id: session_rows.get(session_id))
        )
        documents_repo = types.SimpleNamespace(list_paginated=AsyncMock(return_value=[]))
        tasks_repo = types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[]))
        links_repo = types.SimpleNamespace(
            get_links_for=AsyncMock(
                return_value=[
                    {"source_type": "feature", "source_id": "feature-rollup", "target_type": "session", "target_id": "session-opus"},
                    {"source_type": "feature", "source_id": "feature-rollup", "target_type": "session", "target_id": "session-sonnet"},
                    {"source_type": "feature", "source_id": "feature-rollup", "target_type": "session", "target_id": "session-haiku"},
                    {"source_type": "feature", "source_id": "feature-rollup", "target_type": "session", "target_id": "session-other"},
                ]
            )
        )
        ports = _ports(
            features=features_repo,
            sessions=sessions_repo,
            documents=documents_repo,
            tasks=tasks_repo,
            links=links_repo,
        )

        with patch(
            "backend.application.services.agent_queries.feature_forensics.SessionTranscriptService.list_session_logs",
            new=AsyncMock(return_value=[]),
        ):
            result = await FeatureForensicsQueryService().get_forensics(
                _context(),
                ports,
                "feature-rollup",
            )

        self.assertEqual(result.total_tokens, 265)
        self.assertEqual(result.token_usage_by_model.opus, 120)
        self.assertEqual(result.token_usage_by_model.sonnet, 80)
        self.assertEqual(result.token_usage_by_model.haiku, 40)
        self.assertEqual(result.token_usage_by_model.other, 25)
        self.assertEqual(result.token_usage_by_model.total, result.total_tokens)

    async def test_get_forensics_zero_session_rollup_defaults_to_zeroes(self) -> None:
        features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(
                return_value={
                    "id": "feature-empty-rollup",
                    "name": "Empty Rollup",
                    "status": "in_progress",
                    "updated_at": "2026-04-11T10:00:00+00:00",
                }
            )
        )
        sessions_repo = types.SimpleNamespace(get_by_id=AsyncMock(return_value=None))
        documents_repo = types.SimpleNamespace(list_paginated=AsyncMock(return_value=[]))
        tasks_repo = types.SimpleNamespace(list_by_feature=AsyncMock(return_value=[]))
        links_repo = types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))
        ports = _ports(
            features=features_repo,
            sessions=sessions_repo,
            documents=documents_repo,
            tasks=tasks_repo,
            links=links_repo,
        )

        with patch(
            "backend.application.services.agent_queries.feature_forensics.SessionIntelligenceReadService.list_sessions",
            new=AsyncMock(return_value=types.SimpleNamespace(items=[])),
        ):
            result = await FeatureForensicsQueryService().get_forensics(
                _context(),
                ports,
                "feature-empty-rollup",
            )

        self.assertEqual(result.total_tokens, 0)
        self.assertEqual(result.token_usage_by_model.opus, 0)
        self.assertEqual(result.token_usage_by_model.sonnet, 0)
        self.assertEqual(result.token_usage_by_model.haiku, 0)
        self.assertEqual(result.token_usage_by_model.other, 0)
        self.assertEqual(result.token_usage_by_model.total, 0)
