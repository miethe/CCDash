"""Analytics router for overview, rollups, correlation, and exports."""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from backend.models import AnalyticsMetric, AlertConfig, Notification
from backend.project_manager import project_manager
from backend.db import connection
from backend.db.factory import (
    get_analytics_repository,
    get_alert_config_repository,
    get_entity_link_repository,
    get_feature_repository,
    get_session_repository,
    get_task_repository,
)

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _safe_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _safe_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _parse_iso(value: str | None) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _bucket_ts(ts: datetime, period: str) -> str:
    if period == "hourly":
        return ts.replace(minute=0, second=0, microsecond=0).isoformat()
    if period == "daily":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    if period == "weekly":
        start = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        start = start - timedelta(days=start.weekday())
        return start.isoformat()
    return ts.isoformat()


def _rollup_mode(metric: str) -> str:
    lowered = metric.lower()
    if lowered.endswith("_pct") or lowered.endswith("_rate") or "progress" in lowered or "duration" in lowered:
        return "avg"
    return "sum"


class AlertConfigCreate(BaseModel):
    id: str | None = None
    name: str
    metric: str
    operator: str
    threshold: float
    isActive: bool = True
    scope: str = "session"


class AlertConfigPatch(BaseModel):
    name: str | None = None
    metric: str | None = None
    operator: str | None = None
    threshold: float | None = None
    isActive: bool | None = None
    scope: str | None = None


@analytics_router.get("/metrics", response_model=list[AnalyticsMetric])
async def get_metrics():
    """Legacy metrics endpoint."""
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_analytics_repository(db)

    types = [
        "session_cost", "session_tokens", "session_count",
        "task_velocity", "task_completion_pct",
    ]
    latest = await repo.get_latest_entries(project.id, types)
    return [
        AnalyticsMetric(name="Total Cost", value=round(latest.get("session_cost", 0.0), 4), unit="$"),
        AnalyticsMetric(name="Total Tokens", value=int(latest.get("session_tokens", 0)), unit="tokens"),
        AnalyticsMetric(name="Sessions", value=int(latest.get("session_count", 0)), unit="count"),
        AnalyticsMetric(name="Tasks Done", value=int(latest.get("task_velocity", 0)), unit="count"),
        AnalyticsMetric(name="Completion", value=round(latest.get("task_completion_pct", 0.0), 1), unit="%"),
    ]


