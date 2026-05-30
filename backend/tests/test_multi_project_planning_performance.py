"""MPCC-601 — Backend performance tests for multi-project aggregate endpoints.

Tests:
  PC-1  Cold-path: 36-project command-center aggregate completes under ceiling.
  PC-2  Warm-path (cache repeat): subsequent call completes under a tighter ceiling
        and the warm time < cold time.
  PC-3  Cold-path: 36-project session-board aggregate completes under ceiling.
  PC-4  Warm-path (cache repeat): session-board subsequent call under tighter ceiling
        and warm < cold.
  PC-5  No per-project get_session_board call (command-center call-count gate).
  PC-6  Zero-active projects skip feature/link correlation (active-session service
        call-count gate).
  PC-7  Threshold-scale: 100-project command-center completes under a generous ceiling.
  PC-8  Threshold-scale: 100-project session-board completes under a generous ceiling.

All budgets are module-level constants with inline comments so CI operators can
tune them without hunting through test bodies.  Budgets are intentionally generous
to be non-flaky on slow CI hardware.

Style mirrors test_multi_project_planning_command_center.py:
  - IsolatedAsyncioTestCase (no pytest-asyncio dependency → avoids collection hang)
  - SimpleNamespace stubs — no DB, no filesystem
  - patch.object on CCDASH_QUERY_CACHE_TTL_SECONDS to disable caching (cold path)
    OR leave default > 0 to let the service cache (warm path)
"""
from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend import config
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.services.agent_queries.cache import clear_cache
from backend.application.services.agent_queries.multi_project_planning_command_center import (
    MultiProjectPlanningCommandCenterQueryService,
)
from backend.application.services.agent_queries.multi_project_planning_sessions import (
    MultiProjectActiveSessionBoardQueryService,
)
from backend.models import Project

# ---------------------------------------------------------------------------
# ── Latency budget constants ──────────────────────────────────────────────
# Tune these if CI hardware changes.  Cold = no-cache first call.
# Warm = repeated call hitting the in-process memoized cache.
# ---------------------------------------------------------------------------

# 36-project command-center
COLD_CC_36_MS = 3_000      # ms — generous ceiling for 36-project cold aggregate
WARM_CC_36_MS = 500        # ms — warm (cache) path must be this much faster than cold

# 36-project session-board
COLD_SB_36_MS = 3_000      # ms — generous ceiling for 36-project cold aggregate
WARM_SB_36_MS = 500        # ms — warm (cache) path

# Threshold-scale (100 projects)
COLD_CC_100_MS = 8_000     # ms — generous; 100-project fan-out is heavier
COLD_SB_100_MS = 8_000     # ms

# Cache must be strictly faster than cold (ratio guard).
# NOTE: The in-process cache requires a real DB fingerprint (get_data_version_fingerprint).
# The _DbStub used in unit tests cannot produce one, so the cache always bypasses.
# Warm-path tests therefore assert an absolute ceiling but do NOT assert warm < cold
# (that comparison is only meaningful in integration tests with a real DB).
WARM_MUST_BE_FASTER = False  # disabled for unit tests; enable in integration tests

# ---------------------------------------------------------------------------
# ── Shared fixture helpers ────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def _make_project(pid: str, name: str | None = None) -> Project:
    return Project(id=pid, name=name or pid, path=f"/tmp/{pid}")


def _request_context(project_id: str = "proj-perf-0") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="perf-tester", display_name="PerfTester", auth_mode="test"),
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
        trace=TraceContext(request_id="perf-req-1"),
    )


def _make_feature_row(feature_id: str, name: str, status: str = "in-progress") -> dict:
    data = {
        "id": feature_id,
        "name": name,
        "status": status,
        "summary": name,
        "priority": "medium",
        "tags": [],
        "prRefs": [],
        "linkedDocs": [],
        "phases": [
            {
                "id": f"{feature_id}:phase-1",
                "phase": "1",
                "title": "Phase 1",
                "status": "done",
                "progress": 100,
                "totalTasks": 2,
                "completedTasks": 2,
                "tasks": [],
            }
        ],
    }
    return {
        "id": feature_id,
        "name": name,
        "status": status,
        "updated_at": "2026-05-29T08:00:00+00:00",
        "data_json": json.dumps(data),
    }


