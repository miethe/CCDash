"""Explicit local storage adapter implementations."""
from __future__ import annotations

from typing import Any

from backend.adapters.storage.base import RepositoryBackedStorageUnitOfWork
from backend.db.repositories.analytics import SqliteAnalyticsRepository
from backend.db.repositories.documents import SqliteDocumentRepository
from backend.db.repositories.execution import SqliteExecutionRepository
from backend.db.repositories.features import SqliteFeatureRepository
from backend.db.repositories.intelligence import SqliteAgenticIntelligenceRepository
from backend.db.repositories.links import (
    SqliteAlertConfigRepository,
    SqliteEntityLinkRepository,
    SqliteSyncStateRepository,
    SqliteTagRepository,
)
from backend.db.repositories.pricing import SqlitePricingCatalogRepository
from backend.db.repositories.session_messages import SqliteSessionMessageRepository
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.repositories.tasks import SqliteTaskRepository
from backend.db.repositories.test_definitions import SqliteTestDefinitionRepository
from backend.db.repositories.test_domains import SqliteTestDomainRepository
from backend.db.repositories.test_integrity import SqliteTestIntegrityRepository
from backend.db.repositories.test_mappings import SqliteTestMappingRepository
from backend.db.repositories.test_results import SqliteTestResultRepository
from backend.db.repositories.test_runs import SqliteTestRunRepository
from backend.db.repositories.usage_attribution import SqliteSessionUsageRepository


class LocalStorageUnitOfWork(RepositoryBackedStorageUnitOfWork):
    def __init__(self, db: Any) -> None:
        super().__init__(
            db,
            repo_builders={
                "sessions": SqliteSessionRepository,
                "session_messages": SqliteSessionMessageRepository,
                "documents": SqliteDocumentRepository,
                "tasks": SqliteTaskRepository,
                "analytics": SqliteAnalyticsRepository,
                "session_usage": SqliteSessionUsageRepository,
                "entity_links": SqliteEntityLinkRepository,
                "tags": SqliteTagRepository,
                "features": SqliteFeatureRepository,
                "sync_state": SqliteSyncStateRepository,
                "alert_configs": SqliteAlertConfigRepository,
                "pricing_catalog": SqlitePricingCatalogRepository,
                "test_runs": SqliteTestRunRepository,
                "test_definitions": SqliteTestDefinitionRepository,
                "test_results": SqliteTestResultRepository,
                "test_domains": SqliteTestDomainRepository,
                "test_mappings": SqliteTestMappingRepository,
                "test_integrity": SqliteTestIntegrityRepository,
                "execution": SqliteExecutionRepository,
                "agentic_intelligence": SqliteAgenticIntelligenceRepository,
            },
        )


class FactoryStorageUnitOfWork(LocalStorageUnitOfWork):
    """Transitional compatibility alias for local-mode call sites and tests."""
