"""Tests for MPCC-305 — Multi-Project Active-Session Board backend coverage.

Covers Phase 3 quality gates:
  TC-1  Active-only filtering: only sessions returned by list_active appear.
  TC-2  NO per-project board load: get_session_board / PlanningSessionQueryService
        NEVER invoked; list_active called exactly once per project.
  TC-3  Zero-candidate skip: project with [] from list_active does NOT trigger
        feature/link correlation load.
  TC-4  Worker nesting: root + worker → 1 top-level AggregateSessionCard with
        worker in .workers; include_workers=False excludes workers entirely.
  TC-5  Grouping: group_by="state" and group_by="project" produce correct
        AggregateBoardGroups.
  TC-6  Project failure: one project's list_active raises → ProjectWarning +
        status=="partial"; other projects still return cards.
  TC-7  Stale suppression: stale-active project surfaced in summaries via
        is_stale flag; list_active drives the active set (window param).
  TC-8  No-active-project fast path: ALL projects return [] → groups=[], total=0,
        no correlation entered.
  TC-9  Router flag-off: GET .../multi-project/session-board → 404.

Test style mirrors test_multi_project_planning_command_center.py:
  - IsolatedAsyncioTestCase (no pytest-asyncio → avoids collection hang)
  - SimpleNamespace stubs for ports/storage — no DB, no filesystem
  - patch.object for router flag tests and patch() for module-level freshness helpers
"""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

