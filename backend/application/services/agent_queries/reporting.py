"""After-action reporting service for feature delivery history."""
from __future__ import annotations

from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.agent_queries.feature_forensics import (
    _document_ref_from_row,
    _feature_slug,
    _load_feature_session_rows,
    _session_ref_from_row,
    _task_ref_from_row,
)
from backend.services.workflow_effectiveness import detect_failure_patterns, get_workflow_effectiveness

from ._filters import collect_source_refs, derive_data_freshness, resolve_project_scope
from .models import AARReportDTO, Bottleneck, KeyMetrics, TimelineData, TurningPoint, WorkflowObservation


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _timeline_data(session_rows: list[dict[str, Any]]) -> TimelineData:
    started = [
        str(row.get("started_at") or row.get("startedAt") or "")
        for row in session_rows
        if str(row.get("started_at") or row.get("startedAt") or "").strip()
    ]
    ended = [
        str(row.get("ended_at") or row.get("endedAt") or "")
        for row in session_rows
        if str(row.get("ended_at") or row.get("endedAt") or "").strip()
    ]
    start_value = min(started) if started else ""
    end_value = max(ended) if ended else ""
    duration_days = 0.0
    if start_value and end_value:
        start_dt = derive_data_freshness(start_value)
        end_dt = derive_data_freshness(end_value)
        duration_days = max((end_dt - start_dt).total_seconds() / 86400.0, 0.0)
    return TimelineData(started_at=start_value, ended_at=end_value, duration_days=round(duration_days, 2))


