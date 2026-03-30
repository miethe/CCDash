"""Framework-agnostic application ports."""

from backend.application.ports.core import (
    AuthorizationDecision,
    AuthorizationPolicy,
    CorePorts,
    IngestionStateStorage,
    IdentityProvider,
    IntegrationSnapshotStorage,
    IntegrationClient,
    JobScheduler,
    ObservedProductStorage,
    OperationalStateStorage,
    StorageUnitOfWork,
    WorkspaceMetadataStorage,
    WorkspaceRegistry,
)

__all__ = [
    "AuthorizationDecision",
    "AuthorizationPolicy",
    "CorePorts",
    "IngestionStateStorage",
    "IdentityProvider",
    "IntegrationSnapshotStorage",
    "IntegrationClient",
    "JobScheduler",
    "ObservedProductStorage",
    "OperationalStateStorage",
    "StorageUnitOfWork",
    "WorkspaceMetadataStorage",
    "WorkspaceRegistry",
]
