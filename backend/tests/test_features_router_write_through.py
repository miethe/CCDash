import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.routers import features as features_router


def _make_request(sync_engine=None, *, runtime_profile="local"):
    return types.SimpleNamespace(
        app=types.SimpleNamespace(
            state=types.SimpleNamespace(sync_engine=sync_engine, runtime_profile=runtime_profile)
        )
    )


class _FakeFeatureRepository:
    async def get_phases(self, feature_id: str) -> list[dict]:
        _ = feature_id
        return []


class FeatureRouterWriteThroughTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmpdir.name)
        self.docs_dir = self.project_root / "docs"
        self.progress_dir = self.project_root / ".claude" / "progress"
        self.sessions_dir = self.project_root / "sessions"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.progress_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.feature_file = self.docs_dir / "feature-a-v1.md"
        self.feature_file.write_text("---\nstatus: draft\n---\n# Feature A\n", encoding="utf-8")
        self.project = types.SimpleNamespace(id="project-1")

    async def asyncTearDown(self) -> None:
        self.tmpdir.cleanup()

    async def test_update_feature_status_syncs_when_engine_present(self) -> None:
        sync_engine = AsyncMock()
        repo = _FakeFeatureRepository()

        with (
            patch.object(features_router.project_manager, "get_active_project", return_value=self.project),
            patch.object(features_router.project_manager, "get_active_paths", return_value=(self.sessions_dir, self.docs_dir, self.progress_dir)),
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature_repository", return_value=repo),
            patch.object(features_router, "_resolve_feature_alias_id", return_value="feature-a-v1"),
            patch.object(features_router, "resolve_file_for_feature", return_value=self.feature_file),
            patch.object(features_router, "publish_feature_invalidation", AsyncMock()) as publish_mock,
            patch.object(features_router, "get_feature", AsyncMock(return_value={"id": "feature-a-v1", "status": "in-progress"})) as get_feature_mock,
        ):
            response = await features_router.update_feature_status(
                "feature-a-v1",
                features_router.StatusUpdateRequest(status="in-progress"),
                _make_request(sync_engine, runtime_profile="local"),
            )

        self.assertEqual(response["status"], "in-progress")
        self.assertIn("status: in-progress", self.feature_file.read_text(encoding="utf-8"))
        sync_engine.sync_changed_files.assert_awaited_once()
        publish_mock.assert_awaited_once()
        get_feature_mock.assert_awaited_once_with("feature-a-v1")

    async def test_update_feature_status_rejects_when_sync_engine_missing(self) -> None:
        repo = _FakeFeatureRepository()

        with (
            patch.object(features_router.project_manager, "get_active_project", return_value=self.project),
            patch.object(features_router.project_manager, "get_active_paths", return_value=(self.sessions_dir, self.docs_dir, self.progress_dir)),
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature_repository", return_value=repo),
            patch.object(features_router, "_resolve_feature_alias_id", return_value="feature-a-v1"),
            patch.object(features_router, "resolve_file_for_feature", return_value=self.feature_file),
            patch.object(features_router, "publish_feature_invalidation", AsyncMock()) as publish_mock,
            patch.object(features_router, "get_feature", AsyncMock()) as get_feature_mock,
        ):
            with self.assertRaises(HTTPException) as exc:
                await features_router.update_feature_status(
                    "feature-a-v1",
                    features_router.StatusUpdateRequest(status="in-progress"),
                    _make_request(None, runtime_profile="api"),
                )

        self.assertEqual(exc.exception.status_code, 503)
        self.assertIn("sync_engine is unavailable", str(exc.exception.detail))
        self.assertIn("status: draft", self.feature_file.read_text(encoding="utf-8"))
        publish_mock.assert_not_awaited()
        get_feature_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
