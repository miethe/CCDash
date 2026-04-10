"""Reporting query service for after-action review (AAR) generation.

This service generates comprehensive after-action review reports for features,
analyzing the complete development lifecycle, identifying key turning points,
extracting lessons learned, and providing evidence-based recommendations.
"""

from datetime import datetime, timezone
from typing import Any

from backend.application.context import RequestContext
from backend.application.ports.core import CorePorts
from backend.application.services.agent_queries.models import (
    AARReportDTO,
    Bottleneck,
    KeyMetrics,
    TimelineData,
    TurningPoint,
    WorkflowObservation,
)


class ReportingQueryService:
    """Query service for after-action review report generation."""

    async def generate_aar(
        self,
        context: RequestContext,
        ports: CorePorts,
        feature_id: str,
    ) -> AARReportDTO:
        """Generate an AAR report for a feature.

        Args:
            context: Request context with project information
            ports: Core application ports for data access
            feature_id: Feature identifier to generate report for

        Returns:
            AARReportDTO with comprehensive after-action review
        """
        generated_at = datetime.now(timezone.utc)
        source_refs: list[str] = []

        # Fetch feature details
        try:
            feature = await ports.storage.features().get_feature(feature_id)
            if not feature:
                return AARReportDTO(
                    feature_id=feature_id,
                    feature_slug="not_found",
                    scope_statement="Feature not found",
                    source_refs=["error:feature_not_found"],
                )
            
            feature_slug = feature.get("slug", feature_id)
            scope_statement = feature.get("description", "") or f"Feature: {feature_slug}"
            source_refs.append(f"feature:id={feature_id}")
        except Exception as e:
            return AARReportDTO(
                feature_id=feature_id,
                feature_slug="error",
                scope_statement="Error fetching feature",
                source_refs=[f"error:feature_fetch={str(e)[:50]}"],
            )

        # Fetch all linked sessions
        sessions: list[dict[str, Any]] = []
        try:
            sessions = await ports.storage.entity_links().get_feature_sessions(feature_id)
            source_refs.append(f"sessions:count={len(sessions)}")
        except Exception as e:
            source_refs.append(f"sessions:error={str(e)[:50]}")

        # Compute timeline
        timeline = self._compute_timeline(sessions)

        # Compute key metrics
        key_metrics = self._compute_key_metrics(sessions)

        # Identify turning points
        turning_points = self._identify_turning_points(sessions)

        # Analyze workflow observations
        workflow_observations = self._analyze_workflows(sessions)

        # Identify bottlenecks
        bottlenecks = self._identify_bottlenecks(sessions)

        # Extract successful patterns
        successful_patterns = self._extract_successful_patterns(sessions)

        # Generate lessons learned
        lessons_learned = self._generate_lessons_learned(
            sessions=sessions,
            workflow_observations=workflow_observations,
            bottlenecks=bottlenecks,
        )

        # Collect evidence links
        evidence_links = [
            f"session:{s.get('id', '')}" for s in sessions[:10]  # Top 10 sessions
        ]

        # Compute data freshness
        data_freshness = generated_at
        if sessions:
            valid_timestamps = [
                ts for s in sessions
                if (ts := s.get("started_at")) is not None
            ]
            if valid_timestamps:
                data_freshness = min(valid_timestamps)

        return AARReportDTO(
            feature_id=feature_id,
            feature_slug=feature_slug,
            scope_statement=scope_statement,
            timeline=timeline,
            key_metrics=key_metrics,
            turning_points=turning_points,
            workflow_observations=workflow_observations,
            bottlenecks=bottlenecks,
            successful_patterns=successful_patterns,
            lessons_learned=lessons_learned,
            evidence_links=evidence_links,
            data_freshness=data_freshness,
            generated_at=generated_at,
            source_refs=source_refs,
        )

    def _compute_timeline(self, sessions: list[dict[str, Any]]) -> TimelineData:
        """Compute the timeline for feature development."""
        if not sessions:
            return TimelineData()

        valid_start_times = [
            ts for s in sessions
            if (ts := s.get("started_at")) is not None
        ]
        valid_end_times = [
            ts for s in sessions
            if (ts := s.get("ended_at")) is not None
        ]

        if not valid_start_times:
            return TimelineData()

        start_date = min(valid_start_times)
        end_date = max(valid_end_times) if valid_end_times else datetime.now(timezone.utc)
        
        duration_days = (end_date - start_date).days

        return TimelineData(
            start_date=start_date,
            end_date=end_date,
            duration_days=duration_days,
        )

    def _compute_key_metrics(self, sessions: list[dict[str, Any]]) -> KeyMetrics:
        """Compute key metrics for the feature."""
        total_cost = sum(float(s.get("total_cost", 0.0)) for s in sessions)
        total_tokens = sum(int(s.get("total_tokens", 0)) for s in sessions)
        session_count = len(sessions)
        iteration_count = session_count  # Each session is an iteration

        return KeyMetrics(
            total_cost=total_cost,
            total_tokens=total_tokens,
            session_count=session_count,
            iteration_count=iteration_count,
        )

    def _identify_turning_points(self, sessions: list[dict[str, Any]]) -> list[TurningPoint]:
        """Identify major turning points in feature development."""
        turning_points: list[TurningPoint] = []

        if not sessions:
            return turning_points

        # Sort sessions by start time
        sorted_sessions = sorted(
            sessions,
            key=lambda s: s.get("started_at") or datetime.min.replace(tzinfo=timezone.utc),
        )

        # First successful session
        for i, session in enumerate(sorted_sessions):
            if session.get("status") == "completed":
                turning_points.append(
                    TurningPoint(
                        date=session.get("started_at") or datetime.now(timezone.utc),
                        event="First Successful Session",
                        impact_description=f"Initial breakthrough after {i} attempts",
                    )
                )
                break

        # Major cost spike (session cost > 2x average)
        if len(sessions) > 3:
            avg_cost = sum(float(s.get("total_cost", 0.0)) for s in sessions) / len(sessions)
            for session in sorted_sessions:
                cost = float(session.get("total_cost", 0.0))
                if cost > avg_cost * 2:
                    turning_points.append(
                        TurningPoint(
                            date=session.get("started_at") or datetime.now(timezone.utc),
                            event="High-Cost Session",
                            impact_description=f"Session cost ${cost:.2f} exceeded average by 2x",
                        )
                    )
                    break

        # Workflow change (if workflow changes mid-development)
        workflows_seen: set[str] = set()
        for session in sorted_sessions:
            workflow = session.get("workflow", "unknown")
            if workflow not in workflows_seen and len(workflows_seen) > 0:
                turning_points.append(
                    TurningPoint(
                        date=session.get("started_at") or datetime.now(timezone.utc),
                        event="Workflow Change",
                        impact_description=f"Switched to {workflow} workflow",
                    )
                )
            workflows_seen.add(workflow)

        return turning_points[:5]  # Top 5 turning points

    def _analyze_workflows(self, sessions: list[dict[str, Any]]) -> list[WorkflowObservation]:
        """Analyze workflow usage and effectiveness."""
        workflow_stats: dict[str, dict[str, Any]] = {}

        for session in sessions:
            workflow = session.get("workflow", "unknown")
            if workflow not in workflow_stats:
                workflow_stats[workflow] = {
                    "frequency": 0,
                    "success_count": 0,
                }
            
            workflow_stats[workflow]["frequency"] += 1
            if session.get("status") == "completed":
                workflow_stats[workflow]["success_count"] += 1

        observations: list[WorkflowObservation] = []
        for workflow_id, stats in workflow_stats.items():
            frequency = stats["frequency"]
            effectiveness = stats["success_count"] / frequency if frequency > 0 else 0.0
            
            notes = f"Used {frequency} times with {effectiveness:.0%} success rate"
            
            observations.append(
                WorkflowObservation(
                    workflow_id=workflow_id,
                    frequency=frequency,
                    effectiveness=effectiveness,
                    notes=notes,
                )
            )

        return sorted(observations, key=lambda w: w.frequency, reverse=True)

    def _identify_bottlenecks(self, sessions: list[dict[str, Any]]) -> list[Bottleneck]:
        """Identify bottlenecks in feature development."""
        bottlenecks: list[Bottleneck] = []

        if not sessions:
            return bottlenecks

        # High failure rate
        failed_sessions = [s for s in sessions if s.get("status") in ("failed", "error", "cancelled")]
        if len(failed_sessions) > len(sessions) * 0.3:
            bottlenecks.append(
                Bottleneck(
                    description=f"High failure rate: {len(failed_sessions)}/{len(sessions)} sessions failed",
                    cost_impact=sum(float(s.get("total_cost", 0.0)) for s in failed_sessions),
                    sessions_affected=len(failed_sessions),
                )
            )

        # Long-running sessions (> 1 hour)
        long_sessions = [s for s in sessions if int(s.get("duration_seconds", 0)) > 3600]
        if long_sessions:
            bottlenecks.append(
                Bottleneck(
                    description=f"Long-running sessions: {len(long_sessions)} sessions exceeded 1 hour",
                    cost_impact=sum(float(s.get("total_cost", 0.0)) for s in long_sessions),
                    sessions_affected=len(long_sessions),
                )
            )

        # High iteration count
        if len(sessions) > 10:
            bottlenecks.append(
                Bottleneck(
                    description=f"High iteration count: {len(sessions)} sessions required",
                    cost_impact=sum(float(s.get("total_cost", 0.0)) for s in sessions),
                    sessions_affected=len(sessions),
                )
            )

        return bottlenecks[:5]  # Top 5 bottlenecks

    def _extract_successful_patterns(self, sessions: list[dict[str, Any]]) -> list[str]:
        """Extract successful patterns from session history."""
        patterns: list[str] = []

        successful_sessions = [s for s in sessions if s.get("status") == "completed"]
        
        if not successful_sessions:
            return patterns

        # Most successful workflow
        workflow_success: dict[str, int] = {}
        for session in successful_sessions:
            workflow = session.get("workflow", "unknown")
            workflow_success[workflow] = workflow_success.get(workflow, 0) + 1
        
        if workflow_success:
            top_workflow = max(workflow_success.items(), key=lambda x: x[1])
            patterns.append(f"Workflow '{top_workflow[0]}' had {top_workflow[1]} successful sessions")

        # Cost-effective sessions
        avg_cost = sum(float(s.get("total_cost", 0.0)) for s in successful_sessions) / len(successful_sessions)
        efficient_sessions = [s for s in successful_sessions if float(s.get("total_cost", 0.0)) < avg_cost]
        if efficient_sessions:
            patterns.append(f"{len(efficient_sessions)} sessions completed below average cost")

        # Quick completions
        quick_sessions = [s for s in successful_sessions if int(s.get("duration_seconds", 0)) < 1800]
        if quick_sessions:
            patterns.append(f"{len(quick_sessions)} sessions completed in under 30 minutes")

        return patterns

    def _generate_lessons_learned(
        self,
        sessions: list[dict[str, Any]],
        workflow_observations: list[WorkflowObservation],
        bottlenecks: list[Bottleneck],
    ) -> list[str]:
        """Generate lessons learned from feature development."""
        lessons: list[str] = []

        # Workflow lessons
        if workflow_observations:
            top_workflow = workflow_observations[0]
            if top_workflow.effectiveness > 0.7:
                lessons.append(
                    f"Workflow '{top_workflow.workflow_id}' proved highly effective "
                    f"({top_workflow.effectiveness:.0%} success rate)"
                )
            elif top_workflow.effectiveness < 0.3:
                lessons.append(
                    f"Workflow '{top_workflow.workflow_id}' struggled "
                    f"({top_workflow.effectiveness:.0%} success rate) - consider alternatives"
                )

        # Bottleneck lessons
        if bottlenecks:
            top_bottleneck = bottlenecks[0]
            lessons.append(f"Primary bottleneck: {top_bottleneck.description}")

        # Iteration lessons
        if len(sessions) > 10:
            lessons.append(
                f"High iteration count ({len(sessions)} sessions) suggests need for "
                "better upfront planning or clearer requirements"
            )
        elif len(sessions) <= 3:
            lessons.append(
                f"Low iteration count ({len(sessions)} sessions) indicates "
                "efficient execution or well-defined scope"
            )

        # Cost lessons
        total_cost = sum(float(s.get("total_cost", 0.0)) for s in sessions)
        if total_cost > 10.0:
            lessons.append(
                f"High total cost (${total_cost:.2f}) warrants review of "
                "workflow efficiency and model selection"
            )

        return lessons[:5]  # Top 5 lessons

# Made with Bob
