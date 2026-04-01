import unittest

from backend import config
from backend.verify_db_layer import (
    build_storage_verification_matrix,
    resolve_storage_composition,
    verify_storage_profile_contract,
)


class VerifyDbLayerTests(unittest.TestCase):
    def test_verify_storage_profile_contract_supports_local_sqlite(self) -> None:
        report = verify_storage_profile_contract(
            config.resolve_storage_profile_config({"CCDASH_DB_BACKEND": "sqlite"})
        )

        self.assertEqual(report.composition, "local-sqlite")
        self.assertEqual(report.storage_mode, "local")
        self.assertEqual(report.backend, "sqlite")
        self.assertEqual(report.enterprise_only_table_count, 0)

    def test_verify_storage_profile_contract_supports_dedicated_enterprise_postgres(self) -> None:
        report = verify_storage_profile_contract(
            config.resolve_storage_profile_config(
                {
                    "CCDASH_STORAGE_PROFILE": "enterprise",
                    "CCDASH_DB_BACKEND": "postgres",
                    "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                }
            )
        )

        self.assertEqual(report.composition, "enterprise-postgres")
        self.assertEqual(report.storage_mode, "enterprise")
        self.assertEqual(report.backend, "postgres")
        self.assertGreater(report.enterprise_only_table_count, 0)

    def test_verify_storage_profile_contract_supports_shared_enterprise_postgres(self) -> None:
        report = verify_storage_profile_contract(
            config.resolve_storage_profile_config(
                {
                    "CCDASH_STORAGE_PROFILE": "enterprise",
                    "CCDASH_DB_BACKEND": "postgres",
                    "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                    "CCDASH_STORAGE_SHARED_POSTGRES": "true",
                    "CCDASH_STORAGE_ISOLATION_MODE": "schema",
                    "CCDASH_STORAGE_SCHEMA": "ccdash_app",
                }
            )
        )

        self.assertEqual(report.composition, "shared-enterprise-postgres")
        self.assertEqual(report.storage_mode, "shared-enterprise")
        self.assertTrue(report.shared_postgres_enabled)
        self.assertIn("shared Postgres isolation boundary uses schema 'ccdash_app'", report.checks)

    def test_invalid_shared_postgres_isolation_fails_clearly(self) -> None:
        invalid_profile = config.StorageProfileConfig.model_construct(
            profile="enterprise",
            db_backend="postgres",
            database_url="postgresql://db.example/ccdash",
            filesystem_source_of_truth=False,
            shared_postgres_enabled=True,
            isolation_mode="dedicated",
            schema_name="ccdash_app",
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Storage mode 'shared-enterprise' only supports isolation modes: schema, tenant.",
        ):
            resolve_storage_composition(invalid_profile)

    def test_missing_supported_composition_fails_clearly(self) -> None:
        enterprise_profile = config.resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Resolved storage profile is not part of the supported storage composition matrix.",
        ):
            verify_storage_profile_contract(enterprise_profile, supported_compositions=())

    def test_build_storage_verification_matrix_covers_all_supported_postures(self) -> None:
        matrix = {report.composition: report for report in build_storage_verification_matrix()}

        self.assertSetEqual(
            set(matrix),
            {"local-sqlite", "enterprise-postgres", "shared-enterprise-postgres"},
        )


if __name__ == "__main__":
    unittest.main()