@analytics_router.get("/overview")
async def get_overview(
    start: str | None = None,
    end: str | None = None,
):
    project = project_manager.get_active_project()
    if not project:
        return {"kpis": {}, "generatedAt": datetime.now(timezone.utc).isoformat()}

    db = await connection.get_connection()
    analytics_repo = get_analytics_repository(db)
    task_repo = get_task_repository(db)
    session_repo = get_session_repository(db)

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
    session_filters: dict[str, Any] = {"include_subagents": True}
    if start:
        session_filters["start_date"] = start
    if end:
        session_filters["end_date"] = end
    recent_sessions = await session_repo.list_paginated(0, 250, project.id, "started_at", "desc", session_filters)

    model_counts: dict[str, int] = defaultdict(int)
    for row in recent_sessions:
        model = str(row.get("model") or "").strip()
        if model:
            model_counts[model] += 1
    top_models = [
        {"name": name, "usage": count}
        for name, count in sorted(model_counts.items(), key=lambda item: item[1], reverse=True)[:8]
    ]

    return {
        "kpis": {
            "sessionCost": float(latest.get("session_cost", 0.0)),
            "sessionTokens": int(latest.get("session_tokens", 0)),
            "sessionCount": int(latest.get("session_count", 0)),
            "sessionDurationAvg": float(latest.get("session_duration", 0.0)),
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


@analytics_router.get("/series")
async def get_series(
    metric: str = Query(..., description="Metric type ID"),
    period: str = Query("daily", pattern="^(point|hourly|daily|weekly)$"),
    start: str | None = None,
    end: str | None = None,
    group_by: str | None = None,
    session_id: str | None = None,
    offset: int = 0,
    limit: int = 500,
):
    project = project_manager.get_active_project()
    if not project:
        return {"items": [], "total": 0, "offset": offset, "limit": limit}

    db = await connection.get_connection()
    session_repo = get_session_repository(db)
    analytics_repo = get_analytics_repository(db)

    if metric == "session_tokens" and session_id:
        logs = await session_repo.get_logs(session_id)
        points: list[dict[str, Any]] = []
        cumulative = 0
        for log in logs:
            metadata = _safe_json(log.get("metadata_json"))
            in_tokens = int(metadata.get("inputTokens") or 0)
            out_tokens = int(metadata.get("outputTokens") or 0)
            delta = max(0, in_tokens + out_tokens)
            if delta == 0:
                continue
            cumulative += delta
            points.append({
                "captured_at": log.get("timestamp") or "",
                "value": cumulative,
                "metadata": {
                    "stepTokens": delta,
                    "inputTokens": in_tokens,
                    "outputTokens": out_tokens,
                    "agent": log.get("agent_name") or "",
                },
            })
        return {"items": points[offset:offset + limit], "total": len(points), "offset": offset, "limit": limit}

    raw_points = await analytics_repo.get_trends(project.id, metric, period="point", start=start, end=end)
    if period == "point" and not group_by:
        total = len(raw_points)
        return {"items": raw_points[offset:offset + limit], "total": total, "offset": offset, "limit": limit}

    mode = _rollup_mode(metric)
    aggregates: dict[tuple[str, str], dict[str, Any]] = {}
    for point in raw_points:
        ts = _parse_iso(str(point.get("captured_at") or ""))
        if not ts:
            continue
        if start and ts < (_parse_iso(start) or ts):
            continue
        if end and ts > (_parse_iso(end) or ts):
            continue
        bucket = _bucket_ts(ts, period)
        metadata = _safe_json(point.get("metadata"))
        group_value = str(metadata.get(group_by or "") or "all") if group_by else "all"
        key = (bucket, group_value)
        current = aggregates.get(key)
        if not current:
            aggregates[key] = {
                "captured_at": bucket,
                "value_sum": 0.0,
                "value_count": 0,
                "group": group_value,
            }
            current = aggregates[key]
        current["value_sum"] += float(point.get("value") or 0.0)
        current["value_count"] += 1

    items: list[dict[str, Any]] = []
    for row in aggregates.values():
        value = row["value_sum"]
        if mode == "avg" and row["value_count"] > 0:
            value = value / row["value_count"]
        payload = {"captured_at": row["captured_at"], "value": value}
        if group_by:
            payload["metadata"] = {group_by: row["group"]}
        items.append(payload)
    items.sort(key=lambda row: str(row.get("captured_at") or ""))
    total = len(items)
    return {"items": items[offset:offset + limit], "total": total, "offset": offset, "limit": limit}


@analytics_router.get("/breakdown")
async def get_breakdown(
    dimension: str = Query("model", pattern="^(model|model_family|session_type|tool|agent|skill|feature)$"),
    start: str | None = None,
    end: str | None = None,
    offset: int = 0,
    limit: int = 100,
):
    project = project_manager.get_active_project()
    if not project:
        return {"items": [], "total": 0, "offset": offset, "limit": limit}

    db = await connection.get_connection()
    session_repo = get_session_repository(db)
    link_repo = get_entity_link_repository(db)

    filters: dict[str, Any] = {"include_subagents": True}
    if start:
        filters["start_date"] = start
    if end:
        filters["end_date"] = end
    sessions = await session_repo.list_paginated(0, 2000, project.id, "started_at", "desc", filters)

    counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "tokens": 0, "cost": 0.0})
    if dimension in {"model", "model_family", "session_type"}:
        for row in sessions:
            if dimension == "model":
                key = str(row.get("model") or "Unknown")
            elif dimension == "session_type":
                key = str(row.get("session_type") or "session")
            else:
                model = str(row.get("model") or "").lower()
                if "opus" in model:
                    key = "opus"
                elif "sonnet" in model:
                    key = "sonnet"
                elif "haiku" in model:
                    key = "haiku"
                elif model:
                    key = model.split("-", 1)[0]
                else:
                    key = "unknown"
            counts[key]["count"] += 1
            counts[key]["tokens"] += int(row.get("tokens_in") or 0) + int(row.get("tokens_out") or 0)
            counts[key]["cost"] += float(row.get("total_cost") or 0.0)
    elif dimension == "tool":
        for row in sessions:
            tools = await session_repo.get_tool_usage(str(row.get("id") or ""))
            for tool in tools:
                key = str(tool.get("tool_name") or "unknown")
                counts[key]["count"] += int(tool.get("call_count") or 0)
    elif dimension in {"agent", "skill"}:
        for row in sessions:
            logs = await session_repo.get_logs(str(row.get("id") or ""))
            for log in logs:
                if dimension == "agent":
                    key = str(log.get("agent_name") or "").strip()
                    if not key:
                        continue
                    counts[key]["count"] += 1
                else:
                    metadata = _safe_json(log.get("metadata_json"))
                    if str(log.get("tool_name") or "") == "Skill":
                        key = str(metadata.get("toolLabel") or metadata.get("skill") or "").strip()
                        if key:
                            counts[key]["count"] += 1
    else:
        # feature correlation count via feature -> session links
        for row in sessions:
            session_id = str(row.get("id") or "")
            if not session_id:
                continue
            links = await link_repo.get_links_for("session", session_id, "related")
            for link in links:
                if link.get("source_type") != "feature":
                    continue
                feature_id = str(link.get("source_id") or "").strip()
                if not feature_id:
                    continue
                counts[feature_id]["count"] += 1

    items = [
        {"name": name, **values}
        for name, values in sorted(counts.items(), key=lambda item: item[1]["count"], reverse=True)
    ]
    total = len(items)
    return {"items": items[offset:offset + limit], "total": total, "offset": offset, "limit": limit}


