import asyncio
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from backend import config
from backend.db.migration_governance import SUPPORTED_STORAGE_COMPOSITIONS
from backend.runtime.bootstrap_api import build_api_app
from backend.runtime.bootstrap_local import build_local_app
from backend.runtime.bootstrap_test import build_test_app
from backend.runtime.bootstrap_worker import build_worker_runtime
from backend.runtime.profiles import get_runtime_profile, iter_runtime_profiles
from backend.runtime.storage_contract import get_runtime_storage_contract, resolve_storage_mode
from backend.runtime_ports import build_core_ports
from backend.worker import serve_worker


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


def _enterprise_storage_profile(*, shared: bool = False) -> config.StorageProfileConfig:
    return config.StorageProfileConfig(
        profile="enterprise",
        db_backend="postgres",
        database_url="postgresql://example/test",
        filesystem_source_of_truth=False,
        shared_postgres_enabled=shared,
        isolation_mode="schema" if shared else "dedicated",
        schema_name="ccdash_app" if shared else "ccdash",
    )


def _local_storage_profile() -> config.StorageProfileConfig:
    return config.StorageProfileConfig(
        profile="local",
        db_backend="sqlite",
        database_url="",
        filesystem_source_of_truth=True,
        shared_postgres_enabled=False,
        isolation_mode="dedicated",
        schema_name="ccdash",
    )


def _health_payload(app: object) -> dict[str, object]:
    health_route = next(route for route in app.routes if getattr(route, "path", None) == "/api/health")
    return health_route.endpoint(types.SimpleNamespace(), None)


