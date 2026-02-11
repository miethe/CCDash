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
from backend.project_manager import project_manager
from backend import config

# ── Sessions router ─────────────────────────────────────────────────

sessions_router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@sessions_router.get("", response_model=list[AgentSession])
def list_sessions():
    """Return all parsed agent sessions."""
    sessions_dir, _, _ = project_manager.get_active_paths()
    return scan_sessions(sessions_dir)


@sessions_router.get("/{session_id}", response_model=AgentSession)
def get_session(session_id: str):
    """Return a single session by ID."""
    sessions_dir, _, _ = project_manager.get_active_paths()
    sessions = scan_sessions(sessions_dir)
    for s in sessions:
        if s.id == session_id:
            return s
    raise HTTPException(status_code=404, detail=f"Session {session_id} not found")


# ── Documents router ────────────────────────────────────────────────

documents_router = APIRouter(prefix="/api/documents", tags=["documents"])


@documents_router.get("", response_model=list[PlanDocument])
def list_documents():
    """Return all parsed plan documents (frontmatter only)."""
    _, docs_dir, _ = project_manager.get_active_paths()
    docs = scan_documents(docs_dir)
    # Strip content for list endpoint
    for doc in docs:
        doc.content = None
    return docs


@documents_router.get("/{doc_id}", response_model=PlanDocument)
def get_document(doc_id: str):
    """Return a single document with full content."""
    _, docs_dir, _ = project_manager.get_active_paths()
    docs = scan_documents(docs_dir)
    for d in docs:
        if d.id == doc_id:
            return d
    raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")


# ── Tasks router ────────────────────────────────────────────────────

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@tasks_router.get("", response_model=list[ProjectTask])
def list_tasks():
    """Return all tasks derived from progress files."""
    _, _, progress_dir = project_manager.get_active_paths()
    return scan_progress(progress_dir)


# ── Analytics router ────────────────────────────────────────────────

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@analytics_router.get("/metrics", response_model=list[AnalyticsMetric])
def get_metrics():
    """Derive analytics metrics from sessions and tasks."""
    sessions_dir, _, progress_dir = project_manager.get_active_paths()
    sessions = scan_sessions(sessions_dir)
    tasks = scan_progress(progress_dir)

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
    sessions_dir, _, _ = project_manager.get_active_paths()
    sessions = scan_sessions(sessions_dir)
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

