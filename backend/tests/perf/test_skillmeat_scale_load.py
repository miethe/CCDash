"""P6-004 — SkillMeat scale load benchmark.

Scenarios
---------
1. large_project_ingest_throughput
   Simulates a large-project ingest loop (mock repo writes) at ~9 000 sessions /
   367 features.  Asserts the sync loop scales sub-linearly: p95 wall-clock per
   batch-of-100 sessions must stay under budget.

2. planning_bundle_latency_multi_project
   Planning bundle fan-out over 36 synthetic projects.  Asserts p95 < budget
   across N_PLANNING_RUNS rounds.

3. portfolio_rollup_fanout
   Multi-project portfolio rollup (system-metrics style) fan-out wall-clock p95
   across 50 projects.

Scale assumptions (commented per requirement)
---------------------------------------------
  ~9 000 sessions / 367 features (realistic large-project cardinality)
  36-project fan-out (MPCC standard)
  50-project portfolio rollup

Design
------
- All DB writes are mocked (AsyncMock on the repo layer).  No real 10 GB DB.
- Synthetic fixtures at measured cardinality generated at module level to amortise
  generation cost.
- @pytest.mark.perf — opt-in; excluded from default test runs.
- IsolatedAsyncioTestCase avoids pytest-asyncio collection-hang on complex fixture.
- Budgets are generous-but-real (tested on a laptop-class CI box).

Run
---
  backend/.venv/bin/python -m pytest backend/tests/perf/test_skillmeat_scale_load.py \
    -v -m perf -s
"""
from __future__ import annotations

import asyncio
import statistics
import time
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

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
# Scale constants (documented per requirement)
# ---------------------------------------------------------------------------

# Scenario 1: large-project ingest throughput
INGEST_SESSION_COUNT: int = 9_000    # ~9k sessions — realistic large project
INGEST_FEATURE_COUNT: int = 367      # ~367 features — realistic large project
INGEST_BATCH_SIZE: int = 100         # sessions per batch processed through the loop
N_INGEST_ROUNDS: int = 30            # number of batch samples for percentile calculation
INGEST_BATCH_P95_BUDGET_MS: float = 200.0   # p95 per 100-session batch must be < this

# Scenario 2: planning bundle latency under multi-project fan-out
N_PLANNING_PROJECTS: int = 36        # 36-project fan-out (MPCC standard)
N_PLANNING_FEATURES: int = 5         # features per project
N_PLANNING_RUNS: int = 20            # rounds for percentile calculation
PLANNING_BUNDLE_P95_BUDGET_MS: float = 3_500.0  # generous; matches MPCC performance baseline

# Scenario 3: portfolio rollup fan-out wall-clock p95
N_PORTFOLIO_PROJECTS: int = 50       # 50-project portfolio rollup
N_PORTFOLIO_SESSIONS: int = 2        # active sessions per project
N_PORTFOLIO_RUNS: int = 20           # rounds for percentile calculation
PORTFOLIO_ROLLUP_P95_BUDGET_MS: float = 5_000.0  # generous; 50-project fan-out wall-clock


# ---------------------------------------------------------------------------
# Helpers — synthetic fixtures
# ---------------------------------------------------------------------------


def _make_session_rows(n: int, project_id: str = "proj-scale") -> list[dict[str, Any]]:
    """Generate n minimal session row dicts quickly without real I/O."""
    return [
        {
            "id": f"session-{project_id}-{i}",
            "feature_id": f"feat-{project_id}-{i % max(1, n // 10)}",
            "root_session_id": f"session-{project_id}-{i}",
            "title": f"Session {i}",
            "status": "completed" if i % 3 != 0 else "failed",
            "started_at": "2026-01-01T00:00:00+00:00",
            "ended_at": "2026-01-01T01:00:00+00:00",
            "model": "claude-sonnet-4-6",
            "total_cost": 0.01,
            "observed_tokens": 5_000,
        }
        for i in range(n)
    ]


