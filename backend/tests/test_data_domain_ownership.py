import re
import unittest
from pathlib import Path

from backend.data_domains import (
    MIGRATION_MANAGED_CONCERNS,
    PLANNED_AUTH_AUDIT_CONCERNS,
    PERSISTED_CONCERN_OWNERSHIP,
)
from backend.db.migration_governance import (
    get_table_backend_difference_matrix,
    validate_migration_governance_contract,
)


_CREATE_TABLE_RE = re.compile(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)")
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _migration_tables(relative_path: str) -> set[str]:
    text = (_REPO_ROOT / relative_path).read_text()
    return set(_CREATE_TABLE_RE.findall(text))


class DataDomainOwnershipTests(unittest.TestCase):
    maxDiff = None

    def test_migration_governance_contract_stays_valid(self) -> None:
        validate_migration_governance_contract()

        sqlite_tables = _migration_tables("backend/db/sqlite_migrations.py")
        postgres_tables = _migration_tables("backend/db/postgres_migrations.py")
        difference_matrix = get_table_backend_difference_matrix()

        self.assertSetEqual(sqlite_tables, postgres_tables)
        self.assertSetEqual(set(difference_matrix), sqlite_tables)

    def test_current_migration_tables_are_all_classified(self) -> None:
        sqlite_tables = _migration_tables("backend/db/sqlite_migrations.py")
        classified_tables = set(MIGRATION_MANAGED_CONCERNS)

        self.assertSetEqual(classified_tables, sqlite_tables)

        for concern in classified_tables:
            ownership = PERSISTED_CONCERN_OWNERSHIP[concern]
            self.assertEqual(ownership.kind, "table")
            self.assertTrue(ownership.current)
            self.assertTrue(ownership.domain)
            self.assertTrue(ownership.durability)
            self.assertTrue(ownership.local_owner)
            self.assertTrue(ownership.enterprise_owner)

    def test_future_auth_and_audit_placeholders_are_frozen(self) -> None:
        expected_domains = {
            "principals": "identity_access",
            "memberships": "identity_access",
            "role_bindings": "identity_access",
            "scope_identifiers": "identity_access",
            "privileged_action_audit_records": "audit_security_records",
            "access_decision_logs": "audit_security_records",
        }

        self.assertSetEqual(set(PLANNED_AUTH_AUDIT_CONCERNS), set(expected_domains))

        for concern, expected_domain in expected_domains.items():
            ownership = PERSISTED_CONCERN_OWNERSHIP[concern]
            self.assertEqual(ownership.kind, "placeholder")
            self.assertFalse(ownership.current)
            self.assertEqual(ownership.domain, expected_domain)
            self.assertEqual(ownership.durability, "canonical")
            self.assertEqual(ownership.local_owner, "not part of the local-first storage contract")
            self.assertEqual(ownership.enterprise_owner, "enterprise Postgres canonical home")


if __name__ == "__main__":
    unittest.main()
