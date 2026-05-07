"""Core hexagonal ports for runtime composition."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Mapping, Protocol, runtime_checkable

from backend.application.context import Principal, ProjectScope, RequestContext, RequestMetadata, WorkspaceScope
from backend.models import Project
from backend.services.project_paths.models import ResolvedProjectPaths


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    reason: str = ""
    code: str = ""


@dataclass(frozen=True, slots=True)
class ProjectBinding:
    project: Project
    paths: ResolvedProjectPaths
    source: str
    requested_project_id: str | None = None

    @property
    def locked(self) -> bool:
        return self.source == "explicit"


@runtime_checkable
class IdentityProvider(Protocol):
    async def get_principal(self, metadata: RequestMetadata, *, runtime_profile: str) -> Principal:
        """Resolve the caller principal for a request."""


@runtime_checkable
class AuthorizationPolicy(Protocol):
    async def authorize(
        self,
        context: RequestContext,
        *,
        action: str,
        resource: str | None = None,
    ) -> AuthorizationDecision:
        """Return the authorization decision for the current request."""


@runtime_checkable
class WorkspaceRegistry(Protocol):
    def list_projects(self) -> list[Project]:
        """Return all known projects."""

    def get_project(self, project_id: str) -> Project | None:
        """Return a project by id."""

    def add_project(self, project: Project) -> None:
        """Persist a new project."""

    def update_project(self, project_id: str, project: Project) -> None:
        """Persist a project update."""

    def set_active_project(self, project_id: str) -> None:
        """Set the active project."""

    def get_active_project(self) -> Project | None:
        """Return the current active project."""

    def resolve_project_paths(self, project: Project, *, refresh: bool = False) -> ResolvedProjectPaths:
        """Resolve filesystem paths for a project."""

    def get_active_path_bundle(self, *, refresh: bool = False) -> ResolvedProjectPaths:
        """Resolve filesystem paths for the active project."""

    def resolve_project_binding(
        self,
        project_id: str | None = None,
        *,
        allow_active_fallback: bool = True,
        refresh: bool = False,
    ) -> ProjectBinding | None:
        """Resolve an explicit or active project binding for runtime-owned work."""

    def resolve_scope(
        self,
        project_id: str | None = None,
        *,
        allow_active_fallback: bool = True,
    ) -> tuple[WorkspaceScope | None, ProjectScope | None]:
        """Resolve workspace/project scope.

        Local desktop callers may use the process-global active project as a
        compatibility fallback. Hosted request paths must pass
        ``allow_active_fallback=False`` and select scope through an explicit
        request project id or principal-derived project claim.
        """


@runtime_checkable
class WorkspaceMetadataStorage(Protocol):
    def alert_configs(self) -> Any: ...


@runtime_checkable
class ObservedProductStorage(Protocol):
    def sessions(self) -> Any: ...
    def session_messages(self) -> Any: ...
    def session_embeddings(self) -> Any: ...
    def session_intelligence(self) -> Any: ...
    def documents(self) -> Any: ...
    def tasks(self) -> Any: ...
    def session_usage(self) -> Any: ...
    def entity_links(self) -> Any: ...
    def feature_sessions(self) -> Any: ...
    def tags(self) -> Any: ...
    def features(self) -> Any: ...


@runtime_checkable
class IngestionStateStorage(Protocol):
    def sync_state(self) -> Any: ...


@runtime_checkable
class IntegrationSnapshotStorage(Protocol):
    def pricing_catalog(self) -> Any: ...


@runtime_checkable
class OperationalStateStorage(Protocol):
    def analytics(self) -> Any: ...
    def test_runs(self) -> Any: ...
    def test_definitions(self) -> Any: ...
    def test_results(self) -> Any: ...
    def test_domains(self) -> Any: ...
    def test_mappings(self) -> Any: ...
    def test_integrity(self) -> Any: ...
    def execution(self) -> Any: ...
    def agentic_intelligence(self) -> Any: ...
    def worktree_contexts(self) -> Any: ...


@runtime_checkable
class IdentityAccessStorage(Protocol):
    def principals(self) -> Any: ...
    def scope_identifiers(self) -> Any: ...
    def memberships(self) -> Any: ...
    def role_bindings(self) -> Any: ...


@runtime_checkable
class AuditSecurityStorage(Protocol):
    def privileged_action_audit_records(self) -> Any: ...
    def access_decision_logs(self) -> Any: ...


@runtime_checkable
class StorageUnitOfWork(Protocol):
    @property
    def db(self) -> Any:
        """Return the raw storage connection."""

    def workspace_metadata(self) -> WorkspaceMetadataStorage: ...
    def observed_product(self) -> ObservedProductStorage: ...
    def ingestion_state(self) -> IngestionStateStorage: ...
    def integration_snapshots(self) -> IntegrationSnapshotStorage: ...
    def operational_state(self) -> OperationalStateStorage: ...
    def identity_access(self) -> IdentityAccessStorage: ...
    def audit_security(self) -> AuditSecurityStorage: ...

    def sessions(self) -> Any: ...
    def session_messages(self) -> Any: ...
    def session_embeddings(self) -> Any: ...
    def session_intelligence(self) -> Any: ...
    def documents(self) -> Any: ...
    def tasks(self) -> Any: ...
    def analytics(self) -> Any: ...
    def session_usage(self) -> Any: ...
    def entity_links(self) -> Any: ...
    def feature_sessions(self) -> Any: ...
    def tags(self) -> Any: ...
    def features(self) -> Any: ...
    def sync_state(self) -> Any: ...
    def alert_configs(self) -> Any: ...
    def pricing_catalog(self) -> Any: ...
    def test_runs(self) -> Any: ...
    def test_definitions(self) -> Any: ...
    def test_results(self) -> Any: ...
    def test_domains(self) -> Any: ...
    def test_mappings(self) -> Any: ...
    def test_integrity(self) -> Any: ...
    def execution(self) -> Any: ...
    def agentic_intelligence(self) -> Any: ...
    def worktree_contexts(self) -> Any: ...
    def principals(self) -> Any: ...
    def scope_identifiers(self) -> Any: ...
    def memberships(self) -> Any: ...
    def role_bindings(self) -> Any: ...
    def privileged_action_audit_records(self) -> Any: ...
    def access_decision_logs(self) -> Any: ...


@runtime_checkable
class JobScheduler(Protocol):
    def schedule(self, job: Awaitable[Any], *, name: str | None = None) -> Any:
        """Schedule background work."""


@runtime_checkable
class IntegrationClient(Protocol):
    async def invoke(
        self,
        integration: str,
        operation: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Execute an integration operation."""


@dataclass(frozen=True, slots=True)
class CorePorts:
    identity_provider: IdentityProvider
    authorization_policy: AuthorizationPolicy
    workspace_registry: WorkspaceRegistry
    storage: StorageUnitOfWork
    job_scheduler: JobScheduler
    integration_client: IntegrationClient
