"""
Transport-neutral query option models for the feature surface repository layer.

Encodes the filter/sort/search/pagination contract from:
  - Phase 1 plan: docs/project_plans/implementation_plans/refactors/
      feature-surface-data-loading-redesign-v1/phase-1-repository-query-foundation.md
  - Query matrix:  .claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/query-matrix.md
  - Rollup DTO draft: .claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/rollup-dto-draft.md
    (field-group names, precision taxonomy, 100-ID batch cap)
  - Performance budgets: .claude/worknotes/feature-surface-data-loading-redesign-v1/phase-0/performance-budgets.md

These models are used by both the SQLite and Postgres repository implementations
and by the service layer.  They must NOT be imported from FastAPI routers directly;
API-layer DTOs live in backend/routers/ and translate to/from these types.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Rollup field-group literals (rollup-dto-draft.md §3 column groups)
# ---------------------------------------------------------------------------

RollupFieldGroup = Literal[
    "session_counts",
    "token_cost_totals",
    "model_provider_summary",
    "latest_activity",
    "task_metrics",
    "doc_metrics",
    "test_metrics",
    "freshness",
]

_VALID_ROLLUP_GROUPS: frozenset[str] = frozenset(
    [
        "session_counts",
        "token_cost_totals",
        "model_provider_summary",
        "latest_activity",
        "task_metrics",
        "doc_metrics",
        "test_metrics",
        "freshness",
    ]
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class FeatureSortKey(str, Enum):
    """Sort keys for the feature list query.

    Default direction convention (query-matrix.md §4.1):
      - updated_date, latest_activity, session_count, completed_at, created_at → DESC
      - name → ASC
      - progress, task_count → DESC
    """

    UPDATED_DATE = "updated_at"
    COMPLETED_AT = "completed_at"
    CREATED_AT = "created_at"
    NAME = "name"
    PROGRESS = "progress"
    TASK_COUNT = "total_tasks"
    LATEST_ACTIVITY = "latest_activity"
    SESSION_COUNT = "session_count"

    @property
    def default_direction(self) -> SortDirection:
        """Return the natural default sort direction for this key."""
        if self == FeatureSortKey.NAME:
            return SortDirection.ASC
        return SortDirection.DESC


class ThreadExpansionMode(str, Enum):
    """Controls whether subthread sessions are included in linked-session queries."""

    NONE = "none"
    INHERITED_THREADS = "inherited_threads"


class DateRangeField(str, Enum):
    """Date fields that support range filtering (query-matrix.md §3)."""

    PLANNED = "planned"
    STARTED = "started"
    COMPLETED = "completed"
    UPDATED = "updated"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

class DateRange(BaseModel):
    """Optional ISO-8601 date range.  Both bounds are optional; when both are
    provided, ``from_date`` must be ≤ ``to_date``."""

    from_date: Optional[str] = Field(default=None, description="ISO-8601 lower bound (inclusive)")
    to_date: Optional[str] = Field(default=None, description="ISO-8601 upper bound (inclusive)")

    @model_validator(mode="after")
    def _validate_range_order(self) -> "DateRange":
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError(
                f"DateRange.from_date ({self.from_date!r}) must be ≤ to_date ({self.to_date!r})"
            )
        return self


# ---------------------------------------------------------------------------
# Feature list query
# ---------------------------------------------------------------------------

class FeatureListQuery(BaseModel):
    """Options passed to ``list_feature_cards`` / ``count_feature_cards``.

    Filters, sort, and pagination are independent axes.  All filters are
    ANDed together.  Absence of a filter means "no restriction on that axis".
    """

    # -- text search -------------------------------------------------------
    q: Optional[str] = Field(
        default=None,
        min_length=2,
        description="Substring search over name and id (case-insensitive, min 2 chars)",
    )

    # -- categorical filters -----------------------------------------------
    status: list[str] = Field(
        default_factory=list,
        description="Restrict to features whose status column matches any of these values",
    )
    stage: list[str] = Field(
        default_factory=list,
        description="Restrict to features whose board stage (derived) matches any of these values",
    )
    category: list[str] = Field(
        default_factory=list,
        description="Restrict to features whose category matches any of these values (case-insensitive)",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Restrict to features that carry at least one of these tags (Phase 2, JSON extraction)",
    )

    # -- derived boolean filters -------------------------------------------
    has_deferred: Optional[bool] = Field(
        default=None,
        description="When True, restrict to features with deferredTasks > 0 (Phase 2)",
    )

    # -- date range filters ------------------------------------------------
    planned: Optional[DateRange] = None
    started: Optional[DateRange] = None
    completed: Optional[DateRange] = None
    updated: Optional[DateRange] = None

    # -- numeric range filters ---------------------------------------------
    progress_min: Annotated[Optional[float], Field(ge=0.0, le=1.0)] = None
    progress_max: Annotated[Optional[float], Field(ge=0.0, le=1.0)] = None
    task_count_min: Annotated[Optional[int], Field(ge=0)] = None
    task_count_max: Annotated[Optional[int], Field(ge=0)] = None

    # -- sort --------------------------------------------------------------
    sort_by: FeatureSortKey = FeatureSortKey.UPDATED_DATE
    sort_direction: Annotated[
        Optional[SortDirection],
        Field(
            description=(
                "Explicit direction override.  When None the natural default for "
                "sort_by is used (DESC for date/activity/count sorts, ASC for name)."
            ),
        ),
    ] = None

    # -- pagination --------------------------------------------------------
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=200)] = 50

    @property
    def effective_sort_direction(self) -> SortDirection:
        """Return the resolved sort direction (explicit override or natural default)."""
        if self.sort_direction is not None:
            return self.sort_direction
        return self.sort_by.default_direction


# ---------------------------------------------------------------------------
# Feature list page
# ---------------------------------------------------------------------------

class FeatureListPage(BaseModel):
    """Paginated result from ``list_feature_cards``.

    ``rows`` contains lightweight card-row dicts (the exact shape is determined
    by the Feature List DTO, defined separately in the router layer).
    ``total`` is the post-filter, pre-pagination count.
    """

    rows: list[dict] = Field(default_factory=list)
    total: int = Field(0, ge=0)
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1)
    has_more: bool = False
    truncated: bool = False

    @model_validator(mode="after")
    def _compute_has_more(self) -> "FeatureListPage":
        if not self.model_fields_set.issuperset({"has_more"}):
            self.has_more = (self.offset + len(self.rows)) < self.total
        if not self.model_fields_set.issuperset({"truncated"}):
            self.truncated = len(self.rows) >= self.limit and self.has_more
        return self


# ---------------------------------------------------------------------------
# Phase summary bulk query
# ---------------------------------------------------------------------------

_PHASE_SUMMARY_ID_CAP = 500


class PhaseSummaryBulkQuery(BaseModel):
    """Options for ``list_phase_summaries_for_features`` (P1-003).

    ``feature_ids`` is the bounded set returned by a single ``FeatureListPage``
    (max 200, matching the list hard-cap).  A hard defensive cap of 500 is
    enforced here so callers receive a clear ValueError rather than a silent
    slow query.
    """

    feature_ids: list[str] = Field(..., min_length=1)
    include_progress: bool = True
    include_counts: bool = True

    @field_validator("feature_ids")
    @classmethod
    def _cap_feature_ids(cls, v: list[str]) -> list[str]:
        if len(v) > _PHASE_SUMMARY_ID_CAP:
            raise ValueError(
                f"feature_ids exceeds the maximum batch size of {_PHASE_SUMMARY_ID_CAP}. "
                f"Received {len(v)} IDs."
            )
        return v


class PhaseSummary(BaseModel):
    """Lightweight per-phase aggregate returned by ``list_phase_summaries_for_features``.

    ``order_index`` is derived from the ``phase`` string column (cast to int
    where possible; falls back to None).  ``total_tasks`` / ``completed_tasks``
    default to 0 regardless of ``include_counts`` — callers should treat 0 as
    "not computed" when ``include_counts=False``.  ``progress`` is None unless
    ``include_progress=True``.
    """

    feature_id: str
    phase_id: str
    name: str
    status: Optional[str] = None
    order_index: Optional[int] = None
    total_tasks: int = 0
    completed_tasks: int = 0
    progress: Optional[float] = None


# ---------------------------------------------------------------------------
# Feature rollup query
# ---------------------------------------------------------------------------

_ROLLUP_ID_CAP = 100


class FeatureRollupQuery(BaseModel):
    """Options for ``get_feature_session_rollups`` (P1-004).

    ``feature_ids`` is capped at 100 IDs per the performance budget
    (rollup-dto-draft.md §2, performance-budgets.md §2.2).
    """

    feature_ids: list[str] = Field(..., min_length=1)
    include_fields: set[RollupFieldGroup] = Field(
        default_factory=lambda: {
            "session_counts",
            "token_cost_totals",
            "model_provider_summary",
            "latest_activity",
            "doc_metrics",
        }
    )
    include_freshness: bool = True
    # Opt-in for expensive/partial fields
    include_test_metrics: bool = False
    include_subthread_resolution: bool = False

    @field_validator("feature_ids")
    @classmethod
    def _cap_feature_ids(cls, v: list[str]) -> list[str]:
        if len(v) > _ROLLUP_ID_CAP:
            raise ValueError(
                f"feature_ids exceeds the maximum batch size of {_ROLLUP_ID_CAP}. "
                f"Received {len(v)} IDs.  Split into batches of ≤ {_ROLLUP_ID_CAP}."
            )
        # Deduplicate while preserving order (rollup-dto-draft.md §2)
        seen: set[str] = set()
        deduped: list[str] = []
        for fid in v:
            if fid not in seen:
                seen.add(fid)
                deduped.append(fid)
        return deduped

    @field_validator("include_fields", mode="before")
    @classmethod
    def _validate_field_groups(cls, v: object) -> object:
        if isinstance(v, (set, list, frozenset)):
            unknown = {g for g in v if g not in _VALID_ROLLUP_GROUPS}
            if unknown:
                raise ValueError(
                    f"Unknown rollup field group(s): {sorted(unknown)}.  "
                    f"Valid groups: {sorted(_VALID_ROLLUP_GROUPS)}."
                )
        return v


# ---------------------------------------------------------------------------
# Feature rollup results
# ---------------------------------------------------------------------------

class RollupFreshness(BaseModel):
    """Per-source freshness timestamps for a single feature rollup."""

    session_sync_at: Optional[str] = None
    links_updated_at: Optional[str] = None
    test_health_at: Optional[str] = None
    cache_version: str = ""


class FeatureRollupEntry(BaseModel):
    """Single-feature rollup aggregate; keyed by feature_id in FeatureRollupBatch."""

    feature_id: str
    precision: Literal["exact", "eventually_consistent", "partial"] = "eventually_consistent"
    freshness: Optional[RollupFreshness] = None

    # session_counts group
    session_count: Optional[int] = None
    primary_session_count: Optional[int] = None
    subthread_count: Optional[int] = None
    unresolved_subthread_count: Optional[int] = None

    # token_cost_totals group
    total_cost: Optional[float] = None
    display_cost: Optional[float] = None
    observed_tokens: Optional[int] = None
    model_io_tokens: Optional[int] = None
    cache_input_tokens: Optional[int] = None

    # latest_activity group
    latest_session_at: Optional[str] = None
    latest_activity_at: Optional[str] = None

    # model_provider_summary group
    model_families: Optional[list[dict]] = None
    providers: Optional[list[dict]] = None
    workflow_types: Optional[list[dict]] = None

    # doc_metrics group
    linked_doc_count: Optional[int] = None
    linked_doc_counts_by_type: Optional[list[dict]] = None
    linked_task_count: Optional[int] = None
    linked_commit_count: Optional[int] = None
    linked_pr_count: Optional[int] = None

    # test_metrics group (opt-in)
    test_count: Optional[int] = None
    failing_test_count: Optional[int] = None


class FeatureRollupBatch(BaseModel):
    """Response from ``get_feature_session_rollups``.

    ``rollups`` is keyed by feature_id.  ``missing`` lists requested IDs that
    had no matching feature in the project.  ``errors`` maps feature_id to a
    non-fatal error dict for partially-failed rollups.
    """

    rollups: dict[str, FeatureRollupEntry] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    errors: dict[str, dict] = Field(default_factory=dict)
    generated_at: Optional[str] = None
    cache_version: str = ""


# Alias for symmetry with FeatureListPage
FeatureRollupPage = FeatureRollupBatch


# ---------------------------------------------------------------------------
# Linked-session query
# ---------------------------------------------------------------------------

class LinkedSessionQuery(BaseModel):
    """Options for ``list_feature_session_refs`` / ``list_session_family_refs``.

    Supports offset-based pagination (Phase 1) with an optional opaque cursor
    for future cursor-based migration (Phase 2+, performance-budgets.md §3.2).
    """

    feature_id: str
    root_session_id: Optional[str] = Field(
        None, description="Restrict to sessions within the family of this root session"
    )
    thread_expansion: ThreadExpansionMode = ThreadExpansionMode.NONE

    sort_by: Literal["started_at", "updated_at"] = "started_at"
    sort_direction: SortDirection = SortDirection.DESC

    limit: int = Field(20, ge=1, le=50)
    offset: int = Field(0, ge=0)
    cursor: Optional[str] = Field(
        None,
        description="Opaque cursor for cursor-based pagination (Phase 2); "
        "when provided, offset is ignored.",
    )


# ---------------------------------------------------------------------------
# Linked-session page
# ---------------------------------------------------------------------------

class LinkedSessionPage(BaseModel):
    """Paginated result from ``list_feature_session_refs``."""

    rows: list[dict] = Field(default_factory=list)
    total: int = Field(0, ge=0)
    offset: int = Field(0, ge=0)
    limit: int = Field(20, ge=1)
    next_cursor: Optional[str] = None
    has_more: bool = False