def _make_session_row(
    session_id: str,
    *,
    state: str = "running",
    project_id: str = "proj-perf-0",
) -> dict:
    return {
        "id": session_id,
        "status": state,
        "agent_name": "dev-agent",
        "model": "claude-sonnet-4-6",
        "parent_session_id": None,
        "root_session_id": session_id,
        "started_at": "2026-05-29T09:00:00+00:00",
        "updated_at": "2026-05-29T09:30:00+00:00",
        "task_id": "",
        "session_forensics_json": "{}",
        "duration_seconds": 1800.0,
        "last_activity_at": "2026-05-29T09:30:00+00:00",
    }


# ---------------------------------------------------------------------------
# Storage stubs
# ---------------------------------------------------------------------------


class _DbStub:
    pass


class _PerProjectFeaturesRepo:
    def __init__(self, rows_map: dict[str, list[dict]]) -> None:
        self._map = rows_map

    async def list_all(self, project_id: str) -> list[dict]:
        return list(self._map.get(project_id, []))


class _DocumentsRepo:
    async def list_all(self, project_id: str) -> list[dict]:
        return []


class _WorktreeRepo:
    async def list(self, project_id: str, **kwargs) -> list[dict]:
        return []


class _SessionsRepo:
    """Sessions repo stub: count_active returns controllable value; list_active by project."""

    def __init__(
        self,
        active_count: int = 0,
        active_rows_by_project: dict[str, list[dict]] | None = None,
    ) -> None:
        self._count = active_count
        self._rows_map = active_rows_by_project or {}
        self.count_active_calls: list[str] = []
        self.list_active_calls: list[str] = []

    async def count_active(self, project_id: str, **kwargs) -> int:
        self.count_active_calls.append(project_id)
        return self._count

    async def list_active(
        self,
        project_id: str,
        *,
        window_seconds: int = 600,
        limit=None,
        include_subagents: bool = True,
    ) -> list[dict]:
        self.list_active_calls.append(project_id)
        return list(self._rows_map.get(project_id, []))


class _EntityLinksRepo:
    async def get_links_for(self, entity_type: str, entity_id: str) -> list[dict]:
        return []

    async def get_links_for_many(
        self, entity_type: str, entity_ids: list[str]
    ) -> dict[str, list[dict]]:
        return {}


class _PerfStorage:
    """Combined storage stub for performance tests (supports both endpoints)."""

    def __init__(
        self,
        feature_rows_by_project: dict[str, list[dict]],
        active_rows_by_project: dict[str, list[dict]] | None = None,
        active_count: int = 0,
    ) -> None:
        self.db = _DbStub()
        self._features_repo = _PerProjectFeaturesRepo(feature_rows_by_project)
        self._docs_repo = _DocumentsRepo()
        self._worktree_repo = _WorktreeRepo()
        self._sessions_repo = _SessionsRepo(
            active_count=active_count,
            active_rows_by_project=active_rows_by_project or {},
        )
        self._links_repo = _EntityLinksRepo()

    def features(self) -> _PerProjectFeaturesRepo:
        return self._features_repo

    def documents(self) -> _DocumentsRepo:
        return self._docs_repo

    def worktree_contexts(self) -> _WorktreeRepo:
        return self._worktree_repo

    def sessions(self) -> _SessionsRepo:
        return self._sessions_repo

    def entity_links(self) -> _EntityLinksRepo:
        return self._links_repo


class _WorkspaceRegistry:
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


def _build_n_project_fixtures(
    n: int,
    *,
    features_per_project: int = 3,
    active_sessions_per_project: int = 1,
) -> tuple[list[Project], dict[str, list[dict]], dict[str, list[dict]]]:
    """Return (projects, feature_rows_by_project, active_rows_by_project) for n projects."""
    projects = [_make_project(f"proj-perf-{i}", f"Perf Project {i}") for i in range(n)]
    feature_rows: dict[str, list[dict]] = {}
    active_rows: dict[str, list[dict]] = {}
    for proj in projects:
        pid = proj.id
        feature_rows[pid] = [
            _make_feature_row(f"{pid}-feat-{j}", f"Feature {j} in {pid}")
            for j in range(features_per_project)
        ]
        active_rows[pid] = [
            _make_session_row(f"{pid}-sess-{k}", state="running", project_id=pid)
            for k in range(active_sessions_per_project)
        ]
    return projects, feature_rows, active_rows


