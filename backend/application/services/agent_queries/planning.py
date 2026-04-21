"""Transport-neutral planning query service (PCP-201).

Exposes four read operations that provide planning intelligence derived from
Phase 1 helper functions in ``backend/services/feature_execution.py``.  All
derivation logic lives there; this module is a pure read/aggregate surface
following the ``ProjectStatusQueryService`` / ``FeatureForensicsQueryService``
pattern.

Transport consumers (REST via PCP-202, CLI via PCP-203, MCP via PCP-204) should
instantiate ``PlanningQueryService()`` and call its methods directly — no shared
singleton is required.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.document_linking import classify_doc_subtype, classify_doc_type
from backend.models import (
    Feature,
    FeatureDependencyState,
    FeaturePhase,
    LinkedDocument,
    PlanningEffectiveStatus,
    PlanningGraph,
)
from backend.observability import otel
from backend.services.feature_execution import (
    apply_planning_projection,
    build_planning_graph,
    feature_dependency_state,
    feature_from_row,
    load_execution_documents,
)

from ._filters import collect_source_refs, derive_data_freshness, resolve_project_scope
from .cache import clear_cache, memoized_query
from .feature_forensics import FeatureForensicsQueryService
from .models import (
    FeaturePlanningContextDTO,
    FeatureSummaryItem,
    OpenQuestionResolutionDTO,
    PhaseContextItem,
    PhaseOperationsDTO,
    PhaseTaskItem,
    PlanningArtifactRef,
    PlanningNodeCountsByType,
    PlanningOpenQuestionItem,
    PlanningSpikeItem,
    ProjectPlanningGraphDTO,
    ProjectPlanningSummaryDTO,
    TokenUsageByModel,
)

logger = logging.getLogger(__name__)
_feature_forensics_query_service = FeatureForensicsQueryService()
_PROMOTION_READY_STATUSES = {
    "ready",
    "ready-for-promotion",
    "promote-ready",
    "ready_to_promote",
    "approved",
    "mature",
}
_TERMINAL_FEATURE_STATUSES = {"done", "deferred", "completed"}
_TERMINAL_SUMMARY_STATUSES = {
    "done",
    "completed",
    "closed",
    "deferred",
    "superseded",
}
_ACTIVE_FIRST_STATUS_RANK = {
    "active": 0,
    "in-progress": 0,
    "in_progress": 0,
    "planned": 1,
    "blocked": 2,
    "review": 3,
    "draft": 4,
    "approved": 5,
}
_OQ_ID_PREFIX = re.compile(r"^(oq[-_\s]*\d+)\s*[:\-]\s*(.+)$", re.IGNORECASE)
_OQ_OVERLAY_LOCK = asyncio.Lock()
_OQ_OVERLAY: dict[str, dict[str, PlanningOpenQuestionItem]] = {}

# ── Internal helpers ─────────────────────────────────────────────────────────


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _safe_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        import json  # noqa: PLC0415
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "__dict__"):
        return {
            str(key): raw
            for key, raw in vars(value).items()
            if not str(key).startswith("_")
        }
    return {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_oq_id(value: str) -> str:
    return str(value or "").strip().lower()


def _coerce_token_usage_by_model(value: Any) -> TokenUsageByModel:
    payload = _safe_json_dict(value)
    if not payload:
        return TokenUsageByModel()
    return TokenUsageByModel.model_validate(payload)


def _artifact_ref_from_doc(doc: LinkedDocument) -> PlanningArtifactRef:
    updated_at = ""
    updated = getattr(getattr(doc, "dates", None), "updatedAt", None)
    if getattr(updated, "value", ""):
        updated_at = str(updated.value)
    return PlanningArtifactRef(
        artifact_id=str(getattr(doc, "id", "") or ""),
        title=str(getattr(doc, "title", "") or ""),
        file_path=str(getattr(doc, "filePath", "") or ""),
        canonical_path=str(getattr(doc, "canonicalPath", "") or ""),
        doc_type=str(getattr(doc, "docType", "") or ""),
        status=str(getattr(doc, "status", "") or ""),
        updated_at=updated_at,
        source_ref=str(getattr(doc, "id", "") or getattr(doc, "filePath", "") or ""),
    )


def _extract_question_text(raw: Any) -> tuple[str, str]:
    text = str(raw or "").strip()
    if not text:
        return "", ""
    match = _OQ_ID_PREFIX.match(text)
    if match:
        return match.group(1).upper().replace(" ", ""), match.group(2).strip()
    return "", text


def _derive_open_question_item(
    raw: Any,
    *,
    source_document_id: str,
    source_document_path: str,
    index: int,
) -> PlanningOpenQuestionItem | None:
    if isinstance(raw, str):
        inferred_id, question = _extract_question_text(raw)
        oq_id = inferred_id or f"{source_document_id}:oq-{index}"
        if not question:
            return None
        return PlanningOpenQuestionItem(
            oq_id=oq_id,
            question=question,
            source_document_id=source_document_id,
            source_document_path=source_document_path,
        )

    if not isinstance(raw, dict):
        return None

    question = str(raw.get("question") or raw.get("text") or raw.get("title") or "").strip()
    inferred_id, stripped_question = _extract_question_text(question)
    question = stripped_question or question
    if not question:
        return None
    answer_text = str(
        raw.get("answer_text")
        or raw.get("answerText")
        or raw.get("answer")
        or raw.get("resolution")
        or ""
    ).strip()
    oq_id = str(raw.get("oq_id") or raw.get("oqId") or raw.get("id") or inferred_id or f"{source_document_id}:oq-{index}").strip()
    resolved_raw = raw.get("resolved")
    resolved = bool(resolved_raw) or bool(answer_text)
    severity = str(raw.get("severity") or raw.get("priority") or "medium").strip().lower() or "medium"
    updated_at = str(raw.get("updated_at") or raw.get("updatedAt") or "").strip()
    pending_sync = bool(raw.get("pending_sync") or raw.get("pendingSync"))
    return PlanningOpenQuestionItem(
        oq_id=oq_id,
        question=question,
        severity=severity,
        answer_text=answer_text,
        resolved=resolved,
        pending_sync=pending_sync,
        source_document_id=source_document_id,
        source_document_path=source_document_path,
        updated_at=updated_at,
    )


def _merge_open_question_lists(
    base_items: list[PlanningOpenQuestionItem],
    overlay_items: list[PlanningOpenQuestionItem],
) -> list[PlanningOpenQuestionItem]:
    merged: dict[str, PlanningOpenQuestionItem] = {
        _normalize_oq_id(item.oq_id): item for item in base_items if item.oq_id
    }
    order = [_normalize_oq_id(item.oq_id) for item in base_items if item.oq_id]
    for item in overlay_items:
        key = _normalize_oq_id(item.oq_id)
        if not key:
            continue
        if key not in merged:
            order.append(key)
        merged[key] = item
    return [merged[key] for key in order if key in merged]


def _build_artifact_buckets(
    linked_docs: list[LinkedDocument],
) -> tuple[
    list[PlanningArtifactRef],
    list[PlanningArtifactRef],
    list[PlanningArtifactRef],
    list[PlanningArtifactRef],
    list[PlanningArtifactRef],
    list[PlanningSpikeItem],
]:
    specs: list[PlanningArtifactRef] = []
    prds: list[PlanningArtifactRef] = []
    plans: list[PlanningArtifactRef] = []
    ctxs: list[PlanningArtifactRef] = []
    reports: list[PlanningArtifactRef] = []
    spikes: list[PlanningSpikeItem] = []
    seen: set[tuple[str, str]] = set()

    for doc in linked_docs:
        artifact = _artifact_ref_from_doc(doc)
        dedupe_key = (artifact.artifact_id, artifact.file_path)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        doc_type = str(classify_doc_type(artifact.file_path, {"doc_type": artifact.doc_type}) or artifact.doc_type).strip().lower()
        doc_subtype = str(classify_doc_subtype(artifact.file_path, {"doc_type": artifact.doc_type}) or "").strip().lower()
        if doc_subtype == "spike":
            spikes.append(
                PlanningSpikeItem(
                    spike_id=artifact.artifact_id or artifact.file_path,
                    title=artifact.title,
                    status=artifact.status,
                    file_path=artifact.file_path,
                    source_ref=artifact.source_ref,
                )
            )
            continue
        if doc_type == "prd":
            prds.append(artifact)
        elif doc_type in {"implementation_plan", "phase_plan", "progress"}:
            plans.append(artifact)
        elif doc_type in {"report"}:
            reports.append(artifact)
        elif doc_type in {"context", "tracker"}:
            ctxs.append(artifact)
        elif doc_type in {"design_doc", "spec"}:
            specs.append(artifact)

    return specs, prds, plans, ctxs, reports, spikes


def _payload_open_questions(data: dict[str, Any]) -> list[PlanningOpenQuestionItem]:
    raw_items = data.get("openQuestions")
    if raw_items is None:
        raw_items = data.get("open_questions")
    if not isinstance(raw_items, list):
        return []
    items: list[PlanningOpenQuestionItem] = []
    for idx, raw in enumerate(raw_items, start=1):
        item = _derive_open_question_item(
            raw,
            source_document_id="feature-payload",
            source_document_path="feature-payload",
            index=idx,
        )
        if item is not None:
            items.append(item)
    return items


def _payload_spikes(data: dict[str, Any]) -> list[PlanningSpikeItem]:
    raw_items = data.get("spikes")
    if not isinstance(raw_items, list):
        return []
    spikes: list[PlanningSpikeItem] = []
    for idx, raw in enumerate(raw_items, start=1):
        if isinstance(raw, str):
            title = raw.strip()
            if not title:
                continue
            spikes.append(
                PlanningSpikeItem(
                    spike_id=f"feature-payload:spike-{idx}",
                    title=title,
                    source_ref="feature-payload",
                )
            )
            continue
        if not isinstance(raw, dict):
            continue
        spikes.append(
            PlanningSpikeItem(
                spike_id=str(raw.get("spike_id") or raw.get("spikeId") or raw.get("id") or f"feature-payload:spike-{idx}"),
                title=str(raw.get("title") or raw.get("name") or raw.get("question") or "").strip(),
                status=str(raw.get("status") or "").strip(),
                file_path=str(raw.get("file_path") or raw.get("filePath") or "").strip(),
                source_ref=str(raw.get("source_ref") or raw.get("sourceRef") or "feature-payload").strip(),
            )
        )
    return [item for item in spikes if item.title]


def _doc_row_open_questions(doc_rows: list[dict[str, Any]]) -> list[PlanningOpenQuestionItem]:
    items: list[PlanningOpenQuestionItem] = []
    for row in doc_rows:
        frontmatter = _safe_json_dict(row.get("frontmatter_json") or row.get("frontmatter"))
        raw_questions = frontmatter.get("open_questions")
        if raw_questions is None:
            raw_questions = frontmatter.get("openQuestions")
        if not isinstance(raw_questions, list):
            continue
        doc_id = str(row.get("id") or row.get("document_id") or "")
        doc_path = str(row.get("file_path") or row.get("filePath") or "")
        for idx, raw in enumerate(raw_questions, start=1):
            item = _derive_open_question_item(
                raw,
                source_document_id=doc_id or "document",
                source_document_path=doc_path,
                index=idx,
            )
            if item is not None:
                items.append(item)
    return items


async def _open_question_overlays_for_feature(feature_id: str) -> list[PlanningOpenQuestionItem]:
    feature_key = _feature_key(feature_id)
    async with _OQ_OVERLAY_LOCK:
        overlays = _OQ_OVERLAY.get(feature_key, {})
        return [item.model_copy(deep=True) for item in overlays.values()]


async def _set_open_question_overlay(
    feature_id: str,
    oq_item: PlanningOpenQuestionItem,
) -> None:
    feature_key = _feature_key(feature_id)
    async with _OQ_OVERLAY_LOCK:
        overlays = _OQ_OVERLAY.setdefault(feature_key, {})
        overlays[_normalize_oq_id(oq_item.oq_id)] = oq_item.model_copy(deep=True)


def _is_feature_stale(feature: Feature) -> bool:
    return (
        _mismatch_state(feature.planningStatus) in {"stale", "reversed", "mismatched"}
        and str(feature.status or "").strip().lower() in _TERMINAL_FEATURE_STATUSES
    )


def _is_ready_to_promote(graph: PlanningGraph) -> bool:
    for node in graph.nodes:
        node_status = str(getattr(node, "effectiveStatus", "") or "").strip().lower()
        if node_status in _PROMOTION_READY_STATUSES:
            return True
    return False


def _feature_key(value: str) -> str:
    """Normalise a feature ID/slug for dict lookup — mirrors feature_execution."""
    from backend.document_linking import canonical_slug  # noqa: PLC0415
    token = canonical_slug(str(value or "").strip())
    return token or str(value or "").strip().lower()


def _effective_status(ps: PlanningEffectiveStatus | None) -> str:
    if ps is None:
        return ""
    return str(ps.effectiveStatus or "")


def _raw_status(ps: PlanningEffectiveStatus | None) -> str:
    if ps is None:
        return ""
    return str(ps.rawStatus or "")


def _mismatch_state(ps: PlanningEffectiveStatus | None) -> str:
    if ps is None:
        return "unknown"
    return str(ps.mismatchState.state or "unknown")


def _is_mismatch(ps: PlanningEffectiveStatus | None) -> bool:
    if ps is None:
        return False
    return bool(ps.mismatchState.isMismatch)


def _summary_status_token(item: FeatureSummaryItem) -> str:
    return str(item.effective_status or item.raw_status or "").strip().lower()


def _is_terminal_summary_item(item: FeatureSummaryItem) -> bool:
    return _summary_status_token(item).replace("_", "-") in _TERMINAL_SUMMARY_STATUSES


def _summary_sort_key(item: FeatureSummaryItem) -> tuple[int, str, str]:
    token = _summary_status_token(item)
    normalized = token.replace("_", "-")
    rank = _ACTIVE_FIRST_STATUS_RANK.get(token)
    if rank is None:
        rank = _ACTIVE_FIRST_STATUS_RANK.get(normalized)
    if rank is None:
        rank = 50 if normalized in _TERMINAL_SUMMARY_STATUSES else 20
    return rank, str(item.feature_name or "").lower(), str(item.feature_id or "").lower()


def _shape_feature_summaries(
    items: list[FeatureSummaryItem],
    *,
    active_first: bool,
    include_terminal: bool,
    limit: int | None,
) -> list[FeatureSummaryItem]:
    shaped = list(items)
    if not include_terminal:
        shaped = [item for item in shaped if not _is_terminal_summary_item(item)]
    if active_first:
        shaped = sorted(shaped, key=_summary_sort_key)
    if limit is not None:
        shaped = shaped[: max(1, int(limit))]
    return shaped


def _batch_dict(batch: Any) -> dict[str, Any]:
    """Serialise a PlanningPhaseBatch to a plain dict."""
    if hasattr(batch, "model_dump"):
        return batch.model_dump()
    return dict(batch) if isinstance(batch, dict) else {}


def _graph_dict(graph: PlanningGraph) -> dict[str, Any]:
    return {
        "nodes": [n.model_dump() for n in graph.nodes],
        "edges": [e.model_dump() for e in graph.edges],
        "phaseBatches": [_batch_dict(b) for b in graph.phaseBatches],
    }


def _load_doc_rows_for_feature(
    all_doc_rows: list[dict[str, Any]],
    feature_id: str,
) -> list[dict[str, Any]]:
    """Filter all-project doc rows down to those belonging to *feature_id*."""
    fk = _feature_key(feature_id)
    return [
        row
        for row in all_doc_rows
        if _feature_key(
            str(
                row.get("feature_slug_canonical")
                or row.get("feature_slug_hint")
                or ""
            )
        ) == fk
    ]


_LIGHTWEIGHT_DOC_TYPE_TO_NODE_TYPE = {
    "design_doc": "design_spec",
    "spec": "design_spec",
    "design_spec": "design_spec",
    "implementation_plan": "implementation_plan",
    "phase_plan": "implementation_plan",
    "prd": "prd",
    "progress": "progress",
    "report": "report",
}


def _lightweight_node_type_for_doc(
    *,
    doc_type: str,
    file_path: str,
    primary_role: str = "",
) -> str | None:
    """Classify planning artifact rows without building a full feature graph."""
    role_token = str(primary_role or "").strip().lower()
    path_token = str(file_path or "").strip().lower()
    raw_doc_type = str(doc_type or "").strip().lower()
    if raw_doc_type == "tracker" or "tracker" in role_token or "tracker" in path_token:
        return "tracker"
    if raw_doc_type in {"context", "ctx"} or "context" in role_token or "context" in path_token:
        return "context"

    classified = str(
        classify_doc_type(file_path, {"doc_type": doc_type})
        or raw_doc_type
    ).strip().lower()
    return _LIGHTWEIGHT_DOC_TYPE_TO_NODE_TYPE.get(classified)


def _doc_identity(*, doc_id: str, file_path: str, title: str = "") -> str:
    return str(file_path or doc_id or title or "").strip().lower()


def _linked_document_node_entries(
    linked_docs: list[Any],
) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for raw_doc in linked_docs or []:
        doc = (
            LinkedDocument.model_validate(raw_doc)
            if isinstance(raw_doc, dict)
            else raw_doc
        )
        if not isinstance(doc, LinkedDocument):
            continue
        node_type = _lightweight_node_type_for_doc(
            doc_type=str(getattr(doc, "docType", "") or ""),
            file_path=str(getattr(doc, "filePath", "") or ""),
            primary_role=str(getattr(doc, "primaryDocRole", "") or ""),
        )
        if node_type is None:
            continue
        identity = _doc_identity(
            doc_id=str(getattr(doc, "id", "") or ""),
            file_path=str(getattr(doc, "filePath", "") or ""),
            title=str(getattr(doc, "title", "") or ""),
        )
        if identity:
            entries.append((identity, node_type))
    return entries


def _doc_row_node_entries(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for row in rows:
        node_type = _lightweight_node_type_for_doc(
            doc_type=str(row.get("doc_type") or ""),
            file_path=str(row.get("file_path") or row.get("filePath") or ""),
            primary_role=str(
                row.get("primary_doc_role")
                or row.get("primaryDocRole")
                or ""
            ),
        )
        if node_type is None:
            continue
        identity = _doc_identity(
            doc_id=str(row.get("id") or row.get("document_id") or ""),
            file_path=str(row.get("file_path") or row.get("filePath") or ""),
            title=str(row.get("title") or ""),
        )
        if identity:
            entries.append((identity, node_type))
    return entries


def _count_lightweight_planning_nodes(
    feature: Feature,
    current_doc_rows: list[dict[str, Any]],
) -> tuple[Counter[str], int]:
    """Return planning artifact counts for summary payloads only.

    Full graph node/edge construction remains available through graph/detail
    endpoints; summary only needs artifact facets and a small per-feature count.
    """
    nodes_by_identity: dict[str, str] = {}
    for identity, node_type in _linked_document_node_entries(feature.linkedDocs):
        nodes_by_identity.setdefault(identity, node_type)
    for identity, node_type in _doc_row_node_entries(current_doc_rows):
        nodes_by_identity.setdefault(identity, node_type)
    return Counter(nodes_by_identity.values()), len(nodes_by_identity)


async def _load_all_features(
    ports: CorePorts, project_id: str
) -> tuple[list[dict[str, Any]], list[Feature], dict[str, Feature]]:
    """Return raw rows, Feature objects, and a key-indexed lookup dict."""
    rows: list[dict[str, Any]] = await ports.storage.features().list_all(project_id)
    features = [feature_from_row(row) for row in rows]
    index: dict[str, Feature] = {_feature_key(f.id): f for f in features}
    return rows, features, index


async def _load_all_doc_rows(
    ports: CorePorts, project_id: str
) -> list[dict[str, Any]]:
    try:
        return await ports.storage.documents().list_all(project_id)
    except AttributeError:
        # Fallback: list_paginated when list_all is unavailable.
        return await ports.storage.documents().list_paginated(
            project_id, 0, 500, {"include_progress": True}
        )


def _project_with_planning(
    feature: Feature,
    doc_rows: list[dict[str, Any]],
    feature_index: dict[str, Feature],
) -> Feature:
    """Apply planning projection in-place on a cloned feature object."""
    dep_state = feature_dependency_state(feature, doc_rows, feature_index)
    current_doc_rows = _load_doc_rows_for_feature(doc_rows, feature.id)
    return apply_planning_projection(feature, current_doc_rows, dep_state)


# ── Param extractors (cache key helpers) ────────────────────────────────────


def _summary_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    *,
    project_id_override: str | None = None,
    active_first: bool = True,
    include_terminal: bool = False,
    limit: int | None = 100,
    **_: Any,
) -> dict[str, Any]:
    return {
        "project_id_override": project_id_override,
        "active_first": active_first,
        "include_terminal": include_terminal,
        "limit": limit,
    }


def _graph_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    *,
    project_id_override: str | None = None,
    feature_id: str | None = None,
    depth: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    return {
        "project_id_override": project_id_override,
        "feature_id": feature_id,
        "depth": depth,
    }


def _feature_context_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    *,
    feature_id: str,
    project_id_override: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    return {"feature_id": feature_id, "project_id_override": project_id_override}


def _phase_ops_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    *,
    feature_id: str,
    phase_number: int,
    project_id_override: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    return {
        "feature_id": feature_id,
        "phase_number": phase_number,
        "project_id_override": project_id_override,
    }


# ── Service class ────────────────────────────────────────────────────────────


class PlanningQueryService:
    """Transport-neutral planning intelligence query surface (PCP-201).

    All four methods follow the same structural contract as the other agent
    query services: they accept ``context`` + ``ports``, return a Pydantic DTO
    that extends ``AgentQueryEnvelope``, and are wrapped with ``@memoized_query``
    for TTL-bounded caching.

    Derivation logic (graph building, status projection, dependency analysis)
    is **not** reimplemented here; it delegates exclusively to the public
    wrappers added to ``backend/services/feature_execution.py`` (PCP-201).
    """

    # ── Query 1: Project planning summary ────────────────────────────────────

    @memoized_query("planning_project_summary", param_extractor=_summary_params)
    async def get_project_planning_summary(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        project_id_override: str | None = None,
        active_first: bool = True,
        include_terminal: bool = False,
        limit: int | None = 100,
    ) -> ProjectPlanningSummaryDTO:
        """Return project-level planning health counts and feature summaries.

        Loads all features, applies planning projection, and aggregates:
        active vs stale counts, blocked/mismatch counts, reversal lists, and
        lightweight artifact facets. Full graph payloads are deferred to the
        graph/detail endpoints.
        """
        scope = resolve_project_scope(context, ports, project_id_override)
        if scope is None:
            return ProjectPlanningSummaryDTO(
                status="error",
                project_id=str(project_id_override or ""),
                source_refs=[],
            )

        project = scope.project
        partial = False

        feature_rows: list[dict[str, Any]] = []
        doc_rows: list[dict[str, Any]] = []
        try:
            feature_rows, features, feature_index = await _load_all_features(
                ports, project.id
            )
        except Exception:
            partial = True
            features, feature_index = [], {}

        try:
            doc_rows = await _load_all_doc_rows(ports, project.id)
        except Exception:
            partial = True

        # Apply planning projection to every feature.
        projected: list[Feature] = []
        for feature in features:
            try:
                projected.append(
                    _project_with_planning(feature, doc_rows, feature_index)
                )
            except Exception:
                projected.append(feature)
                partial = True

        # Aggregate counts.
        active_statuses = {"in-progress", "review"}
        stale_ids: list[str] = []
        reversal_ids: list[str] = []
        blocked_ids: list[str] = []
        mismatch_count = 0
        node_type_counter: Counter[str] = Counter()
        feature_summaries: list[FeatureSummaryItem] = []

        for feature in projected:
            ps = feature.planningStatus
            eff = _effective_status(ps)
            raw = _raw_status(ps) or str(feature.status or "backlog")
            ms = _mismatch_state(ps)
            is_mis = _is_mismatch(ps)

            if is_mis:
                mismatch_count += 1
            if ms == "reversed":
                reversal_ids.append(feature.id)
            if ms == "blocked" or eff == "blocked":
                blocked_ids.append(feature.id)

            # Stale = terminal raw status not corroborated by evidence.
            if ms in {"reversed", "mismatched"} and str(feature.status or "").lower() in {
                "done", "deferred", "completed"
            }:
                stale_ids.append(feature.id)

            current_doc_rows = _load_doc_rows_for_feature(doc_rows, feature.id)
            feature_node_counts, node_count = _count_lightweight_planning_nodes(
                feature,
                current_doc_rows,
            )
            node_type_counter.update(feature_node_counts)

            blocked_phases = [
                p
                for p in feature.phases
                if p.planningStatus
                and str(p.planningStatus.effectiveStatus or "").lower() == "blocked"
            ]
            feature_summaries.append(
                FeatureSummaryItem(
                    feature_id=feature.id,
                    feature_name=feature.name,
                    raw_status=raw,
                    effective_status=eff or raw,
                    is_mismatch=is_mis,
                    mismatch_state=ms,
                    has_blocked_phases=bool(blocked_phases),
                    phase_count=len(feature.phases),
                    blocked_phase_count=len(blocked_phases),
                    node_count=node_count,
                )
            )

        # ── Synthesise FeatureSummaryItems from orphan design_spec / prd docs ──
        # These are docs whose canonical slug doesn't match any real feature row.
        # They represent planned work that hasn't spawned an implementation_plan yet.
        _DESIGN_SPEC_DOC_TYPES = {"design_spec", "design_doc", "spec"}
        _PRD_DOC_TYPES = {"prd"}

        def _is_design_spec_row(row: dict[str, Any]) -> bool:
            dt = str(row.get("doc_type") or "").strip().lower()
            ds = str(row.get("doc_subtype") or "").strip().lower()
            if dt in ("design_spec", "design_doc"):
                return True
            if dt == "spec" and ds in ("design_spec", "design_doc", ""):
                return True
            return False

        def _is_prd_row(row: dict[str, Any]) -> bool:
            return str(row.get("doc_type") or "").strip().lower() in _PRD_DOC_TYPES

        # Keys already covered by real feature summaries.
        emitted_keys: set[str] = {
            _feature_key(item.feature_id) for item in feature_summaries
        }

        # Collect orphan candidates: {slug_key -> (row, kind)} preferring design_spec.
        _KIND_PRIORITY = {"design_spec": 0, "prd": 1}
        orphan_candidates: dict[str, tuple[dict[str, Any], str]] = {}
        for row in doc_rows:
            if _is_design_spec_row(row):
                kind = "design_spec"
            elif _is_prd_row(row):
                kind = "prd"
            else:
                continue

            raw_slug = str(
                row.get("feature_slug_canonical")
                or row.get("feature_slug_hint")
                or ""
            ).strip()
            if not raw_slug:
                # Derive a slug from the file path stem as last resort.
                fp = str(row.get("file_path") or "")
                raw_slug = fp.rsplit("/", 1)[-1].rsplit(".", 1)[0] if fp else ""
            if not raw_slug:
                continue

            slug_key = _feature_key(raw_slug)
            if slug_key in emitted_keys:
                continue

            existing = orphan_candidates.get(slug_key)
            if existing is None or _KIND_PRIORITY[kind] < _KIND_PRIORITY[existing[1]]:
                orphan_candidates[slug_key] = (row, kind)

        for slug_key, (row, kind) in orphan_candidates.items():
            # Pull status from frontmatter if available.
            fp_raw = row.get("frontmatter_json") or row.get("frontmatter") or {}
            if isinstance(fp_raw, str):
                import json as _json  # noqa: PLC0415
                try:
                    fp_raw = _json.loads(fp_raw)
                except Exception:
                    fp_raw = {}
            if not isinstance(fp_raw, dict):
                fp_raw = {}
            doc_status = str(
                fp_raw.get("status") or row.get("status") or "draft"
            ).strip() or "draft"

            slug_id = str(
                row.get("feature_slug_canonical")
                or row.get("feature_slug_hint")
                or slug_key
            )
            feature_summaries.append(
                FeatureSummaryItem(
                    feature_id=slug_id,
                    feature_name=str(row.get("title") or slug_id),
                    raw_status=doc_status,
                    effective_status=doc_status,
                    is_mismatch=False,
                    mismatch_state="unknown",
                    has_blocked_phases=False,
                    phase_count=0,
                    blocked_phase_count=0,
                    node_count=1,
                    source_artifact_kind=kind,  # type: ignore[arg-type]
                )
            )
            emitted_keys.add(slug_key)

        # ── Aggregate counts (after synthesis) ───────────────────────────────
        planned_statuses = {"draft", "approved"}
        planned_count = sum(
            1
            for item in feature_summaries
            if item.effective_status.lower() in planned_statuses
        )

        active_count = sum(
            1
            for f in projected
            if (_effective_status(f.planningStatus) or str(f.status or "")).lower()
            in active_statuses
        )

        node_counts = PlanningNodeCountsByType(
            prd=node_type_counter.get("prd", 0),
            design_spec=node_type_counter.get("design_spec", 0),
            implementation_plan=node_type_counter.get("implementation_plan", 0),
            progress=node_type_counter.get("progress", 0),
            context=node_type_counter.get("context", 0),
            tracker=node_type_counter.get("tracker", 0),
            report=node_type_counter.get("report", 0),
        )

        data_freshness = derive_data_freshness(
            *[row.get("updated_at") or row.get("updatedAt") for row in feature_rows]
        )

        return ProjectPlanningSummaryDTO(
            status="partial" if partial else "ok",
            project_id=project.id,
            project_name=project.name,
            total_feature_count=len(feature_summaries),
            planned_feature_count=planned_count,
            active_feature_count=active_count,
            stale_feature_count=len(stale_ids),
            blocked_feature_count=len(blocked_ids),
            mismatch_count=mismatch_count,
            reversal_count=len(reversal_ids),
            stale_feature_ids=sorted(set(stale_ids)),
            reversal_feature_ids=sorted(set(reversal_ids)),
            blocked_feature_ids=sorted(set(blocked_ids)),
            node_counts_by_type=node_counts,
            feature_summaries=_shape_feature_summaries(
                feature_summaries,
                active_first=active_first,
                include_terminal=include_terminal,
                limit=limit,
            ),
            data_freshness=data_freshness,
            source_refs=collect_source_refs(project.id, [f.id for f in projected]),
        )

    # ── Query 2: Project planning graph ──────────────────────────────────────

    @memoized_query("planning_project_graph", param_extractor=_graph_params)
    async def get_project_planning_graph(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        project_id_override: str | None = None,
        feature_id: str | None = None,
        depth: int | None = None,
    ) -> ProjectPlanningGraphDTO:
        """Return aggregated planning graph nodes and edges.

        When *feature_id* is provided the graph is scoped to that feature's
        subgraph (plus family-level relationships).  When omitted, graphs from
        all project features are merged into one flat node/edge list.

        The *depth* parameter is reserved for future depth-limited traversal;
        it is stored in the DTO but does not currently alter the traversal.
        """
        scope = resolve_project_scope(context, ports, project_id_override)
        if scope is None:
            return ProjectPlanningGraphDTO(
                status="error",
                project_id=str(project_id_override or ""),
                feature_id=feature_id,
                depth=depth,
                source_refs=[],
            )

        project = scope.project
        partial = False

        try:
            feature_rows, features, feature_index = await _load_all_features(
                ports, project.id
            )
        except Exception:
            partial = True
            feature_rows, features, feature_index = [], [], {}

        try:
            doc_rows = await _load_all_doc_rows(ports, project.id)
        except Exception:
            doc_rows = []
            partial = True

        # Scope to a single feature when requested.
        target_features = features
        if feature_id:
            fk = _feature_key(feature_id)
            target_features = [f for f in features if _feature_key(f.id) == fk]
            if not target_features:
                return ProjectPlanningGraphDTO(
                    status="error",
                    project_id=project.id,
                    feature_id=feature_id,
                    depth=depth,
                    source_refs=[feature_id],
                )

        all_nodes: list[dict[str, Any]] = []
        all_edges: list[dict[str, Any]] = []
        all_batches: list[dict[str, Any]] = []
        seen_node_ids: set[str] = set()
        seen_edge_tuples: set[tuple[str, str, str]] = set()
        source_feature_ids: list[str] = []

        for feature in target_features:
            try:
                dep_state = feature_dependency_state(feature, doc_rows, feature_index)
                current_doc_rows = _load_doc_rows_for_feature(doc_rows, feature.id)
                apply_planning_projection(feature, current_doc_rows, dep_state)

                linked_docs = [
                    LinkedDocument.model_validate(d)
                    for d in (feature.linkedDocs or [])
                    if isinstance(d, dict)
                ] + [
                    LinkedDocument(
                        id=str(row.get("id") or ""),
                        title=str(row.get("title") or ""),
                        filePath=str(row.get("file_path") or ""),
                        docType=str(row.get("doc_type") or ""),
                        slug=str(row.get("slug") or ""),
                        canonicalSlug=str(row.get("canonical_slug") or ""),
                    )
                    for row in current_doc_rows
                ]
                graph = build_planning_graph(feature, linked_docs, None)

                for node in graph.nodes:
                    if node.id not in seen_node_ids:
                        seen_node_ids.add(node.id)
                        all_nodes.append(node.model_dump())
                for edge in graph.edges:
                    key = (edge.sourceId, edge.targetId, edge.relationType)
                    if key not in seen_edge_tuples:
                        seen_edge_tuples.add(key)
                        all_edges.append(edge.model_dump())
                for batch in graph.phaseBatches:
                    all_batches.append(_batch_dict(batch))

                source_feature_ids.append(feature.id)
            except Exception:
                partial = True

        data_freshness = derive_data_freshness(
            *[row.get("updated_at") or row.get("updatedAt") for row in feature_rows]
        )

        return ProjectPlanningGraphDTO(
            status="partial" if partial else "ok",
            project_id=project.id,
            feature_id=feature_id,
            depth=depth,
            nodes=all_nodes,
            edges=all_edges,
            phase_batches=all_batches,
            node_count=len(all_nodes),
            edge_count=len(all_edges),
            data_freshness=data_freshness,
            source_refs=collect_source_refs(project.id, source_feature_ids),
        )

    # ── Query 3: Feature planning context ────────────────────────────────────

    @memoized_query("planning_feature_context", param_extractor=_feature_context_params)
    async def get_feature_planning_context(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        feature_id: str,
        project_id_override: str | None = None,
    ) -> FeaturePlanningContextDTO:
        """Return one feature's planning subgraph, status provenance, and phase details.

        Preserves the distinction between raw and effective status throughout:
        ``raw_status`` is always the value stored in the feature record; all
        derived/inferred values flow through ``effective_status`` and
        ``planning_status`` (the full ``PlanningEffectiveStatus`` dict).
        """
        scope = resolve_project_scope(context, ports, project_id_override)
        if scope is None:
            return FeaturePlanningContextDTO(
                status="error",
                feature_id=feature_id,
                source_refs=[feature_id],
            )

        project = scope.project
        partial = False

        feature_row = await ports.storage.features().get_by_id(feature_id)
        if feature_row is None:
            return FeaturePlanningContextDTO(
                status="error",
                feature_id=feature_id,
                source_refs=[feature_id],
            )

        try:
            _rows, _features, feature_index = await _load_all_features(
                ports, project.id
            )
        except Exception:
            feature_index = {}
            partial = True

        doc_rows: list[dict[str, Any]] = []
        try:
            doc_rows = await _load_all_doc_rows(ports, project.id)
        except Exception:
            partial = True

        feature = feature_from_row(feature_row)
        feature_payload = _safe_json_dict(feature_row.get("data_json"))
        current_doc_rows = _load_doc_rows_for_feature(doc_rows, feature_id)
        dep_state = feature_dependency_state(feature, doc_rows, feature_index)
        apply_planning_projection(feature, current_doc_rows, dep_state)

        linked_docs: list[LinkedDocument] = []
        try:
            linked_docs = await load_execution_documents(
                ports.storage.db, project.id, feature_id
            )
        except Exception:
            # Fallback: rehydrate from the raw doc rows we already have.
            linked_docs = [
                LinkedDocument(
                    id=str(row.get("id") or ""),
                    title=str(row.get("title") or ""),
                    filePath=str(row.get("file_path") or ""),
                    docType=str(row.get("doc_type") or ""),
                )
                for row in current_doc_rows
            ]
            partial = True

        existing_doc_keys = {
            (str(getattr(doc, "id", "") or ""), str(getattr(doc, "filePath", "") or ""))
            for doc in linked_docs
        }
        for row in current_doc_rows:
            candidate_key = (
                str(row.get("id") or ""),
                str(row.get("file_path") or row.get("filePath") or ""),
            )
            if candidate_key in existing_doc_keys:
                continue
            linked_docs.append(
                LinkedDocument(
                    id=str(row.get("id") or ""),
                    title=str(row.get("title") or ""),
                    filePath=str(row.get("file_path") or row.get("filePath") or ""),
                    docType=str(row.get("doc_type") or row.get("docType") or ""),
                    slug=str(row.get("slug") or ""),
                    canonicalSlug=str(row.get("canonical_slug") or row.get("canonicalSlug") or ""),
                )
            )
            existing_doc_keys.add(candidate_key)

        graph = build_planning_graph(feature, linked_docs, None)
        specs, prds, plans, ctxs, reports, derived_spikes = _build_artifact_buckets(linked_docs)
        payload_spikes = _payload_spikes(feature_payload)
        spikes = payload_spikes or derived_spikes
        open_questions = _merge_open_question_lists(
            _payload_open_questions(feature_payload) + _doc_row_open_questions(current_doc_rows),
            await _open_question_overlays_for_feature(feature_id),
        )

        try:
            forensics = await _feature_forensics_query_service.get_forensics(
                context,
                ports,
                feature_id,
            )
            token_usage = _coerce_token_usage_by_model(forensics.token_usage_by_model)
            total_tokens = _safe_int(forensics.total_tokens)
            if forensics.status == "partial":
                partial = True
        except Exception:
            token_usage = TokenUsageByModel()
            total_tokens = 0
            partial = True

        # Build per-phase context items.
        phase_items: list[PhaseContextItem] = []
        all_blocked_batch_ids: list[str] = []
        for phase in feature.phases:
            ps = phase.planningStatus
            blocked_batches = [
                b for b in (phase.phaseBatches or [])
                if str(getattr(b, "readinessState", "") or "").lower() == "blocked"
            ]
            blocked_batch_ids = [
                str(getattr(b, "batchId", "") or "") for b in blocked_batches
            ]
            all_blocked_batch_ids.extend(blocked_batch_ids)

            phase_items.append(
                PhaseContextItem(
                    phase_id=str(phase.id or ""),
                    phase_token=str(phase.phase or ""),
                    phase_title=str(phase.title or ""),
                    raw_status=_raw_status(ps) or str(phase.status or "backlog"),
                    effective_status=_effective_status(ps) or str(phase.status or "backlog"),
                    is_mismatch=_is_mismatch(ps),
                    mismatch_state=_mismatch_state(ps),
                    planning_status=ps.model_dump() if ps else {},
                    batches=[_batch_dict(b) for b in (phase.phaseBatches or [])],
                    blocked_batch_ids=blocked_batch_ids,
                    total_tasks=_safe_int(phase.totalTasks),
                    completed_tasks=_safe_int(phase.completedTasks),
                    deferred_tasks=_safe_int(phase.deferredTasks),
                )
            )

        fp = feature.planningStatus
        artifact_refs = [node.path for node in graph.nodes if node.path]

        data_freshness = derive_data_freshness(
            feature_row.get("updated_at") or feature_row.get("updatedAt"),
            *[row.get("updated_at") or row.get("updatedAt") for row in current_doc_rows],
        )

        return FeaturePlanningContextDTO(
            status="partial" if partial else "ok",
            feature_id=feature_id,
            feature_name=feature.name,
            raw_status=_raw_status(fp) or str(feature.status or "backlog"),
            effective_status=_effective_status(fp) or str(feature.status or "backlog"),
            mismatch_state=_mismatch_state(fp),
            planning_status=fp.model_dump() if fp else {},
            graph=_graph_dict(graph),
            phases=phase_items,
            blocked_batch_ids=sorted(set(all_blocked_batch_ids)),
            linked_artifact_refs=sorted(set(artifact_refs)),
            specs=specs,
            prds=prds,
            plans=plans,
            ctxs=ctxs,
            reports=reports,
            spikes=spikes,
            open_questions=open_questions,
            ready_to_promote=_is_ready_to_promote(graph),
            is_stale=_is_feature_stale(feature),
            total_tokens=total_tokens,
            token_usage_by_model=token_usage,
            data_freshness=data_freshness,
            source_refs=collect_source_refs(
                feature_id,
                [node.id for node in graph.nodes],
            ),
        )

    async def resolve_open_question(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        feature_id: str,
        oq_id: str,
        answer_text: str,
        project_id_override: str | None = None,
    ) -> OpenQuestionResolutionDTO:
        normalized_answer = str(answer_text or "").strip()
        normalized_oq_id = _normalize_oq_id(oq_id)
        with otel.start_span(
            "planning.oq.resolve",
            {
                "feature_id": feature_id,
                "oq_id": oq_id,
                "answer_length": len(normalized_answer),
                "success": False,
            },
        ) as span:
            if not normalized_answer:
                raise ValueError("answer must not be empty")

            scope = resolve_project_scope(context, ports, project_id_override)
            if scope is None:
                raise LookupError(f"Feature '{feature_id}' not found.")

            feature_row = await ports.storage.features().get_by_id(feature_id)
            if feature_row is None:
                raise LookupError(f"Feature '{feature_id}' not found.")

            try:
                doc_rows = await _load_all_doc_rows(ports, scope.project.id)
            except Exception:
                doc_rows = []

            current_doc_rows = _load_doc_rows_for_feature(doc_rows, feature_id)
            feature_payload = _safe_json_dict(feature_row.get("data_json"))
            open_questions = _merge_open_question_lists(
                _payload_open_questions(feature_payload) + _doc_row_open_questions(current_doc_rows),
                await _open_question_overlays_for_feature(feature_id),
            )

            target = next(
                (
                    item
                    for item in open_questions
                    if _normalize_oq_id(item.oq_id) == normalized_oq_id
                ),
                None,
            )
            if target is None:
                raise LookupError(
                    f"Open question '{oq_id}' not found for feature '{feature_id}'."
                )

            resolved_item = target.model_copy(
                update={
                    "answer_text": normalized_answer,
                    "resolved": True,
                    "pending_sync": True,
                    "updated_at": _utc_now_iso(),
                }
            )
            await _set_open_question_overlay(feature_id, resolved_item)
            clear_cache()
            if span is not None:
                span.set_attribute("success", True)
            return OpenQuestionResolutionDTO(feature_id=feature_id, oq=resolved_item)

    # ── Query 4: Phase operations ─────────────────────────────────────────────

    @memoized_query("planning_phase_ops", param_extractor=_phase_ops_params)
    async def get_phase_operations(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        feature_id: str,
        phase_number: int,
        project_id_override: str | None = None,
    ) -> PhaseOperationsDTO:
        """Return operational detail for a single phase.

        Resolves the target phase by matching ``phase_number`` against each
        phase's ``phase`` token (e.g. ``"1"``, ``"2"``).  Returns batch
        readiness, per-task assignee / blocker data, dependency resolution
        summary, and any progress-document evidence attached to the phase.
        """
        scope = resolve_project_scope(context, ports, project_id_override)
        if scope is None:
            return PhaseOperationsDTO(
                status="error",
                feature_id=feature_id,
                phase_number=phase_number,
                source_refs=[feature_id],
            )

        project = scope.project
        partial = False

        feature_row = await ports.storage.features().get_by_id(feature_id)
        if feature_row is None:
            return PhaseOperationsDTO(
                status="error",
                feature_id=feature_id,
                phase_number=phase_number,
                source_refs=[feature_id],
            )

        try:
            _rows, _features, feature_index = await _load_all_features(
                ports, project.id
            )
        except Exception:
            feature_index = {}
            partial = True

        doc_rows: list[dict[str, Any]] = []
        try:
            doc_rows = await _load_all_doc_rows(ports, project.id)
        except Exception:
            partial = True

        feature = feature_from_row(feature_row)
        current_doc_rows = _load_doc_rows_for_feature(doc_rows, feature_id)
        dep_state = feature_dependency_state(feature, doc_rows, feature_index)
        apply_planning_projection(feature, current_doc_rows, dep_state)

        # Locate the target phase by phase token.
        target_phase: FeaturePhase | None = None
        for phase in feature.phases:
            token = str(phase.phase or "").strip()
            try:
                if int(token) == phase_number:
                    target_phase = phase
                    break
            except (ValueError, TypeError):
                pass

        if target_phase is None:
            return PhaseOperationsDTO(
                status="error",
                feature_id=feature_id,
                phase_number=phase_number,
                source_refs=[feature_id],
            )

        ps = target_phase.planningStatus
        eff = _effective_status(ps) or str(target_phase.status or "backlog")
        is_ready = eff in {"in-progress", "review", "done", "deferred", "completed"}

        # Per-task detail.
        task_items: list[PhaseTaskItem] = []
        for task in (target_phase.tasks or []):
            assignees: list[str] = []
            for field_name in ("assignee", "assignees", "owner", "owners"):
                val = getattr(task, field_name, None)
                if isinstance(val, str) and val.strip():
                    assignees.append(val.strip())
                elif isinstance(val, list):
                    assignees.extend(str(v).strip() for v in val if str(v).strip())

            blockers: list[str] = []
            for field_name in ("blockedBy", "blocked_by", "blockers"):
                val = getattr(task, field_name, None)
                if isinstance(val, str) and val.strip():
                    blockers.append(val.strip())
                elif isinstance(val, list):
                    blockers.extend(str(v).strip() for v in val if str(v).strip())

            # Determine which batch this task belongs to by scanning phase batches.
            batch_id = ""
            task_id = str(getattr(task, "id", "") or "")
            for batch in (target_phase.phaseBatches or []):
                batch_task_ids = list(getattr(batch, "taskIds", []) or [])
                if task_id and task_id in batch_task_ids:
                    batch_id = str(getattr(batch, "batchId", "") or "")
                    break

            task_items.append(
                PhaseTaskItem(
                    task_id=task_id,
                    title=str(getattr(task, "title", "") or ""),
                    status=str(getattr(task, "status", "") or ""),
                    assignees=sorted(set(assignees)),
                    blockers=sorted(set(blockers)),
                    batch_id=batch_id,
                )
            )

        # Batch readiness.
        batches = [_batch_dict(b) for b in (target_phase.phaseBatches or [])]
        blocked_batch_ids = [
            str(getattr(b, "batchId", "") or "")
            for b in (target_phase.phaseBatches or [])
            if str(getattr(b, "readinessState", "") or "").lower() == "blocked"
        ]

        # Readiness state from the first batch if available, otherwise derive from phase.
        readiness_state = "unknown"
        if target_phase.phaseBatches:
            first_batch = target_phase.phaseBatches[0]
            readiness_state = str(
                getattr(first_batch, "readinessState", "unknown") or "unknown"
            )
        elif eff in {"done", "completed", "deferred"}:
            readiness_state = "ready"
        elif eff == "blocked":
            readiness_state = "blocked"
        elif eff in {"in-progress", "review"}:
            readiness_state = "ready"
        elif eff == "backlog":
            readiness_state = "waiting"

        # Dependency resolution summary.
        dep_resolution: dict[str, Any] = {}
        if dep_state:
            dep_resolution = {
                "state": dep_state.state,
                "dependency_count": dep_state.dependencyCount,
                "blocked_dependency_count": dep_state.blockedDependencyCount,
                "resolved_dependency_count": dep_state.resolvedDependencyCount,
                "blocking_reason": dep_state.blockingReason,
                "first_blocking_dependency_id": dep_state.firstBlockingDependencyId,
            }

        # Evidence from progress docs linked to this phase.
        progress_evidence: list[str] = []
        phase_token = str(target_phase.phase or "")
        for row in current_doc_rows:
            if str(row.get("doc_type") or "").strip().lower() != "progress":
                continue
            fp_raw = row.get("frontmatter_json") or row.get("frontmatter") or {}
            if isinstance(fp_raw, str):
                import json  # noqa: PLC0415
                try:
                    fp_raw = json.loads(fp_raw)
                except Exception:
                    fp_raw = {}
            if not isinstance(fp_raw, dict):
                fp_raw = {}
            if str(fp_raw.get("phase") or fp_raw.get("phase_number") or "") == phase_token:
                for key in ("status", "completed_tasks", "total_tasks", "notes"):
                    val = fp_raw.get(key)
                    if val is not None:
                        progress_evidence.append(f"{key}:{val}")

        data_freshness = derive_data_freshness(
            feature_row.get("updated_at") or feature_row.get("updatedAt"),
            *[row.get("updated_at") or row.get("updatedAt") for row in current_doc_rows],
        )

        return PhaseOperationsDTO(
            status="partial" if partial else "ok",
            feature_id=feature_id,
            phase_number=phase_number,
            phase_token=phase_token,
            phase_title=str(target_phase.title or ""),
            raw_status=_raw_status(ps) or str(target_phase.status or "backlog"),
            effective_status=eff,
            is_ready=is_ready,
            readiness_state=readiness_state,
            phase_batches=batches,
            blocked_batch_ids=blocked_batch_ids,
            tasks=task_items,
            dependency_resolution=dep_resolution,
            progress_evidence=progress_evidence,
            data_freshness=data_freshness,
            source_refs=collect_source_refs(feature_id, [str(phase_number)]),
        )
