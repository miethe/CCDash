"""Feature forensics query service for detailed feature development history.

This service provides comprehensive forensic analysis of feature development,
including linked sessions, documents, tasks, iteration history, cost analysis,
and workflow effectiveness patterns.
"""

from datetime import datetime, timezone
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports.core import CorePorts
from backend.application.services.agent_queries.models import (
    DocumentRef,
    FeatureForensicsDTO,
    SessionRef,
    TaskRef,
)


class FeatureForensicsQueryService:
    """Query service for feature-level forensic analysis."""

    async def get_forensics(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str,
    ) -> FeatureForensicsDTO:
        """Get detailed feature development history and forensics.

        Args:
            context: Request context with project information
            ports: Core application ports for data access
            feature_id: Feature identifier to analyze

        Returns:
            FeatureForensicsDTO with comprehensive feature forensics
        """
        generated_at = datetime.now(timezone.utc)
        source_refs: list[str] = []

        # Fetch feature details
        try:
            feature = await ports.storage.features().get_feature(feature_id)
            if not feature:
                return FeatureForensicsDTO(
                    feature_id=feature_id,
                    feature_slug="not_found",
                    status="error",
                    source_refs=["error:feature_not_found"],
                )
            
            feature_slug = feature.get("slug", feature_id)
            feature_status = feature.get("status", "unknown")
            source_refs.append(f"feature:id={feature_id}")
        except Exception as e:
            return FeatureForensicsDTO(
                feature_id=feature_id,
                feature_slug="error",
                status="error",
                source_refs=[f"error:feature_fetch={str(e)[:50]}"],
            )

        # Initialize collections
        linked_sessions: list[SessionRef] = []
        linked_documents: list[DocumentRef] = []
        linked_tasks: list[TaskRef] = []
        iteration_count = 0
        total_cost = 0.0
        total_tokens = 0
        workflow_mix: dict[str, float] = {}
        rework_signals: list[str] = []
        failure_patterns: list[str] = []
        representative_sessions: list[SessionRef] = []

        # Fetch linked sessions
        try:
            sessions = await ports.storage.entity_links().get_feature_sessions(feature_id)
            iteration_count = len(sessions)
            
            workflow_counts: dict[str, int] = {}
            failed_sessions: list[dict[str, Any]] = []
            
            for session in sessions:
                session_id = session.get("id", "")
                session_status = session.get("status", "unknown")
                workflow = session.get("workflow", "unknown")
                cost = float(session.get("total_cost", 0.0))
                tokens = int(session.get("total_tokens", 0))
                
                total_cost += cost
                total_tokens += tokens
                
                # Track workflow usage
                workflow_counts[workflow] = workflow_counts.get(workflow, 0) + 1
                
                # Track failures
                if session_status in ("failed", "error", "cancelled"):
                    failed_sessions.append(session)
                
                # Build SessionRef
                session_ref = SessionRef(
                    session_id=session_id,
                    title=session.get("title", ""),
                    status=session_status,
                    workflow_id=workflow,
                    workflow_name=workflow,
                    started_at=session.get("started_at"),
                    ended_at=session.get("ended_at"),
                    duration_seconds=int(session.get("duration_seconds", 0)),
                    total_cost=cost,
                    total_tokens=tokens,
                    tools_used=session.get("tools_used", []),
                    model=session.get("model", ""),
                    outcome=session_status,
                )
                linked_sessions.append(session_ref)
            
            # Compute workflow mix (percentages)
            total_sessions = len(sessions)
            if total_sessions > 0:
                workflow_mix = {
                    workflow: count / total_sessions
                    for workflow, count in workflow_counts.items()
                }
            
            # Detect rework signals
            if iteration_count > 5:
                rework_signals.append(f"high_iteration_count:{iteration_count}")
            
            if len(failed_sessions) > 0:
                failure_rate = len(failed_sessions) / total_sessions
                if failure_rate > 0.3:
                    rework_signals.append(f"high_failure_rate:{failure_rate:.2f}")
            
            # Extract failure patterns
            for failed in failed_sessions[:5]:  # Top 5 failures
                error_msg = failed.get("error_message", "")
                if error_msg:
                    failure_patterns.append(error_msg[:100])
            
            # Select representative sessions (first, last, and any pivotal ones)
            if sessions:
                representative_sessions.append(linked_sessions[0])  # First session
                if len(linked_sessions) > 1:
                    representative_sessions.append(linked_sessions[-1])  # Last session
                # Add highest cost session if different
                if len(linked_sessions) > 2:
                    highest_cost = max(linked_sessions, key=lambda s: s.total_cost)
                    if highest_cost not in representative_sessions:
                        representative_sessions.append(highest_cost)
            
            source_refs.append(f"sessions:count={len(sessions)}")
        except Exception as e:
            source_refs.append(f"sessions:error={str(e)[:50]}")

        # Fetch linked documents
        try:
            documents = await ports.storage.entity_links().get_feature_documents(feature_id)
            for doc in documents:
                linked_documents.append(
                    DocumentRef(
                        document_id=doc.get("id", ""),
                        path=doc.get("path", ""),
                        title=doc.get("title", ""),
                        document_type=doc.get("type", ""),
                        status=doc.get("status", ""),
                        updated_at=doc.get("updated_at"),
                    )
                )
            source_refs.append(f"documents:count={len(documents)}")
        except Exception as e:
            source_refs.append(f"documents:error={str(e)[:50]}")

        # Fetch linked tasks
        try:
            tasks = await ports.storage.entity_links().get_feature_tasks(feature_id)
            for task in tasks:
                linked_tasks.append(
                    TaskRef(
                        task_id=task.get("id", ""),
                        title=task.get("title", ""),
                        status=task.get("status", ""),
                        assignee=task.get("assignee", ""),
                        updated_at=task.get("updated_at"),
                    )
                )
            source_refs.append(f"tasks:count={len(tasks)}")
        except Exception as e:
            source_refs.append(f"tasks:error={str(e)[:50]}")

        # Generate summary narrative
        summary_narrative = self._generate_summary(
            feature_slug=feature_slug,
            iteration_count=iteration_count,
            total_cost=total_cost,
            workflow_mix=workflow_mix,
            rework_signals=rework_signals,
        )

        # Compute data freshness
        data_freshness = generated_at
        if linked_sessions:
            oldest_session = min(
                (s.started_at for s in linked_sessions if s.started_at),
                default=None,
            )
            if oldest_session:
                data_freshness = oldest_session

        return FeatureForensicsDTO(
            feature_id=feature_id,
            feature_slug=feature_slug,
            status=feature_status,
            linked_sessions=linked_sessions,
            linked_documents=linked_documents,
            linked_tasks=linked_tasks,
            iteration_count=iteration_count,
            total_cost=total_cost,
            total_tokens=total_tokens,
            workflow_mix=workflow_mix,
            rework_signals=rework_signals,
            failure_patterns=failure_patterns,
            representative_sessions=representative_sessions,
            summary_narrative=summary_narrative,
            data_freshness=data_freshness,
            generated_at=generated_at,
            source_refs=source_refs,
        )

    def _generate_summary(
        self,
        feature_slug: str,
        iteration_count: int,
        total_cost: float,
        workflow_mix: dict[str, float],
        rework_signals: list[str],
    ) -> str:
        """Generate a narrative summary of feature development."""
        parts = [f"Feature '{feature_slug}' underwent {iteration_count} development iterations"]
        
        if total_cost > 0:
            parts.append(f"at a total cost of ${total_cost:.2f}")
        
        if workflow_mix:
            top_workflow = max(workflow_mix.items(), key=lambda x: x[1])
            parts.append(f"Primary workflow: {top_workflow[0]} ({top_workflow[1]:.0%})")
        
        if rework_signals:
            parts.append(f"Rework indicators: {len(rework_signals)} detected")
        
        return ". ".join(parts) + "."

# Made with Bob
