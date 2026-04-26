"""Handler functions for v1 client API feature endpoints."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services import resolve_application_request
from backend.application.services.agent_queries import (
    FeatureForensicsDTO,
    FeatureForensicsQueryService,
)
from backend.application.services.agent_queries.models import SessionRef
from backend.application.services.feature_surface import (
    FeatureSurfaceListRollupService,
    ModalSectionResult,
)
from backend.application.services.feature_surface.modal_service import FeatureModalDetailService
from backend.db.repositories.feature_queries import (
    DateRange,
    FeatureListQuery,
    FeatureSortKey,
    SortDirection,
    ThreadExpansionMode,
)
from backend.document_linking import canonical_slug
from backend.routers.client_v1_models import (
    ClientV1Envelope,
    ClientV1PaginatedEnvelope,
    DTOFreshness,
    FeatureCardDTO,
    FeatureDependencySummaryDTO,
    FeatureDocumentCoverageDTO,
    FeatureDocumentSummaryDTO,
    FeatureModalOverviewDTO,
    FeatureModalSectionDTO,
    FeatureModalSectionItemDTO,
    FeatureRollupBucketDTO,
    FeatureRollupErrorDTO,
    FeatureRollupDTO,
    FeatureRollupResponseDTO,
    LinkedFeatureSessionDTO,
    LinkedFeatureSessionPageDTO,
    LinkedFeatureSessionTaskDTO,
    LinkedSessionEnrichmentDTO,
    FeatureDocumentsDTO,
    FeatureSessionsDTO,
    FeatureSummaryDTO,
    build_client_v1_meta,
    build_client_v1_paginated_meta,
)

logger = logging.getLogger("ccdash.client_v1.features")

_feature_forensics_query_service = FeatureForensicsQueryService()
_feature_surface_list_rollup_service = FeatureSurfaceListRollupService()
_feature_modal_detail_service = FeatureModalDetailService()

_MAX_LIMIT = 200
_SUPPORTED_LIST_VIEWS = {"summary", "cards"}
_SUPPORTED_MODAL_SECTIONS = {
    "overview",
    "phases",
    "documents",
    "relations",
    "sessions",
    "test_status",
    "activity",
}
_SUPPORTED_LIST_INCLUDES = {"phase_summary"}
_SUPPORTED_MODAL_SECTION_INCLUDES: dict[str, frozenset[str]] = {
    section: frozenset() for section in _SUPPORTED_MODAL_SECTIONS if section != "overview"
}
_FEATURE_SURFACE_OBSERVABILITY_EVENT = "Feature surface v1 request observed"


def _score_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _feature_row_score(row: dict[str, Any]) -> tuple[int, int, int, str, int]:
    status = str(row.get("status") or "").lower()
    status_rank = {
        "done": 4,
        "completed": 4,
        "review": 3,
        "in-progress": 2,
        "active": 2,
        "planned": 1,
    }.get(status, 0)
    completed = _score_int(row.get("completed_tasks"))
    total = _score_int(row.get("total_tasks"))
    updated_at = str(row.get("updated_at") or "")
    feature_id = str(row.get("id") or "")
    return (status_rank, completed, total, updated_at, len(feature_id))


def _project_id_from_context(context: RequestContext) -> str:
    project = getattr(context, "project", None)
    return str(getattr(project, "project_id", "") or getattr(project, "id", "") or "")


async def _resolve_feature_alias_id(storage: Any, context: RequestContext, feature_id: str) -> str:
    """Resolve base-slug aliases to the best concrete feature row for v1 modal paths."""
    feature_repo = storage.features()
    existing = await feature_repo.get_by_id(feature_id)
    if existing is not None:
        return feature_id

    project_id = _project_id_from_context(context)
    if not project_id or not hasattr(feature_repo, "list_all"):
        return feature_id

    base = canonical_slug(feature_id)
    candidates = await feature_repo.list_all(project_id)
    matches = [
        dict(row)
        for row in candidates
        if canonical_slug(str(row.get("id") or "")) == base
    ]
    if not matches:
        return feature_id
    matches.sort(key=_feature_row_score, reverse=True)
    return str(matches[0].get("id") or feature_id)


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class FeatureCardPageResponseDTO(_CamelModel):
    items: list[FeatureCardDTO] = Field(default_factory=list)
    total: int = Field(0, ge=0)
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)
    has_more: bool = False
    query_hash: str = ""
    precision: Literal["exact", "eventually_consistent", "partial"] = "exact"
    includes: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: dict[str, Any] = Field(default_factory=dict)
    freshness: DTOFreshness | None = None


class FeatureRollupsRequest(_CamelModel):
    feature_ids: list[str] = Field(..., min_length=1, max_length=100)
    fields: list[str] = Field(default_factory=list)
    include_inherited_threads: bool | None = None
    include_freshness: bool | None = None
    include_test_metrics: bool = False
    include_subthread_resolution: bool = False


class FeatureRollupBatchDTO(_CamelModel):
    items: list[FeatureRollupDTO] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    errors: dict[str, dict[str, Any]] = Field(default_factory=dict)
    generated_at: str = ""
    cache_version: str = ""


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, _MAX_LIMIT))


def _instance_id() -> str:
    from backend import config as _cfg

    return getattr(_cfg, "INSTANCE_ID", "") or "ccdash-local"


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    return value


def _payload_size_estimate(value: Any) -> int:
    try:
        encoded = json.dumps(_to_jsonable(value), separators=(",", ":"), default=str)
    except Exception:
        return 0
    return len(encoded.encode("utf-8"))


def _classify_observability_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "validation_error"
    if isinstance(exc, HTTPException):
        if exc.status_code == 404:
            return "not_found"
        if 400 <= exc.status_code < 500:
            return "client_error"
        return "server_error"
    if isinstance(exc, ValueError):
        return "bad_request"
    return "unexpected_error"


def _emit_feature_surface_observation(
    operation: str,
    *,
    started_at: float,
    result_count: int,
    payload: Any,
    cache_status: str,
    error_category: str = "none",
    **fields: Any,
) -> None:
    logger.info(
        _FEATURE_SURFACE_OBSERVABILITY_EVENT,
        extra={
            "operation": operation,
            "latency_ms": round((time.perf_counter() - started_at) * 1000.0, 3),
            "result_count": max(0, int(result_count)),
            "payload_size_estimate": _payload_size_estimate(payload),
            "cache_status": str(cache_status or "unknown"),
            "error_category": error_category,
            **{key: value for key, value in fields.items() if value is not None},
        },
    )


async def _resolve_app_request(
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    requested_project_id: str | None = None,
):
    return await resolve_application_request(
        request_context,
        core_ports,
        core_ports.storage.db,
        requested_project_id=requested_project_id,
    )


def _row_to_feature_summary(row: dict[str, Any]) -> FeatureSummaryDTO:
    return FeatureSummaryDTO(
        id=row.get("id", ""),
        name=row.get("name", ""),
        status=row.get("status", ""),
        category=row.get("category", ""),
        priority=row.get("priority", ""),
        total_tasks=row.get("total_tasks", 0) or 0,
        completed_tasks=row.get("completed_tasks", 0) or 0,
        updated_at=row.get("updated_at", ""),
    )


def _feature_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    raw = row.get("data_json")
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    raw_payload = row.get("raw")
    if isinstance(raw_payload, dict):
        nested = raw_payload.get("data_json")
        if isinstance(nested, dict):
            return dict(nested)
        if isinstance(nested, str) and nested.strip():
            try:
                parsed = json.loads(nested)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
    return {}


def _query_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _build_date_range(from_date: str | None, to_date: str | None) -> DateRange | None:
    if not from_date and not to_date:
        return None
    return DateRange(from_date=from_date, to_date=to_date)


def _translate_validation_error(exc: ValidationError) -> HTTPException:
    details = exc.errors()
    status_code = 422
    if any("Unknown rollup field group" in str(item.get("msg", "")) for item in details):
        status_code = 400
    return HTTPException(status_code=status_code, detail=details)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _validate_view(view: str) -> None:
    if view not in _SUPPORTED_LIST_VIEWS:
        raise _bad_request(
            f"Unsupported feature list view '{view}'. Supported values: {sorted(_SUPPORTED_LIST_VIEWS)}."
        )


def _validate_list_includes(include: list[str] | None) -> list[str]:
    requested = list(dict.fromkeys(include or ["phase_summary"]))
    unsupported = sorted(set(requested) - _SUPPORTED_LIST_INCLUDES)
    if unsupported:
        raise _bad_request(
            f"Unsupported feature list include field(s): {unsupported}. "
            f"Supported values: {sorted(_SUPPORTED_LIST_INCLUDES)}."
        )
    return requested


def _validate_modal_section(section: str) -> str:
    if section not in _SUPPORTED_MODAL_SECTIONS:
        raise _bad_request(
            f"Unsupported feature modal section '{section}'. Supported values: {sorted(_SUPPORTED_MODAL_SECTIONS)}."
        )
    return section


def _validate_modal_includes(section: str, include: list[str] | None) -> list[str]:
    requested = list(dict.fromkeys(include or []))
    supported = _SUPPORTED_MODAL_SECTION_INCLUDES.get(section, frozenset())
    unsupported = sorted(set(requested) - supported)
    if unsupported:
        raise _bad_request(
            f"Unsupported include field(s) for section '{section}': {unsupported}. "
            f"Supported values: {sorted(supported)}."
        )
    return requested


def _build_card_dto(row: dict[str, Any], *, precision: str = "exact") -> FeatureCardDTO:
    source_row = row.get("raw") if isinstance(row.get("raw"), dict) else row
    payload = _feature_payload(source_row)
    planning_status = payload.get("planningStatus") if isinstance(payload.get("planningStatus"), dict) else {}
    quality_signals = payload.get("qualitySignals") if isinstance(payload.get("qualitySignals"), dict) else {}
    dependency_state = payload.get("dependencyState") if isinstance(payload.get("dependencyState"), dict) else {}
    document_coverage = payload.get("documentCoverage") if isinstance(payload.get("documentCoverage"), dict) else {}
    primary_documents = payload.get("primaryDocuments") if isinstance(payload.get("primaryDocuments"), list) else []
    family_position = payload.get("familyPosition") if isinstance(payload.get("familyPosition"), dict) else None
    related_features = payload.get("relatedFeatures") if isinstance(payload.get("relatedFeatures"), list) else []
    phase_summary = row.get("phase_summary") if isinstance(row.get("phase_summary"), list) else []

    return FeatureCardDTO.model_validate(
        {
            "id": str(row.get("id") or ""),
            "name": str(row.get("name") or ""),
            "status": str(row.get("status") or ""),
            "effectiveStatus": str(planning_status.get("effectiveStatus") or row.get("status") or ""),
            "category": str(row.get("category") or ""),
            "tags": payload.get("tags") if isinstance(payload.get("tags"), list) else [],
            "summary": str(payload.get("summary") or ""),
            "descriptionPreview": str(payload.get("description") or "")[:280],
            "priority": str(payload.get("priority") or row.get("priority") or ""),
            "riskLevel": str(payload.get("riskLevel") or ""),
            "complexity": str(payload.get("complexity") or ""),
            "executionReadiness": str(payload.get("executionReadiness") or ""),
            "testImpact": str(payload.get("testImpact") or quality_signals.get("testImpact") or ""),
            "planningStatus": planning_status or None,
            "totalTasks": int(row.get("total_tasks") or 0),
            "completedTasks": int(row.get("completed_tasks") or 0),
            "deferredTasks": int(payload.get("deferredTasks") or 0),
            "phaseCount": int(payload.get("phaseCount") or len(phase_summary) or 0),
            "plannedAt": str(payload.get("plannedAt") or ""),
            "startedAt": str(payload.get("startedAt") or ""),
            "completedAt": str(row.get("completed_at") or payload.get("completedAt") or ""),
            "updatedAt": str(row.get("updated_at") or ""),
            "documentCoverage": FeatureDocumentCoverageDTO.model_validate(
                {
                    "present": document_coverage.get("present") if isinstance(document_coverage.get("present"), list) else [],
                    "missing": document_coverage.get("missing") if isinstance(document_coverage.get("missing"), list) else [],
                    "countsByType": document_coverage.get("countsByType")
                    if isinstance(document_coverage.get("countsByType"), dict)
                    else {},
                }
            ).model_dump(mode="python", by_alias=True, exclude_none=True),
            "qualitySignals": {
                "blockerCount": int(quality_signals.get("blockerCount") or 0),
                "atRiskTaskCount": int(quality_signals.get("atRiskTaskCount") or 0),
                "hasBlockingSignals": bool(quality_signals.get("hasBlockingSignals") or quality_signals.get("blockerCount")),
                "testImpact": str(quality_signals.get("testImpact") or ""),
                "integritySignalRefs": quality_signals.get("integritySignalRefs")
                if isinstance(quality_signals.get("integritySignalRefs"), list)
                else [],
            },
            "dependencyState": FeatureDependencySummaryDTO.model_validate(
                {
                    "state": str(dependency_state.get("state") or ""),
                    "blockingReason": str(dependency_state.get("blockingReason") or ""),
                    "blockedByCount": int(dependency_state.get("blockedByCount") or 0),
                    "readyDependencyCount": int(dependency_state.get("readyDependencyCount") or 0),
                }
            ).model_dump(mode="python", by_alias=True, exclude_none=True),
            "primaryDocuments": [
                FeatureDocumentSummaryDTO.model_validate(
                    {
                        "documentId": str(item.get("documentId") or item.get("document_id") or ""),
                        "title": str(item.get("title") or ""),
                        "docType": str(item.get("docType") or item.get("doc_type") or ""),
                        "status": str(item.get("status") or ""),
                        "filePath": str(item.get("filePath") or item.get("file_path") or ""),
                        "updatedAt": str(item.get("updatedAt") or item.get("updated_at") or ""),
                    }
                ).model_dump(mode="python", by_alias=True, exclude_none=True)
                for item in primary_documents
                if isinstance(item, dict)
            ],
            "familyPosition": (
                {
                    "position": family_position.get("position", family_position.get("index")),
                    "total": family_position.get("total"),
                    "label": str(family_position.get("label") or ""),
                    "nextItemId": str(family_position.get("nextItemId") or family_position.get("next_item_id") or ""),
                    "nextItemLabel": str(family_position.get("nextItemLabel") or family_position.get("next_item_label") or ""),
                }
                if family_position
                else None
            ),
            "relatedFeatureCount": len(related_features),
            "precision": precision,
        }
    )


def _build_rollup_dto(feature_id: str, rollup: Any) -> FeatureRollupDTO:
    freshness = getattr(rollup, "freshness", None)
    freshness_payload: dict[str, Any] | None = None
    if freshness is not None:
        freshness_payload = {
            "observedAt": None,
            "sourceRevision": "",
            "cacheVersion": getattr(freshness, "cache_version", "") or "",
            "sessionSyncAt": getattr(freshness, "session_sync_at", "") or "",
            "linksUpdatedAt": getattr(freshness, "links_updated_at", "") or "",
            "testHealthAt": getattr(freshness, "test_health_at", "") or "",
        }

    return FeatureRollupDTO.model_validate(
        {
            "featureId": feature_id,
            "sessionCount": getattr(rollup, "session_count", None),
            "primarySessionCount": getattr(rollup, "primary_session_count", None),
            "subthreadCount": getattr(rollup, "subthread_count", None),
            "totalCost": getattr(rollup, "total_cost", None),
            "displayCost": getattr(rollup, "display_cost", None),
            "observedTokens": getattr(rollup, "observed_tokens", None),
            "modelIoTokens": getattr(rollup, "model_io_tokens", None),
            "cacheInputTokens": getattr(rollup, "cache_input_tokens", None),
            "latestSessionAt": getattr(rollup, "latest_session_at", "") or "",
            "latestActivityAt": getattr(rollup, "latest_activity_at", "") or "",
            "modelFamilies": [
                FeatureRollupBucketDTO.model_validate(item).model_dump(mode="python", by_alias=True, exclude_none=True)
                for item in (getattr(rollup, "model_families", None) or [])
                if isinstance(item, dict)
            ],
            "providers": [
                FeatureRollupBucketDTO.model_validate(item).model_dump(mode="python", by_alias=True, exclude_none=True)
                for item in (getattr(rollup, "providers", None) or [])
                if isinstance(item, dict)
            ],
            "workflowTypes": [
                FeatureRollupBucketDTO.model_validate(item).model_dump(mode="python", by_alias=True, exclude_none=True)
                for item in (getattr(rollup, "workflow_types", None) or [])
                if isinstance(item, dict)
            ],
            "linkedDocCount": getattr(rollup, "linked_doc_count", None),
            "linkedTaskCount": getattr(rollup, "linked_task_count", None),
            "testCount": getattr(rollup, "test_count", None),
            "failingTestCount": getattr(rollup, "failing_test_count", None),
            "precision": getattr(rollup, "precision", "eventually_consistent"),
            "freshness": freshness_payload,
        }
    )


def _session_row_to_session_ref(row: dict[str, Any], feature_id: str) -> SessionRef:
    tokens = row.get("observed_tokens")
    if tokens in (None, ""):
        tokens = int(row.get("tokens_in") or 0) + int(row.get("tokens_out") or 0)
    return SessionRef(
        session_id=str(row.get("session_id") or ""),
        feature_id=feature_id,
        root_session_id=str(row.get("root_session_id") or ""),
        title=str(row.get("title") or ""),
        status=str(row.get("status") or ""),
        started_at=str(row.get("started_at") or ""),
        ended_at=str(row.get("ended_at") or ""),
        model=str(row.get("model") or ""),
        total_cost=float(row.get("total_cost") or 0.0),
        total_tokens=int(tokens or 0),
        duration_seconds=0.0,
        source_ref="feature_surface.linked_session_page",
    )


def _session_row_to_linked_dto(row: dict[str, Any]) -> LinkedFeatureSessionDTO:
    task_refs = row.get("related_tasks")
    if not isinstance(task_refs, list):
        task_refs = []
    return LinkedFeatureSessionDTO.model_validate(
        {
            "sessionId": str(row.get("session_id") or ""),
            "title": str(row.get("title") or ""),
            "status": str(row.get("status") or ""),
            "model": str(row.get("model") or ""),
            "modelProvider": str(row.get("platform_type") or ""),
            "modelFamily": str(row.get("model_family") or ""),
            "startedAt": str(row.get("started_at") or ""),
            "endedAt": str(row.get("ended_at") or ""),
            "updatedAt": str(row.get("updated_at") or ""),
            "totalCost": float(row.get("total_cost") or 0.0),
            "observedTokens": int(row.get("observed_tokens") or 0),
            "rootSessionId": str(row.get("root_session_id") or ""),
            "parentSessionId": row.get("parent_session_id"),
            "workflowType": str(row.get("session_type") or ""),
            "isPrimaryLink": bool(row.get("is_primary_link", True)),
            "isSubthread": bool(row.get("parent_session_id")),
            "threadChildCount": int(row.get("thread_child_count") or 0),
            "reasons": row.get("reasons") if isinstance(row.get("reasons"), list) else [],
            "commands": row.get("commands") if isinstance(row.get("commands"), list) else [],
            "relatedTasks": [
                LinkedFeatureSessionTaskDTO.model_validate(
                    {
                        "taskId": str(item.get("task_id") or ""),
                        "taskTitle": str(item.get("task_title") or item.get("title") or ""),
                        "phaseId": str(item.get("phase_id") or ""),
                        "phase": str(item.get("phase") or ""),
                        "matchedBy": str(item.get("matched_by") or ""),
                    }
                )
                for item in task_refs
                if isinstance(item, dict)
            ],
        }
    )


def _build_modal_title(section: str) -> str:
    return section.replace("_", " ").title()


def _section_result_to_dto(
    feature_id: str,
    section: str,
    result: ModalSectionResult,
    *,
    includes: list[str],
    limit: int,
    offset: int,
) -> FeatureModalSectionDTO:
    data = result.data or {}
    items: list[FeatureModalSectionItemDTO] = []
    total = int(data.get("total") or 0)
    has_more = bool(data.get("has_more"))

    if section == "phases":
        phases = data.get("phases") if isinstance(data.get("phases"), list) else []
        total = len(phases)
        has_more = False
        items = [
            FeatureModalSectionItemDTO(
                item_id=str(phase.get("phase_id") or ""),
                label=str(phase.get("name") or ""),
                kind="phase",
                status=str(phase.get("status") or ""),
                badges=[
                    f"{int(phase.get('completed_tasks') or 0)}/{int(phase.get('total_tasks') or 0)} tasks"
                ],
                metadata={
                    "orderIndex": phase.get("order_index"),
                    "progress": phase.get("progress"),
                    "tasks": phase.get("tasks") if isinstance(phase.get("tasks"), list) else [],
                },
            )
            for phase in phases
            if isinstance(phase, dict)
        ]
    elif section == "documents":
        docs = data.get("documents") if isinstance(data.get("documents"), list) else []
        total = len(docs)
        items = [
            FeatureModalSectionItemDTO(
                item_id=str(doc.get("document_id") or ""),
                label=str(doc.get("title") or ""),
                kind=str(doc.get("doc_type") or "document"),
                status=str(doc.get("status") or ""),
                href=str(doc.get("file_path") or ""),
                metadata=doc,
            )
            for doc in docs
            if isinstance(doc, dict)
        ]
    elif section == "relations":
        linked = data.get("linked_features") if isinstance(data.get("linked_features"), list) else []
        related = data.get("related_features") if isinstance(data.get("related_features"), list) else []
        records: list[dict[str, Any]] = []
        for item in linked:
            if isinstance(item, dict):
                records.append({"kind": "linked_feature", **item})
        for item in related:
            if isinstance(item, dict):
                records.append({"kind": "related_feature", **item})
            elif isinstance(item, str):
                records.append({"kind": "related_feature", "feature": item})
        total = len(records)
        items = [
            FeatureModalSectionItemDTO(
                item_id=str(item.get("feature") or item.get("feature_id") or item.get("id") or ""),
                label=str(item.get("label") or item.get("name") or item.get("feature") or ""),
                kind=str(item.get("kind") or "relation"),
                status=str(item.get("type") or item.get("status") or ""),
                metadata=item,
            )
            for item in records
        ]
    elif section == "sessions":
        rows = data.get("rows") if isinstance(data.get("rows"), list) else []
        total = int(data.get("total") or 0)
        has_more = bool(data.get("has_more"))
        items = [
            FeatureModalSectionItemDTO(
                item_id=str(row.get("session_id") or ""),
                label=str(row.get("title") or row.get("session_id") or ""),
                kind="session",
                status=str(row.get("status") or ""),
                badges=[str(row.get("model") or "")] if row.get("model") else [],
                metadata=_session_row_to_linked_dto(row).model_dump(mode="json", by_alias=True, exclude_none=True),
            )
            for row in rows
            if isinstance(row, dict)
        ]
    elif section == "test_status":
        tests = data.get("items") if isinstance(data.get("items"), list) else []
        total = len(tests)
        items = [
            FeatureModalSectionItemDTO(
                item_id=str(item.get("id") or item.get("name") or ""),
                label=str(item.get("name") or item.get("label") or ""),
                kind=str(item.get("kind") or "test"),
                status=str(item.get("status") or ""),
                metadata=item,
            )
            for item in tests
            if isinstance(item, dict)
        ]
    elif section == "activity":
        activity = data.get("items") if isinstance(data.get("items"), list) else []
        total = len(activity)
        items = [
            FeatureModalSectionItemDTO(
                item_id=str(item.get("id") or item.get("timestamp") or ""),
                label=str(item.get("label") or item.get("kind") or ""),
                kind=str(item.get("kind") or "activity"),
                status=str(item.get("status") or ""),
                metadata=item,
            )
            for item in activity
            if isinstance(item, dict)
        ]

    precision = "exact"
    if result.status == "unavailable":
        precision = "partial"
    elif section == "sessions":
        precision = "eventually_consistent"

    return FeatureModalSectionDTO(
        feature_id=feature_id,
        section=section,
        title=_build_modal_title(section),
        items=items,
        total=total,
        offset=int(data.get("offset") or offset),
        limit=int(data.get("limit") or limit),
        has_more=has_more,
        includes=includes,
        precision=precision,
    )


async def _get_forensics(
    feature_id: str,
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    bypass_cache: bool = False,
) -> tuple[FeatureForensicsDTO, str]:
    app_request = await _resolve_app_request(request_context, core_ports)
    forensics = await _feature_forensics_query_service.get_forensics(
        app_request.context,
        app_request.ports,
        feature_id,
        bypass_cache=bypass_cache,
    )
    if forensics.status == "error":
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_id}' not found.",
        )
    return forensics, forensics.feature_slug or feature_id


async def list_features_v1(
    status: list[str] | None,
    category: str | None,
    limit: int,
    offset: int,
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    q: str | None = None,
    view: str = "summary",
    stage: list[str] | None = None,
    tags: list[str] | None = None,
    has_deferred: bool | None = None,
    planned_from: str | None = None,
    planned_to: str | None = None,
    started_from: str | None = None,
    started_to: str | None = None,
    completed_from: str | None = None,
    completed_to: str | None = None,
    updated_from: str | None = None,
    updated_to: str | None = None,
    progress_min: float | None = None,
    progress_max: float | None = None,
    task_count_min: int | None = None,
    task_count_max: int | None = None,
    sort_by: FeatureSortKey = FeatureSortKey.UPDATED_DATE,
    sort_direction: SortDirection | None = None,
    include: list[str] | None = None,
) -> ClientV1PaginatedEnvelope[FeatureSummaryDTO] | ClientV1Envelope[FeatureCardPageResponseDTO]:
    started_at = time.perf_counter()
    effective_limit = _clamp_limit(limit)
    effective_offset = max(0, offset)

    try:
        requested_include = list(dict.fromkeys(include or []))
        requested_include = [
            token
            for item in requested_include
            for token in str(item).split(",")
            if str(token).strip()
        ]
        if view == "card":
            view = "cards"
        if view == "summary" and any(item in {"card", "cards"} for item in requested_include):
            view = "cards"
            include = [item for item in requested_include if item not in {"card", "cards"}]

        _validate_view(view)
    except Exception as exc:
        _emit_feature_surface_observation(
            "feature_list",
            started_at=started_at,
            result_count=0,
            payload=None,
            cache_status="unknown",
            error_category=_classify_observability_error(exc),
            view=view,
            limit=effective_limit,
            offset=effective_offset,
        )
        raise

    if view == "summary":
        try:
            app_request = await _resolve_app_request(request_context, core_ports)
            feature_repo = app_request.ports.storage.features()

            project_id: str | None = None
            try:
                scope = app_request.ports.workspace_registry.resolve_scope()
                _, project_scope = scope
                if project_scope is not None:
                    project_id = project_scope.project_id
            except Exception:
                logger.debug("Could not resolve project scope for list_features_v1")

            keyword = q.strip() if q else None
            rows = await feature_repo.list_paginated(project_id, effective_offset, effective_limit, keyword=keyword)
            total = await feature_repo.count(project_id, keyword=keyword)

            if status:
                status_lower = {s.lower() for s in status}
                rows = [r for r in rows if str(r.get("status", "")).lower() in status_lower]
            if category:
                category_lower = category.lower()
                rows = [r for r in rows if str(r.get("category", "")).lower() == category_lower]

            items = [_row_to_feature_summary(row) for row in rows]
            has_more = (effective_offset + len(items)) < total
            truncated = len(items) >= effective_limit and has_more

            envelope = ClientV1PaginatedEnvelope(
                data=items,
                meta=build_client_v1_paginated_meta(
                    instance_id=_instance_id(),
                    total=total,
                    offset=effective_offset,
                    limit=effective_limit,
                    has_more=has_more,
                    truncated=truncated,
                ),
            )
            _emit_feature_surface_observation(
                "feature_list",
                started_at=started_at,
                result_count=len(items),
                payload=envelope.data,
                cache_status="unknown",
                view="summary",
                limit=effective_limit,
                offset=effective_offset,
            )
            return envelope
        except Exception as exc:
            _emit_feature_surface_observation(
                "feature_list",
                started_at=started_at,
                result_count=0,
                payload=None,
                cache_status="unknown",
                error_category=_classify_observability_error(exc),
                view="summary",
                limit=effective_limit,
                offset=effective_offset,
            )
            raise

    try:
        resolved_include = _validate_list_includes(include)
        feature_query = FeatureListQuery(
            q=q.strip() if q else None,
            status=status or [],
            stage=stage or [],
            category=[category] if category else [],
            tags=tags or [],
            has_deferred=has_deferred,
            planned=_build_date_range(planned_from, planned_to),
            started=_build_date_range(started_from, started_to),
            completed=_build_date_range(completed_from, completed_to),
            updated=_build_date_range(updated_from, updated_to),
            progress_min=progress_min,
            progress_max=progress_max,
            task_count_min=task_count_min,
            task_count_max=task_count_max,
            sort_by=sort_by,
            sort_direction=sort_direction,
            offset=effective_offset,
            limit=effective_limit,
        )
        app_request = await _resolve_app_request(request_context, core_ports)
        page = await _feature_surface_list_rollup_service.list_feature_cards(
            app_request.context,
            app_request.ports,
            feature_query,
            include=resolved_include,
        )
        filter_payload = {
            "q": feature_query.q,
            "status": feature_query.status,
            "stage": feature_query.stage,
            "category": feature_query.category,
            "tags": feature_query.tags,
            "hasDeferred": feature_query.has_deferred,
            "planned": feature_query.planned.model_dump(exclude_none=True) if feature_query.planned else None,
            "started": feature_query.started.model_dump(exclude_none=True) if feature_query.started else None,
            "completed": feature_query.completed.model_dump(exclude_none=True) if feature_query.completed else None,
            "updated": feature_query.updated.model_dump(exclude_none=True) if feature_query.updated else None,
            "progressMin": feature_query.progress_min,
            "progressMax": feature_query.progress_max,
            "taskCountMin": feature_query.task_count_min,
            "taskCountMax": feature_query.task_count_max,
        }
        dto = FeatureCardPageResponseDTO(
            items=[_build_card_dto(row.model_dump(mode="python"), precision=page.sort.precision) for row in page.rows],
            total=page.total,
            offset=page.offset,
            limit=page.limit,
            has_more=page.has_more,
            query_hash=_query_hash(
                {
                    "filters": filter_payload,
                    "sort": page.sort.model_dump(mode="json"),
                    "include": resolved_include,
                    "offset": page.offset,
                    "limit": page.limit,
                }
            ),
            precision="exact" if page.sort.precision == "exact" else "partial",
            includes=resolved_include,
            filters={k: v for k, v in filter_payload.items() if v not in (None, [], {})},
            sort=page.sort.model_dump(mode="json"),
        )
        envelope = ClientV1Envelope(
            data=dto,
            meta=build_client_v1_meta(instance_id=_instance_id()),
        )
        _emit_feature_surface_observation(
            "feature_list",
            started_at=started_at,
            result_count=len(dto.items),
            payload=envelope.data,
            cache_status="unknown",
            view="cards",
            limit=effective_limit,
            offset=effective_offset,
        )
        return envelope
    except ValidationError as exc:
        translated = _translate_validation_error(exc)
        _emit_feature_surface_observation(
            "feature_list",
            started_at=started_at,
            result_count=0,
            payload=None,
            cache_status="unknown",
            error_category=_classify_observability_error(translated),
            view=view,
            limit=effective_limit,
            offset=effective_offset,
        )
        raise translated from exc
    except ValueError as exc:
        translated = _bad_request(str(exc))
        _emit_feature_surface_observation(
            "feature_list",
            started_at=started_at,
            result_count=0,
            payload=None,
            cache_status="unknown",
            error_category=_classify_observability_error(translated),
            view=view,
            limit=effective_limit,
            offset=effective_offset,
        )
        raise translated from exc
    except Exception as exc:
        _emit_feature_surface_observation(
            "feature_list",
            started_at=started_at,
            result_count=0,
            payload=None,
            cache_status="unknown",
            error_category=_classify_observability_error(exc),
            view=view,
            limit=effective_limit,
            offset=effective_offset,
        )
        raise


async def get_feature_detail_v1(
    feature_id: str,
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    bypass_cache: bool = False,
) -> ClientV1Envelope[FeatureForensicsDTO]:
    forensics, _ = await _get_forensics(feature_id, request_context, core_ports, bypass_cache=bypass_cache)
    return ClientV1Envelope(
        data=forensics,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


async def get_feature_sessions_v1(
    feature_id: str,
    limit: int,
    offset: int,
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    bypass_cache: bool = False,
) -> ClientV1Envelope[FeatureSessionsDTO]:
    started_at = time.perf_counter()
    effective_limit = _clamp_limit(limit)
    effective_offset = max(0, offset)
    try:
        app_request = await _resolve_app_request(request_context, core_ports)
        remaining = effective_limit
        next_offset = effective_offset
        total = 0
        rows: list[dict[str, Any]] = []

        while remaining > 0:
            chunk_limit = min(remaining, 50)
            section = await _feature_modal_detail_service.get_sessions(
                app_request.context,
                app_request.ports,
                feature_id,
                limit=chunk_limit,
                offset=next_offset,
                thread_expansion=ThreadExpansionMode.INHERITED_THREADS,
            )
            if section.status == "not_found":
                raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found.")

            chunk_rows = section.data.get("rows") if isinstance(section.data.get("rows"), list) else []
            total = int(section.data.get("total") or total)
            rows.extend(row for row in chunk_rows if isinstance(row, dict))
            if not section.data.get("has_more") or not chunk_rows:
                break
            remaining -= len(chunk_rows)
            next_offset += len(chunk_rows)

        feature_slug = feature_id
        if not bypass_cache:
            try:
                _, feature_slug = await _get_forensics(feature_id, request_context, core_ports, bypass_cache=False)
            except HTTPException:
                logger.debug("Feature forensics unavailable for feature sessions slug lookup", exc_info=True)

        dto = FeatureSessionsDTO(
            feature_id=feature_id,
            feature_slug=feature_slug,
            sessions=[_session_row_to_session_ref(row, feature_id) for row in rows],
            total=total,
        )
        envelope = ClientV1Envelope(
            data=dto,
            meta=build_client_v1_meta(instance_id=_instance_id()),
        )
        _emit_feature_surface_observation(
            "feature_sessions_compat",
            started_at=started_at,
            result_count=len(dto.sessions),
            payload=envelope.data,
            cache_status="bypass" if bypass_cache else "unknown",
            feature_id=feature_id,
            limit=effective_limit,
            offset=effective_offset,
        )
        return envelope
    except Exception as exc:
        _emit_feature_surface_observation(
            "feature_sessions_compat",
            started_at=started_at,
            result_count=0,
            payload=None,
            cache_status="bypass" if bypass_cache else "unknown",
            error_category=_classify_observability_error(exc),
            feature_id=feature_id,
            limit=effective_limit,
            offset=effective_offset,
        )
        raise


async def get_feature_documents_v1(
    feature_id: str,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[FeatureDocumentsDTO]:
    forensics, feature_slug = await _get_forensics(feature_id, request_context, core_ports)

    dto = FeatureDocumentsDTO(
        feature_id=feature_id,
        feature_slug=feature_slug,
        documents=forensics.linked_documents,
    )
    return ClientV1Envelope(
        data=dto,
        meta=build_client_v1_meta(instance_id=_instance_id()),
    )


async def post_feature_rollups_v1(
    payload: FeatureRollupsRequest,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[FeatureRollupResponseDTO]:
    started_at = time.perf_counter()
    try:
        app_request = await _resolve_app_request(request_context, core_ports)
        include_subthread_resolution = (
            payload.include_subthread_resolution
            if payload.include_inherited_threads is None
            else payload.include_inherited_threads
        )
        query = _feature_surface_list_rollup_service.build_rollup_query(
            feature_ids=payload.feature_ids,
            fields=payload.fields,
            include_freshness=payload.include_freshness,
            include_test_metrics=payload.include_test_metrics,
            include_subthread_resolution=include_subthread_resolution,
        )
        batch = await _feature_surface_list_rollup_service.get_feature_rollups(
            app_request.context,
            app_request.ports,
            query,
        )
        dto = FeatureRollupResponseDTO(
            rollups={
                feature_id: _build_rollup_dto(feature_id, rollup)
                for feature_id, rollup in batch.rollups.items()
            },
            missing=list(batch.missing),
            errors={
                str(feature_id): FeatureRollupErrorDTO(
                    code=str(error.get("code") or ""),
                    message=str(error.get("message") or ""),
                    detail={
                        k: v
                        for k, v in error.items()
                        if k not in {"code", "message"}
                    },
                )
                for feature_id, error in batch.errors.items()
            },
            generated_at=str(batch.generated_at or ""),
            cache_version=str(batch.cache_version or ""),
        )
        envelope = ClientV1Envelope(
            data=dto,
            meta=build_client_v1_meta(instance_id=_instance_id()),
        )
        _emit_feature_surface_observation(
            "feature_rollups",
            started_at=started_at,
            result_count=len(dto.rollups),
            payload=envelope.data,
            cache_status="available" if dto.cache_version else "unknown",
            requested_feature_count=len(payload.feature_ids),
        )
        return envelope
    except ValidationError as exc:
        translated = _translate_validation_error(exc)
        _emit_feature_surface_observation(
            "feature_rollups",
            started_at=started_at,
            result_count=0,
            payload=None,
            cache_status="unknown",
            error_category=_classify_observability_error(translated),
            requested_feature_count=len(payload.feature_ids),
        )
        raise translated from exc
    except ValueError as exc:
        translated = _bad_request(str(exc))
        _emit_feature_surface_observation(
            "feature_rollups",
            started_at=started_at,
            result_count=0,
            payload=None,
            cache_status="unknown",
            error_category=_classify_observability_error(translated),
            requested_feature_count=len(payload.feature_ids),
        )
        raise translated from exc
    except Exception as exc:
        _emit_feature_surface_observation(
            "feature_rollups",
            started_at=started_at,
            result_count=0,
            payload=None,
            cache_status="unknown",
            error_category=_classify_observability_error(exc),
            requested_feature_count=len(payload.feature_ids),
        )
        raise


async def get_feature_modal_overview_v1(
    feature_id: str,
    request_context: RequestContext,
    core_ports: CorePorts,
) -> ClientV1Envelope[FeatureModalOverviewDTO]:
    started_at = time.perf_counter()
    try:
        app_request = await _resolve_app_request(request_context, core_ports)
        resolved_feature_id = await _resolve_feature_alias_id(
            app_request.ports.storage,
            app_request.context,
            feature_id,
        )
        overview = await _feature_modal_detail_service.get_overview(
            app_request.context,
            app_request.ports,
            resolved_feature_id,
        )
        if overview.status == "not_found":
            raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found.")

        feature_row = await app_request.ports.storage.features().get_by_id(resolved_feature_id)
        card = _build_card_dto(dict(feature_row or {}))

        rollup = None
        rollup_cache_status = "unknown"
        try:
            rollup_query = _feature_surface_list_rollup_service.build_rollup_query(
                feature_ids=[resolved_feature_id],
                fields=[
                    "session_counts",
                    "token_cost_totals",
                    "model_provider_summary",
                    "latest_activity",
                    "doc_metrics",
                ],
                include_freshness=True,
            )
            rollup_batch = await _feature_surface_list_rollup_service.get_feature_rollups(
                app_request.context,
                app_request.ports,
                rollup_query,
            )
            entry = rollup_batch.rollups.get(resolved_feature_id)
            if entry is not None:
                rollup = _build_rollup_dto(resolved_feature_id, entry)
            if getattr(rollup_batch, "cache_version", ""):
                rollup_cache_status = "available"
        except Exception:
            logger.debug("Feature modal overview rollup fetch failed", exc_info=True)

        dto = FeatureModalOverviewDTO(
            feature_id=resolved_feature_id,
            card=card,
            rollup=rollup,
            description=str(overview.data.get("description") or ""),
            precision="eventually_consistent" if rollup is not None else "exact",
        )
        envelope = ClientV1Envelope(
            data=dto,
            meta=build_client_v1_meta(instance_id=_instance_id()),
        )
        _emit_feature_surface_observation(
            "feature_modal_overview",
            started_at=started_at,
            result_count=1,
            payload=envelope.data,
            cache_status=rollup_cache_status,
            feature_id=resolved_feature_id,
        )
        return envelope
    except Exception as exc:
        _emit_feature_surface_observation(
            "feature_modal_overview",
            started_at=started_at,
            result_count=0,
            payload=None,
            cache_status="unknown",
            error_category=_classify_observability_error(exc),
            feature_id=feature_id,
        )
        raise


async def get_feature_modal_section_v1(
    feature_id: str,
    section: str,
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    include: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
) -> ClientV1Envelope[FeatureModalSectionDTO]:
    started_at = time.perf_counter()
    try:
        section = _validate_modal_section(section)
        resolved_include = _validate_modal_includes(section, include)
        effective_limit = max(1, min(limit, 50 if section == "sessions" else _MAX_LIMIT))
        effective_offset = max(0, offset)
        app_request = await _resolve_app_request(request_context, core_ports)
        resolved_feature_id = await _resolve_feature_alias_id(
            app_request.ports.storage,
            app_request.context,
            feature_id,
        )

        if section == "overview":
            raise _bad_request("Use GET /api/v1/features/{feature_id}/modal for overview.")

        if section == "phases":
            result = await _feature_modal_detail_service.get_phases_tasks(
                app_request.context,
                app_request.ports,
                resolved_feature_id,
            )
        elif section == "documents":
            result = await _feature_modal_detail_service.get_docs(
                app_request.context,
                app_request.ports,
                resolved_feature_id,
            )
        elif section == "relations":
            results = await _feature_modal_detail_service.get_sections(
                app_request.context,
                app_request.ports,
                resolved_feature_id,
                sections=["relations"],
            )
            result = results["relations"]
        elif section == "sessions":
            result = await _feature_modal_detail_service.get_sessions(
                app_request.context,
                app_request.ports,
                resolved_feature_id,
                limit=effective_limit,
                offset=effective_offset,
                thread_expansion=ThreadExpansionMode.INHERITED_THREADS,
            )
        elif section == "test_status":
            result = await _feature_modal_detail_service.get_test_status(
                app_request.context,
                app_request.ports,
                resolved_feature_id,
            )
        else:
            result = await _feature_modal_detail_service.get_activity(
                app_request.context,
                app_request.ports,
                resolved_feature_id,
                limit=effective_limit,
                offset=effective_offset,
            )

        if result.status == "not_found":
            raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found.")

        dto = _section_result_to_dto(
            resolved_feature_id,
            section,
            result,
            includes=resolved_include,
            limit=effective_limit,
            offset=effective_offset,
        )
        envelope = ClientV1Envelope(
            data=dto,
            meta=build_client_v1_meta(instance_id=_instance_id()),
        )
        _emit_feature_surface_observation(
            "feature_modal_section",
            started_at=started_at,
            result_count=len(dto.items),
            payload=envelope.data,
            cache_status="unknown",
            feature_id=resolved_feature_id,
            section=section,
            limit=effective_limit,
            offset=effective_offset,
        )
        return envelope
    except Exception as exc:
        normalized_section = section if section in _SUPPORTED_MODAL_SECTIONS else str(section or "")
        _emit_feature_surface_observation(
            "feature_modal_section",
            started_at=started_at,
            result_count=0,
            payload=None,
            cache_status="unknown",
            error_category=_classify_observability_error(exc),
            feature_id=feature_id,
            section=normalized_section,
            limit=limit,
            offset=offset,
        )
        raise


async def get_feature_linked_session_page_v1(
    feature_id: str,
    request_context: RequestContext,
    core_ports: CorePorts,
    *,
    limit: int = 20,
    offset: int = 0,
) -> ClientV1Envelope[LinkedFeatureSessionPageDTO]:
    started_at = time.perf_counter()
    effective_limit = max(1, min(limit, 50))
    effective_offset = max(0, offset)
    try:
        app_request = await _resolve_app_request(request_context, core_ports)
        resolved_feature_id = await _resolve_feature_alias_id(
            app_request.ports.storage,
            app_request.context,
            feature_id,
        )
        result = await _feature_modal_detail_service.get_sessions(
            app_request.context,
            app_request.ports,
            resolved_feature_id,
            limit=effective_limit,
            offset=effective_offset,
            thread_expansion=ThreadExpansionMode.INHERITED_THREADS,
        )
        if result.status == "not_found":
            raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found.")

        rows = result.data.get("rows") if isinstance(result.data.get("rows"), list) else []
        dto = LinkedFeatureSessionPageDTO(
            items=[_session_row_to_linked_dto(row) for row in rows if isinstance(row, dict)],
            total=int(result.data.get("total") or 0),
            offset=int(result.data.get("offset") or effective_offset),
            limit=int(result.data.get("limit") or effective_limit),
            has_more=bool(result.data.get("has_more")),
            enrichment=LinkedSessionEnrichmentDTO(
                includes=[],
                logs_read=False,
                command_count_included=False,
                task_refs_included=False,
                thread_children_included=False,
            ),
            precision="eventually_consistent",
        )
        envelope = ClientV1Envelope(
            data=dto,
            meta=build_client_v1_meta(instance_id=_instance_id()),
        )
        _emit_feature_surface_observation(
            "feature_linked_session_page",
            started_at=started_at,
            result_count=len(dto.items),
            payload=envelope.data,
            cache_status="unknown",
            feature_id=resolved_feature_id,
            limit=effective_limit,
            offset=effective_offset,
        )
        return envelope
    except Exception as exc:
        _emit_feature_surface_observation(
            "feature_linked_session_page",
            started_at=started_at,
            result_count=0,
            payload=None,
            cache_status="unknown",
            error_category=_classify_observability_error(exc),
            feature_id=feature_id,
            limit=effective_limit,
            offset=effective_offset,
        )
        raise
