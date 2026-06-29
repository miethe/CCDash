"""Regression tests for Bug A: system_active_count cache key scoping and type safety.

Two guards verified:
1. The cache key for get_system_active_count is always globally scoped (project_id
   forced to "" → scope "global"), regardless of which project is active in the
   request context.  Without this fix the decorator auto-derived project_id from
   context.project.project_id, scoping the key per-project instead of globally.

2. The public get_system_active_count wrapper validates that the cached value is a
   SystemActiveCountDTO.  If the cache ever returns a foreign type (e.g. a
   PaginatedResponse[Feature] from a cross-cache contamination), the wrapper discards
   the hit and re-executes with bypass_cache=True so the cache is repaired in place.

Run with:
    backend/.venv/bin/python -m pytest backend/tests/test_system_metrics_cache_regression.py -v
"""
from __future__ import annotations

import time
import types
import unittest
from datetime import datetime, timezone
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
from backend.application.services.agent_queries.cache import (
    clear_cache,
    compute_cache_key,
    get_cache,
)
from backend.application.services.agent_queries.system_metrics import (
    SystemMetricsQueryService,
)
from backend.db.sqlite_migrations import run_migrations
from backend.models import Feature, PaginatedResponse, SystemActiveCountDTO
from backend.runtime_ports import build_core_ports


# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_system_metrics.py conventions)
# ---------------------------------------------------------------------------


def _context(project_id: str = "project-A") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name=f"Project {project_id}",
            root_path=Path("/tmp/test"),
            sessions_dir=Path("/tmp/test/sessions"),
            docs_dir=Path("/tmp/test/docs"),
            progress_dir=Path("/tmp/test/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-reg-1"),
    )


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
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
        _ = project_id
        return None, None


class _Storage:
    def __init__(self, *, db: Any, sessions_repo: Any) -> None:
        self.db = db
        self._sessions_repo = sessions_repo

    def sessions(self) -> Any:
        return self._sessions_repo


def _make_project(project_id: str, name: str | None = None) -> types.SimpleNamespace:
    return types.SimpleNamespace(id=project_id, name=name or project_id)


def _make_ports(*, projects: list[Any], db: Any, sessions_repo: Any) -> CorePorts:
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(projects),
        storage=_Storage(db=db, sessions_repo=sessions_repo),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


# ---------------------------------------------------------------------------
# Regression: global cache-key scope fix
# ---------------------------------------------------------------------------


class TestSystemActiveCountCacheKeyScope(unittest.IsolatedAsyncioTestCase):
    """Verify that get_system_active_count always uses the global cache scope."""

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.proj = _make_project("proj-X")
        real_ports = build_core_ports(
            self.db,
            workspace_registry=_WorkspaceRegistry([self.proj]),
        )
        self.sessions_repo = real_ports.storage.sessions()
        self.ports = real_ports

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    async def test_returns_system_active_count_dto_with_cache_disabled(self) -> None:
        """Service returns SystemActiveCountDTO (basic type sanity, cache bypassed)."""
        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = SystemMetricsQueryService()
            result = await svc.get_system_active_count(_context("proj-X"), self.ports)
        self.assertIsInstance(
            result,
            SystemActiveCountDTO,
            f"Expected SystemActiveCountDTO but got {type(result).__name__}",
        )

    async def test_global_scope_same_key_for_different_contexts(self) -> None:
        """Two contexts with different project_ids share the same global cache entry.

        Before the fix, project_id was auto-derived from context.project.project_id,
        producing a per-project key.  After the fix, project_id is forced to ""
        (→ scope "global"), so both contexts hit the same key.
        """
        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 60):
            with patch.object(config, "CCDASH_FINGERPRINT_CACHE_TTL_SECONDS", 0):
                svc = SystemMetricsQueryService()

                ctx_a = _context("proj-A")
                ctx_b = _context("proj-B")

                result_a = await svc.get_system_active_count(ctx_a, self.ports)
                # With global scope, result_b should come from cache (same key)
                result_b = await svc.get_system_active_count(ctx_b, self.ports)

        # Both results should be SystemActiveCountDTO
        self.assertIsInstance(result_a, SystemActiveCountDTO)
        self.assertIsInstance(result_b, SystemActiveCountDTO)

        # Under global scope, both calls use the same cache key so the in-process
        # cache returns the same object for the second call.
        self.assertIs(
            result_a,
            result_b,
            "Expected cache hit (same global scope object) for different project "
            "contexts — the cache key must not be scoped per-project for this endpoint.",
        )


# ---------------------------------------------------------------------------
# Regression: type-safety guard against cache contamination
# ---------------------------------------------------------------------------


class TestSystemActiveCountCacheContaminationGuard(unittest.IsolatedAsyncioTestCase):
    """Verify that get_system_active_count rejects foreign types from the cache.

    Simulates the production failure where the cache returns a PaginatedResponse[Feature]
    instead of SystemActiveCountDTO.  The public wrapper must detect the type mismatch,
    discard the cache hit, and return a freshly computed SystemActiveCountDTO.
    """

    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.proj = _make_project("proj-contam")
        real_ports = build_core_ports(
            self.db,
            workspace_registry=_WorkspaceRegistry([self.proj]),
        )
        self.ports = real_ports

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    async def test_type_guard_rejects_cached_feature_list(self) -> None:
        """Cache hit returning PaginatedResponse[Feature] triggers fallback to fresh query."""
        contaminating_value = PaginatedResponse(
            items=[Feature(id="add-collection-creation-buttons-v1", name="Add buttons")],
            total=1,
            offset=0,
            limit=200,
        )

        # Patch _backend_get so the first cache-read returns the contaminating value
        # (simulating cache cross-contamination).  The bypass_cache=True retry call
        # skips _backend_get entirely and executes the real function.
        with patch(
            "backend.application.services.agent_queries.cache._backend_get",
            new_callable=AsyncMock,
            return_value=contaminating_value,
        ):
            with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 60):
                svc = SystemMetricsQueryService()
                result = await svc.get_system_active_count(
                    _context("proj-contam"), self.ports
                )

        self.assertIsInstance(
            result,
            SystemActiveCountDTO,
            f"Type guard must recover from cache contamination; got {type(result).__name__}",
        )
        # Sanity: the recovered result must have the expected DTO shape
        self.assertIsNotNone(result.total)
        self.assertIsNotNone(result.generated_at)
        self.assertIn(result.status, ("ok", "partial"))


if __name__ == "__main__":
    unittest.main()
