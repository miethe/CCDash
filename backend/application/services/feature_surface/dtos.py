"""Transport-neutral DTOs for the Phase 2 feature surface services."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


FeatureSurfacePrecision = Literal["exact", "eventually_consistent", "partial"]
FeatureModalSectionKey = Literal[
    "overview",
    "phases",
    "documents",
    "relations",
    "sessions",
    "test_status",
    "activity",
]


class FeatureSurfaceDTO(BaseModel):
    """Base model that keeps Python field names snake_case and JSON camelCase."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class DTOFreshness(FeatureSurfaceDTO):
    observed_at: datetime | None = None
    source_revision: str = ""
    cache_version: str = ""


class FeatureDocumentSummaryDTO(FeatureSurfaceDTO):
    document_id: str
    title: str = ""
    doc_type: str = ""
    status: str = ""
    file_path: str = ""
    updated_at: str = ""


class FeatureDocumentCoverageDTO(FeatureSurfaceDTO):
    present: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    counts_by_type: dict[str, int] = Field(default_factory=dict)


class FeatureQualitySignalsDTO(FeatureSurfaceDTO):
    blocker_count: int = Field(0, ge=0)
    at_risk_task_count: int = Field(0, ge=0)
    has_blocking_signals: bool = False
    test_impact: str = ""
    integrity_signal_refs: list[str] = Field(default_factory=list)


class FeatureDependencySummaryDTO(FeatureSurfaceDTO):
    state: str = ""
    blocking_reason: str = ""
    blocked_by_count: int = Field(0, ge=0)
    ready_dependency_count: int = Field(0, ge=0)


class FeatureFamilyPositionDTO(FeatureSurfaceDTO):
    position: int | None = Field(None, ge=1)
    total: int | None = Field(None, ge=1)
    label: str = ""
    next_item_id: str = ""
    next_item_label: str = ""


class FeatureCardDTO(FeatureSurfaceDTO):
    id: str
    name: str = ""
    status: str = ""
    effective_status: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    description_preview: str = ""
    priority: str = ""
    risk_level: str = ""
    complexity: str = ""
    total_tasks: int = Field(0, ge=0)
    completed_tasks: int = Field(0, ge=0)
    deferred_tasks: int = Field(0, ge=0)
    phase_count: int = Field(0, ge=0)
    planned_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    updated_at: str = ""
    document_coverage: FeatureDocumentCoverageDTO = Field(
        default_factory=FeatureDocumentCoverageDTO
    )
    quality_signals: FeatureQualitySignalsDTO = Field(
        default_factory=FeatureQualitySignalsDTO
    )
    dependency_state: FeatureDependencySummaryDTO = Field(
        default_factory=FeatureDependencySummaryDTO
    )
    primary_documents: list[FeatureDocumentSummaryDTO] = Field(default_factory=list)
    family_position: FeatureFamilyPositionDTO | None = None
    related_feature_count: int = Field(0, ge=0)
    precision: FeatureSurfacePrecision = "exact"
    freshness: DTOFreshness | None = None


class FeatureCardPageDTO(FeatureSurfaceDTO):
    items: list[FeatureCardDTO] = Field(default_factory=list)
    total: int = Field(0, ge=0)
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)
    has_more: bool = False
    query_hash: str = ""
    precision: FeatureSurfacePrecision = "exact"
    freshness: DTOFreshness | None = None


class FeatureRollupBucketDTO(FeatureSurfaceDTO):
    key: str
    label: str = ""
    count: int | None = Field(None, ge=0)
    share: float | None = None


class FeatureRollupFreshnessDTO(DTOFreshness):
    session_sync_at: str = ""
    links_updated_at: str = ""
    test_health_at: str = ""


