"""Application services for analytics read paths."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports import CorePorts
from backend.application.services.common import resolve_project
from backend.model_identity import canonical_model_name


def _coerce_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _session_usage_metrics(row: dict[str, Any]) -> dict[str, float | int]:
    token_input = _coerce_int(row.get("tokens_in") or row.get("tokensIn"))
    token_output = _coerce_int(row.get("tokens_out") or row.get("tokensOut"))
    model_io_tokens = _coerce_int(row.get("model_io_tokens") or row.get("modelIOTokens"))
    if model_io_tokens <= 0:
        model_io_tokens = token_input + token_output
    cache_creation_input_tokens = _coerce_int(
        row.get("cache_creation_input_tokens") or row.get("cacheCreationInputTokens")
    )
    cache_read_input_tokens = _coerce_int(
        row.get("cache_read_input_tokens") or row.get("cacheReadInputTokens")
    )
    cache_input_tokens = _coerce_int(row.get("cache_input_tokens") or row.get("cacheInputTokens"))
    if cache_input_tokens <= 0:
        cache_input_tokens = cache_creation_input_tokens + cache_read_input_tokens
    observed_tokens = _coerce_int(row.get("observed_tokens") or row.get("observedTokens"))
    if observed_tokens <= 0:
        observed_tokens = model_io_tokens + cache_input_tokens
    if observed_tokens <= 0:
        observed_tokens = token_input + token_output
    tool_reported_tokens = _coerce_int(row.get("tool_reported_tokens") or row.get("toolReportedTokens"))
    return {
        "tokenInput": token_input,
        "tokenOutput": token_output,
        "modelIOTokens": model_io_tokens,
        "cacheInputTokens": cache_input_tokens,
        "observedTokens": observed_tokens,
        "toolReportedTokens": tool_reported_tokens,
    }


class AnalyticsOverviewService:
    async def get_overview(
        self,
        context: RequestContext,
        ports: CorePorts,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        project = resolve_project(context, ports)
        if project is None:
            return {"kpis": {}, "generatedAt": datetime.now(timezone.utc).isoformat()}

        analytics_repo = ports.storage.analytics()
        task_repo = ports.storage.tasks()
        session_repo = ports.storage.sessions()

        latest = await analytics_repo.get_latest_entries(
            project.id,
            [
                "session_cost",
                "session_tokens",
                "session_count",
                "session_duration",
                "task_velocity",
                "task_completion_pct",
                "tool_call_count",
                "tool_success_rate",
                "feature_progress",
            ],
        )
        task_stats = await task_repo.get_project_stats(project.id)
        session_stats = await session_repo.get_project_stats(project.id)
        session_filters: dict[str, Any] = {"include_subagents": True}
        if start:
            session_filters["start_date"] = start
        if end:
            session_filters["end_date"] = end
        recent_sessions = await session_repo.list_paginated(0, 250, project.id, "started_at", "desc", session_filters)

        model_counts: dict[str, int] = defaultdict(int)
        for row in recent_sessions:
            model = canonical_model_name(str(row.get("model") or "").strip())
            if model:
                model_counts[model] += 1
        top_models = [
            {"name": name, "usage": count}
            for name, count in sorted(model_counts.items(), key=lambda item: item[1], reverse=True)[:8]
        ]

        context_rows = [row for row in recent_sessions if _coerce_int(row.get("current_context_tokens")) > 0]
        avg_context_utilization_pct = round(
            sum(_coerce_float(row.get("context_utilization_pct")) for row in context_rows) / len(context_rows),
            2,
        ) if context_rows else 0.0

        return {
            "kpis": {
                "sessionCost": float(session_stats.get("cost", latest.get("session_cost", 0.0))),
                "sessionTokens": int(session_stats.get("tokens", latest.get("session_tokens", 0))),
                "sessionCount": int(session_stats.get("count", latest.get("session_count", 0))),
                "sessionDurationAvg": float(session_stats.get("duration", latest.get("session_duration", 0.0))),
                "modelIOTokens": sum(int(_session_usage_metrics(row)["modelIOTokens"]) for row in recent_sessions),
                "cacheInputTokens": sum(int(_session_usage_metrics(row)["cacheInputTokens"]) for row in recent_sessions),
                "observedTokens": sum(int(_session_usage_metrics(row)["observedTokens"]) for row in recent_sessions),
                "toolReportedTokens": sum(int(_session_usage_metrics(row)["toolReportedTokens"]) for row in recent_sessions),
                "contextSessionCount": len(context_rows),
                "avgContextUtilizationPct": avg_context_utilization_pct,
                "taskVelocity": int(latest.get("task_velocity", task_stats.get("completed", 0))),
                "taskCompletionPct": float(latest.get("task_completion_pct", task_stats.get("completion_pct", 0.0))),
                "featureProgress": float(latest.get("feature_progress", 0.0)),
                "toolCallCount": int(latest.get("tool_call_count", 0)),
                "toolSuccessRate": float(latest.get("tool_success_rate", 0.0)),
            },
            "topModels": top_models,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "range": {"start": start or "", "end": end or ""},
        }
