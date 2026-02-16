"""Analytics router for trends, metrics, and exports."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from backend.models import (
    AnalyticsMetric, AlertConfig, Notification,
)
from backend.project_manager import project_manager
from backend.db import connection
from backend.db.factory import (
    get_analytics_repository,
    get_alert_config_repository,
    get_session_repository,
)

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@analytics_router.get("/metrics", response_model=list[AnalyticsMetric])
async def get_metrics():
    """Return latest cached metrics for the dashboard."""
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_analytics_repository(db)
    
    # metrics to fetch
    types = [
        "session_cost", "session_tokens", "session_count", 
        "task_velocity", "task_completion_pct"
    ]
    latest = await repo.get_latest_entries(project.id, types)
    
    # If no cached metrics (sync hasn't run), fallback or return zeros
    # Ideally frontend handles this, but let's provide safe defaults
    
    return [
        AnalyticsMetric(name="Total Cost", value=round(latest.get("session_cost", 0.0), 4), unit="$"),
        AnalyticsMetric(name="Total Tokens", value=int(latest.get("session_tokens", 0)), unit="tokens"),
        AnalyticsMetric(name="Sessions", value=int(latest.get("session_count", 0)), unit="count"),
        AnalyticsMetric(name="Tasks Done", value=int(latest.get("task_velocity", 0)), unit="count"),
        # We don't have "Total Tasks" in the simple snapshot map currently, 
        # but we could add it or just show completion %
        AnalyticsMetric(name="Completion", value=round(latest.get("task_completion_pct", 0.0), 1), unit="%"),
    ]


@analytics_router.get("/trends")
async def get_trends(
    metric: str = Query(..., description="Metric type ID (e.g. session_cost)"),
    period: str = "daily",
    start: str | None = None,
    end: str | None = None,
):
    """Get time-series data for a specific metric."""
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_analytics_repository(db)
    
    # If period is 'daily', we might need to aggregate the 'point' data in SQL 
    # if our snapshotter only stores 'point'.
    # For MVP, the snapshotter stores 'point'. 
    # If the user asks for 'daily', we should probably group by day.
    # But SqliteAnalyticsRepository.get_trends filters by `period` column.
    # Our snapshotter currently inserts with period='point'.
    # So for now, we just return the 'point' data and let frontend visualize it, 
    # OR we update the repository to handle on-the-fly aggregation.
    # Let's request 'point' data by default if that's what we have.
    
    # If the UI requests 'daily', but we only have 'point', we should return 'point' or empty?
    # Better: return the raw points and let the chart handle it, or implement aggregation.
    # For Phase 4, let's just return the raw data and ignore 'period' matching strictness if needed,
    # OR better, update `_capture_analytics` to store aggregated data? 
    # No, aggregation is best done on read for flexibility, or periodic jobs.
    # Let's pass 'point' recursively if no data found for requested period?
    # Actually, `get_trends` in repo simply queries `WHERE period = ?`.
    # Let's force period='point' for now since that's what we populate.
    
    trends = await repo.get_trends(project.id, metric, period="point", start=start, end=end)
    return trends


@analytics_router.get("/alerts", response_model=list[AlertConfig])
async def get_alerts():
    """Return alert configurations from DB."""
    db = await connection.get_connection()
    repo = get_alert_config_repository(db)
    
    configs = await repo.list_all()
    results = []
    for c in configs:
        results.append(AlertConfig(
            id=c["id"],
            name=c["name"],
            metric=c["metric"],
            operator=c["operator"],
            threshold=c["threshold"],
            isActive=bool(c["is_active"]),
            scope=c["scope"],
        ))
    return results


@analytics_router.get("/notifications", response_model=list[Notification])
async def get_notifications():
    """Generate notifications from recent session data (DB)."""
    project = project_manager.get_active_project()
    if not project:
        return []

    db = await connection.get_connection()
    repo = get_session_repository(db)
    # Reuse list_paginated for recent sessions
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


@analytics_router.get("/export/prometheus")
async def export_prometheus():
    """Export latest metrics in Prometheus exposition format."""
    project = project_manager.get_active_project()
    if not project:
        return Response("", media_type="text/plain")

    db = await connection.get_connection()
    repo = get_analytics_repository(db)
    
    types = [
        "session_cost", "session_tokens", "session_count", 
        "task_velocity", "task_completion_pct", "tool_call_count", "tool_success_rate"
    ]
    latest = await repo.get_latest_entries(project.id, types)
    
    lines = []
    for metric, value in latest.items():
        # Sanitize metric name
        safe_name = f"ccdash_{metric}"
        lines.append(f"# TYPE {safe_name} gauge")
        lines.append(f'{safe_name}{{project="{project.id}"}} {value}')
    
    return Response("\n".join(lines) + "\n", media_type="text/plain")
