"""Core port composition shared by runtime bootstraps and compatibility paths."""
from __future__ import annotations

from typing import Any

from backend.adapters.auth import LocalIdentityProvider, PermitAllAuthorizationPolicy
from backend.adapters.integrations import NoopIntegrationClient
from backend.adapters.jobs import InProcessJobScheduler
from backend.adapters.storage import FactoryStorageUnitOfWork
from backend.adapters.workspaces import ProjectManagerWorkspaceRegistry
from backend.application.ports import CorePorts
from backend.project_manager import ProjectManager, project_manager


def build_core_ports(
    db: Any,
    *,
    manager: ProjectManager | None = None,
    identity_provider: Any | None = None,
    authorization_policy: Any | None = None,
    workspace_registry: Any | None = None,
    storage: Any | None = None,
    job_scheduler: Any | None = None,
    integration_client: Any | None = None,
) -> CorePorts:
    workspace_manager = manager or project_manager
    return CorePorts(
        identity_provider=identity_provider or LocalIdentityProvider(),
        authorization_policy=authorization_policy or PermitAllAuthorizationPolicy(),
        workspace_registry=workspace_registry or ProjectManagerWorkspaceRegistry(workspace_manager),
        storage=storage or FactoryStorageUnitOfWork(db),
        job_scheduler=job_scheduler or InProcessJobScheduler(),
        integration_client=integration_client or NoopIntegrationClient(),
    )
