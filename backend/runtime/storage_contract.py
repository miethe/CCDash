"""Storage capability and runtime pairing contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend import config
from backend.runtime.profiles import RuntimeProfile


StorageModeName = Literal["local", "enterprise", "shared-enterprise"]


@dataclass(frozen=True, slots=True)
class StorageCapabilityContract:
    mode: StorageModeName
    canonical_store: str
    filesystem_role: str
    integration_store: str
    operational_store: str
    audit_store: str
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


_STORAGE_CAPABILITY_CONTRACTS: dict[StorageModeName, StorageCapabilityContract] = {
    "local": StorageCapabilityContract(
        mode="local",
        canonical_store="sqlite_local_metadata",
        filesystem_role="primary_ingestion_and_derived_source",
        integration_store="profile_local_storage",
        operational_store="profile_local_storage",
        audit_store="not_supported_in_v1_local_mode",
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
    ),
    "api": RuntimeStorageContract(
        runtime_profile="api",
        allowed_storage_profiles=("enterprise",),
        sync_behavior="no_incidental_sync_or_watch",
        job_behavior="no_background_jobs",
        auth_behavior="hosted_auth_expected",
        integration_behavior="integrations_available",
    ),
    "worker": RuntimeStorageContract(
        runtime_profile="worker",
        allowed_storage_profiles=("enterprise",),
        sync_behavior="background_sync_allowed",
        job_behavior="scheduled_jobs_allowed",
        auth_behavior="request_auth_not_expected",
        integration_behavior="integrations_available",
    ),
    "test": RuntimeStorageContract(
        runtime_profile="test",
        allowed_storage_profiles=("local", "enterprise"),
        sync_behavior="background_sync_disabled",
        job_behavior="background_jobs_disabled",
        auth_behavior="auth_disabled_by_default",
        integration_behavior="integrations_disabled_by_default",
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
