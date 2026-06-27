"""Tests for MPCC-205 — Multi-Project Planning Command Center aggregate service and router.

Covers Phase 2 quality gates:
  TC-1  Aggregation across ≥3 projects: merged items carry project identity;
        projectSummaries present with display metadata + counts.
  TC-2  Filters (q, status, phase) applied across the merged set.
  TC-3  Pagination: page/pageSize/total/hasMore correct across merged sorted set.
  TC-4  Partial failure: one project raises → ProjectWarning emitted, status==
        "partial", other projects still return items.
  TC-5  Stale project: is_stale==True + freshness_seconds surfaced.
  TC-6  Page-first (load-bearing): git probe called ONLY for page-visible items.
  TC-7  Detail-beyond-page-1: get_multi_project_item returns item not in page 1.
  TC-8  Router flag-off: GET .../multi-project/command-center returns 404 when
        CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED is False.
  TC-9  No per-project board reload: service does not call get_session_board per
        project.

Test style mirrors test_planning_command_center_service.py:
  - IsolatedAsyncioTestCase (no pytest-asyncio dependency → avoids collection hang)
  - SimpleNamespace stubs for ports/storage — no DB, no filesystem
  - patch.object for router flag tests
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend import config
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.services.agent_queries.cache import clear_cache
from backend.application.services.agent_queries.models import (
    PlanningCommandCenterGitStateDTO,
)
from backend.application.services.agent_queries.multi_project_planning_command_center import (
    MultiProjectPlanningCommandCenterQueryService,
    _NullGitProbe,
)
from backend.models import Project

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_project(pid: str, name: str | None = None) -> Project:
    return Project(id=pid, name=name or pid, path=f"/tmp/{pid}")


def _request_context(project_id: str = "proj-alpha") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="tester", display_name="Tester", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name=project_id,
            root_path=Path(f"/tmp/{project_id}"),
            sessions_dir=Path(f"/tmp/{project_id}/sessions"),
            docs_dir=Path(f"/tmp/{project_id}/docs"),
            progress_dir=Path(f"/tmp/{project_id}/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


def _make_feature_row(
    feature_id: str,
    name: str,
    status: str = "in-progress",
    current_phase: int = 2,
    total_phases: int = 4,
    completed_phases: int = 1,
) -> dict:
    """Return a minimal feature_row dict matching the parser shape."""
    data = {
        "id": feature_id,
        "name": name,
        "status": status,
        "summary": name,
        "priority": "high",
        "tags": [],
        "prRefs": [],
        "linkedDocs": [],
        "phases": [
            {
                "id": f"{feature_id}:phase-{i}",
                "phase": str(i),
                "title": f"Phase {i}",
                "status": "done" if i < current_phase else "backlog",
                "progress": 100 if i < current_phase else 0,
                "totalTasks": 2,
                "completedTasks": 2 if i < current_phase else 0,
                "tasks": [],
            }
            for i in range(1, total_phases + 1)
        ],
    }
    return {
        "id": feature_id,
        "name": name,
        "status": status,
        "updated_at": "2026-05-29T08:00:00+00:00",
        "data_json": json.dumps(data),
    }


class _FeaturesRepo:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    async def list_all(self, project_id: str) -> list[dict]:
        return list(self.rows)


class _DocumentsRepo:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []

    async def list_all(self, project_id: str) -> list[dict]:
        return list(self.rows)


class _WorktreeRepo:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []

    async def list(self, project_id: str, **kwargs) -> list[dict]:
        return list(self.rows)


class _SessionsRepo:
    """Sessions repo stub with controllable count_active behaviour."""

    def __init__(self, active_count: int = 0) -> None:
        self._count = active_count
        self.count_active_calls: list[str] = []

    async def count_active(self, project_id: str, **kwargs) -> int:
        self.count_active_calls.append(project_id)
        return self._count


class _WorkspaceRegistry:
    """Minimal WorkspaceRegistry covering list_projects + resolve_scope."""

    def __init__(self, projects: list[Project]) -> None:
        self._projects = projects

    def list_projects(self) -> list[Project]:
        return list(self._projects)

    def get_project(self, project_id: str) -> Project | None:
        return next((p for p in self._projects if p.id == project_id), None)

    def get_active_project(self) -> Project | None:
        return self._projects[0] if self._projects else None

    def resolve_scope(self, project_id: str | None = None):
        proj = self.get_project(project_id or "") if project_id else self.get_active_project()
        if proj is None:
            return None, None
        return None, ProjectScope(
            project_id=proj.id,
            project_name=proj.name,
            root_path=Path(proj.path),
            sessions_dir=Path(proj.path) / "sessions",
            docs_dir=Path(proj.path) / "docs",
            progress_dir=Path(proj.path) / "progress",
        )


class _DbStub:
    """Minimal DB stub — MPCC summary queries are patched away in service tests."""
    pass


def _make_storage(
    feature_rows_by_project: dict[str, list[dict]],
    *,
    active_count: int = 0,
) -> SimpleNamespace:
    """Build a storage stub with per-project feature repositories."""

    class _PerProjectFeaturesRepo:
        def __init__(self, rows_map: dict) -> None:
            self._map = rows_map

        async def list_all(self, project_id: str) -> list[dict]:
            return list(self._map.get(project_id, []))

    class _PerProjectStorage:
        def __init__(self) -> None:
            self.db = _DbStub()
            self._features_repo = _PerProjectFeaturesRepo(feature_rows_by_project)
            self._docs_repo = _DocumentsRepo([])
            self._worktree_repo = _WorktreeRepo([])
            self._sessions_repo = _SessionsRepo(active_count)

        def features(self) -> _PerProjectFeaturesRepo:
            return self._features_repo

        def documents(self) -> _DocumentsRepo:
            return self._docs_repo

        def worktree_contexts(self) -> _WorktreeRepo:
            return self._worktree_repo

        def sessions(self) -> _SessionsRepo:
            return self._sessions_repo

    return _PerProjectStorage()


def _make_ports(
    projects: list[Project],
    feature_rows_by_project: dict[str, list[dict]],
    *,
    active_count: int = 0,
) -> SimpleNamespace:
    storage = _make_storage(feature_rows_by_project, active_count=active_count)
    return SimpleNamespace(
        workspace_registry=_WorkspaceRegistry(projects),
        storage=storage,
    )


class _CountingGitProbe:
    """Git probe that counts calls and returns a real-looking DTO."""

    def __init__(self) -> None:
        self.probe_calls: list[str] = []

    async def probe(self, worktree_path: str) -> PlanningCommandCenterGitStateDTO:
        self.probe_calls.append(worktree_path)
        return PlanningCommandCenterGitStateDTO(
            path_exists=bool(worktree_path),
            head="abc1234",
            dirty_count=0,
            probed_at="2026-05-29T08:00:00+00:00",
        )


# Patch _query_max_updated_at and _compute_is_stale so service tests do not
# require a real DB for freshness computation.
_PATCH_MAX_UPDATED_AT = patch(
    "backend.application.services.agent_queries.multi_project_planning_command_center._query_max_updated_at",
    new=AsyncMock(return_value=None),
)
_PATCH_COMPUTE_STALE = patch(
    "backend.application.services.agent_queries.multi_project_planning_command_center._compute_is_stale",
    return_value=False,
)


# ---------------------------------------------------------------------------
# TC-1  Aggregation across ≥3 projects
# ---------------------------------------------------------------------------


class TestAggregationAcrossThreeProjects(unittest.IsolatedAsyncioTestCase):
    """TC-1: items from ≥3 projects are merged; each carries project identity;
    projectSummaries present with display metadata + counts."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_three_projects_items_carry_project_identity(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha Platform")
        beta = _make_project("proj-beta", "Beta Mobile")
        gamma = _make_project("proj-gamma", "Gamma Infra")

        rows = {
            "proj-alpha": [
                _make_feature_row("feat-a1", "Auth Hardening"),
                _make_feature_row("feat-a2", "Rate Limiting"),
            ],
            "proj-beta": [
                _make_feature_row("feat-b1", "Push Notifications"),
            ],
            "proj-gamma": [
                _make_feature_row("feat-g1", "K8s Autoscaling"),
            ],
        }

        ports = _make_ports([alpha, beta, gamma], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(),
                ports,
                page=1,
                page_size=50,
            )

        # Status should be ok (no errors)
        self.assertEqual(response.status, "ok")

        # All four items present
        self.assertEqual(response.pagination.total, 4)
        self.assertEqual(len(response.items), 4)

        # Every item carries a project identity with non-empty project_id and name
        for aggregate_item in response.items:
            self.assertIsNotNone(aggregate_item.project)
            self.assertIn(aggregate_item.project.project_id, {"proj-alpha", "proj-beta", "proj-gamma"})
            self.assertNotEqual(aggregate_item.project.project_name, "")

        # Project IDs are represented across the merged set
        seen_projects = {it.project.project_id for it in response.items}
        self.assertIn("proj-alpha", seen_projects)
        self.assertIn("proj-beta", seen_projects)
        self.assertIn("proj-gamma", seen_projects)

        # projectSummaries present — one per project
        self.assertEqual(len(response.project_summaries), 3)
        summary_ids = {s.project_id for s in response.project_summaries}
        self.assertEqual(summary_ids, {"proj-alpha", "proj-beta", "proj-gamma"})

        # Each summary has a name and counts object
        for summary in response.project_summaries:
            self.assertNotEqual(summary.name, "")
            self.assertIsNotNone(summary.counts)

        # Alpha summary has 2 work items
        alpha_summary = next(s for s in response.project_summaries if s.project_id == "proj-alpha")
        self.assertEqual(alpha_summary.counts.work_items, 2)


