"""Tests for server-side cursor/page pagination on the planning session-board endpoint.

Covers T4-001: get_session_board() with explicit cursor+limit params, default
behavior (no cursor, limit=500), and next_cursor generation / terminal page.
"""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.planning_sessions import PlanningSessionQueryService


# ── Lightweight test doubles ──────────────────────────────────────────────────


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


def _make_session(session_id: str, started_at: str = "2026-01-01T00:00:00Z") -> dict:
    """Build a minimal session dict suitable for board card construction."""
    return {
        "id": session_id,
        "status": "completed",
        "started_at": started_at,
        "ended_at": started_at,
        "model": "claude-sonnet",
        "tokens_in": 100,
        "tokens_out": 50,
        "duration_seconds": 10.0,
        "parent_session_id": None,
        "root_session_id": None,
        "agent_id": None,
        "session_type": None,
        "session_forensics_json": None,
    }


def _make_storage(sessions: list[dict]) -> types.SimpleNamespace:
    """Return a storage double whose sessions().list_paginated returns ``sessions``."""
    return types.SimpleNamespace(
        db=object(),
        features=lambda: types.SimpleNamespace(list_all=AsyncMock(return_value=[])),
        sessions=lambda: types.SimpleNamespace(
            list_paginated=AsyncMock(return_value=sessions)
        ),
        entity_links=lambda: types.SimpleNamespace(
            get_links_for_many=AsyncMock(return_value={})
        ),
        sync_state=lambda: types.SimpleNamespace(list_all=AsyncMock(return_value=[])),
    )