@analytics_router.get("/correlation")
async def get_correlation(
    offset: int = 0,
    limit: int = 100,
):
    project = project_manager.get_active_project()
    if not project:
        return {"items": [], "total": 0, "offset": offset, "limit": limit}

    db = await connection.get_connection()
    session_repo = get_session_repository(db)
    link_repo = get_entity_link_repository(db)
    feature_repo = get_feature_repository(db)

    sessions = await session_repo.list_paginated(0, 1200, project.id, "started_at", "desc", {"include_subagents": True})
    items: list[dict[str, Any]] = []
    for row in sessions:
        session_id = str(row.get("id") or "")
        links = await link_repo.get_links_for("session", session_id, "related")
        feature_links = [link for link in links if link.get("source_type") == "feature"]
        if not feature_links:
            items.append({
                "sessionId": session_id,
                "featureId": "",
                "featureName": "",
                "confidence": 0.0,
                "commitHash": row.get("git_commit_hash") or "",
                "model": row.get("model") or "",
                "status": row.get("status") or "",
                "startedAt": row.get("started_at") or "",
                "endedAt": row.get("ended_at") or "",
            })
            continue
        for link in feature_links:
            feature_id = str(link.get("source_id") or "")
            feature_row = await feature_repo.get_by_id(feature_id)
            metadata = _safe_json(link.get("metadata_json"))
            items.append({
                "sessionId": session_id,
                "featureId": feature_id,
                "featureName": (feature_row or {}).get("name", ""),
                "confidence": float(link.get("confidence") or 0.0),
                "linkStrategy": metadata.get("linkStrategy") or "",
                "commitHash": row.get("git_commit_hash") or "",
                "model": row.get("model") or "",
                "status": row.get("status") or "",
                "startedAt": row.get("started_at") or "",
                "endedAt": row.get("ended_at") or "",
            })

    total = len(items)
    return {"items": items[offset:offset + limit], "total": total, "offset": offset, "limit": limit}


@analytics_router.get("/alerts", response_model=list[AlertConfig])
async def get_alerts():
    db = await connection.get_connection()
    repo = get_alert_config_repository(db)
    project = project_manager.get_active_project()
    configs = await repo.list_all(project.id if project else None)
    return [
        AlertConfig(
            id=c["id"],
            name=c["name"],
            metric=c["metric"],
            operator=c["operator"],
            threshold=c["threshold"],
            isActive=bool(c["is_active"]),
            scope=c["scope"],
        )
        for c in configs
    ]


