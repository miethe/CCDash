"""Project-level aggregate agent query service."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.analytics import AnalyticsOverviewService
from backend.application.services.session_intelligence import SessionIntelligenceReadService
from backend.services.workflow_registry import list_workflow_registry

from ._filters import collect_source_refs, derive_data_freshness, resolve_project_scope
from .cache import memoized_query
from .models import CostSummary, ProjectStatusDTO, SessionSummary, WorkflowSummary


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


def _session_summary_from_row(row: dict[str, Any]) -> SessionSummary:
    return SessionSummary(
        session_id=str(row.get("id") or row.get("sessionId") or ""),
        feature_id=str(row.get("feature_id") or row.get("featureId") or row.get("task_id") or row.get("taskId") or ""),
        root_session_id=str(row.get("root_session_id") or row.get("rootSessionId") or ""),
        title=str(row.get("title") or ""),
        status=str(row.get("status") or ""),
        started_at=str(row.get("started_at") or row.get("startedAt") or ""),
        ended_at=str(row.get("ended_at") or row.get("endedAt") or ""),
        model=str(row.get("model") or ""),
        total_cost=_safe_float(row.get("total_cost") or row.get("totalCost")),
        total_tokens=_safe_int(
            row.get("observed_tokens")
            or row.get("observedTokens")
            or row.get("model_io_tokens")
            or row.get("modelIOTokens")
            or row.get("tokens_in")
            or row.get("tokensIn")
        ),
        workflow_refs=[],
    )


def _workflow_summary_from_row(row: dict[str, Any]) -> WorkflowSummary:
    identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
    registry_id = str(
        row.get("id")
        or identity.get("resolvedWorkflowId")
        or identity.get("registryId")
        or ""
    )
    return WorkflowSummary(
        workflow_id=registry_id,
        workflow_name=str(
            identity.get("displayLabel")
            or identity.get("resolvedWorkflowLabel")
            or row.get("scopeLabel")
            or registry_id
        ),
        session_count=_safe_int(row.get("sampleSize") or row.get("sessionCount")),
        success_rate=_safe_float(
            (row.get("effectiveness") or {}).get("successScore")
            if isinstance(row.get("effectiveness"), dict)
            else row.get("successScore")
        ),
        last_observed_at=str(row.get("lastObservedAt") or row.get("generatedAt") or ""),
        representative_session_ids=[],
    )


def _project_status_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    project_id_override: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    return {"project_id_override": project_id_override}


class ProjectStatusQueryService:
    """Aggregate project health for agent-facing transports."""

    @memoized_query("project_status", param_extractor=_project_status_params)
    async def get_status(
        self,
        context: RequestContext,
        ports: CorePorts,
        project_id_override: str | None = None,
    ) -> ProjectStatusDTO:
        scope = resolve_project_scope(context, ports, project_id_override)
        if scope is None:
            return ProjectStatusDTO(
                status="error",
                project_id=str(project_id_override or ""),
                project_name="",
                source_refs=[],
            )

        project = scope.project
        partial = False
        successful_sources = 0

        feature_rows: list[dict[str, Any]] = []
        try:
            feature_rows = await ports.storage.features().list_all(project.id)
            successful_sources += 1
        except Exception:
            partial = True

        recent_sessions: list[SessionSummary] = []
        try:
            response = await SessionIntelligenceReadService().list_sessions(
                context,
                ports,
                include_subagents=True,
                offset=0,
                limit=10,
            )
            recent_sessions = [_session_summary_from_row(item.model_dump()) for item in response.items]
            successful_sources += 1
        except Exception:
            try:
                rows = await ports.storage.sessions().list_paginated(
                    0,
                    10,
                    project.id,
                    "started_at",
                    "desc",
                    {"include_subagents": True},
                )
                recent_sessions = [_session_summary_from_row(row) for row in rows]
                successful_sources += 1
                partial = True
            except Exception:
                partial = True

        analytics_payload: dict[str, Any] = {}
        try:
            analytics_payload = await AnalyticsOverviewService().get_overview(context, ports)
            successful_sources += 1
        except Exception:
            partial = True

        top_workflows: list[WorkflowSummary] = []
        try:
            registry_payload = await list_workflow_registry(ports.storage.db, project, limit=5, offset=0)
            top_workflows = [_workflow_summary_from_row(item) for item in registry_payload.get("items", [])]
            successful_sources += 1
        except Exception:
            partial = True

        sync_freshness: datetime | None = None
        try:
            sync_rows = await ports.storage.sync_state().list_all(project.id)
            if sync_rows:
                sync_freshness = derive_data_freshness(
                    *[row.get("last_synced") or row.get("file_mtime") for row in sync_rows]
                )
            successful_sources += 1
        except Exception:
            partial = True

        feature_counts = dict(Counter(str(row.get("status") or "unknown") for row in feature_rows))
        blocked_features = [
            str(row.get("id") or "")
            for row in feature_rows
            if str(row.get("status") or "").strip().lower() == "blocked"
        ]

        analytics_kpis = analytics_payload.get("kpis", {}) if isinstance(analytics_payload, dict) else {}
        cost_summary = CostSummary(
            total_cost=_safe_float(analytics_kpis.get("sessionCost")),
            total_tokens=_safe_int(analytics_kpis.get("sessionTokens")),
            by_model={
                str(item.get("name") or ""): _safe_float(item.get("usage"))
                for item in analytics_payload.get("topModels", [])
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            } if isinstance(analytics_payload, dict) else {},
            by_workflow={},
        )

        status = "ok"
        if successful_sources == 0:
            status = "error"
        elif partial:
            status = "partial"

        data_freshness = derive_data_freshness(
            sync_freshness,
            analytics_payload.get("generatedAt") if isinstance(analytics_payload, dict) else None,
            *[session.started_at or session.ended_at for session in recent_sessions],
            *[row.get("updated_at") or row.get("updatedAt") for row in feature_rows],
        )

        return ProjectStatusDTO(
            project_id=project.id,
            project_name=project.name,
            status=status,
            feature_counts=feature_counts,
            recent_sessions=recent_sessions,
            cost_last_7d=cost_summary,
            top_workflows=top_workflows,
            sync_freshness=sync_freshness,
            blocked_features=blocked_features,
            data_freshness=data_freshness,
            source_refs=collect_source_refs(
                project.id,
                [session.session_id for session in recent_sessions],
                blocked_features,
                [workflow.workflow_id for workflow in top_workflows],
            ),
        )
