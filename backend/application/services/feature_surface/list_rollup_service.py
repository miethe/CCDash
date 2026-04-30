"""Feature-surface list and rollup composition services.

This service layer sits on top of the Phase 1 repository primitives and keeps
feature-card reads bounded:
  * feature list rows come from ``features.list_feature_cards()``
  * phase summaries come from one bulk ``list_phase_summaries_for_features()``
  * session/doc/test rollups come from ``get_feature_session_rollups()``

It intentionally does not load linked-session detail or session logs.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.common import require_project
from backend.db.repositories.feature_queries import (
    FeatureListPage,
    FeatureListQuery,
    FeatureRollupBatch,
    FeatureRollupQuery,
    FeatureSortKey,
    PhaseSummary,
    PhaseSummaryBulkQuery,
    RollupFieldGroup,
)
from backend.db.repositories.feature_rollup import (
    PostgresFeatureRollupRepository,
    SqliteFeatureRollupRepository,
)

FeatureSurfaceListInclude = Literal["phase_summary"]

_SUPPORTED_LIST_INCLUDES: frozenset[str] = frozenset({"phase_summary"})
_SUPPORTED_ROLLUP_FIELDS: frozenset[str] = frozenset(
    {
        "session_counts",
        "token_cost_totals",
        "model_provider_summary",
        "latest_activity",
        "doc_metrics",
        "test_metrics",
        "freshness",
    }
)
_UNSUPPORTED_ROLLUP_FIELDS: frozenset[str] = frozenset({"task_metrics"})


class FeatureCardPhaseSummaryDTO(BaseModel):
    phase_id: str
    name: str
    status: str | None = None
    order_index: int | None = None
    total_tasks: int = 0
    completed_tasks: int = 0
    progress: float | None = None


class FeatureCardRowDTO(BaseModel):
    id: str
    name: str = ""
    status: str = ""
    category: str = ""
    total_tasks: int = 0
    completed_tasks: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    phase_summary: list[FeatureCardPhaseSummaryDTO] = Field(default_factory=list)


class FeatureListSortMetadataDTO(BaseModel):
    requested_sort_by: str
    applied_sort_by: str
    sort_direction: str
    precision: Literal["exact", "fallback"]
    note: str | None = None


class FeatureCardPageDTO(BaseModel):
    rows: list[FeatureCardRowDTO] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50
    has_more: bool = False
    truncated: bool = False
    sort: FeatureListSortMetadataDTO


class FeatureSurfaceListRollupService:
    """Compose bounded feature-card list rows and batch rollups."""

    async def list_feature_cards(
        self,
        context: RequestContext,
        ports: CorePorts,
        query: FeatureListQuery,
        *,
        requested_project_id: str | None = None,
        include: Iterable[FeatureSurfaceListInclude] | None = None,
    ) -> FeatureCardPageDTO:
        include_fields = self._normalize_list_includes(include)

        project = require_project(context, ports, requested_project_id=requested_project_id)
        feature_repo = ports.storage.features()
        page: FeatureListPage = await feature_repo.list_feature_cards(project.id, query)

        feature_ids = [str(row.get("id") or "") for row in page.rows if row.get("id")]
        phase_summaries_by_feature: dict[str, list[PhaseSummary]] = {fid: [] for fid in feature_ids}

        if feature_ids and "phase_summary" in include_fields:
            phase_summaries_by_feature = await feature_repo.list_phase_summaries_for_features(
                project.id,
                PhaseSummaryBulkQuery(feature_ids=feature_ids),
            )

        rows = [
            self._build_card_row(row, phase_summaries_by_feature.get(str(row.get("id") or ""), []))
            for row in page.rows
        ]

        return FeatureCardPageDTO(
            rows=rows,
            total=page.total,
            offset=page.offset,
            limit=page.limit,
            has_more=page.has_more,
            truncated=page.truncated,
            sort=self._build_sort_metadata(query),
        )

    async def get_feature_rollups(
        self,
        context: RequestContext,
        ports: CorePorts,
        query: FeatureRollupQuery,
        *,
        requested_project_id: str | None = None,
    ) -> FeatureRollupBatch:
        normalized_query = self._normalize_rollup_query(query)
        project = require_project(context, ports, requested_project_id=requested_project_id)
        repo = self._build_rollup_repository(ports.storage.db)
        return await repo.get_feature_session_rollups(project.id, normalized_query)

    def build_rollup_query(
        self,
        *,
        feature_ids: list[str],
        fields: Iterable[str] | None = None,
        include_freshness: bool | None = None,
        include_test_metrics: bool = False,
        include_subthread_resolution: bool = False,
    ) -> FeatureRollupQuery:
        requested_fields = set(fields or [])
        self._validate_rollup_fields(requested_fields)

        normalized_fields = {field for field in requested_fields if field != "freshness"}
        resolved_include_freshness = bool(include_freshness)
        if "freshness" in requested_fields:
            resolved_include_freshness = True
        elif include_freshness is None:
            resolved_include_freshness = not requested_fields

        if not normalized_fields and not resolved_include_freshness:
            raise ValueError("At least one rollup field must be requested.")

        return FeatureRollupQuery(
            feature_ids=feature_ids,
            include_fields=normalized_fields,
            include_freshness=resolved_include_freshness,
            include_test_metrics=include_test_metrics,
            include_subthread_resolution=include_subthread_resolution,
        )

    def _normalize_list_includes(
        self,
        include: Iterable[FeatureSurfaceListInclude] | None,
    ) -> set[str]:
        include_fields = set(include or {"phase_summary"})
        unsupported = include_fields - _SUPPORTED_LIST_INCLUDES
        if unsupported:
            raise ValueError(
                f"Unsupported feature list include field(s): {sorted(unsupported)}. "
                f"Supported values: {sorted(_SUPPORTED_LIST_INCLUDES)}."
            )
        return include_fields

    def _normalize_rollup_query(self, query: FeatureRollupQuery) -> FeatureRollupQuery:
        include_fields = set(query.include_fields)
        self._validate_rollup_fields(include_fields)

        normalized_fields = {field for field in include_fields if field != "freshness"}
        normalized_include_freshness = query.include_freshness or ("freshness" in include_fields)

        if not normalized_fields and not normalized_include_freshness:
            raise ValueError("At least one rollup field must be requested.")

        return FeatureRollupQuery(
            feature_ids=list(query.feature_ids),
            include_fields=normalized_fields,
            include_freshness=normalized_include_freshness,
            include_test_metrics=query.include_test_metrics,
            include_subthread_resolution=query.include_subthread_resolution,
        )

    def _validate_rollup_fields(self, fields: set[str]) -> None:
        unsupported = fields & _UNSUPPORTED_ROLLUP_FIELDS
        if unsupported:
            raise ValueError(
                f"Unsupported rollup field group(s): {sorted(unsupported)}. "
                "These groups are defined in the Phase 1 query model but are not "
                "backed by the current Phase 1 repositories."
            )

        unknown = fields - _SUPPORTED_ROLLUP_FIELDS - _UNSUPPORTED_ROLLUP_FIELDS
        if unknown:
            raise ValueError(
                f"Unknown rollup field group(s): {sorted(unknown)}. "
                f"Supported values: {sorted(_SUPPORTED_ROLLUP_FIELDS | _UNSUPPORTED_ROLLUP_FIELDS)}."
            )

    def _build_card_row(
        self,
        row: dict[str, Any],
        phase_summaries: list[PhaseSummary],
    ) -> FeatureCardRowDTO:
        return FeatureCardRowDTO(
            id=str(row.get("id") or ""),
            name=str(row.get("name") or ""),
            status=str(row.get("status") or ""),
            category=str(row.get("category") or ""),
            total_tasks=int(row.get("total_tasks") or 0),
            completed_tasks=int(row.get("completed_tasks") or 0),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            completed_at=row.get("completed_at"),
            raw=dict(row),
            phase_summary=[
                FeatureCardPhaseSummaryDTO(
                    phase_id=summary.phase_id,
                    name=summary.name,
                    status=summary.status,
                    order_index=summary.order_index,
                    total_tasks=summary.total_tasks,
                    completed_tasks=summary.completed_tasks,
                    progress=summary.progress,
                )
                for summary in phase_summaries
            ],
        )

    def _build_sort_metadata(self, query: FeatureListQuery) -> FeatureListSortMetadataDTO:
        if query.sort_by == FeatureSortKey.LATEST_ACTIVITY:
            return FeatureListSortMetadataDTO(
                requested_sort_by=query.sort_by.value,
                applied_sort_by=query.sort_by.value,
                sort_direction=query.effective_sort_direction.value,
                precision="exact",
            )

        if query.sort_by == FeatureSortKey.SESSION_COUNT:
            return FeatureListSortMetadataDTO(
                requested_sort_by=query.sort_by.value,
                applied_sort_by=query.sort_by.value,
                sort_direction=query.effective_sort_direction.value,
                precision="exact",
            )

        return FeatureListSortMetadataDTO(
            requested_sort_by=query.sort_by.value,
            applied_sort_by=query.sort_by.value,
            sort_direction=query.effective_sort_direction.value,
            precision="exact",
        )

    def _build_rollup_repository(self, db: Any) -> Any:
        if hasattr(db, "fetch"):
            return PostgresFeatureRollupRepository(db)
        return SqliteFeatureRollupRepository(db)


__all__ = [
    "FeatureCardPageDTO",
    "FeatureCardPhaseSummaryDTO",
    "FeatureCardRowDTO",
    "FeatureListSortMetadataDTO",
    "FeatureSurfaceListRollupService",
]
