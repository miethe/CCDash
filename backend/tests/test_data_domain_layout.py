import unittest

from backend.adapters.storage.enterprise import EnterpriseStorageUnitOfWork
from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.data_domain_layout import REPOSITORY_OWNERSHIP, SCHEMA_BOUNDARIES
from backend.data_domains import MIGRATION_MANAGED_CONCERNS, PLANNED_AUTH_AUDIT_CONCERNS


class DataDomainLayoutTests(unittest.TestCase):
    def test_schema_boundaries_cover_current_and_planned_table_sets(self) -> None:
        current_tables: set[str] = set()
        planned_tables: set[str] = set()

        for boundary in SCHEMA_BOUNDARIES.values():
            current_tables.update(boundary.current_tables)
            planned_tables.update(boundary.planned_tables)
            self.assertTrue(boundary.postgres_schema)
            self.assertTrue(boundary.sqlite_group)

        self.assertSetEqual(current_tables, set(MIGRATION_MANAGED_CONCERNS))
        self.assertSetEqual(planned_tables, set(PLANNED_AUTH_AUDIT_CONCERNS))

    def test_repository_ownership_matches_storage_unit_of_work_keys(self) -> None:
        local = LocalStorageUnitOfWork(object())
        enterprise = EnterpriseStorageUnitOfWork(object())
        expected_keys = set(REPOSITORY_OWNERSHIP)

        self.assertSetEqual(set(local._repo_builders), expected_keys)
        self.assertSetEqual(set(enterprise._repo_builders), expected_keys)

    def test_repository_ownership_points_at_domain_specific_modules(self) -> None:
        for ownership in REPOSITORY_OWNERSHIP.values():
            self.assertIn(ownership.boundary, SCHEMA_BOUNDARIES)
            self.assertTrue(ownership.concerns)
            self.assertIn("backend.db.repositories", ownership.sqlite_module)
            self.assertIn("backend.db.repositories.postgres", ownership.postgres_module)


if __name__ == "__main__":
    unittest.main()
