"""Local SQLite-backed StorageUnitOfWork adapter.

Implements the existing StorageUnitOfWork port using the repository factory
helpers. This is the explicit adapter for the "local" storage profile.

Note: This duplicates the lightweight behavior of the previous
FactoryStorageUnitOfWork while making the composition choice explicit at the
runtime layer. The factory-backed bridge remains for internal compatibility
only and should not be imported by new code.
"""
from __future__ import annotations

from typing import Any, Callable

from backend.db import factory


class LocalStorageUnitOfWork:
    def __init__(self, db: Any):
        self._db = db
        self._cache: dict[str, Any] = {}

    @property
    def db(self) -> Any:
        return self._db

    def _repo(self, key: str, builder: Callable[[Any], Any]) -> Any:
        if key not in self._cache:
            self._cache[key] = builder(self._db)
        return self._cache[key]

    # Port methods
    def sessions(self) -> Any:
        return self._repo("sessions", factory.get_session_repository)

    def session_messages(self) -> Any:
        return self._repo("session_messages", factory.get_session_message_repository)

    def documents(self) -> Any:
        return self._repo("documents", factory.get_document_repository)

    def tasks(self) -> Any:
        return self._repo("tasks", factory.get_task_repository)

    def analytics(self) -> Any:
        return self._repo("analytics", factory.get_analytics_repository)

    def session_usage(self) -> Any:
        return self._repo("session_usage", factory.get_session_usage_repository)

    def entity_links(self) -> Any:
        return self._repo("entity_links", factory.get_entity_link_repository)

    def tags(self) -> Any:
        return self._repo("tags", factory.get_tag_repository)

    def features(self) -> Any:
        return self._repo("features", factory.get_feature_repository)

    def sync_state(self) -> Any:
        return self._repo("sync_state", factory.get_sync_state_repository)

    def alert_configs(self) -> Any:
        return self._repo("alert_configs", factory.get_alert_config_repository)

    def pricing_catalog(self) -> Any:
        return self._repo("pricing_catalog", factory.get_pricing_catalog_repository)

    def test_runs(self) -> Any:
        return self._repo("test_runs", factory.get_test_run_repository)

    def test_definitions(self) -> Any:
        return self._repo("test_definitions", factory.get_test_definition_repository)

    def test_results(self) -> Any:
        return self._repo("test_results", factory.get_test_result_repository)

    def test_domains(self) -> Any:
        return self._repo("test_domains", factory.get_test_domain_repository)

    def test_mappings(self) -> Any:
        return self._repo("test_mappings", factory.get_test_mapping_repository)

    def test_integrity(self) -> Any:
        return self._repo("test_integrity", factory.get_test_integrity_repository)

    def execution(self) -> Any:
        return self._repo("execution", factory.get_execution_repository)

    def agentic_intelligence(self) -> Any:
        return self._repo("agentic_intelligence", factory.get_agentic_intelligence_repository)

