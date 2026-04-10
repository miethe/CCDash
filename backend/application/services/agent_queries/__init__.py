"""Agent query services for CLI and MCP integration.

This package provides transport-neutral query services that power both
the CLI and MCP server implementations. Each service returns structured
DTOs with envelope metadata for consistent error handling and caching.
"""

from backend.application.services.agent_queries.feature_forensics import (
    FeatureForensicsQueryService,
)
from backend.application.services.agent_queries.models import (
    AARReportDTO,
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
    TemporalEnvelopeDTO,
    TimelineData,
    TurningPoint,
    WorkflowDiagnostic,
    WorkflowDiagnosticsDTO,
    WorkflowObservation,
    WorkflowSummary,
)
from backend.application.services.agent_queries.project_status import (
    ProjectStatusQueryService,
)
from backend.application.services.agent_queries.reporting import (
    ReportingQueryService,
)
from backend.application.services.agent_queries.workflow_intelligence import (
    WorkflowDiagnosticsQueryService,
)

__all__ = [
    # Services
    "FeatureForensicsQueryService",
    "ProjectStatusQueryService",
    "ReportingQueryService",
    "WorkflowDiagnosticsQueryService",
    # DTOs
    "AARReportDTO",
    "Bottleneck",
    "CostSummary",
    "DocumentRef",
    "FeatureForensicsDTO",
    "KeyMetrics",
    "ProjectStatusDTO",
    "QueryStatus",
    "SessionRef",
    "SessionSummary",
    "TaskRef",
    "TemporalEnvelopeDTO",
    "TimelineData",
    "TurningPoint",
    "WorkflowDiagnostic",
    "WorkflowDiagnosticsDTO",
    "WorkflowObservation",
    "WorkflowSummary",
]

# Made with Bob
