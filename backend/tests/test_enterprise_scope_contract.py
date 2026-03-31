import unittest

from backend.enterprise_scope_contract import (
    DIRECT_OWNER_SUBJECT_TYPES,
    SCOPE_CONTRACTS,
    SCOPE_INHERITANCE_RULES,
)


class EnterpriseScopeContractTests(unittest.TestCase):
    def test_scope_contracts_cover_phase4_scope_types(self) -> None:
        self.assertSetEqual(
            set(SCOPE_CONTRACTS),
            {"enterprise", "team", "workspace", "project", "owned_entity"},
        )

    def test_owned_entity_scope_reserves_direct_owner_subjects(self) -> None:
        contract = SCOPE_CONTRACTS["owned_entity"]

        self.assertEqual(contract.ownership_mode, "directly-owned")
        self.assertEqual(DIRECT_OWNER_SUBJECT_TYPES, ("user", "team", "enterprise"))
        self.assertIn("project", contract.parent_scope_types)

    def test_scope_inheritance_rules_freeze_membership_and_audit_behavior(self) -> None:
        self.assertIn("inherit", SCOPE_INHERITANCE_RULES["memberships"])
        self.assertIn("scope-rooted", SCOPE_INHERITANCE_RULES["audit_records"])


if __name__ == "__main__":
    unittest.main()

