"""Workflow diagnostics query service for workflow effectiveness analysis.

This service analyzes workflow performance across a project or specific feature,
computing effectiveness scores, identifying top performers and problem workflows,
and providing actionable insights for workflow optimization.
"""

from datetime import datetime, timezone
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports.core import CorePorts
from backend.application.services.agent_queries.models import (
    SessionRef,
    WorkflowDiagnostic,
    WorkflowDiagnosticsDTO,
)
from backend.application.services.agent_queries._filters import resolve_project_scope
from backend.application.services.common import resolve_project


class WorkflowDiagnosticsQueryService:
    """Query service for workflow effectiveness diagnostics."""

    async def get_diagnostics(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str | None = None,
    ) -> WorkflowDiagnosticsDTO:
        """Analyze workflow effectiveness across project or single feature.

        Args:
            context: Request context with project information
            ports: Core application ports for data access
            feature_id: Optional feature ID to scope analysis

        Returns:
            WorkflowDiagnosticsDTO with workflow effectiveness metrics
        """
        # Resolve project scope
        try:
            project_scope = resolve_project_scope(context, ports, None)
            project_id = project_scope.project_id
        except ValueError:
            project = resolve_project(context, ports)
            if project is None:
                return WorkflowDiagnosticsDTO(
                    project_id="unknown",
                    status="error",
                    source_refs=["error:no_project_available"],
                )
            project_id = project.id

        generated_at = datetime.now(timezone.utc)
        status = "ok"
        source_refs: list[str] = []

        # Fetch sessions (optionally filtered by feature)
        sessions: list[dict[str, Any]] = []
        try:
            if feature_id:
                sessions = await ports.storage.entity_links().get_feature_sessions(feature_id)
                source_refs.append(f"scope:feature={feature_id}")
            else:
                sessions = await ports.storage.sessions().list_sessions(
                    project_id=project_id,
                    limit=500,  # Analyze up to 500 recent sessions
                )
                source_refs.append(f"scope:project={project_id}")
            
            source_refs.append(f"sessions:analyzed={len(sessions)}")
        except Exception as e:
            status = "partial"
            source_refs.append(f"sessions:error={str(e)[:50]}")
            sessions = []

        # Aggregate workflow statistics
        workflow_stats: dict[str, dict[str, Any]] = {}
        
        for session in sessions:
            workflow = session.get("workflow", "unknown")
            if workflow not in workflow_stats:
                workflow_stats[workflow] = {
                    "session_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "total_cost": 0.0,
                    "total_tokens": 0,
                    "total_duration": 0,
                    "failures": [],
                    "sessions": [],
                }
            
            stats = workflow_stats[workflow]
            stats["session_count"] += 1
            stats["total_cost"] += float(session.get("total_cost", 0.0))
            stats["total_tokens"] += int(session.get("total_tokens", 0))
            stats["total_duration"] += int(session.get("duration_seconds", 0))
            
            session_status = session.get("status", "unknown")
            if session_status == "completed":
                stats["success_count"] += 1
            elif session_status in ("failed", "error", "cancelled"):
                stats["failure_count"] += 1
                error_msg = session.get("error_message", "unknown_error")
                stats["failures"].append(error_msg[:100])
            
            # Keep reference to sessions for representative samples
            stats["sessions"].append(session)

        # Build WorkflowDiagnostic objects
        workflows: list[WorkflowDiagnostic] = []
        
        for workflow_id, stats in workflow_stats.items():
            session_count = stats["session_count"]
            success_count = stats["success_count"]
            failure_count = stats["failure_count"]
            
            # Compute success rate
            success_rate = success_count / session_count if session_count > 0 else 0.0
            
            # Compute cost efficiency (lower is better, normalized)
            avg_cost = stats["total_cost"] / session_count if session_count > 0 else 0.0
            cost_efficiency = 1.0 / (1.0 + avg_cost) if avg_cost > 0 else 1.0
            
            # Compute speed score (faster is better, normalized)
            avg_duration = stats["total_duration"] / session_count if session_count > 0 else 0.0
            speed_score = 1.0 / (1.0 + avg_duration / 3600.0) if avg_duration > 0 else 1.0
            
            # Compute effectiveness score (weighted combination)
            effectiveness_score = (
                success_rate * 0.5 +  # 50% weight on success
                cost_efficiency * 0.25 +  # 25% weight on cost
                speed_score * 0.25  # 25% weight on speed
            )
            
            # Extract common failures (top 3)
            common_failures = list(set(stats["failures"]))[:3]
            
            # Select representative sessions (first 3)
            representative_sessions = [
                SessionRef(
                    session_id=s.get("id", ""),
                    title=s.get("title", ""),
                    status=s.get("status", ""),
                    workflow_id=workflow_id,
                    workflow_name=workflow_id,
                    started_at=s.get("started_at"),
                    ended_at=s.get("ended_at"),
                    duration_seconds=int(s.get("duration_seconds", 0)),
                    total_cost=float(s.get("total_cost", 0.0)),
                    total_tokens=int(s.get("total_tokens", 0)),
                    tools_used=s.get("tools_used", []),
                    model=s.get("model", ""),
                    outcome=s.get("status", ""),
                )
                for s in stats["sessions"][:3]
            ]
            
            workflows.append(
                WorkflowDiagnostic(
                    workflow_id=workflow_id,
                    workflow_name=workflow_id,
                    effectiveness_score=effectiveness_score,
                    session_count=session_count,
                    success_count=success_count,
                    failure_count=failure_count,
                    cost_efficiency=cost_efficiency,
                    common_failures=common_failures,
                    representative_sessions=representative_sessions,
                )
            )

        # Sort workflows by effectiveness score
        workflows.sort(key=lambda w: w.effectiveness_score, reverse=True)

        # Identify top performers (top 3 by effectiveness)
        top_performers = workflows[:3]

        # Identify problem workflows (bottom 3 with failures)
        problem_workflows = [
            w for w in workflows
            if w.failure_count > 0 and w.effectiveness_score < 0.5
        ][-3:]  # Bottom 3

        # Compute data freshness
        data_freshness = generated_at
        if sessions:
            valid_timestamps = [
                ts for s in sessions
                if (ts := s.get("started_at")) is not None
            ]
            if valid_timestamps:
                data_freshness = min(valid_timestamps)

        return WorkflowDiagnosticsDTO(
            project_id=project_id,
            status=status,
            workflows=workflows,
            top_performers=top_performers,
            problem_workflows=problem_workflows,
            data_freshness=data_freshness,
            generated_at=generated_at,
            source_refs=source_refs,
        )

# Made with Bob
