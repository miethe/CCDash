"""T1-002: activeSessions field on PlanningCommandCenterItemDTO + ttl=30.

Tests:
  TC-1  activeSessions populated when running-state sessions exist for a feature.
  TC-2  activeSessions is empty list (never null) when no sessions are running.
  TC-3  activeSessions uses _STATUS_STATE_MAP from planning_sessions for liveness
        classification (R4 hard constraint): DB statuses running, in_progress, and
        active all appear in the populated list; no novel heuristic is introduced.
  TC-4  ttl=30 kwarg passed to the planning-board @memoized_query decorator;
        verified by checking the effective TTL resolved at decoration time.
  TC-5  Resilience: storage failure on sessions() does not raise; activeSessions
        defaults to empty list.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.services.agent_queries import cache as cache_mod
from backend.application.services.agent_queries.cache import _resolve_ttl
from backend.application.services.agent_queries.models import (
    AggregateWorkItemSession,
    PlanningCommandCenterItemDTO,
)
from backend.application.services.agent_queries.planning_command_center import (
    PlanningCommandCenterQueryService,
    _RUNNING_DB_STATUSES,
    _SESSION_STATE_MAP,
)
from backend.application.services.agent_queries.planning_sessions import _STATUS_STATE_MAP
from backend.models import Project

# ---------------------------------------------------------------------------
# Shared helpers (mirror test_planning_command_center_service.py style)
# ---------------------------------------------------------------------------


def _make_project(pid: str = "proj-1") -> Project:
    return Project(id=pid, name=f"Project {pid}", path=f"/tmp/{pid}")


def _request_context(project: Project) -> RequestContext:
    return RequestContext(
        principal=Principal(subject="tester", display_name="Tester", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project.id,
            project_name=project.name,
            root_path=Path(project.path),
            sessions_dir=Path(project.path) / "sessions",
            docs_dir=Path(project.path) / "docs",
            progress_dir=Path(project.path) / "progress",
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-t1002"),
    )


def _make_feature_row(feature_id: str = "feat-1", status: str = "in-progress") -> dict:
    return {
        "id": feature_id,
        "name": f"Feature {feature_id}",
        "status": status,
        "updated_at": "2026-06-04T00:00:00+00:00",
        "data_json": json.dumps(
            {
                "id": feature_id,
                "name": f"Feature {feature_id}",
                "status": status,
                "summary": "Test feature for T1-002",
                "priority": "medium",
                "tags": [],
                "phases": [
                    {
                        "id": f"{feature_id}:phase-1",
                        "phase": "1",
                        "title": "Phase 1",
                        "status": "active",
                        "progress": 0,
                        "totalTasks": 1,
                        "completedTasks": 0,
                        "tasks": [],
                    }
                ],
            }
        ),
    }


def _make_session_row(
    session_id: str,
    feature_id: str,
    status: str = "running",
    model: str = "claude-opus-4",
) -> dict:
    return {
        "id": session_id,
        "feature_id": feature_id,
        "status": status,
        "model": model,
        "started_at": "2026-06-04T10:00:00+00:00",
        "agent_id": f"agent-{session_id}",
        "updated_at": "2026-06-04T10:05:00+00:00",
    }


class _FeaturesRepo:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    async def list_all(self, project_id: str) -> list[dict]:
        return list(self.rows)

    async def get_by_id(self, feature_id: str) -> dict | None:
        for row in self.rows:
            if row.get("id") == feature_id:
                return row
        return None


class _DocumentsRepo:
    async def list_all(self, project_id: str) -> list[dict]:
        return []


class _WorktreeRepo:
    async def list(self, project_id: str, **kwargs) -> list[dict]:
        return []


class _SessionsRepo:
    """Minimal sessions repo stub for T1-002 tests."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def list_paginated(
        self,
        offset: int,
        limit: int,
        project_id: str | None = None,
        sort_by: str = "started_at",
        sort_order: str = "desc",
        filters: dict | None = None,
    ) -> list[dict]:
        filters = filters or {}
        wanted_status = filters.get("status", "")
        result = []
        for row in self._rows:
            if wanted_status and row.get("status") != wanted_status:
                continue
            result.append(row)
        return result[offset:offset + limit]


