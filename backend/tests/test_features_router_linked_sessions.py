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
    async def get_by_id(self, session_id):
        if session_id != "S-1":
            return None
        return {
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

    async def get_logs(self, session_id):
        return [
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


if __name__ == "__main__":
    unittest.main()
