"""Shared DTO contracts for transport-neutral agent query services."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


QueryStatus = Literal["ok", "partial", "error"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentQueryEnvelope(BaseModel):
    """Common response envelope for all agent query services.

    Status semantics:
    - ``ok``: the primary entity resolved and all required supporting sources loaded
    - ``partial``: the primary entity resolved but one or more supporting sources were unavailable
    - ``error``: the primary entity or request scope could not be resolved
    """

    status: QueryStatus = "ok"
    data_freshness: datetime = Field(default_factory=_utc_now)
    generated_at: datetime = Field(default_factory=_utc_now)
    source_refs: list[str] = Field(default_factory=list)


class SessionSummary(BaseModel):
    session_id: str
    feature_id: str = ""
    root_session_id: str = ""
    title: str = ""
    status: str = ""
    started_at: str = ""
    ended_at: str = ""
    model: str = ""
    total_cost: float = 0.0
    total_tokens: int = 0
    workflow_refs: list[str] = Field(default_factory=list)


class SessionRef(SessionSummary):
    duration_seconds: float = 0.0
    tool_names: list[str] = Field(default_factory=list)
    source_ref: str = ""


class CostSummary(BaseModel):
    total_cost: float = 0.0
    total_tokens: int = 0
    by_model: dict[str, float] = Field(default_factory=dict)
    by_workflow: dict[str, float] = Field(default_factory=dict)


class WorkflowSummary(BaseModel):
    workflow_id: str
    workflow_name: str = ""
    session_count: int = 0
    success_rate: float = 0.0
    last_observed_at: str = ""
    representative_session_ids: list[str] = Field(default_factory=list)


class WorkflowDiagnostic(BaseModel):
    workflow_id: str
    workflow_name: str = ""
    effectiveness_score: float = 0.0
    session_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    cost_efficiency: float = 0.0
    common_failures: list[str] = Field(default_factory=list)
    representative_sessions: list[SessionRef] = Field(default_factory=list)


class DocumentRef(BaseModel):
    document_id: str
    title: str = ""
    file_path: str = ""
    canonical_path: str = ""
    doc_type: str = ""
    status: str = ""
    updated_at: str = ""
    feature_slug: str = ""


class TaskRef(BaseModel):
    task_id: str
    title: str = ""
    status: str = ""
    priority: str = ""
    owner: str = ""
    phase_id: str = ""
    updated_at: str = ""


class TimelineData(BaseModel):
    started_at: str = ""
    ended_at: str = ""
    duration_days: float = 0.0


class KeyMetrics(BaseModel):
    total_cost: float = 0.0
    total_tokens: int = 0
    session_count: int = 0
    iteration_count: int = 0


class TurningPoint(BaseModel):
    timestamp: str = ""
    event: str = ""
    impact: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class WorkflowObservation(BaseModel):
    workflow_id: str
    workflow_name: str = ""
    frequency: int = 0
    effectiveness_score: float = 0.0
    notes: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class Bottleneck(BaseModel):
    description: str
    cost_impact: float = 0.0
    sessions_affected: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class ProjectStatusDTO(AgentQueryEnvelope):
    project_id: str
    project_name: str = ""
    feature_counts: dict[str, int] = Field(default_factory=dict)
    recent_sessions: list[SessionSummary] = Field(default_factory=list)
    cost_last_7d: CostSummary = Field(default_factory=CostSummary)
    top_workflows: list[WorkflowSummary] = Field(default_factory=list)
    sync_freshness: datetime | None = None
    blocked_features: list[str] = Field(default_factory=list)


class TelemetryAvailability(BaseModel):
    """Indicates whether each evidence category contains populated data."""

    tasks: bool = False
    documents: bool = False
    sessions: bool = False


class TokenUsageByModel(BaseModel):
    """Per-feature token rollup bucketed by normalized model family."""

    opus: int = 0
    sonnet: int = 0
    haiku: int = 0
    other: int = 0
    total: int = 0


class PlanningArtifactRef(BaseModel):
    """Artifact reference grouped into planning payload buckets."""

    artifact_id: str = ""
    title: str = ""
    file_path: str = ""
    canonical_path: str = ""
    doc_type: str = ""
    status: str = ""
    updated_at: str = ""
    source_ref: str = ""


class PlanningSpikeItem(BaseModel):
    """Derived SPIKE item for the planning drawer payload."""

    spike_id: str = ""
    title: str = ""
    status: str = ""
    file_path: str = ""
    source_ref: str = ""


class PlanningOpenQuestionItem(BaseModel):
    """Open-question state surfaced in the planning feature payload."""

    oq_id: str = ""
    question: str = ""
    severity: str = "medium"
    answer_text: str = ""
    resolved: bool = False
    pending_sync: bool = False
    source_document_id: str = ""
    source_document_path: str = ""
    updated_at: str = ""


class FeatureForensicsDTO(AgentQueryEnvelope):
    """Feature execution history and evidence forensics.

    Alias fields: ``name`` mirrors the canonical feature name; ``feature_status`` is the
    feature lifecycle status. Use ``feature_status`` (not the envelope ``status``) for
    feature state — the envelope ``status`` represents query-result status (ok/partial/error).
    ``telemetry_available`` indicates data completeness (tasks/documents/sessions populated).
    """

    feature_id: str
    feature_slug: str = ""
    feature_status: str = ""
    name: str = ""
    telemetry_available: TelemetryAvailability = Field(default_factory=TelemetryAvailability)
    linked_sessions: list[SessionRef] = Field(default_factory=list)
    linked_documents: list[DocumentRef] = Field(default_factory=list)
    linked_tasks: list[TaskRef] = Field(default_factory=list)
    iteration_count: int = 0
    total_cost: float = 0.0
    total_tokens: int = 0
    token_usage_by_model: TokenUsageByModel = Field(default_factory=TokenUsageByModel)
    workflow_mix: dict[str, float] = Field(default_factory=dict)
    rework_signals: list[str] = Field(default_factory=list)
    failure_patterns: list[str] = Field(default_factory=list)
    representative_sessions: list[SessionRef] = Field(default_factory=list)
    summary_narrative: str = ""
    sessions_note: str = (
        "Session linkage is eventually-consistent (populated by the background sync engine). "
        "For the canonical session list use GET /v1/features/{id}/sessions."
    )


class WorkflowDiagnosticsDTO(AgentQueryEnvelope):
    project_id: str
    feature_id: str | None = None
    workflows: list[WorkflowDiagnostic] = Field(default_factory=list)
    top_performers: list[WorkflowDiagnostic] = Field(default_factory=list)
    problem_workflows: list[WorkflowDiagnostic] = Field(default_factory=list)


class AARReportDTO(AgentQueryEnvelope):
    feature_id: str
    feature_slug: str = ""
    scope_statement: str = ""
    timeline: TimelineData = Field(default_factory=TimelineData)
    key_metrics: KeyMetrics = Field(default_factory=KeyMetrics)
    turning_points: list[TurningPoint] = Field(default_factory=list)
    workflow_observations: list[WorkflowObservation] = Field(default_factory=list)
    bottlenecks: list[Bottleneck] = Field(default_factory=list)
    successful_patterns: list[str] = Field(default_factory=list)
    lessons_learned: list[str] = Field(default_factory=list)
    evidence_links: list[str] = Field(default_factory=list)


# ── Planning query DTOs (PCP-201) ────────────────────────────────────────────
# These DTOs wrap the backend/models.py planning primitives (PlanningNode,
# PlanningEdge, PlanningGraph, PlanningEffectiveStatus, PlanningPhaseBatch)
# and add the standard agent-query envelope fields.  They use snake_case field
# names with camelCase JSON aliases to match the pattern of the existing DTOs
# above.  The raw planning model types from backend.models are imported inline
# to avoid circular imports at module load time.


class PlanningStatusCounts(BaseModel):
    """Mutually exclusive bucket counts across all features in a project."""

    shaping: int = 0
    planned: int = 0
    active: int = 0
    blocked: int = 0
    review: int = 0
    completed: int = 0
    deferred: int = 0
    stale_or_mismatched: int = 0


class PlanningCtxPerPhase(BaseModel):
    """Context-document-to-phase ratio for the project."""

    context_count: int = 0
    phase_count: int = 0
    ratio: float | None = None
    source: Literal["backend", "unavailable"] = "unavailable"


class PlanningTokenTelemetryEntry(BaseModel):
    """Per-model-family token rollup entry."""

    model_family: str
    total_tokens: int


class PlanningTokenTelemetry(BaseModel):
    """Project-level token telemetry aggregated from session attribution."""

    total_tokens: int | None = None
    by_model_family: list[PlanningTokenTelemetryEntry] = Field(default_factory=list)
    source: Literal["session_attribution", "unavailable"] = "unavailable"


class FeatureSummaryItem(BaseModel):
    """Lightweight per-feature summary used in project-level planning views."""

    feature_id: str
    feature_name: str = ""
    raw_status: str = ""
    effective_status: str = ""
    is_mismatch: bool = False
    mismatch_state: str = "unknown"
    has_blocked_phases: bool = False
    phase_count: int = 0
    blocked_phase_count: int = 0
    node_count: int = 0
    source_artifact_kind: Literal["feature", "design_spec", "prd"] = "feature"


class PlanningNodeCountsByType(BaseModel):
    """Counts of PlanningNode instances bucketed by PlanningNodeType."""

    prd: int = 0
    design_spec: int = 0
    implementation_plan: int = 0
    progress: int = 0
    context: int = 0
    tracker: int = 0
    report: int = 0


class ProjectPlanningSummaryDTO(AgentQueryEnvelope):
    """Project-level planning health summary (PCP-201, query 1).

    Provides aggregate counts and status snapshots without returning raw
    graph data.  Use ``ProjectPlanningGraphDTO`` when you need node/edge lists.

    Field notes:
    - ``stale_feature_ids`` — features whose raw status is terminal but whose
      phase or document evidence does not yet corroborate completion.
    - ``reversal_feature_ids`` — features where a planning mismatch of type
      ``reversed`` was detected (raw status is ahead of evidence).
    - ``mismatch_count`` — total count of features with *any* mismatch state
      that is not ``aligned``.
    """

    project_id: str
    project_name: str = ""
    total_feature_count: int = 0
    planned_feature_count: int = 0
    active_feature_count: int = 0
    stale_feature_count: int = 0
    blocked_feature_count: int = 0
    mismatch_count: int = 0
    reversal_count: int = 0
    stale_feature_ids: list[str] = Field(default_factory=list)
    reversal_feature_ids: list[str] = Field(default_factory=list)
    blocked_feature_ids: list[str] = Field(default_factory=list)
    node_counts_by_type: PlanningNodeCountsByType = Field(
        default_factory=PlanningNodeCountsByType
    )
    feature_summaries: list[FeatureSummaryItem] = Field(default_factory=list)
    status_counts: PlanningStatusCounts | None = None
    ctx_per_phase: PlanningCtxPerPhase | None = None
    token_telemetry: PlanningTokenTelemetry | None = None


class ProjectPlanningGraphDTO(AgentQueryEnvelope):
    """Aggregated planning graph for a project or feature seed (PCP-201, query 2).

    When ``feature_id`` is supplied the graph is scoped to that feature's
    subgraph (plus family-level relationships).  When omitted all features
    in the project are included.

    The ``nodes`` and ``edges`` lists are flat representations of
    ``PlanningNode`` / ``PlanningEdge`` models from ``backend.models``.  They
    are serialised as plain dicts here so the DTO remains JSON-serialisable
    without a separate Pydantic discriminator layer.
    """

    project_id: str
    feature_id: str | None = None
    depth: int | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    phase_batches: list[dict[str, Any]] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0


class PhaseContextItem(BaseModel):
    """One phase's planning context inside ``FeaturePlanningContextDTO``."""

    phase_id: str = ""
    phase_token: str = ""
    phase_title: str = ""
    raw_status: str = ""
    effective_status: str = ""
    is_mismatch: bool = False
    mismatch_state: str = "unknown"
    planning_status: dict[str, Any] = Field(default_factory=dict)
    batches: list[dict[str, Any]] = Field(default_factory=list)
    blocked_batch_ids: list[str] = Field(default_factory=list)
    total_tasks: int = 0
    completed_tasks: int = 0
    deferred_tasks: int = 0