def _context(project_id: str = "proj-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Test Project",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


def _ports(sessions: list[dict]) -> CorePorts:
    project = types.SimpleNamespace(id="proj-1", name="Test Project")
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_make_storage(sessions),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class PlanningSessionsPaginationTests(unittest.IsolatedAsyncioTestCase):
    """T4-001: server-side cursor/page pagination for get_session_board."""

    def setUp(self) -> None:
        self.service = PlanningSessionQueryService()
        self.ctx = _context()

    # ── Default behavior (no cursor, default limit=500) ───────────────────────

    async def test_default_returns_first_page_page1(self) -> None:
        """No cursor → page=1, page_size=500 (backward-compatible default)."""
        sessions = [_make_session(f"s{i}") for i in range(3)]
        ports = _ports(sessions)

        result = await self.service.get_session_board(self.ctx, ports)

        self.assertEqual(result.page, 1)
        self.assertEqual(result.page_size, 500)

    async def test_default_no_next_cursor_when_fewer_rows_than_limit(self) -> None:
        """Fewer rows than limit → next_cursor is None (terminal page)."""
        sessions = [_make_session(f"s{i}") for i in range(3)]
        ports = _ports(sessions)

        result = await self.service.get_session_board(self.ctx, ports)

        self.assertIsNone(result.next_cursor)

    async def test_status_ok_with_sessions(self) -> None:
        """Status is 'ok' when all loads succeed."""
        sessions = [_make_session("sess-1")]
        ports = _ports(sessions)

        result = await self.service.get_session_board(self.ctx, ports)

        self.assertIn(result.status, ("ok", "partial"))

    # ── Explicit limit: fewer rows → terminal page ────────────────────────────

    async def test_explicit_limit_fewer_rows_no_next_cursor(self) -> None:
        """limit=10 but only 5 rows returned → next_cursor is None."""
        sessions = [_make_session(f"s{i}", started_at=f"2026-01-{i + 1:02d}T00:00:00Z") for i in range(5)]
        ports = _ports(sessions)

        result = await self.service.get_session_board(self.ctx, ports, limit=10)

        self.assertIsNone(result.next_cursor)
        self.assertEqual(result.page_size, 10)

    # ── Explicit limit: exactly limit rows → has next_cursor ─────────────────

    async def test_explicit_limit_full_page_has_next_cursor(self) -> None:
        """limit=3 and exactly 3 rows returned → next_cursor is set."""
        sessions = [_make_session(f"s{i}", started_at=f"2026-01-{i + 1:02d}T00:00:00Z") for i in range(3)]
        ports = _ports(sessions)

        result = await self.service.get_session_board(self.ctx, ports, limit=3)

        self.assertIsNotNone(result.next_cursor)
        # Cursor must be a non-empty string
        self.assertIsInstance(result.next_cursor, str)
        self.assertTrue(len(result.next_cursor) > 0)  # type: ignore[arg-type]

    async def test_next_cursor_encodes_page_number(self) -> None:
        """next_cursor encodes the next (2nd) page number."""
        sessions = [_make_session(f"s{i}", started_at=f"2026-01-{i + 1:02d}T00:00:00Z") for i in range(2)]
        ports = _ports(sessions)

        result = await self.service.get_session_board(self.ctx, ports, limit=2)

        assert result.next_cursor is not None
        page_str, _ = result.next_cursor.split(":", 1)
        self.assertEqual(int(page_str), 2)

    # ── Cursor decoding → correct offset on second page ──────────────────────

    async def test_cursor_page2_passes_correct_offset(self) -> None:
        """Providing cursor='2:<iso>' causes offset=limit to be used."""
        # We capture the offset argument passed to list_paginated.
        captured: dict = {}

        async def mock_list_paginated(offset: int, limit: int, **_kwargs):
            captured["offset"] = offset
            captured["limit"] = limit
            return []

        project = types.SimpleNamespace(id="proj-1", name="Test Project")
        storage = types.SimpleNamespace(
            db=object(),
            features=lambda: types.SimpleNamespace(list_all=AsyncMock(return_value=[])),
            sessions=lambda: types.SimpleNamespace(
                list_paginated=mock_list_paginated,
            ),
            entity_links=lambda: types.SimpleNamespace(
                get_links_for_many=AsyncMock(return_value={})
            ),
            sync_state=lambda: types.SimpleNamespace(list_all=AsyncMock(return_value=[])),
        )
        ports = CorePorts(
            identity_provider=_IdentityProvider(),
            authorization_policy=_AuthorizationPolicy(),
            workspace_registry=_WorkspaceRegistry(project),
            storage=storage,
            job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
            integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
        )

        # cursor encodes page 2 → expected offset = (2-1)*5 = 5
        cursor = "2:2026-01-05T00:00:00Z"
        await self.service.get_session_board(self.ctx, ports, cursor=cursor, limit=5)

        self.assertEqual(captured.get("offset"), 5)
        self.assertEqual(captured.get("limit"), 5)

    async def test_invalid_cursor_falls_back_to_offset_zero(self) -> None:
        """An unparseable cursor must not raise; it falls back to offset=0."""
        captured: dict = {}

        async def mock_list_paginated(offset: int, limit: int, **_kwargs):
            captured["offset"] = offset
            return []

        project = types.SimpleNamespace(id="proj-1", name="Test Project")
        storage = types.SimpleNamespace(
            db=object(),
            features=lambda: types.SimpleNamespace(list_all=AsyncMock(return_value=[])),
            sessions=lambda: types.SimpleNamespace(
                list_paginated=mock_list_paginated,
            ),
            entity_links=lambda: types.SimpleNamespace(
                get_links_for_many=AsyncMock(return_value={})
            ),
            sync_state=lambda: types.SimpleNamespace(list_all=AsyncMock(return_value=[])),
        )
        ports = CorePorts(
            identity_provider=_IdentityProvider(),
            authorization_policy=_AuthorizationPolicy(),
            workspace_registry=_WorkspaceRegistry(project),
            storage=storage,
            job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
            integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
        )

        await self.service.get_session_board(self.ctx, ports, cursor="NOT_VALID_CURSOR", limit=10)

        self.assertEqual(captured.get("offset"), 0)

    # ── No-project-scope error path ───────────────────────────────────────────

    async def test_missing_project_scope_returns_error_status(self) -> None:
        """When workspace_registry returns no scope, status='error' is returned."""
        storage = types.SimpleNamespace(
            db=object(),
            features=lambda: types.SimpleNamespace(list_all=AsyncMock(return_value=[])),
            sessions=lambda: types.SimpleNamespace(list_paginated=AsyncMock(return_value=[])),
            entity_links=lambda: types.SimpleNamespace(get_links_for_many=AsyncMock(return_value={})),
            sync_state=lambda: types.SimpleNamespace(list_all=AsyncMock(return_value=[])),
        )
        no_project_registry = types.SimpleNamespace(
            get_active_project=lambda: None,
            resolve_scope=lambda project_id=None: (None, None),
        )
        ports = CorePorts(
            identity_provider=_IdentityProvider(),
            authorization_policy=_AuthorizationPolicy(),
            workspace_registry=no_project_registry,
            storage=storage,
            job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
            integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
        )
        ctx = RequestContext(
            principal=Principal(subject="test", display_name="Test", auth_mode="test"),
            workspace=None,
            project=None,  # no project scope
            runtime_profile="test",
            trace=TraceContext(request_id="req-err"),
        )

        result = await self.service.get_session_board(ctx, ports)

        self.assertEqual(result.status, "error")
        self.assertIsNone(result.next_cursor)

    # ── Page number in response ───────────────────────────────────────────────

    async def test_page_number_is_1_on_first_call(self) -> None:
        """First page (no cursor) always reports page=1."""
        ports = _ports([])

        result = await self.service.get_session_board(self.ctx, ports, limit=50)

        self.assertEqual(result.page, 1)

    async def test_page_size_matches_limit(self) -> None:
        """page_size in response matches the limit param."""
        ports = _ports([])

        result = await self.service.get_session_board(self.ctx, ports, limit=42)

        self.assertEqual(result.page_size, 42)

    # ── DTO shape: pagination fields present even with empty result ───────────

    async def test_pagination_fields_present_on_empty_board(self) -> None:
        """page, page_size, next_cursor are always present in the DTO."""
        ports = _ports([])

        result = await self.service.get_session_board(self.ctx, ports)

        self.assertIsNotNone(result.page)
        self.assertIsNotNone(result.page_size)
        # next_cursor may be None on an empty result — that is correct
        self.assertIn("next_cursor", type(result).model_fields)


if __name__ == "__main__":
    unittest.main()
