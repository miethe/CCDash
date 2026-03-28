import unittest

from backend.config import resolve_storage_profile_config
from backend.runtime.storage_contract import get_storage_capability_contract, resolve_storage_mode


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


if __name__ == "__main__":
    unittest.main()
