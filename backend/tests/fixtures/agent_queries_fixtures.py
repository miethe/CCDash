"""Test fixtures and builders for agent query service tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts


def utc_now() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc)


def make_test_session(
    session_id: str = "test-session",
    status: str = "completed",
    workflow: str = "code",
    cost: float = 1.0,
    tokens: int = 1000,
    duration: int = 300,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    model: str = "claude-3-5-sonnet-20241022",
    title: str = "Test Session",
    tools_used: list[str] | None = None,
    error_message: str = "",
) -> dict[str, Any]:
    """Create a test session object."""
    if started_at is None:
        started_at = utc_now() - timedelta(hours=1)
    if ended_at is None:
        ended_at = started_at + timedelta(seconds=duration)
    
    return {
        "id": session_id,
        "title": title,
        "status": status,
        "workflow": workflow,
        "total_cost": cost,
        "total_tokens": tokens,
        "duration_seconds": duration,
        "started_at": started_at,
        "ended_at": ended_at,
        "model": model,
        "tools_used": tools_used or ["read_file", "write_to_file"],
        "error_message": error_message,
    }


def make_test_feature(
    feature_id: str = "test-feature",
    slug: str = "test-feature",
    status: str = "in_progress",
    description: str = "Test feature description",
) -> dict[str, Any]:
    """Create a test feature object."""
    return {
        "id": feature_id,
        "slug": slug,
        "status": status,
        "description": description,
    }


def make_test_document(
    document_id: str = "test-doc",
    path: str = "docs/test.md",
    title: str = "Test Document",
    doc_type: str = "plan",
    status: str = "active",
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a test document object."""
    if updated_at is None:
        updated_at = utc_now()
    
    return {
        "id": document_id,
        "path": path,
        "title": title,
        "type": doc_type,
        "status": status,
        "updated_at": updated_at,
    }


def make_test_task(
    task_id: str = "test-task",
    title: str = "Test Task",
    status: str = "in_progress",
    assignee: str = "test-user",
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a test task object."""
    if updated_at is None:
        updated_at = utc_now()
    
    return {
        "id": task_id,
        "title": title,
        "status": status,
        "assignee": assignee,
        "updated_at": updated_at,
    }


def make_request_context(project_id: str = "test-project") -> RequestContext:
    """Create a test request context."""
    return RequestContext(
        principal=Principal(
            subject="test:operator",
            display_name="Test Operator",
            auth_mode="test",
        ),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Test Project",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/sessions"),
            docs_dir=Path("/tmp/docs"),
            progress_dir=Path("/tmp/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-test"),
    )


def make_mock_ports(project_id: str = "test-project") -> CorePorts:
    """Create mocked CorePorts with all repositories."""
    # Create mock storage with async repositories
    storage = MagicMock()
    
    # Mock sessions repository
    sessions_repo = AsyncMock()
    sessions_repo.list_sessions = AsyncMock(return_value=[])
    storage.sessions = MagicMock(return_value=sessions_repo)
    
    # Mock features repository
    features_repo = AsyncMock()
    features_repo.list_features = AsyncMock(return_value=[])
    features_repo.get_feature = AsyncMock(return_value=None)
    storage.features = MagicMock(return_value=features_repo)
    
    # Mock entity_links repository
    entity_links_repo = AsyncMock()
    entity_links_repo.get_feature_sessions = AsyncMock(return_value=[])
    entity_links_repo.get_feature_documents = AsyncMock(return_value=[])
    entity_links_repo.get_feature_tasks = AsyncMock(return_value=[])
    storage.entity_links = MagicMock(return_value=entity_links_repo)
    
    # Mock sync_state repository
    sync_state_repo = AsyncMock()
    sync_state_repo.get_last_sync_time = AsyncMock(return_value=None)
    storage.sync_state = MagicMock(return_value=sync_state_repo)
    
    # Create fake project
    project = type("Project", (), {"id": project_id, "name": "Test Project"})()
    
    # Create fake workspace registry
    workspace_registry = MagicMock()
    workspace_registry.get_project = MagicMock(return_value=project)
    workspace_registry.get_active_project = MagicMock(return_value=project)
    
    # Create fake identity provider
    identity_provider = MagicMock()
    identity_provider.get_principal = AsyncMock(
        return_value=Principal(
            subject="test:operator",
            display_name="Test Operator",
            auth_mode="test",
        )
    )
    
    # Create fake authorization policy
    authorization_policy = MagicMock()
    authorization_policy.authorize = AsyncMock(
        return_value=AuthorizationDecision(allowed=True)
    )
    
    # Create fake job scheduler
    job_scheduler = MagicMock()
    job_scheduler.schedule = MagicMock(side_effect=lambda job, **kwargs: job)
    
    # Create fake integration client
    integration_client = MagicMock()
    integration_client.invoke = AsyncMock(return_value={})
    
    return CorePorts(
        identity_provider=identity_provider,
        authorization_policy=authorization_policy,
        workspace_registry=workspace_registry,
        storage=storage,
        job_scheduler=job_scheduler,
        integration_client=integration_client,
    )


__all__ = [
    "make_test_session",
    "make_test_feature",
    "make_test_document",
    "make_test_task",
    "make_request_context",
    "make_mock_ports",
    "utc_now",
]

# Made with Bob