class FeatureRollupDTO(FeatureSurfaceDTO):
    feature_id: str
    session_count: int | None = Field(None, ge=0)
    primary_session_count: int | None = Field(None, ge=0)
    subthread_count: int | None = Field(None, ge=0)
    total_cost: float | None = Field(None, ge=0)
    display_cost: float | None = Field(None, ge=0)
    observed_tokens: int | None = Field(None, ge=0)
    model_io_tokens: int | None = Field(None, ge=0)
    cache_input_tokens: int | None = Field(None, ge=0)
    latest_session_at: str = ""
    latest_activity_at: str = ""
    model_families: list[FeatureRollupBucketDTO] = Field(default_factory=list)
    providers: list[FeatureRollupBucketDTO] = Field(default_factory=list)
    workflow_types: list[FeatureRollupBucketDTO] = Field(default_factory=list)
    linked_doc_count: int | None = Field(None, ge=0)
    linked_task_count: int | None = Field(None, ge=0)
    test_count: int | None = Field(None, ge=0)
    failing_test_count: int | None = Field(None, ge=0)
    precision: FeatureSurfacePrecision = "eventually_consistent"
    freshness: FeatureRollupFreshnessDTO | None = None


class FeatureModalOverviewDTO(FeatureSurfaceDTO):
    feature_id: str
    card: FeatureCardDTO
    rollup: FeatureRollupDTO | None = None
    description: str = ""
    precision: FeatureSurfacePrecision = "exact"
    freshness: DTOFreshness | None = None


class FeatureModalSectionItemDTO(FeatureSurfaceDTO):
    item_id: str
    label: str = ""
    kind: str = ""
    status: str = ""
    description: str = ""
    href: str = ""
    badges: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeatureModalSectionDTO(FeatureSurfaceDTO):
    feature_id: str
    section: FeatureModalSectionKey
    title: str = ""
    items: list[FeatureModalSectionItemDTO] = Field(default_factory=list)
    total: int = Field(0, ge=0)
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)
    has_more: bool = False
    includes: list[str] = Field(default_factory=list)
    precision: FeatureSurfacePrecision = "exact"
    freshness: DTOFreshness | None = None


class LinkedFeatureSessionTaskDTO(FeatureSurfaceDTO):
    task_id: str
    task_title: str = ""
    phase_id: str = ""
    phase: str = ""
    matched_by: str = ""


class LinkedFeatureSessionDTO(FeatureSurfaceDTO):
    session_id: str
    title: str = ""
    status: str = ""
    model: str = ""
    model_provider: str = ""
    model_family: str = ""
    started_at: str = ""
    ended_at: str = ""
    updated_at: str = ""
    total_cost: float = Field(0.0, ge=0)
    observed_tokens: int = Field(0, ge=0)
    root_session_id: str = ""
    parent_session_id: str | None = None
    workflow_type: str = ""
    is_primary_link: bool = False
    is_subthread: bool = False
    thread_child_count: int = Field(0, ge=0)
    reasons: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    related_tasks: list[LinkedFeatureSessionTaskDTO] = Field(default_factory=list)


class LinkedSessionEnrichmentDTO(FeatureSurfaceDTO):
    includes: list[str] = Field(default_factory=list)
    logs_read: bool = False
    command_count_included: bool = False
    task_refs_included: bool = False
    thread_children_included: bool = False


class LinkedFeatureSessionPageDTO(FeatureSurfaceDTO):
    items: list[LinkedFeatureSessionDTO] = Field(default_factory=list)
    total: int = Field(0, ge=0)
    offset: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)
    has_more: bool = False
    next_cursor: str | None = None
    enrichment: LinkedSessionEnrichmentDTO = Field(
        default_factory=LinkedSessionEnrichmentDTO
    )
    precision: FeatureSurfacePrecision = "eventually_consistent"
    freshness: DTOFreshness | None = None


__all__ = [
    "DTOFreshness",
    "FeatureCardDTO",
    "FeatureCardPageDTO",
    "FeatureDependencySummaryDTO",
    "FeatureDocumentCoverageDTO",
    "FeatureDocumentSummaryDTO",
    "FeatureFamilyPositionDTO",
    "FeatureModalOverviewDTO",
    "FeatureModalSectionDTO",
    "FeatureModalSectionItemDTO",
    "FeatureQualitySignalsDTO",
    "FeatureRollupBucketDTO",
    "FeatureRollupDTO",
    "FeatureRollupFreshnessDTO",
    "FeatureSurfacePrecision",
    "LinkedFeatureSessionDTO",
    "LinkedFeatureSessionPageDTO",
    "LinkedFeatureSessionTaskDTO",
    "LinkedSessionEnrichmentDTO",
]
