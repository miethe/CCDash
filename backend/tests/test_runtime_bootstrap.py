import asyncio
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from backend.adapters.auth import LocalIdentityProvider, StaticBearerTokenIdentityProvider
from backend.adapters.storage import EnterpriseStorageUnitOfWork, LocalStorageUnitOfWork
from backend import config
from backend.db.migration_governance import SUPPORTED_STORAGE_COMPOSITIONS
from backend.db.repositories.identity_access import LocalPrincipalRepository
from backend.db.repositories.postgres.identity_access import PostgresPrincipalRepository
from backend.runtime.bootstrap_api import build_api_app
from backend.runtime.bootstrap_local import build_local_app
from backend.runtime.bootstrap_test import build_test_app
from backend.runtime.bootstrap_worker import build_worker_runtime
from backend.runtime.profiles import get_runtime_profile, iter_runtime_profiles
from backend.runtime.storage_contract import (
    build_storage_profile_validation_matrix,
    get_runtime_storage_contract,
    resolve_storage_mode,
)
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


def _expected_health_validation_matrix() -> list[dict[str, object]]:
    return [
        {
            **entry,
            "supportedStorageIsolationModes": list(entry["supportedStorageIsolationModes"]),
            "requiredStorageGuarantees": list(entry["requiredStorageGuarantees"]),
        }
        for entry in build_storage_profile_validation_matrix()
    ]


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
        self.assertIn("storageComposition", status)
        self.assertIn("storageCanonicalStore", status)
        self.assertIn("auditStore", status)
        self.assertIn("auditWriteSupported", status)
        self.assertIn("auditWriteAuthoritative", status)
        self.assertIn("auditWriteStatus", status)
        self.assertIn("auditWriteNotes", status)
        self.assertIn("sessionEmbeddingWriteSupported", status)
        self.assertIn("sessionEmbeddingWriteAuthoritative", status)
        self.assertIn("sessionEmbeddingWriteStatus", status)
        self.assertIn("sessionEmbeddingWriteNotes", status)
        self.assertIn("sessionIntelligenceProfile", status)
        self.assertIn("sessionIntelligenceAnalyticsLevel", status)
        self.assertIn("sessionIntelligenceBackfillStrategy", status)
        self.assertIn("sessionIntelligenceMemoryDraftFlow", status)
        self.assertIn("sessionIntelligenceIsolationBoundary", status)
        self.assertIn("filesystemSourceOfTruth", status)
        self.assertIn("storageFilesystemRole", status)
        self.assertIn("sharedPostgresEnabled", status)
        self.assertIn("storageIsolationMode", status)
        self.assertIn("supportedStorageIsolationModes", status)
        self.assertIn("storageSchema", status)
        self.assertIn("canonicalSessionStore", status)
        self.assertIn("requiredStorageGuarantees", status)
        self.assertIn("storageProfileValidationMatrix", status)
        self.assertIn("migrationGovernanceStatus", status)
        self.assertIn("migrationStatus", status)
        self.assertIn("syncProvisioned", status)
        self.assertEqual(status["storageComposition"], "enterprise-postgres")
        self.assertEqual(status["auditStore"], "postgres_phase_4_foundation")
        self.assertTrue(status["auditWriteSupported"])
        self.assertTrue(status["auditWriteAuthoritative"])
        self.assertEqual(status["auditWriteStatus"], "authoritative")
        self.assertTrue(status["sessionEmbeddingWriteSupported"])
        self.assertTrue(status["sessionEmbeddingWriteAuthoritative"])
        self.assertEqual(status["sessionEmbeddingWriteStatus"], "authoritative")
        self.assertEqual(status["sessionIntelligenceProfile"], "enterprise_canonical")
        self.assertEqual(status["sessionIntelligenceAnalyticsLevel"], "full")
        self.assertEqual(status["sessionIntelligenceBackfillStrategy"], "checkpointed_enterprise_backfill")
        self.assertEqual(status["sessionIntelligenceMemoryDraftFlow"], "approval_gated_enterprise_publish")
        self.assertEqual(status["sessionIntelligenceIsolationBoundary"], "dedicated_instance")
        self.assertEqual(status["storageFilesystemRole"], "optional_ingestion_adapter_only")
        self.assertEqual(status["storageProfileValidationMatrix"], build_storage_profile_validation_matrix())
        self.assertEqual(status["migrationGovernanceStatus"], "verified")
        self.assertEqual(status["migrationStatus"], "not_started")
        self.assertFalse(status["syncProvisioned"])
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
        self.assertIsInstance(ports.storage, EnterpriseStorageUnitOfWork)

    def test_build_core_ports_uses_local_storage_adapter(self) -> None:
        marker = object()

        ports = build_core_ports(
            marker,
            runtime_profile=get_runtime_profile("local"),
            storage_profile=_local_storage_profile(),
        )

        self.assertIsInstance(ports.storage, LocalStorageUnitOfWork)
        self.assertIsInstance(ports.identity_provider, LocalIdentityProvider)
        self.assertIs(ports.storage.db, marker)
        self.assertIsInstance(ports.storage.identity_access().principals(), LocalPrincipalRepository)
        self.assertFalse(ports.storage.principals().describe_capability().supported)

    def test_build_core_ports_uses_enterprise_storage_adapter(self) -> None:
        marker = object()

        ports = build_core_ports(
            marker,
            runtime_profile=get_runtime_profile("api"),
            storage_profile=_enterprise_storage_profile(),
        )

        self.assertIsInstance(ports.storage, EnterpriseStorageUnitOfWork)
        self.assertIsInstance(ports.identity_provider, StaticBearerTokenIdentityProvider)
        self.assertIsInstance(ports.storage.identity_access().principals(), PostgresPrincipalRepository)
        self.assertTrue(ports.storage.principals().describe_capability().supported)
        self.assertTrue(ports.storage.audit_security().privileged_action_audit_records().describe_capability().authoritative)
        self.assertIs(ports.storage.db, marker)

    def test_health_endpoint_reports_local_sqlite_composition(self) -> None:
        app = build_local_app()
        app.state.runtime_container.storage_profile = _local_storage_profile()

        payload = _health_payload(app)

        self.assertEqual(payload["profile"], "local")
        self.assertEqual(payload["storageMode"], "local")
        self.assertEqual(payload["storageProfile"], "local")
        self.assertEqual(payload["storageBackend"], "sqlite")
        self.assertEqual(payload["storageComposition"], "local-sqlite")
        self.assertEqual(payload["storageCanonicalStore"], "sqlite_local_metadata")
        self.assertEqual(payload["auditStore"], "not_supported_in_v1_local_mode")
        self.assertFalse(payload["auditWriteSupported"])
        self.assertFalse(payload["auditWriteAuthoritative"])
        self.assertEqual(payload["auditWriteStatus"], "unsupported")
        self.assertFalse(payload["sessionEmbeddingWriteSupported"])
        self.assertFalse(payload["sessionEmbeddingWriteAuthoritative"])
        self.assertEqual(payload["sessionEmbeddingWriteStatus"], "unsupported")
        self.assertEqual(payload["sessionIntelligenceProfile"], "local_cache")
        self.assertEqual(payload["sessionIntelligenceAnalyticsLevel"], "limited_optional")
        self.assertEqual(payload["sessionIntelligenceBackfillStrategy"], "local_rebuild_from_filesystem")
        self.assertEqual(payload["sessionIntelligenceMemoryDraftFlow"], "reviewable_local_drafts")
        self.assertEqual(payload["sessionIntelligenceIsolationBoundary"], "not_applicable")
        self.assertEqual(payload["storageFilesystemRole"], "primary_ingestion_and_derived_source")
        self.assertFalse(payload["sharedPostgresEnabled"])
        self.assertEqual(payload["migrationGovernanceStatus"], "verified")
        self.assertEqual(payload["migrationStatus"], "not_started")
        self.assertIn("local-sqlite", payload["supportedStorageCompositions"])
        self.assertIsInstance(payload["requiredStorageGuarantees"], list)
        self.assertFalse(payload["syncProvisioned"])

    def test_health_endpoint_reports_enterprise_postgres_composition(self) -> None:
        app = build_api_app()
        app.state.runtime_container.storage_profile = _enterprise_storage_profile()

        payload = _health_payload(app)

        self.assertEqual(payload["profile"], "api")
        self.assertEqual(payload["storageMode"], "enterprise")
        self.assertEqual(payload["storageProfile"], "enterprise")
        self.assertEqual(payload["storageBackend"], "postgres")
        self.assertEqual(payload["storageComposition"], "enterprise-postgres")
        self.assertEqual(payload["storageCanonicalStore"], "postgres_dedicated")
        self.assertEqual(payload["auditStore"], "postgres_phase_4_foundation")
        self.assertTrue(payload["auditWriteSupported"])
        self.assertTrue(payload["auditWriteAuthoritative"])
        self.assertEqual(payload["auditWriteStatus"], "authoritative")
        self.assertTrue(payload["sessionEmbeddingWriteSupported"])
        self.assertTrue(payload["sessionEmbeddingWriteAuthoritative"])
        self.assertEqual(payload["sessionEmbeddingWriteStatus"], "authoritative")
        self.assertEqual(payload["sessionIntelligenceProfile"], "enterprise_canonical")
        self.assertEqual(payload["sessionIntelligenceAnalyticsLevel"], "full")
        self.assertEqual(payload["sessionIntelligenceBackfillStrategy"], "checkpointed_enterprise_backfill")
        self.assertEqual(payload["sessionIntelligenceMemoryDraftFlow"], "approval_gated_enterprise_publish")
        self.assertEqual(payload["sessionIntelligenceIsolationBoundary"], "dedicated_instance")
        self.assertEqual(payload["storageFilesystemRole"], "optional_ingestion_adapter_only")
        self.assertEqual(payload["storageIsolationMode"], "dedicated")
        self.assertFalse(payload["sharedPostgresEnabled"])
        self.assertEqual(payload["migrationGovernanceStatus"], "verified")
        self.assertEqual(payload["migrationStatus"], "not_started")
        self.assertIn("enterprise-postgres", payload["supportedStorageCompositions"])
        self.assertEqual(payload["supportedStorageProfiles"], ["enterprise"])
        self.assertFalse(payload["syncProvisioned"])

    def test_health_endpoint_reports_shared_enterprise_postgres_composition(self) -> None:
        app = build_api_app()
        app.state.runtime_container.storage_profile = _enterprise_storage_profile(shared=True)

        payload = _health_payload(app)

        self.assertEqual(payload["storageMode"], "shared-enterprise")
        self.assertEqual(payload["storageProfile"], "enterprise")
        self.assertEqual(payload["storageBackend"], "postgres")
        self.assertEqual(payload["storageComposition"], "shared-enterprise-postgres")
        self.assertEqual(payload["storageCanonicalStore"], "postgres_shared_instance")
        self.assertEqual(payload["auditStore"], "postgres_schema_or_tenant_boundary_phase_4_foundation")
        self.assertTrue(payload["auditWriteSupported"])
        self.assertTrue(payload["auditWriteAuthoritative"])
        self.assertEqual(payload["auditWriteStatus"], "authoritative")
        self.assertTrue(payload["sessionEmbeddingWriteSupported"])
        self.assertTrue(payload["sessionEmbeddingWriteAuthoritative"])
        self.assertEqual(payload["sessionEmbeddingWriteStatus"], "authoritative")
        self.assertEqual(payload["sessionIntelligenceProfile"], "enterprise_canonical_shared_boundary")
        self.assertEqual(payload["sessionIntelligenceAnalyticsLevel"], "full")
        self.assertEqual(payload["sessionIntelligenceBackfillStrategy"], "checkpointed_enterprise_backfill")
        self.assertEqual(payload["sessionIntelligenceMemoryDraftFlow"], "approval_gated_enterprise_publish")
        self.assertEqual(payload["sessionIntelligenceIsolationBoundary"], "schema_or_tenant_boundary")
        self.assertEqual(payload["storageFilesystemRole"], "optional_ingestion_adapter_only")
        self.assertTrue(payload["sharedPostgresEnabled"])
        self.assertEqual(payload["storageIsolationMode"], "schema")
        self.assertEqual(payload["supportedStorageIsolationModes"], ["schema", "tenant"])
        self.assertEqual(payload["migrationGovernanceStatus"], "verified")
        self.assertEqual(payload["migrationStatus"], "not_started")
        self.assertIn("shared-enterprise-postgres", payload["supportedStorageCompositions"])

    def test_health_endpoint_storage_composition_matrix_matches_governance(self) -> None:
        app = build_test_app()
        payload = _health_payload(app)
        reported = set(payload["supportedStorageCompositions"])
        expected = {entry.composition for entry in SUPPORTED_STORAGE_COMPOSITIONS}
        self.assertSetEqual(reported, expected)

    def test_health_endpoint_exposes_storage_profile_validation_matrix(self) -> None:
        app = build_test_app()

        payload = _health_payload(app)

        self.assertEqual(payload["storageProfileValidationMatrix"], _expected_health_validation_matrix())


