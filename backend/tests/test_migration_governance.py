import unittest

from backend.data_domains import PLANNED_AUTH_AUDIT_CONCERNS
from backend.db.migration_governance import (
    BACKEND_SCHEMA_CAPABILITIES,
    SUPPORTED_BACKEND_DIFFERENCE_CATEGORIES,
    SUPPORTED_STORAGE_COMPOSITIONS,
    get_enterprise_only_postgres_table_schemas,
    get_enterprise_only_postgres_tables,
    get_postgres_migration_tables,
    resolve_storage_composition_contract,
    get_sqlite_migration_tables,
    get_table_backend_difference_matrix,
    validate_migration_governance_contract,
)
from backend.config import resolve_storage_profile_config


class MigrationGovernanceTests(unittest.TestCase):
    def test_validate_migration_governance_contract(self) -> None:
        validate_migration_governance_contract()

    def test_shared_migration_tables_match_across_backends(self) -> None:
        """Shared tables (excluding enterprise-only) must be identical in SQLite and Postgres."""
        enterprise_only = get_enterprise_only_postgres_tables()
        shared_postgres = get_postgres_migration_tables() - enterprise_only
        self.assertSetEqual(get_sqlite_migration_tables(), shared_postgres)

    def test_enterprise_only_tables_exist_only_in_postgres(self) -> None:
        enterprise_only = get_enterprise_only_postgres_tables()
        sqlite_tables = get_sqlite_migration_tables()
        self.assertTrue(enterprise_only, "Enterprise-only table set should not be empty")
        self.assertSetEqual(enterprise_only & sqlite_tables, set())

    def test_enterprise_only_tables_match_planned_concerns(self) -> None:
        enterprise_only = get_enterprise_only_postgres_tables()
        self.assertSetEqual(enterprise_only, set(PLANNED_AUTH_AUDIT_CONCERNS))

    def test_enterprise_only_tables_are_in_expected_schemas(self) -> None:
        schema_map = get_enterprise_only_postgres_table_schemas()
        expected = {
            "principals": "identity",
            "scope_identifiers": "identity",
            "memberships": "identity",
            "role_bindings": "identity",
            "privileged_action_audit_records": "audit",
            "access_decision_logs": "audit",
        }
        self.assertEqual(schema_map, expected)

    def test_postgres_tables_are_superset_of_sqlite(self) -> None:
        sqlite_tables = get_sqlite_migration_tables()
        postgres_tables = get_postgres_migration_tables()
        self.assertTrue(sqlite_tables.issubset(postgres_tables))
        self.assertGreater(len(postgres_tables), len(sqlite_tables))

    def test_table_difference_matrix_classifies_shared_tables(self) -> None:
        """Difference matrix covers shared tables only (not enterprise-only)."""
        matrix = get_table_backend_difference_matrix()
        self.assertSetEqual(set(matrix), set(get_sqlite_migration_tables()))

        for categories in matrix.values():
            self.assertSetEqual(
                set(categories) - set(SUPPORTED_BACKEND_DIFFERENCE_CATEGORIES),
                set(),
            )

    def test_json_storage_differences_are_explicit(self) -> None:
        matrix = get_table_backend_difference_matrix()
        self.assertIn("json_storage", matrix["external_definition_sources"])
        self.assertIn("json_storage", matrix["external_definitions"])
        self.assertIn("json_storage", matrix["execution_runs"])

    def test_supported_storage_compositions_cover_phase4_matrix(self) -> None:
        compositions = {entry.composition: entry for entry in SUPPORTED_STORAGE_COMPOSITIONS}
        self.assertSetEqual(
            set(compositions),
            {"local-sqlite", "enterprise-postgres", "shared-enterprise-postgres"},
        )

        self.assertEqual(compositions["local-sqlite"].backend, "sqlite")
        self.assertEqual(compositions["enterprise-postgres"].backend, "postgres")
        self.assertEqual(compositions["shared-enterprise-postgres"].backend, "postgres")
        self.assertEqual(compositions["shared-enterprise-postgres"].isolation_modes, ("schema", "tenant"))

    def test_backend_capabilities_matrix_is_explicit(self) -> None:
        self.assertSetEqual(set(BACKEND_SCHEMA_CAPABILITIES), {"sqlite", "postgres"})
        self.assertFalse(BACKEND_SCHEMA_CAPABILITIES["sqlite"].supports_gin_indexes)
        self.assertTrue(BACKEND_SCHEMA_CAPABILITIES["postgres"].supports_gin_indexes)

    def test_storage_composition_resolver_matches_shared_enterprise_posture(self) -> None:
        profile = resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_STORAGE_SHARED_POSTGRES": "true",
                "CCDASH_STORAGE_ISOLATION_MODE": "schema",
                "CCDASH_STORAGE_SCHEMA": "ccdash_app",
            }
        )

        composition = resolve_storage_composition_contract(profile)

        self.assertEqual(composition.composition, "shared-enterprise-postgres")


if __name__ == "__main__":
    unittest.main()
