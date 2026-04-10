"""Shared Pydantic DTOs for transport-neutral agent query services."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


QueryStatus = Literal["ok", "partial", "error"]


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class TemporalEnvelopeDTO(BaseModel):
    """Common non-status envelope fields shared by all agent query DTOs."""

    data_freshness: datetime = Field(default_factory=utc_now)
    generated_at: datetime = Field(default_factory=utc_now)
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("source_refs", mode="before")
    @classmethod
    def _normalize_source_refs(cls, value: object) -> list[str]:
        """Normalize source references into a deduplicated string list."""
        if value is None:
            return []
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, Iterable):
            items = [str(item) for item in value]
        else:
            items = [str(value)]
        normalized: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    @model_validator(mode="after")
    def _ensure_freshness_not_after_generation(self) -> "TemporalEnvelopeDTO":
        """Keep generated timestamps at or after known data freshness."""
        if self.generated_at < self.data_freshness:
            self.generated_at = self.data_freshness
        return self


class SessionSummary(BaseModel):
    """Condensed session representation for project-level status views."""

    session_id: str
    title: str = ""
    status: str = ""
    workflow_id: str = ""
    workflow_name: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int = Field(default=0, ge=0)
    total_cost: float = Field(default=0.0, ge=0.0)
    total_tokens: int = Field(default=0, ge=0)
    model: str = ""
    feature_ids: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)


class SessionRef(BaseModel):
    """Rich session reference for feature and workflow diagnostics."""

    session_id: str
    title: str = ""
    status: str = ""
    workflow_id: str = ""
    workflow_name: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int = Field(default=0, ge=0)
    total_cost: float = Field(default=0.0, ge=0.0)
    total_tokens: int = Field(default=0, ge=0)
    tools_used: list[str] = Field(default_factory=list)
    model: str = ""
    outcome: str = ""
    complexity_score: float | None = Field(default=None, ge=0.0)
    failure_patterns: list[str] = Field(default_factory=list)


class DocumentRef(BaseModel):
    """Reference to a document linked to a feature or report."""

    document_id: str
    path: str = ""
    title: str = ""
    document_type: str = ""
    status: str = ""
    updated_at: datetime | None = None


class TaskRef(BaseModel):
    """Reference to a task linked to a feature."""

    task_id: str
    title: str = ""
    status: str = ""
    assignee: str = ""
    updated_at: datetime | None = None


class CostSummary(BaseModel):
    """Aggregated cost metrics for a time-bounded query."""

    total: float = Field(default=0.0, ge=0.0)
    by_model: dict[str, float] = Field(default_factory=dict)
    by_workflow: dict[str, float] = Field(default_factory=dict)

    @field_validator("by_model", "by_workflow", mode="before")
    @classmethod
    def _normalize_cost_maps(cls, value: object) -> dict[str, float]:
        """Normalize cost maps to string keys and non-negative float values."""
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            return {}
        normalized: dict[str, float] = {}
        for key, amount in value.items():
            name = str(key).strip()
            if not name:
                continue
            normalized[name] = max(float(amount), 0.0)
        return normalized


class WorkflowSummary(BaseModel):
    """Compact workflow rollup for project status responses."""

    workflow_id: str
    workflow_name: str = ""
    session_count: int = Field(default=0, ge=0)
    total_cost: float = Field(default=0.0, ge=0.0)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class WorkflowDiagnostic(BaseModel):
    """Detailed workflow analytics for diagnostics responses."""

    workflow_id: str
    workflow_name: str = ""
    effectiveness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    session_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    cost_efficiency: float = Field(default=0.0, ge=0.0)
    common_failures: list[str] = Field(default_factory=list)
    representative_sessions: list[SessionRef] = Field(default_factory=list)


class TimelineData(BaseModel):
    """Date-bounded execution timeline for a feature report."""

    start_date: datetime | None = None
    end_date: datetime | None = None
    duration_days: int = Field(default=0, ge=0)


class KeyMetrics(BaseModel):
    """Top-line metrics for after-action review reporting."""

    total_cost: float = Field(default=0.0, ge=0.0)
    total_tokens: int = Field(default=0, ge=0)
    session_count: int = Field(default=0, ge=0)
    iteration_count: int = Field(default=0, ge=0)


class TurningPoint(BaseModel):
    """Major event that changed the direction of feature implementation."""

    date: datetime
    event: str
    impact_description: str


class WorkflowObservation(BaseModel):
    """Narrative and frequency observation for a workflow in an AAR report."""

    workflow_id: str
    frequency: int = Field(default=0, ge=0)
    effectiveness: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: str = ""


class Bottleneck(BaseModel):
    """Observed bottleneck affecting delivery quality, speed, or cost."""

    description: str
    cost_impact: float = Field(default=0.0, ge=0.0)
    sessions_affected: int = Field(default=0, ge=0)


class ProjectStatusDTO(TemporalEnvelopeDTO):
    """Composite project status response for agent-facing queries."""

    project_id: str
    project_name: str
    status: QueryStatus = "ok"
    feature_counts: dict[str, int] = Field(
        default_factory=lambda: {
            "todo": 0,
            "in_progress": 0,
            "blocked": 0,
            "done": 0,
        }
    )
    recent_sessions: list[SessionSummary] = Field(default_factory=list)
    cost_last_7d: CostSummary = Field(default_factory=CostSummary)
    top_workflows: list[WorkflowSummary] = Field(default_factory=list)
    sync_freshness: datetime = Field(default_factory=utc_now)
    blocked_features: list[str] = Field(default_factory=list)

    @field_validator("feature_counts", mode="before")
    @classmethod
    def _normalize_feature_counts(cls, value: object) -> dict[str, int]:
        """Ensure expected feature status buckets exist with integer counts."""
        buckets = {"todo": 0, "in_progress": 0, "blocked": 0, "done": 0}
        if value is None:
            return buckets
        if not isinstance(value, Mapping):
            return buckets
        for key, count in value.items():
            normalized_key = str(key).strip()
            if not normalized_key:
                continue
            buckets[normalized_key] = max(int(count), 0)
        return buckets


class FeatureForensicsDTO(TemporalEnvelopeDTO):
    """Detailed forensic report for feature delivery history."""

    feature_id: str
    feature_slug: str
    status: str
    linked_sessions: list[SessionRef] = Field(default_factory=list)
    linked_documents: list[DocumentRef] = Field(default_factory=list)
    linked_tasks: list[TaskRef] = Field(default_factory=list)
    iteration_count: int = Field(default=0, ge=0)
    total_cost: float = Field(default=0.0, ge=0.0)
    total_tokens: int = Field(default=0, ge=0)
    workflow_mix: dict[str, float] = Field(default_factory=dict)
    rework_signals: list[str] = Field(default_factory=list)
    failure_patterns: list[str] = Field(default_factory=list)
    representative_sessions: list[SessionRef] = Field(default_factory=list)
    summary_narrative: str = ""

    @field_validator("workflow_mix", mode="before")
    @classmethod
    def _normalize_workflow_mix(cls, value: object) -> dict[str, float]:
        """Normalize workflow percentages to a stable non-negative float map."""
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            return {}
        normalized: dict[str, float] = {}
        for key, ratio in value.items():
            name = str(key).strip()
            if not name:
                continue
            normalized[name] = max(float(ratio), 0.0)
        return normalized


class WorkflowDiagnosticsDTO(TemporalEnvelopeDTO):
    """Workflow effectiveness diagnostics for a project or feature scope."""

    project_id: str
    status: QueryStatus = "ok"
    workflows: list[WorkflowDiagnostic] = Field(default_factory=list)
    top_performers: list[WorkflowDiagnostic] = Field(default_factory=list)
    problem_workflows: list[WorkflowDiagnostic] = Field(default_factory=list)


class AARReportDTO(TemporalEnvelopeDTO):
    """After-action review report describing outcomes for a feature."""

    feature_id: str
    feature_slug: str
    scope_statement: str = ""
    timeline: TimelineData = Field(default_factory=TimelineData)
    key_metrics: KeyMetrics = Field(default_factory=KeyMetrics)
    turning_points: list[TurningPoint] = Field(default_factory=list)
    workflow_observations: list[WorkflowObservation] = Field(default_factory=list)
    bottlenecks: list[Bottleneck] = Field(default_factory=list)
    successful_patterns: list[str] = Field(default_factory=list)
    lessons_learned: list[str] = Field(default_factory=list)
    evidence_links: list[str] = Field(default_factory=list)


__all__ = [
    "AARReportDTO",
    "Bottleneck",
    "CostSummary",
    "DocumentRef",
    "FeatureForensicsDTO",
    "KeyMetrics",
    "ProjectStatusDTO",
    "QueryStatus",
    "TemporalEnvelopeDTO",
    "SessionRef",
    "SessionSummary",
    "TaskRef",
    "TimelineData",
    "TurningPoint",
    "WorkflowDiagnostic",
    "WorkflowDiagnosticsDTO",
    "WorkflowObservation",
    "WorkflowSummary",
]

# Made with Bob
