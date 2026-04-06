import unittest

from pydantic import ValidationError

from backend.config import resolve_storage_profile_config
from backend.db.migration_governance import SUPPORTED_STORAGE_COMPOSITIONS, validate_migration_governance_contract
from backend.runtime.storage_contract import (
    build_storage_profile_validation_matrix,
    get_storage_capability_contract,
    resolve_storage_mode,
)


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


if __name__ == "__main__":
    unittest.main()
