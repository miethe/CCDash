"""Shared domain DTOs for CCDash client API v1."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class InstanceMetaDTO(BaseModel):
    instance_id: str = ""
    version: str = ""
    environment: str = ""
    db_backend: str = ""
    capabilities: list[str] = Field(default_factory=list)
    server_time: datetime | None = None


class SessionRef(BaseModel):
    session_id: str = ""
    title: str = ""
    model: str = ""
    total_cost: float = 0.0
    total_turns: int = 0
    started_at: str = ""


class DocumentRef(BaseModel):
    path: str = ""
    title: str = ""
    doc_type: str = ""


class FeatureSummaryDTO(BaseModel):
    id: str = ""
    name: str = ""
    status: str = ""
    category: str = ""
    priority: str = ""
    total_tasks: int = 0
    completed_tasks: int = 0
    updated_at: str = ""


class FeatureSessionsDTO(BaseModel):
    feature_id: str = ""
    feature_slug: str = ""
    sessions: list[SessionRef] = Field(default_factory=list)
    total: int = 0


class FeatureDocumentsDTO(BaseModel):
    feature_id: str = ""
    feature_slug: str = ""
    documents: list[DocumentRef] = Field(default_factory=list)


class SessionFamilyDTO(BaseModel):
    root_session_id: str = ""
    session_count: int = 0
    members: list[SessionRef] = Field(default_factory=list)


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
FeatureRollupFieldKey = Literal[
    "session_counts",
    "token_cost_totals",
    "model_provider_summary",
    "latest_activity",
    "doc_metrics",
    "test_metrics",
    "freshness",
]


class FeatureSurfaceDTO(BaseModel):
    """Base model for feature-surface contracts using API-facing camelCase aliases."""

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
    document_id: str = ""
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
    id: str = ""
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
    execution_readiness: str = ""
    test_impact: str = ""
    planning_status: dict[str, Any] | None = None
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
    key: str = ""
    label: str = ""
    count: int | None = Field(None, ge=0)
    share: float | None = None


class FeatureRollupFreshnessDTO(DTOFreshness):
    session_sync_at: str = ""
    links_updated_at: str = ""
    test_health_at: str = ""


class FeatureRollupDTO(FeatureSurfaceDTO):
    feature_id: str = ""
    session_count: int | None = Field(None, ge=0)
    primary_session_count: int | None = Field(None, ge=0)
    subthread_count: int | None = Field(None, ge=0)
    unresolved_subthread_count: int | None = Field(None, ge=0)
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
    linked_doc_counts_by_type: list[FeatureRollupBucketDTO] = Field(default_factory=list)
    linked_task_count: int | None = Field(None, ge=0)
    linked_commit_count: int | None = Field(None, ge=0)
    linked_pr_count: int | None = Field(None, ge=0)
    test_count: int | None = Field(None, ge=0)
    failing_test_count: int | None = Field(None, ge=0)
    precision: FeatureSurfacePrecision = "eventually_consistent"
    freshness: FeatureRollupFreshnessDTO | None = None


class FeatureRollupRequestDTO(FeatureSurfaceDTO):
    feature_ids: list[str] = Field(..., min_length=1, max_length=100)
    fields: list[FeatureRollupFieldKey] = Field(default_factory=list)
    include_inherited_threads: bool = True
    include_freshness: bool = True
    include_test_metrics: bool = False


class FeatureRollupErrorDTO(FeatureSurfaceDTO):
    code: str = ""
    message: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class FeatureRollupResponseDTO(FeatureSurfaceDTO):
    rollups: dict[str, FeatureRollupDTO] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    errors: dict[str, FeatureRollupErrorDTO] = Field(default_factory=dict)
    generated_at: str = ""
    cache_version: str = ""


class FeatureModalOverviewDTO(FeatureSurfaceDTO):
    feature_id: str = ""
    card: FeatureCardDTO = Field(default_factory=FeatureCardDTO)
    rollup: FeatureRollupDTO | None = None
    description: str = ""
    precision: FeatureSurfacePrecision = "exact"
    freshness: DTOFreshness | None = None


class FeatureModalSectionItemDTO(FeatureSurfaceDTO):
    item_id: str = ""
    label: str = ""
    kind: str = ""
    status: str = ""
    description: str = ""
    href: str = ""
    badges: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeatureModalSectionDTO(FeatureSurfaceDTO):
    feature_id: str = ""
    section: FeatureModalSectionKey = "overview"
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
    task_id: str = ""
    task_title: str = ""
    phase_id: str = ""
    phase: str = ""
    matched_by: str = ""


class LinkedFeatureSessionDTO(FeatureSurfaceDTO):
    session_id: str = ""
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


# ---------------------------------------------------------------------------
# Phase 2: Session detail + transcript v1 response contracts
# ---------------------------------------------------------------------------
# These models are the contracts package source of truth for the
# GET /api/v1/sessions/{id}/detail  and
# GET /api/v1/sessions/{id}/transcript  response shapes.
#
# Field names are intentionally camelCase to match the keys emitted by
# SessionDetailBundle.as_dict() / TranscriptPage.as_dict() so that
# model_validate(bundle.as_dict()) works without alias resolution.
# Consumers that prefer snake_case can iterate .model_fields.
# ---------------------------------------------------------------------------


class TranscriptPageV1(BaseModel):
    """Cursor-paginated transcript page.

    Mirrors ``TranscriptPage.as_dict()`` from the Phase 1 service:
    ``{items, cursor, limit, nextCursor}``.  ``items`` are pre-redacted
    log-entry dicts.  ``nextCursor`` is ``None`` when this is the last page.
    """

    items: list[Any] = Field(default_factory=list)
    cursor: str = ""
    limit: int = 0
    nextCursor: Optional[str] = None  # noqa: N815 — intentional camelCase (service contract)


class SessionDetailV1(BaseModel):
    """Full session detail bundle — transcript-bearing v1 response.

    Mirrors ``SessionDetailBundle.as_dict()`` from the Phase 1 service.
    Optional segments (``transcript``, ``subagents``, ``tokens``,
    ``artifacts``, ``links``) are ``None`` when the consumer did not request
    them via the ``include`` query param — this is a CONTRACT STATE, not a
    bug.  Empty list / empty dict means the segment was requested but the
    session has no data.
    """

    sessionId: str = ""  # noqa: N815
    projectId: str = ""  # noqa: N815
    session: dict[str, Any] = Field(default_factory=dict)
    transcript: Optional[TranscriptPageV1] = None
    subagents: Optional[list[Any]] = None
    tokens: Optional[dict[str, Any]] = None
    artifacts: Optional[list[Any]] = None
    links: Optional[list[Any]] = None
    redactedFieldCount: int = 0  # noqa: N815


class SessionTranscriptPageV1(BaseModel):
    """Standalone cursor-paginated transcript page for the /transcript endpoint.

    Extends ``TranscriptPageV1`` with ``sessionId``/``projectId`` identity
    fields and the aggregate ``redactedFieldCount`` so the dedicated
    transcript endpoint is self-describing.
    """

    sessionId: str = ""  # noqa: N815
    projectId: str = ""  # noqa: N815
    items: list[Any] = Field(default_factory=list)
    cursor: str = ""
    limit: int = 0
    nextCursor: Optional[str] = None  # noqa: N815
    redactedFieldCount: int = 0  # noqa: N815


# ---------------------------------------------------------------------------
# Phase 10 (T10-001): Capability discovery contract
# ---------------------------------------------------------------------------


class CapabilityV1(BaseModel):
    """Capability advertisement for IntentTree and LAN agents.

    Clients feature-detect against ``capabilities``.  ``api_version`` is a
    string (currently ``"1"``) — a mismatch means the client should warn but
    should NOT hard-fail: future minor revisions increment the version string
    while preserving backward compat.

    Server-declared capability identifiers (v1):
    - ``sessions:cross-project``  — list/search/detail/transcript accept an
      explicit ``project_id`` param; detail+transcript REQUIRE it (400 if
      missing).
    - ``sessions:detail``         — full transcript-bearing detail bundle
      available at ``/sessions/{id}/detail``.
    - ``research-runs:*``         — Research Foundry run telemetry ingest
      (``POST /api/v1/ingest/rf-events``); wildcard placeholder pending
      the Phase 3+ query surface.
    """

    api_version: str = "1"
    capabilities: list[str] = Field(default_factory=list)
    instance_id: str = ""
    server_time: datetime | None = None