class ReportingQueryService:
    """Generate deterministic feature after-action reports."""

    async def generate_aar(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str,
    ) -> AARReportDTO:
        scope = resolve_project_scope(context, ports)
        if scope is None:
            return AARReportDTO(status="error", feature_id=feature_id, source_refs=[feature_id])

        partial = False
        feature_row = await ports.storage.features().get_by_id(feature_id)
        if feature_row is None:
            return AARReportDTO(status="error", feature_id=feature_id, source_refs=[feature_id])

        links: list[dict[str, Any]] = []
        try:
            links = await ports.storage.entity_links().get_links_for("feature", feature_id, "related")
        except Exception:
            partial = True

        linked_session_ids = sorted(
            {
                str(link.get("target_id") or link.get("source_id") or "")
                for link in links
                if "session" in {str(link.get("source_type") or ""), str(link.get("target_type") or "")}
            }
        )

        document_rows: list[dict[str, Any]] = []
        try:
            document_rows = await ports.storage.documents().list_paginated(
                scope.project.id,
                0,
                100,
                {"feature": feature_id, "include_progress": True},
            )
        except Exception:
            partial = True

        task_rows: list[dict[str, Any]] = []
        try:
            task_rows = await ports.storage.tasks().list_by_feature(feature_id)
        except Exception:
            partial = True

        session_rows: list[dict[str, Any]] = []
        try:
            session_rows = await _load_feature_session_rows(context, ports, feature_id, linked_session_ids)
        except Exception:
            partial = True

        session_refs = [_session_ref_from_row(row) for row in session_rows]
        document_refs = [_document_ref_from_row(row) for row in document_rows]
        task_refs = [_task_ref_from_row(row) for row in task_rows]

        effectiveness_payload: dict[str, Any] = {}
        failure_payload: dict[str, Any] = {}
        try:
            effectiveness_payload = await get_workflow_effectiveness(
                ports.storage.db,
                scope.project,
                feature_id=feature_id,
                limit=20,
                offset=0,
            )
        except Exception:
            partial = True

        try:
            failure_payload = await detect_failure_patterns(
                ports.storage.db,
                scope.project,
                feature_id=feature_id,
                limit=20,
                offset=0,
            )
        except Exception:
            partial = True

        total_cost = round(sum(ref.total_cost for ref in session_refs), 6)
        total_tokens = sum(ref.total_tokens for ref in session_refs)
        timeline = _timeline_data(session_rows)
        key_metrics = KeyMetrics(
            total_cost=total_cost,
            total_tokens=total_tokens,
            session_count=len(session_refs),
            iteration_count=len(session_refs),
        )

        turning_points: list[TurningPoint] = []
        if session_refs:
            turning_points.append(
                TurningPoint(
                    timestamp=session_refs[0].started_at,
                    event="first_session_started",
                    impact="Initial implementation work began.",
                    evidence_refs=[session_refs[0].session_id],
                )
            )
            successful = next(
                (ref for ref in session_refs if str(ref.status).lower() in {"completed", "done", "success"}),
                None,
            )
            if successful is not None:
                turning_points.append(
                    TurningPoint(
                        timestamp=successful.ended_at or successful.started_at,
                        event="first_successful_session",
                        impact="A successful session established a working path forward.",
                        evidence_refs=[successful.session_id],
                    )
                )

        workflow_observations = [
            WorkflowObservation(
                workflow_id=str(item.get("scopeId") or item.get("id") or ""),
                workflow_name=str(item.get("scopeLabel") or item.get("scopeId") or ""),
                frequency=int(item.get("sampleSize") or 0),
                effectiveness_score=_safe_float(item.get("successScore")),
                notes=f"Observed {int(item.get('sampleSize') or 0)} sessions with success score {_safe_float(item.get('successScore')):.2f}.",
                evidence_refs=[],
            )
            for item in effectiveness_payload.get("items", [])
            if str(item.get("scopeType") or "") in {"workflow", "effective_workflow"}
        ][:5]

        bottlenecks = [
            Bottleneck(
                description=str(item.get("title") or item.get("patternType") or ""),
                cost_impact=_safe_float(item.get("averageRiskScore")),
                sessions_affected=list(item.get("sessionIds") or []),
                evidence_refs=list(item.get("sessionIds") or []),
            )
            for item in failure_payload.get("items", [])
            if isinstance(item, dict)
        ][:5]

        successful_patterns = [
            observation.workflow_name
            for observation in workflow_observations
            if observation.effectiveness_score >= 0.7
        ]
        lessons_learned = []
        if successful_patterns:
            lessons_learned.append(f"Repeatable success was concentrated in: {', '.join(successful_patterns)}.")
        if bottlenecks:
            lessons_learned.append(f"The largest bottleneck was: {bottlenecks[0].description}.")
        if not lessons_learned:
            lessons_learned.append("Insufficient execution evidence was available to derive strong lessons.")

        status = "ok"
        if partial:
            status = "partial"

        return AARReportDTO(
            status=status,
            feature_id=feature_id,
            feature_slug=_feature_slug(feature_row),
            scope_statement=(
                f"Feature {_feature_slug(feature_row)} spans {len(document_refs)} documents, "
                f"{len(task_refs)} tasks, and {len(session_refs)} sessions."
            ),
            timeline=timeline,
            key_metrics=key_metrics,
            turning_points=turning_points,
            workflow_observations=workflow_observations,
            bottlenecks=bottlenecks,
            successful_patterns=successful_patterns,
            lessons_learned=lessons_learned,
            evidence_links=[
                *[ref.session_id for ref in session_refs],
                *[ref.file_path for ref in document_refs if ref.file_path],
            ],
            data_freshness=derive_data_freshness(
                feature_row.get("updated_at") or feature_row.get("updatedAt"),
                *[row.get("updated_at") or row.get("updatedAt") or row.get("started_at") or row.get("startedAt") for row in session_rows],
                *[row.get("updated_at") or row.get("updatedAt") for row in document_rows],
                *[row.get("updated_at") or row.get("updatedAt") for row in task_rows],
                effectiveness_payload.get("generatedAt"),
                failure_payload.get("generatedAt"),
            ),
            source_refs=collect_source_refs(
                feature_id,
                [ref.session_id for ref in session_refs],
                [ref.document_id for ref in document_refs],
                [ref.task_id for ref in task_refs],
            ),
        )
