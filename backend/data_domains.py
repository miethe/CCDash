"""Code-owned ownership matrix for persisted CCDash data concerns.

Phase 1 task DPM-003 freezes the current domain model so follow-on schema and
adapter work can depend on a stable ownership contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal


DataDomain = Literal[
    "workspace_project_metadata",
    "observed_product_entities",
    "ingestion_cache_state",
    "integration_snapshots",
    "operational_job_data",
    "identity_access",
    "audit_security_records",
]

DurabilityClass = Literal["canonical", "mixed", "derived", "refreshable", "operational"]
ConcernKind = Literal["table", "artifact", "placeholder"]


@dataclass(frozen=True)
class PersistedConcernOwnership:
    concern: str
    kind: ConcernKind
    domain: DataDomain
    durability: DurabilityClass
    local_owner: str
    enterprise_owner: str
    notes: str = ""
    current: bool = True
    migration_managed: bool = False


def _entry(
    concern: str,
    *,
    kind: ConcernKind,
    domain: DataDomain,
    durability: DurabilityClass,
    local_owner: str,
    enterprise_owner: str,
    notes: str = "",
    current: bool = True,
    migration_managed: bool = False,
) -> PersistedConcernOwnership:
    return PersistedConcernOwnership(
        concern=concern,
        kind=kind,
        domain=domain,
        durability=durability,
        local_owner=local_owner,
        enterprise_owner=enterprise_owner,
        notes=notes,
        current=current,
        migration_managed=migration_managed,
    )


def _build_matrix() -> dict[str, PersistedConcernOwnership]:
    entries: dict[str, PersistedConcernOwnership] = {}

    def register_many(
        concerns: tuple[str, ...],
        *,
        kind: ConcernKind,
        domain: DataDomain,
        durability: DurabilityClass,
        local_owner: str,
        enterprise_owner: str,
        notes: str = "",
        current: bool = True,
        migration_managed: bool = False,
    ) -> None:
        for concern in concerns:
            entries[concern] = _entry(
                concern,
                kind=kind,
                domain=domain,
                durability=durability,
                local_owner=local_owner,
                enterprise_owner=enterprise_owner,
                notes=notes,
                current=current,
                migration_managed=migration_managed,
            )

    register_many(
        ("projects.json", "workspace_registry_state"),
        kind="artifact",
        domain="workspace_project_metadata",
        durability="canonical",
        local_owner="local filesystem + SQLite app metadata",
        enterprise_owner="enterprise Postgres canonical app metadata",
        notes="Filesystem-backed workspace metadata remains local-first, but the hosted target owner is canonical app metadata.",
    )
    register_many(
        ("app_metadata", "alert_configs"),
        kind="table",
        domain="workspace_project_metadata",
        durability="canonical",
        local_owner="local filesystem + SQLite app metadata",
        enterprise_owner="enterprise Postgres canonical app metadata",
        migration_managed=True,
    )

    register_many(
        (
            "entity_links",
            "external_links",
            "tags",
            "entity_tags",
            "sessions",
            "session_logs",
            "session_messages",
            "session_tool_usage",
            "session_file_updates",
            "session_artifacts",
            "session_usage_events",
            "session_usage_attributions",
            "session_relationships",
            "documents",
            "document_refs",
            "tasks",
            "features",
            "feature_phases",
            "commit_correlations",
        ),
        kind="table",
        domain="observed_product_entities",
        durability="mixed",
        local_owner="SQLite cache + local metadata",
        enterprise_owner="enterprise Postgres canonical or mixed-mode hosted storage",
        migration_managed=True,
    )

    register_many(
        ("sync_state",),
        kind="table",
        domain="ingestion_cache_state",
        durability="derived",
        local_owner="profile-local storage adapter",
        enterprise_owner="profile-local storage adapter",
        notes="Filesystem sync state is adapter-owned rather than canonical shared data.",
        migration_managed=True,
    )

    register_many(
        (
            "external_definition_sources",
            "external_definitions",
            "pricing_catalog_entries",
        ),
        kind="table",
        domain="integration_snapshots",
        durability="refreshable",
        local_owner="SQLite refreshable snapshot cache",
        enterprise_owner="enterprise Postgres refreshable snapshot store",
        migration_managed=True,
    )

    register_many(
        (
            "schema_version",
            "metric_types",
            "analytics_entries",
            "analytics_entity_links",
            "telemetry_events",
            "outbound_telemetry_queue",
            "session_stack_observations",
            "session_stack_components",
            "effectiveness_rollups",
            "execution_runs",
            "execution_run_events",
            "execution_approvals",
            "test_runs",
            "test_definitions",
            "test_results",
            "test_domains",
            "test_feature_mappings",
            "test_integrity_signals",
            "test_metrics",
        ),
        kind="table",
        domain="operational_job_data",
        durability="operational",
        local_owner="local adapter allowed for local mode",
        enterprise_owner="enterprise Postgres preferred for hosted mode",
        migration_managed=True,
    )

    register_many(
        ("principals", "memberships", "role_bindings", "scope_identifiers"),
        kind="placeholder",
        domain="identity_access",
        durability="canonical",
        local_owner="not part of the local-first storage contract",
        enterprise_owner="enterprise Postgres canonical home",
        notes="Planned auth-era tables reserved for future enterprise identity and scope management work.",
        current=False,
    )
    register_many(
        ("privileged_action_audit_records", "access_decision_logs"),
        kind="placeholder",
        domain="audit_security_records",
        durability="canonical",
        local_owner="not part of the local-first storage contract",
        enterprise_owner="enterprise Postgres canonical home",
        notes="Planned audit/security records reserved for future privileged-action and access-decision tracking.",
        current=False,
    )

    return entries


PERSISTED_CONCERN_OWNERSHIP = MappingProxyType(_build_matrix())
MIGRATION_MANAGED_CONCERNS = tuple(
    concern
    for concern, ownership in PERSISTED_CONCERN_OWNERSHIP.items()
    if ownership.migration_managed
)
PLANNED_AUTH_AUDIT_CONCERNS = tuple(
    concern
    for concern, ownership in PERSISTED_CONCERN_OWNERSHIP.items()
    if ownership.kind == "placeholder"
)


def get_persisted_concern_ownership(concern: str) -> PersistedConcernOwnership:
    """Return the frozen ownership record for a persisted concern."""

    return PERSISTED_CONCERN_OWNERSHIP[concern]


def iter_persisted_concern_ownership() -> tuple[PersistedConcernOwnership, ...]:
    """Return the ownership matrix in stable declaration order."""

    return tuple(PERSISTED_CONCERN_OWNERSHIP.values())
