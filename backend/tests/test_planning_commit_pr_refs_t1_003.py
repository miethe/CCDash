"""Unit tests for T1-003: commit_refs / pr_refs on FeatureSummaryItem.

Verifies:
1. ``commit_refs`` and ``pr_refs`` are populated from ``feature.commitRefs`` /
   ``feature.prRefs`` (sourced from ``data_json``) without introducing new DB
   queries.
2. Both fields default to an empty list when the feature carries no refs.
3. The fields survive the full ``_build_summary_from_data`` path (the same path
   exercised by ``get_project_planning_summary``).
"""
from __future__ import annotations

import json
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from backend.application.context import (
    Principal,
    ProjectScope,
    RequestContext,
    TraceContext,
)
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.cache import clear_cache
from backend.application.services.agent_queries.models import FeatureSummaryItem
from backend.application.services.agent_queries.planning import PlanningQueryService
from backend.models import Feature, FeaturePhase


_PROJECT_ID = "project-t1-003"


# ── Minimal fixture helpers ───────────────────────────────────────────────────


def _feature(
    *,
    fid: str,
    name: str = "Feature",
    status: str = "in-progress",
    commit_refs: list[str] | None = None,
    pr_refs: list[str] | None = None,
) -> Feature:
    return Feature(
        id=fid,
        name=name,
        status=status,
        totalTasks=0,
        completedTasks=0,
        category="enhancement",
        tags=[],
        updatedAt="2026-06-04T10:00:00+00:00",
        linkedDocs=[],
        phases=[],
        relatedFeatures=[],
        commitRefs=commit_refs or [],
        prRefs=pr_refs or [],
    )


def _feature_row(feature: Feature) -> dict:
    """Build a raw DB-style dict that ``feature_from_row`` would produce."""
    return {
        "id": feature.id,
        "name": feature.name,
        "status": feature.status,
        "total_tasks": feature.totalTasks,
        "completed_tasks": feature.completedTasks,
        "deferred_tasks": feature.deferredTasks,
        "category": feature.category,
        "updated_at": feature.updatedAt,
        "data_json": json.dumps(
            {
                "id": feature.id,
                "name": feature.name,
                "status": feature.status,
                "phases": [],
                "linkedDocs": [],
                "linkedFeatures": [],
                "commitRefs": feature.commitRefs,
                "prRefs": feature.prRefs,
            }
        ),
    }


# ── Minimal auth / workspace / storage stubs ─────────────────────────────────


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def __init__(self, project):
        self._project = project

    def get_project(self, project_id):
        if self._project and getattr(self._project, "id", "") == project_id:
            return self._project
        return None

    def get_active_project(self):
        return self._project

    def resolve_scope(self, project_id=None):
        if self._project is None:
            return None, None
        resolved_id = project_id or self._project.id
        return None, ProjectScope(
            project_id=resolved_id,
            project_name=self._project.name,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


class _Storage:
    def __init__(self, *, features_repo, docs_repo, db=None):
        self.db = db or object()
        self._features_repo = features_repo
        self._docs_repo = docs_repo

    def features(self):
        return self._features_repo

    def documents(self):
        return self._docs_repo

    def sessions(self):
        return types.SimpleNamespace(list_paginated=AsyncMock(return_value=[]))

    def sync_state(self):
        return types.SimpleNamespace(list_all=AsyncMock(return_value=[]))

    def entity_links(self):
        return types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))


def _context(project_id: str = _PROJECT_ID) -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Project T1-003",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-t1-003"),
    )


def _ports(*, features_repo, docs_repo, db=None) -> CorePorts:
    project = types.SimpleNamespace(id=_PROJECT_ID, name="Project T1-003")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_Storage(features_repo=features_repo, docs_repo=docs_repo, db=db),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class FeatureSummaryItemDefaultsTests(unittest.TestCase):
    """T1-003 — both fields default to empty list when absent."""

    def test_commit_refs_defaults_to_empty_list(self) -> None:
        item = FeatureSummaryItem(feature_id="f1")
        self.assertEqual(item.commit_refs, [])

    def test_pr_refs_defaults_to_empty_list(self) -> None:
        item = FeatureSummaryItem(feature_id="f1")
        self.assertEqual(item.pr_refs, [])

    def test_both_fields_accept_string_lists(self) -> None:
        item = FeatureSummaryItem(
            feature_id="f1",
            commit_refs=["abc123", "def456"],
            pr_refs=["#42"],
        )
        self.assertEqual(item.commit_refs, ["abc123", "def456"])
        self.assertEqual(item.pr_refs, ["#42"])


