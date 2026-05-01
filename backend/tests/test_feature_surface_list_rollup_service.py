from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.feature_surface import FeatureSurfaceListRollupService
from backend.db.repositories.feature_queries import (
    FeatureListPage,
    FeatureListQuery,
    FeatureRollupBatch,
    FeatureRollupEntry,
    FeatureRollupQuery,
    FeatureSortKey,
    PhaseSummary,
)


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
    def __init__(self, *, features_repo, db=None):
        self.db = db if db is not None else object()
        self._features_repo = features_repo
        self.sessions = AsyncMock(side_effect=AssertionError("service must not load sessions repo"))
        self.session_messages = AsyncMock(
            side_effect=AssertionError("service must not load session messages")
        )

    def features(self):
        return self._features_repo


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


def _ports(*, features_repo, db=None) -> CorePorts:
    project = types.SimpleNamespace(id="project-1", name="Project 1")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_Storage(features_repo=features_repo, db=db),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


class _FakeRollupDb:
    def __init__(self, batch: FeatureRollupBatch):
        self.batch = batch
        self.fetch_calls: list[tuple[str, list[str]]] = []

    async def fetch(self, sql: str, *args):
        if "SELECT id FROM features" in sql:
            feature_ids = list(args[1])
            self.fetch_calls.append(("existing", feature_ids))
            return [{"id": fid} for fid in feature_ids if fid != "missing-feature"]

        if "GROUP BY el.source_id, s.model" in sql:
            feature_ids = list(args[1])
            self.fetch_calls.append(("model", feature_ids))
            return []

        if "workflow_type" in sql and "GROUP BY el.source_id" in sql:
            feature_ids = list(args[1])
            self.fetch_calls.append(("workflow", feature_ids))
            return []

        if "FROM entity_links el" in sql and "JOIN sessions s" in sql:
            feature_ids = list(args[1])
            self.fetch_calls.append(("session", feature_ids))
            rows = []
            for fid in feature_ids:
                rollup = self.batch.rollups.get(fid)
                if rollup is None:
                    continue
                rows.append(
                    {
                        "feature_id": fid,
                        "session_count": rollup.session_count or 0,
                        "primary_session_count": rollup.primary_session_count or 0,
                        "subthread_count": rollup.subthread_count or 0,
                        "total_cost": rollup.total_cost or 0.0,
                        "display_cost": rollup.display_cost or 0.0,
                        "observed_tokens": rollup.observed_tokens or 0,
                        "model_io_tokens": rollup.model_io_tokens or 0,
                        "cache_input_tokens": rollup.cache_input_tokens or 0,
                        "latest_session_at": rollup.latest_session_at,
                        "latest_activity_at": rollup.latest_activity_at,
                    }
                )
            return rows

        return []


class FeatureSurfaceListRollupServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_feature_cards_stitches_phase_summaries_in_bulk(self) -> None:
        features_repo = types.SimpleNamespace(
            list_feature_cards=AsyncMock(
                return_value=FeatureListPage(
                    rows=[
                        {
                            "id": "FEAT-1",
                            "name": "Feature 1",
                            "status": "active",
                            "category": "cat-a",
                            "total_tasks": 8,
                            "completed_tasks": 3,
                            "updated_at": "2026-04-23T10:00:00Z",
                        },
                        {
                            "id": "FEAT-2",
                            "name": "Feature 2",
                            "status": "backlog",
                            "category": "cat-b",
                            "total_tasks": 5,
                            "completed_tasks": 0,
                            "updated_at": "2026-04-22T10:00:00Z",
                        },
                    ],
                    total=2,
                    offset=0,
                    limit=50,
                )
            ),
            list_phase_summaries_for_features=AsyncMock(
                return_value={
                    "FEAT-1": [
                        PhaseSummary(
                            feature_id="FEAT-1",
                            phase_id="FEAT-1:p1",
                            name="Phase 1",
                            status="done",
                            order_index=1,
                            total_tasks=4,
                            completed_tasks=4,
                            progress=1.0,
                        )
                    ],
                    "FEAT-2": [],
                }
            ),
        )
        service = FeatureSurfaceListRollupService()

        page = await service.list_feature_cards(
            _context(),
            _ports(features_repo=features_repo),
            FeatureListQuery(sort_by=FeatureSortKey.LATEST_ACTIVITY),
        )

        self.assertEqual([row.id for row in page.rows], ["FEAT-1", "FEAT-2"])
        self.assertEqual(page.rows[0].phase_summary[0].phase_id, "FEAT-1:p1")
        self.assertEqual(page.rows[0].phase_summary[0].name, "Phase 1")
        self.assertEqual(page.rows[1].phase_summary, [])
        self.assertEqual(page.sort.requested_sort_by, "latest_activity")
        self.assertEqual(page.sort.applied_sort_by, "latest_activity")
        self.assertEqual(page.sort.precision, "exact")
        features_repo.list_phase_summaries_for_features.assert_awaited_once()
        phase_query = features_repo.list_phase_summaries_for_features.await_args.args[1]
        self.assertEqual(phase_query.feature_ids, ["FEAT-1", "FEAT-2"])

    async def test_list_feature_cards_reports_session_count_sort_as_exact(self) -> None:
        features_repo = types.SimpleNamespace(
            list_feature_cards=AsyncMock(
                return_value=FeatureListPage(
                    rows=[],
                    total=0,
                    offset=0,
                    limit=50,
                )
            ),
            list_phase_summaries_for_features=AsyncMock(return_value={}),
        )
        service = FeatureSurfaceListRollupService()

        page = await service.list_feature_cards(
            _context(),
            _ports(features_repo=features_repo),
            FeatureListQuery(sort_by=FeatureSortKey.SESSION_COUNT),
        )

        self.assertEqual(page.sort.requested_sort_by, "session_count")
        self.assertEqual(page.sort.applied_sort_by, "session_count")
        self.assertEqual(page.sort.precision, "exact")

    async def test_list_feature_cards_rejects_unsupported_include(self) -> None:
        features_repo = types.SimpleNamespace(
            list_feature_cards=AsyncMock(),
            list_phase_summaries_for_features=AsyncMock(),
        )
        service = FeatureSurfaceListRollupService()

        with self.assertRaisesRegex(ValueError, "Unsupported feature list include field"):
            await service.list_feature_cards(
                _context(),
                _ports(features_repo=features_repo),
                FeatureListQuery(),
                include=["dependency_summary"],
            )

        features_repo.list_feature_cards.assert_not_called()

    async def test_build_rollup_query_rejects_unsupported_task_metrics(self) -> None:
        service = FeatureSurfaceListRollupService()

        with self.assertRaisesRegex(ValueError, "Unsupported rollup field group"):
            service.build_rollup_query(
                feature_ids=["FEAT-1"],
                fields=["task_metrics"],
            )

    async def test_build_rollup_query_rejects_empty_request_without_freshness(self) -> None:
        service = FeatureSurfaceListRollupService()

        with self.assertRaisesRegex(ValueError, "At least one rollup field"):
            service.build_rollup_query(
                feature_ids=["FEAT-1"],
                fields=[],
                include_freshness=False,
            )

    async def test_get_feature_rollups_uses_bounded_repo_batch(self) -> None:
        batch = FeatureRollupBatch(
            rollups={
                "FEAT-1": FeatureRollupEntry(
                    feature_id="FEAT-1",
                    session_count=3,
                    primary_session_count=2,
                    subthread_count=1,
                    total_cost=12.5,
                    display_cost=12.5,
                    observed_tokens=900,
                    model_io_tokens=700,
                    cache_input_tokens=200,
                    latest_activity_at="2026-04-23T12:00:00Z",
                )
            },
            missing=["missing-feature"],
            cache_version="test-cache",
        )
        features_repo = types.SimpleNamespace(
            list_feature_cards=AsyncMock(),
            list_phase_summaries_for_features=AsyncMock(),
        )
        fake_db = _FakeRollupDb(batch)
        service = FeatureSurfaceListRollupService()

        result = await service.get_feature_rollups(
            _context(),
            _ports(features_repo=features_repo, db=fake_db),
            FeatureRollupQuery(
                feature_ids=["FEAT-1", "missing-feature"],
                include_fields={"session_counts", "latest_activity"},
                include_freshness=False,
            ),
        )

        self.assertIn("FEAT-1", result.rollups)
        self.assertEqual(result.rollups["FEAT-1"].session_count, 3)
        self.assertEqual(result.missing, ["missing-feature"])

    async def test_get_feature_rollups_treats_freshness_field_as_flag(self) -> None:
        batch = FeatureRollupBatch(
            rollups={},
            cache_version="test-cache",
        )
        service = FeatureSurfaceListRollupService()
        query = service.build_rollup_query(
            feature_ids=["FEAT-1"],
            fields=["freshness", "session_counts"],
            include_freshness=False,
        )

        self.assertEqual(query.include_fields, {"session_counts"})
        self.assertTrue(query.include_freshness)