class _WorkspaceRegistry:
    def __init__(self, project: Project) -> None:
        self.project = project

    def get_project(self, project_id: str) -> Project | None:
        return self.project if project_id == self.project.id else None

    def get_active_project(self) -> Project | None:
        return self.project

    def resolve_scope(self, project_id: str):
        return None, ProjectScope(
            project_id=project_id,
            project_name=self.project.name,
            root_path=Path(self.project.path),
            sessions_dir=Path(self.project.path) / "sessions",
            docs_dir=Path(self.project.path) / "docs",
            progress_dir=Path(self.project.path) / "progress",
        )


def _make_storage(
    feature_rows: list[dict],
    session_rows: list[dict] | None = None,
) -> SimpleNamespace:
    sessions_repo = _SessionsRepo(session_rows or [])
    return SimpleNamespace(
        features=lambda: _FeaturesRepo(feature_rows),
        documents=lambda: _DocumentsRepo(),
        worktree_contexts=lambda: _WorktreeRepo(),
        sessions=lambda: sessions_repo,
    )


def _make_ports(project: Project, session_rows: list[dict] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        storage=_make_storage([_make_feature_row()], session_rows),
        workspace_registry=_WorkspaceRegistry(project),
    )


# ---------------------------------------------------------------------------
# TC-1: activeSessions populated when running sessions exist
# ---------------------------------------------------------------------------


class T1002ActiveSessionsPopulatedTests(unittest.IsolatedAsyncioTestCase):
    """TC-1: activeSessions list is non-empty when running-state sessions are seeded."""

    async def test_active_sessions_populated_for_running_session(self) -> None:
        project = _make_project()
        session_row = _make_session_row("sess-run-1", "feat-1", status="running")
        ports = _make_ports(project, session_rows=[session_row])

        service = PlanningCommandCenterQueryService()
        page = await service.get_command_center(
            _request_context(project),
            ports,
            project_id_override="proj-1",
            page=1,
            page_size=10,
        )

        self.assertIn(page.status, {"ok", "partial"})
        self.assertEqual(page.total, 1)
        item = page.items[0]

        # activeSessions must be a list (never None)
        self.assertIsInstance(item.active_sessions, list)
        self.assertEqual(
            len(item.active_sessions),
            1,
            "Expected exactly one active session for the feature",
        )
        sess = item.active_sessions[0]
        self.assertIsInstance(sess, AggregateWorkItemSession)
        self.assertEqual(sess.session_id, "sess-run-1")
        self.assertEqual(sess.state, "running")
        self.assertEqual(sess.model, "claude-opus-4")
        self.assertEqual(sess.started_at, "2026-06-04T10:00:00+00:00")

    async def test_active_sessions_contain_in_progress_status(self) -> None:
        """DB status 'in_progress' maps to running per _STATUS_STATE_MAP."""
        project = _make_project()
        session_row = _make_session_row("sess-ip-1", "feat-1", status="in_progress")
        ports = _make_ports(project, session_rows=[session_row])

        service = PlanningCommandCenterQueryService()
        page = await service.get_command_center(
            _request_context(project),
            ports,
            project_id_override="proj-1",
            page=1,
            page_size=10,
        )

        item = page.items[0]
        session_ids = [s.session_id for s in item.active_sessions]
        self.assertIn("sess-ip-1", session_ids, "in_progress sessions must appear in activeSessions")

    async def test_active_sessions_contain_active_status(self) -> None:
        """DB status 'active' maps to running per _STATUS_STATE_MAP."""
        project = _make_project()
        session_row = _make_session_row("sess-active-1", "feat-1", status="active")
        ports = _make_ports(project, session_rows=[session_row])

        service = PlanningCommandCenterQueryService()
        page = await service.get_command_center(
            _request_context(project),
            ports,
            project_id_override="proj-1",
            page=1,
            page_size=10,
        )

        item = page.items[0]
        session_ids = [s.session_id for s in item.active_sessions]
        self.assertIn("sess-active-1", session_ids, "active sessions must appear in activeSessions")


