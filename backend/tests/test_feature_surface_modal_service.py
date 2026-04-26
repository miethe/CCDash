from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.feature_surface.modal_service import FeatureModalDetailService
from backend.db.repositories.feature_queries import ThreadExpansionMode


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
    def __init__(
        self,
        *,
        feature_row: dict[str, object],
        phase_rows: list[object] | None = None,
        task_rows: list[dict[str, object]] | None = None,
        doc_rows: list[dict[str, object]] | None = None,
        session_repo: object | None = None,
    ) -> None:
        self.db = object()
        self._features_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value=feature_row),
            list_phase_summaries_for_features=AsyncMock(return_value={feature_row["id"]: phase_rows or []}),
        )
        self._tasks_repo = types.SimpleNamespace(list_by_feature=AsyncMock(return_value=task_rows or []))
        self._docs_repo = types.SimpleNamespace(list_paginated=AsyncMock(return_value=doc_rows or []))
        self._session_repo = session_repo

    def features(self):
        return self._features_repo

    def tasks(self):
        return self._tasks_repo

    def documents(self):
        return self._docs_repo

    def feature_sessions(self):
        return self._session_repo


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


def _ports(storage: _Storage) -> CorePorts:
    project = types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=storage,
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


def _feature_row() -> dict[str, object]:
    return {
        "id": "feature-1",
        "project_id": "project-1",
        "name": "Feature One",
        "status": "in_progress",
        "category": "delivery",
        "total_tasks": 5,
        "completed_tasks": 2,
        "updated_at": "2026-04-23T12:00:00+00:00",
        "data_json": {
            "summary": "Concise summary",
            "priority": "high",
            "riskLevel": "medium",
            "complexity": "moderate",
            "executionReadiness": "ready",
            "tags": ["modal", "phase-2"],
            "deferredTasks": 1,
            "phaseCount": 2,
            "plannedAt": "2026-04-20",
            "startedAt": "2026-04-21",
            "documentCoverage": {"coverageScore": 0.75},
            "qualitySignals": {"blockerCount": 1},
            "planningStatus": {"effectiveStatus": "active"},
            "linkedFeatures": [{"feature": "dep-1", "type": "blocked_by"}],
            "relatedFeatures": ["dep-1", "dep-2"],
            "dependencyState": {"state": "blocked"},
            "blockingFeatures": [{"feature": "dep-1"}],
            "familySummary": {"featureFamily": "alpha"},
            "familyPosition": {"index": 1},
            "executionGate": {"state": "ready_after_dependencies"},
        },
    }


class FeatureModalDetailServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_overview_uses_feature_row_only(self) -> None:
        storage = _Storage(feature_row=_feature_row(), session_repo=AsyncMock())
        service = FeatureModalDetailService()

        result = await service.get_overview(_context(), _ports(storage), "feature-1")

        self.assertEqual(result.section, "overview")
        self.assertEqual(result.cost_profile, "feature_lookup")
        self.assertEqual(result.data["feature_id"], "feature-1")
        self.assertEqual(result.data["related_feature_count"], 2)
        storage._tasks_repo.list_by_feature.assert_not_called()
        storage._docs_repo.list_paginated.assert_not_called()

    async def test_phases_tasks_uses_phase_summary_bulk_and_task_list(self) -> None:
        phase_rows = [
            types.SimpleNamespace(
                phase_id="phase-1",
                name="Phase 1",
                status="in_progress",
                order_index=1,
                progress=0.5,
                total_tasks=2,
                completed_tasks=1,
            )
        ]
        task_rows = [
            {"id": "task-1", "title": "Implement", "status": "done", "phase_id": "phase-1"},
            {"id": "task-2", "title": "Verify", "status": "todo", "phase_id": "phase-1"},
        ]
        storage = _Storage(feature_row=_feature_row(), phase_rows=phase_rows, task_rows=task_rows, session_repo=AsyncMock())
        service = FeatureModalDetailService()

        result = await service.get_phases_tasks(_context(), _ports(storage), "feature-1")

        self.assertEqual(result.section, "phases")
        self.assertEqual(result.data["task_count"], 2)
        self.assertEqual(len(result.data["phases"]), 1)
        self.assertEqual(len(result.data["phases"][0]["tasks"]), 2)
        storage._features_repo.list_phase_summaries_for_features.assert_awaited_once()
        storage._tasks_repo.list_by_feature.assert_awaited_once_with("feature-1")

    async def test_sessions_use_source_paged_repository(self) -> None:
        session_repo = types.SimpleNamespace(
            list_feature_session_refs=AsyncMock(
                return_value=types.SimpleNamespace(
                    rows=[{"session_id": "session-1"}],
                    total=3,
                    offset=10,
                    limit=5,
                    has_more=False,
                )
            )
        )
        storage = _Storage(feature_row=_feature_row(), session_repo=session_repo)
        service = FeatureModalDetailService()

        result = await service.get_sessions(
            _context(),
            _ports(storage),
            "feature-1",
            limit=5,
            offset=10,
        )

        self.assertEqual(result.section, "sessions")
        self.assertEqual(result.data["rows"], [{"session_id": "session-1"}])
        self.assertEqual(result.data["total"], 3)
        storage._features_repo.get_by_id.assert_awaited_once_with("feature-1")
        call = session_repo.list_feature_session_refs.await_args
        self.assertEqual(call.args[0], "project-1")
        self.assertEqual(call.args[1].feature_id, "feature-1")
        self.assertEqual(call.args[1].limit, 5)
        self.assertEqual(call.args[1].offset, 10)
        self.assertEqual(call.args[1].thread_expansion, ThreadExpansionMode.INHERITED_THREADS)

    async def test_get_sections_only_loads_requested_sections_and_uses_fallback_loaders(self) -> None:
        storage = _Storage(feature_row=_feature_row(), session_repo=AsyncMock())
        test_status_loader = AsyncMock(return_value={"feature_id": "feature-1", "total_tests": 4})
        activity_loader = AsyncMock(return_value={"feature_id": "feature-1", "items": [{"kind": "commit"}]})
        service = FeatureModalDetailService(
            test_status_loader=test_status_loader,
            activity_loader=activity_loader,
        )

        result = await service.get_sections(
            _context(),
            _ports(storage),
            "feature-1",
            sections=["overview", "relations", "test_status", "activity"],
        )

        self.assertEqual(set(result.keys()), {"overview", "relations", "test_status", "activity"})
        self.assertEqual(result["relations"].data["dependency_state"]["state"], "blocked")
        self.assertEqual(result["test_status"].data["total_tests"], 4)
        self.assertEqual(result["activity"].data["items"][0]["kind"], "commit")
        storage._tasks_repo.list_by_feature.assert_not_called()
        storage._docs_repo.list_paginated.assert_not_called()
        test_status_loader.assert_awaited_once()
        activity_loader.assert_awaited_once()
