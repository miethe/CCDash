"""Explicit local storage adapter implementations."""
from __future__ import annotations

from typing import Any

from backend.adapters.storage.base import RepositoryBackedStorageUnitOfWork
from backend.db.repositories.analytics import SqliteAnalyticsRepository
from backend.db.repositories.documents import SqliteDocumentRepository
from backend.db.repositories.execution import SqliteExecutionRepository
from backend.db.repositories.features import SqliteFeatureRepository
from backend.db.repositories.intelligence import SqliteAgenticIntelligenceRepository
from backend.db.repositories.identity_access import (
    LocalAccessDecisionLogRepository,
    LocalMembershipRepository,
    LocalPrincipalRepository,
    LocalPrivilegedActionAuditRepository,
    LocalRoleBindingRepository,
    LocalScopeIdentifierRepository,
)
from backend.db.repositories.entity_graph import SqliteEntityLinkRepository, SqliteTagRepository
from backend.db.repositories.feature_sessions import SqliteFeatureSessionRepository
from backend.db.repositories.pricing import SqlitePricingCatalogRepository
from backend.db.repositories.runtime_state import SqliteAlertConfigRepository, SqliteSyncStateRepository
from backend.db.repositories.session_embeddings import SqliteSessionEmbeddingRepository
from backend.db.repositories.session_intelligence import SqliteSessionIntelligenceRepository
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
from backend.db.repositories.worktree_contexts import SqliteWorktreeContextRepository


class LocalStorageUnitOfWork(RepositoryBackedStorageUnitOfWork):
    def __init__(self, db: Any) -> None:
        super().__init__(
            db,
            repo_builders={
                "sessions": SqliteSessionRepository,
                "session_messages": SqliteSessionMessageRepository,
                "session_embeddings": SqliteSessionEmbeddingRepository,
                "session_intelligence": SqliteSessionIntelligenceRepository,
                "documents": SqliteDocumentRepository,
                "tasks": SqliteTaskRepository,
                "analytics": SqliteAnalyticsRepository,
                "session_usage": SqliteSessionUsageRepository,
                "entity_links": SqliteEntityLinkRepository,
                "feature_sessions": SqliteFeatureSessionRepository,
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
                "worktree_contexts": SqliteWorktreeContextRepository,
                "principals": LocalPrincipalRepository,
                "scope_identifiers": LocalScopeIdentifierRepository,
                "memberships": LocalMembershipRepository,
                "role_bindings": LocalRoleBindingRepository,
                "privileged_action_audit_records": LocalPrivilegedActionAuditRepository,
                "access_decision_logs": LocalAccessDecisionLogRepository,
            },
        )


class FactoryStorageUnitOfWork(LocalStorageUnitOfWork):
    """Transitional compatibility alias for local-mode call sites and tests."""
