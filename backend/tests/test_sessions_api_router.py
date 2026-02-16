import types
import unittest
from unittest.mock import patch

from backend.routers import api as api_router


class _FakeRepo:
    def __init__(self) -> None:
        self.last_filters = None

    async def list_paginated(self, offset, limit, project_id, sort_by, sort_order, filters):
        self.last_filters = dict(filters)
        return [
            {
                "id": "S-main",
                "task_id": "",
                "status": "completed",
                "model": "claude-sonnet",
                "session_type": "session",
                "parent_session_id": None,
                "root_session_id": "S-main",
                "agent_id": None,
                "duration_seconds": 1,
                "tokens_in": 1,
                "tokens_out": 1,
                "total_cost": 0.0,
                "started_at": "2026-02-16T00:00:00Z",
                "quality_rating": 0,
                "friction_rating": 0,
                "git_commit_hash": None,
                "git_author": None,
                "git_branch": None,
            }
        ]

    async def count(self, project_id, filters):
        return 1


class SessionApiRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_sessions_defaults_to_excluding_subagents(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")

        with patch.object(api_router.project_manager, "get_active_project", return_value=project), patch.object(api_router.connection, "get_connection", return_value=object()), patch.object(api_router, "get_session_repository", return_value=repo):
            response = await api_router.list_sessions(include_subagents=False)

        self.assertEqual(response.total, 1)
        self.assertFalse(repo.last_filters["include_subagents"])
        self.assertEqual(response.items[0].rootSessionId, "S-main")

    async def test_list_sessions_accepts_thread_filters(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")

        with patch.object(api_router.project_manager, "get_active_project", return_value=project), patch.object(api_router.connection, "get_connection", return_value=object()), patch.object(api_router, "get_session_repository", return_value=repo):
            await api_router.list_sessions(include_subagents=True, root_session_id="S-main")

        self.assertTrue(repo.last_filters["include_subagents"])
        self.assertEqual(repo.last_filters["root_session_id"], "S-main")


if __name__ == "__main__":
    unittest.main()