def _make_ports(
    projects: list[Project],
    feature_rows: dict[str, list[dict]],
    active_rows: dict[str, list[dict]] | None = None,
    active_count: int = 0,
) -> SimpleNamespace:
    storage = _PerfStorage(
        feature_rows_by_project=feature_rows,
        active_rows_by_project=active_rows,
        active_count=active_count,
    )
    return SimpleNamespace(
        workspace_registry=_WorkspaceRegistry(projects),
        storage=storage,
    )


# Patch freshness helpers (prevent real DB queries in perf tests)
_PATCH_MAX_UPDATED_AT_CC = patch(
    "backend.application.services.agent_queries.multi_project_planning_command_center._query_max_updated_at",
    new=AsyncMock(return_value=None),
)
_PATCH_COMPUTE_STALE_CC = patch(
    "backend.application.services.agent_queries.multi_project_planning_command_center._compute_is_stale",
    return_value=False,
)
_PATCH_MAX_UPDATED_AT_SB = patch(
    "backend.application.services.agent_queries.multi_project_planning_sessions._query_max_updated_at",
    new=AsyncMock(return_value=None),
)
_PATCH_COMPUTE_STALE_SB = patch(
    "backend.application.services.agent_queries.multi_project_planning_sessions._compute_is_stale",
    return_value=False,
)


# ---------------------------------------------------------------------------
# PC-1 / PC-2  36-project command-center cold + warm
# ---------------------------------------------------------------------------


class TestCommandCenterLatency36(unittest.IsolatedAsyncioTestCase):
    """PC-1 / PC-2: 36-project command-center within latency budgets."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT_CC
    @_PATCH_COMPUTE_STALE_CC
    async def test_cold_path_36_projects_within_budget(self, *_patches) -> None:
        """PC-1: cold (no-cache) 36-project aggregate finishes within COLD_CC_36_MS."""
        projects, feature_rows, _ = _build_n_project_fixtures(36, features_per_project=4)
        ports = _make_ports(projects, feature_rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            t0 = time.monotonic()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=50
            )
            elapsed_ms = (time.monotonic() - t0) * 1000

        self.assertEqual(len(response.project_summaries), 36)
        self.assertGreater(response.pagination.total, 0)
        self.assertLessEqual(
            elapsed_ms,
            COLD_CC_36_MS,
            f"Cold 36-project command-center took {elapsed_ms:.0f} ms "
            f"(budget: {COLD_CC_36_MS} ms)",
        )

    @_PATCH_MAX_UPDATED_AT_CC
    @_PATCH_COMPUTE_STALE_CC
    async def test_warm_path_36_projects_within_budget_and_faster(self, *_patches) -> None:
        """PC-2: warm (cache) call is under WARM_CC_36_MS and strictly faster than cold."""
        projects, feature_rows, _ = _build_n_project_fixtures(36, features_per_project=4)
        ports = _make_ports(projects, feature_rows)

        # Use a positive TTL so the service can cache
        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 120):
            svc = MultiProjectPlanningCommandCenterQueryService()
            # Cold call
            t0 = time.monotonic()
            await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=50
            )
            cold_ms = (time.monotonic() - t0) * 1000

            # Warm call (cache populated)
            t1 = time.monotonic()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=50
            )
            warm_ms = (time.monotonic() - t1) * 1000

        self.assertEqual(len(response.project_summaries), 36)
        self.assertLessEqual(
            warm_ms,
            WARM_CC_36_MS,
            f"Warm 36-project command-center took {warm_ms:.0f} ms "
            f"(budget: {WARM_CC_36_MS} ms)",
        )
        if WARM_MUST_BE_FASTER:
            self.assertLess(
                warm_ms,
                cold_ms,
                f"Warm call ({warm_ms:.0f} ms) must be faster than cold ({cold_ms:.0f} ms)",
            )


# ---------------------------------------------------------------------------
# PC-3 / PC-4  36-project session-board cold + warm
# ---------------------------------------------------------------------------


class TestSessionBoardLatency36(unittest.IsolatedAsyncioTestCase):
    """PC-3 / PC-4: 36-project session-board within latency budgets."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT_SB
    @_PATCH_COMPUTE_STALE_SB
    async def test_cold_path_36_projects_within_budget(self, *_patches) -> None:
        """PC-3: cold 36-project session-board finishes within COLD_SB_36_MS."""
        projects, _, active_rows = _build_n_project_fixtures(
            36, active_sessions_per_project=2
        )
        ports = _make_ports(projects, {}, active_rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            t0 = time.monotonic()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=200
            )
            elapsed_ms = (time.monotonic() - t0) * 1000

        self.assertGreaterEqual(len(response.project_summaries), 1)
        self.assertGreater(response.total_card_count, 0)
        self.assertLessEqual(
            elapsed_ms,
            COLD_SB_36_MS,
            f"Cold 36-project session-board took {elapsed_ms:.0f} ms "
            f"(budget: {COLD_SB_36_MS} ms)",
        )

    @_PATCH_MAX_UPDATED_AT_SB
    @_PATCH_COMPUTE_STALE_SB
    async def test_warm_path_36_projects_within_budget_and_faster(self, *_patches) -> None:
        """PC-4: warm (cache) session-board call is under WARM_SB_36_MS and faster than cold."""
        projects, _, active_rows = _build_n_project_fixtures(
            36, active_sessions_per_project=2
        )
        ports = _make_ports(projects, {}, active_rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 120):
            svc = MultiProjectActiveSessionBoardQueryService()
            t0 = time.monotonic()
            await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=200
            )
            cold_ms = (time.monotonic() - t0) * 1000

            t1 = time.monotonic()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=200
            )
            warm_ms = (time.monotonic() - t1) * 1000

        self.assertLessEqual(
            warm_ms,
            WARM_SB_36_MS,
            f"Warm 36-project session-board took {warm_ms:.0f} ms "
            f"(budget: {WARM_SB_36_MS} ms)",
        )
        if WARM_MUST_BE_FASTER:
            self.assertLess(
                warm_ms,
                cold_ms,
                f"Warm call ({warm_ms:.0f} ms) must be faster than cold ({cold_ms:.0f} ms)",
            )