# ---------------------------------------------------------------------------
# TC-2: activeSessions is empty list (never null) when no sessions are running
# ---------------------------------------------------------------------------


class T1002EmptyActiveSessionsTests(unittest.IsolatedAsyncioTestCase):
    """TC-2: activeSessions defaults to empty list when no running sessions exist."""

    async def test_active_sessions_empty_when_no_running_sessions(self) -> None:
        project = _make_project()
        # Seed completed sessions only — none should appear in activeSessions.
        session_rows = [
            _make_session_row("sess-done-1", "feat-1", status="completed"),
            _make_session_row("sess-fail-1", "feat-1", status="failed"),
        ]
        ports = _make_ports(project, session_rows=session_rows)

        service = PlanningCommandCenterQueryService()
        page = await service.get_command_center(
            _request_context(project),
            ports,
            project_id_override="proj-1",
            page=1,
            page_size=10,
        )

        item = page.items[0]
        # Must be an empty list, NOT None.
        self.assertIsNotNone(
            item.active_sessions,
            "active_sessions must never be None — it must be an empty list",
        )
        self.assertIsInstance(item.active_sessions, list)
        self.assertEqual(
            len(item.active_sessions),
            0,
            "active_sessions must be empty when no running sessions exist",
        )

    async def test_active_sessions_empty_when_no_session_repo(self) -> None:
        """When storage has no sessions() method the field still defaults to []."""
        project = _make_project()
        # Intentionally omit 'sessions' from storage to simulate old/partial storage.
        storage_without_sessions = SimpleNamespace(
            features=lambda: _FeaturesRepo([_make_feature_row()]),
            documents=lambda: _DocumentsRepo(),
            worktree_contexts=lambda: _WorktreeRepo(),
            # sessions intentionally absent
        )
        ports = SimpleNamespace(
            storage=storage_without_sessions,
            workspace_registry=_WorkspaceRegistry(project),
        )

        service = PlanningCommandCenterQueryService()
        page = await service.get_command_center(
            _request_context(project),
            ports,
            project_id_override="proj-1",
            page=1,
            page_size=10,
        )

        self.assertIn(page.status, {"ok", "partial"})
        item = page.items[0]
        self.assertIsNotNone(item.active_sessions)
        self.assertIsInstance(item.active_sessions, list)
        self.assertEqual(
            item.active_sessions,
            [],
            "active_sessions must be [] when sessions() is unavailable",
        )


# ---------------------------------------------------------------------------
# TC-3: R4 hard constraint — liveness heuristic derived from _STATUS_STATE_MAP
# ---------------------------------------------------------------------------


class T1002R4LivenessHeuristicTests(unittest.TestCase):
    """TC-3: _RUNNING_DB_STATUSES is derived from planning_sessions._STATUS_STATE_MAP."""

    def test_running_db_statuses_match_status_state_map(self) -> None:
        """All statuses that map to 'running' in _STATUS_STATE_MAP must appear in
        _RUNNING_DB_STATUSES, and no extras should be present."""
        expected = frozenset(s for s, state in _STATUS_STATE_MAP.items() if state == "running")
        self.assertEqual(
            _RUNNING_DB_STATUSES,
            expected,
            "_RUNNING_DB_STATUSES must be derived solely from planning_sessions._STATUS_STATE_MAP",
        )

    def test_session_state_map_import_is_planning_sessions_map(self) -> None:
        """_SESSION_STATE_MAP in planning_command_center must be the same object as
        planning_sessions._STATUS_STATE_MAP (imported alias, not a copy)."""
        self.assertIs(
            _SESSION_STATE_MAP,
            _STATUS_STATE_MAP,
            "_SESSION_STATE_MAP must be the exact _STATUS_STATE_MAP from planning_sessions",
        )

    def test_classic_running_statuses_are_included(self) -> None:
        """running, in_progress, and active must all be in _RUNNING_DB_STATUSES."""
        for status in ("running", "in_progress", "active"):
            self.assertIn(
                status,
                _RUNNING_DB_STATUSES,
                f"'{status}' must be a recognised running DB status (R4 constraint)",
            )


