"""Shared DTO contracts for transport-neutral agent query services."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

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


class FeatureForensicsDTO(AgentQueryEnvelope):
    feature_id: str
    feature_slug: str = ""
    feature_status: str = ""
    linked_sessions: list[SessionRef] = Field(default_factory=list)
    linked_documents: list[DocumentRef] = Field(default_factory=list)
    linked_tasks: list[TaskRef] = Field(default_factory=list)
    iteration_count: int = 0
    total_cost: float = 0.0
    total_tokens: int = 0
    workflow_mix: dict[str, float] = Field(default_factory=dict)
    rework_signals: list[str] = Field(default_factory=list)
    failure_patterns: list[str] = Field(default_factory=list)
    representative_sessions: list[SessionRef] = Field(default_factory=list)
    summary_narrative: str = ""


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
