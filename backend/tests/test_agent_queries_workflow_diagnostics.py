import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.workflow_intelligence import WorkflowDiagnosticsQueryService


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
    db = object()


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


def _ports(project=None) -> CorePorts:
    resolved_project = project if project is not None else types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(resolved_project),
        storage=_Storage(),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


class WorkflowDiagnosticsQueryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_diagnostics_returns_ok_payload(self) -> None:
        with patch(
            "backend.application.services.agent_queries.workflow_intelligence.list_workflow_registry",
            new=AsyncMock(
                return_value={
                    "items": [
                        {
                            "id": "registry-1",
                            "identity": {"displayLabel": "Phase Execution", "registryId": "wf-1"},
                            "sampleSize": 4,
                        }
                    ],
                    "generatedAt": "2026-04-11T10:00:00+00:00",
                }
            ),
        ), patch(
            "backend.application.services.agent_queries.workflow_intelligence.get_workflow_effectiveness",
            new=AsyncMock(
                return_value={
                    "items": [{"scopeType": "workflow", "scopeId": "wf-1", "scopeLabel": "Phase Execution", "sampleSize": 4, "successScore": 0.75, "efficiencyScore": 0.8}],
                    "generatedAt": "2026-04-11T10:01:00+00:00",
                }
            ),
        ), patch(
            "backend.application.services.agent_queries.workflow_intelligence.detect_failure_patterns",
            new=AsyncMock(return_value={"items": [{"scopeId": "wf-1", "title": "Retry Loop"}], "generatedAt": "2026-04-11T10:02:00+00:00"}),
        ), patch(
            "backend.application.services.agent_queries.workflow_intelligence.fetch_workflow_details",
            new=AsyncMock(return_value=[{"id": "registry-1", "representativeSessions": [{"sessionId": "session-1", "workflowRef": "wf-1"}]}]),
        ):
            result = await WorkflowDiagnosticsQueryService().get_diagnostics(_context(), _ports())

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.workflows[0].workflow_id, "wf-1")
        self.assertEqual(result.workflows[0].common_failures, ["Retry Loop"])
        self.assertEqual(result.workflows[0].representative_sessions[0].session_id, "session-1")

    async def test_get_diagnostics_returns_partial_when_failure_patterns_unavailable(self) -> None:
        with patch(
            "backend.application.services.agent_queries.workflow_intelligence.list_workflow_registry",
            new=AsyncMock(return_value={"items": [], "generatedAt": "2026-04-11T10:00:00+00:00"}),
        ), patch(
            "backend.application.services.agent_queries.workflow_intelligence.get_workflow_effectiveness",
            new=AsyncMock(return_value={"items": [], "generatedAt": "2026-04-11T10:01:00+00:00"}),
        ), patch(
            "backend.application.services.agent_queries.workflow_intelligence.detect_failure_patterns",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = await WorkflowDiagnosticsQueryService().get_diagnostics(_context(), _ports())

        self.assertEqual(result.status, "partial")

    async def test_get_diagnostics_returns_error_when_project_unresolved(self) -> None:
        result = await WorkflowDiagnosticsQueryService().get_diagnostics(_context("missing"), _ports(project=None))
        self.assertEqual(result.status, "error")