class RuntimeProfileTests(unittest.TestCase):
    def test_runtime_profiles_cover_expected_modes(self) -> None:
        profiles = {profile.name: profile for profile in iter_runtime_profiles()}

        self.assertEqual(set(profiles), {"local", "api", "worker", "test"})
        self.assertTrue(profiles["local"].capabilities.watch)
        self.assertFalse(profiles["api"].capabilities.watch)
        self.assertFalse(profiles["test"].capabilities.jobs)
        self.assertTrue(profiles["worker"].capabilities.jobs)
        self.assertTrue(profiles["worker"].capabilities.sync)
        self.assertEqual(profiles["local"].recommended_storage_profile, "local")
        self.assertEqual(profiles["api"].recommended_storage_profile, "enterprise")
        self.assertEqual(profiles["worker"].recommended_storage_profile, "enterprise")

    def test_worker_bootstrap_returns_worker_runtime_container(self) -> None:
        container = build_worker_runtime()

        self.assertEqual(container.profile, get_runtime_profile("worker"))

    def test_runtime_to_storage_mapping_is_explicit(self) -> None:
        mappings = {
            profile.name: get_runtime_storage_contract(profile).allowed_storage_profiles
            for profile in iter_runtime_profiles()
        }

        self.assertEqual(
            mappings,
            {
                "local": ("local",),
                "api": ("enterprise",),
                "worker": ("enterprise",),
                "test": ("local", "enterprise"),
            },
        )

    def test_storage_profile_contract_requires_postgres_for_enterprise(self) -> None:
        with self.assertRaises(ValidationError):
            config.StorageProfileConfig(
                profile="enterprise",
                db_backend="sqlite",
                database_url="",
                filesystem_source_of_truth=False,
                shared_postgres_enabled=False,
                isolation_mode="dedicated",
                schema_name="ccdash",
            )

    def test_storage_profile_contract_requires_isolation_for_shared_postgres(self) -> None:
        with self.assertRaises(ValidationError):
            config.StorageProfileConfig(
                profile="enterprise",
                db_backend="postgres",
                database_url="postgresql://example/test",
                filesystem_source_of_truth=False,
                shared_postgres_enabled=True,
                isolation_mode="dedicated",
                schema_name="ccdash",
            )

    def test_runtime_container_status_exposes_storage_contract(self) -> None:
        container = build_api_app().state.runtime_container
        container.storage_profile = _enterprise_storage_profile()

        status = container.runtime_status()

        self.assertEqual(status["profile"], "api")
        self.assertEqual(status["recommendedStorageProfile"], "enterprise")
        self.assertEqual(status["allowedStorageProfiles"], ("enterprise",))
        self.assertEqual(status["supportedStorageProfiles"], ("enterprise",))
        self.assertEqual(status["storageMode"], "enterprise")
        self.assertEqual(status["storageProfile"], "enterprise")
        self.assertEqual(status["storageBackend"], "postgres")
        self.assertEqual(status["storageCanonicalStore"], "postgres_dedicated")
        self.assertIn("storageMode", status)
        self.assertIn("storageProfile", status)
        self.assertIn("storageBackend", status)
        self.assertIn("storageCanonicalStore", status)
        self.assertIn("filesystemSourceOfTruth", status)
        self.assertIn("storageFilesystemRole", status)
        self.assertIn("sharedPostgresEnabled", status)
        self.assertIn("storageIsolationMode", status)
        self.assertIn("supportedStorageIsolationModes", status)
        self.assertIn("storageSchema", status)
        self.assertIn("canonicalSessionStore", status)
        self.assertIn("requiredStorageGuarantees", status)
        self.assertEqual(status["canonicalSessionStore"], "postgres")

    def test_api_runtime_rejects_local_storage_profile(self) -> None:
        local_profile = config.StorageProfileConfig(
            profile="local",
            db_backend="sqlite",
            database_url="",
            filesystem_source_of_truth=True,
            shared_postgres_enabled=False,
            isolation_mode="dedicated",
            schema_name="ccdash",
        )

        with self.assertRaisesRegex(RuntimeError, "Runtime profile 'api' only supports storage profiles: enterprise"):
            build_core_ports(object(), runtime_profile=get_runtime_profile("api"), storage_profile=local_profile)

    def test_worker_runtime_rejects_local_storage_profile(self) -> None:
        local_profile = config.StorageProfileConfig(
            profile="local",
            db_backend="sqlite",
            database_url="",
            filesystem_source_of_truth=True,
            shared_postgres_enabled=False,
            isolation_mode="dedicated",
            schema_name="ccdash",
        )

        with self.assertRaisesRegex(RuntimeError, "Runtime profile 'worker' only supports storage profiles: enterprise"):
            build_core_ports(object(), runtime_profile=get_runtime_profile("worker"), storage_profile=local_profile)

    def test_test_runtime_allows_shared_enterprise_storage_profile(self) -> None:
        shared_enterprise = config.StorageProfileConfig(
            profile="enterprise",
            db_backend="postgres",
            database_url="postgresql://example/test",
            filesystem_source_of_truth=False,
            shared_postgres_enabled=True,
            isolation_mode="schema",
            schema_name="ccdash_app",
        )

        ports = build_core_ports(
            object(),
            runtime_profile=get_runtime_profile("test"),
            storage_profile=shared_enterprise,
        )

        self.assertEqual(resolve_storage_mode(shared_enterprise), "shared-enterprise")
        self.assertIsNotNone(ports.storage)

    def test_health_endpoint_reports_local_sqlite_composition(self) -> None:
        app = build_local_app()
        app.state.runtime_container.storage_profile = _local_storage_profile()

        payload = _health_payload(app)

        self.assertEqual(payload["profile"], "local")
        self.assertEqual(payload["storageMode"], "local")
        self.assertEqual(payload["storageProfile"], "local")
        self.assertEqual(payload["storageBackend"], "sqlite")
        self.assertEqual(payload["storageCanonicalStore"], "sqlite_local_metadata")
        self.assertFalse(payload["sharedPostgresEnabled"])
        self.assertIn("local-sqlite", payload["supportedStorageCompositions"])
        self.assertIsInstance(payload["requiredStorageGuarantees"], list)

    def test_health_endpoint_reports_enterprise_postgres_composition(self) -> None:
        app = build_api_app()
        app.state.runtime_container.storage_profile = _enterprise_storage_profile()

        payload = _health_payload(app)

        self.assertEqual(payload["profile"], "api")
        self.assertEqual(payload["storageMode"], "enterprise")
        self.assertEqual(payload["storageProfile"], "enterprise")
        self.assertEqual(payload["storageBackend"], "postgres")
        self.assertEqual(payload["storageCanonicalStore"], "postgres_dedicated")
        self.assertEqual(payload["storageIsolationMode"], "dedicated")
        self.assertFalse(payload["sharedPostgresEnabled"])
        self.assertIn("enterprise-postgres", payload["supportedStorageCompositions"])
        self.assertEqual(payload["supportedStorageProfiles"], ["enterprise"])

    def test_health_endpoint_reports_shared_enterprise_postgres_composition(self) -> None:
        app = build_api_app()
        app.state.runtime_container.storage_profile = _enterprise_storage_profile(shared=True)

        payload = _health_payload(app)

        self.assertEqual(payload["storageMode"], "shared-enterprise")
        self.assertEqual(payload["storageProfile"], "enterprise")
        self.assertEqual(payload["storageBackend"], "postgres")
        self.assertEqual(payload["storageCanonicalStore"], "postgres_shared_instance")
        self.assertTrue(payload["sharedPostgresEnabled"])
        self.assertEqual(payload["storageIsolationMode"], "schema")
        self.assertEqual(payload["supportedStorageIsolationModes"], ["schema", "tenant"])
        self.assertIn("shared-enterprise-postgres", payload["supportedStorageCompositions"])

    def test_health_endpoint_storage_composition_matrix_matches_governance(self) -> None:
        app = build_test_app()
        payload = _health_payload(app)
        reported = set(payload["supportedStorageCompositions"])
        expected = {entry.composition for entry in SUPPORTED_STORAGE_COMPOSITIONS}
        self.assertSetEqual(reported, expected)


class RuntimeBootstrapLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_profile_rejects_local_storage_before_opening_db(self) -> None:
        local_profile = config.StorageProfileConfig(
            profile="local",
            db_backend="sqlite",
            database_url="",
            filesystem_source_of_truth=True,
            shared_postgres_enabled=False,
            isolation_mode="dedicated",
            schema_name="ccdash",
        )

        with patch("backend.runtime.container.config.STORAGE_PROFILE", local_profile):
            app = build_api_app()

        with (
            patch("backend.runtime.container.initialize_observability") as initialize_observability,
            patch("backend.runtime.container.connection.get_connection", AsyncMock()) as get_connection,
        ):
            with self.assertRaisesRegex(RuntimeError, "Runtime profile 'api' only supports storage profiles: enterprise"):
                async with app.router.lifespan_context(app):
                    await asyncio.sleep(0)

        initialize_observability.assert_not_called()
        get_connection.assert_not_awaited()

    async def test_worker_profile_rejects_local_storage_before_opening_db(self) -> None:
        local_profile = config.StorageProfileConfig(
            profile="local",
            db_backend="sqlite",
            database_url="",
            filesystem_source_of_truth=True,
            shared_postgres_enabled=False,
            isolation_mode="dedicated",
            schema_name="ccdash",
        )

        with patch("backend.runtime.container.config.STORAGE_PROFILE", local_profile):
            container = build_worker_runtime()

        with (
            patch("backend.runtime.container.initialize_observability") as initialize_observability,
            patch("backend.runtime.container.connection.get_connection", AsyncMock()) as get_connection,
        ):
            with self.assertRaisesRegex(RuntimeError, "Runtime profile 'worker' only supports storage profiles: enterprise"):
                await serve_worker(container=container, stop_event=asyncio.Event())

        initialize_observability.assert_not_called()
        get_connection.assert_not_awaited()

    async def test_local_profile_starts_sync_pipeline_and_watcher(self) -> None:
        app = build_local_app()
        app.state.runtime_container.storage_profile = _local_storage_profile()
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
            patch("backend.adapters.jobs.runtime.resolve_test_sources", return_value=[]),
            patch("backend.adapters.jobs.runtime.effective_test_flags", return_value=types.SimpleNamespace(testVisualizerEnabled=False)),
            patch("backend.adapters.jobs.runtime.skillmeat_refresh_configured", return_value=False),
            patch("backend.adapters.jobs.runtime.file_watcher.start", AsyncMock()) as watcher_start,
            patch("backend.adapters.jobs.runtime.file_watcher.stop", AsyncMock()) as watcher_stop,
            patch("backend.adapters.jobs.runtime.config.STARTUP_SYNC_DELAY_SECONDS", 0),
            patch("backend.adapters.jobs.runtime.config.STARTUP_SYNC_LIGHT_MODE", True),
            patch("backend.adapters.jobs.runtime.config.STARTUP_DEFERRED_REBUILD_LINKS", False),
            patch("backend.adapters.jobs.runtime.config.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS", 0),
            patch("backend.runtime_ports.project_manager.get_active_project", return_value=project),
            patch("backend.runtime_ports.project_manager.get_active_path_bundle", return_value=bundle),
        ):
            async with app.router.lifespan_context(app):
                await asyncio.sleep(0)
                self.assertEqual(app.state.runtime_profile, get_runtime_profile("local"))
                self.assertIs(app.state.sync_engine, fake_sync)
                self.assertIsNotNone(app.state.live_event_broker)
                self.assertIsNotNone(app.state.live_event_publisher)
                self.assertTrue(hasattr(app.state, "sync_task"))
                watcher_start.assert_awaited_once()
                fake_sync.sync_project.assert_awaited_once()

            watcher_stop.assert_awaited_once()
            close_connection.assert_awaited_once()

    async def test_api_profile_skips_incidental_background_startup(self) -> None:
        app = build_api_app()
        app.state.runtime_container.storage_profile = _enterprise_storage_profile()
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
            patch("backend.adapters.jobs.runtime.resolve_test_sources", return_value=[]),
            patch("backend.adapters.jobs.runtime.effective_test_flags", return_value=types.SimpleNamespace(testVisualizerEnabled=False)),
            patch("backend.adapters.jobs.runtime.file_watcher.start", AsyncMock()) as watcher_start,
            patch("backend.adapters.jobs.runtime.file_watcher.stop", AsyncMock()) as watcher_stop,
            patch("backend.adapters.jobs.runtime.config.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS", 0),
            patch("backend.runtime_ports.project_manager.get_active_project", return_value=project),
            patch("backend.runtime_ports.project_manager.get_active_path_bundle", return_value=bundle),
        ):
            async with app.router.lifespan_context(app):
                await asyncio.sleep(0)
                self.assertEqual(app.state.runtime_profile, get_runtime_profile("api"))
                self.assertIs(app.state.sync_engine, fake_sync)
                self.assertIsNotNone(app.state.live_event_broker)
                self.assertIsNotNone(app.state.live_event_publisher)
                self.assertFalse(hasattr(app.state, "sync_task"))
                watcher_start.assert_not_awaited()
                fake_sync.sync_project.assert_not_awaited()

            watcher_stop.assert_not_awaited()
            close_connection.assert_awaited_once()

    async def test_test_profile_disables_background_work_by_default(self) -> None:
        app = build_test_app()
        app.state.runtime_container.storage_profile = _local_storage_profile()
        fake_sync = _fake_sync_engine()

        with (
            patch("backend.runtime.container.initialize_observability"),
            patch("backend.runtime.container.shutdown_observability"),
            patch("backend.runtime.container.connection.get_connection", AsyncMock(return_value=object())),
            patch("backend.runtime.container.connection.close_connection", AsyncMock()) as close_connection,
            patch("backend.runtime.container.migrations.run_migrations", AsyncMock()),
            patch("backend.runtime.container.sync_engine.SyncEngine", return_value=fake_sync),
            patch("backend.adapters.jobs.runtime.file_watcher.start", AsyncMock()) as watcher_start,
            patch("backend.adapters.jobs.runtime.file_watcher.stop", AsyncMock()) as watcher_stop,
            patch("backend.adapters.jobs.runtime.config.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS", 0),
            patch("backend.runtime_ports.project_manager.get_active_project", return_value=None),
        ):
            async with app.router.lifespan_context(app):
                await asyncio.sleep(0)
                self.assertEqual(app.state.runtime_profile, get_runtime_profile("test"))
                self.assertIsNotNone(app.state.live_event_broker)
                self.assertIsNotNone(app.state.live_event_publisher)
                self.assertFalse(hasattr(app.state, "sync_task"))
                self.assertFalse(hasattr(app.state, "analytics_snapshot_task"))
                watcher_start.assert_not_awaited()

            watcher_stop.assert_not_awaited()
            close_connection.assert_awaited_once()

    async def test_worker_process_starts_without_http_server(self) -> None:
        project = _active_project()
        bundle = _ResolvedBundle()
        fake_sync = _fake_sync_engine()
        stop_event = asyncio.Event()
        container = build_worker_runtime()
        container.storage_profile = _enterprise_storage_profile()

        with (
            patch("backend.runtime.container.initialize_observability"),
            patch("backend.runtime.container.shutdown_observability"),
            patch("backend.runtime.container.connection.get_connection", AsyncMock(return_value=object())),
            patch("backend.runtime.container.connection.close_connection", AsyncMock()) as close_connection,
            patch("backend.runtime.container.migrations.run_migrations", AsyncMock()),
            patch("backend.runtime.container.sync_engine.SyncEngine", return_value=fake_sync),
            patch("backend.adapters.jobs.runtime.resolve_test_sources", return_value=[]),
            patch("backend.adapters.jobs.runtime.effective_test_flags", return_value=types.SimpleNamespace(testVisualizerEnabled=False)),
            patch("backend.adapters.jobs.runtime.skillmeat_refresh_configured", return_value=False),
            patch("backend.adapters.jobs.runtime.file_watcher.start", AsyncMock()) as watcher_start,
            patch("backend.adapters.jobs.runtime.file_watcher.stop", AsyncMock()) as watcher_stop,
            patch("backend.adapters.jobs.runtime.config.STARTUP_SYNC_DELAY_SECONDS", 0),
            patch("backend.adapters.jobs.runtime.config.STARTUP_SYNC_LIGHT_MODE", True),
            patch("backend.adapters.jobs.runtime.config.STARTUP_DEFERRED_REBUILD_LINKS", False),
            patch("backend.adapters.jobs.runtime.config.ANALYTICS_SNAPSHOT_INTERVAL_SECONDS", 0),
            patch("backend.runtime_ports.project_manager.get_active_project", return_value=project),
            patch("backend.runtime_ports.project_manager.get_active_path_bundle", return_value=bundle),
        ):
            task = asyncio.create_task(serve_worker(container=container, stop_event=stop_event))
            await asyncio.sleep(0.05)
            self.assertTrue(fake_sync.sync_project.await_count >= 1)
            watcher_start.assert_not_awaited()
            stop_event.set()
            await task

        watcher_stop.assert_not_awaited()
        close_connection.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
