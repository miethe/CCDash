import re
import unittest
from pathlib import Path

from backend.data_domains import (
    MIGRATION_MANAGED_CONCERNS,
    PLANNED_AUTH_AUDIT_CONCERNS,
    PERSISTED_CONCERN_OWNERSHIP,
)
from backend.db.migration_governance import (
    get_enterprise_only_postgres_tables,
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

    def test_every_concern_has_supported_ownership_posture(self) -> None:
        valid_postures = {
            "scope-owned",
            "directly-ownable",
            "inherits-parent-ownership",
        }
        directly_ownable = {
            "alert_configs",
            "sessions",
            "documents",
            "tasks",
            "features",
        }

        for concern, ownership in PERSISTED_CONCERN_OWNERSHIP.items():
            self.assertIn(ownership.ownership_posture, valid_postures)
            if ownership.ownership_posture == "directly-ownable":
                self.assertEqual(ownership.direct_owner_subject_types, ("user", "team", "enterprise"))
                self.assertIn(concern, directly_ownable)
            else:
                self.assertEqual(ownership.direct_owner_subject_types, ())

    def test_migration_governance_contract_stays_valid(self) -> None:
        validate_migration_governance_contract()

        sqlite_tables = _migration_tables("backend/db/sqlite_migrations.py")
        postgres_tables = _migration_tables("backend/db/postgres_migrations.py")
        enterprise_only = get_enterprise_only_postgres_tables()
        difference_matrix = get_table_backend_difference_matrix()

        # Shared tables match across backends.
        self.assertSetEqual(sqlite_tables, postgres_tables - enterprise_only)
        # Difference matrix classifies every shared table.
        self.assertSetEqual(set(difference_matrix), sqlite_tables)

    def test_enterprise_postgres_tables_equal_shared_plus_planned(self) -> None:
        """Postgres migration tables = shared SQLite tables + planned enterprise concerns."""
        sqlite_tables = _migration_tables("backend/db/sqlite_migrations.py")
        postgres_tables = _migration_tables("backend/db/postgres_migrations.py")
        self.assertSetEqual(postgres_tables, sqlite_tables | set(PLANNED_AUTH_AUDIT_CONCERNS))

    def test_current_migration_tables_are_all_classified(self) -> None:
        sqlite_tables = _migration_tables("backend/db/sqlite_migrations.py")
        classified_tables = set(MIGRATION_MANAGED_CONCERNS)
        directly_ownable = {
            "alert_configs",
            "sessions",
            "documents",
            "tasks",
            "features",
        }

        self.assertSetEqual(classified_tables, sqlite_tables)

        for concern in classified_tables:
            ownership = PERSISTED_CONCERN_OWNERSHIP[concern]
            self.assertEqual(ownership.kind, "table")
            self.assertTrue(ownership.current)
            self.assertTrue(ownership.domain)
            self.assertTrue(ownership.durability)
            self.assertTrue(ownership.local_owner)
            self.assertTrue(ownership.enterprise_owner)
            self.assertTrue(ownership.ownership_posture)
            if concern in directly_ownable:
                self.assertEqual(ownership.ownership_posture, "directly-ownable")
            else:
                self.assertNotEqual(ownership.ownership_posture, "directly-ownable")

    def test_future_auth_and_audit_placeholders_are_frozen(self) -> None:
        expected_domains = {
            "principals": ("identity_access", "scope-owned"),
            "memberships": ("identity_access", "inherits-parent-ownership"),
            "role_bindings": ("identity_access", "inherits-parent-ownership"),
            "scope_identifiers": ("identity_access", "scope-owned"),
            "privileged_action_audit_records": ("audit_security_records", "scope-owned"),
            "access_decision_logs": ("audit_security_records", "scope-owned"),
        }

        self.assertSetEqual(set(PLANNED_AUTH_AUDIT_CONCERNS), set(expected_domains))

        for concern, (expected_domain, expected_posture) in expected_domains.items():
            ownership = PERSISTED_CONCERN_OWNERSHIP[concern]
            self.assertEqual(ownership.kind, "placeholder")
            self.assertFalse(ownership.current)
            self.assertEqual(ownership.domain, expected_domain)
            self.assertEqual(ownership.durability, "canonical")
            self.assertEqual(ownership.local_owner, "not part of the local-first storage contract")
            self.assertEqual(ownership.enterprise_owner, "enterprise Postgres canonical home")
            self.assertEqual(ownership.ownership_posture, expected_posture)
            self.assertEqual(ownership.direct_owner_subject_types, ())

    def test_enterprise_only_tables_have_no_direct_ownership_columns(self) -> None:
        """Identity/audit tables must not reserve direct ownership columns (per Phase 4 spec)."""
        enterprise_only = get_enterprise_only_postgres_tables()
        for concern in enterprise_only:
            ownership = PERSISTED_CONCERN_OWNERSHIP[concern]
            self.assertEqual(
                ownership.direct_owner_subject_types,
                (),
                f"Enterprise-only table '{concern}' must not have direct ownership subjects",
            )
            self.assertNotEqual(
                ownership.ownership_posture,
                "directly-ownable",
                f"Enterprise-only table '{concern}' must not be directly-ownable",
            )


if __name__ == "__main__":
    unittest.main()
