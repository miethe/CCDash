"""Unit tests for ProjectStatusQueryService."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from backend.application.services.agent_queries.models import ProjectStatusDTO
from backend.application.services.agent_queries.project_status import ProjectStatusQueryService
from backend.tests.fixtures.agent_queries_fixtures import (
    make_mock_ports,
    make_request_context,
    make_test_feature,
    make_test_session,
    utc_now,
)


class ProjectStatusQueryServiceTests(unittest.IsolatedAsyncioTestCase):
    """Test suite for ProjectStatusQueryService."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.service = ProjectStatusQueryService()
        self.context = make_request_context("test-project")
        self.ports = make_mock_ports("test-project")

    async def test_happy_path_with_complete_data(self) -> None:
        """Test service with complete data from all repositories."""
        # Arrange: Mock repository responses
        now = utc_now()
        seven_days_ago = now - timedelta(days=7)
        
        # Mock features
        features = [
            make_test_feature("feat-1", "feat-1", "in_progress"),
            make_test_feature("feat-2", "feat-2", "done"),
            make_test_feature("feat-3", "feat-3", "blocked"),
            make_test_feature("feat-4", "feat-4", "todo"),
        ]
        self.ports.storage.features().list_features = AsyncMock(return_value=features)
        
        # Mock sessions (recent ones within 7 days)
        sessions = [
            make_test_session(
                "sess-1", "completed", "code", 2.5, 5000, 600,
                started_at=seven_days_ago + timedelta(days=1),
                model="claude-3-5-sonnet-20241022",
            ),
            make_test_session(
                "sess-2", "completed", "architect", 1.2, 3000, 300,
                started_at=seven_days_ago + timedelta(days=2),
                model="claude-3-5-sonnet-20241022",
            ),
            make_test_session(
                "sess-3", "completed", "code", 0.8, 2000, 200,
                started_at=seven_days_ago + timedelta(days=3),
                model="gpt-4",
            ),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Mock sync state
        sync_time = now - timedelta(minutes=5)
        self.ports.storage.sync_state().get_last_sync_time = AsyncMock(
            return_value={"last_sync_at": sync_time}
        )
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertIsInstance(result, ProjectStatusDTO)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.project_id, "test-project")
        self.assertEqual(result.project_name, "Test Project")
        
        # Feature counts
        self.assertEqual(result.feature_counts["in_progress"], 1)
        self.assertEqual(result.feature_counts["done"], 1)
        self.assertEqual(result.feature_counts["blocked"], 1)
        self.assertEqual(result.feature_counts["todo"], 1)
        
        # Recent sessions
        self.assertEqual(len(result.recent_sessions), 3)
        self.assertEqual(result.recent_sessions[0].session_id, "sess-1")
        
        # Cost summary
        self.assertAlmostEqual(result.cost_last_7d.total, 4.5, places=2)
        self.assertIn("claude-3-5-sonnet-20241022", result.cost_last_7d.by_model)
        self.assertIn("code", result.cost_last_7d.by_workflow)
        
        # Top workflows
        self.assertGreater(len(result.top_workflows), 0)
        self.assertEqual(result.top_workflows[0].workflow_id, "code")
        
        # Blocked features
        self.assertEqual(result.blocked_features, ["feat-3"])
        
        # Sync freshness
        self.assertEqual(result.sync_freshness, sync_time)
        
        # Source refs
        self.assertIn("features:count=4", result.source_refs)
        self.assertIn("sessions:recent=3", result.source_refs)

    async def test_partial_degradation_features_unavailable(self) -> None:
        """Test graceful degradation when features repository fails."""
        # Arrange: Mock features to fail
        self.ports.storage.features().list_features = AsyncMock(
            side_effect=Exception("DB connection error")
        )
        
        # Mock sessions to succeed
        sessions = [make_test_session("sess-1", "completed", "code", 1.0, 1000, 300)]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertEqual(result.status, "partial")
        self.assertIn("features:error=", result.source_refs[0])
        # feature_counts has default buckets even on failure
        self.assertIn("todo", result.feature_counts)
        self.assertEqual(len(result.recent_sessions), 1)  # Sessions still work

    async def test_partial_degradation_sessions_unavailable(self) -> None:
        """Test graceful degradation when sessions repository fails."""
        # Arrange: Mock sessions to fail
        self.ports.storage.sessions().list_sessions = AsyncMock(
            side_effect=Exception("Query timeout")
        )
        
        # Mock features to succeed
        features = [make_test_feature("feat-1", "feat-1", "in_progress")]
        self.ports.storage.features().list_features = AsyncMock(return_value=features)
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertEqual(result.status, "partial")
        self.assertIn("sessions:error=", result.source_refs[1])
        self.assertEqual(result.feature_counts["in_progress"], 1)  # Features still work
        self.assertEqual(len(result.recent_sessions), 0)  # Sessions failed

    async def test_multiple_subsystem_failures(self) -> None:
        """Test handling of multiple repository failures."""
        # Arrange: Mock multiple failures
        self.ports.storage.features().list_features = AsyncMock(
            side_effect=Exception("Features error")
        )
        self.ports.storage.sessions().list_sessions = AsyncMock(
            side_effect=Exception("Sessions error")
        )
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertEqual(result.status, "partial")
        self.assertIn("features:error=", result.source_refs[0])
        self.assertIn("sessions:error=", result.source_refs[1])
        # feature_counts has default buckets even on failure
        self.assertIn("todo", result.feature_counts)
        self.assertEqual(len(result.recent_sessions), 0)

    async def test_empty_data_returns_valid_dto(self) -> None:
        """Test service handles empty data gracefully."""
        # Arrange: Mock empty responses
        self.ports.storage.features().list_features = AsyncMock(return_value=[])
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertEqual(result.status, "ok")  # Empty is valid
        # feature_counts has default buckets even when empty
        self.assertIn("todo", result.feature_counts)
        self.assertEqual(len(result.recent_sessions), 0)
        self.assertEqual(result.cost_last_7d.total, 0.0)
        self.assertEqual(len(result.top_workflows), 0)

    async def test_filters_sessions_to_last_7_days(self) -> None:
        """Test that only sessions from last 7 days are included."""
        # Arrange
        now = utc_now()
        eight_days_ago = now - timedelta(days=8)
        six_days_ago = now - timedelta(days=6)
        
        sessions = [
            make_test_session("old-sess", started_at=eight_days_ago),
            make_test_session("recent-sess", started_at=six_days_ago),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.features().list_features = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertEqual(len(result.recent_sessions), 1)
        self.assertEqual(result.recent_sessions[0].session_id, "recent-sess")

    async def test_limits_recent_sessions_to_10(self) -> None:
        """Test that recent sessions are limited to top 10."""
        # Arrange
        now = utc_now()
        sessions = [
            make_test_session(f"sess-{i}", started_at=now - timedelta(hours=i))
            for i in range(15)
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.features().list_features = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertEqual(len(result.recent_sessions), 10)

    async def test_cost_summary_aggregation(self) -> None:
        """Test cost summary is correctly aggregated."""
        # Arrange
        now = utc_now()
        sessions = [
            make_test_session("s1", "completed", "code", 1.5, model="claude-3-5-sonnet-20241022", started_at=now),
            make_test_session("s2", "completed", "code", 2.0, model="claude-3-5-sonnet-20241022", started_at=now),
            make_test_session("s3", "completed", "architect", 1.0, model="gpt-4", started_at=now),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.features().list_features = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertAlmostEqual(result.cost_last_7d.total, 4.5, places=2)
        self.assertAlmostEqual(result.cost_last_7d.by_model["claude-3-5-sonnet-20241022"], 3.5, places=2)
        self.assertAlmostEqual(result.cost_last_7d.by_model["gpt-4"], 1.0, places=2)
        self.assertAlmostEqual(result.cost_last_7d.by_workflow["code"], 3.5, places=2)
        self.assertAlmostEqual(result.cost_last_7d.by_workflow["architect"], 1.0, places=2)

    async def test_workflow_ranking_by_usage(self) -> None:
        """Test workflows are ranked by session count."""
        # Arrange
        sessions = [
            make_test_session("s1", workflow="code"),
            make_test_session("s2", workflow="code"),
            make_test_session("s3", workflow="code"),
            make_test_session("s4", workflow="architect"),
            make_test_session("s5", workflow="architect"),
            make_test_session("s6", workflow="debug"),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.features().list_features = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertGreaterEqual(len(result.top_workflows), 3)
        self.assertEqual(result.top_workflows[0].workflow_id, "code")
        self.assertEqual(result.top_workflows[0].session_count, 3)
        self.assertEqual(result.top_workflows[1].workflow_id, "architect")
        self.assertEqual(result.top_workflows[1].session_count, 2)

    async def test_success_rate_calculation(self) -> None:
        """Test workflow success rate is calculated correctly."""
        # Arrange
        sessions = [
            make_test_session("s1", status="completed", workflow="code"),
            make_test_session("s2", status="completed", workflow="code"),
            make_test_session("s3", status="failed", workflow="code"),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.features().list_features = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertEqual(len(result.top_workflows), 1)
        self.assertAlmostEqual(result.top_workflows[0].success_rate, 2/3, places=2)

    async def test_blocked_features_identification(self) -> None:
        """Test blocked features are correctly identified."""
        # Arrange
        features = [
            make_test_feature("feat-1", status="blocked"),
            make_test_feature("feat-2", status="in_progress"),
            make_test_feature("feat-3", status="blocked"),
        ]
        self.ports.storage.features().list_features = AsyncMock(return_value=features)
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertEqual(len(result.blocked_features), 2)
        self.assertIn("feat-1", result.blocked_features)
        self.assertIn("feat-3", result.blocked_features)

    async def test_sync_freshness_tracking(self) -> None:
        """Test sync freshness is tracked correctly."""
        # Arrange
        sync_time = utc_now() - timedelta(minutes=10)
        self.ports.storage.sync_state().get_last_sync_time = AsyncMock(
            return_value={"last_sync_at": sync_time}
        )
        self.ports.storage.features().list_features = AsyncMock(return_value=[])
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertEqual(result.sync_freshness, sync_time)
        self.assertIn("sync:checked", result.source_refs)

    async def test_sync_unavailable_fallback(self) -> None:
        """Test fallback when sync state is unavailable."""
        # Arrange
        self.ports.storage.sync_state().get_last_sync_time = AsyncMock(
            side_effect=Exception("Sync error")
        )
        self.ports.storage.features().list_features = AsyncMock(return_value=[])
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertIsNotNone(result.sync_freshness)
        self.assertIn("sync:unavailable", result.source_refs)

    async def test_data_freshness_from_oldest_session(self) -> None:
        """Test data freshness is computed from oldest session."""
        # Arrange
        now = utc_now()
        oldest = now - timedelta(days=5)
        sessions = [
            make_test_session("s1", started_at=now - timedelta(days=1)),
            make_test_session("s2", started_at=oldest),
            make_test_session("s3", started_at=now),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.features().list_features = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        
        # Assert
        self.assertEqual(result.data_freshness, oldest)

    async def test_dto_serialization_round_trip(self) -> None:
        """Test DTO can be serialized and deserialized."""
        # Arrange
        features = [make_test_feature("feat-1", status="in_progress")]
        sessions = [make_test_session("sess-1")]
        self.ports.storage.features().list_features = AsyncMock(return_value=features)
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_status(self.context, self.ports)
        dto_dict = result.model_dump()
        reconstructed = ProjectStatusDTO.model_validate(dto_dict)
        
        # Assert
        self.assertEqual(reconstructed.project_id, result.project_id)
        self.assertEqual(reconstructed.status, result.status)
        self.assertEqual(len(reconstructed.recent_sessions), len(result.recent_sessions))
        self.assertEqual(reconstructed.cost_last_7d.total, result.cost_last_7d.total)

    async def test_no_project_available_error_handling(self) -> None:
        """Test handling when no project is available."""
        # Arrange: Mock registry to return None (simulates no project scenario)
        self.ports.workspace_registry.get_active_project = lambda: None
        self.ports.workspace_registry.get_project = lambda project_id: None
        
        # Act - Use override to trigger the no-project path
        result = await self.service.get_status(self.context, self.ports, project_id_override="nonexistent")
        
        # Assert - When project lookup fails completely, service returns error status
        self.assertIsInstance(result, ProjectStatusDTO)
        self.assertEqual(result.project_id, "unknown")
        self.assertIn("error:no_project_available", result.source_refs)


if __name__ == "__main__":
    unittest.main()

# Made with Bob
