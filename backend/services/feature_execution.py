"""Feature execution workbench service helpers."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

import aiosqlite

from backend.db.factory import get_document_repository, get_feature_repository
from backend.document_linking import canonical_slug, normalize_doc_status, normalize_doc_type
from backend.models import (
    ExecutionRecommendation,
    ExecutionRecommendationEvidence,
    ExecutionRecommendationOption,
    ExecutionGateState,
    Feature,
    FeatureDependencyEvidence,
    FeatureDependencyState,
    FeatureExecutionAnalyticsSummary,
    FeatureExecutionDerivedState,
    FeatureExecutionContext,
    FeatureExecutionWarning,
    FeatureFamilyItem,
    FeatureFamilyPosition,
    FeatureFamilySummary,
    FeaturePhase,
    FeaturePrimaryDocuments,
    FeatureDocumentCoverage,
    FeatureQualitySignals,
    LinkedDocument,
    RecommendedStack,
    StackRecommendationEvidence,
)

_TERMINAL_PHASE_STATUSES = {"done", "deferred", "completed"}
_FINAL_FEATURE_STATUSES = {"done", "deferred", "completed"}
_DOC_COMPLETION_STATUSES = {"completed", "deferred", "inferred_complete"}
_DOC_WRITE_THROUGH_TYPES = {"prd", "implementation_plan", "phase_plan"}
_FAMILY_STATUS_ORDER = {"done": 0, "deferred": 0, "completed": 0, "review": 1, "in-progress": 2, "backlog": 3}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _coerce_phase_number(raw: str) -> int | None:
    token = str(raw or "").strip().lower()
    if not token:
        return None
    if token.startswith("phase"):
        pieces = token.split()
        token = pieces[-1] if pieces else ""
    if token.isdigit():
        return int(token)
    return None


def _normalize_doc_type(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _feature_key(value: str) -> str:
    token = canonical_slug(str(value or "").strip())
    return token or str(value or "").strip().lower()


def _document_to_linked(row: dict[str, Any]) -> LinkedDocument:
    metadata = row.get("metadata_json")
    frontmatter = row.get("frontmatter_json")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    if isinstance(frontmatter, str):
        try:
            frontmatter = json.loads(frontmatter)
        except Exception:
            frontmatter = {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return LinkedDocument(
        id=str(row.get("id") or ""),
        title=str(row.get("title") or row.get("file_path") or "Untitled"),
        filePath=str(row.get("file_path") or ""),
        docType=str(row.get("doc_type") or "").strip() or "spec",
        category=str(row.get("category") or ""),
        featureFamily=str(metadata.get("featureFamily") or ""),
        primaryDocRole=str(metadata.get("primaryDocRole") or ""),
        blockedBy=[str(v) for v in (frontmatter.get("blockedBy") or frontmatter.get("blocked_by") or []) if isinstance(v, str)],
        sequenceOrder=metadata.get(
            "sequenceOrder",
            frontmatter.get("sequenceOrder") if frontmatter.get("sequenceOrder") is not None else frontmatter.get("sequence_order"),
        ),
        prdRef=str(row.get("prd_ref") or ""),
    )


def _is_completion_equivalent_doc_status(raw: str) -> bool:
    return normalize_doc_status(raw, default="") in _DOC_COMPLETION_STATUSES


def _phase_is_terminal(status: str) -> bool:
    return str(status or "").strip().lower() in _TERMINAL_PHASE_STATUSES


def _feature_is_finalized(status: str) -> bool:
    return str(status or "").strip().lower() in _FINAL_FEATURE_STATUSES


def _plan_documents(documents: list[LinkedDocument]) -> list[LinkedDocument]:
    return [doc for doc in documents if _normalize_doc_type(doc.docType) == "implementation_plan"]


def _find_planning_seed(documents: list[LinkedDocument]) -> LinkedDocument | None:
    candidates = [
        doc
        for doc in documents
        if _normalize_doc_type(doc.docType) in {"prd", "report"}
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda doc: (doc.docType != "prd", doc.filePath))[0]


def _phase_is_completion_equivalent(phase: Any) -> bool:
    status = str(getattr(phase, "status", "") or "").strip().lower()
    if status in _TERMINAL_PHASE_STATUSES:
        return True
    total = max(_safe_int(getattr(phase, "totalTasks", 0), 0), 0)
    completed = max(_safe_int(getattr(phase, "completedTasks", 0), 0), 0)
    return total > 0 and completed >= total


def _feature_from_row(row: dict[str, Any]) -> Feature:
    data = row.get("data_json")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}

    linked_docs = data.get("linkedDocs") or []
    phases = data.get("phases") or []
    return Feature(
        id=str(row.get("id") or data.get("id") or ""),
        name=str(row.get("name") or data.get("name") or ""),
        status=str(row.get("status") or data.get("status") or "backlog"),
        totalTasks=_safe_int(row.get("total_tasks", data.get("totalTasks", 0)), 0),
        completedTasks=_safe_int(row.get("completed_tasks", data.get("completedTasks", 0)), 0),
        deferredTasks=_safe_int(data.get("deferredTasks", row.get("deferred_tasks", 0)), 0),
        category=str(row.get("category") or data.get("category") or ""),
        tags=[str(v) for v in (data.get("tags") or []) if str(v).strip()],
        description=str(data.get("description") or ""),
        summary=str(data.get("summary") or ""),
        priority=str(data.get("priority") or ""),
        riskLevel=str(data.get("riskLevel") or ""),
        complexity=str(data.get("complexity") or ""),
        track=str(data.get("track") or ""),
        timelineEstimate=str(data.get("timelineEstimate") or ""),
        targetRelease=str(data.get("targetRelease") or ""),
        milestone=str(data.get("milestone") or ""),
        owners=[str(v) for v in (data.get("owners") or []) if str(v).strip()],
        contributors=[str(v) for v in (data.get("contributors") or []) if str(v).strip()],
        requestLogIds=[str(v) for v in (data.get("requestLogIds") or []) if str(v).strip()],
        commitRefs=[str(v) for v in (data.get("commitRefs") or []) if str(v).strip()],
        prRefs=[str(v) for v in (data.get("prRefs") or []) if str(v).strip()],
        executionReadiness=str(data.get("executionReadiness") or ""),
        testImpact=str(data.get("testImpact") or ""),
        featureFamily=str(data.get("featureFamily") or ""),
        updatedAt=str(row.get("updated_at") or data.get("updatedAt") or ""),
        plannedAt=str(data.get("plannedAt") or ""),
        startedAt=str(data.get("startedAt") or ""),
        completedAt=str(data.get("completedAt") or ""),
        linkedDocs=[LinkedDocument.model_validate(doc) for doc in linked_docs if isinstance(doc, dict)],
        linkedFeatures=[
            ref.model_dump() if hasattr(ref, "model_dump") else dict(ref)
            for ref in (data.get("linkedFeatures") or [])
            if isinstance(ref, dict) or hasattr(ref, "model_dump")
        ],
        primaryDocuments=FeaturePrimaryDocuments.model_validate(data.get("primaryDocuments") or {}) if isinstance(data.get("primaryDocuments"), dict) else FeaturePrimaryDocuments(),
        documentCoverage=FeatureDocumentCoverage.model_validate(data.get("documentCoverage") or {}) if isinstance(data.get("documentCoverage"), dict) else FeatureDocumentCoverage(),
        qualitySignals=FeatureQualitySignals.model_validate(data.get("qualitySignals") or {}) if isinstance(data.get("qualitySignals"), dict) else FeatureQualitySignals(),
        phases=[FeaturePhase.model_validate(phase) for phase in phases if isinstance(phase, dict)],
        relatedFeatures=[str(v) for v in (data.get("relatedFeatures") or []) if str(v).strip()],
        dates=data.get("dates") if isinstance(data.get("dates"), dict) else {},
        timeline=data.get("timeline") if isinstance(data.get("timeline"), list) else [],
    )


def _feature_sequence_order(feature: Feature, documents: list[LinkedDocument]) -> int | None:
    candidates: list[int] = []
    for doc in documents:
        if not isinstance(doc.sequenceOrder, int):
            continue
        if _feature_key(doc.featureFamily) and _feature_key(doc.featureFamily) != _feature_key(feature.featureFamily):
            continue
        candidates.append(int(doc.sequenceOrder))
    if candidates:
        return sorted(candidates)[0]
    return None


def _feature_completion_snapshot(feature: Feature, doc_rows: list[dict[str, Any]]) -> tuple[bool, list[str], list[str], list[str]]:
    prd_statuses: list[str] = []
    plan_statuses: list[str] = []
    phase_plan_statuses: list[str] = []
    completion_doc_ids: list[str] = []

    for row in doc_rows:
        doc_type = normalize_doc_type(str(row.get("doc_type") or row.get("docType") or ""))
        if doc_type not in _DOC_WRITE_THROUGH_TYPES:
            continue
        status_value = normalize_doc_status(str(row.get("status") or ""), default="")
        doc_id = str(row.get("id") or "")
        if doc_id:
            completion_doc_ids.append(doc_id)
        if doc_type == "prd":
            prd_statuses.append(status_value)
        elif doc_type == "implementation_plan":
            plan_statuses.append(status_value)
        elif doc_type == "phase_plan":
            phase_plan_statuses.append(status_value)

    prd_complete = any(_is_completion_equivalent_doc_status(s) for s in prd_statuses)
    plan_complete = any(_is_completion_equivalent_doc_status(s) for s in plan_statuses)
    phased_plan_complete = bool(phase_plan_statuses) and all(_is_completion_equivalent_doc_status(s) for s in phase_plan_statuses)
    progress_complete = bool(feature.phases) and all(_phase_is_completion_equivalent(phase) for phase in feature.phases)

    evidence: list[str] = []
    if prd_complete:
        evidence.append("prd_completion_equivalent")
    if plan_complete:
        evidence.append("implementation_plan_completion_equivalent")
    if phased_plan_complete:
        evidence.append("phase_plan_completion_equivalent")
    if progress_complete:
        evidence.append("feature_phases_completion_equivalent")

    return (prd_complete or plan_complete or phased_plan_complete or progress_complete, evidence, completion_doc_ids, [
        f"prd:{status}" for status in prd_statuses
    ] + [f"implementation_plan:{status}" for status in plan_statuses] + [f"phase_plan:{status}" for status in phase_plan_statuses])


def _feature_dependency_evidence(
    feature: Feature,
    doc_rows: list[dict[str, Any]],
    feature_index: dict[str, Feature],
) -> list[FeatureDependencyEvidence]:
    evidence_items: list[FeatureDependencyEvidence] = []
    seen: set[str] = set()
    for ref in feature.linkedFeatures:
        relation = str(getattr(ref, "type", "") or "").strip().lower().replace("-", "_").replace(" ", "_")
        source = str(getattr(ref, "source", "") or "").strip().lower().replace("-", "_").replace(" ", "_")
        if relation != "blocked_by" and source != "blocked_by":
            continue
        dependency_id = _feature_key(getattr(ref, "feature", ""))
        if not dependency_id or dependency_id in seen:
            continue
        seen.add(dependency_id)
        resolved_feature = feature_index.get(dependency_id)
        if resolved_feature is None:
            evidence_items.append(
                FeatureDependencyEvidence(
                    dependencyFeatureId=dependency_id,
                    dependencyStatus="unknown",
                    blockingReason=f"Dependency feature '{dependency_id}' could not be resolved.",
                    resolved=False,
                    state="blocked_unknown",
                )
            )
            continue

        dep_doc_rows = [
            row
            for row in doc_rows
            if _feature_key(str(row.get("feature_slug_canonical") or row.get("feature_slug_hint") or "")) == _feature_key(resolved_feature.id)
        ]
        is_complete, completion_evidence, blocking_doc_ids, doc_statuses = _feature_completion_snapshot(resolved_feature, dep_doc_rows)
        resolved_status = str(resolved_feature.status or "").strip().lower()
        if is_complete:
            evidence_items.append(
                FeatureDependencyEvidence(
                    dependencyFeatureId=resolved_feature.id,
                    dependencyFeatureName=resolved_feature.name,
                    dependencyStatus=resolved_status or "complete",
                    dependencyCompletionEvidence=completion_evidence or ["dependency_completion_equivalent"],
                    blockingDocumentIds=blocking_doc_ids,
                    blockingReason="Dependency feature is completion-equivalent.",
                    resolved=True,
                    state="complete",
                )
            )
            continue

        if resolved_status and resolved_status not in {"backlog", "in-progress", "review", "done", "deferred", "completed"}:
            evidence_items.append(
                FeatureDependencyEvidence(
                    dependencyFeatureId=resolved_feature.id,
                    dependencyFeatureName=resolved_feature.name,
                    dependencyStatus=resolved_status,
                    dependencyCompletionEvidence=doc_statuses,
                    blockingDocumentIds=blocking_doc_ids,
                    blockingReason="Dependency status is present but not recognized as complete.",
                    resolved=True,
                    state="blocked_unknown",
                )
            )
            continue

        evidence_items.append(
            FeatureDependencyEvidence(
                dependencyFeatureId=resolved_feature.id,
                dependencyFeatureName=resolved_feature.name,
                dependencyStatus=resolved_status or "blocked",
                dependencyCompletionEvidence=doc_statuses,
                blockingDocumentIds=blocking_doc_ids,
                blockingReason=f"Dependency feature '{resolved_feature.name or resolved_feature.id}' is not complete.",
                resolved=True,
                state="blocked",
            )
        )
    return evidence_items


def _feature_dependency_state(feature: Feature, doc_rows: list[dict[str, Any]], feature_index: dict[str, Feature]) -> FeatureDependencyState:
    dependencies = _feature_dependency_evidence(feature, doc_rows, feature_index)
    if not dependencies:
        return FeatureDependencyState(
            state="unblocked",
            dependencyCount=0,
            dependencies=[],
        )

    resolved = [dep for dep in dependencies if dep.resolved]
    blocked = [dep for dep in dependencies if dep.state == "blocked"]
    unknown = [dep for dep in dependencies if dep.state == "blocked_unknown"]
    completion_evidence = [
        evidence
        for dep in dependencies
        if dep.state == "complete"
        for evidence in dep.dependencyCompletionEvidence
    ]
    blocking_feature_ids = [dep.dependencyFeatureId for dep in blocked + unknown if dep.dependencyFeatureId]
    blocking_document_ids = [
        doc_id
        for dep in blocked + unknown
        for doc_id in dep.blockingDocumentIds
        if doc_id
    ]
    first_blocking = next((dep for dep in dependencies if dep.state in {"blocked", "blocked_unknown"}), None)
    aggregate_state = "unblocked"
    if unknown:
        aggregate_state = "blocked_unknown"
    elif blocked:
        aggregate_state = "blocked"

    return FeatureDependencyState(
        state=aggregate_state,
        dependencyCount=len(dependencies),
        resolvedDependencyCount=len(resolved),
        blockedDependencyCount=len(blocked),
        unknownDependencyCount=len(unknown),
        blockingFeatureIds=sorted(dict.fromkeys(blocking_feature_ids)),
        blockingDocumentIds=sorted(dict.fromkeys(blocking_document_ids)),
        firstBlockingDependencyId=first_blocking.dependencyFeatureId if first_blocking else "",
        blockingReason=first_blocking.blockingReason if first_blocking else "",
        completionEvidence=sorted(dict.fromkeys(completion_evidence)),
        dependencies=dependencies,
    )


def _family_status_rank(status: str) -> int:
    return _FAMILY_STATUS_ORDER.get(str(status or "").strip().lower(), 4)


def _feature_family_item(
    feature: Feature,
    sequence_order: int | None,
    current_feature_id: str,
    dependency_state: FeatureDependencyState,
    primary_doc: LinkedDocument | None,
    completion_equivalent: bool = False,
) -> FeatureFamilyItem:
    effective_status = feature.status
    if completion_equivalent and str(feature.status or "").strip().lower() not in _FINAL_FEATURE_STATUSES:
        effective_status = "done"
    return FeatureFamilyItem(
        featureId=feature.id,
        featureName=feature.name,
        featureStatus=effective_status,
        featureFamily=_feature_key(feature.featureFamily),
        sequenceOrder=sequence_order,
        isCurrent=_feature_key(feature.id) == _feature_key(current_feature_id),
        isSequenced=sequence_order is not None,
        isBlocked=dependency_state.state == "blocked",
        isBlockedUnknown=dependency_state.state == "blocked_unknown",
        isExecutable=(
            not completion_equivalent
            and dependency_state.state in {"unblocked", "ready_after_dependencies"}
            and effective_status not in _FINAL_FEATURE_STATUSES
        ),
        dependencyState=dependency_state,
        primaryDocId=str(primary_doc.id) if primary_doc else "",
        primaryDocPath=str(primary_doc.filePath) if primary_doc else "",
    )


def _family_summary(
    feature: Feature,
    family_features: list[Feature],
    doc_rows: list[dict[str, Any]],
    feature_index: dict[str, Feature],
) -> tuple[FeatureFamilySummary, FeatureFamilyPosition, FeatureFamilyItem | None]:
    family_key = _feature_key(feature.featureFamily)
    if not family_key:
        family_key = _feature_key(feature.id)

    family_members = [member for member in family_features if _feature_key(member.featureFamily or member.id) == family_key]
    if not family_members:
        family_members = [feature]

    family_items: list[tuple[FeatureFamilyItem, tuple[Any, ...]]] = []
    for member in family_members:
        member_doc_rows = [
            row
            for row in doc_rows
            if _feature_key(str(row.get("feature_slug_canonical") or row.get("feature_slug_hint") or "")) == _feature_key(member.id)
        ]
        member_docs = [_document_to_linked(row) for row in member_doc_rows]
        member_seq = _feature_sequence_order(member, member_docs)
        member_dependency_state = _feature_dependency_state(member, member_doc_rows, feature_index)
        member_completion_equivalent, _, _, _ = _feature_completion_snapshot(member, member_doc_rows)
        primary_doc = next((doc for doc in member_docs if _normalize_doc_type(doc.docType) == "implementation_plan"), None)
        item = _feature_family_item(
            member,
            member_seq,
            feature.id,
            member_dependency_state,
            primary_doc,
            completion_equivalent=member_completion_equivalent,
        )
        sort_key = (
            0 if item.isSequenced else 1,
            member_seq if member_seq is not None else 10_000,
            _family_status_rank(item.featureStatus),
            (member.name or member.id).strip().lower(),
            member.id.strip().lower(),
        )
        family_items.append((item, sort_key))

    ordered_items = [item for item, _ in sorted(family_items, key=lambda pair: pair[1])]
    for index, item in enumerate(ordered_items, start=1):
        item.familyIndex = index
        item.totalFamilyItems = len(ordered_items)

    preceding_open_item_seen = False
    next_recommended_item: FeatureFamilyItem | None = None
    for item in ordered_items:
        if item.featureStatus in _FINAL_FEATURE_STATUSES:
            item.isExecutable = False
            continue
        if preceding_open_item_seen:
            item.isExecutable = False
            continue
        item.isExecutable = item.dependencyState.state in {"unblocked", "ready_after_dependencies"}
        if item.isExecutable and next_recommended_item is None:
            next_recommended_item = item
        preceding_open_item_seen = True

    current_item = next((item for item in ordered_items if item.isCurrent), None)
    if current_item is None:
        current_item = ordered_items[0] if ordered_items else None

    sequenced_count = sum(1 for item in ordered_items if item.isSequenced)
    unsequenced_count = len(ordered_items) - sequenced_count
    current_index = current_item.familyIndex if current_item else 0
    current_sequenced_index = current_index if current_item and current_item.isSequenced else 0
    if (
        next_recommended_item is None
        and current_item
        and current_item.isExecutable
        and current_item.dependencyState.state in {"unblocked", "ready_after_dependencies"}
    ):
        next_recommended_item = current_item

    summary = FeatureFamilySummary(
        featureFamily=family_key,
        totalItems=len(ordered_items),
        sequencedItems=sequenced_count,
        unsequencedItems=unsequenced_count,
        currentFeatureId=feature.id,
        currentFeatureName=feature.name,
        currentPosition=current_index,
        currentSequencedPosition=current_sequenced_index,
        nextRecommendedFeatureId=next_recommended_item.featureId if next_recommended_item else "",
        nextRecommendedFamilyItem=next_recommended_item,
        items=ordered_items,
    )
    position = FeatureFamilyPosition(
        familyKey=family_key,
        currentIndex=current_index,
        sequencedIndex=current_sequenced_index,
        totalItems=len(ordered_items),
        sequencedItems=sequenced_count,
        unsequencedItems=unsequenced_count,
        display=(
            f"{current_index} of {len(ordered_items)}" if current_index and current_item and current_item.isSequenced
            else (f"Unsequenced, {current_index} of {len(ordered_items)}" if current_index else "Unsequenced")
        ),
        currentItemId=current_item.featureId if current_item else "",
        nextItemId=next_recommended_item.featureId if next_recommended_item else "",
        nextItemLabel=next_recommended_item.featureName if next_recommended_item else "",
    )
    return summary, position, next_recommended_item


def _execution_gate_state(
    feature: Feature,
    dependency_state: FeatureDependencyState,
    family_summary: FeatureFamilySummary,
    family_position: FeatureFamilyPosition,
    recommended_family_item: FeatureFamilyItem | None,
) -> ExecutionGateState:
    if dependency_state.state == "blocked_unknown":
        return ExecutionGateState(
            state="unknown_dependency_state",
            blockingDependencyId=dependency_state.firstBlockingDependencyId,
            firstExecutableFamilyItemId=recommended_family_item.featureId if recommended_family_item else "",
            recommendedFamilyItemId=recommended_family_item.featureId if recommended_family_item else "",
            familyPosition=family_position,
            dependencyState=dependency_state,
            familySummary=family_summary,
            reason=dependency_state.blockingReason or "Dependency evidence is incomplete.",
            waitingOnFamilyPredecessor=False,
            isReady=False,
        )
    if dependency_state.state == "blocked":
        return ExecutionGateState(
            state="blocked_dependency",
            blockingDependencyId=dependency_state.firstBlockingDependencyId,
            firstExecutableFamilyItemId=recommended_family_item.featureId if recommended_family_item else "",
            recommendedFamilyItemId=recommended_family_item.featureId if recommended_family_item else "",
            familyPosition=family_position,
            dependencyState=dependency_state,
            familySummary=family_summary,
            reason=dependency_state.blockingReason or "Dependency must be completed first.",
            waitingOnFamilyPredecessor=False,
            isReady=False,
        )

    current_item = next((item for item in family_summary.items if item.isCurrent), None)
    predecessor_item = next(
        (
            item
            for item in family_summary.items
            if current_item
            and item.familyIndex < current_item.familyIndex
            and item.featureStatus not in _FINAL_FEATURE_STATUSES
        ),
        None,
    )
    if current_item and recommended_family_item and recommended_family_item.featureId != feature.id:
        return ExecutionGateState(
            state="waiting_on_family_predecessor",
            blockingDependencyId=dependency_state.firstBlockingDependencyId,
            firstExecutableFamilyItemId=recommended_family_item.featureId,
            recommendedFamilyItemId=recommended_family_item.featureId,
            familyPosition=family_position,
            dependencyState=dependency_state,
            familySummary=family_summary,
            reason=(
                f"Family predecessor '{recommended_family_item.featureName or recommended_family_item.featureId}' should execute first."
            ),
            waitingOnFamilyPredecessor=True,
            isReady=False,
        )
    if current_item and predecessor_item and not current_item.isExecutable and current_item.featureStatus not in _FINAL_FEATURE_STATUSES:
        return ExecutionGateState(
            state="waiting_on_family_predecessor",
            blockingDependencyId=predecessor_item.featureId,
            firstExecutableFamilyItemId=recommended_family_item.featureId if recommended_family_item else "",
            recommendedFamilyItemId=recommended_family_item.featureId if recommended_family_item else predecessor_item.featureId,
            familyPosition=family_position,
            dependencyState=dependency_state,
            familySummary=family_summary,
            reason=(
                f"Family predecessor '{predecessor_item.featureName or predecessor_item.featureId}' should complete before this item."
            ),
            waitingOnFamilyPredecessor=True,
            isReady=False,
        )

    return ExecutionGateState(
        state="ready",
        blockingDependencyId="",
        firstExecutableFamilyItemId=recommended_family_item.featureId if recommended_family_item else feature.id,
        recommendedFamilyItemId=recommended_family_item.featureId if recommended_family_item else feature.id,
        familyPosition=family_position,
        dependencyState=dependency_state,
        familySummary=family_summary,
        reason="Dependency and family ordering are clear.",
        waitingOnFamilyPredecessor=False,
        isReady=True,
    )


async def load_feature_execution_derived_state(
    db: Any,
    project_id: str,
    feature: Feature,
    documents: list[LinkedDocument] | None = None,
) -> FeatureExecutionDerivedState:
    feature_repo = get_feature_repository(db)
    doc_repo = get_document_repository(db)

    feature_rows = await feature_repo.list_all(project_id)
    family_features = [_feature_from_row(row) for row in feature_rows]
    feature_index: dict[str, Feature] = {}
    for item in family_features:
        feature_index[_feature_key(item.id)] = item

    doc_rows = await doc_repo.list_all(project_id)
    dependency_state = _feature_dependency_state(feature, doc_rows, feature_index)
    family_summary, family_position, recommended_family_item = _family_summary(feature, family_features, doc_rows, feature_index)

    execution_gate = _execution_gate_state(feature, dependency_state, family_summary, family_position, recommended_family_item)

    return FeatureExecutionDerivedState(
        dependencyState=dependency_state,
        familySummary=family_summary,
        familyPosition=family_position,
        executionGate=execution_gate,
        recommendedFamilyItem=recommended_family_item,
    )


async def load_feature_execution_derived_states(
    db: Any,
    project_id: str,
    features: list[Feature],
) -> dict[str, FeatureExecutionDerivedState]:
    feature_repo = get_feature_repository(db)
    doc_repo = get_document_repository(db)

    feature_rows = await feature_repo.list_all(project_id)
    family_features = [_feature_from_row(row) for row in feature_rows]
    feature_index: dict[str, Feature] = {_feature_key(item.id): item for item in family_features}
    doc_rows = await doc_repo.list_all(project_id)

    derived: dict[str, FeatureExecutionDerivedState] = {}
    for feature in features:
        dependency_state = _feature_dependency_state(feature, doc_rows, feature_index)
        family_summary, family_position, recommended_family_item = _family_summary(
            feature,
            family_features,
            doc_rows,
            feature_index,
        )

        execution_gate = _execution_gate_state(
            feature,
            dependency_state,
            family_summary,
            family_position,
            recommended_family_item,
        )
        derived[feature.id] = FeatureExecutionDerivedState(
            dependencyState=dependency_state,
            familySummary=family_summary,
            familyPosition=family_position,
            executionGate=execution_gate,
            recommendedFamilyItem=recommended_family_item,
        )

    return derived


def _phase_snapshot(feature: Feature) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for phase in feature.phases:
        number = _coerce_phase_number(phase.phase)
        status = str(phase.status or "backlog").strip().lower()
        is_terminal = _phase_is_terminal(status)

        # Count deferred tasks as completed for progression detection.
        completed = _safe_int(getattr(phase, "completedTasks", 0), 0)
        deferred = _safe_int(getattr(phase, "deferredTasks", 0), 0)
        total = _safe_int(getattr(phase, "totalTasks", 0), 0)
        effectively_completed = max(completed, deferred)
        if total > 0:
            effectively_completed = min(total, effectively_completed)

        has_completed_work = is_terminal or (
            total > 0 and effectively_completed >= total
        )

        snapshots.append(
            {
                "token": str(phase.phase),
                "number": number,
                "status": status,
                "terminal": is_terminal,
                "completed": has_completed_work,
            }
        )
    return snapshots


def build_execution_recommendation(
    feature: Feature,
    documents: list[LinkedDocument],
) -> ExecutionRecommendation:
    plan_docs = _plan_documents(documents)
    plan_doc = sorted(plan_docs, key=lambda doc: doc.filePath)[0] if plan_docs else None
    planning_seed_doc = _find_planning_seed(documents)

    phases = _phase_snapshot(feature)
    completed_numbers = sorted(
        {
            int(row["number"])
            for row in phases
            if row["number"] is not None and bool(row["completed"])
        }
    )
    active_numbers = sorted(
        {
            int(row["number"])
            for row in phases
            if row["number"] is not None and row["status"] in {"in-progress", "review"}
        }
    )

    highest_completed = completed_numbers[-1] if completed_numbers else None
    next_phase: int | None = None
    if highest_completed is not None:
        candidate = highest_completed + 1
        for row in phases:
            if row["number"] == candidate and not bool(row["terminal"]):
                next_phase = candidate
                break

    def make_option(
        rule_id: str,
        command: str,
        confidence: float,
        explanation: str,
        evidence_refs: list[str],
    ) -> ExecutionRecommendationOption:
        return ExecutionRecommendationOption(
            command=command,
            ruleId=rule_id,
            confidence=confidence,
            explanation=explanation,
            evidenceRefs=evidence_refs,
        )

    candidates: list[ExecutionRecommendationOption] = []

    # R1
    if plan_doc is None and planning_seed_doc is not None:
        candidates.append(
            make_option(
                "R1_PLAN_FROM_PRD_OR_REPORT",
                f"/plan:plan-feature {planning_seed_doc.filePath}",
                0.96,
                "Implementation plan is missing but a PRD/report exists, so planning should be generated first.",
                [planning_seed_doc.filePath, "missing:implementation_plan"],
            )
        )

    # R2
    if plan_doc is not None and not completed_numbers:
        candidates.append(
            make_option(
                "R2_START_PHASE_1",
                f"/dev:execute-phase 1 {plan_doc.filePath}",
                0.92,
                "Implementation plan exists and no completed phases were detected, so Phase 1 should start.",
                [plan_doc.filePath, "completed_phases:0"],
            )
        )

    # R3
    if plan_doc is not None and highest_completed is not None and next_phase is not None:
        candidates.append(
            make_option(
                "R3_ADVANCE_TO_NEXT_PHASE",
                f"/dev:execute-phase {next_phase} {plan_doc.filePath}",
                0.9,
                "A completed phase was found and the next phase is not terminal, so advance to the next phase.",
                [
                    plan_doc.filePath,
                    f"highest_completed_phase:{highest_completed}",
                    f"next_phase:{next_phase}",
                ],
            )
        )

    # R4
    if plan_doc is not None and active_numbers:
        active_phase = active_numbers[0]
        candidates.append(
            make_option(
                "R4_RESUME_ACTIVE_PHASE",
                f"/dev:execute-phase {active_phase} {plan_doc.filePath}",
                0.89,
                "An in-progress/review phase is active, so work should resume in that phase.",
                [plan_doc.filePath, f"active_phase:{active_phase}"],
            )
        )

    # R5
    all_terminal = bool(phases) and all(bool(row["terminal"]) for row in phases)
    if all_terminal and not _feature_is_finalized(feature.status):
        candidates.append(
            make_option(
                "R5_COMPLETE_STORY",
                f"/dev:complete-user-story {feature.id}",
                0.9,
                "All phases are terminal but feature status is not finalized, so story completion should run.",
                [f"feature:{feature.id}", "all_phases_terminal:true"],
            )
        )

    # R6 fallback
    fallback_confidence = 0.66 if documents else 0.45
    candidates.append(
        make_option(
            "R6_FALLBACK_QUICK_FEATURE",
            f"/dev:quick-feature {feature.id}",
            fallback_confidence,
            "Evidence is insufficient or ambiguous for a deterministic phase command.",
            [f"feature:{feature.id}", "evidence:insufficient"],
        )
    )

    primary = candidates[0]
    alternatives: list[ExecutionRecommendationOption] = []
    seen_commands = {primary.command}
    for candidate in candidates[1:]:
        if candidate.command in seen_commands:
            continue
        alternatives.append(candidate)
        seen_commands.add(candidate.command)
        if len(alternatives) >= 2:
            break

    evidence: list[ExecutionRecommendationEvidence] = []
    for idx, ref in enumerate(primary.evidenceRefs):
        source_type = "context"
        if ref.endswith(".md"):
            source_type = "document"
        elif ref.startswith("active_phase") or ref.startswith("next_phase") or ref.startswith("highest_completed_phase"):
            source_type = "phase"
        elif ref.startswith("feature:"):
            source_type = "feature"
        evidence.append(
            ExecutionRecommendationEvidence(
                id=f"EV-{idx + 1}",
                label=ref.split(":", 1)[0].replace("_", " ").title(),
                value=ref,
                sourceType=source_type,
                sourcePath=ref if ref.endswith(".md") else "",
            )
        )

    return ExecutionRecommendation(
        primary=primary,
        alternatives=alternatives,
        ruleId=primary.ruleId,
        confidence=primary.confidence,
        explanation=primary.explanation,
        evidenceRefs=primary.evidenceRefs,
        evidence=evidence,
    )


async def load_execution_documents(
    db: Any,
    project_id: str,
    feature_id: str,
    fallback_documents: list[LinkedDocument] | None = None,
) -> list[LinkedDocument]:
    repo = get_document_repository(db)
    rows = await repo.list_paginated(
        project_id,
        0,
        250,
        {
            "feature": feature_id,
            "include_progress": True,
        },
    )
    docs = [_document_to_linked(row) for row in rows]

    if not docs and fallback_documents:
        docs = list(fallback_documents)

    deduped: dict[str, LinkedDocument] = {}
    for doc in docs:
        key = (doc.filePath or doc.id or doc.title).strip().lower()
        if not key:
            continue
        deduped[key] = doc

    return sorted(
        deduped.values(),
        key=lambda doc: (
            doc.sequenceOrder if isinstance(doc.sequenceOrder, int) else 10_000,
            doc.docType,
            doc.filePath,
            doc.title,
        ),
    )


def _session_value(session: Any, key: str, default: Any = None) -> Any:
    if isinstance(session, dict):
        return session.get(key, default)
    return getattr(session, key, default)


async def load_execution_analytics(
    db: Any,
    project_id: str,
    feature_id: str,
    sessions: list[Any],
) -> FeatureExecutionAnalyticsSummary:
    model_tokens = {
        str(_session_value(session, "modelDisplayName") or _session_value(session, "model") or "").strip()
        for session in sessions
        if str(_session_value(session, "modelDisplayName") or _session_value(session, "model") or "").strip()
    }

    summary = FeatureExecutionAnalyticsSummary(
        sessionCount=len(sessions),
        primarySessionCount=sum(1 for session in sessions if bool(_session_value(session, "isPrimaryLink", False))),
        totalSessionCost=round(sum(_safe_float(_session_value(session, "totalCost"), 0.0) for session in sessions), 4),
        modelCount=len(model_tokens),
    )

    if isinstance(db, aiosqlite.Connection):
        query = """
            SELECT
                COALESCE(SUM(CASE WHEN event_type = 'artifact.linked' THEN 1 ELSE 0 END), 0) AS artifact_events,
                COALESCE(SUM(CASE WHEN event_type = 'log.command' THEN 1 ELSE 0 END), 0) AS command_events,
                COALESCE(MAX(occurred_at), '') AS last_event_at
            FROM telemetry_events
            WHERE project_id = ? AND feature_id = ?
        """
        async with db.execute(query, (project_id, feature_id)) as cur:
            row = await cur.fetchone()
            if row:
                summary.artifactEventCount = _safe_int(row[0], 0)
                summary.commandEventCount = _safe_int(row[1], 0)
                summary.lastEventAt = str(row[2] or "")
        return summary

    row = await db.fetchrow(
        """
            SELECT
                COALESCE(SUM(CASE WHEN event_type = 'artifact.linked' THEN 1 ELSE 0 END), 0) AS artifact_events,
                COALESCE(SUM(CASE WHEN event_type = 'log.command' THEN 1 ELSE 0 END), 0) AS command_events,
                COALESCE(MAX(occurred_at), '') AS last_event_at
            FROM telemetry_events
            WHERE project_id = $1 AND feature_id = $2
        """,
        project_id,
        feature_id,
    )
    if row:
        summary.artifactEventCount = _safe_int(row.get("artifact_events"), 0)
        summary.commandEventCount = _safe_int(row.get("command_events"), 0)
        summary.lastEventAt = str(row.get("last_event_at") or "")
    return summary


def build_execution_context(
    feature: Feature,
    documents: list[LinkedDocument],
    sessions: list[Any],
    analytics: FeatureExecutionAnalyticsSummary,
    warnings: list[FeatureExecutionWarning] | None = None,
    recommended_stack: RecommendedStack | None = None,
    stack_alternatives: list[RecommendedStack] | None = None,
    stack_evidence: list[StackRecommendationEvidence] | None = None,
    definition_resolution_warnings: list[FeatureExecutionWarning] | None = None,
    derived_state: FeatureExecutionDerivedState | None = None,
) -> FeatureExecutionContext:
    recommendation = build_execution_recommendation(feature, documents)
    return FeatureExecutionContext(
        feature=feature,
        documents=documents,
        sessions=[session.model_dump() if hasattr(session, "model_dump") else dict(session) for session in sessions],
        analytics=analytics,
        recommendations=recommendation,
        dependencyState=derived_state.dependencyState if derived_state else None,
        familySummary=derived_state.familySummary if derived_state else None,
        familyPosition=derived_state.familyPosition if derived_state else None,
        executionGate=derived_state.executionGate if derived_state else None,
        recommendedFamilyItem=derived_state.recommendedFamilyItem if derived_state else None,
        warnings=warnings or [],
        recommendedStack=recommended_stack,
        stackAlternatives=stack_alternatives or [],
        stackEvidence=stack_evidence or [],
        definitionResolutionWarnings=definition_resolution_warnings or [],
        generatedAt=datetime.now(timezone.utc).isoformat(),
    )
