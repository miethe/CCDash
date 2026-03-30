"""Core port composition shared by runtime bootstraps and compatibility paths."""
from __future__ import annotations

from typing import Any

from backend import config
from backend.adapters.auth import LocalIdentityProvider, PermitAllAuthorizationPolicy
from backend.adapters.integrations import NoopIntegrationClient
from backend.adapters.jobs import InProcessJobScheduler
from backend.adapters.storage import EnterpriseStorageUnitOfWork, LocalStorageUnitOfWork
from backend.adapters.workspaces import ProjectManagerWorkspaceRegistry
from backend.application.ports import CorePorts, StorageUnitOfWork
from backend.project_manager import ProjectManager, project_manager
from backend.runtime.profiles import RuntimeProfile
from backend.runtime.storage_contract import validate_runtime_storage_pairing


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
    return CorePorts(
        identity_provider=identity_provider or LocalIdentityProvider(),
        authorization_policy=authorization_policy or PermitAllAuthorizationPolicy(),
        workspace_registry=workspace_registry or _build_workspace_registry(workspace_manager, runtime_profile, resolved_storage_profile),
        storage=storage or _build_storage_unit_of_work(db, runtime_profile, resolved_storage_profile),
        job_scheduler=job_scheduler or InProcessJobScheduler(),
        integration_client=integration_client or NoopIntegrationClient(),
    )


def _build_workspace_registry(
    manager: ProjectManager,
    runtime_profile: RuntimeProfile | None,
    storage_profile: config.StorageProfileConfig,
) -> ProjectManagerWorkspaceRegistry:
    _ = runtime_profile, storage_profile
    return ProjectManagerWorkspaceRegistry(manager)


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