class CommitPrRefsPopulatedFromFeatureDataTests(unittest.IsolatedAsyncioTestCase):
    """T1-003 — refs from data_json surfaced on FeatureSummaryItem in summary DTO.

    Uses a seeded document_refs-style fixture: feature rows carry ``commitRefs``
    and ``prRefs`` inside ``data_json`` (exactly as the parser / feature_from_row
    would produce from document_refs with ref_kind='commit' / ref_kind='pr').
    No new DB queries are introduced — the test verifies only already-fetched
    feature data is consumed.
    """

    def setUp(self) -> None:
        clear_cache()

    async def test_commit_refs_populated_from_feature_data_json(self) -> None:
        feat = _feature(
            fid="feat-refs",
            name="Refs Feature",
            status="in-progress",
            commit_refs=["abc123", "def456"],
            pr_refs=["#7"],
        )
        rows = [_feature_row(feat)]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=rows[0]),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports, include_terminal=True, limit=100
        )

        self.assertEqual(len(result.feature_summaries), 1)
        item = result.feature_summaries[0]
        self.assertEqual(item.feature_id, "feat-refs")
        self.assertEqual(item.commit_refs, ["abc123", "def456"])
        self.assertEqual(item.pr_refs, ["#7"])

    async def test_pr_refs_populated_from_feature_data_json(self) -> None:
        feat = _feature(
            fid="feat-prs",
            name="PR Feature",
            status="planned",
            commit_refs=[],
            pr_refs=["#100", "#101"],
        )
        rows = [_feature_row(feat)]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=rows[0]),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports, include_terminal=True, limit=100
        )

        self.assertEqual(len(result.feature_summaries), 1)
        item = result.feature_summaries[0]
        self.assertEqual(item.commit_refs, [])
        self.assertEqual(item.pr_refs, ["#100", "#101"])

    async def test_empty_refs_when_feature_carries_none(self) -> None:
        feat = _feature(
            fid="feat-norefs",
            name="No Refs",
            status="backlog",
            commit_refs=[],
            pr_refs=[],
        )
        rows = [_feature_row(feat)]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=rows[0]),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        self.assertEqual(len(result.feature_summaries), 1)
        item = result.feature_summaries[0]
        self.assertEqual(item.commit_refs, [])
        self.assertEqual(item.pr_refs, [])

    async def test_multiple_features_refs_kept_separate(self) -> None:
        feat_a = _feature(
            fid="feat-a",
            name="Feature A",
            status="in-progress",
            commit_refs=["aaaa111"],
            pr_refs=["#1"],
        )
        feat_b = _feature(
            fid="feat-b",
            name="Feature B",
            status="in-progress",
            commit_refs=["bbbb222"],
            pr_refs=["#2", "#3"],
        )
        rows = [_feature_row(feat_a), _feature_row(feat_b)]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports, include_terminal=True, limit=100
        )

        by_id = {item.feature_id: item for item in result.feature_summaries}
        self.assertIn("feat-a", by_id)
        self.assertIn("feat-b", by_id)
        self.assertEqual(by_id["feat-a"].commit_refs, ["aaaa111"])
        self.assertEqual(by_id["feat-a"].pr_refs, ["#1"])
        self.assertEqual(by_id["feat-b"].commit_refs, ["bbbb222"])
        self.assertEqual(by_id["feat-b"].pr_refs, ["#2", "#3"])

    async def test_no_extra_db_queries_introduced(self) -> None:
        """Refs come from already-fetched feature data — features_repo.list_all
        must be called exactly once regardless of ref counts."""
        feat = _feature(
            fid="feat-noextra",
            name="No Extra Queries",
            status="in-progress",
            commit_refs=["sha1", "sha2", "sha3"],
            pr_refs=["#10", "#11"],
        )
        rows = [_feature_row(feat)]
        list_all_mock = AsyncMock(return_value=rows)
        features_repo = types.SimpleNamespace(
            list_all=list_all_mock,
            get_by_id=AsyncMock(return_value=rows[0]),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        await PlanningQueryService().get_project_planning_summary(
            _context(), ports, include_terminal=True, limit=100
        )

        # Only one call to the feature repo — no N+1 per ref.
        self.assertEqual(list_all_mock.await_count, 1)


if __name__ == "__main__":
    unittest.main()