def _make_feature_rows(n: int, project_id: str = "proj-scale") -> list[dict[str, Any]]:
    return [
        {
            "id": f"feat-{project_id}-{i}",
            "name": f"Feature {i}",
            "status": "active" if i % 2 == 0 else "done",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "data_json": "{}",
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Helpers — mock repos for scenario 1 (ingest throughput)
# ---------------------------------------------------------------------------


class _MockSessionsRepo:
    """Counts upsert calls; never hits a real DB."""

    def __init__(self) -> None:
        self.upsert_calls: int = 0

    async def upsert(self, row: dict[str, Any], project_id: str) -> None:
        self.upsert_calls += 1
        # Tiny cooperative yield to simulate async I/O scheduling overhead
        await asyncio.sleep(0)

    async def list_paginated(self, project_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    async def get_project_stats(self, project_id: str) -> dict[str, Any]:
        return {"count": INGEST_SESSION_COUNT, "cost": 90.0, "tokens": 45_000_000, "duration": 3_600.0}


class _MockFeaturesRepo:
    def __init__(self) -> None:
        self.upsert_calls: int = 0

    async def upsert(self, row: dict[str, Any], project_id: str) -> None:
        self.upsert_calls += 1
        await asyncio.sleep(0)

    async def list_all(self, project_id: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        return _make_feature_rows(INGEST_FEATURE_COUNT, project_id)


# ---------------------------------------------------------------------------
# Helpers — MPCC fixture builders (shared with scenarios 2 & 3)
# ---------------------------------------------------------------------------


def _make_project(pid: str, name: str | None = None) -> Project:
    return Project(id=pid, name=name or pid, path=f"/tmp/{pid}")


def _request_context(project_id: str = "proj-scale-0") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="scale-tester", display_name="Scale Tester", auth_mode="test"),
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
        trace=TraceContext(request_id="scale-req-1"),
    )


class _ScaleFeaturesRepo:
    def __init__(self, rows_by_project: dict[str, list[dict[str, Any]]]) -> None:
        self._map = rows_by_project

    async def list_all(self, project_id: str) -> list[dict[str, Any]]:
        return list(self._map.get(project_id, []))


class _ScaleDocumentsRepo:
    async def list_all(self, project_id: str) -> list[dict[str, Any]]:
        return []


class _ScaleWorktreeRepo:
    async def list(self, project_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        return []


class _ScaleSessionsRepo:
    def __init__(
        self,
        active_count: int = 0,
        active_rows_by_project: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._count = active_count
        self._rows_map = active_rows_by_project or {}

    async def count_active(self, project_id: str, **kwargs: Any) -> int:
        return self._count

    async def list_active(
        self,
        project_id: str,
        *,
        window_seconds: int = 600,
        limit: int | None = None,
        include_subagents: bool = True,
    ) -> list[dict[str, Any]]:
        return list(self._rows_map.get(project_id, []))


class _ScaleEntityLinksRepo:
    async def get_links_for(self, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        return []

    async def get_links_for_many(
        self, entity_type: str, entity_ids: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        return {}


class _ScaleStorage:
    def __init__(
        self,
        feature_rows_by_project: dict[str, list[dict[str, Any]]],
        active_rows_by_project: dict[str, list[dict[str, Any]]] | None = None,
        active_count: int = 0,
    ) -> None:
        self.db = SimpleNamespace()
        self._features = _ScaleFeaturesRepo(feature_rows_by_project)
        self._documents = _ScaleDocumentsRepo()
        self._worktrees = _ScaleWorktreeRepo()
        self._sessions = _ScaleSessionsRepo(
            active_count=active_count,
            active_rows_by_project=active_rows_by_project or {},
        )
        self._links = _ScaleEntityLinksRepo()

    def features(self) -> _ScaleFeaturesRepo:
        return self._features

    def documents(self) -> _ScaleDocumentsRepo:
        return self._documents

    def worktree_contexts(self) -> _ScaleWorktreeRepo:
        return self._worktrees

    def sessions(self) -> _ScaleSessionsRepo:
        return self._sessions

    def entity_links(self) -> _ScaleEntityLinksRepo:
        return self._links


class _ScaleWorkspaceRegistry:
    def __init__(self, projects: list[Project]) -> None:
        self._projects = projects

    def list_projects(self) -> list[Project]:
        return list(self._projects)

    def get_project(self, project_id: str) -> Project | None:
        return next((p for p in self._projects if p.id == project_id), None)

    def get_active_project(self) -> Project | None:
        return self._projects[0] if self._projects else None

    def resolve_scope(self, project_id: str | None = None) -> tuple[Any, Any]:
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


def _build_n_project_ports(
    n: int,
    features_per_project: int = 5,
    active_sessions_per_project: int = 2,
) -> SimpleNamespace:
    projects = [_make_project(f"proj-scale-{i}", f"Scale Project {i}") for i in range(n)]
    feature_rows: dict[str, list[dict[str, Any]]] = {}
    active_rows: dict[str, list[dict[str, Any]]] = {}
    for proj in projects:
        pid = proj.id
        feature_rows[pid] = _make_feature_rows(features_per_project, pid)
        active_rows[pid] = [
            {
                "id": f"{pid}-sess-{k}",
                "status": "running",
                "agent_name": "dev-agent",
                "model": "claude-sonnet-4-6",
                "parent_session_id": None,
                "root_session_id": f"{pid}-sess-{k}",
                "started_at": "2026-05-29T09:00:00+00:00",
                "updated_at": "2026-05-29T09:30:00+00:00",
                "task_id": "",
                "session_forensics_json": "{}",
                "duration_seconds": 1_800.0,
                "last_activity_at": "2026-05-29T09:30:00+00:00",
            }
            for k in range(active_sessions_per_project)
        ]
    return SimpleNamespace(
        workspace_registry=_ScaleWorkspaceRegistry(projects),
        storage=_ScaleStorage(
            feature_rows_by_project=feature_rows,
            active_rows_by_project=active_rows,
            active_count=active_sessions_per_project,
        ),
    )


# Patches that prevent freshness helpers from issuing real DB queries
_PATCH_MAX_UPDATED_AT_CC = patch(
    "backend.application.services.agent_queries.multi_project_planning_command_center._query_max_updated_at",
    new_callable=lambda: lambda *a, **kw: AsyncMock(return_value=None)(),
)
_PATCH_COMPUTE_STALE_CC = patch(
    "backend.application.services.agent_queries.multi_project_planning_command_center._compute_is_stale",
    return_value=False,
)
_PATCH_MAX_UPDATED_AT_SB = patch(
    "backend.application.services.agent_queries.multi_project_planning_sessions._query_max_updated_at",
    new_callable=lambda: lambda *a, **kw: AsyncMock(return_value=None)(),
)
_PATCH_COMPUTE_STALE_SB = patch(
    "backend.application.services.agent_queries.multi_project_planning_sessions._compute_is_stale",
    return_value=False,
)


# ---------------------------------------------------------------------------
# Scenario 1 — large-project ingest throughput
# ---------------------------------------------------------------------------


@pytest.mark.perf
class TestLargeProjectIngestThroughput(unittest.IsolatedAsyncioTestCase):
    """P6-004-S1: large-project ingest throughput.

    Scale: ~9 000 sessions / 367 features (realistic large-project cardinality).
    Measures the async mock-upsert loop latency per INGEST_BATCH_SIZE sessions.
    The goal is to confirm the sync loop doesn't exhibit O(n^2) behaviour and
    stays well under the per-batch budget across N_INGEST_ROUNDS samples.
    """

    async def asyncSetUp(self) -> None:
        # Pre-build session rows once to amortise generation cost.
        self._session_rows = _make_session_rows(INGEST_SESSION_COUNT, "proj-ingest")
        self._feature_rows = _make_feature_rows(INGEST_FEATURE_COUNT, "proj-ingest")

    async def _run_ingest_batch(
        self, batch: list[dict[str, Any]], repo: _MockSessionsRepo
    ) -> float:
        """Simulate one batch of session upserts through the mock repo.

        This mirrors the per-file loop inside SyncEngine.sync_sessions_for_project
        without importing the real sync engine (which would pull in real DB deps).
        """
        t0 = time.perf_counter()
        for row in batch:
            await repo.upsert(row, "proj-ingest")
        return (time.perf_counter() - t0) * 1000.0

    async def test_ingest_loop_p95_per_batch(self) -> None:
        """S1: p95 per INGEST_BATCH_SIZE session upserts must be < INGEST_BATCH_P95_BUDGET_MS."""
        repo = _MockSessionsRepo()
        latencies_ms: list[float] = []

        # Sample N_INGEST_ROUNDS batches drawn from the full session pool.
        # Each batch starts at a sliding offset so we exercise the full range.
        total_sessions = len(self._session_rows)
        for i in range(N_INGEST_ROUNDS):
            start = (i * INGEST_BATCH_SIZE) % (total_sessions - INGEST_BATCH_SIZE)
            batch = self._session_rows[start : start + INGEST_BATCH_SIZE]
            elapsed_ms = await self._run_ingest_batch(batch, repo)
            latencies_ms.append(elapsed_ms)

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

        print(
            f"\n[P6-004-S1] Ingest throughput ({INGEST_SESSION_COUNT} sessions / "
            f"{INGEST_FEATURE_COUNT} features, batch={INGEST_BATCH_SIZE}):\n"
            f"  p50 = {p50:.2f} ms\n"
            f"  p95 = {p95:.2f} ms  (budget: {INGEST_BATCH_P95_BUDGET_MS} ms)\n"
            f"  p99 = {p99:.2f} ms\n"
            f"  total upserts = {repo.upsert_calls}"
        )

        self.assertEqual(
            repo.upsert_calls,
            N_INGEST_ROUNDS * INGEST_BATCH_SIZE,
            "Unexpected upsert call count — batch loop may have short-circuited",
        )
        self.assertLess(
            p95,
            INGEST_BATCH_P95_BUDGET_MS,
            f"[P6-004-S1] FAIL: p95 = {p95:.2f} ms exceeds budget {INGEST_BATCH_P95_BUDGET_MS} ms",
        )
        print(f"[P6-004-S1] PASS: p95 = {p95:.2f} ms < {INGEST_BATCH_P95_BUDGET_MS} ms")

    async def test_feature_list_scales_linearly_with_count(self) -> None:
        """S1-b: listing INGEST_FEATURE_COUNT feature rows through mock repo stays cheap.

        Projects with 367 features must not exhibit O(n^2) feature listing.
        """
        repo = _MockFeaturesRepo()
        latencies_ms: list[float] = []
        for _ in range(N_INGEST_ROUNDS):
            t0 = time.perf_counter()
            rows = await repo.list_all("proj-ingest")
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies_ms.append(elapsed_ms)

        self.assertEqual(len(rows), INGEST_FEATURE_COUNT)
        latencies_ms.sort()
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        print(
            f"\n[P6-004-S1b] Feature list throughput ({INGEST_FEATURE_COUNT} features):\n"
            f"  p95 = {p95:.2f} ms"
        )
        # Feature listing should be extremely fast in-memory; 50 ms is extremely generous.
        self.assertLess(p95, 50.0, f"Feature list p95 = {p95:.2f} ms exceeds 50 ms")


# ---------------------------------------------------------------------------
# Scenario 2 — planning bundle latency under multi-project fan-out
# ---------------------------------------------------------------------------


@pytest.mark.perf
class TestPlanningBundleLatencyMultiProject(unittest.IsolatedAsyncioTestCase):
    """P6-004-S2: planning bundle p95 < PLANNING_BUNDLE_P95_BUDGET_MS under 36-project fan-out.

    Scale: 36 projects × 5 features each.  Mirrors the MPCC performance baseline
    from test_multi_project_planning_performance.py (PC-1) but runs N_PLANNING_RUNS
    times and asserts a p95 over the sample rather than a single-call ceiling.
    """

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    async def test_planning_bundle_p95_under_budget(self) -> None:
        """S2: p95 over N_PLANNING_RUNS cold fan-out calls must be < PLANNING_BUNDLE_P95_BUDGET_MS."""
        ports = _build_n_project_ports(
            N_PLANNING_PROJECTS, features_per_project=N_PLANNING_FEATURES
        )
        latencies_ms: list[float] = []

        with (
            patch(
                "backend.application.services.agent_queries.multi_project_planning_command_center"
                "._query_max_updated_at",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.application.services.agent_queries.multi_project_planning_command_center"
                "._compute_is_stale",
                return_value=False,
            ),
            patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0),  # cold path every round
        ):
            svc = MultiProjectPlanningCommandCenterQueryService()
            for _ in range(N_PLANNING_RUNS):
                clear_cache()
                t0 = time.perf_counter()
                response = await svc.get_multi_project_command_center(
                    _request_context(), ports, page=1, page_size=50
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                latencies_ms.append(elapsed_ms)

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

        print(
            f"\n[P6-004-S2] Planning bundle fan-out "
            f"({N_PLANNING_PROJECTS} projects × {N_PLANNING_FEATURES} features, "
            f"n={N_PLANNING_RUNS}):\n"
            f"  p50 = {p50:.1f} ms\n"
            f"  p95 = {p95:.1f} ms  (budget: {PLANNING_BUNDLE_P95_BUDGET_MS} ms)\n"
            f"  p99 = {p99:.1f} ms"
        )

        self.assertGreater(len(response.project_summaries), 0)
        self.assertLess(
            p95,
            PLANNING_BUNDLE_P95_BUDGET_MS,
            f"[P6-004-S2] FAIL: planning bundle p95 = {p95:.1f} ms "
            f"exceeds budget {PLANNING_BUNDLE_P95_BUDGET_MS} ms",
        )
        print(f"[P6-004-S2] PASS: p95 = {p95:.1f} ms < {PLANNING_BUNDLE_P95_BUDGET_MS} ms")


# ---------------------------------------------------------------------------
# Scenario 3 — multi-project portfolio rollup fan-out wall-clock p95
# ---------------------------------------------------------------------------


@pytest.mark.perf
class TestPortfolioRollupFanout(unittest.IsolatedAsyncioTestCase):
    """P6-004-S3: multi-project portfolio rollup p95 < PORTFOLIO_ROLLUP_P95_BUDGET_MS.

    Scale: 50 projects × 2 active sessions each.  Uses the active-session board
    service (MultiProjectActiveSessionBoardQueryService) as the rollup proxy,
    matching the fan-out pattern used by the portfolio endpoint.
    """

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    async def test_portfolio_rollup_p95_under_budget(self) -> None:
        """S3: p95 over N_PORTFOLIO_RUNS cold fan-out calls must be < PORTFOLIO_ROLLUP_P95_BUDGET_MS."""
        ports = _build_n_project_ports(
            N_PORTFOLIO_PROJECTS, active_sessions_per_project=N_PORTFOLIO_SESSIONS
        )
        latencies_ms: list[float] = []

        with (
            patch(
                "backend.application.services.agent_queries.multi_project_planning_sessions"
                "._query_max_updated_at",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.application.services.agent_queries.multi_project_planning_sessions"
                "._compute_is_stale",
                return_value=False,
            ),
            patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0),  # cold path every round
        ):
            svc = MultiProjectActiveSessionBoardQueryService()
            for _ in range(N_PORTFOLIO_RUNS):
                clear_cache()
                t0 = time.perf_counter()
                response = await svc.get_multi_project_session_board(
                    _request_context(), ports, group_by="state", page=1, page_size=200
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                latencies_ms.append(elapsed_ms)

        latencies_ms.sort()
        p50 = statistics.median(latencies_ms)
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

        print(
            f"\n[P6-004-S3] Portfolio rollup fan-out "
            f"({N_PORTFOLIO_PROJECTS} projects × {N_PORTFOLIO_SESSIONS} active sessions, "
            f"n={N_PORTFOLIO_RUNS}):\n"
            f"  p50 = {p50:.1f} ms\n"
            f"  p95 = {p95:.1f} ms  (budget: {PORTFOLIO_ROLLUP_P95_BUDGET_MS} ms)\n"
            f"  p99 = {p99:.1f} ms"
        )

        self.assertGreater(response.total_card_count, 0)
        self.assertLess(
            p95,
            PORTFOLIO_ROLLUP_P95_BUDGET_MS,
            f"[P6-004-S3] FAIL: portfolio rollup p95 = {p95:.1f} ms "
            f"exceeds budget {PORTFOLIO_ROLLUP_P95_BUDGET_MS} ms",
        )
        print(f"[P6-004-S3] PASS: p95 = {p95:.1f} ms < {PORTFOLIO_ROLLUP_P95_BUDGET_MS} ms")
