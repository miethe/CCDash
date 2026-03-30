"""Shared repository-backed storage unit-of-work primitives."""
from __future__ import annotations

from typing import Any, Callable, Mapping


RepositoryBuilder = Callable[[Any], Any]


class RepositoryBackedStorageUnitOfWork:
    def __init__(self, db: Any, *, repo_builders: Mapping[str, RepositoryBuilder]) -> None:
        self._db = db
        self._repo_builders = dict(repo_builders)
        self._cache: dict[str, Any] = {}

    @property
    def db(self) -> Any:
        return self._db

    def _repo(self, key: str) -> Any:
        if key not in self._cache:
            self._cache[key] = self._repo_builders[key](self._db)
        return self._cache[key]

    def sessions(self) -> Any:
        return self._repo("sessions")

    def session_messages(self) -> Any:
        return self._repo("session_messages")

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
