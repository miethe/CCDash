"""Application services for document read paths."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import HTTPException

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.common import resolve_project
from backend.date_utils import make_date_value
from backend.document_linking import (
    make_document_id,
    normalize_doc_status,
    normalize_doc_subtype,
    normalize_doc_type,
    normalize_ref_path,
)
from backend.models import PaginatedResponse, PlanDocument


def _safe_json(raw: str | dict | None) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _string_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(value) for value in raw if isinstance(value, str) and str(value).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _linked_feature_ref_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        feature = str(item.get("feature") or "").strip().lower()
        if not feature:
            continue
        confidence: float | None = None
        confidence_raw = item.get("confidence")
        if confidence_raw is not None:
            try:
                confidence = max(0.0, min(1.0, float(confidence_raw)))
            except Exception:
                confidence = None
        refs.append(
            {
                "feature": feature,
                "type": str(item.get("type") or "").strip().lower().replace("-", "_").replace(" ", "_"),
                "source": str(item.get("source") or "").strip().lower().replace("-", "_").replace(" ", "_"),
                "confidence": confidence,
                "notes": str(item.get("notes") or ""),
                "evidence": _string_list(item.get("evidence")),
            }
        )
    return refs


def _map_document_row_to_model(
    row: dict[str, Any],
    *,
    include_content: bool = False,
    link_counts: dict[str, int] | None = None,
) -> PlanDocument:
    fm = _safe_json(row.get("frontmatter_json"))
    metadata = _safe_json(row.get("metadata_json"))

    file_path = str(row.get("file_path") or "")
    canonical_path = str(row.get("canonical_path") or file_path)
    normalized_canonical = normalize_ref_path(canonical_path) or canonical_path
    path_segments = [segment for segment in normalized_canonical.split("/") if segment]

    linked_features = _string_list(fm.get("linkedFeatures"))
    linked_feature_refs = _linked_feature_ref_list(fm.get("linkedFeatureRefs"))
    if not linked_feature_refs:
        linked_feature_refs = _linked_feature_ref_list(metadata.get("linkedFeatureRefs"))

    feature_candidates = sorted(
        {
            *linked_features,
            *[str(value.get("feature") or "") for value in linked_feature_refs if isinstance(value, dict)],
            str(row.get("feature_slug_hint") or ""),
            str(row.get("feature_slug_canonical") or ""),
        }
    )
    feature_candidates = [value for value in feature_candidates if value]

    metadata_task_counts = metadata.get("taskCounts")
    if not isinstance(metadata_task_counts, dict):
        metadata_task_counts = {}

    date_metadata = metadata.get("dates")
    if not isinstance(date_metadata, dict):
        date_metadata = {}
    if not date_metadata.get("createdAt") and row.get("created_at"):
        date_metadata["createdAt"] = make_date_value(row.get("created_at"), "medium", "repository", "document_record_created")
    if not date_metadata.get("updatedAt") and row.get("updated_at"):
        date_metadata["updatedAt"] = make_date_value(row.get("updated_at"), "medium", "repository", "document_record_updated")
    if not date_metadata.get("lastActivityAt"):
        last_activity = row.get("last_modified") or row.get("updated_at")
        if last_activity:
            date_metadata["lastActivityAt"] = make_date_value(last_activity, "medium", "repository", "document_last_activity")

    timeline = metadata.get("timeline")
    if not isinstance(timeline, list):
        timeline = []

    frontmatter_obj = {
        "tags": _string_list(fm.get("tags")),
        "linkedFeatures": linked_features,
        "linkedFeatureRefs": linked_feature_refs,
        "blockedBy": _string_list(fm.get("blockedBy") or fm.get("blocked_by")),
        "sequenceOrder": fm.get("sequenceOrder") if fm.get("sequenceOrder") is not None else fm.get("sequence_order"),
        "linkedSessions": _string_list(fm.get("linkedSessions")),
        "linkedTasks": _string_list(fm.get("linkedTasks")),
        "lineageFamily": str(fm.get("lineageFamily") or ""),
        "lineageParent": str(fm.get("lineageParent") or ""),
        "lineageChildren": _string_list(fm.get("lineageChildren")),
        "lineageType": str(fm.get("lineageType") or ""),
        "version": fm.get("version"),
        "commits": _string_list(fm.get("commits")),
        "prs": _string_list(fm.get("prs")),
        "requestLogIds": _string_list(fm.get("requestLogIds")),
        "commitRefs": _string_list(fm.get("commitRefs")),
        "prRefs": _string_list(fm.get("prRefs")),
        "relatedRefs": _string_list(fm.get("relatedRefs")),
        "pathRefs": _string_list(fm.get("pathRefs")),
        "slugRefs": _string_list(fm.get("slugRefs")),
        "prd": str(fm.get("prd") or ""),
        "prdRefs": _string_list(fm.get("prdRefs")),
        "sourceDocuments": _string_list(fm.get("sourceDocuments")),
        "filesAffected": _string_list(fm.get("filesAffected")),
        "filesModified": _string_list(fm.get("filesModified")),
        "contextFiles": _string_list(fm.get("contextFiles")),
        "integritySignalRefs": _string_list(fm.get("integritySignalRefs")),
        "fieldKeys": _string_list(fm.get("fieldKeys")),
        "raw": fm.get("raw") if isinstance(fm.get("raw"), dict) else fm,
    }

    raw_status_normalized = str(row.get("status_normalized") or row.get("status") or "")
    normalized_status = normalize_doc_status(raw_status_normalized, default="pending")
    raw_doc_type = str(row.get("doc_type") or "")
    normalized_doc_type = normalize_doc_type(raw_doc_type, default="document")
    normalized_subtype = normalize_doc_subtype(
        str(row.get("doc_subtype") or ""),
        root_kind=str(row.get("root_kind") or ""),
        doc_type=normalized_doc_type,
    )

    completed_at = ""
    raw_completed = date_metadata.get("completedAt")
    if isinstance(raw_completed, dict):
        completed_at = str(raw_completed.get("value") or "")

    return PlanDocument(
        id=str(row.get("id") or make_document_id(normalized_canonical)),
        title=str(row.get("title") or ""),
        filePath=file_path,
        status=str(row.get("status") or "active"),
        createdAt=str(row.get("created_at") or ""),
        updatedAt=str(row.get("updated_at") or ""),
        completedAt=completed_at,
        lastModified=str(row.get("last_modified") or ""),
        author=str(row.get("author") or ""),
        docType=normalized_doc_type,
        category=str(row.get("category") or ""),
        docSubtype=normalized_subtype,
        rootKind=str(row.get("root_kind") or "project_plans"),
        canonicalPath=normalized_canonical,
        hasFrontmatter=bool(row.get("has_frontmatter")),
        frontmatterType=str(row.get("frontmatter_type") or ""),
        statusNormalized=normalized_status,
        featureSlugHint=str(row.get("feature_slug_hint") or ""),
        featureSlugCanonical=str(row.get("feature_slug_canonical") or ""),
        prdRef=str(row.get("prd_ref") or ""),
        phaseToken=str(row.get("phase_token") or ""),
        phaseNumber=row.get("phase_number"),
        overallProgress=row.get("overall_progress"),
        completionEstimate=str(metadata.get("completionEstimate") or ""),
        description=str(metadata.get("description") or ""),
        summary=str(metadata.get("summary") or ""),
        priority=str(metadata.get("priority") or ""),
        riskLevel=str(metadata.get("riskLevel") or ""),
        complexity=str(metadata.get("complexity") or ""),
        track=str(metadata.get("track") or ""),
        timelineEstimate=str(metadata.get("timelineEstimate") or ""),
        targetRelease=str(metadata.get("targetRelease") or ""),
        milestone=str(metadata.get("milestone") or ""),
        decisionStatus=str(metadata.get("decisionStatus") or ""),
        executionReadiness=str(metadata.get("executionReadiness") or ""),
        testImpact=str(metadata.get("testImpact") or ""),
        primaryDocRole=str(metadata.get("primaryDocRole") or ""),
        featureSlug=str(metadata.get("featureSlug") or ""),
        featureFamily=str(metadata.get("featureFamily") or ""),
        blockedBy=_string_list(metadata.get("blockedBy")),
        sequenceOrder=metadata.get("sequenceOrder"),
        featureVersion=str(metadata.get("featureVersion") or ""),
        planRef=str(metadata.get("planRef") or ""),
        implementationPlanRef=str(metadata.get("implementationPlanRef") or ""),
        totalTasks=int(row.get("total_tasks") or 0),
        completedTasks=int(row.get("completed_tasks") or 0),
        inProgressTasks=int(row.get("in_progress_tasks") or 0),
        blockedTasks=int(row.get("blocked_tasks") or 0),
        pathSegments=path_segments,
        featureCandidates=feature_candidates,
        frontmatter=frontmatter_obj,
        metadata={
            "phase": str(metadata.get("phase") or row.get("phase_token") or ""),
            "phaseNumber": metadata.get("phaseNumber", row.get("phase_number")),
            "overallProgress": metadata.get("overallProgress", row.get("overall_progress")),
            "completionEstimate": str(metadata.get("completionEstimate") or ""),
            "description": str(metadata.get("description") or ""),
            "summary": str(metadata.get("summary") or ""),
            "priority": str(metadata.get("priority") or ""),
            "riskLevel": str(metadata.get("riskLevel") or ""),
            "complexity": str(metadata.get("complexity") or ""),
            "track": str(metadata.get("track") or ""),
            "timelineEstimate": str(metadata.get("timelineEstimate") or ""),
            "targetRelease": str(metadata.get("targetRelease") or ""),
            "milestone": str(metadata.get("milestone") or ""),
            "decisionStatus": str(metadata.get("decisionStatus") or ""),
            "executionReadiness": str(metadata.get("executionReadiness") or ""),
            "testImpact": str(metadata.get("testImpact") or ""),
            "primaryDocRole": str(metadata.get("primaryDocRole") or ""),
            "featureSlug": str(metadata.get("featureSlug") or ""),
            "featureFamily": str(metadata.get("featureFamily") or ""),
            "blockedBy": _string_list(metadata.get("blockedBy")),
            "sequenceOrder": metadata.get("sequenceOrder"),
            "featureVersion": str(metadata.get("featureVersion") or ""),
            "planRef": str(metadata.get("planRef") or ""),
            "implementationPlanRef": str(metadata.get("implementationPlanRef") or ""),
            "taskCounts": {
                "total": int(metadata_task_counts.get("total", row.get("total_tasks") or 0)),
                "completed": int(metadata_task_counts.get("completed", row.get("completed_tasks") or 0)),
                "inProgress": int(metadata_task_counts.get("inProgress", row.get("in_progress_tasks") or 0)),
                "blocked": int(metadata_task_counts.get("blocked", row.get("blocked_tasks") or 0)),
            },
            "owners": _string_list(metadata.get("owners")),
            "contributors": _string_list(metadata.get("contributors")),
            "reviewers": _string_list(metadata.get("reviewers")),
            "approvers": _string_list(metadata.get("approvers")),
            "audience": _string_list(metadata.get("audience")),
            "labels": _string_list(metadata.get("labels")),
            "linkedTasks": _string_list(metadata.get("linkedTasks")),
            "requestLogIds": _string_list(metadata.get("requestLogIds")),
            "commitRefs": _string_list(metadata.get("commitRefs")),
            "prRefs": _string_list(metadata.get("prRefs")),
            "sourceDocuments": _string_list(metadata.get("sourceDocuments")),
            "filesAffected": _string_list(metadata.get("filesAffected")),
            "filesModified": _string_list(metadata.get("filesModified")),
            "contextFiles": _string_list(metadata.get("contextFiles")),
            "integritySignalRefs": _string_list(metadata.get("integritySignalRefs")),
            "executionEntrypoints": [
                entry
                for entry in metadata.get("executionEntrypoints", [])
                if isinstance(entry, dict)
            ] if isinstance(metadata.get("executionEntrypoints"), list) else [],
            "linkedFeatureRefs": linked_feature_refs,
            "docTypeFields": metadata.get("docTypeFields", {}) if isinstance(metadata.get("docTypeFields"), dict) else {},
            "featureSlugHint": metadata.get("featureSlugHint", row.get("feature_slug_hint") or ""),
            "canonicalPath": metadata.get("canonicalPath", normalized_canonical),
        },
        linkCounts={
            "features": int((link_counts or {}).get("features", 0)),
            "tasks": int((link_counts or {}).get("tasks", 0)),
            "sessions": int((link_counts or {}).get("sessions", 0)),
            "documents": int((link_counts or {}).get("documents", 0)),
        },
        dates=date_metadata,
        timeline=[event for event in timeline if isinstance(event, dict)],
        content=(str(row.get("content") or "") if include_content else None),
    )


class DocumentQueryService:
    async def list_documents(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        filters: dict[str, Any],
        offset: int,
        limit: int,
    ) -> PaginatedResponse[PlanDocument]:
        project = resolve_project(context, ports)
        if project is None:
            return PaginatedResponse(items=[], total=0, offset=offset, limit=limit)

        repo = ports.storage.documents()
        rows = await repo.list_paginated(project.id, offset, limit, filters)
        total = await repo.count(project.id, filters)
        items = [_map_document_row_to_model(row, include_content=False) for row in rows]
        return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)

    async def get_catalog(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        project = resolve_project(context, ports)
        if project is None:
            return {"total": 0}
        return await ports.storage.documents().get_catalog_facets(project.id, filters)

    async def get_document(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        doc_id: str,
        include_content: bool,
    ) -> PlanDocument:
        project = resolve_project(context, ports, required=True)
        if project is None:
            raise HTTPException(status_code=404, detail="No active project")

        row = await self._resolve_row(
            ports,
            project_id=project.id,
            doc_id=doc_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
        return _map_document_row_to_model(row, include_content=include_content)

    async def get_document_links(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        doc_id: str,
    ) -> dict[str, Any]:
        project = resolve_project(context, ports, required=True)
        if project is None:
            raise HTTPException(status_code=404, detail="No active project")

        row = await self._resolve_row(ports, project_id=project.id, doc_id=doc_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

        canonical_doc_id = str(row.get("id") or doc_id)
        link_repo = ports.storage.entity_links()
        feature_repo = ports.storage.features()
        task_repo = ports.storage.tasks()
        session_repo = ports.storage.sessions()
        doc_repo = ports.storage.documents()

        links = await link_repo.get_links_for("document", canonical_doc_id)

        feature_ids: set[str] = set()
        task_ids: set[str] = set()
        session_ids: set[str] = set()
        document_ids: set[str] = set()

        for link in links:
            source_type = str(link.get("source_type") or "")
            source_id = str(link.get("source_id") or "")
            target_type = str(link.get("target_type") or "")
            target_id = str(link.get("target_id") or "")

            if source_type == "document" and source_id == canonical_doc_id:
                counterpart_type = target_type
                counterpart_id = target_id
            elif target_type == "document" and target_id == canonical_doc_id:
                counterpart_type = source_type
                counterpart_id = source_id
            else:
                continue

            if counterpart_type == "feature":
                feature_ids.add(counterpart_id)
            elif counterpart_type == "task":
                task_ids.add(counterpart_id)
            elif counterpart_type == "session":
                session_ids.add(counterpart_id)
            elif counterpart_type == "document" and counterpart_id != canonical_doc_id:
                document_ids.add(counterpart_id)

        # Bulk fetch all linked entities to avoid N+1 per-link awaits.
        feature_id_list = sorted(feature_ids)
        session_id_list = sorted(session_ids)
        doc_id_list = sorted(document_ids)

        feature_map, session_map, doc_map = await asyncio.gather(
            feature_repo.get_many_by_ids(feature_id_list),
            session_repo.get_many_by_ids(session_id_list),
            doc_repo.get_many_by_ids(doc_id_list),
        )

        features = []
        for feature_id in feature_id_list:
            feature_row = feature_map.get(feature_id)
            if not feature_row:
                continue
            features.append(
                {
                    "id": feature_id,
                    "name": feature_row.get("name", ""),
                    "status": feature_row.get("status", ""),
                    "category": feature_row.get("category", ""),
                }
            )

        tasks = []
        for task_row in await task_repo.list_all(project.id):
            task_id = str(task_row.get("id") or "")
            if task_id not in task_ids:
                continue
            tasks.append(
                {
                    "id": task_id,
                    "title": task_row.get("title", ""),
                    "status": task_row.get("status", ""),
                    "sourceFile": task_row.get("source_file", ""),
                    "sessionId": task_row.get("session_id", ""),
                    "featureId": task_row.get("feature_id"),
                    "phaseId": task_row.get("phase_id"),
                }
            )

        sessions = []
        for session_id in session_id_list:
            session_row = session_map.get(session_id)
            if not session_row:
                continue
            sessions.append(
                {
                    "id": session_id,
                    "status": session_row.get("status", ""),
                    "model": session_row.get("model", ""),
                    "startedAt": session_row.get("started_at", ""),
                    "totalCost": session_row.get("total_cost", 0.0),
                }
            )

        documents = []
        for linked_doc_id in doc_id_list:
            linked_row = doc_map.get(linked_doc_id)
            if not linked_row:
                continue
            documents.append(
                {
                    "id": linked_doc_id,
                    "title": linked_row.get("title", ""),
                    "filePath": linked_row.get("file_path", ""),
                    "canonicalPath": linked_row.get("canonical_path", ""),
                    "docType": linked_row.get("doc_type", ""),
                    "docSubtype": linked_row.get("doc_subtype", ""),
                }
            )

        return {
            "documentId": canonical_doc_id,
            "features": features,
            "tasks": tasks,
            "sessions": sessions,
            "documents": documents,
        }

    async def _resolve_row(
        self,
        ports: CorePorts,
        *,
        project_id: str,
        doc_id: str,
    ) -> dict[str, Any] | None:
        repo = ports.storage.documents()
        row = await repo.get_by_id(doc_id)
        if row:
            return row

        row = await repo.get_by_path(project_id, doc_id)
        if row:
            return row

        if doc_id.startswith("DOC-"):
            candidate_path = normalize_ref_path(doc_id[4:].replace("-", "/"))
            if candidate_path:
                return await repo.get_by_path(project_id, candidate_path)
        return None