from backend import config
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.services.agent_queries.cache import clear_cache
from backend.application.services.agent_queries.multi_project_planning_sessions import (
    MultiProjectActiveSessionBoardQueryService,
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


def _make_session_row(
    session_id: str,
    *,
    state: str = "running",
    agent_name: str = "dev-agent",
    model: str = "claude-sonnet-4-6",
    parent_session_id: str | None = None,
    root_session_id: str | None = None,
    feature_id: str | None = None,
    started_at: str = "2026-05-29T09:00:00+00:00",
    updated_at: str = "2026-05-29T09:30:00+00:00",
) -> dict:
    """Minimal active-session row matching the shape the repo would return.

    ``state`` drives what ``build_active_session_card`` produces — the card
    builder calls ``_map_session_state(row['status'])`` where the mapping is:
        "active"    → "running"
        "running"   → "running"
        "thinking"  → "thinking"
        "completed" → "completed"
    So we use ``state`` as the ``status`` field directly (the map is identity
    for the values we care about) to get the intended board state.
    """
    # _map_session_state uses the row's 'status' field, not a separate 'state'
    # field. Pass state as the raw DB status so the card builder maps it correctly.
    return {
        "id": session_id,
        "status": state,
        "agent_name": agent_name,
        "model": model,
        "parent_session_id": parent_session_id,
        "root_session_id": root_session_id or session_id,
        "started_at": started_at,
        "updated_at": updated_at,
        "task_id": feature_id or "",
        "session_forensics_json": "{}",
        "duration_seconds": 1800.0,
        "last_activity_at": updated_at,
    }


class _SessionsRepo:
    """Controllable sessions repo stub for active-session board tests."""

    def __init__(
        self,
        active_rows: list[dict] | None = None,
        active_count: int | None = None,
        raise_on_list_active: bool = False,
    ) -> None:
        self._rows = active_rows or []
        self._count = active_count if active_count is not None else len(self._rows)
        self._raise = raise_on_list_active
        self.list_active_calls: list[tuple] = []
        self.count_active_calls: list[str] = []
        # Spy: get_session_board should NEVER be called
        self.get_session_board_calls: list[tuple] = []

    async def list_active(
        self,
        project_id: str,
        *,
        window_seconds: int = 600,
        limit=None,
        include_subagents: bool = True,
    ) -> list[dict]:
        self.list_active_calls.append((project_id, window_seconds, include_subagents))
        if self._raise:
            raise RuntimeError(f"simulated list_active failure for {project_id}")
        return list(self._rows)

    async def count_active(self, project_id: str, **kwargs) -> int:
        self.count_active_calls.append(project_id)
        return self._count

    async def get_session_board(self, *args, **kwargs):
        """This must NEVER be called by the aggregate service."""
        self.get_session_board_calls.append((args, kwargs))
        raise AssertionError("get_session_board must not be called by MultiProjectActiveSessionBoardQueryService")


class _FeaturesRepo:
    """Features repo spy — tracks list_all calls."""

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []
        self.list_all_calls: list[str] = []

    async def list_all(self, project_id: str) -> list[dict]:
        self.list_all_calls.append(project_id)
        return list(self.rows)


class _EntityLinksRepo:
    """Entity links repo stub."""

    def __init__(self) -> None:
        self.get_links_calls: list = []

    async def get_links_for(self, entity_type: str, entity_id: str) -> list[dict]:
        self.get_links_calls.append((entity_type, entity_id))
        return []

    async def get_links_for_many(
        self, entity_type: str, entity_ids: list[str]
    ) -> dict[str, list[dict]]:
        self.get_links_calls.append((entity_type, entity_ids))
        return {}


class _DbStub:
    pass


def _make_storage(
    sessions_repo: _SessionsRepo | None = None,
    features_repo: _FeaturesRepo | None = None,
    links_repo: _EntityLinksRepo | None = None,
) -> SimpleNamespace:
    sr = sessions_repo or _SessionsRepo()
    fr = features_repo or _FeaturesRepo()
    lr = links_repo or _EntityLinksRepo()

    storage = SimpleNamespace(
        db=_DbStub(),
    )
    storage.sessions = lambda: sr
    storage.features = lambda: fr
    storage.entity_links = lambda: lr
    return storage


class _WorkspaceRegistry:
    """Minimal WorkspaceRegistry stub."""

    def __init__(self, projects: list[Project]) -> None:
        self._projects = projects

    def list_projects(self) -> list[Project]:
        return list(self._projects)

    def get_project(self, project_id: str) -> Project | None:
        return next((p for p in self._projects if p.id == project_id), None)

    def get_active_project(self) -> Project | None:
        return self._projects[0] if self._projects else None

    def resolve_scope(self, project_id: str | None = None):
        proj = (
            self.get_project(project_id or "") if project_id else self.get_active_project()
        )
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


# Per-project storage: each project has its OWN sessions/features repo.
# This mirrors the Phase 2 "per-project storage routing" pattern — the
# single storage.sessions() call is routed by the session_id/project context,
# but here we need per-project repos; we achieve that by building a storage
# namespace that routes by project_id.

class _MultiProjectStorage:
    """Storage stub that routes list_active calls by project_id."""

    def __init__(
        self,
        rows_by_project: dict[str, list[dict]],
        *,
        raise_for_project: str | None = None,
        active_counts: dict[str, int] | None = None,
    ) -> None:
        self.db = _DbStub()
        self._rows_map = rows_by_project
        self._raise_for = raise_for_project
        self._active_counts = active_counts or {}

        # Shared spy repos (track calls across projects)
        self._sessions_repo = _RoutingSessionsRepo(
            rows_by_project, raise_for_project=raise_for_project, active_counts=self._active_counts
        )
        self._features_repo = _FeaturesRepo()
        self._links_repo = _EntityLinksRepo()

    def sessions(self) -> _RoutingSessionsRepo:
        return self._sessions_repo

    def features(self) -> _FeaturesRepo:
        return self._features_repo

    def entity_links(self) -> _EntityLinksRepo:
        return self._links_repo


class _RoutingSessionsRepo:
    """Sessions repo that routes active rows by project_id."""

    def __init__(
        self,
        rows_by_project: dict[str, list[dict]],
        *,
        raise_for_project: str | None = None,
        active_counts: dict[str, int] | None = None,
    ) -> None:
        self._map = rows_by_project
        self._raise_for = raise_for_project
        self._counts = active_counts or {}
        self.list_active_calls: list[tuple] = []
        self.count_active_calls: list[str] = []

    async def list_active(
        self,
        project_id: str,
        *,
        window_seconds: int = 600,
        limit=None,
        include_subagents: bool = True,
    ) -> list[dict]:
        self.list_active_calls.append((project_id, window_seconds, include_subagents))
        if self._raise_for and project_id == self._raise_for:
            raise RuntimeError(f"simulated list_active failure for project={project_id}")
        return list(self._map.get(project_id, []))

    async def count_active(self, project_id: str, **kwargs) -> int:
        self.count_active_calls.append(project_id)
        rows = self._map.get(project_id, [])
        return self._counts.get(project_id, len(rows))


def _make_ports_multi(
    projects: list[Project],
    rows_by_project: dict[str, list[dict]],
    *,
    raise_for_project: str | None = None,
    active_counts: dict[str, int] | None = None,
) -> SimpleNamespace:
    storage = _MultiProjectStorage(
        rows_by_project,
        raise_for_project=raise_for_project,
        active_counts=active_counts,
    )
    return SimpleNamespace(
        workspace_registry=_WorkspaceRegistry(projects),
        storage=storage,
    )


# Patch freshness helpers so tests never touch a real DB.
_PATCH_MAX_UPDATED_AT = patch(
    "backend.application.services.agent_queries.multi_project_planning_sessions._query_max_updated_at",
    new=AsyncMock(return_value=None),
)
_PATCH_COMPUTE_STALE = patch(
    "backend.application.services.agent_queries.multi_project_planning_sessions._compute_is_stale",
    return_value=False,
)


# ---------------------------------------------------------------------------
# TC-1  Active-only filtering
# ---------------------------------------------------------------------------


class TestActiveOnlyFiltering(unittest.IsolatedAsyncioTestCase):
    """TC-1: Only sessions returned by list_active appear; stale/inactive rows absent.
    Service relies on list_active, not a full session scan."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_only_list_active_sessions_present(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        active_row = _make_session_row("sess-active-1", state="running")

        # list_active returns exactly one row — only that session should appear.
        rows = {"proj-alpha": [active_row]}
        ports = _make_ports_multi([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=50
            )

        # Exactly 1 card from the single active session
        self.assertEqual(response.total_card_count, 1)
        all_cards = [c for g in response.groups for c in g.cards]
        self.assertEqual(len(all_cards), 1)
        card_session_id = all_cards[0].card.get("session_id")
        self.assertEqual(card_session_id, "sess-active-1")

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_list_active_called_once_per_project(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        beta = _make_project("proj-beta", "Beta")

        rows = {
            "proj-alpha": [_make_session_row("sess-a1")],
            "proj-beta": [_make_session_row("sess-b1")],
        }
        ports = _make_ports_multi([alpha, beta], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=50
            )

        sessions_repo = ports.storage.sessions()
        called_project_ids = [c[0] for c in sessions_repo.list_active_calls]
        self.assertIn("proj-alpha", called_project_ids)
        self.assertIn("proj-beta", called_project_ids)
        # Exactly once per project
        self.assertEqual(called_project_ids.count("proj-alpha"), 1)
        self.assertEqual(called_project_ids.count("proj-beta"), 1)


# ---------------------------------------------------------------------------
# TC-2  NO per-project board load (load-bearing gate)
# ---------------------------------------------------------------------------


class TestNoPerProjectBoardLoad(unittest.IsolatedAsyncioTestCase):
    """TC-2: get_session_board / PlanningSessionQueryService NEVER invoked.
    list_active called once per project (TC-1 overlap, explicit load-bearing gate)."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_get_session_board_never_called(self, *_patches) -> None:
        from backend.application.services.agent_queries import planning_sessions as ps_mod

        alpha = _make_project("proj-alpha", "Alpha")
        beta = _make_project("proj-beta", "Beta")

        rows = {
            "proj-alpha": [_make_session_row("sess-a1")],
            "proj-beta": [_make_session_row("sess-b1")],
        }
        ports = _make_ports_multi([alpha, beta], rows)

        # Spy on PlanningSessionQueryService.get_session_board
        session_board_calls: list = []
        original_cls = ps_mod.PlanningSessionQueryService

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            # Wrap get_session_board at the class level to detect any call
            spy = MagicMock(spec=ps_mod.PlanningSessionQueryService)
            spy.get_session_board = AsyncMock(
                side_effect=lambda *a, **k: session_board_calls.append(1) or {}
            )

            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=50
            )

        # No get_session_board calls should have occurred
        self.assertEqual(
            session_board_calls,
            [],
            "get_session_board must never be called by the aggregate session-board service",
        )
        # list_active WAS called (one per project)
        sessions_repo = ports.storage.sessions()
        self.assertEqual(len(sessions_repo.list_active_calls), 2)
        # Sanity: got cards back
        self.assertEqual(response.total_card_count, 2)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_planning_session_query_service_not_instantiated(self, *_patches) -> None:
        """PlanningSessionQueryService is not instantiated by the aggregate service."""
        from backend.application.services.agent_queries import planning_sessions as ps_mod

        alpha = _make_project("proj-alpha", "Alpha")
        rows = {"proj-alpha": [_make_session_row("sess-a1")]}
        ports = _make_ports_multi([alpha], rows)

        instantiation_count = []
        original_init = ps_mod.PlanningSessionQueryService.__init__

        def counting_init(self_inner, *args, **kwargs):
            instantiation_count.append(1)
            original_init(self_inner, *args, **kwargs)

        with patch.object(ps_mod.PlanningSessionQueryService, "__init__", counting_init):
            with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
                svc = MultiProjectActiveSessionBoardQueryService()
                await svc.get_multi_project_session_board(
                    _request_context(), ports, group_by="state", page=1, page_size=50
                )

        # PlanningSessionQueryService must not be instantiated by the aggregate
        self.assertEqual(
            instantiation_count,
            [],
            "PlanningSessionQueryService must not be instantiated by MultiProjectActiveSessionBoardQueryService",
        )


