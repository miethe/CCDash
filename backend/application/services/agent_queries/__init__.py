"""Transport-neutral agent query service contracts and helpers."""

from backend.application.services.agent_queries import cache
from backend.application.services.agent_queries.cache import (
    _query_cache,
    clear_cache,
    compute_cache_key,
    get_cache,
    get_data_version_fingerprint,
)
from backend.application.services.agent_queries._filters import (
    AgentQueryProjectScope,
    collect_source_refs,
    derive_data_freshness,
    normalize_entity_ids,
    resolve_project_scope,
    resolve_time_window,
)
from backend.application.services.agent_queries.models import (
    AARReportDTO,
    AgentQueryEnvelope,
    Bottleneck,
    CostSummary,
    DocumentRef,
    FeatureForensicsDTO,
    KeyMetrics,
    ProjectStatusDTO,
    QueryStatus,
    SessionRef,
    SessionSummary,
    TaskRef,
    TimelineData,
    TurningPoint,
    WorkflowDiagnostic,
    WorkflowDiagnosticsDTO,
    WorkflowObservation,
    WorkflowSummary,
)
from backend.application.services.agent_queries.feature_forensics import FeatureForensicsQueryService
from backend.application.services.agent_queries.project_status import ProjectStatusQueryService
from backend.application.services.agent_queries.reporting import ReportingQueryService
from backend.application.services.agent_queries.workflow_intelligence import WorkflowDiagnosticsQueryService

__all__ = [
    # Cache module and helpers (CACHE-003)
    "cache",
    "_query_cache",
    "clear_cache",
    "compute_cache_key",
    "get_cache",
    "get_data_version_fingerprint",
    # DTOs and shared contracts
    "AARReportDTO",
    "AgentQueryEnvelope",
    "AgentQueryProjectScope",
    "Bottleneck",
    "CostSummary",
    "DocumentRef",
    "FeatureForensicsDTO",
    "KeyMetrics",
    "ProjectStatusDTO",
    "ProjectStatusQueryService",
    "QueryStatus",
    "SessionRef",
    "SessionSummary",
    "TaskRef",
    "TimelineData",
    "TurningPoint",
    "WorkflowDiagnostic",
    "WorkflowDiagnosticsDTO",
    "WorkflowDiagnosticsQueryService",
    "FeatureForensicsQueryService",
    "ReportingQueryService",
    "WorkflowObservation",
    "WorkflowSummary",
    "collect_source_refs",
    "derive_data_freshness",
    "normalize_entity_ids",
    "resolve_project_scope",
    "resolve_time_window",
]