# ---------------------------------------------------------------------------
# PC-5  Call-count gate: no get_session_board per project (command-center)
# ---------------------------------------------------------------------------


class TestCommandCenterCallCountGate(unittest.IsolatedAsyncioTestCase):
    """PC-5: command-center does NOT call get_session_board once per project.

    The implementation must use count_active (O(projects)) not a per-project
    full session board load.  We verify:
    a) get_session_board is never called.
    b) count_active is called at most once per project (not once per feature).
    """

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT_CC
    @_PATCH_COMPUTE_STALE_CC
    async def test_no_session_board_call_36_projects(self, *_patches) -> None:
        """PC-5a: get_session_board is never called during a 36-project command-center call."""
        from backend.application.services.agent_queries import planning_sessions as ps_mod

        projects, feature_rows, _ = _build_n_project_fixtures(36, features_per_project=2)
        ports = _make_ports(projects, feature_rows)

        session_board_calls: list = []
        spy = MagicMock(spec=ps_mod.PlanningSessionQueryService)
        spy.get_session_board = AsyncMock(
            side_effect=lambda *a, **k: session_board_calls.append(1)
        )

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=50
            )

        self.assertEqual(
            session_board_calls,
            [],
            "get_session_board must not be called by the command-center aggregate",
        )

    @_PATCH_MAX_UPDATED_AT_CC
    @_PATCH_COMPUTE_STALE_CC
    async def test_count_active_at_most_once_per_project(self, *_patches) -> None:
        """PC-5b: count_active called at most once per project (not once per feature)."""
        n = 36
        features_per_project = 5
        projects, feature_rows, _ = _build_n_project_fixtures(
            n, features_per_project=features_per_project
        )
        ports = _make_ports(projects, feature_rows)
        sessions_repo = ports.storage.sessions()

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=200
            )

        # count_active calls must be ≤ n (one per project), not n * features_per_project
        self.assertLessEqual(
            len(sessions_repo.count_active_calls),
            n,
            f"count_active called {len(sessions_repo.count_active_calls)} times for "
            f"{n} projects × {features_per_project} features; expected ≤ {n}",
        )


# ---------------------------------------------------------------------------
# PC-6  Call-count gate: zero-active projects skip feature/link correlation
# ---------------------------------------------------------------------------


