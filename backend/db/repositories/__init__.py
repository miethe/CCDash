"""Repository package for database access."""

from .sessions import SqliteSessionRepository
from .documents import SqliteDocumentRepository
from .tasks import SqliteTaskRepository
from .features import SqliteFeatureRepository
from .test_runs import SqliteTestRunRepository
from .test_definitions import SqliteTestDefinitionRepository
from .test_results import SqliteTestResultRepository
from .test_domains import SqliteTestDomainRepository
from .test_mappings import SqliteTestMappingRepository
from .test_integrity import SqliteTestIntegrityRepository
from .entity_graph import SqliteEntityLinkRepository, SqliteTagRepository
from .runtime_state import SqliteSyncStateRepository
from .analytics import SqliteAnalyticsRepository
from .execution import SqliteExecutionRepository
from .telemetry_queue import SqliteTelemetryQueueRepository

__all__ = [
    "SqliteSessionRepository",
    "SqliteDocumentRepository",
    "SqliteTaskRepository",
    "SqliteFeatureRepository",
    "SqliteTestRunRepository",
    "SqliteTestDefinitionRepository",
    "SqliteTestResultRepository",
    "SqliteTestDomainRepository",
    "SqliteTestMappingRepository",
    "SqliteTestIntegrityRepository",
    "SqliteEntityLinkRepository",
    "SqliteSyncStateRepository",
    "SqliteTagRepository",
    "SqliteAnalyticsRepository",
    "SqliteExecutionRepository",
    "SqliteTelemetryQueueRepository",
]
