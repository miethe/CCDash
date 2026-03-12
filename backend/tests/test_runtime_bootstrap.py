import asyncio
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.runtime.bootstrap_api import build_api_app
from backend.runtime.bootstrap_local import build_local_app
from backend.runtime.bootstrap_test import build_test_app
from backend.runtime.bootstrap_worker import build_worker_runtime
from backend.runtime.profiles import get_runtime_profile, iter_runtime_profiles


class _ResolvedBundle:
    def __init__(self) -> None:
        self.root = types.SimpleNamespace(path=Path("/tmp/project"))
        self._paths = (
            Path("/tmp/sessions"),
            Path("/tmp/project/docs"),
            Path("/tmp/project/progress"),
        )

    def as_tuple(self) -> tuple[Path, Path, Path]:
        return self._paths


def _active_project() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        id="project-1",
        testConfig=types.SimpleNamespace(
            autoSyncOnStartup=False,
            maxFilesPerScan=25,
            maxParseConcurrency=4,
        ),
    )


def _fake_sync_engine() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        sync_project=AsyncMock(return_value={"sessions_synced": 1}),
        sync_test_sources=AsyncMock(return_value={"synced": 0}),
        rebuild_links=AsyncMock(return_value={"created": 0}),
        capture_analytics_snapshot=AsyncMock(return_value={"captured": True}),
    )


class RuntimeProfileTests(unittest.TestCase):
    def test_runtime_profiles_cover_expected_modes(self) -> None:
        profiles = {profile.name: profile for profile in iter_runtime_profiles()}

        self.assertEqual(set(profiles), {"local", "api", "worker", "test"})
        self.assertTrue(profiles["local"].capabilities.watch)
        self.assertFalse(profiles["api"].capabilities.watch)
        self.assertFalse(profiles["test"].capabilities.jobs)
        self.assertTrue(profiles["worker"].capabilities.jobs)

    def test_worker_bootstrap_returns_worker_runtime_container(self) -> None:
        container = build_worker_runtime()

        self.assertEqual(container.profile, get_runtime_profile("worker"))


class RuntimeBootstrapLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_profile_starts_sync_pipeline_and_watcher(self) -> None:
        app = build_local_app()
        project = _active_project()
        bundle = _ResolvedBundle()
        fake_sync = _fake_sync_engine()

        with (
            patch("backend.runtime.container.initialize_observability"),
            patch("backend.runtime.container.shutdown_observability"),
            patch("backend.runtime.container.connection.get_connection", AsyncMock(return_value=object())),
            patch("backend.runtime.container.connection.close_connection", AsyncMock()) as close_connection,
            patch("backend.runtime.container.migrations.run_migrations", AsyncMock()),
            patch("backend.runtime.container.sync_engine.SyncEngine", return_value=fake_sync),
            patch("backend.runtime.container.project_manager.get_active_project", return_value=project),
            patch("backend.runtime.container.project_manager.get_active_path_bundle", return_value=bundle),
            patch("backend.runtime.container.resolve_test_sources", return_value=[]),
            patch("backend.runtime.container.effective_test_flags", return_value=types.SimpleNamespace(testVisualizerEnabled=False)),
            patch("backend.runtime.container.skillmeat_refresh_configured", return_value=False),
            patch("backend.runtime.container.file_watcher.start", AsyncMock()) as watcher_start,
            patch("backend.runtime.container.file_watcher.stop", AsyncMock()) as watcher_stop,
            patch("backend.runtime.container.config.STARTUP_SYNC_DELAY_SECONDS", 0),
            patch("backend.runtime.container.config.STARTUP_SYNC_LIGHT_MODE", True),
            patch("backend.runtime.container.config.STARTUP_DEFERRED_REBUILD_LINKS", False),
            patch("backend.runtime.container.config.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS", 0),
        ):
            async with app.router.lifespan_context(app):
                await asyncio.sleep(0)
                self.assertEqual(app.state.runtime_profile, get_runtime_profile("local"))
                self.assertIs(app.state.sync_engine, fake_sync)
                self.assertTrue(hasattr(app.state, "sync_task"))
                watcher_start.assert_awaited_once()
                fake_sync.sync_project.assert_awaited_once()

            watcher_stop.assert_awaited_once()
            close_connection.assert_awaited_once()

    async def test_api_profile_skips_incidental_background_startup(self) -> None:
        app = build_api_app()
        project = _active_project()
        bundle = _ResolvedBundle()
        fake_sync = _fake_sync_engine()

        with (
            patch("backend.runtime.container.initialize_observability"),
            patch("backend.runtime.container.shutdown_observability"),
            patch("backend.runtime.container.connection.get_connection", AsyncMock(return_value=object())),
            patch("backend.runtime.container.connection.close_connection", AsyncMock()) as close_connection,
            patch("backend.runtime.container.migrations.run_migrations", AsyncMock()),
            patch("backend.runtime.container.sync_engine.SyncEngine", return_value=fake_sync),
            patch("backend.runtime.container.project_manager.get_active_project", return_value=project),
            patch("backend.runtime.container.project_manager.get_active_path_bundle", return_value=bundle),
            patch("backend.runtime.container.resolve_test_sources", return_value=[]),
            patch("backend.runtime.container.effective_test_flags", return_value=types.SimpleNamespace(testVisualizerEnabled=False)),
            patch("backend.runtime.container.file_watcher.start", AsyncMock()) as watcher_start,
            patch("backend.runtime.container.file_watcher.stop", AsyncMock()) as watcher_stop,
            patch("backend.runtime.container.config.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS", 0),
        ):
            async with app.router.lifespan_context(app):
                await asyncio.sleep(0)
                self.assertEqual(app.state.runtime_profile, get_runtime_profile("api"))
                self.assertIs(app.state.sync_engine, fake_sync)
                self.assertFalse(hasattr(app.state, "sync_task"))
                watcher_start.assert_not_awaited()
                fake_sync.sync_project.assert_not_awaited()

            watcher_stop.assert_not_awaited()
            close_connection.assert_awaited_once()

    async def test_test_profile_disables_background_work_by_default(self) -> None:
        app = build_test_app()
        fake_sync = _fake_sync_engine()

        with (
            patch("backend.runtime.container.initialize_observability"),
            patch("backend.runtime.container.shutdown_observability"),
            patch("backend.runtime.container.connection.get_connection", AsyncMock(return_value=object())),
            patch("backend.runtime.container.connection.close_connection", AsyncMock()) as close_connection,
            patch("backend.runtime.container.migrations.run_migrations", AsyncMock()),
            patch("backend.runtime.container.sync_engine.SyncEngine", return_value=fake_sync),
            patch("backend.runtime.container.project_manager.get_active_project", return_value=None),
            patch("backend.runtime.container.file_watcher.start", AsyncMock()) as watcher_start,
            patch("backend.runtime.container.file_watcher.stop", AsyncMock()) as watcher_stop,
            patch("backend.runtime.container.config.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS", 0),
        ):
            async with app.router.lifespan_context(app):
                await asyncio.sleep(0)
                self.assertEqual(app.state.runtime_profile, get_runtime_profile("test"))
                self.assertFalse(hasattr(app.state, "sync_task"))
                self.assertFalse(hasattr(app.state, "analytics_snapshot_task"))
                watcher_start.assert_not_awaited()

            watcher_stop.assert_not_awaited()
            close_connection.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
