"""Storage capability and runtime pairing contracts."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from backend import config
from backend.runtime.profiles import RuntimeProfile


StorageModeName = Literal["local", "enterprise", "shared-enterprise"]
ProbeCheckCode = Literal[
    "db_connection",
    "storage_pairing",
    "migration_governance",
    "schema_migrations",
    "auth_contract",
    "worker_binding",
    "watcher_runtime",
    "startup_sync",
]


@dataclass(frozen=True, slots=True)
class StorageCapabilityContract:
    mode: StorageModeName
    canonical_store: str
    filesystem_role: str
    integration_store: str
    operational_store: str
    audit_store: str
    session_intelligence_profile: str
    session_intelligence_analytics_level: str
    session_intelligence_backfill_strategy: str
    session_intelligence_memory_draft_flow: str
    session_intelligence_isolation_boundary: str
    supported_isolation_modes: tuple[config.StorageIsolationMode, ...]
    required_guarantees: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuntimeStorageContract:
    runtime_profile: str
    allowed_storage_profiles: tuple[config.StorageProfileName, ...]
    sync_behavior: str
    job_behavior: str
    auth_behavior: str
    integration_behavior: str
    readiness_checks: tuple[ProbeCheckCode, ...]
    live_probe_interval_seconds: int
    ready_probe_interval_seconds: int
    detail_probe_interval_seconds: int


_STORAGE_CAPABILITY_CONTRACTS: dict[StorageModeName, StorageCapabilityContract] = {
    "local": StorageCapabilityContract(
        mode="local",
        canonical_store="sqlite_local_metadata",
        filesystem_role="primary_ingestion_and_derived_source",
        integration_store="profile_local_storage",
        operational_store="profile_local_storage",
        audit_store="not_supported_in_v1_local_mode",
        session_intelligence_profile="local_cache",
        session_intelligence_analytics_level="limited_optional",
        session_intelligence_backfill_strategy="local_rebuild_from_filesystem",
        session_intelligence_memory_draft_flow="reviewable_local_drafts",
        session_intelligence_isolation_boundary="not_applicable",
        supported_isolation_modes=("dedicated",),
        required_guarantees=(
            "SQLite remains the default local-first posture.",
            "Filesystem-derived ingestion and cache rebuilds remain first-class.",
            "Hosted-only identity and audit concerns are out of scope for local mode.",
        ),
    ),
    "enterprise": StorageCapabilityContract(
        mode="enterprise",
        canonical_store="postgres_dedicated",
        filesystem_role="optional_ingestion_adapter_only",
        integration_store="postgres",
        operational_store="postgres",
        audit_store="postgres_phase_4_foundation",
        session_intelligence_profile="enterprise_canonical",
        session_intelligence_analytics_level="full",
        session_intelligence_backfill_strategy="checkpointed_enterprise_backfill",
        session_intelligence_memory_draft_flow="approval_gated_enterprise_publish",
        session_intelligence_isolation_boundary="dedicated_instance",
        supported_isolation_modes=("dedicated",),
        required_guarantees=(
            "Postgres is the canonical hosted store.",
            "API runtimes must not assume local filesystem watch behavior.",
            "Identity and audit data belong in canonical Postgres-owned storage.",
        ),
    ),
    "shared-enterprise": StorageCapabilityContract(
        mode="shared-enterprise",
        canonical_store="postgres_shared_instance",
        filesystem_role="optional_ingestion_adapter_only",
        integration_store="postgres_schema_or_tenant_boundary",
        operational_store="postgres_schema_or_tenant_boundary",
        audit_store="postgres_schema_or_tenant_boundary_phase_4_foundation",
        session_intelligence_profile="enterprise_canonical_shared_boundary",
        session_intelligence_analytics_level="full",
        session_intelligence_backfill_strategy="checkpointed_enterprise_backfill",
        session_intelligence_memory_draft_flow="approval_gated_enterprise_publish",
        session_intelligence_isolation_boundary="schema_or_tenant_boundary",
        supported_isolation_modes=("schema", "tenant"),
        required_guarantees=(
            "Shared Postgres requires an explicit CCDash isolation boundary.",
            "Cross-application table coupling is not allowed.",
            "Hosted identity, audit, and operational data stay inside the CCDash boundary.",
        ),
    ),
}


_RUNTIME_STORAGE_CONTRACTS: dict[str, RuntimeStorageContract] = {
    "local": RuntimeStorageContract(
        runtime_profile="local",
        allowed_storage_profiles=("local",),
        sync_behavior="watch_and_sync_enabled",
        job_behavior="in_process_jobs_allowed",
        auth_behavior="local_no_auth",
        integration_behavior="integrations_available",
        readiness_checks=(
            "db_connection",
            "storage_pairing",
            "migration_governance",
            "schema_migrations",
        ),
        live_probe_interval_seconds=30,
        ready_probe_interval_seconds=30,
        detail_probe_interval_seconds=90,
    ),
    "api": RuntimeStorageContract(
        runtime_profile="api",
        allowed_storage_profiles=("enterprise",),
        sync_behavior="no_incidental_sync_or_watch",
        job_behavior="no_background_jobs",
        auth_behavior="hosted_auth_expected",
        integration_behavior="integrations_available",
        readiness_checks=(
            "db_connection",
            "storage_pairing",
            "migration_governance",
            "schema_migrations",
            "auth_contract",
        ),
        live_probe_interval_seconds=15,
        ready_probe_interval_seconds=20,
        detail_probe_interval_seconds=60,
    ),
    "worker": RuntimeStorageContract(
        runtime_profile="worker",
        allowed_storage_profiles=("enterprise",),
        sync_behavior="background_sync_allowed",
        job_behavior="scheduled_jobs_allowed",
        auth_behavior="request_auth_not_expected",
        integration_behavior="integrations_available",
        readiness_checks=(
            "db_connection",
            "storage_pairing",
            "migration_governance",
            "schema_migrations",
            "worker_binding",
        ),
        live_probe_interval_seconds=15,
        ready_probe_interval_seconds=20,
        detail_probe_interval_seconds=45,
    ),
    "worker-watch": RuntimeStorageContract(
        runtime_profile="worker-watch",
        allowed_storage_profiles=("enterprise",),
        sync_behavior="watch_and_background_sync_allowed",
        job_behavior="scheduled_jobs_allowed",
        auth_behavior="request_auth_not_expected",
        integration_behavior="integrations_available",
        readiness_checks=(
            "db_connection",
            "storage_pairing",
            "migration_governance",
            "schema_migrations",
            "worker_binding",
        ),
        live_probe_interval_seconds=15,
        ready_probe_interval_seconds=20,
        detail_probe_interval_seconds=45,
    ),
    "test": RuntimeStorageContract(
        runtime_profile="test",
        allowed_storage_profiles=("local", "enterprise"),
        sync_behavior="background_sync_disabled",
        job_behavior="background_jobs_disabled",
        auth_behavior="auth_disabled_by_default",
        integration_behavior="integrations_disabled_by_default",
        readiness_checks=(
            "db_connection",
            "storage_pairing",
            "migration_governance",
            "schema_migrations",
        ),
        live_probe_interval_seconds=60,
        ready_probe_interval_seconds=60,
        detail_probe_interval_seconds=120,
    ),
}


def resolve_storage_mode(storage_profile: config.StorageProfileConfig) -> StorageModeName:
    if storage_profile.profile == "enterprise" and storage_profile.shared_postgres_enabled:
        return "shared-enterprise"
    return storage_profile.profile


def get_storage_capability_contract(
    storage_profile: config.StorageProfileConfig,
) -> StorageCapabilityContract:
    return _STORAGE_CAPABILITY_CONTRACTS[resolve_storage_mode(storage_profile)]


def get_runtime_storage_contract(runtime_profile: RuntimeProfile) -> RuntimeStorageContract:
    return _RUNTIME_STORAGE_CONTRACTS[runtime_profile.name]


def default_runtime_activity_snapshot(runtime_profile: RuntimeProfile) -> dict[str, str | bool]:
    return {
        "watcher": "stopped",
        "startupSync": "idle",
        "analyticsSnapshots": "idle",
        "telemetryExports": "idle",
        "cacheWarming": "idle",
        "jobsEnabled": runtime_profile.capabilities.jobs,
    }


def serialize_probe_cadence(runtime_contract: RuntimeStorageContract) -> dict[str, int]:
    return {
        "liveSeconds": runtime_contract.live_probe_interval_seconds,
        "readySeconds": runtime_contract.ready_probe_interval_seconds,
        "detailSeconds": runtime_contract.detail_probe_interval_seconds,
    }


@lru_cache(maxsize=1)
def build_storage_profile_validation_matrix() -> tuple[dict[str, Any], ...]:
    validation_profiles = (
        config.resolve_storage_profile_config({"CCDASH_DB_BACKEND": "sqlite"}),
        config.resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
            }
        ),
        config.resolve_storage_profile_config(
            {
                "CCDASH_STORAGE_PROFILE": "enterprise",
                "CCDASH_DB_BACKEND": "postgres",
                "CCDASH_DATABASE_URL": "postgresql://db.example/ccdash",
                "CCDASH_STORAGE_SHARED_POSTGRES": "true",
                "CCDASH_STORAGE_ISOLATION_MODE": "schema",
                "CCDASH_STORAGE_SCHEMA": "ccdash_app",
            }
        ),
    )
    return tuple(_build_storage_profile_validation_row(profile) for profile in validation_profiles)


def _build_storage_profile_validation_row(
    storage_profile: config.StorageProfileConfig,
) -> dict[str, Any]:
    from backend.db.migration_governance import resolve_storage_composition_contract

    storage_contract = get_storage_capability_contract(storage_profile)
    storage_composition = resolve_storage_composition_contract(storage_profile)
    enterprise_capability = storage_contract.mode != "local"
    capability_status = "authoritative" if enterprise_capability else "unsupported"
    return {
        "storageMode": storage_contract.mode,
        "storageProfile": storage_profile.profile,
        "storageBackend": storage_profile.db_backend,
        "storageComposition": storage_composition.composition,
        "storageFilesystemRole": storage_contract.filesystem_role,
        "sharedPostgresEnabled": storage_profile.shared_postgres_enabled,
        "supportedStorageIsolationModes": storage_contract.supported_isolation_modes,
        "storageCanonicalStore": storage_contract.canonical_store,
        "auditStore": storage_contract.audit_store,
        "auditWriteSupported": enterprise_capability,
        "auditWriteAuthoritative": enterprise_capability,
        "auditWriteStatus": capability_status,
        "sessionEmbeddingWriteSupported": enterprise_capability,
        "sessionEmbeddingWriteAuthoritative": enterprise_capability,
        "sessionEmbeddingWriteStatus": capability_status,
        "sessionIntelligenceProfile": storage_contract.session_intelligence_profile,
        "sessionIntelligenceAnalyticsLevel": storage_contract.session_intelligence_analytics_level,
        "sessionIntelligenceBackfillStrategy": storage_contract.session_intelligence_backfill_strategy,
        "sessionIntelligenceMemoryDraftFlow": storage_contract.session_intelligence_memory_draft_flow,
        "sessionIntelligenceIsolationBoundary": storage_contract.session_intelligence_isolation_boundary,
        "requiredStorageGuarantees": storage_contract.required_guarantees,
    }


def validate_runtime_storage_pairing(
    runtime_profile: RuntimeProfile | None,
    storage_profile: config.StorageProfileConfig,
) -> None:
    if runtime_profile is None:
        return

    runtime_contract = get_runtime_storage_contract(runtime_profile)
    if storage_profile.profile not in runtime_contract.allowed_storage_profiles:
        allowed = ", ".join(runtime_contract.allowed_storage_profiles)
        raise RuntimeError(
            f"Runtime profile '{runtime_profile.name}' only supports storage profiles: {allowed}. "
            f"Resolved storage profile: {storage_profile.profile}."
        )

    storage_contract = get_storage_capability_contract(storage_profile)
    if storage_profile.isolation_mode not in storage_contract.supported_isolation_modes:
        allowed = ", ".join(storage_contract.supported_isolation_modes)
        raise RuntimeError(
            f"Storage mode '{storage_contract.mode}' only supports isolation modes: {allowed}. "
            f"Resolved isolation mode: {storage_profile.isolation_mode}."
        )
