"""Shared repository-backed storage unit-of-work primitives."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


RepositoryBuilder = Callable[[Any], Any]


@dataclass(frozen=True)
class _RepositoryDomainView:
    _uow: "RepositoryBackedStorageUnitOfWork"
    _keys: tuple[str, ...]

    def _repo(self, key: str) -> Any:
        if key not in self._keys:
            raise AttributeError(f"Repository '{key}' is not part of this domain view")
        return self._uow._repo(key)


class _WorkspaceMetadataView(_RepositoryDomainView):
    def alert_configs(self) -> Any:
        return self._repo("alert_configs")


class _ObservedProductView(_RepositoryDomainView):
    def sessions(self) -> Any:
        return self._repo("sessions")

    def session_messages(self) -> Any:
        return self._repo("session_messages")

    def session_embeddings(self) -> Any:
        return self._repo("session_embeddings")

    def documents(self) -> Any:
        return self._repo("documents")

    def tasks(self) -> Any:
        return self._repo("tasks")

    def session_usage(self) -> Any:
        return self._repo("session_usage")

    def entity_links(self) -> Any:
        return self._repo("entity_links")

    def tags(self) -> Any:
        return self._repo("tags")

    def features(self) -> Any:
        return self._repo("features")


class _IngestionStateView(_RepositoryDomainView):
    def sync_state(self) -> Any:
        return self._repo("sync_state")


class _IntegrationSnapshotView(_RepositoryDomainView):
    def pricing_catalog(self) -> Any:
        return self._repo("pricing_catalog")


class _OperationalStateView(_RepositoryDomainView):
    def analytics(self) -> Any:
        return self._repo("analytics")

    def test_runs(self) -> Any:
        return self._repo("test_runs")

    def test_definitions(self) -> Any:
        return self._repo("test_definitions")

    def test_results(self) -> Any:
        return self._repo("test_results")

    def test_domains(self) -> Any:
        return self._repo("test_domains")

    def test_mappings(self) -> Any:
        return self._repo("test_mappings")

    def test_integrity(self) -> Any:
        return self._repo("test_integrity")

    def execution(self) -> Any:
        return self._repo("execution")

    def agentic_intelligence(self) -> Any:
        return self._repo("agentic_intelligence")


class _IdentityAccessView(_RepositoryDomainView):
    def principals(self) -> Any:
        return self._repo("principals")

    def scope_identifiers(self) -> Any:
        return self._repo("scope_identifiers")

    def memberships(self) -> Any:
        return self._repo("memberships")

    def role_bindings(self) -> Any:
        return self._repo("role_bindings")


class _AuditSecurityView(_RepositoryDomainView):
    def privileged_action_audit_records(self) -> Any:
        return self._repo("privileged_action_audit_records")

    def access_decision_logs(self) -> Any:
        return self._repo("access_decision_logs")


class RepositoryBackedStorageUnitOfWork:
    def __init__(self, db: Any, *, repo_builders: Mapping[str, RepositoryBuilder]) -> None:
        self._db = db
        self._repo_builders = dict(repo_builders)
        self._cache: dict[str, Any] = {}
        self._workspace_metadata_view = _WorkspaceMetadataView(self, ("alert_configs",))
        self._observed_product_view = _ObservedProductView(
            self,
            (
                "sessions",
                "session_messages",
                "session_embeddings",
                "documents",
                "tasks",
                "session_usage",
                "entity_links",
                "tags",
                "features",
            ),
        )
        self._ingestion_state_view = _IngestionStateView(self, ("sync_state",))
        self._integration_snapshot_view = _IntegrationSnapshotView(self, ("pricing_catalog",))
        self._operational_state_view = _OperationalStateView(
            self,
            (
                "analytics",
                "test_runs",
                "test_definitions",
                "test_results",
                "test_domains",
                "test_mappings",
                "test_integrity",
                "execution",
                "agentic_intelligence",
            ),
        )
        self._identity_access_view = _IdentityAccessView(
            self,
            (
                "principals",
                "scope_identifiers",
                "memberships",
                "role_bindings",
            ),
        )
        self._audit_security_view = _AuditSecurityView(
            self,
            (
                "privileged_action_audit_records",
                "access_decision_logs",
            ),
        )

    @property
    def db(self) -> Any:
        return self._db

    def workspace_metadata(self) -> _WorkspaceMetadataView:
        return self._workspace_metadata_view

    def observed_product(self) -> _ObservedProductView:
        return self._observed_product_view

    def ingestion_state(self) -> _IngestionStateView:
        return self._ingestion_state_view

    def integration_snapshots(self) -> _IntegrationSnapshotView:
        return self._integration_snapshot_view

    def operational_state(self) -> _OperationalStateView:
        return self._operational_state_view

    def identity_access(self) -> _IdentityAccessView:
        return self._identity_access_view

    def audit_security(self) -> _AuditSecurityView:
        return self._audit_security_view

    def _repo(self, key: str) -> Any:
        if key not in self._cache:
            self._cache[key] = self._repo_builders[key](self._db)
        return self._cache[key]

    def sessions(self) -> Any:
        return self._repo("sessions")

    def session_messages(self) -> Any:
        return self._repo("session_messages")

    def session_embeddings(self) -> Any:
        return self._repo("session_embeddings")

    def documents(self) -> Any:
        return self._repo("documents")

    def tasks(self) -> Any:
        return self._repo("tasks")

    def analytics(self) -> Any:
        return self._repo("analytics")

    def session_usage(self) -> Any:
        return self._repo("session_usage")

    def entity_links(self) -> Any:
        return self._repo("entity_links")

    def tags(self) -> Any:
        return self._repo("tags")

    def features(self) -> Any:
        return self._repo("features")

    def sync_state(self) -> Any:
        return self._repo("sync_state")

    def alert_configs(self) -> Any:
        return self._repo("alert_configs")

    def pricing_catalog(self) -> Any:
        return self._repo("pricing_catalog")

    def test_runs(self) -> Any:
        return self._repo("test_runs")

    def test_definitions(self) -> Any:
        return self._repo("test_definitions")

    def test_results(self) -> Any:
        return self._repo("test_results")

    def test_domains(self) -> Any:
        return self._repo("test_domains")

    def test_mappings(self) -> Any:
        return self._repo("test_mappings")

    def test_integrity(self) -> Any:
        return self._repo("test_integrity")

    def execution(self) -> Any:
        return self._repo("execution")

    def agentic_intelligence(self) -> Any:
        return self._repo("agentic_intelligence")

    def principals(self) -> Any:
        return self._repo("principals")

    def scope_identifiers(self) -> Any:
        return self._repo("scope_identifiers")

    def memberships(self) -> Any:
        return self._repo("memberships")

    def role_bindings(self) -> Any:
        return self._repo("role_bindings")

    def privileged_action_audit_records(self) -> Any:
        return self._repo("privileged_action_audit_records")

    def access_decision_logs(self) -> Any:
        return self._repo("access_decision_logs")
