"""Enterprise identity and audit repository seams for Postgres-backed storage."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from uuid import uuid4


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
    async def record_privileged_action(self, record: dict[str, Any]) -> None:
        metadata = record.get("metadata_json") if isinstance(record.get("metadata_json"), dict) else {}
        await self.db.execute(
            """
            INSERT INTO audit.privileged_action_audit_records (
                id, actor_id, scope_id, action, resource_type, resource_id,
                decision, decision_reason, ip_address, user_agent, metadata_json, occurred_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12)
            """,
            str(record.get("id") or uuid4()),
            str(record.get("actor_id") or ""),
            str(record.get("scope_id") or ""),
            str(record.get("action") or ""),
            str(record.get("resource_type") or ""),
            str(record.get("resource_id") or ""),
            str(record.get("decision") or "allowed"),
            str(record.get("decision_reason") or ""),
            str(record.get("ip_address") or ""),
            str(record.get("user_agent") or ""),
            json.dumps(metadata, sort_keys=True),
            str(record.get("occurred_at") or ""),
        )


class PostgresAccessDecisionLogRepository(_PostgresEnterpriseRepository):
    async def record_access_decision(self, record: dict[str, Any]) -> None:
        metadata = record.get("metadata_json") if isinstance(record.get("metadata_json"), dict) else {}
        await self.db.execute(
            """
            INSERT INTO audit.access_decision_logs (
                id, principal_id, scope_id, resource_type, resource_id,
                requested_action, decision, evaluator, matched_binding_id, metadata_json, occurred_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
            """,
            str(record.get("id") or uuid4()),
            str(record.get("principal_id") or ""),
            str(record.get("scope_id") or ""),
            str(record.get("resource_type") or ""),
            str(record.get("resource_id") or ""),
            str(record.get("requested_action") or ""),
            str(record.get("decision") or ""),
            str(record.get("evaluator") or "policy_engine"),
            str(record.get("matched_binding_id") or ""),
            json.dumps(metadata, sort_keys=True),
            str(record.get("occurred_at") or ""),
        )
