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
    FeatureEvidenceSummary,
    FeatureForensicsDTO,
    FeaturePlanningContextDTO,
    FeatureSummaryItem,
    KeyMetrics,
    NextRunContextRef,
    OpenQuestionResolutionDTO,
    PhaseContextItem,
    PhaseOperationsDTO,
    PhaseTaskItem,
    PlanningArtifactRef,
    PlanningNextRunPreviewDTO,
    PlanningNodeCountsByType,
    PlanningOpenQuestionItem,
    PlanningSpikeItem,
    ProjectPlanningSummaryDTO,
    ProjectPlanningGraphDTO,
    ProjectStatusDTO,
    PromptContextSelection,
    QueryStatus,
    SessionRef,
    SessionSummary,
    SnapshotDiagnosticsDTO,
    TaskRef,
    TimelineData,
    TokenUsageByModel,
    TurningPoint,
    WorkflowDiagnostic,
    WorkflowDiagnosticsDTO,
    WorkflowObservation,
    WorkflowSummary,
)
from backend.application.services.agent_queries.artifact_intelligence import ArtifactIntelligenceQueryService
from backend.application.services.agent_queries.feature_forensics import FeatureForensicsQueryService
from backend.application.services.agent_queries.feature_evidence_summary import FeatureEvidenceSummaryService
from backend.application.services.agent_queries.planning import PlanningQueryService
from backend.application.services.agent_queries.project_status import ProjectStatusQueryService
from backend.application.services.agent_queries.reporting import ReportingQueryService
from backend.application.services.agent_queries.planning_sessions import (
    PlanningAgentSessionBoardDTO,
    PlanningSessionQueryService,
)
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
    "FeatureEvidenceSummary",
    "FeatureEvidenceSummaryService",
    "FeatureForensicsDTO",
    "ArtifactIntelligenceQueryService",
    "KeyMetrics",
    "ProjectStatusDTO",
    "ProjectStatusQueryService",
    "QueryStatus",
    "SessionRef",
    "SessionSummary",
    "SnapshotDiagnosticsDTO",
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
    # Planning query service and DTOs (PCP-201)
    "PlanningQueryService",
    "FeaturePlanningContextDTO",
    "FeatureSummaryItem",
    "OpenQuestionResolutionDTO",
    "PhaseContextItem",
    "PhaseOperationsDTO",
    "PhaseTaskItem",
    "PlanningArtifactRef",
    "PlanningNodeCountsByType",
    "PlanningOpenQuestionItem",
    "PlanningSpikeItem",
    "ProjectPlanningSummaryDTO",
    "ProjectPlanningGraphDTO",
    "TokenUsageByModel",
    # Planning session board (PASB-103)
    "PlanningAgentSessionBoardDTO",
    "PlanningSessionQueryService",
    # Next-run preview (PASB-401)
    "NextRunContextRef",
    "PlanningNextRunPreviewDTO",
    "PromptContextSelection",
]
