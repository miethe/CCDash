"""Workflow diagnostics service built on existing registry/effectiveness helpers."""
from __future__ import annotations

from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.services.workflow_effectiveness import detect_failure_patterns, get_workflow_effectiveness
import logging

from backend.services.workflow_registry import fetch_workflow_details, list_workflow_registry
from backend.observability import otel

_logger = logging.getLogger(__name__)

from ._filters import collect_source_refs, derive_data_freshness, resolve_project_scope
from .cache import memoized_query
from .models import SessionRef, WorkflowDiagnostic, WorkflowDiagnosticsDTO


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _session_ref_from_registry_evidence(row: dict[str, Any]) -> SessionRef:
    return SessionRef(
        session_id=str(row.get("sessionId") or ""),
        feature_id=str(row.get("featureId") or ""),
        root_session_id="",
        title=str(row.get("title") or ""),
        status=str(row.get("status") or ""),
        started_at=str(row.get("startedAt") or ""),
        ended_at=str(row.get("endedAt") or ""),
        model="",
        total_cost=0.0,
        total_tokens=0,
        workflow_refs=[str(row.get("workflowRef") or "")] if str(row.get("workflowRef") or "").strip() else [],
        duration_seconds=0.0,
        tool_names=[],
        source_ref=str(row.get("sessionId") or ""),
    )


def _workflow_diagnostics_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    feature_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    return {"feature_id": feature_id}


class WorkflowDiagnosticsQueryService:
    """Aggregate workflow effectiveness and failure patterns for agents."""

    @memoized_query("workflow_diagnostics", param_extractor=_workflow_diagnostics_params)
    async def get_diagnostics(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str | None = None,
    ) -> WorkflowDiagnosticsDTO:
        scope = resolve_project_scope(context, ports)
        if scope is None:
            return WorkflowDiagnosticsDTO(
                status="error",
                project_id="",
                feature_id=feature_id,
                source_refs=collect_source_refs(feature_id),
            )

        partial = False
        successful_sources = 0
        registry_payload: dict[str, Any] = {}
        effectiveness_payload: dict[str, Any] = {}
        failure_payload: dict[str, Any] = {}

        try:
            registry_payload = await list_workflow_registry(ports.storage.db, scope.project, limit=200, offset=0)
            successful_sources += 1
        except Exception:
            partial = True

        try:
            effectiveness_payload = await get_workflow_effectiveness(
                ports.storage.db,
                scope.project,
                feature_id=feature_id,
                limit=200,
                offset=0,
            )
            successful_sources += 1
        except Exception:
            partial = True

        try:
            failure_payload = await detect_failure_patterns(
                ports.storage.db,
                scope.project,
                feature_id=feature_id,
                limit=200,
                offset=0,
            )
            successful_sources += 1
        except Exception:
            partial = True

        diagnostics: dict[str, WorkflowDiagnostic] = {}

        for row in effectiveness_payload.get("items", []):
            scope_type = str(row.get("scopeType") or "")
            if scope_type not in {"workflow", "effective_workflow"}:
                continue
            workflow_id = str(row.get("scopeId") or row.get("id") or "")
            diagnostics[workflow_id] = WorkflowDiagnostic(
                workflow_id=workflow_id,
                workflow_name=str(row.get("scopeLabel") or workflow_id),
                effectiveness_score=_safe_float(row.get("successScore")),
                session_count=_safe_int(row.get("sampleSize")),
                success_count=round(_safe_int(row.get("sampleSize")) * _safe_float(row.get("successScore"))),
                failure_count=max(
                    _safe_int(row.get("sampleSize")) - round(_safe_int(row.get("sampleSize")) * _safe_float(row.get("successScore"))),
                    0,
                ),
                cost_efficiency=_safe_float(row.get("efficiencyScore")),
            )

        registry_items = registry_payload.get("items", [])

        # --- batch-fetch all registry details in one pass (eliminates N+1) ---
        registry_ids: list[str] = []
        for row in registry_items:
            identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
            workflow_id = str(
                identity.get("resolvedWorkflowId")
                or identity.get("registryId")
                or row.get("id")
                or ""
            )
            registry_ids.append(str(row.get("id") or workflow_id))

        try:
            batch_details = await fetch_workflow_details(
                ports.storage.db,
                scope.project,
                registry_ids,
            )
            otel.record_workflow_detail_batch_rows(len(batch_details))
        except Exception:
            batch_details = []
            partial = True

        fetched_ids = {str(d.get("id") or ""): d for d in batch_details}

        missing = [rid for rid in registry_ids if rid not in fetched_ids]
        if missing:
            _logger.warning(
                "fetch_workflow_details: %d registry IDs not found in detail store: %s",
                len(missing),
                missing,
            )

        for row in registry_items:
            identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
            workflow_id = str(
                identity.get("resolvedWorkflowId")
                or identity.get("registryId")
                or row.get("id")
                or ""
            )
            diagnostic = diagnostics.setdefault(
                workflow_id,
                WorkflowDiagnostic(
                    workflow_id=workflow_id,
                    workflow_name=str(identity.get("displayLabel") or workflow_id),
                    session_count=_safe_int(row.get("sampleSize")),
                ),
            )
            if not diagnostic.workflow_name:
                diagnostic.workflow_name = str(identity.get("displayLabel") or workflow_id)
            if not diagnostic.session_count:
                diagnostic.session_count = _safe_int(row.get("sampleSize"))

            detail = fetched_ids.get(str(row.get("id") or workflow_id))
            if isinstance(detail, dict):
                diagnostic.representative_sessions = [
                    _session_ref_from_registry_evidence(item)
                    for item in detail.get("representativeSessions", [])[:3]
                    if isinstance(item, dict)
                ]

        for row in failure_payload.get("items", []):
            workflow_id = str(row.get("scopeId") or "")
            diagnostic = diagnostics.setdefault(
                workflow_id,
                WorkflowDiagnostic(workflow_id=workflow_id, workflow_name=workflow_id),
            )
            title = str(row.get("title") or row.get("patternType") or "").strip()
            if title:
                diagnostic.common_failures.append(title)

        workflows = list(diagnostics.values())
        top_performers = sorted(workflows, key=lambda item: item.effectiveness_score, reverse=True)[:5]
        problem_workflows = sorted(
            workflows,
            key=lambda item: (item.failure_count, -item.effectiveness_score),
            reverse=True,
        )[:5]

        status = "ok"
        if successful_sources == 0:
            status = "error"
        elif partial:
            status = "partial"

        return WorkflowDiagnosticsDTO(
            status=status,
            project_id=scope.project.id,
            feature_id=feature_id,
            workflows=workflows,
            top_performers=top_performers,
            problem_workflows=problem_workflows,
            data_freshness=derive_data_freshness(
                registry_payload.get("generatedAt"),
                effectiveness_payload.get("generatedAt"),
                failure_payload.get("generatedAt"),
            ),
            source_refs=collect_source_refs(
                scope.project.id,
                feature_id,
                [item.workflow_id for item in workflows],
                [ref.session_id for item in workflows for ref in item.representative_sessions],
            ),
        )
