"""Core port composition shared by runtime bootstraps and compatibility paths."""
from __future__ import annotations

from typing import Any

from backend import config
from backend.adapters.auth import (
    LocalIdentityProvider,
    PermitAllAuthorizationPolicy,
    StaticBearerTokenIdentityProvider,
)
from backend.adapters.integrations import NoopIntegrationClient
from backend.adapters.jobs import InProcessJobScheduler
from backend.adapters.storage import EnterpriseStorageUnitOfWork, LocalStorageUnitOfWork
from backend.adapters.workspaces import ProjectManagerWorkspaceRegistry
from backend.application.ports import CorePorts, StorageUnitOfWork
from backend.db.migration_governance import (
    build_migration_governance_metadata,
    resolve_storage_composition_contract,
)
from backend.project_manager import ProjectManager, project_manager
from backend.runtime.profiles import RuntimeProfile
from backend.runtime.storage_contract import (
    get_runtime_storage_contract,
    get_storage_capability_contract,
    serialize_probe_cadence,
    validate_runtime_storage_pairing,
)


def build_core_ports(
    db: Any,
    *,
    runtime_profile: RuntimeProfile | None = None,
    storage_profile: config.StorageProfileConfig | None = None,
    manager: ProjectManager | None = None,
    identity_provider: Any | None = None,
    authorization_policy: Any | None = None,
    workspace_registry: Any | None = None,
    storage: Any | None = None,
    job_scheduler: Any | None = None,
    integration_client: Any | None = None,
) -> CorePorts:
    workspace_manager = manager or project_manager
    resolved_storage_profile = storage_profile or config.STORAGE_PROFILE
    validate_runtime_storage_pairing(runtime_profile, resolved_storage_profile)
    resolved_identity_provider = identity_provider or _build_identity_provider(runtime_profile)
    return CorePorts(
        identity_provider=resolved_identity_provider,
        authorization_policy=authorization_policy or PermitAllAuthorizationPolicy(),
        workspace_registry=workspace_registry or build_workspace_registry(
            runtime_profile=runtime_profile,
            storage_profile=resolved_storage_profile,
            manager=workspace_manager,
        ),
        storage=storage or _build_storage_unit_of_work(db, runtime_profile, resolved_storage_profile),
        job_scheduler=job_scheduler or InProcessJobScheduler(),
        integration_client=integration_client or NoopIntegrationClient(),
    )


def build_runtime_metadata(
    runtime_profile: RuntimeProfile,
    storage_profile: config.StorageProfileConfig,
) -> dict[str, object]:
    validate_runtime_storage_pairing(runtime_profile, storage_profile)
    runtime_contract = get_runtime_storage_contract(runtime_profile)
    storage_contract = get_storage_capability_contract(storage_profile)
    storage_composition = resolve_storage_composition_contract(storage_profile)
    governance_metadata = build_migration_governance_metadata(storage_profile)
    runtime_capabilities = {
        "watch": runtime_profile.capabilities.watch,
        "sync": runtime_profile.capabilities.sync,
        "jobs": runtime_profile.capabilities.jobs,
        "auth": runtime_profile.capabilities.auth,
        "integrations": runtime_profile.capabilities.integrations,
    }
    return {
        "profile": runtime_profile.name,
        "runtimeDescription": runtime_profile.description,
        "watchEnabled": runtime_profile.capabilities.watch,
        "syncEnabled": runtime_profile.capabilities.sync,
        "jobsEnabled": runtime_profile.capabilities.jobs,
        "authEnabled": runtime_profile.capabilities.auth,
        "integrationsEnabled": runtime_profile.capabilities.integrations,
        "runtimeCapabilities": runtime_capabilities,
        "recommendedStorageProfile": runtime_profile.recommended_storage_profile,
        "allowedStorageProfiles": runtime_contract.allowed_storage_profiles,
        "supportedStorageProfiles": runtime_contract.allowed_storage_profiles,
        "runtimeSyncBehavior": runtime_contract.sync_behavior,
        "runtimeJobBehavior": runtime_contract.job_behavior,
        "runtimeAuthBehavior": runtime_contract.auth_behavior,
        "runtimeIntegrationBehavior": runtime_contract.integration_behavior,
        "requiredReadinessChecks": runtime_contract.readiness_checks,
        "probeCadence": serialize_probe_cadence(runtime_contract),
        "storageMode": storage_contract.mode,
        "storageProfile": storage_profile.profile,
        "storageBackend": storage_profile.db_backend,
        "storageComposition": storage_composition.composition,
        "storageCanonicalStore": storage_contract.canonical_store,
        "filesystemSourceOfTruth": storage_profile.filesystem_source_of_truth,
        "storageFilesystemRole": storage_contract.filesystem_role,
        "sharedPostgresEnabled": storage_profile.shared_postgres_enabled,
        "storageIsolationMode": storage_profile.isolation_mode,
        "supportedStorageIsolationModes": storage_contract.supported_isolation_modes,
        "storageSchema": storage_profile.schema_name,
        "canonicalSessionStore": storage_profile.canonical_session_store,
        "requiredStorageGuarantees": storage_contract.required_guarantees,
        "migrationGovernanceStatus": governance_metadata["migrationGovernanceStatus"],
        "supportedStorageCompositions": governance_metadata["supportedStorageCompositions"],
        "supportedBackendDifferenceCategories": governance_metadata["supportedBackendDifferenceCategories"],
    }


def build_workspace_registry(
    *,
    runtime_profile: RuntimeProfile | None = None,
    storage_profile: config.StorageProfileConfig | None = None,
    manager: ProjectManager | None = None,
) -> ProjectManagerWorkspaceRegistry:
    _ = runtime_profile, storage_profile
    return ProjectManagerWorkspaceRegistry(manager or project_manager)


def _build_identity_provider(runtime_profile: RuntimeProfile | None) -> object:
    if runtime_profile is not None and runtime_profile.capabilities.auth:
        return StaticBearerTokenIdentityProvider()
    return LocalIdentityProvider()


def _build_storage_unit_of_work(
    db: Any,
    runtime_profile: RuntimeProfile | None,
    storage_profile: config.StorageProfileConfig,
) -> StorageUnitOfWork:
    _ = runtime_profile
    if storage_profile.profile == "enterprise" and storage_profile.db_backend != "postgres":
        raise RuntimeError("Enterprise storage profile requires the Postgres DB backend.")
    if storage_profile.profile == "enterprise":
        return EnterpriseStorageUnitOfWork(db)
    return LocalStorageUnitOfWork(db)