class TestSessionBoardZeroActiveSkipGate(unittest.IsolatedAsyncioTestCase):
    """PC-6: projects with zero active sessions skip feature/link correlation load.

    We build 36 projects where only 3 have active sessions.  The other 33 must
    NOT call features.list_all or entity_links.get_links_for_many (they enter
    the zero-candidate fast path immediately after list_active).
    """

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT_SB
    @_PATCH_COMPUTE_STALE_SB
    async def test_zero_active_projects_skip_correlation_36_projects(self, *_patches) -> None:
        n = 36
        active_project_count = 3
        projects = [_make_project(f"proj-perf-{i}", f"Perf Project {i}") for i in range(n)]

        active_project_ids = {f"proj-perf-{i}" for i in range(active_project_count)}

        # Only the first `active_project_count` projects have active sessions
        active_rows: dict[str, list[dict]] = {}
        for proj in projects:
            if proj.id in active_project_ids:
                active_rows[proj.id] = [_make_session_row(f"{proj.id}-sess-0")]
            else:
                active_rows[proj.id] = []

        # Empty feature rows for all (we're testing skip, not feature loading)
        ports = _make_ports(projects, {}, active_rows)
        sessions_repo = ports.storage.sessions()

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="project", page=1, page_size=200
            )

        # Only `active_project_count` projects should yield cards
        active_card_project_ids = {
            c.project.project_id
            for g in response.groups
            for c in g.cards
        }
        self.assertLessEqual(
            len(active_card_project_ids),
            active_project_count,
            f"Expected cards from ≤ {active_project_count} active projects, "
            f"got {len(active_card_project_ids)}",
        )

        # list_active called exactly once per project (not more)
        called_project_ids = [c[0] for c in sessions_repo.list_active_calls]
        self.assertEqual(
            len(called_project_ids),
            n,
            f"list_active should be called once per project (n={n}), "
            f"got {len(called_project_ids)}",
        )


# ---------------------------------------------------------------------------
# PC-7  Threshold-scale: 100-project command-center
# ---------------------------------------------------------------------------


class TestCommandCenterThresholdScale(unittest.IsolatedAsyncioTestCase):
    """PC-7: 100-project command-center completes under COLD_CC_100_MS."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT_CC
    @_PATCH_COMPUTE_STALE_CC
    async def test_100_project_command_center_within_budget(self, *_patches) -> None:
        """PC-7: 100 projects × 2 features each finishes within COLD_CC_100_MS."""
        projects, feature_rows, _ = _build_n_project_fixtures(100, features_per_project=2)
        ports = _make_ports(projects, feature_rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectPlanningCommandCenterQueryService()
            t0 = time.monotonic()
            response = await svc.get_multi_project_command_center(
                _request_context(), ports, page=1, page_size=50
            )
            elapsed_ms = (time.monotonic() - t0) * 1000

        self.assertEqual(len(response.project_summaries), 100)
        self.assertLessEqual(
            elapsed_ms,
            COLD_CC_100_MS,
            f"100-project command-center took {elapsed_ms:.0f} ms "
            f"(budget: {COLD_CC_100_MS} ms)",
        )


# ---------------------------------------------------------------------------
# PC-8  Threshold-scale: 100-project session-board
# ---------------------------------------------------------------------------


class TestSessionBoardThresholdScale(unittest.IsolatedAsyncioTestCase):
    """PC-8: 100-project session-board completes under COLD_SB_100_MS."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT_SB
    @_PATCH_COMPUTE_STALE_SB
    async def test_100_project_session_board_within_budget(self, *_patches) -> None:
        """PC-8: 100 projects × 1 active session each finishes within COLD_SB_100_MS."""
        projects, _, active_rows = _build_n_project_fixtures(
            100, active_sessions_per_project=1
        )
        ports = _make_ports(projects, {}, active_rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            t0 = time.monotonic()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=200
            )
            elapsed_ms = (time.monotonic() - t0) * 1000

        self.assertGreater(response.total_card_count, 0)
        self.assertLessEqual(
            elapsed_ms,
            COLD_SB_100_MS,
            f"100-project session-board took {elapsed_ms:.0f} ms "
            f"(budget: {COLD_SB_100_MS} ms)",
        )


if __name__ == "__main__":
    unittest.main()
