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

import logging
from collections import Counter
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.models import (
    Feature,
    FeatureDependencyState,
    FeaturePhase,
    LinkedDocument,
    PlanningEffectiveStatus,
    PlanningGraph,
)
from backend.services.feature_execution import (
    apply_planning_projection,
    build_planning_graph,
    feature_dependency_state,
    feature_from_row,
    load_execution_documents,
)

from ._filters import collect_source_refs, derive_data_freshness, resolve_project_scope
from .cache import memoized_query
from .models import (
    FeaturePlanningContextDTO,
    FeatureSummaryItem,
    PhaseContextItem,
    PhaseOperationsDTO,
    PhaseTaskItem,
    PlanningNodeCountsByType,
    ProjectPlanningGraphDTO,
    ProjectPlanningSummaryDTO,
)

logger = logging.getLogger(__name__)

# ── Internal helpers ─────────────────────────────────────────────────────────


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


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
    **_: Any,
) -> dict[str, Any]:
    return {"project_id_override": project_id_override}


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
    ) -> ProjectPlanningSummaryDTO:
        """Return project-level planning health counts and feature summaries.

        Loads all features, applies planning projection, and aggregates:
        active vs stale counts, blocked/mismatch counts, reversal lists, and
        node-type distribution across all feature planning graphs.
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

            # Count node types from each feature's graph.
            current_doc_rows = _load_doc_rows_for_feature(doc_rows, feature.id)
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
                )
                for row in current_doc_rows
            ]
            try:
                graph = build_planning_graph(feature, linked_docs, None)
                for node in graph.nodes:
                    node_type_counter[str(node.type)] += 1
                node_count = len(graph.nodes)
            except Exception:
                node_count = 0
                partial = True

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
            total_feature_count=len(projected),
            active_feature_count=active_count,
            stale_feature_count=len(stale_ids),
            blocked_feature_count=len(blocked_ids),
            mismatch_count=mismatch_count,
            reversal_count=len(reversal_ids),
            stale_feature_ids=sorted(set(stale_ids)),
            reversal_feature_ids=sorted(set(reversal_ids)),
            blocked_feature_ids=sorted(set(blocked_ids)),
            node_counts_by_type=node_counts,
            feature_summaries=feature_summaries,
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

        graph = build_planning_graph(feature, linked_docs, None)

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
            data_freshness=data_freshness,
            source_refs=collect_source_refs(
                feature_id,
                [node.id for node in graph.nodes],
            ),
        )

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