class FeaturePlanningContextDTO(AgentQueryEnvelope):
    """Single-feature planning context including graph, status, and phases (PCP-201, query 3).

    Preserves raw vs effective status provenance — never collapse them.
    ``planning_status`` is the feature-level ``PlanningEffectiveStatus`` serialised
    as a dict.  ``mismatch_state`` is a convenience copy of
    ``planning_status.mismatchState.state`` for quick filtering.
    """

    feature_id: str
    feature_name: str = ""
    raw_status: str = ""
    effective_status: str = ""
    mismatch_state: str = "unknown"
    planning_status: dict[str, Any] = Field(default_factory=dict)
    graph: dict[str, Any] = Field(default_factory=dict)
    phases: list[PhaseContextItem] = Field(default_factory=list)
    blocked_batch_ids: list[str] = Field(default_factory=list)
    linked_artifact_refs: list[str] = Field(default_factory=list)
    specs: list[PlanningArtifactRef] = Field(default_factory=list)
    prds: list[PlanningArtifactRef] = Field(default_factory=list)
    plans: list[PlanningArtifactRef] = Field(default_factory=list)
    ctxs: list[PlanningArtifactRef] = Field(default_factory=list)
    reports: list[PlanningArtifactRef] = Field(default_factory=list)
    spikes: list[PlanningSpikeItem] = Field(default_factory=list)
    open_questions: list[PlanningOpenQuestionItem] = Field(default_factory=list)
    ready_to_promote: bool = False
    is_stale: bool = False
    total_tokens: int = 0
    token_usage_by_model: TokenUsageByModel = Field(default_factory=TokenUsageByModel)


