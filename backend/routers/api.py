"""API routers for sessions, documents, tasks, and analytics."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.models import (
    AgentSession, PlanDocument, ProjectTask,
    AnalyticsMetric, AlertConfig, Notification,
)
from backend.parsers.sessions import scan_sessions
from backend.parsers.documents import scan_documents
from backend.parsers.progress import scan_progress
from backend import config

# ── Sessions router ─────────────────────────────────────────────────

sessions_router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@sessions_router.get("", response_model=list[AgentSession])
def list_sessions():
    """Return all parsed agent sessions."""
    return scan_sessions(config.SESSIONS_DIR)


@sessions_router.get("/{session_id}", response_model=AgentSession)
def get_session(session_id: str):
    """Return a single session by ID."""
    sessions = scan_sessions(config.SESSIONS_DIR)
    for s in sessions:
        if s.id == session_id:
            return s
    raise HTTPException(status_code=404, detail=f"Session {session_id} not found")


# ── Documents router ────────────────────────────────────────────────

documents_router = APIRouter(prefix="/api/documents", tags=["documents"])


@documents_router.get("", response_model=list[PlanDocument])
def list_documents():
    """Return all parsed plan documents (frontmatter only)."""
    docs = scan_documents(config.DOCUMENTS_DIR)
    # Strip content for list endpoint
    for doc in docs:
        doc.content = None
    return docs


@documents_router.get("/{doc_id}", response_model=PlanDocument)
def get_document(doc_id: str):
    """Return a single document with full content."""
    docs = scan_documents(config.DOCUMENTS_DIR)
    for d in docs:
        if d.id == doc_id:
            return d
    raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")


# ── Tasks router ────────────────────────────────────────────────────

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@tasks_router.get("", response_model=list[ProjectTask])
def list_tasks():
    """Return all tasks derived from progress files."""
    return scan_progress(config.PROGRESS_DIR)


# ── Analytics router ────────────────────────────────────────────────

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@analytics_router.get("/metrics", response_model=list[AnalyticsMetric])
def get_metrics():
    """Derive analytics metrics from sessions and tasks."""
    sessions = scan_sessions(config.SESSIONS_DIR)
    tasks = scan_progress(config.PROGRESS_DIR)

    total_cost = sum(s.totalCost for s in sessions)
    total_tokens = sum(s.tokensIn + s.tokensOut for s in sessions)
    total_sessions = len(sessions)
    done_tasks = sum(1 for t in tasks if t.status == "done")
    total_tasks = len(tasks)
    completion_pct = (done_tasks / total_tasks * 100) if total_tasks > 0 else 0

    return [
        AnalyticsMetric(name="Total Cost", value=round(total_cost, 4), unit="$"),
        AnalyticsMetric(name="Total Tokens", value=total_tokens, unit="tokens"),
        AnalyticsMetric(name="Sessions", value=total_sessions, unit="count"),
        AnalyticsMetric(name="Tasks Done", value=done_tasks, unit="count"),
        AnalyticsMetric(name="Total Tasks", value=total_tasks, unit="count"),
        AnalyticsMetric(name="Completion", value=round(completion_pct, 1), unit="%"),
    ]


@analytics_router.get("/alerts", response_model=list[AlertConfig])
def get_alerts():
    """Return alert configurations (stub for now)."""
    return [
        AlertConfig(
            id="alert-cost",
            name="Cost Threshold",
            metric="cost_threshold",
            operator=">",
            threshold=5.0,
            isActive=True,
            scope="session",
        ),
        AlertConfig(
            id="alert-duration",
            name="Long Session",
            metric="total_tokens",
            operator=">",
            threshold=600,
            isActive=True,
            scope="session",
        ),
        AlertConfig(
            id="alert-friction",
            name="High Friction",
            metric="avg_quality",
            operator="<",
            threshold=3,
            isActive=False,
            scope="weekly",
        ),
    ]


@analytics_router.get("/notifications", response_model=list[Notification])
def get_notifications():
    """Generate notifications from recent session data."""
    sessions = scan_sessions(config.SESSIONS_DIR)
    notifications: list[Notification] = []

    for i, session in enumerate(sessions[:5]):
        notifications.append(Notification(
            id=f"notif-{session.id}",
            alertId="alert-cost",
            message=f"Session {session.id}: Model={session.model}, "
                    f"Cost=${session.totalCost:.4f}, Duration={session.durationSeconds}s",
            timestamp=session.startedAt,
            isRead=i > 0,
        ))

    return notifications