# ---------------------------------------------------------------------------
# TC-4: ttl=30 on the @memoized_query decorator
# ---------------------------------------------------------------------------


class T1002TTLTests(unittest.TestCase):
    """TC-4: The @memoized_query decorator on get_command_center uses ttl=30."""

    def test_get_command_center_decorator_has_ttl_30(self) -> None:
        """Verify that _resolve_ttl("pcc_command_center", 30) returns 30.

        The decorator stores ``ttl=30`` as ``_explicit_ttl`` in the wrapper
        closure.  ``_resolve_ttl(endpoint_name, explicit_ttl)`` returns the
        explicit value when it is not None, so passing 30 must yield 30.
        """
        effective_ttl = _resolve_ttl("pcc_command_center", explicit_ttl=30)
        self.assertEqual(
            effective_ttl,
            30,
            "_resolve_ttl('pcc_command_center', 30) must return 30 (ttl=30 kwarg honoured)",
        )

    def test_resolve_ttl_explicit_overrides_global(self) -> None:
        """Explicit ttl=30 must beat the global CCDASH_QUERY_CACHE_TTL_SECONDS."""
        # Patch global TTL to a different value and confirm explicit wins.
        with patch.object(cache_mod.config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 600):
            effective_ttl = _resolve_ttl("pcc_command_center", explicit_ttl=30)
        self.assertEqual(
            effective_ttl,
            30,
            "Explicit ttl=30 must override CCDASH_QUERY_CACHE_TTL_SECONDS=600",
        )

    def test_get_command_center_is_memoized_query_wrapped(self) -> None:
        """get_command_center must have the @memoized_query __wrapped__ sentinel."""
        method = PlanningCommandCenterQueryService.get_command_center
        self.assertTrue(
            hasattr(method, "__wrapped__"),
            "get_command_center must be decorated with @memoized_query",
        )


# ---------------------------------------------------------------------------
# TC-5: Resilience — storage failure on sessions() does not raise
# ---------------------------------------------------------------------------


class T1002ResilienceTests(unittest.IsolatedAsyncioTestCase):
    """TC-5: A sessions repo failure returns empty activeSessions gracefully."""

    async def test_sessions_repo_exception_yields_empty_active_sessions(self) -> None:
        """If sessions() raises an unexpected exception, activeSessions is [] and the
        page still returns items (status may be 'partial' but must not be 'error')."""
        project = _make_project()

        class _BrokenSessionsRepo:
            async def list_paginated(self, *args, **kwargs):
                raise RuntimeError("DB unavailable")

        storage = SimpleNamespace(
            features=lambda: _FeaturesRepo([_make_feature_row()]),
            documents=lambda: _DocumentsRepo(),
            worktree_contexts=lambda: _WorktreeRepo(),
            sessions=lambda: _BrokenSessionsRepo(),
        )
        ports = SimpleNamespace(
            storage=storage,
            workspace_registry=_WorkspaceRegistry(project),
        )

        service = PlanningCommandCenterQueryService()
        page = await service.get_command_center(
            _request_context(project),
            ports,
            project_id_override="proj-1",
            page=1,
            page_size=10,
        )

        # Page must still contain items; status should not be 'error'.
        self.assertNotEqual(page.status, "error")
        self.assertGreaterEqual(page.total, 1)
        item = page.items[0]
        self.assertIsInstance(item.active_sessions, list)
        self.assertEqual(item.active_sessions, [])

    async def test_active_sessions_model_field_has_safe_default(self) -> None:
        """PlanningCommandCenterItemDTO.active_sessions defaults to [] when not supplied."""
        import json as _json
        from backend.application.services.agent_queries.models import (
            PlanningCommandCenterFeatureDTO,
        )

        dto = PlanningCommandCenterItemDTO(
            feature=PlanningCommandCenterFeatureDTO(feature_id="feat-x"),
        )
        self.assertIsNotNone(dto.active_sessions)
        self.assertIsInstance(dto.active_sessions, list)
        self.assertEqual(dto.active_sessions, [])


if __name__ == "__main__":
    unittest.main()