class StorageAdapterCompositionTests(unittest.TestCase):
    """DPM-101 / DPM-102 — Adapter composition and unit-of-work split.

    Verify that:
    - ``LocalStorageUnitOfWork`` and ``EnterpriseStorageUnitOfWork`` are the
      explicit profile-aware adapters used by the composition root.
    - ``FactoryStorageUnitOfWork`` is a backward-compat alias (subclass of
      ``LocalStorageUnitOfWork``) and is *not* returned by the composition root.
    - Both adapters satisfy the ``StorageUnitOfWork`` port protocol so that
      consumers programmed to the interface work with either adapter.
    - No connection-type inspection is required in the composition path: the
      adapter is chosen from the storage profile, not from the connection type.
    """

    def test_factory_adapter_is_backward_compat_alias_for_local_adapter(self) -> None:
        """FactoryStorageUnitOfWork inherits LocalStorageUnitOfWork so existing
        consumers and tests that import it directly continue to work as-is.
        """
        from backend.adapters.storage.local import FactoryStorageUnitOfWork

        self.assertTrue(issubclass(FactoryStorageUnitOfWork, LocalStorageUnitOfWork))

    def test_composition_root_returns_exact_local_type_not_factory_alias(self) -> None:
        """build_core_ports returns a plain LocalStorageUnitOfWork instance — not
        the FactoryStorageUnitOfWork alias — confirming the factory is no longer
        the architectural control point for storage selection.
        """
        from backend.adapters.storage.local import FactoryStorageUnitOfWork

        ports = build_core_ports(
            object(),
            runtime_profile=get_runtime_profile("test"),
            storage_profile=_local_storage_profile(),
        )

        self.assertIs(type(ports.storage), LocalStorageUnitOfWork)
        self.assertIsNot(type(ports.storage), FactoryStorageUnitOfWork)

    def test_enterprise_adapter_is_not_derived_from_factory_compat_bridge(self) -> None:
        """EnterpriseStorageUnitOfWork is independent of the factory compat bridge.
        The FactoryStorageUnitOfWork alias exists only for local-mode call sites.
        """
        from backend.adapters.storage.local import FactoryStorageUnitOfWork

        self.assertFalse(issubclass(EnterpriseStorageUnitOfWork, FactoryStorageUnitOfWork))

    def test_local_adapter_satisfies_storage_unit_of_work_protocol(self) -> None:
        """LocalStorageUnitOfWork satisfies the StorageUnitOfWork port protocol so
        that routers and services using the port interface require no change.
        """
        from backend.application.ports import StorageUnitOfWork

        adapter = LocalStorageUnitOfWork(object())

        self.assertIsInstance(adapter, StorageUnitOfWork)

    def test_enterprise_adapter_satisfies_storage_unit_of_work_protocol(self) -> None:
        """EnterpriseStorageUnitOfWork satisfies the StorageUnitOfWork port protocol."""
        from backend.application.ports import StorageUnitOfWork

        adapter = EnterpriseStorageUnitOfWork(object())

        self.assertIsInstance(adapter, StorageUnitOfWork)

    def test_local_adapter_db_attribute_is_connection_passed_at_construction(self) -> None:
        """The composition root passes the resolved DB connection directly to the
        adapter constructor; the adapter's .db property must return the same object.
        This verifies the composition path requires no connection-type inspection.
        """
        sentinel = object()

        adapter = LocalStorageUnitOfWork(sentinel)

        self.assertIs(adapter.db, sentinel)

    def test_enterprise_adapter_db_attribute_is_connection_passed_at_construction(self) -> None:
        sentinel = object()

        adapter = EnterpriseStorageUnitOfWork(sentinel)

        self.assertIs(adapter.db, sentinel)


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
                self.assertEqual(app.state.runtime_container.runtime_status()["migrationStatus"], "applied")
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
                self.assertEqual(app.state.runtime_container.runtime_status()["migrationStatus"], "applied")
                self.assertIsNotNone(app.state.live_event_broker)
                self.assertIsNotNone(app.state.live_event_publisher)
                self.assertFalse(hasattr(app.state, "sync_engine"))
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
                self.assertFalse(hasattr(app.state, "sync_engine"))
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
        container.storage_profile = config.resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://example/test",
                "CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED": "true",
            }
        )

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
