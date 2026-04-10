"""Unit tests for ReportingQueryService."""

import unittest
from datetime import timedelta
from unittest.mock import AsyncMock

from backend.application.services.agent_queries.models import AARReportDTO
from backend.application.services.agent_queries.reporting import ReportingQueryService
from backend.tests.fixtures.agent_queries_fixtures import (
    make_mock_ports,
    make_request_context,
    make_test_feature,
    make_test_session,
    utc_now,
)


class ReportingQueryServiceTests(unittest.IsolatedAsyncioTestCase):
    """Test suite for ReportingQueryService."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.service = ReportingQueryService()
        self.context = make_request_context("test-project")
        self.ports = make_mock_ports("test-project")

    async def test_happy_path_with_complete_data(self) -> None:
        """Test AAR generation with complete feature data."""
        # Arrange
        feature = make_test_feature("feat-1", "feat-1", "done", "User authentication feature")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        now = utc_now()
        sessions = [
            make_test_session("s1", "completed", "code", 2.0, 5000, 1800, started_at=now - timedelta(days=5)),
            make_test_session("s2", "completed", "code", 1.5, 3000, 1200, started_at=now - timedelta(days=4)),
            make_test_session("s3", "failed", "architect", 0.5, 1000, 600, started_at=now - timedelta(days=3)),
            make_test_session("s4", "completed", "code", 1.0, 2000, 900, started_at=now - timedelta(days=2)),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertIsInstance(result, AARReportDTO)
        self.assertEqual(result.feature_id, "feat-1")
        self.assertEqual(result.feature_slug, "feat-1")
        self.assertIn("User authentication", result.scope_statement)
        
        # Timeline
        self.assertIsNotNone(result.timeline.start_date)
        self.assertIsNotNone(result.timeline.end_date)
        self.assertEqual(result.timeline.duration_days, 3)
        
        # Key metrics
        self.assertAlmostEqual(result.key_metrics.total_cost, 5.0, places=2)
        self.assertEqual(result.key_metrics.total_tokens, 11000)
        self.assertEqual(result.key_metrics.session_count, 4)
        self.assertEqual(result.key_metrics.iteration_count, 4)
        
        # Turning points
        self.assertGreater(len(result.turning_points), 0)
        
        # Workflow observations
        self.assertGreater(len(result.workflow_observations), 0)
        
        # Bottlenecks
        self.assertGreaterEqual(len(result.bottlenecks), 0)
        
        # Successful patterns
        self.assertGreaterEqual(len(result.successful_patterns), 0)
        
        # Lessons learned
        self.assertGreater(len(result.lessons_learned), 0)
        
        # Evidence links
        self.assertGreater(len(result.evidence_links), 0)

    async def test_feature_not_found(self) -> None:
        """Test handling when feature does not exist."""
        # Arrange
        self.ports.storage.features().get_feature = AsyncMock(return_value=None)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "nonexistent")
        
        # Assert
        self.assertEqual(result.feature_id, "nonexistent")
        self.assertEqual(result.feature_slug, "not_found")
        self.assertIn("Feature not found", result.scope_statement)
        self.assertIn("error:feature_not_found", result.source_refs)

    async def test_feature_fetch_error(self) -> None:
        """Test handling when feature fetch fails."""
        # Arrange
        self.ports.storage.features().get_feature = AsyncMock(
            side_effect=Exception("Database error")
        )
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertEqual(result.feature_id, "feat-1")
        self.assertEqual(result.feature_slug, "error")
        self.assertIn("Error fetching feature", result.scope_statement)
        self.assertIn("error:feature_fetch=", result.source_refs[0])

    async def test_sessions_unavailable_graceful_degradation(self) -> None:
        """Test graceful degradation when sessions are unavailable."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(
            side_effect=Exception("Sessions error")
        )
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertEqual(result.feature_id, "feat-1")
        self.assertIn("sessions:error=", result.source_refs[1])
        # Should still return valid DTO with empty data
        self.assertEqual(result.key_metrics.session_count, 0)

    async def test_timeline_computation(self) -> None:
        """Test timeline is computed correctly from sessions."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        now = utc_now()
        start = now - timedelta(days=10)
        end = now - timedelta(days=2)
        
        sessions = [
            make_test_session("s1", started_at=start, ended_at=start + timedelta(hours=1)),
            make_test_session("s2", started_at=now - timedelta(days=5), ended_at=now - timedelta(days=5) + timedelta(hours=1)),
            make_test_session("s3", started_at=end, ended_at=end + timedelta(hours=1)),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertEqual(result.timeline.start_date, start)
        self.assertEqual(result.timeline.end_date, end + timedelta(hours=1))
        self.assertEqual(result.timeline.duration_days, 8)

    async def test_key_metrics_aggregation(self) -> None:
        """Test key metrics are aggregated correctly."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", cost=1.5, tokens=3000),
            make_test_session("s2", cost=2.0, tokens=4000),
            make_test_session("s3", cost=0.5, tokens=1000),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertAlmostEqual(result.key_metrics.total_cost, 4.0, places=2)
        self.assertEqual(result.key_metrics.total_tokens, 8000)
        self.assertEqual(result.key_metrics.session_count, 3)
        self.assertEqual(result.key_metrics.iteration_count, 3)

    async def test_turning_point_first_success(self) -> None:
        """Test turning point is identified for first successful session."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        now = utc_now()
        sessions = [
            make_test_session("s1", "failed", started_at=now - timedelta(days=3)),
            make_test_session("s2", "failed", started_at=now - timedelta(days=2)),
            make_test_session("s3", "completed", started_at=now - timedelta(days=1)),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertGreater(len(result.turning_points), 0)
        first_success = next((tp for tp in result.turning_points if "First Successful" in tp.event), None)
        self.assertIsNotNone(first_success)
        if first_success:
            self.assertIn("2 attempts", first_success.impact_description)

    async def test_turning_point_cost_spike(self) -> None:
        """Test turning point is identified for high-cost sessions."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", cost=1.0),
            make_test_session("s2", cost=1.0),
            make_test_session("s3", cost=1.0),
            make_test_session("s4", cost=5.0),  # 5x average
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        cost_spike = next((tp for tp in result.turning_points if "High-Cost" in tp.event), None)
        self.assertIsNotNone(cost_spike)

    async def test_turning_point_workflow_change(self) -> None:
        """Test turning point is identified for workflow changes."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        now = utc_now()
        sessions = [
            make_test_session("s1", workflow="code", started_at=now - timedelta(days=3)),
            make_test_session("s2", workflow="code", started_at=now - timedelta(days=2)),
            make_test_session("s3", workflow="architect", started_at=now - timedelta(days=1)),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        workflow_change = next((tp for tp in result.turning_points if "Workflow Change" in tp.event), None)
        self.assertIsNotNone(workflow_change)

    async def test_workflow_observations_frequency_and_effectiveness(self) -> None:
        """Test workflow observations include frequency and effectiveness."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", "completed", "code"),
            make_test_session("s2", "completed", "code"),
            make_test_session("s3", "failed", "code"),
            make_test_session("s4", "completed", "architect"),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertEqual(len(result.workflow_observations), 2)
        code_obs = next(wo for wo in result.workflow_observations if wo.workflow_id == "code")
        self.assertEqual(code_obs.frequency, 3)
        self.assertAlmostEqual(code_obs.effectiveness, 2/3, places=2)

    async def test_bottleneck_high_failure_rate(self) -> None:
        """Test bottleneck is identified for high failure rate."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", "failed", cost=1.0),
            make_test_session("s2", "failed", cost=1.0),
            make_test_session("s3", "completed", cost=1.0),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertGreater(len(result.bottlenecks), 0)
        failure_bottleneck = next((b for b in result.bottlenecks if "failure rate" in b.description), None)
        self.assertIsNotNone(failure_bottleneck)
        if failure_bottleneck:
            self.assertEqual(failure_bottleneck.sessions_affected, 2)

    async def test_bottleneck_long_running_sessions(self) -> None:
        """Test bottleneck is identified for long-running sessions."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", duration=7200),  # 2 hours
            make_test_session("s2", duration=5400),  # 1.5 hours
            make_test_session("s3", duration=300),   # 5 minutes
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        long_session_bottleneck = next((b for b in result.bottlenecks if "Long-running" in b.description), None)
        self.assertIsNotNone(long_session_bottleneck)

    async def test_bottleneck_high_iteration_count(self) -> None:
        """Test bottleneck is identified for high iteration count."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [make_test_session(f"s{i}") for i in range(12)]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        iteration_bottleneck = next((b for b in result.bottlenecks if "iteration count" in b.description), None)
        self.assertIsNotNone(iteration_bottleneck)

    async def test_successful_patterns_extraction(self) -> None:
        """Test successful patterns are extracted."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", "completed", "code", cost=0.5, duration=1200),
            make_test_session("s2", "completed", "code", cost=0.6, duration=1500),
            make_test_session("s3", "completed", "architect", cost=2.0, duration=3600),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertGreater(len(result.successful_patterns), 0)
        # Should identify code workflow as most successful
        self.assertTrue(any("code" in pattern for pattern in result.successful_patterns))

    async def test_lessons_learned_high_effectiveness_workflow(self) -> None:
        """Test lessons learned for highly effective workflows."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", "completed", "excellent"),
            make_test_session("s2", "completed", "excellent"),
            make_test_session("s3", "completed", "excellent"),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertGreater(len(result.lessons_learned), 0)
        effectiveness_lesson = next((l for l in result.lessons_learned if "highly effective" in l), None)
        self.assertIsNotNone(effectiveness_lesson)

    async def test_lessons_learned_low_iteration_count(self) -> None:
        """Test lessons learned for efficient execution."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", "completed"),
            make_test_session("s2", "completed"),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        efficiency_lesson = next((l for l in result.lessons_learned if "efficient execution" in l), None)
        self.assertIsNotNone(efficiency_lesson)

    async def test_evidence_links_include_top_sessions(self) -> None:
        """Test evidence links include top 10 sessions."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [make_test_session(f"s{i}") for i in range(15)]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertEqual(len(result.evidence_links), 10)
        self.assertTrue(all(link.startswith("session:") for link in result.evidence_links))

    async def test_dto_serialization_round_trip(self) -> None:
        """Test DTO can be serialized and deserialized."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", "completed", "code", 1.5, 3000),
            make_test_session("s2", "completed", "architect", 1.0, 2000),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.generate_aar(self.context, self.ports, "feat-1")
        dto_dict = result.model_dump()
        reconstructed = AARReportDTO.model_validate(dto_dict)
        
        # Assert
        self.assertEqual(reconstructed.feature_id, result.feature_id)
        self.assertEqual(reconstructed.feature_slug, result.feature_slug)
        self.assertEqual(reconstructed.key_metrics.total_cost, result.key_metrics.total_cost)
        self.assertEqual(len(reconstructed.workflow_observations), len(result.workflow_observations))


if __name__ == "__main__":
    unittest.main()

# Made with Bob