class OpenQuestionResolutionDTO(BaseModel):
    """Transport-neutral response payload for OQ resolution writes."""

    feature_id: str
    oq: PlanningOpenQuestionItem


class PhaseTaskItem(BaseModel):
    """Task summary within a phase operations response."""

    task_id: str = ""
    title: str = ""
    status: str = ""
    assignees: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    batch_id: str = ""


class PhaseOperationsDTO(AgentQueryEnvelope):
    """Operational detail for a single phase (PCP-201, query 4).

    Returns batch readiness, per-task assignee / blocker data, and any
    evidence extracted from progress frontmatter.  ``phase_batches`` preserves
    the ``parallelization.batch_N`` semantics from ``PlanningPhaseBatch``.
    ``dependency_resolution`` summarises whether the phase's upstream
    dependencies are cleared.
    """

    feature_id: str
    phase_number: int
    phase_token: str = ""
    phase_title: str = ""
    raw_status: str = ""
    effective_status: str = ""
    is_ready: bool = False
    readiness_state: str = "unknown"
    phase_batches: list[dict[str, Any]] = Field(default_factory=list)
    blocked_batch_ids: list[str] = Field(default_factory=list)
    tasks: list[PhaseTaskItem] = Field(default_factory=list)
    dependency_resolution: dict[str, Any] = Field(default_factory=dict)
    progress_evidence: list[str] = Field(default_factory=list)
