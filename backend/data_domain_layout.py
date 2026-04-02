"""Code-owned schema and repository boundary contract for persisted domains."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal


RepositoryOwnershipMode = Literal["owner-aware", "scope-aware-only"]
OwnershipColumn = Literal["owner_subject_type", "owner_subject_id", "visibility"]

TENANCY_SCOPE_COLUMN = "tenant_id_or_enterprise_id"
DIRECT_OWNERSHIP_COLUMNS: tuple[OwnershipColumn, ...] = (
    "owner_subject_type",
    "owner_subject_id",
    "visibility",
)


@dataclass(frozen=True)
class SchemaBoundary:
    key: str
    domain: str
    postgres_schema: str
    sqlite_group: str
    current_tables: tuple[str, ...]
    planned_tables: tuple[str, ...] = ()
    filesystem_artifacts: tuple[str, ...] = ()
    directly_ownable_concerns: tuple[str, ...] = ()
    scope_owned_concerns: tuple[str, ...] = ()
    inherited_ownership_concerns: tuple[str, ...] = ()
    tenancy_scope_column: str = ""
    direct_ownership_columns: tuple[OwnershipColumn, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class RepositoryOwnership:
    key: str
    domain: str
    boundary: str
    sqlite_module: str
    postgres_module: str
    concerns: tuple[str, ...]
    ownership_mode: RepositoryOwnershipMode
    directly_ownable_concerns: tuple[str, ...] = ()
    scope_owned_concerns: tuple[str, ...] = ()
    inherited_ownership_concerns: tuple[str, ...] = ()
    tenancy_scope_column: str = ""
    direct_ownership_columns: tuple[OwnershipColumn, ...] = ()
    notes: str = ""


SCHEMA_BOUNDARIES = MappingProxyType(
    {
        "workspace_metadata": SchemaBoundary(
            key="workspace_metadata",
            domain="workspace_project_metadata",
            postgres_schema="app",
            sqlite_group="workspace metadata tables",
            current_tables=("app_metadata", "alert_configs"),
            filesystem_artifacts=("projects.json", "workspace_registry_state"),
            directly_ownable_concerns=("alert_configs",),
            scope_owned_concerns=("projects.json", "workspace_registry_state", "app_metadata"),
            tenancy_scope_column=TENANCY_SCOPE_COLUMN,
            direct_ownership_columns=DIRECT_OWNERSHIP_COLUMNS,
            notes=(
                "Workspace metadata stays local-first but maps to canonical app-owned tables in hosted mode. "
                "Only alert configs reserve direct ownership primitives; app metadata remains scope-owned."
            ),
        ),
        "observed_entities": SchemaBoundary(
            key="observed_entities",
            domain="observed_product_entities",
            postgres_schema="app",
            sqlite_group="observed entity tables",
            current_tables=(
                "entity_links",
                "external_links",
                "tags",
                "entity_tags",
                "sessions",
                "session_logs",
                "session_messages",
                "session_embeddings",
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
            directly_ownable_concerns=("sessions", "documents", "tasks", "features"),
            scope_owned_concerns=("tags",),
            inherited_ownership_concerns=(
                "entity_links",
                "external_links",
                "entity_tags",
                "session_logs",
                "session_messages",
                "session_embeddings",
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
            tenancy_scope_column=TENANCY_SCOPE_COLUMN,
            direct_ownership_columns=DIRECT_OWNERSHIP_COLUMNS,
            notes=(
                "Observed entities remain mixed in V1: SQLite-local for local-first workflows and Postgres-directional "
                "for hosted canonicalization. Direct ownership primitives are reserved only on root content objects."
            ),
        ),
        "ingestion_state": SchemaBoundary(
            key="ingestion_state",
            domain="ingestion_cache_state",
            postgres_schema="ops",
            sqlite_group="ingestion adapter state tables",
            current_tables=("sync_state",),
            scope_owned_concerns=("sync_state",),
            notes="Sync state belongs to the ingestion adapter boundary rather than app-canonical data.",
        ),
        "integration_snapshots": SchemaBoundary(
            key="integration_snapshots",
            domain="integration_snapshots",
            postgres_schema="integration",
            sqlite_group="refreshable integration snapshot tables",
            current_tables=(
                "external_definition_sources",
                "external_definitions",
                "pricing_catalog_entries",
            ),
            scope_owned_concerns=("external_definition_sources", "pricing_catalog_entries"),
            inherited_ownership_concerns=("external_definitions",),
            notes=(
                "Integration data is refreshable and intentionally separated from canonical product state. "
                "Snapshot roots stay scope-owned; definitions inherit from their source."
            ),
        ),
        "operational_state": SchemaBoundary(
            key="operational_state",
            domain="operational_job_data",
            postgres_schema="ops",
            sqlite_group="runtime and job state tables",
            current_tables=(
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
            scope_owned_concerns=(
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
            inherited_ownership_concerns=(
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
            notes=(
                "Hosted deployments should treat this boundary as ops-owned even when local mode persists it in SQLite. "
                "Operational rows remain scope-aware only and do not reserve direct ownership primitives."
            ),
        ),
        "identity_access": SchemaBoundary(
            key="identity_access",
            domain="identity_access",
            postgres_schema="identity",
            sqlite_group="not part of the local-first contract",
            current_tables=(),
            planned_tables=("principals", "memberships", "role_bindings", "scope_identifiers"),
            scope_owned_concerns=("principals", "scope_identifiers"),
            inherited_ownership_concerns=("memberships", "role_bindings"),
            notes=(
                "Reserved for enterprise-only identity and scope storage introduced in Phase 4. "
                "Identity roots are governed by scope, while memberships and bindings inherit from those roots."
            ),
        ),
        "audit_security": SchemaBoundary(
            key="audit_security",
            domain="audit_security_records",
            postgres_schema="audit",
            sqlite_group="not part of the local-first contract",
            current_tables=(),
            planned_tables=("privileged_action_audit_records", "access_decision_logs"),
            scope_owned_concerns=("privileged_action_audit_records", "access_decision_logs"),
            notes=(
                "Reserved for enterprise-only privileged action and access decision records. "
                "Audit rows remain scope-governed unless a later plan proves they are independently shareable."
            ),
        ),
    }
)


REPOSITORY_OWNERSHIP = MappingProxyType(
    {
        "sessions": RepositoryOwnership(
            key="sessions",
            domain="observed_product_entities",
            boundary="observed_entities",
            sqlite_module="backend.db.repositories.sessions",
            postgres_module="backend.db.repositories.postgres.sessions",
            concerns=(
                "sessions",
                "session_logs",
                "session_relationships",
                "session_tool_usage",
                "session_file_updates",
                "session_artifacts",
            ),
            ownership_mode="owner-aware",
            directly_ownable_concerns=("sessions",),
            inherited_ownership_concerns=(
                "session_logs",
                "session_relationships",
                "session_tool_usage",
                "session_file_updates",
                "session_artifacts",
            ),
            tenancy_scope_column=TENANCY_SCOPE_COLUMN,
            direct_ownership_columns=DIRECT_OWNERSHIP_COLUMNS,
            notes="Session roots must become owner-aware in hosted mode; child transcript artifacts inherit from the parent session.",
        ),
        "session_messages": RepositoryOwnership(
            key="session_messages",
            domain="observed_product_entities",
            boundary="observed_entities",
            sqlite_module="backend.db.repositories.session_messages",
            postgres_module="backend.db.repositories.postgres.session_messages",
            concerns=("session_messages",),
            ownership_mode="scope-aware-only",
            inherited_ownership_concerns=("session_messages",),
            notes="Message-level transcript rows inherit ownership from the parent session and should stay scope-aware only.",
        ),
        "session_embeddings": RepositoryOwnership(
            key="session_embeddings",
            domain="observed_product_entities",
            boundary="observed_entities",
            sqlite_module="backend.db.repositories.session_embeddings",
            postgres_module="backend.db.repositories.postgres.session_embeddings",
            concerns=("session_embeddings",),
            ownership_mode="scope-aware-only",
            inherited_ownership_concerns=("session_embeddings",),
            notes=(
                "Transcript embedding blocks remain enterprise-only in Phase 2 and inherit "
                "ownership from canonical session/message lineage."
            ),
        ),
        "documents": RepositoryOwnership(
            key="documents",
            domain="observed_product_entities",
            boundary="observed_entities",
            sqlite_module="backend.db.repositories.documents",
            postgres_module="backend.db.repositories.postgres.documents",
            concerns=("documents", "document_refs"),
            ownership_mode="owner-aware",
            directly_ownable_concerns=("documents",),
            inherited_ownership_concerns=("document_refs",),
            tenancy_scope_column=TENANCY_SCOPE_COLUMN,
            direct_ownership_columns=DIRECT_OWNERSHIP_COLUMNS,
            notes="Document roots may become directly ownable; reference rows inherit from the parent document.",
        ),
        "tasks": RepositoryOwnership(
            key="tasks",
            domain="observed_product_entities",
            boundary="observed_entities",
            sqlite_module="backend.db.repositories.tasks",
            postgres_module="backend.db.repositories.postgres.tasks",
            concerns=("tasks",),
            ownership_mode="owner-aware",
            directly_ownable_concerns=("tasks",),
            tenancy_scope_column=TENANCY_SCOPE_COLUMN,
            direct_ownership_columns=DIRECT_OWNERSHIP_COLUMNS,
            notes="Task roots may become directly ownable in hosted mode and should reserve ownership primitives now.",
        ),
        "features": RepositoryOwnership(
            key="features",
            domain="observed_product_entities",
            boundary="observed_entities",
            sqlite_module="backend.db.repositories.features",
            postgres_module="backend.db.repositories.postgres.features",
            concerns=("features", "feature_phases", "commit_correlations"),
            ownership_mode="owner-aware",
            directly_ownable_concerns=("features",),
            inherited_ownership_concerns=("feature_phases", "commit_correlations"),
            tenancy_scope_column=TENANCY_SCOPE_COLUMN,
            direct_ownership_columns=DIRECT_OWNERSHIP_COLUMNS,
            notes="Feature roots may become directly ownable; phase and correlation rows inherit from the parent feature.",
        ),
        "entity_links": RepositoryOwnership(
            key="entity_links",
            domain="observed_product_entities",
            boundary="observed_entities",
            sqlite_module="backend.db.repositories.entity_graph",
            postgres_module="backend.db.repositories.postgres.entity_graph",
            concerns=("entity_links", "external_links"),
            ownership_mode="scope-aware-only",
            inherited_ownership_concerns=("entity_links", "external_links"),
            notes="Link rows inherit ownership from the linked canonical entities and should remain scope-aware only.",
        ),
        "tags": RepositoryOwnership(
            key="tags",
            domain="observed_product_entities",
            boundary="observed_entities",
            sqlite_module="backend.db.repositories.entity_graph",
            postgres_module="backend.db.repositories.postgres.entity_graph",
            concerns=("tags", "entity_tags"),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("tags",),
            inherited_ownership_concerns=("entity_tags",),
            notes="Tags remain scope-owned taxonomy state; join rows inherit from the governed entity/tag pair.",
        ),
        "sync_state": RepositoryOwnership(
            key="sync_state",
            domain="ingestion_cache_state",
            boundary="ingestion_state",
            sqlite_module="backend.db.repositories.runtime_state",
            postgres_module="backend.db.repositories.postgres.runtime_state",
            concerns=("sync_state",),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("sync_state",),
            notes="Sync checkpoints are adapter state, not app-canonical data.",
        ),
        "alert_configs": RepositoryOwnership(
            key="alert_configs",
            domain="workspace_project_metadata",
            boundary="workspace_metadata",
            sqlite_module="backend.db.repositories.runtime_state",
            postgres_module="backend.db.repositories.postgres.runtime_state",
            concerns=("alert_configs",),
            ownership_mode="owner-aware",
            directly_ownable_concerns=("alert_configs",),
            tenancy_scope_column=TENANCY_SCOPE_COLUMN,
            direct_ownership_columns=DIRECT_OWNERSHIP_COLUMNS,
            notes="Alert config roots may become directly ownable for user/team/enterprise sharing in hosted mode.",
        ),
        "principals": RepositoryOwnership(
            key="principals",
            domain="identity_access",
            boundary="identity_access",
            sqlite_module="backend.db.repositories.identity_access",
            postgres_module="backend.db.repositories.postgres.identity_access",
            concerns=("principals",),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("principals",),
            notes="Principal roots stay enterprise-only and scope-governed.",
        ),
        "scope_identifiers": RepositoryOwnership(
            key="scope_identifiers",
            domain="identity_access",
            boundary="identity_access",
            sqlite_module="backend.db.repositories.identity_access",
            postgres_module="backend.db.repositories.postgres.identity_access",
            concerns=("scope_identifiers",),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("scope_identifiers",),
            notes="Scope identifiers define the enterprise/team/workspace/project hierarchy and remain scope-owned.",
        ),
        "memberships": RepositoryOwnership(
            key="memberships",
            domain="identity_access",
            boundary="identity_access",
            sqlite_module="backend.db.repositories.identity_access",
            postgres_module="backend.db.repositories.postgres.identity_access",
            concerns=("memberships",),
            ownership_mode="scope-aware-only",
            inherited_ownership_concerns=("memberships",),
            notes="Membership rows inherit from their principal and scope roots.",
        ),
        "role_bindings": RepositoryOwnership(
            key="role_bindings",
            domain="identity_access",
            boundary="identity_access",
            sqlite_module="backend.db.repositories.identity_access",
            postgres_module="backend.db.repositories.postgres.identity_access",
            concerns=("role_bindings",),
            ownership_mode="scope-aware-only",
            inherited_ownership_concerns=("role_bindings",),
            notes="Role bindings stay scope-aware only and inherit from the governing principal and scope.",
        ),
        "privileged_action_audit_records": RepositoryOwnership(
            key="privileged_action_audit_records",
            domain="audit_security_records",
            boundary="audit_security",
            sqlite_module="backend.db.repositories.identity_access",
            postgres_module="backend.db.repositories.postgres.identity_access",
            concerns=("privileged_action_audit_records",),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("privileged_action_audit_records",),
            notes="Privileged-action audit rows are enterprise-only and scope-rooted.",
        ),
        "access_decision_logs": RepositoryOwnership(
            key="access_decision_logs",
            domain="audit_security_records",
            boundary="audit_security",
            sqlite_module="backend.db.repositories.identity_access",
            postgres_module="backend.db.repositories.postgres.identity_access",
            concerns=("access_decision_logs",),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("access_decision_logs",),
            notes="Access-decision records remain enterprise-only scope-owned audit rows.",
        ),
        "analytics": RepositoryOwnership(
            key="analytics",
            domain="operational_job_data",
            boundary="operational_state",
            sqlite_module="backend.db.repositories.analytics",
            postgres_module="backend.db.repositories.postgres.analytics",
            concerns=("analytics_entries", "analytics_entity_links", "metric_types"),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("analytics_entries", "metric_types"),
            inherited_ownership_concerns=("analytics_entity_links",),
            notes="Analytics roots remain scope-owned operational data; linked rows inherit from the governed run or entity.",
        ),
        "session_usage": RepositoryOwnership(
            key="session_usage",
            domain="observed_product_entities",
            boundary="observed_entities",
            sqlite_module="backend.db.repositories.usage_attribution",
            postgres_module="backend.db.repositories.postgres.usage_attribution",
            concerns=("session_usage_events", "session_usage_attributions"),
            ownership_mode="scope-aware-only",
            inherited_ownership_concerns=("session_usage_events", "session_usage_attributions"),
            notes="Usage rows inherit from the parent session and should stay scope-aware only.",
        ),
        "pricing_catalog": RepositoryOwnership(
            key="pricing_catalog",
            domain="integration_snapshots",
            boundary="integration_snapshots",
            sqlite_module="backend.db.repositories.pricing",
            postgres_module="backend.db.repositories.postgres.pricing",
            concerns=("pricing_catalog_entries", "external_definition_sources", "external_definitions"),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("pricing_catalog_entries", "external_definition_sources"),
            inherited_ownership_concerns=("external_definitions",),
            notes="Snapshot repositories remain scope-aware only; definition rows inherit from their source snapshot.",
        ),
        "test_runs": RepositoryOwnership(
            key="test_runs",
            domain="operational_job_data",
            boundary="operational_state",
            sqlite_module="backend.db.repositories.test_runs",
            postgres_module="backend.db.repositories.postgres.test_runs",
            concerns=("test_runs",),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("test_runs",),
            notes="Test runs remain scope-owned operational entities.",
        ),
        "test_definitions": RepositoryOwnership(
            key="test_definitions",
            domain="operational_job_data",
            boundary="operational_state",
            sqlite_module="backend.db.repositories.test_definitions",
            postgres_module="backend.db.repositories.postgres.test_definitions",
            concerns=("test_definitions",),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("test_definitions",),
            notes="Test definitions are scope-owned operational definitions, not directly ownable content.",
        ),
        "test_results": RepositoryOwnership(
            key="test_results",
            domain="operational_job_data",
            boundary="operational_state",
            sqlite_module="backend.db.repositories.test_results",
            postgres_module="backend.db.repositories.postgres.test_results",
            concerns=("test_results",),
            ownership_mode="scope-aware-only",
            inherited_ownership_concerns=("test_results",),
            notes="Test results inherit from their governing test run and scope.",
        ),
        "test_domains": RepositoryOwnership(
            key="test_domains",
            domain="operational_job_data",
            boundary="operational_state",
            sqlite_module="backend.db.repositories.test_domains",
            postgres_module="backend.db.repositories.postgres.test_domains",
            concerns=("test_domains",),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("test_domains",),
            notes="Test domains remain scope-owned operational taxonomy.",
        ),
        "test_mappings": RepositoryOwnership(
            key="test_mappings",
            domain="operational_job_data",
            boundary="operational_state",
            sqlite_module="backend.db.repositories.test_mappings",
            postgres_module="backend.db.repositories.postgres.test_mappings",
            concerns=("test_feature_mappings",),
            ownership_mode="scope-aware-only",
            inherited_ownership_concerns=("test_feature_mappings",),
            notes="Feature mapping rows inherit from the governing test domain and feature scope.",
        ),
        "test_integrity": RepositoryOwnership(
            key="test_integrity",
            domain="operational_job_data",
            boundary="operational_state",
            sqlite_module="backend.db.repositories.test_integrity",
            postgres_module="backend.db.repositories.postgres.test_integrity",
            concerns=("test_integrity_signals", "test_metrics"),
            ownership_mode="scope-aware-only",
            inherited_ownership_concerns=("test_integrity_signals", "test_metrics"),
            notes="Integrity and metric rows inherit from the governing run or test scope.",
        ),
        "execution": RepositoryOwnership(
            key="execution",
            domain="operational_job_data",
            boundary="operational_state",
            sqlite_module="backend.db.repositories.execution",
            postgres_module="backend.db.repositories.postgres.execution",
            concerns=("execution_runs", "execution_run_events", "execution_approvals"),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("execution_runs",),
            inherited_ownership_concerns=("execution_run_events", "execution_approvals"),
            notes="Execution runs stay scope-owned; event and approval rows inherit from the parent run.",
        ),
        "agentic_intelligence": RepositoryOwnership(
            key="agentic_intelligence",
            domain="operational_job_data",
            boundary="operational_state",
            sqlite_module="backend.db.repositories.intelligence",
            postgres_module="backend.db.repositories.postgres.intelligence",
            concerns=(
                "session_stack_observations",
                "session_stack_components",
                "effectiveness_rollups",
                "telemetry_events",
                "outbound_telemetry_queue",
            ),
            ownership_mode="scope-aware-only",
            scope_owned_concerns=("effectiveness_rollups", "telemetry_events", "outbound_telemetry_queue"),
            inherited_ownership_concerns=("session_stack_observations", "session_stack_components"),
            notes="These tables remain operational until a future plan splits analytics and intelligence further.",
        ),
    }
)


def iter_schema_boundaries() -> tuple[SchemaBoundary, ...]:
    return tuple(SCHEMA_BOUNDARIES.values())


def iter_repository_ownership() -> tuple[RepositoryOwnership, ...]:
    return tuple(REPOSITORY_OWNERSHIP.values())
