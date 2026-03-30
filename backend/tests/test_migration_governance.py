import unittest

from backend.db.migration_governance import (
    BACKEND_SCHEMA_CAPABILITIES,
    SUPPORTED_BACKEND_DIFFERENCE_CATEGORIES,
    SUPPORTED_STORAGE_COMPOSITIONS,
    get_postgres_migration_tables,
    get_sqlite_migration_tables,
    get_table_backend_difference_matrix,
    validate_migration_governance_contract,
)


class MigrationGovernanceTests(unittest.TestCase):
    def test_validate_migration_governance_contract(self) -> None:
        validate_migration_governance_contract()

    def test_migration_tables_match_across_supported_backends(self) -> None:
        self.assertSetEqual(get_sqlite_migration_tables(), get_postgres_migration_tables())

    def test_table_difference_matrix_classifies_all_tables(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
