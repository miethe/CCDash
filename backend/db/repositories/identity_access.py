"""Local compatibility repositories for enterprise-only identity and audit domains."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class StorageCapabilityDescriptor:
    supported: bool
    authoritative: bool
    storage_profile: str
    notes: str


class _LocalEnterpriseOnlyRepository:
    def __init__(self, db: Any) -> None:
        self.db = db

    def describe_capability(self) -> StorageCapabilityDescriptor:
        return StorageCapabilityDescriptor(
            supported=False,
            authoritative=False,
            storage_profile="local",
            notes=(
                "Local SQLite remains a bounded compatibility profile. Enterprise identity "
                "and audit data do not have a local authoritative store."
            ),
        )


class LocalPrincipalRepository(_LocalEnterpriseOnlyRepository):
    pass


class LocalScopeIdentifierRepository(_LocalEnterpriseOnlyRepository):
    pass


class LocalMembershipRepository(_LocalEnterpriseOnlyRepository):
    pass


class LocalRoleBindingRepository(_LocalEnterpriseOnlyRepository):
    pass


class LocalPrivilegedActionAuditRepository(_LocalEnterpriseOnlyRepository):
    async def record_privileged_action(self, _record: dict[str, Any]) -> None:
        """No-op in local mode; enterprise audit storage is not authoritative here."""
        return None


class LocalAccessDecisionLogRepository(_LocalEnterpriseOnlyRepository):
    async def record_access_decision(self, _record: dict[str, Any]) -> None:
        """No-op in local mode; enterprise audit storage is not authoritative here."""
        return None
