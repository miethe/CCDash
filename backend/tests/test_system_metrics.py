"""Tests for system-wide metrics (T4-001, T4-002, T4-004).

Covers:
  T4-001  Unit tests on SystemMetricsQueryService
  T4-002  Integration + performance tests
  T4-004  R-P3 seam parity (dashboard contract)

Test structure follows the project's IsolatedAsyncioTestCase + aiosqlite
in-memory DB pattern established in test_agent_queries_integration.py and
test_feature_surface_benchmarks.py.

Performance budget policy (mirrors test_feature_surface_benchmarks.py):
  - Tests always print timing.
  - Tests fail only when elapsed > budget (hard limit).
  - CCDASH_RUN_PERF_TESTS env var gates the 36-project raw-latency test on CI.
"""
from __future__ import annotations

import os
import time
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend import config
from backend.application.context import (
    Principal,
    ProjectScope,
    RequestContext,
    TraceContext,
)
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.cache import clear_cache
from backend.application.services.agent_queries.system_metrics import (
    SystemMetricsQueryService,
    _compute_is_stale,
    _fetch_project_summary,
)
from backend.db.sqlite_migrations import run_migrations
from backend.models import ProjectActiveCountSummaryDTO, SystemActiveCountDTO
from backend.runtime_ports import build_core_ports


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


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


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    """Minimal workspace registry for unit tests."""

    def __init__(self, projects: list[Any]) -> None:
        self._projects = projects
        self._active = projects[0] if projects else None

    def list_projects(self) -> list[Any]:
        return list(self._projects)

    def get_project(self, project_id: str) -> Any | None:
        return next((p for p in self._projects if p.id == project_id), None)

    def get_active_project(self) -> Any | None:
        return self._active

    def resolve_scope(self, project_id: str | None = None) -> tuple[Any, Any]:
        proj = self.get_project(project_id or "") if project_id else self._active
        if proj is None:
            return None, None
        return None, ProjectScope(
            project_id=proj.id,
            project_name=proj.name,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


class _Storage:
    """Minimal storage adapter for unit tests."""

    def __init__(self, *, db: Any, sessions_repo: Any) -> None:
        self.db = db
        self._sessions_repo = sessions_repo

    def sessions(self) -> Any:
        return self._sessions_repo


def _make_project(project_id: str, name: str | None = None) -> types.SimpleNamespace:
    return types.SimpleNamespace(id=project_id, name=name or project_id)


def _make_ports(
    *,
    projects: list[Any],
    db: Any,
    sessions_repo: Any,
) -> CorePorts:
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(projects),
        storage=_Storage(db=db, sessions_repo=sessions_repo),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


async def _insert_session(
    db: aiosqlite.Connection,
    *,
    session_id: str,
    project_id: str,
    status: str = "active",
    updated_at: str,
) -> None:
    """Insert a minimal sessions row used by count_active + _query_max_updated_at."""
    await db.execute(
        """
        INSERT OR REPLACE INTO sessions
            (id, project_id, status, updated_at, created_at, source_file)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, project_id, status, updated_at, updated_at, f"{session_id}.jsonl"),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# T4-001  Unit tests on the service
# ---------------------------------------------------------------------------

class TestStalenessHorizonBoundary(unittest.IsolatedAsyncioTestCase):
    """T4-001-a: stale / boundary / fresh staleness semantics."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        horizon = config.CCDASH_SYSTEM_METRICS_STALE_HORIZON_SECONDS
        now = _now_utc()

        self.proj_fresh = _make_project("proj-fresh")
        self.proj_boundary = _make_project("proj-boundary")
        self.proj_stale = _make_project("proj-stale")

        ts_fresh = now.strftime("%Y-%m-%dT%H:%M:%S")
        ts_boundary = (now - timedelta(seconds=horizon - 1)).strftime("%Y-%m-%dT%H:%M:%S")
        ts_stale = (now - timedelta(seconds=horizon + 60)).strftime("%Y-%m-%dT%H:%M:%S")

        await _insert_session(self.db, session_id="s-fresh", project_id="proj-fresh", updated_at=ts_fresh)
        await _insert_session(self.db, session_id="s-boundary", project_id="proj-boundary", updated_at=ts_boundary)
        await _insert_session(self.db, session_id="s-stale", project_id="proj-stale", status="completed", updated_at=ts_stale)

        # Build ports with a real sessions repo
        real_ports = build_core_ports(
            self.db,
            workspace_registry=_WorkspaceRegistry([self.proj_fresh, self.proj_boundary, self.proj_stale]),
        )
        self.sessions_repo = real_ports.storage.sessions()
        self.ports = real_ports

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    async def test_stale_horizon_boundary(self) -> None:
        """Fresh, boundary, and stale projects return correct is_stale values."""
        # Disable cache so the service makes real DB calls
        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = SystemMetricsQueryService()
            dto = await svc.get_system_active_count(_context("proj-fresh"), self.ports)

        by_id = {p.project_id: p for p in dto.per_project}

        self.assertIn("proj-fresh", by_id)
        self.assertIn("proj-boundary", by_id)
        self.assertIn("proj-stale", by_id)

        self.assertFalse(by_id["proj-fresh"].is_stale, "Fresh project should not be stale")
        self.assertFalse(by_id["proj-boundary"].is_stale, "Boundary project (horizon-1s) should not be stale")
        self.assertTrue(by_id["proj-stale"].is_stale, "Stale project (horizon+60s) should be stale")


class TestPartialAggregateResilience(unittest.IsolatedAsyncioTestCase):
    """T4-001-b: one erroring project → partial status, others intact."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        now = _now_utc().strftime("%Y-%m-%dT%H:%M:%S")
        await _insert_session(self.db, session_id="s1", project_id="proj-ok-1", updated_at=now)
        await _insert_session(self.db, session_id="s2", project_id="proj-ok-2", updated_at=now)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    async def test_partial_aggregate_resilience(self) -> None:
        proj_ok1 = _make_project("proj-ok-1")
        proj_err = _make_project("proj-error")
        proj_ok2 = _make_project("proj-ok-2")

        real_ports = build_core_ports(
            self.db,
            workspace_registry=_WorkspaceRegistry([proj_ok1, proj_err, proj_ok2]),
        )
        real_sessions_repo = real_ports.storage.sessions()

        # Wrap count_active to raise for the error project
        original_count_active = real_sessions_repo.count_active

        async def patched_count_active(project_id: str, **kwargs: Any) -> int:
            if project_id == "proj-error":
                raise Exception("db down")
            return await original_count_active(project_id, **kwargs)

        real_sessions_repo.count_active = patched_count_active

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = SystemMetricsQueryService()
            dto = await svc.get_system_active_count(_context(), real_ports)

        self.assertEqual(dto.status, "partial")
        by_id = {p.project_id: p for p in dto.per_project}

        # Erroring project has null count + error string
        err_proj = by_id["proj-error"]
        self.assertIsNone(err_proj.count)
        self.assertIsNone(err_proj.is_stale)
        self.assertIsNotNone(err_proj.error)
        self.assertIn("db down", err_proj.error)

        # OK projects have valid counts
        self.assertIsNotNone(by_id["proj-ok-1"].count)
        self.assertIsNone(by_id["proj-ok-1"].error)
        self.assertIsNotNone(by_id["proj-ok-2"].count)
        self.assertIsNone(by_id["proj-ok-2"].error)

        # Total excludes erroring project
        expected_total = (by_id["proj-ok-1"].count or 0) + (by_id["proj-ok-2"].count or 0)
        self.assertEqual(dto.total, expected_total)


class TestCacheHit(unittest.IsolatedAsyncioTestCase):
    """T4-001-c: second call within TTL reuses cached result."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    async def test_cache_hit(self) -> None:
        proj = _make_project("proj-cache")
        ports = build_core_ports(
            self.db,
            workspace_registry=_WorkspaceRegistry([proj]),
        )
        sessions_repo = ports.storage.sessions()

        # Track call count
        call_count = 0
        original = sessions_repo.count_active

        async def counting_count_active(project_id: str, **kwargs: Any) -> int:
            nonlocal call_count
            call_count += 1
            return await original(project_id, **kwargs)

        sessions_repo.count_active = counting_count_active

        # Ensure TTL > 0 so cache is active
        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 60):
            svc = SystemMetricsQueryService()
            dto1 = await svc.get_system_active_count(_context(), ports)
            calls_after_first = call_count

            dto2 = await svc.get_system_active_count(_context(), ports)
            calls_after_second = call_count

        # The second call must not make additional DB calls
        self.assertEqual(
            calls_after_second,
            calls_after_first,
            "Second call within TTL should hit cache, not re-query DB",
        )
        # Both calls return the same DTO (same generated_at is the cache signal)
        self.assertEqual(dto1.generated_at, dto2.generated_at)


class TestAllErrorsReturnsPartialStatus(unittest.IsolatedAsyncioTestCase):
    """T4-001-d: all projects error → status=partial, total=0."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    async def test_all_errors_returns_partial_status(self) -> None:
        projects = [_make_project(f"proj-{i}") for i in range(3)]
        ports = build_core_ports(
            self.db,
            workspace_registry=_WorkspaceRegistry(projects),
        )
        sessions_repo = ports.storage.sessions()

        async def always_fails(project_id: str, **kwargs: Any) -> int:
            raise Exception(f"fatal error for {project_id}")

        sessions_repo.count_active = always_fails

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = SystemMetricsQueryService()
            dto = await svc.get_system_active_count(_context(), ports)

        self.assertEqual(dto.status, "partial")
        self.assertEqual(dto.total, 0)
        for p in dto.per_project:
            self.assertIsNotNone(p.error, f"Project {p.project_id} should have an error")


# ---------------------------------------------------------------------------
# T4-002  Integration + performance tests
# ---------------------------------------------------------------------------

class TestSystemMetricsTransportParity(unittest.IsolatedAsyncioTestCase):
    """T4-002-a: service DTO == HTTP JSON response (structural parity)."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        now = _now_utc()
        horizon = config.CCDASH_SYSTEM_METRICS_STALE_HORIZON_SECONDS

        # Seed 5 projects: 4 fresh, 1 stale
        self.projects = [_make_project(f"proj-{i}", f"Project {i}") for i in range(5)]
        for i, proj in enumerate(self.projects):
            if i < 4:
                ts = now.strftime("%Y-%m-%dT%H:%M:%S")
            else:
                ts = (now - timedelta(seconds=horizon + 120)).strftime("%Y-%m-%dT%H:%M:%S")
            await _insert_session(
                self.db,
                session_id=f"s-{i}",
                project_id=proj.id,
                status="active",
                updated_at=ts,
            )

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    async def test_system_metrics_transport_parity(self) -> None:
        from fastapi import Response
        from unittest.mock import MagicMock

        from backend.routers import agent as agent_router
        from backend.application.ports import CorePorts

        ports = build_core_ports(
            self.db,
            workspace_registry=_WorkspaceRegistry(self.projects),
        )

        # Call service directly
        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = SystemMetricsQueryService()
            service_dto = await svc.get_system_active_count(_context(), ports)

        # Reset cache then call via router handler (mimics HTTP path)
        clear_cache()

        app_request = types.SimpleNamespace(context=_context(), ports=ports)
        mock_response = MagicMock(spec=Response)
        mock_response.headers = {}

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            with patch.object(
                agent_router,
                "_resolve_app_request",
                new=AsyncMock(return_value=app_request),
            ):
                router_dto = await agent_router.get_system_active_count(
                    response=mock_response,
                    request_context=object(),
                    core_ports=object(),
                )

        # Structural equality (ignoring generated_at since two separate calls)
        self.assertEqual(service_dto.total, router_dto.total)
        self.assertEqual(service_dto.status, router_dto.status)
        self.assertEqual(service_dto.window_seconds, router_dto.window_seconds)
        self.assertEqual(len(service_dto.per_project), len(router_dto.per_project))

        svc_by_id = {p.project_id: p for p in service_dto.per_project}
        rtr_by_id = {p.project_id: p for p in router_dto.per_project}
        for proj_id in svc_by_id:
            self.assertIn(proj_id, rtr_by_id)
            self.assertEqual(svc_by_id[proj_id].count, rtr_by_id[proj_id].count)
            self.assertEqual(svc_by_id[proj_id].is_stale, rtr_by_id[proj_id].is_stale)


@unittest.skipUnless(
    os.environ.get("CCDASH_RUN_PERF_TESTS"),
    "Set CCDASH_RUN_PERF_TESTS=1 to run latency assertions against 36 projects",
)
class TestSystemMetricsPerformance(unittest.IsolatedAsyncioTestCase):
    """T4-002-b: p95 latency < 200 ms over 36 projects, cache disabled."""

    _PROJECT_COUNT = 36
    _SAMPLE_COUNT = 10
    _P95_BUDGET_MS = 200.0

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        # WAL mode for parallel read performance
        await self.db.execute("PRAGMA journal_mode=WAL")

        now = _now_utc().strftime("%Y-%m-%dT%H:%M:%S")
        self.projects = [_make_project(f"perf-proj-{i}") for i in range(self._PROJECT_COUNT)]
        for i, proj in enumerate(self.projects):
            await _insert_session(
                self.db,
                session_id=f"perf-s-{i}",
                project_id=proj.id,
                updated_at=now,
            )

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    async def test_system_metrics_performance(self) -> None:
        ports = build_core_ports(
            self.db,
            workspace_registry=_WorkspaceRegistry(self.projects),
        )

        latencies_ms: list[float] = []
        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = SystemMetricsQueryService()
            for _ in range(self._SAMPLE_COUNT):
                t0 = time.monotonic()
                await svc.get_system_active_count(_context(), ports)
                latencies_ms.append((time.monotonic() - t0) * 1000)

        latencies_ms.sort()
        p95_idx = int(len(latencies_ms) * 0.95) - 1
        p95 = latencies_ms[max(0, p95_idx)]

        print(
            f"\nPERF [system_metrics/{self._PROJECT_COUNT}p x{self._SAMPLE_COUNT}] "
            f"p95={p95:.1f}ms  budget={self._P95_BUDGET_MS:.0f}ms  "
            f"min={latencies_ms[0]:.1f}ms  max={latencies_ms[-1]:.1f}ms"
        )
        self.assertLess(
            p95,
            self._P95_BUDGET_MS,
            f"p95 {p95:.1f}ms exceeds budget {self._P95_BUDGET_MS:.0f}ms",
        )


class TestSystemMetricsPerformanceCached(unittest.IsolatedAsyncioTestCase):
    """T4-002-c: second cached call completes in < 20 ms."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        now = _now_utc().strftime("%Y-%m-%dT%H:%M:%S")
        self.proj = _make_project("cache-proj")
        await _insert_session(self.db, session_id="cs1", project_id="cache-proj", updated_at=now)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    async def test_system_metrics_performance_cached(self) -> None:
        ports = build_core_ports(
            self.db,
            workspace_registry=_WorkspaceRegistry([self.proj]),
        )

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 60):
            svc = SystemMetricsQueryService()
            # First call — populates cache
            await svc.get_system_active_count(_context(), ports)

            # Second call — must be served from cache
            t0 = time.monotonic()
            await svc.get_system_active_count(_context(), ports)
            elapsed_ms = (time.monotonic() - t0) * 1000

        print(f"\nPERF [system_metrics_cached] elapsed={elapsed_ms:.2f}ms  budget=20ms")
        self.assertLess(
            elapsed_ms,
            20.0,
            f"Cached call took {elapsed_ms:.2f}ms, expected < 20ms",
        )


# ---------------------------------------------------------------------------
# T4-004  R-P3 seam parity: dashboard contract key presence
# ---------------------------------------------------------------------------

class TestDashboardContractParity(unittest.IsolatedAsyncioTestCase):
    """T4-004: GET /api/agent/system/active-count response satisfies SystemMetricsChip contract.

    Asserts key presence + type (not value equality), per the spec.
    Required top-level keys: total, per_project, generated_at, window_seconds, status
    Required per-project keys: project_id, project_name, count, is_stale, last_synced_at
    """

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        now = _now_utc().strftime("%Y-%m-%dT%H:%M:%S")
        self.projects = [_make_project("parity-1", "Parity One"), _make_project("parity-2", "Parity Two")]
        await _insert_session(self.db, session_id="par-s1", project_id="parity-1", updated_at=now)
        await _insert_session(self.db, session_id="par-s2", project_id="parity-2", updated_at=now)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    async def test_dashboard_contract_parity(self) -> None:
        from fastapi import Response
        from unittest.mock import MagicMock

        from backend.routers import agent as agent_router

        ports = build_core_ports(
            self.db,
            workspace_registry=_WorkspaceRegistry(self.projects),
        )
        app_request = types.SimpleNamespace(context=_context(), ports=ports)
        mock_response = MagicMock(spec=Response)
        mock_response.headers = {}

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            with patch.object(
                agent_router,
                "_resolve_app_request",
                new=AsyncMock(return_value=app_request),
            ):
                dto = await agent_router.get_system_active_count(
                    response=mock_response,
                    request_context=object(),
                    core_ports=object(),
                )

        # Serialize to dict via model_dump for key-presence inspection
        payload = dto.model_dump()

        # ── Top-level keys ───────────────────────────────────────────────
        required_top_level = {"total", "per_project", "generated_at", "window_seconds", "status"}
        for key in required_top_level:
            self.assertIn(key, payload, f"Top-level key '{key}' missing from response")

        self.assertIsInstance(payload["total"], int)
        self.assertIsInstance(payload["per_project"], list)
        self.assertIsInstance(payload["window_seconds"], int)
        self.assertIn(payload["status"], ("ok", "partial"))

        # ── Per-project keys ─────────────────────────────────────────────
        required_per_project = {"project_id", "project_name", "count", "is_stale", "last_synced_at"}
        self.assertGreaterEqual(len(payload["per_project"]), 2, "Expected at least 2 per-project entries")
        for entry in payload["per_project"]:
            for key in required_per_project:
                self.assertIn(
                    key,
                    entry,
                    f"Per-project key '{key}' missing from entry {entry.get('project_id', '?')}",
                )
            # Values may be None (null in JSON) — presence is what matters
            self.assertIsInstance(entry["project_id"], str)
            self.assertIsInstance(entry["project_name"], str)


if __name__ == "__main__":
    unittest.main()
