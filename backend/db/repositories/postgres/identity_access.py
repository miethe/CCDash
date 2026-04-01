"""Enterprise identity and audit repository seams for Postgres-backed storage."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class StorageCapabilityDescriptor:
    supported: bool
    authoritative: bool
    storage_profile: str
    notes: str


class _PostgresEnterpriseRepository:
    def __init__(self, db: Any) -> None:
        self.db = db

    def describe_capability(self) -> StorageCapabilityDescriptor:
        return StorageCapabilityDescriptor(
            supported=True,
            authoritative=True,
            storage_profile="enterprise",
            notes=(
                "Enterprise Postgres is the canonical home for identity, scope, membership, "
                "role binding, and audit storage."
            ),
        )


class PostgresPrincipalRepository(_PostgresEnterpriseRepository):
    pass


class PostgresScopeIdentifierRepository(_PostgresEnterpriseRepository):
    pass


class PostgresMembershipRepository(_PostgresEnterpriseRepository):
    pass


class PostgresRoleBindingRepository(_PostgresEnterpriseRepository):
    pass


class PostgresPrivilegedActionAuditRepository(_PostgresEnterpriseRepository):
    pass


class PostgresAccessDecisionLogRepository(_PostgresEnterpriseRepository):
    pass
