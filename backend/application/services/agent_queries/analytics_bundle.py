"""Transport-neutral analytics overview bundle query service (T5-004).

Composes above-fold analytics data (KPIs + top models) into a single
``AnalyticsOverviewBundleDTO``.  Detailed tab breakdowns (workflow
effectiveness, session intelligence, etc.) remain as separate lazy endpoints.

Delegates to the existing ``AnalyticsOverviewService`` — no new DB queries
are introduced.  Wrapped with ``@memoized_query`` and emits an OTEL span.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.analytics import AnalyticsOverviewService
from backend.observability import otel

from ._filters import collect_source_refs, resolve_project_scope
from .cache import memoized_query
from .models import (
    AnalyticsKPIsDTO,
    AnalyticsOverviewBundleDTO,
    AnalyticsTopModelDTO,
)

__all__ = ["AnalyticsBundleQueryService"]

logger = logging.getLogger(__name__)

# Module-level singleton reused across requests (mirrors analytics_router.py pattern)
_analytics_overview_service = AnalyticsOverviewService()


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


def _analytics_bundle_params(
    self: Any,
    context: RequestContext,
    ports: CorePorts,
    project_id_override: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    return {"project_id_override": project_id_override}


class AnalyticsBundleQueryService:
    """Transport-neutral analytics overview bundle query service (T5-004).

    Returns above-fold KPIs and model usage.  Tab-level detail (session
    intelligence, workflow effectiveness, etc.) stays lazy.
    """

    @memoized_query("analytics_overview_bundle", param_extractor=_analytics_bundle_params)
    async def get_analytics_overview_bundle(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        project_id_override: str | None = None,
    ) -> AnalyticsOverviewBundleDTO:
        """Return the Analytics above-fold bundle.

        Composes:
        - ``kpis``: session cost/token/count KPIs plus task and tool metrics.
        - ``top_models``: model usage breakdown (up to 8 entries).
        - ``range``: effective date range used for KPI computation.

        Failures in the underlying analytics read degrade the bundle to
        ``status="partial"`` rather than raising.
        """
        with otel.start_span(
            "ccdash.analytics.overview.bundle",
            {"project_id": project_id_override or ""},
        ):
            scope = resolve_project_scope(context, ports, project_id_override)
            if scope is None:
                return AnalyticsOverviewBundleDTO(
                    status="error",
                    project_id=str(project_id_override or ""),
                    source_refs=[],
                )

            project = scope.project
            partial = False
            source_refs = collect_source_refs(project.id)

            raw: dict[str, Any] = {}
            try:
                raw = await _analytics_overview_service.get_overview(context, ports)
                source_refs = collect_source_refs(source_refs, "analytics")
            except Exception:
                logger.warning(
                    "AnalyticsBundleQueryService: failed to load analytics overview for project %s",
                    project.id,
                )
                partial = True

            kpis_raw: dict[str, Any] = raw.get("kpis", {}) if isinstance(raw, dict) else {}
            top_models_raw: list[Any] = raw.get("topModels", []) if isinstance(raw, dict) else []
            date_range: dict[str, str] = raw.get("range", {}) if isinstance(raw, dict) else {}

            kpis = AnalyticsKPIsDTO(
                session_count=_safe_int(kpis_raw.get("sessionCount")),
                session_cost=_safe_float(kpis_raw.get("sessionCost")),
                session_tokens=_safe_int(kpis_raw.get("sessionTokens")),
                session_duration_avg=_safe_float(kpis_raw.get("sessionDurationAvg")),
                task_velocity=_safe_int(kpis_raw.get("taskVelocity")),
                task_completion_pct=_safe_float(kpis_raw.get("taskCompletionPct")),
                feature_progress=_safe_float(kpis_raw.get("featureProgress")),
                tool_call_count=_safe_int(kpis_raw.get("toolCallCount")),
                tool_success_rate=_safe_float(kpis_raw.get("toolSuccessRate")),
                model_io_tokens=_safe_int(kpis_raw.get("modelIOTokens")),
                cache_input_tokens=_safe_int(kpis_raw.get("cacheInputTokens")),
                observed_tokens=_safe_int(kpis_raw.get("observedTokens")),
                context_session_count=_safe_int(kpis_raw.get("contextSessionCount")),
                avg_context_utilization_pct=_safe_float(kpis_raw.get("avgContextUtilizationPct")),
                tool_reported_tokens=_safe_int(kpis_raw.get("toolReportedTokens")),
            )

            top_models = [
                AnalyticsTopModelDTO(
                    name=str(item.get("name") or ""),
                    usage=_safe_int(item.get("usage")),
                )
                for item in top_models_raw
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            ]

            return AnalyticsOverviewBundleDTO(
                status="partial" if partial else "ok",
                project_id=project.id,
                kpis=kpis,
                top_models=top_models,
                range=date_range,
                source_refs=source_refs,
            )