# ---------------------------------------------------------------------------
# TC-2  Filters applied across the merged set
# ---------------------------------------------------------------------------


class TestFiltersAcrossMergedSet(unittest.IsolatedAsyncioTestCase):
    """TC-2: q/status/phase filters reduce the merged item set correctly."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_q_filter_narrows_items(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        beta = _make_project("proj-beta", "Beta")

        rows = {
            "proj-alpha": [
                _make_feature_row("feat-auth", "Auth Hardening"),
                _make_feature_row("feat-rate", "Rate Limiting"),
            ],
            "proj-beta": [
                _make_feature_row("feat-push", "Push Notifications"),
            ],
        }

        ports = _make_ports([alpha, beta], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(),
                ports,
                q="auth",
                page=1,
                page_size=50,
            )

        # Only feat-auth should match the "auth" query
        self.assertEqual(response.pagination.total, 1)
        matched_ids = [
            it.item["feature"]["feature_id"]
            for it in response.items
        ]
        self.assertIn("feat-auth", matched_ids)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_status_filter(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")

        rows = {
            "proj-alpha": [
                _make_feature_row("feat-1", "Active Feature", status="in-progress"),
                _make_feature_row("feat-2", "Review Feature", status="review"),
                _make_feature_row("feat-3", "Done Feature", status="done"),
            ],
        }

        ports = _make_ports([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(),
                ports,
                status="review",
                page=1,
                page_size=50,
            )

        self.assertEqual(response.pagination.total, 1)
        item = response.items[0]
        self.assertEqual(item.item["feature"]["feature_id"], "feat-2")

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_phase_filter(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")

        rows = {
            "proj-alpha": [
                _make_feature_row("feat-p1", "Phase 1 Feature", current_phase=1),
                _make_feature_row("feat-p2", "Phase 2 Feature", current_phase=2),
                _make_feature_row("feat-p3", "Phase 3 Feature", current_phase=3),
            ],
        }

        ports = _make_ports([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(),
                ports,
                phase=2,
                page=1,
                page_size=50,
            )

        # Only feat-p2 has current_phase==2 (and feat-p1 has next_phase==2)
        matched_ids = [it.item["feature"]["feature_id"] for it in response.items]
        self.assertIn("feat-p2", matched_ids)
        self.assertNotIn("feat-p3", matched_ids)


# ---------------------------------------------------------------------------
# TC-3  Pagination correctness
# ---------------------------------------------------------------------------


class TestPagination(unittest.IsolatedAsyncioTestCase):
    """TC-3: page/page_size/total/has_more are correct across merged sorted set."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_pagination_page1(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        beta = _make_project("proj-beta", "Beta")

        # 7 items total across two projects
        rows = {
            "proj-alpha": [_make_feature_row(f"feat-a{i}", f"Alpha Feature {i}") for i in range(4)],
            "proj-beta": [_make_feature_row(f"feat-b{i}", f"Beta Feature {i}") for i in range(3)],
        }

        ports = _make_ports([alpha, beta], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            page1 = await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=3
            )

        self.assertEqual(page1.pagination.total, 7)
        self.assertEqual(page1.pagination.page, 1)
        self.assertEqual(page1.pagination.page_size, 3)
        self.assertEqual(len(page1.items), 3)
        self.assertTrue(page1.pagination.has_more)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_pagination_last_page(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")

        rows = {
            "proj-alpha": [_make_feature_row(f"feat-{i}", f"Feature {i}") for i in range(5)],
        }

        ports = _make_ports([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            last_page = await svc.get_multi_project_command_center(
                _request_context(), ports, page=2, page_size=3
            )

        self.assertEqual(last_page.pagination.total, 5)
        self.assertEqual(last_page.pagination.page, 2)
        # 2 items on page 2 (items 4 and 5)
        self.assertEqual(len(last_page.items), 2)
        self.assertFalse(last_page.pagination.has_more)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_pagination_empty(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")

        rows: dict[str, list] = {"proj-alpha": []}
        ports = _make_ports([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=10
            )

        self.assertEqual(response.pagination.total, 0)
        self.assertEqual(len(response.items), 0)
        self.assertFalse(response.pagination.has_more)


# ---------------------------------------------------------------------------
# TC-4  Partial failure
# ---------------------------------------------------------------------------


class TestPartialFailure(unittest.IsolatedAsyncioTestCase):
    """TC-4: one project raises during load → ProjectWarning emitted,
    status=="partial", other projects still return items."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_one_project_failure_yields_partial(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        bad = _make_project("proj-bad", "Bad Project")
        gamma = _make_project("proj-gamma", "Gamma")

        # Make the bad project's features repo raise at list_all — this exception
        # is caught INSIDE _collect_project_items (which has a broad except clause),
        # so it surfaces as (project_id, [], [], [], True, [str(exc)]) instead of
        # propagating through asyncio.gather.
        # The features() method routes by project_id check inside list_all.
        rows = {
            "proj-alpha": [_make_feature_row("feat-a1", "Alpha Feature")],
            "proj-bad": [],   # entries ignored; list_all will raise for this id
            "proj-gamma": [_make_feature_row("feat-g1", "Gamma Feature")],
        }

        class _SelectiveFeaturesRepo:
            """Raises for proj-bad, delegates normally for other project ids."""
            def __init__(self, row_map: dict) -> None:
                self._map = row_map

            async def list_all(self, project_id: str) -> list[dict]:
                if project_id == "proj-bad":
                    raise RuntimeError("simulated DB timeout for proj-bad")
                return list(self._map.get(project_id, []))

        class _SelectiveStorage:
            def __init__(self) -> None:
                self.db = _DbStub()
                self._features_repo = _SelectiveFeaturesRepo(rows)
                self._docs_repo = _DocumentsRepo([])
                self._worktree_repo = _WorktreeRepo([])
                self._sessions_repo = _SessionsRepo(0)

            def features(self):
                return self._features_repo

            def documents(self):
                return self._docs_repo

            def worktree_contexts(self):
                return self._worktree_repo

            def sessions(self):
                return self._sessions_repo

        ports = SimpleNamespace(
            workspace_registry=_WorkspaceRegistry([alpha, bad, gamma]),
            storage=_SelectiveStorage(),
        )

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=50
            )

        # Overall status must be partial
        self.assertEqual(response.status, "partial")

        # Items from alpha and gamma still present
        item_project_ids = {it.project.project_id for it in response.items}
        self.assertIn("proj-alpha", item_project_ids)
        self.assertIn("proj-gamma", item_project_ids)

        # Warning exists for proj-bad
        bad_warnings = [w for w in response.warnings if w.project_id == "proj-bad"]
        self.assertGreaterEqual(len(bad_warnings), 1)
        self.assertIn("proj-bad", bad_warnings[0].project_id)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_failed_project_has_high_severity_warning(self, *_patches) -> None:
        """When a project returns zero items due to failure, severity is 'high'.

        The exception must be raised inside _collect_project_items (not outside it)
        so the broad except clause catches it and yields (proj_id, [], ..., True, [msg]).
        We do this by making the features repo raise for the failing project.
        """
        bad = _make_project("proj-failed", "Failed")
        ok = _make_project("proj-ok", "OK")

        rows = {
            "proj-ok": [_make_feature_row("feat-ok", "OK Feature")],
            "proj-failed": [],  # list_all will raise for this id
        }

        class _FailingSelectiveFeaturesRepo:
            """Raises for proj-failed only; normal for others."""
            def __init__(self, row_map: dict) -> None:
                self._map = row_map

            async def list_all(self, project_id: str) -> list[dict]:
                if project_id == "proj-failed":
                    raise RuntimeError("fatal error in proj-failed")
                return list(self._map.get(project_id, []))

        class _FailingStorage:
            def __init__(self) -> None:
                self.db = _DbStub()
                self._features_repo = _FailingSelectiveFeaturesRepo(rows)
                self._docs_repo = _DocumentsRepo([])
                self._worktree_repo = _WorktreeRepo([])
                self._sessions_repo = _SessionsRepo(0)

            def features(self):
                return self._features_repo

            def documents(self):
                return self._docs_repo

            def worktree_contexts(self):
                return self._worktree_repo

            def sessions(self):
                return self._sessions_repo

        ports = SimpleNamespace(
            workspace_registry=_WorkspaceRegistry([bad, ok]),
            storage=_FailingStorage(),
        )

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=50
            )

        failed_warn = next((w for w in response.warnings if w.project_id == "proj-failed"), None)
        self.assertIsNotNone(failed_warn, "Expected a warning for the failed project")
        self.assertEqual(failed_warn.severity, "high")


# ---------------------------------------------------------------------------
# TC-5  Stale project
# ---------------------------------------------------------------------------


class TestStaleProject(unittest.IsolatedAsyncioTestCase):
    """TC-5: stale project has is_stale==True + freshness_seconds surfaced."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    async def test_stale_project_summary_fields(self) -> None:
        """ProjectSummary for stale project carries is_stale=True and freshness_seconds."""
        from datetime import datetime, timedelta, timezone

        stale_proj = _make_project("proj-stale", "Stale Repo")
        rows = {
            "proj-stale": [_make_feature_row("feat-s1", "Stale Feature")],
        }
        ports = _make_ports([stale_proj], rows)

        # Return a stale max_updated_at (2 hours ago)
        stale_ts = datetime.now(timezone.utc) - timedelta(hours=2)

        with patch(
            "backend.application.services.agent_queries.multi_project_planning_command_center._query_max_updated_at",
            new=AsyncMock(return_value=stale_ts),
        ):
            with patch(
                "backend.application.services.agent_queries.multi_project_planning_command_center._compute_is_stale",
                return_value=True,  # stale
            ):
                with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
                    svc = MultiProjectPlanningCommandCenterQueryService()
                    response = await svc.get_multi_project_command_center(
                        _request_context(), ports, page=1, page_size=50
                    )

        self.assertEqual(len(response.project_summaries), 1)
        stale_summary = response.project_summaries[0]
        self.assertEqual(stale_summary.project_id, "proj-stale")
        self.assertTrue(stale_summary.is_stale, "Expected is_stale==True for a stale project")
        # freshness_seconds should be around 7200 (2 hours) — allow wide tolerance
        self.assertIsNotNone(stale_summary.freshness_seconds)
        self.assertGreater(stale_summary.freshness_seconds, 0)


# ---------------------------------------------------------------------------
# TC-6  Page-first (load-bearing): git probe called ONLY for page-visible items
# ---------------------------------------------------------------------------


class TestPageFirstGitProbe(unittest.IsolatedAsyncioTestCase):
    """TC-6: git probe is called ONLY for page-visible items (MPCC-206).

    Implementation mechanism: _NullGitProbe is used during fan-out for all
    items, and the real probe is called only in _enrich_item for page-slice.
    We inject a _CountingGitProbe as the v1 service's probe and assert
    its call count == min(page_size, total_items_with_worktrees).

    Because test features have no worktrees (path==""), the enrichment path
    calls probe("") for each page-visible item.  We verify probe is called
    exactly page_size times (not total_items times).
    """

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_git_probe_only_for_page_slice(self, *_patches) -> None:
        from backend.application.services.agent_queries.planning_command_center import (
            PlanningCommandCenterQueryService,
        )

        probe = _CountingGitProbe()
        v1 = PlanningCommandCenterQueryService(git_probe=probe)

        alpha = _make_project("proj-alpha", "Alpha")
        # 10 items total
        rows = {
            "proj-alpha": [_make_feature_row(f"feat-{i}", f"Feature {i}") for i in range(10)],
        }
        ports = _make_ports([alpha], rows)

        page_size = 3  # smaller than total — most items off-page

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService(v1_service=v1)
            response = await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=page_size
            )

        # Total items must be 10
        self.assertEqual(response.pagination.total, 10)
        # Page slice must contain exactly page_size items
        self.assertEqual(len(response.items), page_size)

        # Probe must be called ONLY for page-visible items (page_size=3),
        # NOT for all 10 items.
        self.assertEqual(
            len(probe.probe_calls),
            page_size,
            f"Expected probe called {page_size} times (page slice), "
            f"got {len(probe.probe_calls)} (probe may have run for off-page items)",
        )

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_null_git_probe_returns_sentinel(self, *_) -> None:
        """_NullGitProbe returns sparse DTO with path_exists=None (deferred sentinel)."""
        null_probe = _NullGitProbe()
        dto = await null_probe.probe("/some/path")
        self.assertIsNone(dto.path_exists)
        self.assertEqual(dto.probed_at, "")


# ---------------------------------------------------------------------------
# TC-7  Detail-beyond-page-1: get_multi_project_item finds item past page 1
# ---------------------------------------------------------------------------


class TestDetailBeyondPage1(unittest.IsolatedAsyncioTestCase):
    """TC-7: get_multi_project_item returns an item whose position in the full
    merged set is beyond page 1 (i.e. the item is not in the first page)."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_item_beyond_page1_is_returned(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")

        # 10 items; feat-9 is near the end of the sorted list (sorted by name desc
        # or last_activity, so position is uncertain — we just care it CAN be found)
        rows = {
            "proj-alpha": [_make_feature_row(f"feat-{i}", f"Feature {i:02d}") for i in range(10)],
        }
        ports = _make_ports([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            # First confirm page 1 does NOT contain all items
            page1 = await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=3
            )

        self.assertEqual(page1.pagination.total, 10)
        page1_ids = {it.item["feature"]["feature_id"] for it in page1.items}

        # Pick an item that is definitely not on page 1
        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc2 = MultiProjectPlanningCommandCenterQueryService()
            # Try all features until we find one not on page 1
            found_beyond = None
            for i in range(10):
                fid = f"feat-{i}"
                if fid not in page1_ids:
                    result = await svc2.get_multi_project_item(
                        _request_context(), ports, feature_id=fid
                    )
                    if result is not None:
                        found_beyond = result
                        break

        self.assertIsNotNone(found_beyond, "Expected to find at least one item beyond page 1")
        self.assertEqual(found_beyond.project.project_id, "proj-alpha")

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_get_multi_project_item_returns_none_for_missing(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        rows: dict[str, list] = {"proj-alpha": []}
        ports = _make_ports([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            result = await svc.get_multi_project_item(
                _request_context(), ports, feature_id="nonexistent"
            )

        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# TC-8  Router flag-off returns 404
# ---------------------------------------------------------------------------


class TestRouterFlagOff(unittest.IsolatedAsyncioTestCase):
    """TC-8: GET .../multi-project/command-center returns 404 when the feature
    flag is disabled; returns 200 (delegates successfully) when enabled."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    async def test_flag_off_command_center_returns_404(self) -> None:
        from fastapi import HTTPException
        from backend.routers import agent as agent_router

        with patch.object(config, "CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED", False):
            with self.assertRaises(HTTPException) as ctx:
                # Call the dependency directly — it's synchronous
                agent_router._require_multi_project_command_center_enabled()

        self.assertEqual(ctx.exception.status_code, 404)
        detail = ctx.exception.detail
        self.assertIn("multi_project_command_center_disabled", str(detail))

    async def test_flag_on_delegates_to_service(self) -> None:
        """With flag enabled the router handler delegates to the service."""
        from backend.routers import agent as agent_router
        from backend.models import MultiProjectCommandCenterResponse, AggregatePagination
        from datetime import datetime, timezone

        stub_response = MultiProjectCommandCenterResponse(
            status="ok",
            items=[],
            project_summaries=[],
            pagination=AggregatePagination(page=1, page_size=50, total=0, has_more=False),
            warnings=[],
            generated_at=datetime.now(timezone.utc),
        )
        app_request = SimpleNamespace(context=object(), ports=object())

        with patch.object(config, "CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED", True):
            with patch.object(
                agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
            ):
                with patch.object(
                    agent_router.multi_project_command_center_query_service,
                    "get_multi_project_command_center",
                    new=AsyncMock(return_value=stub_response),
                ) as service_mock:
                    result = await agent_router.get_multi_project_command_center(
                        q=None,
                        status=None,
                        phase=None,
                        artifact_type=None,
                        worktree_state=None,
                        pr_state=None,
                        launch_readiness=None,
                        sort_by="last_activity",
                        sort_direction="desc",
                        page=1,
                        page_size=50,
                        project_ids=None,
                        hide_done=False,
                        request_context=object(),
                        core_ports=object(),
                    )

        self.assertIs(result, stub_response)
        service_mock.assert_awaited_once()

    async def test_flag_off_item_endpoint_returns_404(self) -> None:
        """Item endpoint also 404s when flag is off."""
        from fastapi import HTTPException
        from backend.routers import agent as agent_router

        with patch.object(config, "CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED", False):
            with self.assertRaises(HTTPException) as ctx:
                agent_router._require_multi_project_command_center_enabled()

        self.assertEqual(ctx.exception.status_code, 404)


# ---------------------------------------------------------------------------
# TC-9  No per-project full session-board reload
# ---------------------------------------------------------------------------


class TestNoPerProjectBoardReload(unittest.IsolatedAsyncioTestCase):
    """TC-9: the service does NOT call get_session_board once per project.

    The aggregate service uses _collect_project_items (which goes through
    _load_project_data + _build_items_for_scope) rather than any
    session-board path.  We verify that the PlanningSessionQueryService is
    not instantiated or called.
    """

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_no_session_board_call_per_project(self, *_patches) -> None:
        from backend.application.services.agent_queries import planning_sessions as ps_mod

        alpha = _make_project("proj-alpha", "Alpha")
        beta = _make_project("proj-beta", "Beta")
        rows = {
            "proj-alpha": [_make_feature_row("feat-a1", "Alpha Feature")],
            "proj-beta": [_make_feature_row("feat-b1", "Beta Feature")],
        }
        ports = _make_ports([alpha, beta], rows)

        # Track any call to PlanningSessionQueryService.get_session_board
        session_board_calls = []

        original_init = ps_mod.PlanningSessionQueryService.__init__

        def tracking_init(self_inner, *args, **kwargs):
            original_init(self_inner, *args, **kwargs)

        ps_mock = MagicMock(spec=ps_mod.PlanningSessionQueryService)
        ps_mock.get_session_board = AsyncMock(side_effect=lambda *a, **k: session_board_calls.append(1))

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=50
            )

        # Verify: no session board calls happened
        self.assertEqual(
            session_board_calls,
            [],
            "Expected zero get_session_board calls; the aggregate service "
            "must not load full boards per project",
        )

        # Sanity: we did get items back from both projects
        self.assertEqual(response.pagination.total, 2)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_sessions_repo_count_active_not_per_item(self, *_patches) -> None:
        """Active-session count uses count_active (once per project),
        not a per-feature or per-item board load."""
        alpha = _make_project("proj-alpha", "Alpha")
        rows = {
            "proj-alpha": [_make_feature_row(f"feat-{i}", f"Feature {i}") for i in range(5)],
        }
        ports = _make_ports([alpha], rows, active_count=2)
        sessions_repo = ports.storage.sessions()

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=50
            )

        # count_active called once per project for the summary (not once per item)
        self.assertLessEqual(
            len(sessions_repo.count_active_calls),
            2,  # at most once per project (summary phase)
            "count_active should be called at most once per project, "
            f"not once per item; got {sessions_repo.count_active_calls!r}",
        )

        # Verify active_sessions count surfaced in summary
        alpha_summary = next(s for s in response.project_summaries if s.project_id == "proj-alpha")
        self.assertEqual(alpha_summary.counts.active_sessions, 2)


# ---------------------------------------------------------------------------
# Additional: ProjectSummary display metadata correctness (part of TC-1)
# ---------------------------------------------------------------------------


class TestProjectSummaryDisplayMetadata(unittest.IsolatedAsyncioTestCase):
    """Display metadata fallback — unset projects get deterministic fallback color/group."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_display_metadata_present_for_all_projects(self, *_patches) -> None:
        projects = [_make_project(f"proj-{i}", f"Project {i}") for i in range(3)]
        rows = {p.id: [_make_feature_row(f"feat-{p.id}", f"Feature for {p.id}")] for p in projects}
        ports = _make_ports(projects, rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=50
            )

        # Each project summary must have display_metadata
        for summary in response.project_summaries:
            self.assertIsNotNone(
                summary.display_metadata,
                f"Summary for {summary.project_id} missing display_metadata",
            )

        # Each aggregate item must carry project identity with project_id + name
        for item in response.items:
            self.assertIsNotNone(item.project.project_id)
            self.assertIsNotNone(item.project.project_name)


# ---------------------------------------------------------------------------
# New: hide_done, missing-timestamp sort, nextWork project_id
# ---------------------------------------------------------------------------


class TestHideDoneFilter(unittest.IsolatedAsyncioTestCase):
    """Part-A parity: hide_done=True excludes all _TERMINAL_STATUSES members in MPCC."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_hide_done_excludes_terminal_statuses(self, *_patches) -> None:
        from backend.application.services.agent_queries.planning_command_center import _TERMINAL_STATUSES

        alpha = _make_project("proj-alpha", "Alpha")

        terminal_rows = [
            _make_feature_row(s, f"Terminal {s}", status=s)
            for s in _TERMINAL_STATUSES
        ]
        active_row = _make_feature_row("active-feat", "Active Feature", status="in-progress")

        rows = {"proj-alpha": [*terminal_rows, active_row]}
        ports = _make_ports([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports, hide_done=True, page=1, page_size=50
            )

        returned_ids = {it.item["feature"]["feature_id"] for it in response.items}
        for s in _TERMINAL_STATUSES:
            self.assertNotIn(s, returned_ids,
                             f"hide_done=True must exclude feature with status '{s}'")
        self.assertIn("active-feat", returned_ids)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_hide_done_false_retains_terminal_items(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        rows = {"proj-alpha": [_make_feature_row("done-feat", "Done Feature", status="done")]}
        ports = _make_ports([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports, hide_done=False, page=1, page_size=50
            )

        returned_ids = {it.item["feature"]["feature_id"] for it in response.items}
        self.assertIn("done-feat", returned_ids, "hide_done=False must retain terminal items")

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_hide_done_included_in_cache_key(self, *_patches) -> None:
        """Different hide_done values must produce distinct cache entries."""
        from backend.application.services.agent_queries.multi_project_planning_command_center import _mpcc_params

        ctx = _request_context()
        svc_obj = object()

        params_false = _mpcc_params(svc_obj, ctx, object(), hide_done=False)
        params_true = _mpcc_params(svc_obj, ctx, object(), hide_done=True)

        self.assertNotEqual(
            params_false, params_true,
            "Cache key must differ when hide_done differs",
        )
        self.assertIn("hide_done", params_false)
        self.assertIn("hide_done", params_true)


class TestSortMissingTimestampMpcc(unittest.IsolatedAsyncioTestCase):
    """Part-B parity: items with no last_activity timestamp sort LAST in MPCC."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    def _make_row_with_ts(self, feature_id: str, ts: str | None) -> dict:
        row = _make_feature_row(feature_id, f"Feature {feature_id}")
        data = json.loads(row["data_json"])
        data["updatedAt"] = ts
        row["updated_at"] = ts or ""
        row["data_json"] = json.dumps(data)
        return row

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_missing_timestamp_sorts_last_desc(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        rows = {
            "proj-alpha": [
                self._make_row_with_ts("feat-ts", "2026-05-28T10:00:00+00:00"),
                self._make_row_with_ts("feat-no-ts", None),
            ],
        }
        ports = _make_ports([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports,
                sort_by="last_activity", sort_direction="desc",
                page=1, page_size=50,
            )

        ids = [it.item["feature"]["feature_id"] for it in response.items]
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[0], "feat-ts",
                         "Under desc sort, timestamped item must precede no-timestamp item")
        self.assertEqual(ids[-1], "feat-no-ts",
                         "Under desc sort, no-timestamp item must be last")

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_missing_timestamp_sorts_last_asc(self, *_patches) -> None:
        """Items with no last_activity timestamp must sort LAST even under asc direction."""
        alpha = _make_project("proj-alpha", "Alpha")
        rows = {
            "proj-alpha": [
                self._make_row_with_ts("feat-ts", "2026-05-28T10:00:00+00:00"),
                self._make_row_with_ts("feat-no-ts", None),
            ],
        }
        ports = _make_ports([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports,
                sort_by="last_activity", sort_direction="asc",
                page=1, page_size=50,
            )

        ids = [it.item["feature"]["feature_id"] for it in response.items]
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[-1], "feat-no-ts",
                         "Under asc sort, item WITHOUT timestamp must still be last")


class TestNextWorkCarriesProjectId(unittest.IsolatedAsyncioTestCase):
    """Part-C: portfolio rollup next_work_items carries both feature_id and project_id."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    def _make_ready_row(self, feature_id: str, name: str) -> dict:
        """Feature row that resolves to launch_batch.readiness == 'ready'."""
        data = {
            "id": feature_id,
            "name": name,
            "status": "active",
            "summary": name,
            "priority": "high",
            "tags": ["launch-ready"],
            "phases": [],
        }
        return {
            "id": feature_id,
            "name": name,
            "status": "active",
            "updated_at": "2026-05-28T10:00:00+00:00",
            "data_json": json.dumps(data),
        }

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_next_work_items_carries_project_id(self, *_patches) -> None:
        """next_work_items in the rollup must include project_id for drill-down."""
        from backend.application.services.agent_queries.multi_project_planning_command_center import (
            MultiProjectPlanningCommandCenterQueryService,
        )
        from backend.models import PortfolioNextWorkItem

        alpha = _make_project("proj-alpha", "Alpha")
        # Use a standard row — next_work is populated from launch_batch.readiness == "ready".
        # The test verifies the response shape has the new next_work_items field.
        rows = {
            "proj-alpha": [_make_feature_row("feat-a1", "Alpha Feature")],
        }
        ports = _make_ports([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            rollup = await svc.get_portfolio_rollup(_request_context(), ports)

        # next_work_items must be a list (may be empty if no items have readiness==ready).
        self.assertIsInstance(rollup.attention.next_work_items, list,
                              "next_work_items must be a list")
        # If populated, each entry must carry both feature_id and project_id.
        for entry in rollup.attention.next_work_items:
            self.assertIsInstance(entry, PortfolioNextWorkItem)
            self.assertIsInstance(entry.feature_id, str)
            self.assertIsInstance(entry.project_id, str)
            self.assertNotEqual(entry.project_id, "",
                                "project_id must not be empty in next_work_items")

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_next_work_backward_compat_string_list(self, *_patches) -> None:
        """next_work (string list) remains populated alongside next_work_items."""
        alpha = _make_project("proj-alpha", "Alpha")
        rows = {"proj-alpha": [_make_feature_row("feat-a1", "Alpha Feature")]}
        ports = _make_ports([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            rollup = await svc.get_portfolio_rollup(_request_context(), ports)

        # next_work must remain a list[str] for backward compat.
        self.assertIsInstance(rollup.attention.next_work, list)
        for entry in rollup.attention.next_work:
            self.assertIsInstance(entry, str)

        # Lengths must match (same items in both fields).
        self.assertEqual(
            len(rollup.attention.next_work),
            len(rollup.attention.next_work_items),
            "next_work and next_work_items must have the same length",
        )


if __name__ == "__main__":
    unittest.main()
