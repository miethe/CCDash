"""Project status query service for high-level project health and trends.

This service aggregates data from multiple repositories to provide a comprehensive
view of project status, including feature counts, recent activity, cost metrics,
and workflow effectiveness.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports.core import CorePorts
from backend.application.services.agent_queries.models import (
    CostSummary,
    ProjectStatusDTO,
    SessionSummary,
    WorkflowSummary,
)
from backend.application.services.agent_queries._filters import resolve_project_scope
from backend.application.services.common import resolve_project


class ProjectStatusQueryService:
    """Query service for project-level status and health metrics."""

    async def get_status(
        self,
        context: RequestContext,
        ports: CorePorts,
        project_id_override: str | None = None,
    ) -> ProjectStatusDTO:
        """Get high-level project status and trends.

        Args:
            context: Request context with project information
            ports: Core application ports for data access
            project_id_override: Optional project ID to override context

        Returns:
            ProjectStatusDTO with project health metrics and trends
        """
        # Resolve project scope
        try:
            project_scope = resolve_project_scope(context, ports, project_id_override)
            project_id = project_scope.project_id
            project_name = project_scope.project_name
        except ValueError as e:
            # Fallback to active project
            project = resolve_project(context, ports, requested_project_id=project_id_override)
            if project is None:
                # Return minimal response if no project available
                return ProjectStatusDTO(
                    project_id="unknown",
                    project_name="No Active Project",
                    status="error",
                    source_refs=["error:no_project_available"],
                )
            project_id = project.id
            project_name = project.name

        generated_at = datetime.now(timezone.utc)
        status = "ok"
        source_refs: list[str] = []

        # Initialize response with defaults
        feature_counts: dict[str, int] = {}
        recent_sessions: list[SessionSummary] = []
        cost_last_7d = CostSummary()
        top_workflows: list[WorkflowSummary] = []
        sync_freshness = generated_at
        blocked_features: list[str] = []

        # Fetch feature counts by status
        try:
            features = await ports.storage.features().list_features(project_id)
            feature_counts = {}
            for feature in features:
                feature_status = feature.get("status", "unknown")
                feature_counts[feature_status] = feature_counts.get(feature_status, 0) + 1
                
                # Track blocked features
                if feature_status == "blocked":
                    feature_id = feature.get("id", "")
                    if feature_id:
                        blocked_features.append(feature_id)
            
            source_refs.append(f"features:count={len(features)}")
        except Exception as e:
            status = "partial"
            source_refs.append(f"features:error={str(e)[:50]}")

        # Fetch recent sessions (last 100 for analysis)
        all_sessions: list[dict[str, Any]] = []
        try:
            all_sessions = await ports.storage.sessions().list_sessions(
                project_id=project_id,
                limit=100,
            )
            
            # Filter to last 7 days and convert to SessionSummary
            seven_days_ago = generated_at - timedelta(days=7)
            recent_session_data = [
                s for s in all_sessions
                if s.get("started_at") and s["started_at"] >= seven_days_ago
            ][:10]  # Top 10 most recent
            
            recent_sessions = [
                SessionSummary(
                    session_id=s.get("id", ""),
                    title=s.get("title", ""),
                    status=s.get("status", "unknown"),
                    workflow_id=s.get("workflow", ""),
                    workflow_name=s.get("workflow", ""),
                    started_at=s.get("started_at"),
                    ended_at=s.get("ended_at"),
                    duration_seconds=int(s.get("duration_seconds", 0)),
                    total_cost=float(s.get("total_cost", 0.0)),
                    total_tokens=int(s.get("total_tokens", 0)),
                    model=s.get("model", "unknown"),
                )
                for s in recent_session_data
            ]
            
            # Compute cost summary for last 7 days
            total_cost = sum(s.total_cost for s in recent_sessions)
            by_model: dict[str, float] = {}
            by_workflow: dict[str, float] = {}
            
            for s in recent_sessions:
                if s.model:
                    by_model[s.model] = by_model.get(s.model, 0.0) + s.total_cost
                if s.workflow_id:
                    by_workflow[s.workflow_id] = by_workflow.get(s.workflow_id, 0.0) + s.total_cost
            
            cost_last_7d = CostSummary(
                total=total_cost,
                by_model=by_model,
                by_workflow=by_workflow,
            )
            
            source_refs.append(f"sessions:recent={len(recent_sessions)}")
        except Exception as e:
            status = "partial"
            source_refs.append(f"sessions:error={str(e)[:50]}")

        # Identify top workflows from recent sessions
        try:
            workflow_counts: dict[str, dict[str, Any]] = {}
            
            for session in all_sessions[:50]:  # Analyze top 50 sessions
                workflow = session.get("workflow", "unknown")
                if workflow not in workflow_counts:
                    workflow_counts[workflow] = {
                        "count": 0,
                        "total_cost": 0.0,
                        "success_count": 0,
                    }
                
                workflow_counts[workflow]["count"] += 1
                workflow_counts[workflow]["total_cost"] += session.get("total_cost", 0.0)
                
                if session.get("status") == "completed":
                    workflow_counts[workflow]["success_count"] += 1
            
            # Convert to WorkflowSummary and sort by usage
            top_workflows = [
                WorkflowSummary(
                    workflow_id=name,
                    workflow_name=name,
                    session_count=data["count"],
                    total_cost=data["total_cost"],
                    success_rate=data["success_count"] / data["count"] if data["count"] > 0 else 0.0,
                )
                for name, data in sorted(
                    workflow_counts.items(),
                    key=lambda x: x[1]["count"],
                    reverse=True,
                )[:5]  # Top 5 workflows
            ]
            
            source_refs.append(f"workflows:identified={len(workflow_counts)}")
        except Exception as e:
            status = "partial"
            source_refs.append(f"workflows:error={str(e)[:50]}")

        # Check sync freshness
        try:
            # Query sync engine for last sync time
            sync_state = await ports.storage.sync_state().get_last_sync_time(project_id)
            if sync_state:
                sync_freshness = sync_state.get("last_sync_at", generated_at)
            source_refs.append("sync:checked")
        except Exception:
            # Sync freshness is optional, use generated_at as fallback
            source_refs.append("sync:unavailable")

        # Compute data freshness (oldest session timestamp)
        data_freshness = generated_at
        if recent_sessions:
            oldest_session = min(
                (s.started_at for s in recent_sessions if s.started_at),
                default=None,
            )
            if oldest_session:
                data_freshness = oldest_session

        return ProjectStatusDTO(
            project_id=project_id,
            project_name=project_name,
            status=status,
            feature_counts=feature_counts,
            recent_sessions=recent_sessions,
            cost_last_7d=cost_last_7d,
            top_workflows=top_workflows,
            sync_freshness=sync_freshness,
            blocked_features=blocked_features,
            data_freshness=data_freshness,
            generated_at=generated_at,
            source_refs=source_refs,
        )

# Made with Bob
