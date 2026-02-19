import json
import types
import unittest
from unittest.mock import patch

from backend.routers import features as features_router
from backend.session_mappings import default_session_mappings


class _FakeFeatureRepo:
    async def get_by_id(self, feature_id):
        if feature_id != "feat-1":
            return None
        return {"id": "feat-1", "name": "Feature One"}


class _FakeLinkRepo:
    async def get_links_for(self, source_type, source_id, link_type=None):
        return [
            {
                "source_type": "feature",
                "source_id": "feat-1",
                "target_type": "session",
                "target_id": "S-1",
                "confidence": 0.8,
                "metadata_json": json.dumps(
                    {
                        "linkStrategy": "session_evidence",
                        "signals": [{"type": "command_args_path"}],
                        "commands": ["/dev:execute-phase"],
                        "title": "Execute phase",
                    }
                ),
            }
        ]


class _FakeSessionRepo:
    def __init__(self, rows=None, logs_by_id=None, root_members=None):
        default_row = {
            "id": "S-1",
            "status": "completed",
            "model": "claude",
            "started_at": "2026-02-17T00:00:00Z",
            "total_cost": 0.12,
            "duration_seconds": 120,
            "git_commit_hash": None,
            "git_commit_hashes_json": "[]",
            "session_type": "session",
            "parent_session_id": None,
            "root_session_id": "S-1",
            "agent_id": None,
        }
        self.rows = rows or {"S-1": default_row}
        self.logs_by_id = logs_by_id or {
            "S-1": [
                {
                    "type": "command",
                    "content": "/dev:execute-phase",
                    "metadata_json": json.dumps(
                        {
                            "args": "1 docs/project_plans/implementation_plans/features/example-v1.md",
                            "parsedCommand": {
                                "phaseToken": "1",
                                "phases": ["1"],
                                "featurePath": "docs/project_plans/implementation_plans/features/example-v1.md",
                                "featureSlug": "example-v1",
                            },
                        }
                    ),
                }
            ]
        }
        self.root_members = root_members or {"S-1": ["S-1"]}

    async def get_by_id(self, session_id):
        return self.rows.get(session_id)

    async def get_logs(self, session_id):
        return self.logs_by_id.get(session_id, [])

    async def count(self, project_id, filters=None):
        filters = filters or {}
        root_id = filters.get("root_session_id")
        if root_id:
            return len(self.root_members.get(root_id, []))
        return len(self.rows)

    async def list_paginated(self, offset, limit, project_id=None, sort_by="started_at", sort_order="desc", filters=None):
        filters = filters or {}
        root_id = filters.get("root_session_id")
        if root_id:
            ids = self.root_members.get(root_id, [])
            members = [self.rows[sid] for sid in ids if sid in self.rows]
        else:
            members = list(self.rows.values())
        return members[offset : offset + limit]


class FeatureLinkedSessionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_linked_sessions_include_session_metadata(self) -> None:
        feature_repo = _FakeFeatureRepo()
        link_repo = _FakeLinkRepo()
        session_repo = _FakeSessionRepo()
        project = types.SimpleNamespace(id="project-1")

        with patch.object(features_router.connection, "get_connection", return_value=object()), patch.object(features_router.project_manager, "get_active_project", return_value=project), patch.object(features_router, "get_feature_repository", return_value=feature_repo), patch.object(features_router, "get_entity_link_repository", return_value=link_repo), patch.object(features_router, "get_session_repository", return_value=session_repo), patch.object(features_router, "load_session_mappings", return_value=default_session_mappings()):
            response = await features_router.get_feature_linked_sessions("feat-1")

        self.assertEqual(len(response), 1)
        metadata = response[0].sessionMetadata
        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertEqual(metadata.get("sessionTypeLabel"), "Phased Execution")
        self.assertEqual(metadata.get("relatedPhases"), ["1"])
        self.assertEqual(response[0].title, "Phased Execution - Phase 1")

    async def test_linked_sessions_include_inherited_subthreads_for_linked_main(self) -> None:
        feature_repo = _FakeFeatureRepo()
        project = types.SimpleNamespace(id="project-1")

        class _MainOnlyLinkRepo:
            async def get_links_for(self, source_type, source_id, link_type=None):
                return [
                    {
                        "source_type": "feature",
                        "source_id": "feat-1",
                        "target_type": "session",
                        "target_id": "S-main",
                        "confidence": 0.9,
                        "metadata_json": json.dumps({"linkStrategy": "session_evidence", "commands": ["/dev:execute-phase"]}),
                    }
                ]

        rows = {
            "S-main": {
                "id": "S-main",
                "status": "completed",
                "model": "claude",
                "started_at": "2026-02-17T00:00:00Z",
                "total_cost": 1.0,
                "duration_seconds": 120,
                "git_commit_hash": None,
                "git_commit_hashes_json": "[]",
                "session_type": "session",
                "parent_session_id": None,
                "root_session_id": "S-main",
                "agent_id": None,
            },
            "S-agent-a1": {
                "id": "S-agent-a1",
                "status": "completed",
                "model": "claude",
                "started_at": "2026-02-17T00:01:00Z",
                "total_cost": 0.4,
                "duration_seconds": 45,
                "git_commit_hash": None,
                "git_commit_hashes_json": "[]",
                "session_type": "subagent",
                "parent_session_id": "S-main",
                "root_session_id": "S-main",
                "agent_id": "a1",
            },
            "S-agent-a2": {
                "id": "S-agent-a2",
                "status": "completed",
                "model": "claude",
                "started_at": "2026-02-17T00:02:00Z",
                "total_cost": 0.5,
                "duration_seconds": 60,
                "git_commit_hash": None,
                "git_commit_hashes_json": "[]",
                "session_type": "subagent",
                "parent_session_id": "S-main",
                "root_session_id": "S-main",
                "agent_id": "a2",
            },
        }
        logs_by_id = {
            "S-main": [
                {
                    "type": "command",
                    "content": "/dev:execute-phase",
                    "metadata_json": json.dumps({"args": "1 docs/project_plans/implementation_plans/features/example-v1.md"}),
                }
            ],
            "S-agent-a1": [],
            "S-agent-a2": [],
        }
        root_members = {"S-main": ["S-main", "S-agent-a1", "S-agent-a2"]}
        session_repo = _FakeSessionRepo(rows=rows, logs_by_id=logs_by_id, root_members=root_members)

        with (
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router.project_manager, "get_active_project", return_value=project),
            patch.object(features_router, "get_feature_repository", return_value=feature_repo),
            patch.object(features_router, "get_entity_link_repository", return_value=_MainOnlyLinkRepo()),
            patch.object(features_router, "get_session_repository", return_value=session_repo),
            patch.object(features_router, "load_session_mappings", return_value=default_session_mappings()),
        ):
            response = await features_router.get_feature_linked_sessions("feat-1")

        ids = {item.sessionId for item in response}
        self.assertEqual(ids, {"S-main", "S-agent-a1", "S-agent-a2"})

        inherited = {item.sessionId: item for item in response if item.sessionId.startswith("S-agent-")}
        self.assertEqual(inherited["S-agent-a1"].linkStrategy, "thread_inheritance")
        self.assertTrue(inherited["S-agent-a1"].isSubthread)
        self.assertEqual(inherited["S-agent-a2"].linkStrategy, "thread_inheritance")
        self.assertTrue(inherited["S-agent-a2"].isSubthread)


if __name__ == "__main__":
    unittest.main()
