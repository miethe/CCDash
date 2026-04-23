"""Section-oriented modal detail helpers for the feature surface."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Mapping

import aiosqlite

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.db.repositories.feature_queries import (
    LinkedSessionQuery,
    PhaseSummaryBulkQuery,
    SortDirection,
    ThreadExpansionMode,
)
from backend.db.repositories.feature_sessions import SqliteFeatureSessionRepository

try:
    import asyncpg
except ImportError:  # pragma: no cover - asyncpg may be absent in SQLite-only envs
    asyncpg = None


TestStatusLoader = Callable[
    [RequestContext, CorePorts, dict[str, Any]],
    Awaitable[dict[str, Any] | None],
]
ActivityLoader = Callable[
    [RequestContext, CorePorts, dict[str, Any], int, int],
    Awaitable[dict[str, Any] | None],
]


@dataclass(slots=True)
class ModalSectionResult:
    section: str
    cost_profile: str
    data: dict[str, Any]
    status: str = "ok"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _feature_payload(feature_row: Mapping[str, Any]) -> dict[str, Any]:
    raw = feature_row.get("data_json")
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _project_id_from_context(context: RequestContext) -> str:
    project = getattr(context, "project", None)
    return str(getattr(project, "project_id", "") or "")


def _row_or_none(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    if hasattr(row, "model_dump"):
        dumped = row.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if hasattr(row, "__dict__"):
        data = vars(row)
        if isinstance(data, dict):
            return dict(data)
    return dict(row)


def _group_tasks_by_phase(task_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in task_rows:
        phase_id = str(row.get("phase_id") or row.get("phaseId") or "")
        grouped.setdefault(phase_id, []).append(
            {
                "task_id": str(row.get("id") or row.get("task_id") or ""),
                "title": str(row.get("title") or ""),
                "status": str(row.get("status") or ""),
                "priority": str(row.get("priority") or ""),
                "owner": str(row.get("owner") or ""),
                "phase_id": phase_id,
                "updated_at": str(row.get("updated_at") or row.get("updatedAt") or ""),
            }
        )
    return grouped


class FeatureModalDetailService:
    """Build independently loadable modal-detail sections for a single feature."""

    def __init__(
        self,
        *,
        test_status_loader: TestStatusLoader | None = None,
        activity_loader: ActivityLoader | None = None,
    ) -> None:
        self._test_status_loader = test_status_loader
        self._activity_loader = activity_loader

    async def get_sections(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str,
        *,
        sections: Iterable[str],
        sessions_limit: int = 20,
        sessions_offset: int = 0,
    ) -> dict[str, ModalSectionResult]:
        feature_row = await self._get_feature_row(ports, feature_id)
        if feature_row is None:
            return {
                section: ModalSectionResult(
                    section=section,
                    status="not_found",
                    cost_profile="feature_lookup",
                    data={},
                )
                for section in sections
            }

        results: dict[str, ModalSectionResult] = {}
        for section in sections:
            if section == "overview":
                results[section] = self._build_overview(feature_row)
            elif section == "phases":
                results[section] = await self.get_phases_tasks(context, ports, feature_id, feature_row=feature_row)
            elif section == "documents":
                results[section] = await self.get_docs(context, ports, feature_id, feature_row=feature_row)
            elif section == "relations":
                results[section] = self._build_relations(feature_row)
            elif section == "sessions":
                results[section] = await self.get_sessions(
                    context,
                    ports,
                    feature_id,
                    limit=sessions_limit,
                    offset=sessions_offset,
                    feature_row=feature_row,
                )
            elif section == "test_status":
                results[section] = await self.get_test_status(context, ports, feature_id, feature_row=feature_row)
            elif section == "activity":
                results[section] = await self.get_activity(
                    context,
                    ports,
                    feature_id,
                    limit=50,
                    offset=0,
                    feature_row=feature_row,
                )
        return results

    async def get_overview(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str,
    ) -> ModalSectionResult:
        feature_row = await self._get_feature_row(ports, feature_id)
        if feature_row is None:
            return ModalSectionResult(section="overview", status="not_found", cost_profile="feature_lookup", data={})
        return self._build_overview(feature_row)

    async def get_phases_tasks(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str,
        *,
        feature_row: dict[str, Any] | None = None,
    ) -> ModalSectionResult:
        _ = context
        row = feature_row or await self._get_feature_row(ports, feature_id)
        if row is None:
            return ModalSectionResult(section="phases", status="not_found", cost_profile="feature_lookup", data={})

        phase_rows = await self._load_phase_rows(ports, row)
        task_rows = await self._load_task_rows(ports, feature_id)
        tasks_by_phase = _group_tasks_by_phase(task_rows)

        phases: list[dict[str, Any]] = []
        for phase in phase_rows:
            phase_id = str(phase.get("phase_id") or phase.get("id") or "")
            phases.append(
                {
                    "phase_id": phase_id,
                    "name": str(phase.get("name") or phase.get("title") or ""),
                    "status": str(phase.get("status") or ""),
                    "order_index": phase.get("order_index"),
                    "progress": phase.get("progress"),
                    "total_tasks": _safe_int(phase.get("total_tasks")),
                    "completed_tasks": _safe_int(phase.get("completed_tasks")),
                    "tasks": tasks_by_phase.get(phase_id, []),
                }
            )

        return ModalSectionResult(
            section="phases",
            cost_profile="feature_lookup + phase_summary_bulk + task_list_by_feature",
            data={
                "feature_id": feature_id,
                "phases": phases,
                "task_count": len(task_rows),
            },
        )

    async def get_docs(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str,
        *,
        feature_row: dict[str, Any] | None = None,
    ) -> ModalSectionResult:
        row = feature_row or await self._get_feature_row(ports, feature_id)
        if row is None:
            return ModalSectionResult(section="documents", status="not_found", cost_profile="feature_lookup", data={})

        project_id = _project_id_from_context(context) or str(row.get("project_id") or "")
        docs_repo = ports.storage.documents()
        docs = await docs_repo.list_paginated(
            project_id,
            0,
            100,
            {"feature": feature_id, "include_progress": True},
        )
        normalized = [
            {
                "document_id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "doc_type": str(item.get("doc_type") or item.get("docType") or ""),
                "file_path": str(item.get("file_path") or item.get("filePath") or ""),
                "status": str(item.get("status") or ""),
                "updated_at": str(item.get("updated_at") or item.get("updatedAt") or ""),
            }
            for item in docs
        ]

        payload = _feature_payload(row)
        return ModalSectionResult(
            section="documents",
            cost_profile="feature_lookup + documents.list_paginated(limit=100)",
            data={
                "feature_id": feature_id,
                "documents": normalized,
                "document_coverage": payload.get("documentCoverage") if isinstance(payload.get("documentCoverage"), dict) else {},
                "primary_documents": payload.get("primaryDocuments") if isinstance(payload.get("primaryDocuments"), list) else [],
            },
        )

    async def get_sessions(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "started_at",
        sort_direction: SortDirection = SortDirection.DESC,
        thread_expansion: ThreadExpansionMode = ThreadExpansionMode.INHERITED_THREADS,
        root_session_id: str | None = None,
        feature_row: dict[str, Any] | None = None,
    ) -> ModalSectionResult:
        row = feature_row or await self._get_feature_row(ports, feature_id)
        if row is None:
            return ModalSectionResult(section="sessions", status="not_found", cost_profile="feature_lookup", data={})

        project_id = _project_id_from_context(context) or str(row.get("project_id") or "")
        repo = self._feature_session_repository(ports.storage)
        page = await repo.list_feature_session_refs(
            project_id,
            LinkedSessionQuery(
                feature_id=feature_id,
                root_session_id=root_session_id,
                thread_expansion=thread_expansion,
                sort_by=sort_by,
                sort_direction=sort_direction,
                limit=limit,
                offset=offset,
            ),
        )
        return ModalSectionResult(
            section="sessions",
            cost_profile="feature_session_repository.page(limit<=50)",
            data={
                "feature_id": feature_id,
                "rows": page.rows,
                "total": page.total,
                "offset": page.offset,
                "limit": page.limit,
                "has_more": page.has_more,
            },
        )

    async def get_test_status(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str,
        *,
        feature_row: dict[str, Any] | None = None,
    ) -> ModalSectionResult:
        row = feature_row or await self._get_feature_row(ports, feature_id)
        if row is None:
            return ModalSectionResult(section="test_status", status="not_found", cost_profile="feature_lookup", data={})

        if self._test_status_loader is None:
            return ModalSectionResult(
                section="test_status",
                status="unavailable",
                cost_profile="deferred_loader",
                data={"feature_id": feature_id},
            )

        payload = await self._test_status_loader(context, ports, row)
        return ModalSectionResult(
            section="test_status",
            status="ok" if payload is not None else "unavailable",
            cost_profile="deferred_loader",
            data=payload or {"feature_id": feature_id},
        )

    async def get_activity(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        feature_row: dict[str, Any] | None = None,
    ) -> ModalSectionResult:
        row = feature_row or await self._get_feature_row(ports, feature_id)
        if row is None:
            return ModalSectionResult(section="activity", status="not_found", cost_profile="feature_lookup", data={})

        if self._activity_loader is None:
            return ModalSectionResult(
                section="activity",
                status="unavailable",
                cost_profile="deferred_loader",
                data={"feature_id": feature_id, "items": [], "limit": limit, "offset": offset},
            )

        payload = await self._activity_loader(context, ports, row, limit, offset)
        return ModalSectionResult(
            section="activity",
            status="ok" if payload is not None else "unavailable",
            cost_profile="deferred_loader",
            data=payload or {"feature_id": feature_id, "items": [], "limit": limit, "offset": offset},
        )

    def _build_overview(self, feature_row: Mapping[str, Any]) -> ModalSectionResult:
        payload = _feature_payload(feature_row)
        related_features = payload.get("relatedFeatures")
        return ModalSectionResult(
            section="overview",
            cost_profile="feature_lookup",
            data={
                "feature_id": str(feature_row.get("id") or ""),
                "name": str(feature_row.get("name") or ""),
                "status": str(feature_row.get("status") or ""),
                "category": str(feature_row.get("category") or ""),
                "summary": str(payload.get("summary") or ""),
                "description": str(payload.get("description") or ""),
                "priority": str(payload.get("priority") or ""),
                "risk_level": str(payload.get("riskLevel") or ""),
                "complexity": str(payload.get("complexity") or ""),
                "execution_readiness": str(payload.get("executionReadiness") or ""),
                "tags": _string_list(payload.get("tags")),
                "total_tasks": _safe_int(feature_row.get("total_tasks")),
                "completed_tasks": _safe_int(feature_row.get("completed_tasks")),
                "deferred_tasks": _safe_int(payload.get("deferredTasks")),
                "phase_count": _safe_int(payload.get("phaseCount")),
                "updated_at": str(feature_row.get("updated_at") or ""),
                "planned_at": str(payload.get("plannedAt") or ""),
                "started_at": str(payload.get("startedAt") or ""),
                "completed_at": str(payload.get("completedAt") or ""),
                "document_coverage": payload.get("documentCoverage") if isinstance(payload.get("documentCoverage"), dict) else {},
                "quality_signals": payload.get("qualitySignals") if isinstance(payload.get("qualitySignals"), dict) else {},
                "planning_status": payload.get("planningStatus") if isinstance(payload.get("planningStatus"), dict) else {},
                "related_feature_count": len(related_features) if isinstance(related_features, list) else 0,
            },
        )

    def _build_relations(self, feature_row: Mapping[str, Any]) -> ModalSectionResult:
        payload = _feature_payload(feature_row)
        blocking = payload.get("blockingFeatures")
        return ModalSectionResult(
            section="relations",
            cost_profile="feature_lookup",
            data={
                "feature_id": str(feature_row.get("id") or ""),
                "linked_features": payload.get("linkedFeatures") if isinstance(payload.get("linkedFeatures"), list) else [],
                "related_features": payload.get("relatedFeatures") if isinstance(payload.get("relatedFeatures"), list) else [],
                "dependency_state": payload.get("dependencyState") if isinstance(payload.get("dependencyState"), dict) else {},
                "blocking_features": blocking if isinstance(blocking, list) else [],
                "family_summary": payload.get("familySummary") if isinstance(payload.get("familySummary"), dict) else {},
                "family_position": payload.get("familyPosition") if isinstance(payload.get("familyPosition"), dict) else {},
                "execution_gate": payload.get("executionGate") if isinstance(payload.get("executionGate"), dict) else {},
            },
        )

    async def _get_feature_row(self, ports: CorePorts, feature_id: str) -> dict[str, Any] | None:
        row = await ports.storage.features().get_by_id(feature_id)
        return _row_or_none(row)

    async def _load_phase_rows(
        self,
        ports: CorePorts,
        feature_row: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        project_id = str(feature_row.get("project_id") or "")
        feature_id = str(feature_row.get("id") or "")
        feature_repo = ports.storage.features()
        if hasattr(feature_repo, "list_phase_summaries_for_features"):
            summaries = await feature_repo.list_phase_summaries_for_features(
                project_id,
                PhaseSummaryBulkQuery(feature_ids=[feature_id]),
            )
            rows = summaries.get(feature_id, [])
            return [_row_or_none(item) or {} for item in rows]

        payload = _feature_payload(feature_row)
        raw_phases = payload.get("phases")
        if not isinstance(raw_phases, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in raw_phases:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "phase_id": str(item.get("id") or ""),
                    "name": str(item.get("title") or ""),
                    "status": str(item.get("status") or ""),
                    "order_index": _safe_int(item.get("phase"), 0),
                    "progress": _safe_float(item.get("progress"), 0.0),
                    "total_tasks": _safe_int(item.get("totalTasks")),
                    "completed_tasks": _safe_int(item.get("completedTasks")),
                }
            )
        return rows

    async def _load_task_rows(self, ports: CorePorts, feature_id: str) -> list[dict[str, Any]]:
        rows = await ports.storage.tasks().list_by_feature(feature_id)
        return [_row_or_none(item) or {} for item in rows]

    def _feature_session_repository(self, storage: Any) -> Any:
        if hasattr(storage, "feature_sessions"):
            provider = storage.feature_sessions
            return provider() if callable(provider) else provider

        db = getattr(storage, "db", None)
        if isinstance(db, aiosqlite.Connection):
            return SqliteFeatureSessionRepository(db)
        if asyncpg is not None and isinstance(db, asyncpg.Connection):
            from backend.db.repositories.postgres.feature_sessions import PostgresFeatureSessionRepository

            return PostgresFeatureSessionRepository(db)
        raise TypeError("Storage does not expose a compatible feature session repository binding")
