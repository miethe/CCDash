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
OwnershipPosture = Literal["scope-owned", "directly-ownable", "inherits-parent-ownership"]
OwnerSubjectType = Literal["user", "team", "enterprise"]


@dataclass(frozen=True)
class PersistedConcernOwnership:
    concern: str
    kind: ConcernKind
    domain: DataDomain
    durability: DurabilityClass
    local_owner: str
    enterprise_owner: str
    ownership_posture: OwnershipPosture
    direct_owner_subject_types: tuple[OwnerSubjectType, ...] = ()
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
    ownership_posture: OwnershipPosture,
    direct_owner_subject_types: tuple[OwnerSubjectType, ...] = (),
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
        ownership_posture=ownership_posture,
        direct_owner_subject_types=direct_owner_subject_types,
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
        ownership_posture: OwnershipPosture,
        direct_owner_subject_types: tuple[OwnerSubjectType, ...] = (),
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
                ownership_posture=ownership_posture,
                direct_owner_subject_types=direct_owner_subject_types,
                notes=notes,
                current=current,
                migration_managed=migration_managed,
            )

    directly_ownable_subjects: tuple[OwnerSubjectType, ...] = ("user", "team", "enterprise")

    register_many(
        ("projects.json", "workspace_registry_state"),
        kind="artifact",
        domain="workspace_project_metadata",
        durability="canonical",
        local_owner="local filesystem + SQLite app metadata",
        enterprise_owner="enterprise Postgres canonical app metadata",
        ownership_posture="scope-owned",
        notes="Filesystem-backed workspace metadata remains local-first, but the hosted target owner is canonical app metadata.",
    )
    register_many(
        ("app_metadata",),
        kind="table",
        domain="workspace_project_metadata",
        durability="canonical",
        local_owner="local filesystem + SQLite app metadata",
        enterprise_owner="enterprise Postgres canonical app metadata",
        ownership_posture="scope-owned",
        migration_managed=True,
    )
    register_many(
        ("alert_configs",),
        kind="table",
        domain="workspace_project_metadata",
        durability="canonical",
        local_owner="local filesystem + SQLite app metadata",
        enterprise_owner="enterprise Postgres canonical app metadata",
        ownership_posture="directly-ownable",
        direct_owner_subject_types=directly_ownable_subjects,
        notes="Alert configs may later support direct user, team, or enterprise ownership for shareable notification policies.",
        migration_managed=True,
    )

    register_many(
        ("sessions", "documents", "tasks", "features"),
        kind="table",
        domain="observed_product_entities",
        durability="mixed",
        local_owner="SQLite cache + local metadata",
        enterprise_owner="enterprise Postgres canonical or mixed-mode hosted storage",
        ownership_posture="directly-ownable",
        direct_owner_subject_types=directly_ownable_subjects,
        notes="These canonical entity roots may later support direct user, team, or enterprise ownership in hosted mode.",
        migration_managed=True,
    )
    register_many(
        ("tags",),
        kind="table",
        domain="observed_product_entities",
        durability="mixed",
        local_owner="SQLite cache + local metadata",
        enterprise_owner="enterprise Postgres canonical or mixed-mode hosted storage",
        ownership_posture="scope-owned",
        notes="Tags remain scope-owned taxonomy rows unless a later plan proves they must become independently ownable.",
        migration_managed=True,
    )
    register_many(
        (
            "entity_links",
            "external_links",
            "entity_tags",
            "session_logs",
            "session_messages",
            "session_sentiment_facts",
            "session_code_churn_facts",
            "session_scope_drift_facts",
            "session_tool_usage",
            "session_file_updates",
            "session_artifacts",
            "session_usage_events",
            "session_usage_attributions",
            "session_relationships",
            "document_refs",
            "feature_phases",
            "commit_correlations",
        ),
        kind="table",
        domain="observed_product_entities",
        durability="mixed",
        local_owner="SQLite cache + local metadata",
        enterprise_owner="enterprise Postgres canonical or mixed-mode hosted storage",
        ownership_posture="inherits-parent-ownership",
        notes="These rows inherit ownership from the governing canonical entity instead of carrying direct ownership primitives.",
        migration_managed=True,
    )
    register_many(
        ("session_embeddings",),
        kind="table",
        domain="observed_product_entities",
        durability="canonical",
        local_owner="not part of the local-first storage contract",
        enterprise_owner="enterprise Postgres canonical transcript intelligence store",
        ownership_posture="inherits-parent-ownership",
        notes=(
            "Session embedding blocks inherit ownership from the parent session/message lineage and "
            "remain enterprise-only in Phase 2."
        ),
        migration_managed=True,
    )

    register_many(
        ("sync_state",),
        kind="table",
        domain="ingestion_cache_state",
        durability="derived",
        local_owner="profile-local storage adapter",
        enterprise_owner="profile-local storage adapter",
        ownership_posture="scope-owned",
        notes="Filesystem sync state is adapter-owned rather than canonical shared data.",
        migration_managed=True,
    )

    register_many(
        (
            "external_definition_sources",
            "pricing_catalog_entries",
            "artifact_snapshot_cache",
            "artifact_identity_map",
        ),
        kind="table",
        domain="integration_snapshots",
        durability="refreshable",
        local_owner="SQLite refreshable snapshot cache",
        enterprise_owner="enterprise Postgres refreshable snapshot store",
        ownership_posture="scope-owned",
        notes=(
            "Snapshot roots and project-scoped identity reconciliation state remain scope-governed; "
            "they should not reserve direct ownership primitives."
        ),
        migration_managed=True,
    )
    register_many(
        ("external_definitions",),
        kind="table",
        domain="integration_snapshots",
        durability="refreshable",
        local_owner="SQLite refreshable snapshot cache",
        enterprise_owner="enterprise Postgres refreshable snapshot store",
        ownership_posture="inherits-parent-ownership",
        notes="Definitions inherit ownership from their governing snapshot source rather than storing direct ownership fields.",
        migration_managed=True,
    )
    register_many(
        ("session_memory_drafts",),
        kind="table",
        domain="operational_job_data",
        durability="refreshable",
        local_owner="SQLite operational state store",
        enterprise_owner="enterprise Postgres operational state store",
        ownership_posture="scope-owned",
        notes="Session memory draft roots remain project-scoped operational records until explicitly published to SkillMeat.",
        migration_managed=True,
    )

    register_many(
        (
            "schema_version",
            "metric_types",
            "analytics_entries",
            "telemetry_events",
            "outbound_telemetry_queue",
            "effectiveness_rollups",
            "execution_runs",
            "test_runs",
            "test_definitions",
            "test_domains",
        ),
        kind="table",
        domain="operational_job_data",
        durability="operational",
        local_owner="local adapter allowed for local mode",
        enterprise_owner="enterprise Postgres preferred for hosted mode",
        ownership_posture="scope-owned",
        notes="Operational roots stay scope-aware only; they should not gain direct ownership columns.",
        migration_managed=True,
    )
    register_many(
        (
            "analytics_entity_links",
            "session_stack_observations",
            "session_stack_components",
            "execution_run_events",
            "execution_approvals",
            "test_results",
            "test_feature_mappings",
            "test_integrity_signals",
            "test_metrics",
        ),
        kind="table",
        domain="operational_job_data",
        durability="operational",
        local_owner="local adapter allowed for local mode",
        enterprise_owner="enterprise Postgres preferred for hosted mode",
        ownership_posture="inherits-parent-ownership",
        notes="Child operational rows inherit ownership from the governing run, observation, or scope root.",
        migration_managed=True,
    )

    register_many(
        ("principals", "scope_identifiers"),
        kind="placeholder",
        domain="identity_access",
        durability="canonical",
        local_owner="not part of the local-first storage contract",
        enterprise_owner="enterprise Postgres canonical home",
        ownership_posture="scope-owned",
        notes="Identity roots are governed by tenant or enterprise scope rather than direct user/team ownership columns.",
        current=False,
    )
    register_many(
        ("memberships", "role_bindings"),
        kind="placeholder",
        domain="identity_access",
        durability="canonical",
        local_owner="not part of the local-first storage contract",
        enterprise_owner="enterprise Postgres canonical home",
        ownership_posture="inherits-parent-ownership",
        notes="Membership and binding records inherit ownership from the governing principal and scope roots.",
        current=False,
    )
    register_many(
        ("privileged_action_audit_records", "access_decision_logs"),
        kind="placeholder",
        domain="audit_security_records",
        durability="canonical",
        local_owner="not part of the local-first storage contract",
        enterprise_owner="enterprise Postgres canonical home",
        ownership_posture="scope-owned",
        notes="Audit records remain scope-governed and must not reserve direct ownership columns unless a later plan proves they are independently shareable.",
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
ENTERPRISE_ONLY_POSTGRES_CONCERNS = tuple(
    concern
    for concern, ownership in PERSISTED_CONCERN_OWNERSHIP.items()
    if ownership.local_owner == "not part of the local-first storage contract"
)


def get_persisted_concern_ownership(concern: str) -> PersistedConcernOwnership:
    """Return the frozen ownership record for a persisted concern."""

    return PERSISTED_CONCERN_OWNERSHIP[concern]


def iter_persisted_concern_ownership() -> tuple[PersistedConcernOwnership, ...]:
    """Return the ownership matrix in stable declaration order."""

    return tuple(PERSISTED_CONCERN_OWNERSHIP.values())