@analytics_router.post("/alerts", response_model=AlertConfig)
async def create_alert(payload: AlertConfigCreate):
    db = await connection.get_connection()
    repo = get_alert_config_repository(db)
    project = project_manager.get_active_project()
    alert_id = payload.id or f"alert-{uuid.uuid4().hex[:8]}"
    data = {
        "id": alert_id,
        "project_id": project.id if project else None,
        "name": payload.name,
        "metric": payload.metric,
        "operator": payload.operator,
        "threshold": payload.threshold,
        "is_active": payload.isActive,
        "scope": payload.scope,
    }
    await repo.upsert(data)
    return AlertConfig(
        id=alert_id,
        name=payload.name,
        metric=payload.metric,
        operator=payload.operator,
        threshold=payload.threshold,
        isActive=payload.isActive,
        scope=payload.scope,
    )


@analytics_router.patch("/alerts/{alert_id}", response_model=AlertConfig)
async def update_alert(alert_id: str, payload: AlertConfigPatch):
    db = await connection.get_connection()
    repo = get_alert_config_repository(db)
    project = project_manager.get_active_project()
    configs = await repo.list_all(project.id if project else None)
    current = next((c for c in configs if c.get("id") == alert_id), None)
    if not current:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    merged = {
        "id": alert_id,
        "project_id": current.get("project_id"),
        "name": payload.name if payload.name is not None else current.get("name", ""),
        "metric": payload.metric if payload.metric is not None else current.get("metric", ""),
        "operator": payload.operator if payload.operator is not None else current.get("operator", ">"),
        "threshold": payload.threshold if payload.threshold is not None else float(current.get("threshold") or 0.0),
        "is_active": payload.isActive if payload.isActive is not None else bool(current.get("is_active")),
        "scope": payload.scope if payload.scope is not None else current.get("scope", "session"),
    }
    await repo.upsert(merged)
    return AlertConfig(
        id=alert_id,
        name=str(merged["name"]),
        metric=str(merged["metric"]),
        operator=str(merged["operator"]),
        threshold=float(merged["threshold"]),
        isActive=bool(merged["is_active"]),
        scope=str(merged["scope"]),
    )


@analytics_router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str):
    db = await connection.get_connection()
    repo = get_alert_config_repository(db)
    await repo.delete(alert_id)
    return {"status": "ok", "id": alert_id}


@analytics_router.get("/notifications", response_model=list[Notification])
async def get_notifications():
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_session_repository(db)
    sessions = await repo.list_paginated(0, 5, project.id, sort_by="started_at", sort_order="desc")

    notifications: list[Notification] = []
    for i, s in enumerate(sessions):
        notifications.append(Notification(
            id=f"notif-{s['id']}",
            alertId="alert-cost",
            message=f"Session {s['id']}: Model={s['model']}, Cost=${s['total_cost']:.4f}",
            timestamp=s["started_at"] or "",
            isRead=i > 0,
        ))
    return notifications


@analytics_router.get("/trends")
async def get_trends(
    metric: str = Query(..., description="Metric type ID"),
    period: str = "daily",
    start: str | None = None,
    end: str | None = None,
):
    """Legacy trends endpoint."""
    payload = await get_series(metric=metric, period=period, start=start, end=end, group_by=None, session_id=None, offset=0, limit=500)
    return payload["items"]


@analytics_router.get("/export/prometheus")
async def export_prometheus():
    project = project_manager.get_active_project()
    if not project:
        return Response("", media_type="text/plain")

    db = await connection.get_connection()
    repo = get_analytics_repository(db)
    types = [
        "session_cost", "session_tokens", "session_count",
        "task_velocity", "task_completion_pct", "tool_call_count", "tool_success_rate",
    ]
    latest = await repo.get_latest_entries(project.id, types)

    lines = []
    for metric, value in latest.items():
        safe_name = f"ccdash_{metric}"
        lines.append(f"# TYPE {safe_name} gauge")
        lines.append(f'{safe_name}{{project="{project.id}"}} {value}')
    return Response("\n".join(lines) + "\n", media_type="text/plain")