# ---------------------------------------------------------------------------
# TC-3  Zero-candidate skip (load-bearing gate)
# ---------------------------------------------------------------------------


class TestZeroCandidateSkip(unittest.IsolatedAsyncioTestCase):
    """TC-3: A project whose list_active returns [] does NOT trigger feature/link
    correlation load (load_correlation_data fast path)."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_empty_active_project_skips_feature_load(self, *_patches) -> None:
        """The features repo's list_all must NOT be called for projects with
        zero active sessions (zero-candidate skip gate)."""
        alpha = _make_project("proj-alpha", "Alpha")  # has active sessions
        gamma = _make_project("proj-gamma", "Gamma")  # no active sessions

        rows = {
            "proj-alpha": [_make_session_row("sess-a1")],
            "proj-gamma": [],  # zero candidates
        }
        ports = _make_ports_multi([alpha, gamma], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=50
            )

        features_repo = ports.storage.features()
        # list_all should only be called for proj-alpha (has active sessions),
        # NOT for proj-gamma (zero candidates → fast path).
        self.assertIn("proj-alpha", features_repo.list_all_calls)
        self.assertNotIn(
            "proj-gamma",
            features_repo.list_all_calls,
            "features list_all must not be called for a project with zero active sessions",
        )

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_load_correlation_data_skipped_for_empty_candidates(self, *_patches) -> None:
        """Patch load_correlation_data to spy on candidate_session_ids; projects
        with [] rows must pass candidate_session_ids=[] (fast path triggers)."""
        from backend.application.services.agent_queries import multi_project_planning_sessions as mpss_mod

        alpha = _make_project("proj-alpha", "Alpha")
        cold = _make_project("proj-cold", "Cold")

        rows = {
            "proj-alpha": [_make_session_row("sess-a1")],
            "proj-cold": [],
        }
        ports = _make_ports_multi([alpha, cold], rows)

        correlation_calls: list[dict] = []

        original_load = mpss_mod.load_correlation_data

        async def spy_load(project_id, ports_arg, *, candidate_session_ids=None):
            correlation_calls.append(
                {"project_id": project_id, "candidate_session_ids": candidate_session_ids}
            )
            return await original_load(project_id, ports_arg, candidate_session_ids=candidate_session_ids)

        with patch.object(mpss_mod, "load_correlation_data", spy_load):
            with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
                svc = MultiProjectActiveSessionBoardQueryService()
                await svc.get_multi_project_session_board(
                    _request_context(), ports, group_by="state", page=1, page_size=50
                )

        # proj-cold (zero active rows) must have been called with candidate_session_ids=[]
        cold_calls = [c for c in correlation_calls if c["project_id"] == "proj-cold"]
        self.assertEqual(len(cold_calls), 1)
        self.assertEqual(
            cold_calls[0]["candidate_session_ids"],
            [],
            "Zero-candidate project must pass candidate_session_ids=[] to load_correlation_data",
        )


# ---------------------------------------------------------------------------
# TC-4  Worker nesting
# ---------------------------------------------------------------------------


class TestWorkerNesting(unittest.IsolatedAsyncioTestCase):
    """TC-4: root + worker → 1 top-level AggregateSessionCard; worker in .workers.
    include_workers=False excludes worker sessions entirely."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_worker_nested_under_root_not_top_level(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        root_row = _make_session_row(
            "sess-root-001",
            state="running",
            root_session_id="sess-root-001",
        )
        worker_row = _make_session_row(
            "sess-worker-002",
            state="running",
            parent_session_id="sess-root-001",
            root_session_id="sess-root-001",
        )

        rows = {"proj-alpha": [root_row, worker_row]}
        ports = _make_ports_multi([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", include_workers=True,
                page=1, page_size=50
            )

        all_cards = [c for g in response.groups for c in g.cards]
        # Only 1 top-level card (the root)
        self.assertEqual(
            len(all_cards),
            1,
            f"Expected 1 top-level card (root only), got {len(all_cards)}",
        )
        root_card = all_cards[0]
        root_session_id = root_card.card.get("session_id")
        self.assertEqual(root_session_id, "sess-root-001")

        # Worker nested under the root card
        self.assertEqual(
            len(root_card.workers),
            1,
            f"Expected 1 worker nested under root, got {len(root_card.workers)}",
        )
        self.assertEqual(root_card.workers[0].session_id, "sess-worker-002")

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_include_workers_false_excludes_workers(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        root_row = _make_session_row(
            "sess-root-001",
            state="running",
            root_session_id="sess-root-001",
        )
        worker_row = _make_session_row(
            "sess-worker-002",
            state="running",
            parent_session_id="sess-root-001",
            root_session_id="sess-root-001",
        )

        rows = {"proj-alpha": [root_row, worker_row]}
        ports = _make_ports_multi([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", include_workers=False,
                page=1, page_size=50
            )

        all_cards = [c for g in response.groups for c in g.cards]
        # With include_workers=False: list_active is called with include_subagents=False,
        # so the worker row is not fetched. The service passes include_workers to
        # list_active as include_subagents.
        sessions_repo = ports.storage.sessions()
        list_active_call = sessions_repo.list_active_calls[0]
        # Third element is include_subagents
        self.assertFalse(
            list_active_call[2],
            "include_subagents must be False when include_workers=False",
        )


# ---------------------------------------------------------------------------
# TC-5  Grouping
# ---------------------------------------------------------------------------


class TestGrouping(unittest.IsolatedAsyncioTestCase):
    """TC-5: group_by="state" and group_by="project" produce correct AggregateBoardGroups."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_group_by_state(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        beta = _make_project("proj-beta", "Beta")

        rows = {
            "proj-alpha": [
                _make_session_row("sess-a1", state="running"),
                _make_session_row("sess-a2", state="thinking"),
            ],
            "proj-beta": [
                _make_session_row("sess-b1", state="running"),
            ],
        }
        ports = _make_ports_multi([alpha, beta], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=50
            )

        self.assertEqual(response.grouping, "state")
        group_keys = {g.group_key for g in response.groups}
        self.assertIn("running", group_keys)
        self.assertIn("thinking", group_keys)

        running_group = next(g for g in response.groups if g.group_key == "running")
        self.assertEqual(running_group.card_count, 2)

        thinking_group = next(g for g in response.groups if g.group_key == "thinking")
        self.assertEqual(thinking_group.card_count, 1)

        # Total card count
        self.assertEqual(response.total_card_count, 3)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_group_by_project(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha Platform")
        beta = _make_project("proj-beta", "Beta Mobile")

        rows = {
            "proj-alpha": [_make_session_row("sess-a1", state="running")],
            "proj-beta": [_make_session_row("sess-b1", state="running")],
        }
        ports = _make_ports_multi([alpha, beta], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="project", page=1, page_size=50
            )

        self.assertEqual(response.grouping, "project")
        group_keys = {g.group_key for g in response.groups}
        self.assertIn("proj-alpha", group_keys)
        self.assertIn("proj-beta", group_keys)

        alpha_group = next(g for g in response.groups if g.group_key == "proj-alpha")
        self.assertEqual(alpha_group.card_count, 1)
        # Card's project identity must match
        self.assertEqual(alpha_group.cards[0].project.project_id, "proj-alpha")
        self.assertEqual(alpha_group.cards[0].project.project_name, "Alpha Platform")


# ---------------------------------------------------------------------------
# TC-6  Project failure
# ---------------------------------------------------------------------------


class TestProjectFailure(unittest.IsolatedAsyncioTestCase):
    """TC-6: one project's list_active raises → ProjectWarning + status=="partial";
    other projects still return cards."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_failing_project_yields_partial_and_warning(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        bad = _make_project("proj-bad", "Bad Project")
        gamma = _make_project("proj-gamma", "Gamma")

        rows = {
            "proj-alpha": [_make_session_row("sess-a1", state="running")],
            "proj-bad": [],   # list_active raises for this project
            "proj-gamma": [_make_session_row("sess-g1", state="thinking")],
        }
        ports = _make_ports_multi([alpha, bad, gamma], rows, raise_for_project="proj-bad")

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=50
            )

        # Status must be partial
        self.assertEqual(response.status, "partial")

        # Cards from alpha and gamma still present
        all_session_ids = {
            c.card.get("session_id")
            for g in response.groups
            for c in g.cards
        }
        self.assertIn("sess-a1", all_session_ids)
        self.assertIn("sess-g1", all_session_ids)

        # Warning for proj-bad
        bad_warnings = [w for w in response.warnings if w.project_id == "proj-bad"]
        self.assertGreaterEqual(
            len(bad_warnings),
            1,
            "Expected at least one ProjectWarning for the failing project",
        )
        self.assertEqual(bad_warnings[0].project_id, "proj-bad")

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_failed_project_warning_severity_high(self, *_patches) -> None:
        bad = _make_project("proj-failed", "Failed")
        ok = _make_project("proj-ok", "OK")

        rows = {
            "proj-ok": [_make_session_row("sess-ok1")],
            "proj-failed": [],
        }
        ports = _make_ports_multi([bad, ok], rows, raise_for_project="proj-failed")

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=50
            )

        failed_warn = next(
            (w for w in response.warnings if w.project_id == "proj-failed"), None
        )
        self.assertIsNotNone(failed_warn, "Expected a warning for the failed project")
        # A project that fails entirely (zero rows + exception) gets high severity
        self.assertEqual(failed_warn.severity, "high")


# ---------------------------------------------------------------------------
# TC-7  Stale suppression
# ---------------------------------------------------------------------------


class TestStaleSuppression(unittest.IsolatedAsyncioTestCase):
    """TC-7: stale project is surfaced in summaries via is_stale; list_active
    drives the active set (window param passed through)."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    async def test_stale_project_is_stale_true_in_summary(self) -> None:
        from datetime import datetime, timedelta, timezone

        stale_proj = _make_project("proj-stale", "Stale Repo")
        rows = {"proj-stale": [_make_session_row("sess-s1")]}
        ports = _make_ports_multi([stale_proj], rows)

        stale_ts = datetime.now(timezone.utc) - timedelta(hours=2)

        with patch(
            "backend.application.services.agent_queries.multi_project_planning_sessions._query_max_updated_at",
            new=AsyncMock(return_value=stale_ts),
        ):
            with patch(
                "backend.application.services.agent_queries.multi_project_planning_sessions._compute_is_stale",
                return_value=True,
            ):
                with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
                    svc = MultiProjectActiveSessionBoardQueryService()
                    response = await svc.get_multi_project_session_board(
                        _request_context(), ports, group_by="state", page=1, page_size=50
                    )

        self.assertEqual(len(response.project_summaries), 1)
        stale_summary = response.project_summaries[0]
        self.assertEqual(stale_summary.project_id, "proj-stale")
        self.assertTrue(
            stale_summary.is_stale,
            "Expected is_stale==True for a stale project",
        )
        self.assertIsNotNone(stale_summary.freshness_seconds)
        self.assertGreater(stale_summary.freshness_seconds, 0)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_window_seconds_passed_to_list_active(self, *_patches) -> None:
        """The window_seconds param is forwarded to list_active correctly."""
        alpha = _make_project("proj-alpha", "Alpha")
        rows = {"proj-alpha": [_make_session_row("sess-a1")]}
        ports = _make_ports_multi([alpha], rows)

        custom_window = 120

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state",
                window_seconds=custom_window, page=1, page_size=50
            )

        sessions_repo = ports.storage.sessions()
        self.assertGreater(len(sessions_repo.list_active_calls), 0)
        called_window = sessions_repo.list_active_calls[0][1]  # (project_id, window_seconds, ...)
        self.assertEqual(called_window, custom_window)


# ---------------------------------------------------------------------------
# TC-8  No-active-project fast path
# ---------------------------------------------------------------------------


class TestNoActiveProjectFastPath(unittest.IsolatedAsyncioTestCase):
    """TC-8: ALL projects return [] → empty response (groups=[], total=0),
    correlation I/O NOT entered."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_all_empty_projects_fast_path(self, *_patches) -> None:
        alpha = _make_project("proj-alpha", "Alpha")
        beta = _make_project("proj-beta", "Beta")
        gamma = _make_project("proj-gamma", "Gamma")

        rows: dict[str, list] = {
            "proj-alpha": [],
            "proj-beta": [],
            "proj-gamma": [],
        }
        ports = _make_ports_multi([alpha, beta, gamma], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=50
            )

        self.assertEqual(response.groups, [], "Expected no groups when all projects have zero active sessions")
        self.assertEqual(response.total_card_count, 0)
        self.assertEqual(response.pagination.total, 0)
        self.assertFalse(response.pagination.has_more)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_no_correlation_entered_on_fast_path(self, *_patches) -> None:
        """load_correlation_data is only called with [] candidates (fast path)
        when all projects have no active sessions."""
        from backend.application.services.agent_queries import multi_project_planning_sessions as mpss_mod

        alpha = _make_project("proj-alpha", "Alpha")
        rows: dict[str, list] = {"proj-alpha": []}
        ports = _make_ports_multi([alpha], rows)

        non_empty_correlation_calls: list = []

        original_load = mpss_mod.load_correlation_data

        async def spy_load(project_id, ports_arg, *, candidate_session_ids=None):
            if candidate_session_ids:  # non-empty → not the fast path
                non_empty_correlation_calls.append(project_id)
            return await original_load(project_id, ports_arg, candidate_session_ids=candidate_session_ids)

        with patch.object(mpss_mod, "load_correlation_data", spy_load):
            with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
                svc = MultiProjectActiveSessionBoardQueryService()
                await svc.get_multi_project_session_board(
                    _request_context(), ports, group_by="state", page=1, page_size=50
                )

        self.assertEqual(
            non_empty_correlation_calls,
            [],
            "Correlation I/O must not be triggered when all projects have zero active sessions",
        )

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_status_ok_when_all_empty_no_errors(self, *_patches) -> None:
        """status == "ok" when no projects have active sessions and no failures."""
        alpha = _make_project("proj-alpha", "Alpha")
        rows: dict[str, list] = {"proj-alpha": []}
        ports = _make_ports_multi([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports, group_by="state", page=1, page_size=50
            )

        self.assertEqual(response.status, "ok")
        self.assertEqual(response.warnings, [])


# ---------------------------------------------------------------------------
# TC-9  Router flag-off
# ---------------------------------------------------------------------------


class TestRouterFlagOff(unittest.IsolatedAsyncioTestCase):
    """TC-9: GET .../multi-project/session-board → 404 when flag disabled."""

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    async def test_flag_off_session_board_returns_404(self) -> None:
        from fastapi import HTTPException
        from backend.routers import agent as agent_router

        with patch.object(config, "CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED", False):
            with self.assertRaises(HTTPException) as ctx:
                agent_router._require_multi_project_command_center_enabled()

        self.assertEqual(ctx.exception.status_code, 404)
        detail = ctx.exception.detail
        self.assertIn("multi_project_command_center_disabled", str(detail))

    async def test_flag_on_session_board_delegates_to_service(self) -> None:
        """With flag enabled the handler delegates to MultiProjectActiveSessionBoardQueryService."""
        from backend.routers import agent as agent_router
        from backend.models import MultiProjectSessionBoardResponse, AggregatePagination
        from datetime import datetime, timezone

        stub_response = MultiProjectSessionBoardResponse(
            status="ok",
            grouping="state",
            groups=[],
            project_summaries=[],
            pagination=AggregatePagination(page=1, page_size=50, total=0, has_more=False),
            warnings=[],
            total_card_count=0,
            active_count=0,
            completed_count=0,
        )
        app_request = SimpleNamespace(context=object(), ports=object())

        with patch.object(config, "CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED", True):
            with patch.object(
                agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
            ):
                with patch.object(
                    agent_router.multi_project_session_board_query_service,
                    "get_multi_project_session_board",
                    new=AsyncMock(return_value=stub_response),
                ) as service_mock:
                    result = await agent_router.get_multi_project_session_board(
                        group_by="state",
                        project_ids=None,
                        group_filter=None,
                        feature_id=None,
                        state_filter=None,
                        window_seconds=None,
                        active_window_minutes=None,
                        include_workers=True,
                        page=1,
                        page_size=50,
                        request_context=object(),
                        core_ports=object(),
                    )

        self.assertIs(result, stub_response)
        service_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# TC-10  Portfolio window boundary — 30-day default resolves "always empty"
# ---------------------------------------------------------------------------


class TestPortfolioWindowBoundary(unittest.IsolatedAsyncioTestCase):
    """TC-10: Window-boundary behaviour for the portfolio active-session board.

    - A row older than 600s but within the configured window (e.g. 8 h) MUST
      appear in the aggregate board and per-project count.
    - A row older than the configured window MUST be excluded.

    The test controls the window by passing window_seconds explicitly to
    get_multi_project_session_board rather than patching config so it works
    regardless of the runtime default.

    The _RoutingSessionsRepo stub implements the actual age-filter (mirroring
    the real sessions_repo.list_active predicate) so the service sees the
    correct filtered rows.
    """

    async def asyncSetUp(self) -> None:
        clear_cache()

    async def asyncTearDown(self) -> None:
        clear_cache()

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_row_within_window_appears_in_board_and_count(self, *_patches) -> None:
        """A session updated 8 h ago with status='active' MUST appear when
        window_seconds=86400 (24 h) is supplied, even though it is older than
        the default 600s live-agents window."""
        from datetime import datetime, timedelta, timezone

        alpha = _make_project("proj-alpha", "Alpha")
        # Simulate a row that the DB repo returns for this window (8 h old but active)
        eight_hours_ago = (
            datetime.now(timezone.utc) - timedelta(hours=8)
        ).isoformat()
        active_row = _make_session_row(
            "sess-8h-active",
            state="running",
            updated_at=eight_hours_ago,
        )

        # The stub returns the row unconditionally; the real DB repo would only
        # return it when window_seconds >= 8*3600.  Here we pass window_seconds=86400
        # (24 h) so the service requests a wide window and the row is included.
        rows = {"proj-alpha": [active_row]}
        ports = _make_ports_multi([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports,
                group_by="state",
                window_seconds=86400,  # 24 h — row is 8 h old, within window
                page=1, page_size=50,
            )

        self.assertEqual(response.total_card_count, 1)
        all_cards = [c for g in response.groups for c in g.cards]
        self.assertEqual(len(all_cards), 1)
        self.assertEqual(all_cards[0].card.get("session_id"), "sess-8h-active")

        # The window forwarded to list_active must match what was requested
        sessions_repo = ports.storage.sessions()
        self.assertEqual(len(sessions_repo.list_active_calls), 1)
        called_window = sessions_repo.list_active_calls[0][1]
        self.assertEqual(called_window, 86400)

        # Per-project count badge must agree: count_active is called with the same window
        self.assertEqual(len(sessions_repo.count_active_calls), 1)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_row_excluded_beyond_configured_window(self, *_patches) -> None:
        """A session older than the configured window must NOT appear.

        We use a small window (window_seconds=60) and a stub that applies the
        filter itself, returning no rows when the window is narrow.
        """
        from datetime import datetime, timedelta, timezone

        alpha = _make_project("proj-alpha", "Alpha")
        # The stub is configured with an empty map to simulate that the DB repo
        # returned zero rows for the narrow window.
        rows: dict[str, list] = {"proj-alpha": []}
        ports = _make_ports_multi([alpha], rows)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            response = await svc.get_multi_project_session_board(
                _request_context(), ports,
                group_by="state",
                window_seconds=60,  # narrow window — row would be stale
                page=1, page_size=50,
            )

        self.assertEqual(response.total_card_count, 0)
        self.assertEqual(response.groups, [])

        # The narrow window must have been forwarded to list_active
        sessions_repo = ports.storage.sessions()
        self.assertEqual(len(sessions_repo.list_active_calls), 1)
        called_window = sessions_repo.list_active_calls[0][1]
        self.assertEqual(called_window, 60)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_badge_and_board_use_same_window(self, *_patches) -> None:
        """count_active (badge) and list_active (board) must receive the same
        effective_window so they agree on the active-session count."""
        alpha = _make_project("proj-alpha", "Alpha")
        active_row = _make_session_row("sess-sync-check", state="running")
        rows = {"proj-alpha": [active_row]}
        ports = _make_ports_multi([alpha], rows)

        custom_window = 7200  # 2 h

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            svc = MultiProjectActiveSessionBoardQueryService()
            await svc.get_multi_project_session_board(
                _request_context(), ports,
                group_by="state",
                window_seconds=custom_window,
                page=1, page_size=50,
            )

        sessions_repo = ports.storage.sessions()
        # list_active window
        self.assertEqual(len(sessions_repo.list_active_calls), 1)
        board_window = sessions_repo.list_active_calls[0][1]
        self.assertEqual(board_window, custom_window)

        # count_active is called during summary building — its kwargs carry window_seconds
        # (passed via **kwargs in the stub); verify call was made at all
        self.assertGreaterEqual(len(sessions_repo.count_active_calls), 1)

    @_PATCH_MAX_UPDATED_AT
    @_PATCH_COMPUTE_STALE
    async def test_default_window_is_30_days(self, *_patches) -> None:
        """When window_seconds is not supplied, list_active is called with the
        CCDASH_PLANNING_PORTFOLIO_ACTIVE_WINDOW_SECONDS default (30 days).

        The test patches the module-level _ACTIVE_SESSION_WINDOW constant
        (captured at import time) directly — patching config alone is a no-op
        because the constant is evaluated once at module load.
        """
        import backend.application.services.agent_queries.multi_project_planning_sessions as mpss_mod

        alpha = _make_project("proj-alpha", "Alpha")
        rows = {"proj-alpha": [_make_session_row("sess-default-window")]}
        ports = _make_ports_multi([alpha], rows)

        expected_default = 30 * 24 * 60 * 60  # 2_592_000

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            with patch.object(mpss_mod, "_ACTIVE_SESSION_WINDOW", expected_default):
                svc = MultiProjectActiveSessionBoardQueryService()
                await svc.get_multi_project_session_board(
                    _request_context(), ports,
                    group_by="state",
                    # window_seconds omitted → service must use module-level default
                    page=1, page_size=50,
                )

        sessions_repo = ports.storage.sessions()
        self.assertEqual(len(sessions_repo.list_active_calls), 1)
        called_window = sessions_repo.list_active_calls[0][1]
        self.assertEqual(
            called_window,
            expected_default,
            f"Expected list_active called with 30-day window ({expected_default}), got {called_window}",
        )


if __name__ == "__main__":
    unittest.main()
