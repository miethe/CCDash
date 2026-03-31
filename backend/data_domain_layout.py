"""Code-owned schema and repository boundary contract for persisted domains."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from backend.data_domains import OwnerSubjectType


RepositoryOwnershipMode = Literal["owner-aware", "scope-aware-only"]


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
    direct_owner_subject_types: tuple[OwnerSubjectType, ...] = ()
    ownership_primitive_columns: tuple[str, ...] = ()
    scope_owned_concerns: tuple[str, ...] = ()
    inherited_ownership_concerns: tuple[str, ...] = ()
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
    notes: str = ""


_DIRECT_OWNER_SUBJECT_TYPES: tuple[OwnerSubjectType, ...] = ("user", "team", "enterprise")
OWNERSHIP_PRIMITIVE_COLUMNS: tuple[str, ...] = (
    "tenant_id or enterprise_id",
    "owner_subject_type",
    "owner_subject_id",
    "visibility",
)


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
            direct_owner_subject_types=_DIRECT_OWNER_SUBJECT_TYPES,
            ownership_primitive_columns=OWNERSHIP_PRIMITIVE_COLUMNS,
            scope_owned_concerns=("projects.json", "workspace_registry_state", "app_metadata"),
            notes="Workspace metadata stays local-first but maps to canonical app-owned tables in hosted mode. Only alert configurations are expected to need direct user/team/enterprise ownership semantics.",
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
            direct_owner_subject_types=_DIRECT_OWNER_SUBJECT_TYPES,
            ownership_primitive_columns=OWNERSHIP_PRIMITIVE_COLUMNS,
            scope_owned_concerns=("tags",),
            inherited_ownership_concerns=(
                "entity_links",
                "external_links",
                "entity_tags",
                "session_logs",
                "session_messages",
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
            notes="Observed entities remain mixed in V1: SQLite-local for local-first workflows and Postgres-directional for hosted canonicalization. Only the canonical content roots reserve direct ownership primitives; linked rows inherit from those roots.",
        ),
        "ingestion_state": SchemaBoundary(
            key="ingestion_state",
            domain="ingestion_cache_state",
            postgres_schema="ops",
            sqlite_group="ingestion adapter state tables",
            current_tables=("sync_state",),
            scope_owned_concerns=("sync_state",),
            notes="Sync state belongs to the ingestion adapter boundary rather than app-canonical data and must not reserve direct ownership primitives.",
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
            notes="Integration data is refreshable and intentionally separated from canonical product state. Snapshot children inherit from the governing source/snapshot root instead of storing direct ownership.",
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
            notes="Hosted deployments should treat this boundary as ops-owned even when local mode persists it in SQLite. Operational rows are scope-aware only and should not gain direct ownership columns.",
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
            notes="Reserved for enterprise-only identity and scope storage introduced in Phase 4. Identity roots are scope-owned; memberships and bindings inherit from those roots instead of introducing direct content ownership fields.",
        ),
        "audit_security": SchemaBoundary(
            key="audit_security",
            domain="audit_security_records",
            postgres_schema="audit",
            sqlite_group="not part of the local-first contract",
            current_tables=(),
            planned_tables=("privileged_action_audit_records", "access_decision_logs"),
            scope_owned_concerns=("privileged_action_audit_records", "access_decision_logs"),
            notes="Reserved for enterprise-only privileged action and access decision records. Audit rows are scope-governed and must not reserve direct ownership primitives unless a later plan proves independent shareability.",
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
            notes="Session roots must become owner-aware in hosted mode. Supporting session rows inherit ownership from the canonical session root.",
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
            notes="Message-level transcript storage is the additive seam for future canonical session work, but rows inherit ownership from the parent session instead of carrying direct owner columns.",
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
            notes="Document roots may later support direct ownership; refs inherit from the governing document.",
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
            notes="Task roots may later support direct ownership and visibility rules in hosted mode.",
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
            notes="Feature roots are owner-aware; phase and commit correlation rows inherit ownership from the feature.",
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
            notes="Link rows inherit ownership from the canonical entity they connect and should not grow independent owner columns.",
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
            notes="Tags are scope-owned taxonomy rows; entity-tag joins inherit from the tagged entity and taxonomy scope.",
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
            notes="Alert configs may later support direct user/team/enterprise ownership for shareable notification policies.",
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
            notes="Analytics rows are operational and remain scope-aware only.",
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
            notes="Usage attribution rows inherit ownership from the parent session and should remain scope-aware only.",
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
            notes="Snapshot repositories remain scope-aware only; child definitions inherit from their snapshot source.",
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
