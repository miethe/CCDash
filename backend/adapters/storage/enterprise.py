"""Explicit enterprise storage adapter implementations."""
from __future__ import annotations

from typing import Any

from backend.adapters.storage.base import RepositoryBackedStorageUnitOfWork
from backend.db.repositories.postgres.analytics import PostgresAnalyticsRepository
from backend.db.repositories.postgres.documents import PostgresDocumentRepository
from backend.db.repositories.postgres.execution import PostgresExecutionRepository
from backend.db.repositories.postgres.features import PostgresFeatureRepository
from backend.db.repositories.postgres.identity_access import (
    PostgresAccessDecisionLogRepository,
    PostgresMembershipRepository,
    PostgresPrincipalRepository,
    PostgresPrivilegedActionAuditRepository,
    PostgresRoleBindingRepository,
    PostgresScopeIdentifierRepository,
)
from backend.db.repositories.postgres.intelligence import PostgresAgenticIntelligenceRepository
from backend.db.repositories.postgres.entity_graph import PostgresEntityLinkRepository, PostgresTagRepository
from backend.db.repositories.postgres.pricing import PostgresPricingCatalogRepository
from backend.db.repositories.postgres.runtime_state import (
    PostgresAlertConfigRepository,
    PostgresSyncStateRepository,
)
from backend.db.repositories.postgres.session_embeddings import PostgresSessionEmbeddingRepository
from backend.db.repositories.postgres.session_intelligence import PostgresSessionIntelligenceRepository
from backend.db.repositories.postgres.session_messages import PostgresSessionMessageRepository
from backend.db.repositories.postgres.sessions import PostgresSessionRepository
from backend.db.repositories.postgres.tasks import PostgresTaskRepository
from backend.db.repositories.postgres.test_definitions import PostgresTestDefinitionRepository
from backend.db.repositories.postgres.test_domains import PostgresTestDomainRepository
from backend.db.repositories.postgres.test_integrity import PostgresTestIntegrityRepository
from backend.db.repositories.postgres.test_mappings import PostgresTestMappingRepository
from backend.db.repositories.postgres.test_results import PostgresTestResultRepository
from backend.db.repositories.postgres.test_runs import PostgresTestRunRepository
from backend.db.repositories.postgres.usage_attribution import PostgresSessionUsageRepository


class EnterpriseStorageUnitOfWork(RepositoryBackedStorageUnitOfWork):
    def __init__(self, db: Any) -> None:
        super().__init__(
            db,
            repo_builders={
                "sessions": PostgresSessionRepository,
                "session_messages": PostgresSessionMessageRepository,
                "session_embeddings": PostgresSessionEmbeddingRepository,
                "session_intelligence": PostgresSessionIntelligenceRepository,
                "documents": PostgresDocumentRepository,
                "tasks": PostgresTaskRepository,
                "analytics": PostgresAnalyticsRepository,
                "session_usage": PostgresSessionUsageRepository,
                "entity_links": PostgresEntityLinkRepository,
                "tags": PostgresTagRepository,
                "features": PostgresFeatureRepository,
                "sync_state": PostgresSyncStateRepository,
                "alert_configs": PostgresAlertConfigRepository,
                "pricing_catalog": PostgresPricingCatalogRepository,
                "test_runs": PostgresTestRunRepository,
                "test_definitions": PostgresTestDefinitionRepository,
                "test_results": PostgresTestResultRepository,
                "test_domains": PostgresTestDomainRepository,
                "test_mappings": PostgresTestMappingRepository,
                "test_integrity": PostgresTestIntegrityRepository,
                "execution": PostgresExecutionRepository,
                "agentic_intelligence": PostgresAgenticIntelligenceRepository,
                "principals": PostgresPrincipalRepository,
                "scope_identifiers": PostgresScopeIdentifierRepository,
                "memberships": PostgresMembershipRepository,
                "role_bindings": PostgresRoleBindingRepository,
                "privileged_action_audit_records": PostgresPrivilegedActionAuditRepository,
                "access_decision_logs": PostgresAccessDecisionLogRepository,
            },
        )
