import json
import types
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.routers import api as api_router


class _FakeRepo:
    def __init__(self) -> None:
        self.last_filters = None
        self.last_include_subagents_for_facets = None
        self.last_include_subagents_for_platform_facets = None

    async def list_paginated(self, offset, limit, project_id, sort_by, sort_order, filters):
        self.last_filters = dict(filters)
        return [
            {
                "id": "S-main",
                "task_id": "",
                "status": "completed",
                "model": "claude-sonnet",
                "platform_type": "Claude Code",
                "platform_version": "2.1.52",
                "platform_versions_json": "[\"2.1.52\"]",
                "platform_version_transitions_json": "[]",
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

    async def get_logs(self, session_id):
        return []

    async def get_model_facets(self, project_id, include_subagents=True):
        self.last_include_subagents_for_facets = include_subagents
        return [
            {"model": "claude-opus-4-5-20251101", "count": 7},
            {"model": "claude-sonnet-4-0-20251001", "count": 3},
        ]

    async def get_platform_facets(self, project_id, include_subagents=True):
        self.last_include_subagents_for_platform_facets = include_subagents
        return [
            {"platform_type": "Claude Code", "platform_version": "2.1.52", "count": 9},
            {"platform_type": "Claude Code", "platform_version": "2.1.51", "count": 2},
        ]


class _FakeSessionDetailRepo:
    async def get_by_id(self, session_id):
        if session_id == "S-main":
            return {"id": session_id}
        return None


class _FakeLinkRepo:
    async def get_links_for(self, entity_type, entity_id, link_type=None):
        return [
            {
                "source_type": "feature",
                "source_id": "feat-alpha",
                "target_type": "session",
                "target_id": "S-main",
                "confidence": 0.8,
                "metadata_json": json.dumps(
                    {
                        "linkStrategy": "session_evidence",
                        "signals": [{"type": "file_write"}, {"type": "command_args_path"}],
                        "commands": ["/clear", "/model", "/dev:execute-phase"],
                        "commitHashes": ["abc1234"],
                        "ambiguityShare": 0.64,
                    }
                ),
            },
            {
                "source_type": "document",
                "source_id": "DOC-1",
                "target_type": "session",
                "target_id": "S-main",
                "confidence": 1.0,
                "metadata_json": "{}",
            },
        ]


class _FakeFeatureRepo:
    async def get_by_id(self, feature_id):
        if feature_id != "feat-alpha":
            return None
        return {
            "id": "feat-alpha",
            "name": "Feature Alpha",
            "status": "in-progress",
            "category": "enhancement",
            "updated_at": "2026-02-16T12:00:00Z",
            "total_tasks": 10,
            "completed_tasks": 4,
        }


class SessionApiRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_sessions_defaults_to_excluding_subagents(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")

        with patch.object(api_router.project_manager, "get_active_project", return_value=project), patch.object(api_router.connection, "get_connection", return_value=object()), patch.object(api_router, "get_session_repository", return_value=repo), patch.object(api_router, "load_session_mappings", return_value=[]):
            response = await api_router.list_sessions(include_subagents=False)

        self.assertEqual(response.total, 1)
        self.assertFalse(repo.last_filters["include_subagents"])
        self.assertEqual(response.items[0].rootSessionId, "S-main")

    async def test_list_sessions_accepts_thread_filters(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")

        with patch.object(api_router.project_manager, "get_active_project", return_value=project), patch.object(api_router.connection, "get_connection", return_value=object()), patch.object(api_router, "get_session_repository", return_value=repo), patch.object(api_router, "load_session_mappings", return_value=[]):
            await api_router.list_sessions(include_subagents=True, root_session_id="S-main")

        self.assertTrue(repo.last_filters["include_subagents"])
        self.assertEqual(repo.last_filters["root_session_id"], "S-main")

    async def test_list_sessions_accepts_model_identity_filters(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")
        with patch.object(api_router.project_manager, "get_active_project", return_value=project), patch.object(api_router.connection, "get_connection", return_value=object()), patch.object(api_router, "get_session_repository", return_value=repo), patch.object(api_router, "load_session_mappings", return_value=[]):
            await api_router.list_sessions(
                model_provider="Claude",
                model_family="Opus",
                model_version="Opus 4.5",
            )

        self.assertEqual(repo.last_filters["model_provider"], "Claude")
        self.assertEqual(repo.last_filters["model_family"], "Opus")
        self.assertEqual(repo.last_filters["model_version"], "Opus 4.5")

    async def test_list_sessions_accepts_platform_filters(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")
        with patch.object(api_router.project_manager, "get_active_project", return_value=project), patch.object(api_router.connection, "get_connection", return_value=object()), patch.object(api_router, "get_session_repository", return_value=repo), patch.object(api_router, "load_session_mappings", return_value=[]):
            await api_router.list_sessions(
                platform_type="Claude Code",
                platform_version="2.1.52",
            )

        self.assertEqual(repo.last_filters["platform_type"], "Claude Code")
        self.assertEqual(repo.last_filters["platform_version"], "2.1.52")

    async def test_get_session_model_facets_returns_normalized_values(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")

        with patch.object(api_router.project_manager, "get_active_project", return_value=project), patch.object(api_router.connection, "get_connection", return_value=object()), patch.object(api_router, "get_session_repository", return_value=repo):
            response = await api_router.get_session_model_facets(include_subagents=False)

        self.assertEqual(len(response), 2)
        self.assertFalse(repo.last_include_subagents_for_facets)
        self.assertEqual(response[0].modelProvider, "Claude")
        self.assertEqual(response[0].modelFamily, "Opus")
        self.assertEqual(response[0].modelVersion, "Opus 4.5")

    async def test_get_session_platform_facets_returns_values(self) -> None:
        repo = _FakeRepo()
        project = types.SimpleNamespace(id="project-1")

        with patch.object(api_router.project_manager, "get_active_project", return_value=project), patch.object(api_router.connection, "get_connection", return_value=object()), patch.object(api_router, "get_session_repository", return_value=repo):
            response = await api_router.get_session_platform_facets(include_subagents=False)

        self.assertEqual(len(response), 2)
        self.assertFalse(repo.last_include_subagents_for_platform_facets)
        self.assertEqual(response[0].platformType, "Claude Code")
        self.assertEqual(response[0].platformVersion, "2.1.52")

    async def test_get_session_linked_features_returns_scored_links(self) -> None:
        session_repo = _FakeSessionDetailRepo()
        link_repo = _FakeLinkRepo()
        feature_repo = _FakeFeatureRepo()

        with patch.object(api_router.connection, "get_connection", return_value=object()), patch.object(api_router, "get_session_repository", return_value=session_repo), patch.object(api_router, "get_entity_link_repository", return_value=link_repo), patch.object(api_router, "get_feature_repository", return_value=feature_repo):
            response = await api_router.get_session_linked_features("S-main")

        self.assertEqual(len(response), 1)
        self.assertEqual(response[0].featureId, "feat-alpha")
        self.assertEqual(response[0].featureName, "Feature Alpha")
        self.assertTrue(response[0].isPrimaryLink)
        self.assertIn("file_write", response[0].reasons)
        self.assertEqual(response[0].commands, ["/dev:execute-phase"])

    async def test_get_session_linked_features_404_when_missing(self) -> None:
        session_repo = _FakeSessionDetailRepo()

        with patch.object(api_router.connection, "get_connection", return_value=object()), patch.object(api_router, "get_session_repository", return_value=session_repo):
            with self.assertRaises(HTTPException) as ctx:
                await api_router.get_session_linked_features("S-missing")

        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
