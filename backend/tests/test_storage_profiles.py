import unittest
from unittest.mock import patch

from pydantic import ValidationError

from backend.config import (
    resolve_runtime_environment_contract,
    resolve_storage_profile_config,
    validate_runtime_environment_contract,
)
from backend.db.migration_governance import (
    SUPPORTED_STORAGE_COMPOSITIONS,
    build_migration_governance_metadata,
    validate_migration_governance_contract,
)
from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import get_runtime_profile
from backend.runtime.storage_contract import (
    build_storage_profile_validation_matrix,
    get_storage_capability_contract,
    get_runtime_storage_contract,
    resolve_storage_mode,
)
from backend.runtime_ports import build_runtime_metadata


class StorageProfileConfigTests(unittest.TestCase):
    def test_defaults_to_local_profile_for_sqlite(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_DB_BACKEND": "sqlite",
                "CCDASH_DATABASE_URL": "postgresql://ignored.example/ccdash",
            }
        )

        self.assertEqual(profile.profile, "local")
        self.assertEqual(profile.db_backend, "sqlite")
        self.assertTrue(profile.filesystem_source_of_truth)
        self.assertFalse(profile.shared_postgres_enabled)
        self.assertEqual(profile.isolation_mode, "dedicated")

    def test_derives_enterprise_profile_from_postgres_backend(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )

        self.assertEqual(profile.profile, "enterprise")
        self.assertEqual(profile.db_backend, "postgres")
        self.assertFalse(profile.filesystem_source_of_truth)
        self.assertEqual(profile.database_url, "postgresql://db.example/ccdash")

    def test_explicit_local_profile_rejects_postgres_backend(self) -> None:
        with self.assertRaises(ValidationError):
            resolve_storage_profile_config(
                {
                    "CCDASH_STORAGE_PROFILE": "local",
                    "CCDASH_DB_BACKEND": "postgres",
                    "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                }
            )

    def test_local_profile_rejects_non_dedicated_isolation(self) -> None:
        with self.assertRaises(ValidationError):
            resolve_storage_profile_config(
                {
                    "CCDASH_STORAGE_PROFILE": "local",
                    "CCDASH_DB_BACKEND": "sqlite",
                    "CCDASH_STORAGE_ISOLATION_MODE": "tenant",
                }
            )

    def test_dedicated_enterprise_profile_rejects_schema_isolation(self) -> None:
        with self.assertRaises(ValidationError):
            resolve_storage_profile_config(
                {
                    "CCDASH_STORAGE_PROFILE": "enterprise",
                    "CCDASH_DB_BACKEND": "postgres",
                    "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                    "CCDASH_STORAGE_ISOLATION_MODE": "schema",
                }
            )

    def test_shared_postgres_contract_uses_explicit_isolation(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_STORAGE_SHARED_POSTGRES": "true",
                "CCDASH_STORAGE_ISOLATION_MODE": "schema",
                "CCDASH_STORAGE_SCHEMA": "ccdash_app",
                "CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED": "true",
            }
        )

        self.assertEqual(profile.profile, "enterprise")
        self.assertTrue(profile.shared_postgres_enabled)
        self.assertEqual(profile.isolation_mode, "schema")
        self.assertEqual(profile.schema_name, "ccdash_app")
        self.assertTrue(profile.filesystem_source_of_truth)

    def test_shared_postgres_resolves_shared_enterprise_mode(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_STORAGE_SHARED_POSTGRES": "true",
                "CCDASH_STORAGE_ISOLATION_MODE": "tenant",
            }
        )

        contract = get_storage_capability_contract(profile)

        self.assertEqual(resolve_storage_mode(profile), "shared-enterprise")
        self.assertEqual(contract.mode, "shared-enterprise")
        self.assertEqual(contract.supported_isolation_modes, ("schema", "tenant"))

    def test_api_environment_contract_requires_shared_database_url_and_api_secret(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )

        contract = resolve_runtime_environment_contract(
            "api",
            profile,
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_API_BEARER_TOKEN": "secret-token",
            },
        )

        self.assertEqual(contract.deployment_mode, "hosted")
        self.assertTrue(contract.valid)
        self.assertEqual(
            contract.required_variables,
            ("CCDASH_DATABASE_URL", "CCDASH_API_BEARER_TOKEN"),
        )
        self.assertEqual(
            contract.secret_variables,
            ("CCDASH_DATABASE_URL", "CCDASH_API_BEARER_TOKEN"),
        )
        self.assertEqual(contract.shared[2].name, "CCDASH_DATABASE_URL")
        self.assertEqual(contract.shared[2].status, "configured")
        self.assertEqual(contract.api_only[0].status, "configured")

    def test_api_auth_contract_defaults_to_static_bearer_provider(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )

        contract = resolve_runtime_environment_contract(
            "api",
            profile,
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_API_BEARER_TOKEN": "secret-token",
            },
        )

        self.assertTrue(contract.valid)
        self.assertEqual(contract.api_only[0].name, "CCDASH_API_BEARER_TOKEN")
        self.assertEqual(contract.api_only[0].status, "configured")
        self.assertEqual(contract.api_only[1].name, "CCDASH_AUTH_PROVIDER")
        self.assertEqual(contract.api_only[1].status, "default")
        self.assertEqual(contract.required_variables, ("CCDASH_DATABASE_URL", "CCDASH_API_BEARER_TOKEN"))

    def test_api_auth_contract_requires_clerk_provider_secrets(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )

        contract = resolve_runtime_environment_contract(
            "api",
            profile,
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_AUTH_PROVIDER": "clerk",
            },
        )

        self.assertFalse(contract.valid)
        self.assertEqual(
            contract.required_variables,
            (
                "CCDASH_DATABASE_URL",
                "CCDASH_CLERK_PUBLISHABLE_KEY",
                "CCDASH_CLERK_SECRET_KEY",
                "CCDASH_CLERK_JWT_KEY",
            ),
        )
        self.assertEqual(
            contract.secret_variables,
            ("CCDASH_DATABASE_URL", "CCDASH_CLERK_SECRET_KEY", "CCDASH_CLERK_JWT_KEY"),
        )
        self.assertIn(
            "Runtime profile 'api' auth provider 'clerk' requires non-empty environment variables before serving traffic: "
            "CCDASH_CLERK_PUBLISHABLE_KEY, CCDASH_CLERK_SECRET_KEY, CCDASH_CLERK_JWT_KEY.",
            contract.errors,
        )

    def test_api_auth_contract_requires_oidc_provider_settings(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )

        contract = resolve_runtime_environment_contract(
            "api",
            profile,
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_AUTH_PROVIDER": "oidc",
            },
        )

        self.assertFalse(contract.valid)
        self.assertEqual(
            contract.required_variables,
            (
                "CCDASH_DATABASE_URL",
                "CCDASH_OIDC_ISSUER",
                "CCDASH_OIDC_AUDIENCE",
                "CCDASH_OIDC_CLIENT_ID",
                "CCDASH_OIDC_CLIENT_SECRET",
                "CCDASH_OIDC_CALLBACK_URL",
                "CCDASH_OIDC_JWKS_URL",
            ),
        )
        self.assertEqual(contract.secret_variables, ("CCDASH_DATABASE_URL", "CCDASH_OIDC_CLIENT_SECRET"))
        self.assertIn(
            "Runtime profile 'api' auth provider 'oidc' requires non-empty environment variables before serving traffic: "
            "CCDASH_OIDC_ISSUER, CCDASH_OIDC_AUDIENCE, CCDASH_OIDC_CLIENT_ID, CCDASH_OIDC_CLIENT_SECRET, "
            "CCDASH_OIDC_CALLBACK_URL, CCDASH_OIDC_JWKS_URL.",
            contract.errors,
        )

    def test_api_local_no_auth_provider_requires_explicit_enablement(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )

        missing_contract = resolve_runtime_environment_contract(
            "api",
            profile,
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_AUTH_PROVIDER": "local",
            },
        )
        explicit_contract = resolve_runtime_environment_contract(
            "api",
            profile,
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_AUTH_PROVIDER": "local",
                "CCDASH_LOCAL_NO_AUTH_ENABLED": "true",
            },
        )

        self.assertFalse(missing_contract.valid)
        self.assertIn(
            "Runtime profile 'api' auth provider 'local' requires non-empty environment variables before serving traffic: "
            "CCDASH_LOCAL_NO_AUTH_ENABLED.",
            missing_contract.errors,
        )
        self.assertTrue(explicit_contract.valid)
        self.assertEqual(explicit_contract.required_variables, ("CCDASH_DATABASE_URL", "CCDASH_LOCAL_NO_AUTH_ENABLED"))
        self.assertIn(
            "Hosted API is explicitly configured for local no-auth; only use this behind an external trusted authentication boundary.",
            explicit_contract.warnings,
        )

    def test_hosted_environment_contract_rejects_local_database_url_placeholder(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
            }
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Runtime profile 'api' requires an explicit non-placeholder CCDASH_DATABASE_URL before serving hosted traffic.",
        ):
            validate_runtime_environment_contract(
                "api",
                profile,
                {
                    "CCDASH_STORAGE_PROFILE": "enterprise",
                    "CCDASH_DB_BACKEND": "postgres",
                },
            )

    def test_worker_environment_contract_requires_project_binding(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )

        contract = resolve_runtime_environment_contract(
            "worker",
            profile,
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            },
        )

        self.assertFalse(contract.valid)
        self.assertEqual(contract.required_variables, ("CCDASH_DATABASE_URL", "CCDASH_WORKER_PROJECT_ID"))
        self.assertEqual(contract.worker_only[0].name, "CCDASH_WORKER_PROJECT_ID")
        self.assertEqual(contract.worker_only[0].status, "missing")
        self.assertIn(
            "Runtime profile 'worker' requires a non-empty CCDASH_WORKER_PROJECT_ID before starting background jobs.",
            contract.errors,
        )

    def test_worker_watch_environment_contract_requires_project_binding(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED": "true",
            }
        )

        contract = resolve_runtime_environment_contract(
            "worker-watch",
            profile,
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED": "true",
            },
        )

        self.assertFalse(contract.valid)
        self.assertEqual(contract.required_variables, ("CCDASH_DATABASE_URL", "CCDASH_WORKER_PROJECT_ID"))
        self.assertEqual(contract.worker_only[0].name, "CCDASH_WORKER_PROJECT_ID")
        self.assertEqual(contract.worker_only[0].status, "missing")
        self.assertIn(
            "Runtime profile 'worker-watch' requires a non-empty CCDASH_WORKER_PROJECT_ID before starting background jobs.",
            contract.errors,
        )

    def test_capability_matrix_freezes_expected_canonical_stores(self) -> None:
        local_profile = resolve_storage_profile_config({"CCDASH_DB_BACKEND": "sqlite"})
        enterprise_profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )
        shared_profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_STORAGE_SHARED_POSTGRES": "true",
                "CCDASH_STORAGE_ISOLATION_MODE": "schema",
            }
        )

        self.assertEqual(get_storage_capability_contract(local_profile).canonical_store, "sqlite_local_metadata")
        self.assertEqual(get_storage_capability_contract(enterprise_profile).canonical_store, "postgres_dedicated")
        self.assertEqual(get_storage_capability_contract(shared_profile).canonical_store, "postgres_shared_instance")

    def test_capability_matrix_freezes_session_intelligence_rollout_contract(self) -> None:
        local_profile = resolve_storage_profile_config({"CCDASH_DB_BACKEND": "sqlite"})
        enterprise_profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )
        shared_profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_STORAGE_SHARED_POSTGRES": "true",
                "CCDASH_STORAGE_ISOLATION_MODE": "schema",
            }
        )

        local_contract = get_storage_capability_contract(local_profile)
        enterprise_contract = get_storage_capability_contract(enterprise_profile)
        shared_contract = get_storage_capability_contract(shared_profile)

        self.assertEqual(local_contract.session_intelligence_profile, "local_cache")
        self.assertEqual(local_contract.session_intelligence_analytics_level, "limited_optional")
        self.assertEqual(local_contract.session_intelligence_backfill_strategy, "local_rebuild_from_filesystem")
        self.assertEqual(local_contract.session_intelligence_memory_draft_flow, "reviewable_local_drafts")
        self.assertEqual(local_contract.session_intelligence_isolation_boundary, "not_applicable")

        self.assertEqual(enterprise_contract.session_intelligence_profile, "enterprise_canonical")
        self.assertEqual(enterprise_contract.session_intelligence_analytics_level, "full")
        self.assertEqual(
            enterprise_contract.session_intelligence_backfill_strategy,
            "checkpointed_enterprise_backfill",
        )
        self.assertEqual(
            enterprise_contract.session_intelligence_memory_draft_flow,
            "approval_gated_enterprise_publish",
        )
        self.assertEqual(enterprise_contract.session_intelligence_isolation_boundary, "dedicated_instance")

        self.assertEqual(shared_contract.session_intelligence_profile, "enterprise_canonical_shared_boundary")
        self.assertEqual(shared_contract.session_intelligence_analytics_level, "full")
        self.assertEqual(shared_contract.session_intelligence_backfill_strategy, "checkpointed_enterprise_backfill")
        self.assertEqual(
            shared_contract.session_intelligence_memory_draft_flow,
            "approval_gated_enterprise_publish",
        )
        self.assertEqual(shared_contract.session_intelligence_isolation_boundary, "schema_or_tenant_boundary")

    def test_storage_profile_validation_matrix_freezes_supported_capability_differences(self) -> None:
        matrix = {entry["storageMode"]: entry for entry in build_storage_profile_validation_matrix()}

        self.assertSetEqual(set(matrix), {"local", "enterprise", "shared-enterprise"})

        self.assertEqual(matrix["local"]["storageProfile"], "local")
        self.assertEqual(matrix["local"]["storageBackend"], "sqlite")
        self.assertEqual(matrix["local"]["storageComposition"], "local-sqlite")
        self.assertEqual(matrix["local"]["storageFilesystemRole"], "primary_ingestion_and_derived_source")
        self.assertEqual(matrix["local"]["auditWriteStatus"], "unsupported")
        self.assertEqual(matrix["local"]["sessionEmbeddingWriteStatus"], "unsupported")
        self.assertEqual(matrix["local"]["sessionIntelligenceAnalyticsLevel"], "limited_optional")

        self.assertEqual(matrix["enterprise"]["storageProfile"], "enterprise")
        self.assertEqual(matrix["enterprise"]["storageBackend"], "postgres")
        self.assertEqual(matrix["enterprise"]["storageComposition"], "enterprise-postgres")
        self.assertFalse(matrix["enterprise"]["sharedPostgresEnabled"])
        self.assertEqual(matrix["enterprise"]["auditWriteStatus"], "authoritative")
        self.assertEqual(matrix["enterprise"]["sessionEmbeddingWriteStatus"], "authoritative")
        self.assertEqual(matrix["enterprise"]["sessionIntelligenceProfile"], "enterprise_canonical")
        self.assertEqual(matrix["enterprise"]["sessionIntelligenceIsolationBoundary"], "dedicated_instance")

        self.assertEqual(matrix["shared-enterprise"]["storageProfile"], "enterprise")
        self.assertEqual(matrix["shared-enterprise"]["storageBackend"], "postgres")
        self.assertEqual(matrix["shared-enterprise"]["storageComposition"], "shared-enterprise-postgres")
        self.assertTrue(matrix["shared-enterprise"]["sharedPostgresEnabled"])
        self.assertEqual(matrix["shared-enterprise"]["supportedStorageIsolationModes"], ("schema", "tenant"))
        self.assertEqual(
            matrix["shared-enterprise"]["sessionIntelligenceProfile"],
            "enterprise_canonical_shared_boundary",
        )
        self.assertEqual(
            matrix["shared-enterprise"]["sessionIntelligenceIsolationBoundary"],
            "schema_or_tenant_boundary",
        )

    def test_storage_composition_matrix_covers_phase4_profiles(self) -> None:
        validate_migration_governance_contract()
        compositions = {entry.composition: entry for entry in SUPPORTED_STORAGE_COMPOSITIONS}

        self.assertSetEqual(
            set(compositions),
            {"local-sqlite", "enterprise-postgres", "shared-enterprise-postgres"},
        )

        self.assertEqual(compositions["local-sqlite"].storage_mode, "local")
        self.assertEqual(compositions["local-sqlite"].backend, "sqlite")
        self.assertEqual(compositions["local-sqlite"].isolation_modes, ("dedicated",))

        self.assertEqual(compositions["enterprise-postgres"].storage_mode, "enterprise")
        self.assertEqual(compositions["enterprise-postgres"].backend, "postgres")
        self.assertEqual(compositions["enterprise-postgres"].isolation_modes, ("dedicated",))

        self.assertEqual(compositions["shared-enterprise-postgres"].storage_mode, "shared-enterprise")
        self.assertEqual(compositions["shared-enterprise-postgres"].backend, "postgres")
        self.assertEqual(compositions["shared-enterprise-postgres"].isolation_modes, ("schema", "tenant"))

    def test_runtime_probe_contract_metadata_is_stable(self) -> None:
        profile = get_runtime_profile("api")
        storage_profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )

        contract = get_runtime_storage_contract(profile)
        metadata = build_runtime_metadata(profile, storage_profile)

        self.assertEqual(
            contract.readiness_checks,
            (
                "db_connection",
                "storage_pairing",
                "migration_governance",
                "schema_migrations",
                "auth_contract",
            ),
        )
        self.assertEqual(
            metadata["probeCadence"],
            {"liveSeconds": 15, "readySeconds": 20, "detailSeconds": 60},
        )
        self.assertEqual(
            metadata["requiredReadinessChecks"],
            (
                "db_connection",
                "storage_pairing",
                "migration_governance",
                "schema_migrations",
                "auth_contract",
            ),
        )
        self.assertEqual(
            metadata["runtimeCapabilities"],
            {
                "watch": False,
                "sync": False,
                "jobs": False,
                "auth": True,
                "integrations": True,
            },
        )
        self.assertIn("enterprise-postgres", metadata["supportedStorageCompositions"])
        self.assertIn("json_storage", metadata["supportedBackendDifferenceCategories"])

    def test_worker_watch_probe_contract_requires_binding_watcher_and_startup_sync(self) -> None:
        profile = get_runtime_profile("worker-watch")
        storage_profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED": "true",
            }
        )

        contract = get_runtime_storage_contract(profile)
        metadata = build_runtime_metadata(profile, storage_profile)

        self.assertEqual(contract.allowed_storage_profiles, ("enterprise",))
        self.assertEqual(
            contract.readiness_checks,
            (
                "db_connection",
                "storage_pairing",
                "migration_governance",
                "schema_migrations",
                "worker_binding",
                "watcher_runtime",
                "startup_sync",
            ),
        )
        self.assertEqual(metadata["requiredReadinessChecks"], contract.readiness_checks)
        self.assertEqual(
            metadata["runtimeCapabilities"],
            {
                "watch": True,
                "sync": True,
                "jobs": True,
                "auth": False,
                "integrations": True,
            },
        )
        self.assertTrue(metadata["filesystemSourceOfTruth"])

    def test_migration_governance_metadata_reports_supported_probe_dimensions(self) -> None:
        storage_profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_STORAGE_SHARED_POSTGRES": "true",
                "CCDASH_STORAGE_ISOLATION_MODE": "schema",
            }
        )

        metadata = build_migration_governance_metadata(storage_profile)

        self.assertEqual(metadata["storageComposition"], "shared-enterprise-postgres")
        self.assertEqual(metadata["migrationGovernanceStatus"], "verified")
        self.assertIn("local-sqlite", metadata["supportedStorageCompositions"])
        self.assertIn("shared-enterprise-postgres", metadata["supportedStorageCompositions"])
        self.assertIn("postgres_gin_indexes", metadata["supportedBackendDifferenceCategories"])

    def test_runtime_status_marks_optional_local_watcher_gap_as_degraded(self) -> None:
        container = RuntimeContainer(profile=get_runtime_profile("local"))
        container.storage_profile = resolve_storage_profile_config({"CCDASH_DB_BACKEND": "sqlite"})
        container.migration_status = "applied"

        with patch("backend.runtime.container.connection._connection", object()):
            status = container.runtime_status()

        probe = status["probeContract"]

        self.assertEqual(probe["schemaVersion"], "ops-201-v1")
        self.assertEqual(probe["live"]["state"], "live")
        self.assertEqual(probe["ready"]["state"], "degraded")
        self.assertEqual(probe["ready"]["status"], "warn")
        self.assertTrue(probe["ready"]["ready"])
        self.assertTrue(probe["ready"]["degraded"])
        self.assertIn("watcher_runtime", status["degradedReasonCodes"])
        self.assertEqual(
            probe["detail"]["recommendedCadence"],
            {"liveSeconds": 30, "readySeconds": 30, "detailSeconds": 90},
        )
        self.assertEqual(probe["detail"]["runtime"]["profile"], "local")

    def test_worker_runtime_status_marks_missing_binding_as_not_ready(self) -> None:
        container = RuntimeContainer(profile=get_runtime_profile("worker"))
        container.storage_profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )
        container.migration_status = "applied"

        with patch("backend.runtime.container.connection._connection", object()):
            with patch("backend.runtime.container.config.resolve_worker_binding_config") as binding_config:
                binding_config.return_value = type(
                    "BindingConfig",
                    (),
                    {"configured": False, "project_id": ""},
                )()
                status = container.runtime_status()

        probe = status["probeContract"]

        self.assertEqual(probe["ready"]["state"], "not_ready")
        self.assertEqual(probe["ready"]["status"], "fail")
        self.assertFalse(probe["ready"]["ready"])
        self.assertIn("worker_binding", status["degradedReasonCodes"])
        self.assertEqual(probe["detail"]["binding"]["projectId"], None)

    def test_worker_watch_runtime_status_requires_binding_watcher_and_startup_sync(self) -> None:
        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))
        container.storage_profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED": "true",
            }
        )
        container.migration_status = "applied"

        with patch("backend.runtime.container.connection._connection", object()):
            with patch("backend.runtime.container.config.resolve_worker_binding_config") as binding_config:
                binding_config.return_value = type(
                    "BindingConfig",
                    (),
                    {"configured": True, "project_id": "project-1"},
                )()
                status = container.runtime_status()

        checks = {check["code"]: check for check in status["probeContract"]["ready"]["checks"]}

        self.assertEqual(status["probeReadyState"], "not_ready")
        self.assertFalse(status["probeReady"])
        self.assertEqual(checks["worker_binding"]["status"], "fail")
        self.assertTrue(checks["worker_binding"]["required"])
        self.assertEqual(checks["worker_binding"]["data"]["bindingRequired"], True)
        self.assertEqual(checks["watcher_runtime"]["status"], "fail")
        self.assertTrue(checks["watcher_runtime"]["required"])
        self.assertEqual(checks["startup_sync"]["status"], "fail")
        self.assertTrue(checks["startup_sync"]["required"])
        self.assertIn("worker_binding", status["degradedReasonCodes"])
        self.assertIn("watcher_runtime", status["degradedReasonCodes"])
        self.assertIn("startup_sync", status["degradedReasonCodes"])

    def test_worker_watch_startup_binding_requires_project_id(self) -> None:
        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))
        container.storage_profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_ENTERPRISE_FILESYSTEM_INGESTION_ENABLED": "true",
            }
        )

        with patch(
            "backend.runtime.container.config.resolve_worker_binding_config",
            return_value=type("BindingConfig", (), {"configured": False, "project_id": ""})(),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Runtime profile 'worker-watch' requires a non-empty CCDASH_WORKER_PROJECT_ID before starting background jobs.",
            ):
                container._resolve_startup_project_binding()

    def test_worker_status_does_not_require_watcher_runtime_readiness(self) -> None:
        container = RuntimeContainer(profile=get_runtime_profile("worker"))
        container.storage_profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )
        container.migration_status = "applied"
        container.project_binding = type(
            "ProjectBinding",
            (),
            {
                "project": type("Project", (), {"id": "project-1", "name": "Project 1"})(),
                "paths": type("Paths", (), {"root": type("Root", (), {"path": "/tmp/project"})()})(),
                "source": "explicit",
                "requested_project_id": "project-1",
                "locked": True,
            },
        )()

        with patch("backend.runtime.container.connection._connection", object()):
            with patch("backend.runtime.container.config.resolve_worker_binding_config") as binding_config:
                binding_config.return_value = type(
                    "BindingConfig",
                    (),
                    {"configured": True, "project_id": "project-1"},
                )()
                status = container.runtime_status()

        checks = {check["code"]: check for check in status["probeContract"]["ready"]["checks"]}

        self.assertEqual(status["probeReadyState"], "ready")
        self.assertTrue(status["probeReady"])
        self.assertEqual(checks["watcher_runtime"]["status"], "not_applicable")
        self.assertFalse(checks["watcher_runtime"]["required"])
        self.assertEqual(checks["startup_sync"]["status"], "pass")
        self.assertFalse(checks["startup_sync"]["required"])


if __name__ == "__main__":
    unittest.main()
