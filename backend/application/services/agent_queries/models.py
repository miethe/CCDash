"""Shared DTO contracts for transport-neutral agent query services."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


QueryStatus = Literal["ok", "partial", "error"]
PlanningCommandRuleId = Literal[
    "PCC-CMD-001",
    "PCC-CMD-002",
    "PCC-CMD-003",
    "PCC-CMD-004",
    "PCC-CMD-005",
    "PCC-CMD-006",
    "PCC-CMD-007",
    "PCC-CMD-008",
    "PCC-CMD-009",
]


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


class FeatureEvidenceSummary(AgentQueryEnvelope):
    """Bounded evidence summary for planning surfaces — lighter than FeatureForensicsDTO."""

    feature_id: str
    feature_slug: str = ""
    feature_status: str = ""
    name: str = ""
    session_count: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    token_usage_by_model: TokenUsageByModel = Field(default_factory=TokenUsageByModel)
    workflow_mix: dict[str, float] = Field(default_factory=dict)
    latest_activity: datetime | None = None
    telemetry_available: TelemetryAvailability = Field(default_factory=TelemetryAvailability)


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


class SnapshotDiagnosticsDTO(AgentQueryEnvelope):
    project_id: str
    snapshot_age_seconds: int | None = None
    artifact_count: int = 0
    resolved_count: int = 0
    unresolved_count: int = 0
    is_stale: bool = True


class ArtifactRankingsDTO(AgentQueryEnvelope):
    project_id: str
    period: str = "30d"
    total: int = 0
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ArtifactRecommendationsDTO(AgentQueryEnvelope):
    project_id: str
    period: str = "30d"
    total: int = 0
    recommendations: list[dict[str, Any]] = Field(default_factory=list)


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


class AARReviewFlag(BaseModel):
    """One deterministic surface-issue signal computed for an AAR review.

    Each flag is a threshold/lookup/regex check over already-materialized DB
    rows -- never a model/semantic judgment (ccdash-aar-review-mvp §8 Hard
    Invariant).
    """

    flag_id: str
    triggered: bool = False
    severity: Literal["low", "medium", "high"] = "low"
    evidence_refs: list[str] = Field(default_factory=list)
    rationale: str = ""


class AARReviewCorrelation(BaseModel):
    """Nested document->session correlation result (PRD §7.2).

    ``confidence`` is ``None`` when correlation fails entirely (i.e.
    ``session_ids`` is empty) -- per the OQ-2 verdict decision, a null
    confidence always routes ``AARReviewDTO.triage_verdict`` to
    ``human_triage_required``, never ``surface_only``. The correlation
    ``strategy`` string is whatever ``aar_review.py`` resolves it to
    (``explicit_session_ref``, a link's ``linkStrategy`` metadata value, or
    ``two_hop_doc_feature_session``) -- see that module for the exact set.
    """

    strategy: str | None = None
    confidence: float | None = None
    session_ids: list[str] = Field(default_factory=list)
    feature_id: str | None = None


class AARReviewDTO(BaseModel):
    """Deterministic AAR-document-to-session triage verdict.

    Canonical shape per the ``ccdash-automated-aar-review-v1`` PRD §7.2
    (``schema_version`` 2): a nested ``correlation`` object plus a 3-value
    ``triage_verdict`` enum (``surface_only`` | ``deep_review_recommended`` |
    ``human_triage_required``).

    DEPRECATED ALIASES: ``session_refs``, ``correlation_confidence``,
    ``correlation_strategy``, and ``verdict`` are the pre-§7.2 Tier-1-MVP
    flat fields. They are kept -- auto-synced from the nested values by
    ``_sync_deprecated_aliases`` below -- for one release window so existing
    consumers do not break. Do not read them in new code; do not remove them
    before the next major ``schema_version`` bump (>= 3).

    Intentionally **not** an ``AgentQueryEnvelope`` subclass -- this shape is
    frozen by the feature contract's §6/§7.2 Data Requirements
    (``generated_at`` is a plain ISO-8601 string here, not a ``datetime``,
    and there is no ``data_freshness`` field).
    """

    schema_version: int = 2
    status: Literal["ok", "error"] = "ok"
    document_id: str
    correlation: AARReviewCorrelation = Field(default_factory=AARReviewCorrelation)
    flags: list[AARReviewFlag] = Field(default_factory=list)
    triage_verdict: Literal["surface_only", "deep_review_recommended", "human_triage_required"] | None = None
    reasons: list[str] = Field(default_factory=list)
    generated_at: str = ""
    source_refs: list[str] = Field(default_factory=list)

    # ── Deprecated flat aliases (Tier-1 MVP shape) ───────────────────────────
    # Removal window: not before schema_version >= 3. Populated verbatim from
    # the nested `correlation`/`triage_verdict` fields by the validator below
    # -- callers should set `correlation=` and `triage_verdict=` only.
    session_refs: list[str] = Field(default_factory=list)
    correlation_confidence: float | None = None
    correlation_strategy: str | None = None
    verdict: Literal["surface_only", "deep_review_recommended", "human_triage_required"] | None = None

    @model_validator(mode="after")
    def _sync_deprecated_aliases(self) -> "AARReviewDTO":
        self.session_refs = list(self.correlation.session_ids)
        self.correlation_confidence = self.correlation.confidence
        self.correlation_strategy = self.correlation.strategy
        self.verdict = self.triage_verdict
        return self


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
    source: Literal["backend", "session_attribution", "unavailable"] = "unavailable"


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
    commit_refs: list[str] = Field(default_factory=list)
    pr_refs: list[str] = Field(default_factory=list)


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


class SessionLink(BaseModel):
    """Compact session reference surfaced inside a phase context item.

    Used by ``PhaseContextItem.linked_sessions_by_phase`` to expose the
    inverse phase→sessions mapping.  All fields have safe defaults so the DTO
    remains resilience-safe when individual DB columns are absent.
    """

    session_id: str
    agent_name: str | None = None
    start_time: str | None = None
    transcript_href: str | None = None


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
    linked_sessions_by_phase: dict[int, list[SessionLink]] | None = None
    """Inverse phase→sessions mapping.  None when the query returned no results."""


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


# ── Planning Command Center DTOs (PCC-101) ───────────────────────────────────


class PlanningCommandTargetArtifactDTO(BaseModel):
    """Artifact targeted by a planning command recommendation."""

    path: str = ""
    doc_type: str = ""
    title: str = ""
    exists: bool | None = None
    source_ref: str = ""


class PlanningCommandCapabilityDTO(BaseModel):
    """Capability required to execute a recommended planning command."""

    name: str
    supported: bool = True
    required: bool = True
    warning: str = ""
    fallback_command: str = ""


class PlanningCommandAlternativeDTO(BaseModel):
    """Non-primary command candidate shown as an explainable alternative."""

    rule_id: PlanningCommandRuleId
    command: str = ""
    confidence: float = 0.0
    rationale: str = ""
    target_artifact_path: str = ""
    target_artifact_doc_type: str = ""
    phase: int | None = None
    warnings: list[str] = Field(default_factory=list)
    required_capabilities: list[PlanningCommandCapabilityDTO] = Field(default_factory=list)


class PlanningCommandResolutionDTO(BaseModel):
    """Deterministic command recommendation for a planning work item."""

    command: str = ""
    rule_id: PlanningCommandRuleId
    confidence: float = 0.0
    rationale: str = ""
    target_artifact_path: str = ""
    target_artifact_doc_type: str = ""
    target_artifact: PlanningCommandTargetArtifactDTO | None = None
    phase: int | None = None
    warnings: list[str] = Field(default_factory=list)
    alternatives: list[PlanningCommandAlternativeDTO] = Field(default_factory=list)
    required_capabilities: list[PlanningCommandCapabilityDTO] = Field(default_factory=list)


class PlanningCommandCenterFeatureDTO(BaseModel):
    """Feature identity shown in the command-center work-item list."""

    feature_id: str
    feature_slug: str = ""
    name: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    priority: str = ""
    summary: str = ""


class PlanningCommandCenterStatusDTO(BaseModel):
    """Raw and derived planning status for a command-center item."""

    raw_status: str = ""
    effective_status: str = ""
    planning_signal: str = ""
    mismatch_state: str = "unknown"
    is_mismatch: bool = False


class PlanningCommandCenterTierDTO(BaseModel):
    tier_number: int | None = None
    tier_name: str = ""
    estimated_points: float | None = None


class PlanningCommandCenterStoryPointsDTO(BaseModel):
    total: float = 0.0
    remaining: float = 0.0
    completed: float = 0.0


class PlanningCommandCenterPhaseDTO(BaseModel):
    current_phase: int | None = None
    next_phase: int | None = None
    total_phases: int = 0
    completed_phases: int = 0


class PlanningCommandCenterArtifactDTO(BaseModel):
    artifact_id: str = ""
    path: str = ""
    doc_type: str = ""
    title: str = ""
    status: str = ""
    exists: bool | None = None


class PlanningCommandCenterRelatedFileDTO(BaseModel):
    path: str = ""
    doc_type: str = ""
    size_bytes: int | None = None
    last_modified: str = ""
    addable: bool = True


class PlanningCommandCenterPhaseRowDTO(BaseModel):
    phase_number: int | None = None
    name: str = ""
    story_points: float | None = None
    phase_files: list[str] = Field(default_factory=list)
    domain: str = ""
    model: str = ""
    agents: list[str] = Field(default_factory=list)
    status: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    linked_sessions: list[SessionLink] = Field(default_factory=list)
    """Compact session references linked to this phase via the inverse phase→sessions query."""


class PlanningCommandCenterLaunchAgentDTO(BaseModel):
    agent_id: str = ""
    label: str = ""
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    state: str = "unknown"


class PlanningCommandCenterLaunchBatchDTO(BaseModel):
    batch_id: str = ""
    label: str = ""
    readiness: str = "unknown"
    agents: list[PlanningCommandCenterLaunchAgentDTO] = Field(default_factory=list)
    queued_count: int = 0
    running_count: int = 0


class PlanningCommandCenterWorktreeDTO(BaseModel):
    context_id: str = ""
    path: str = ""
    branch: str = ""
    status: str = ""
    phase_number: int | None = None
    batch_id: str = ""


class PlanningCommandCenterGitStateDTO(BaseModel):
    path_exists: bool | None = None
    head: str = ""
    dirty_count: int | None = None
    stash_count: int | None = None
    upstream: str = ""
    ahead: int | None = None
    behind: int | None = None
    probed_at: str = ""
    warnings: list[str] = Field(default_factory=list)


class PlanningCommandCenterPullRequestDTO(BaseModel):
    provider: str = ""
    number: int | None = None
    url: str = ""
    state: str = ""
    review_status: str = ""


class PlanningCommandCenterBlockerDTO(BaseModel):
    label: str = ""
    reason: str = ""
    severity: str = ""


class PlanningCommandCenterCapabilitiesDTO(BaseModel):
    copy_command: bool = True
    launch: bool = False
    review: bool = False
    merge: bool = False
    cleanup: bool = False
    open_pr: bool = False
    edit_command: bool = True


class AggregateWorkItemSession(BaseModel):
    """Compact running-session reference for the command-center work-item list.

    Populated only for sessions whose board state maps to ``"running"``
    (raw DB statuses: ``running``, ``in_progress``, ``active``).  Uses the
    same state classification as ``planning_sessions._STATUS_STATE_MAP``.

    All fields are optional or have safe defaults so the DTO is resilience-safe:
    missing fields from the DB row are represented as ``None`` / empty string
    rather than raising.
    """

    session_id: str
    state: str = "running"
    model: str | None = None
    started_at: str | None = None
    agent_name: str | None = None


class PlanningCommandCenterItemDTO(BaseModel):
    """Single command-center work item consumed by aggregate endpoints."""

    feature: PlanningCommandCenterFeatureDTO
    status: PlanningCommandCenterStatusDTO = Field(default_factory=PlanningCommandCenterStatusDTO)
    tier: PlanningCommandCenterTierDTO = Field(default_factory=PlanningCommandCenterTierDTO)
    story_points: PlanningCommandCenterStoryPointsDTO = Field(default_factory=PlanningCommandCenterStoryPointsDTO)
    phase: PlanningCommandCenterPhaseDTO = Field(default_factory=PlanningCommandCenterPhaseDTO)
    artifacts: list[PlanningCommandCenterArtifactDTO] = Field(default_factory=list)
    target_artifact: PlanningCommandTargetArtifactDTO | None = None
    command: PlanningCommandResolutionDTO | None = None
    related_files: list[PlanningCommandCenterRelatedFileDTO] = Field(default_factory=list)
    phase_rows: list[PlanningCommandCenterPhaseRowDTO] = Field(default_factory=list)
    launch_batch: PlanningCommandCenterLaunchBatchDTO | None = None
    worktree: PlanningCommandCenterWorktreeDTO | None = None
    git_state: PlanningCommandCenterGitStateDTO | None = None
    pull_request: PlanningCommandCenterPullRequestDTO | None = None
    blockers: list[PlanningCommandCenterBlockerDTO] = Field(default_factory=list)
    last_activity: dict[str, Any] = Field(default_factory=dict)
    capabilities: PlanningCommandCenterCapabilitiesDTO = Field(default_factory=PlanningCommandCenterCapabilitiesDTO)
    active_sessions: list[AggregateWorkItemSession] = Field(default_factory=list)
    """Running sessions correlated to this feature.  Empty list when none are running."""
    commit_refs: list[str] = Field(default_factory=list)
    """Commit SHAs linked to this feature from planning doc frontmatter / document_refs."""
    pr_refs: list[str] = Field(default_factory=list)
    """PR references (URLs or '#NNN') linked to this feature."""


class PlanningCommandCenterPageDTO(AgentQueryEnvelope):
    """Paginated command-center response contract."""

    project_id: str
    items: list[PlanningCommandCenterItemDTO] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    sort_by: str = ""
    sort_direction: Literal["asc", "desc"] = "asc"
    warnings: list[str] = Field(default_factory=list)


# ── Planning Agent Session Board DTOs ────────────────────────────────────────
# These DTOs define the data contracts for the Planning Agent Session Board
# feature, which surfaces agent sessions as rich cards on a Kanban-style board
# correlated to features, phases, and tasks.


class SessionCorrelationEvidence(BaseModel):
    """Evidence for why a session is linked to a planning entity."""

    source_type: str
    source_id: str | None = None
    source_label: str = ""
    confidence: str = "unknown"
    detail: str | None = None


class SessionCorrelation(BaseModel):
    """Aggregated correlation for one session-to-planning-entity binding."""

    feature_id: str | None = None
    feature_name: str | None = None
    phase_number: int | None = None
    phase_title: str | None = None
    batch_id: str | None = None
    task_id: str | None = None
    task_title: str | None = None
    confidence: str = "unknown"
    evidence: list[SessionCorrelationEvidence] = Field(default_factory=list)


class SessionRelationship(BaseModel):
    """Relationship between sessions."""

    related_session_id: str
    relation_type: str = ""
    agent_name: str | None = None
    state: str | None = None


class SessionActivityMarker(BaseModel):
    """Lightweight activity indicator for a session."""

    marker_type: str = ""
    label: str = ""
    timestamp: str | None = None
    detail: str | None = None


class SessionTokenSummary(BaseModel):
    """Compact token usage for a session."""

    tokens_in: int = 0
    tokens_out: int = 0
    total_tokens: int = 0
    context_window_pct: float | None = None
    model: str | None = None


class PlanningAgentSessionCardDTO(BaseModel):
    """Primary board card representing one agent session."""

    session_id: str
    agent_name: str | None = None
    agent_type: str | None = None
    state: str = "unknown"
    model: str | None = None
    correlation: SessionCorrelation | None = None
    transcript_href: str | None = None
    planning_href: str | None = None
    phase_href: str | None = None
    parent_session_id: str | None = None
    root_session_id: str | None = None
    started_at: str | None = None
    last_activity_at: str | None = None
    duration_seconds: float | None = None
    token_summary: SessionTokenSummary | None = None
    relationships: list[SessionRelationship] = Field(default_factory=list)
    activity_markers: list[SessionActivityMarker] = Field(default_factory=list)
    git_branch: str | None = None
    git_commit_hash: str | None = None


class PlanningBoardGroupDTO(BaseModel):
    """A group of session cards on the planning board."""

    group_key: str
    group_label: str = ""
    group_type: str = ""
    cards: list[PlanningAgentSessionCardDTO] = Field(default_factory=list)
    card_count: int = 0


PlanningBoardGroupingMode = Literal["state", "feature", "phase", "agent", "model"]


class PlanningAgentSessionBoardDTO(AgentQueryEnvelope):
    """Top-level board response for the Planning Agent Session Board.

    ``feature_id`` is populated only when the board is scoped to a single
    feature.  ``grouping`` reflects the applied ``PlanningBoardGroupingMode``.
    ``active_count`` and ``completed_count`` are convenience tallies derived
    from the card states across all groups.

    Pagination fields (T4-001):
    - ``page``: 1-based page number of the returned window (absent when
      cursor-based pagination is used).
    - ``page_size``: number of cards requested per page.  Equals the applied
      ``limit`` query param (default 500 for backward compatibility).
    - ``next_cursor``: opaque cursor for the next page.  ``None`` when there
      are no more cards (i.e. this is the last or only page).  FE must tolerate
      this field being absent — it is ``None`` by default.
    """

    project_id: str
    feature_id: str | None = None
    grouping: str = "state"
    groups: list[PlanningBoardGroupDTO] = Field(default_factory=list)
    total_card_count: int = 0
    active_count: int = 0
    completed_count: int = 0
    # ── Pagination (T4-001) ──────────────────────────────────────────────────
    page: int | None = None
    page_size: int | None = None
    next_cursor: str | None = None


class NextRunContextRef(BaseModel):
    """Reference to an artifact or session for next-run prompt context."""

    ref_type: str = ""
    ref_id: str = ""
    ref_label: str = ""
    ref_path: str | None = None


class PromptContextSelection(BaseModel):
    """User's selected context items for prompt composition (PASB-401).

    Carries the explicit selections the caller wants injected into the rendered
    prompt skeleton.  All fields default to empty so callers can omit any
    dimension they don't need.
    """

    session_ids: list[str] = Field(default_factory=list)
    phase_refs: list[str] = Field(default_factory=list)
    task_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    transcript_refs: list[str] = Field(default_factory=list)


class PlanningNextRunPreviewDTO(AgentQueryEnvelope):
    """Next-run prompt preview for a feature or phase.

    ``command`` is the full CLI invocation string.  ``prompt_skeleton`` is the
    rendered prompt text with placeholders resolved where possible.
    ``context_refs`` lists the artifacts and sessions that will be injected as
    context.  ``warnings`` surfaces any missing or stale inputs that may affect
    run quality.
    """

    feature_id: str
    feature_name: str | None = None
    phase_number: int | None = None
    command: str = ""
    prompt_skeleton: str = ""
    context_refs: list[NextRunContextRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── P5a Fat-Read Bundle DTOs ──────────────────────────────────────────────────
# These DTOs compose existing cached reads into single above-fold bundles.
# They reduce the FE waterfall from N parallel above-fold requests to ≤1 per view.


class SessionCardDTO(BaseModel):
    """Lightweight session card for the Dashboard bundle sessions list."""

    session_id: str
    title: str = ""
    status: str = ""
    started_at: str = ""
    ended_at: str = ""
    model: str = ""
    total_cost: float = 0.0
    total_tokens: int = 0
    feature_id: str = ""
    root_session_id: str = ""


class DashboardBundleDTO(AgentQueryEnvelope):
    """Fat-read bundle for the Dashboard view (T5-001).

    Composes the most-recent sessions page (limit 20, desc ``started_at``) and
    task counts by status into a single above-fold response.  Both fields are
    resilience-safe: missing values default to empty list / empty dict.

    Field notes:
    - ``sessions``: up to 20 most-recent session cards sorted by ``started_at`` desc.
    - ``task_counts``: dict mapping status string to integer count for the project.
    """

    project_id: str
    sessions: list[SessionCardDTO] = Field(default_factory=list)
    task_counts: dict[str, int] = Field(default_factory=dict)


class PlanningViewBundleDTO(AgentQueryEnvelope):
    """Fat-read bundle for the Planning view (T5-003).

    Always includes the planning summary.  Graph and session board are optional
    and included only when requested via the ``include=`` query parameter.

    Field notes:
    - ``summary``: project-level planning health counts (always present).
    - ``graph``: planning graph nodes/edges (present when ``include=graph``).
    - ``session_board``: planning agent session board (present when
      ``include=session_board``).
    """

    project_id: str
    summary: ProjectPlanningSummaryDTO | None = None
    graph: ProjectPlanningGraphDTO | None = None
    session_board: "PlanningAgentSessionBoardDTO | None" = None


class AnalyticsKPIsDTO(BaseModel):
    """Above-fold analytics KPI snapshot (T5-004)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    session_count: int = 0
    session_cost: float = 0.0
    session_tokens: int = 0
    session_duration_avg: float = 0.0
    task_velocity: int = 0
    task_completion_pct: float = 0.0
    feature_progress: float = 0.0
    tool_call_count: int = 0
    tool_success_rate: float = 0.0
    model_io_tokens: int = Field(default=0, serialization_alias="modelIOTokens")
    cache_input_tokens: int = 0
    observed_tokens: int = 0
    context_session_count: int = 0
    avg_context_utilization_pct: float = 0.0
    tool_reported_tokens: int = 0


class AnalyticsTopModelDTO(BaseModel):
    """Single model entry in the top-models list."""

    name: str
    usage: int = 0


class AnalyticsOverviewBundleDTO(AgentQueryEnvelope):
    """Fat-read bundle for the Analytics above-fold view (T5-004).

    Contains only above-fold KPIs and top models.  Detailed tab breakdowns
    (workflow effectiveness, session intelligence, etc.) remain as separate lazy
    endpoints so they are not penalised by bundle latency.

    Field notes:
    - ``kpis``: key performance indicators for the project.
    - ``top_models``: model usage breakdown (up to 8 entries).
    - ``range``: effective date range used for KPI computation.
    """

    project_id: str
    kpis: AnalyticsKPIsDTO = Field(default_factory=AnalyticsKPIsDTO)
    top_models: list[AnalyticsTopModelDTO] = Field(default_factory=list)
    range: dict[str, str] = Field(default_factory=dict)
