import unittest

from backend.routers import features as features_router


class _FakeFeatureRepo:
    def __init__(self, rows):
        self._rows = rows

    async def list_all(self, project_id):
        return self._rows


class FeatureAliasResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_prefers_best_canonical_alias_for_base_slug(self) -> None:
        repo = _FakeFeatureRepo([
            {
                "id": "multi-platform-project-deployments",
                "status": "in-progress",
                "completed_tasks": 65,
                "total_tasks": 71,
                "updated_at": "2026-02-19T15:00:00Z",
            },
            {
                "id": "multi-platform-project-deployments-v1",
                "status": "done",
                "completed_tasks": 71,
                "total_tasks": 71,
                "updated_at": "2026-02-19T16:00:00Z",
            },
        ])

        resolved = await features_router._resolve_feature_alias_id(
            repo,
            "project-1",
            "multi-platform-project-deployments",
        )

        self.assertEqual(resolved, "multi-platform-project-deployments-v1")

    async def test_returns_input_when_no_canonical_match_exists(self) -> None:
        repo = _FakeFeatureRepo([
            {
                "id": "another-feature-v2",
                "status": "done",
                "completed_tasks": 10,
                "total_tasks": 10,
                "updated_at": "2026-02-19T16:00:00Z",
            },
        ])

        resolved = await features_router._resolve_feature_alias_id(
            repo,
            "project-1",
            "multi-platform-project-deployments",
        )

        self.assertEqual(resolved, "multi-platform-project-deployments")


if __name__ == "__main__":
    unittest.main()
