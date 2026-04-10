"""Unit tests for FeatureForensicsQueryService."""

import unittest
from datetime import timedelta
from unittest.mock import AsyncMock

from backend.application.services.agent_queries.feature_forensics import FeatureForensicsQueryService
from backend.application.services.agent_queries.models import FeatureForensicsDTO
from backend.tests.fixtures.agent_queries_fixtures import (
    make_mock_ports,
    make_request_context,
    make_test_document,
    make_test_feature,
    make_test_session,
    make_test_task,
    utc_now,
)


class FeatureForensicsQueryServiceTests(unittest.IsolatedAsyncioTestCase):
    """Test suite for FeatureForensicsQueryService."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.service = FeatureForensicsQueryService()
        self.context = make_request_context("test-project")
        self.ports = make_mock_ports("test-project")

    async def test_happy_path_with_complete_data(self) -> None:
        """Test service with complete feature forensics data."""
        # Arrange
        feature = make_test_feature("feat-1", "feat-1", "in_progress")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        # Mock linked sessions
        sessions = [
            make_test_session("s1", "completed", "code", 2.0, 5000, 600),
            make_test_session("s2", "completed", "code", 1.5, 3000, 400),
            make_test_session("s3", "failed", "architect", 0.5, 1000, 200, error_message="Timeout error"),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Mock linked documents
        documents = [
            make_test_document("doc-1", "docs/plan.md", "Feature Plan", "plan"),
            make_test_document("doc-2", "docs/spec.md", "Technical Spec", "spec"),
        ]
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=documents)
        
        # Mock linked tasks
        tasks = [
            make_test_task("task-1", "Implement feature", "done"),
            make_test_task("task-2", "Write tests", "in_progress"),
        ]
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=tasks)
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertIsInstance(result, FeatureForensicsDTO)
        self.assertEqual(result.feature_id, "feat-1")
        self.assertEqual(result.feature_slug, "feat-1")
        self.assertEqual(result.status, "in_progress")
        
        # Linked entities
        self.assertEqual(len(result.linked_sessions), 3)
        self.assertEqual(len(result.linked_documents), 2)
        self.assertEqual(len(result.linked_tasks), 2)
        
        # Metrics
        self.assertEqual(result.iteration_count, 3)
        self.assertAlmostEqual(result.total_cost, 4.0, places=2)
        self.assertEqual(result.total_tokens, 9000)
        
        # Workflow mix
        self.assertIn("code", result.workflow_mix)
        self.assertIn("architect", result.workflow_mix)
        self.assertAlmostEqual(result.workflow_mix["code"], 2/3, places=2)
        self.assertAlmostEqual(result.workflow_mix["architect"], 1/3, places=2)
        
        # Failure patterns
        self.assertEqual(len(result.failure_patterns), 1)
        self.assertIn("Timeout error", result.failure_patterns[0])
        
        # Representative sessions
        self.assertGreater(len(result.representative_sessions), 0)
        
        # Summary narrative
        self.assertIn("feat-1", result.summary_narrative)
        self.assertIn("3 development iterations", result.summary_narrative)

    async def test_feature_not_found(self) -> None:
        """Test handling when feature does not exist."""
        # Arrange
        self.ports.storage.features().get_feature = AsyncMock(return_value=None)
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "nonexistent")
        
        # Assert
        self.assertEqual(result.feature_id, "nonexistent")
        self.assertEqual(result.feature_slug, "not_found")
        self.assertEqual(result.status, "error")
        self.assertIn("error:feature_not_found", result.source_refs)

    async def test_feature_fetch_error(self) -> None:
        """Test handling when feature fetch fails."""
        # Arrange
        self.ports.storage.features().get_feature = AsyncMock(
            side_effect=Exception("Database error")
        )
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertEqual(result.feature_id, "feat-1")
        self.assertEqual(result.feature_slug, "error")
        self.assertEqual(result.status, "error")
        self.assertIn("error:feature_fetch=", result.source_refs[0])

    async def test_partial_degradation_sessions_unavailable(self) -> None:
        """Test graceful degradation when sessions are unavailable."""
        # Arrange
        feature = make_test_feature("feat-1", "feat-1", "in_progress")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(
            side_effect=Exception("Sessions error")
        )
        
        # Documents and tasks still work
        documents = [make_test_document("doc-1")]
        tasks = [make_test_task("task-1")]
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=documents)
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=tasks)
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertEqual(result.feature_id, "feat-1")
        self.assertIn("sessions:error=", result.source_refs[1])
        self.assertEqual(len(result.linked_sessions), 0)
        self.assertEqual(len(result.linked_documents), 1)  # Still works
        self.assertEqual(len(result.linked_tasks), 1)  # Still works

    async def test_partial_degradation_documents_unavailable(self) -> None:
        """Test graceful degradation when documents are unavailable."""
        # Arrange
        feature = make_test_feature("feat-1", "feat-1", "in_progress")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [make_test_session("s1")]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(
            side_effect=Exception("Documents error")
        )
        
        tasks = [make_test_task("task-1")]
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=tasks)
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertIn("documents:error=", result.source_refs[2])
        self.assertEqual(len(result.linked_sessions), 1)  # Still works
        self.assertEqual(len(result.linked_documents), 0)
        self.assertEqual(len(result.linked_tasks), 1)  # Still works

    async def test_empty_data_returns_valid_dto(self) -> None:
        """Test service handles feature with no linked entities."""
        # Arrange
        feature = make_test_feature("feat-1", "feat-1", "todo")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=[])
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=[])
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertEqual(result.feature_id, "feat-1")
        self.assertEqual(result.status, "todo")
        self.assertEqual(result.iteration_count, 0)
        self.assertEqual(result.total_cost, 0.0)
        self.assertEqual(len(result.linked_sessions), 0)
        self.assertEqual(len(result.workflow_mix), 0)

    async def test_iteration_count_computation(self) -> None:
        """Test iteration count equals number of sessions."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [make_test_session(f"s{i}") for i in range(7)]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=[])
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertEqual(result.iteration_count, 7)

    async def test_cost_and_token_aggregation(self) -> None:
        """Test cost and token metrics are correctly aggregated."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", cost=1.5, tokens=3000),
            make_test_session("s2", cost=2.0, tokens=4000),
            make_test_session("s3", cost=0.5, tokens=1000),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=[])
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertAlmostEqual(result.total_cost, 4.0, places=2)
        self.assertEqual(result.total_tokens, 8000)

    async def test_workflow_mix_percentages_sum_to_one(self) -> None:
        """Test workflow mix percentages sum to 100%."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", workflow="code"),
            make_test_session("s2", workflow="code"),
            make_test_session("s3", workflow="architect"),
            make_test_session("s4", workflow="debug"),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=[])
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        total_percentage = sum(result.workflow_mix.values())
        self.assertAlmostEqual(total_percentage, 1.0, places=2)
        self.assertAlmostEqual(result.workflow_mix["code"], 0.5, places=2)
        self.assertAlmostEqual(result.workflow_mix["architect"], 0.25, places=2)
        self.assertAlmostEqual(result.workflow_mix["debug"], 0.25, places=2)

    async def test_rework_signal_high_iteration_count(self) -> None:
        """Test rework signal is detected for high iteration count."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [make_test_session(f"s{i}") for i in range(8)]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=[])
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertGreater(len(result.rework_signals), 0)
        self.assertTrue(any("high_iteration_count" in signal for signal in result.rework_signals))

    async def test_rework_signal_high_failure_rate(self) -> None:
        """Test rework signal is detected for high failure rate."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", status="failed"),
            make_test_session("s2", status="failed"),
            make_test_session("s3", status="completed"),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=[])
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertGreater(len(result.rework_signals), 0)
        self.assertTrue(any("high_failure_rate" in signal for signal in result.rework_signals))

    async def test_failure_pattern_extraction(self) -> None:
        """Test failure patterns are extracted from failed sessions."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", status="failed", error_message="Timeout connecting to API"),
            make_test_session("s2", status="failed", error_message="Permission denied"),
            make_test_session("s3", status="completed"),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=[])
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertEqual(len(result.failure_patterns), 2)
        self.assertIn("Timeout connecting to API", result.failure_patterns[0])
        self.assertIn("Permission denied", result.failure_patterns[1])

    async def test_representative_session_selection(self) -> None:
        """Test representative sessions include first, last, and highest cost."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        now = utc_now()
        sessions = [
            make_test_session("first", cost=1.0, started_at=now - timedelta(days=5)),
            make_test_session("middle", cost=5.0, started_at=now - timedelta(days=3)),
            make_test_session("last", cost=1.5, started_at=now - timedelta(days=1)),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=[])
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertEqual(len(result.representative_sessions), 3)
        session_ids = [s.session_id for s in result.representative_sessions]
        self.assertIn("first", session_ids)
        self.assertIn("last", session_ids)
        self.assertIn("middle", session_ids)  # Highest cost

    async def test_summary_narrative_generation(self) -> None:
        """Test summary narrative includes key information."""
        # Arrange
        feature = make_test_feature("feat-1", slug="user-authentication")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [
            make_test_session("s1", workflow="code", cost=2.5),
            make_test_session("s2", workflow="code", cost=1.5),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=[])
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        narrative = result.summary_narrative
        self.assertIn("user-authentication", narrative)
        self.assertIn("2 development iterations", narrative)
        self.assertIn("$4.00", narrative)
        self.assertIn("code", narrative)

    async def test_data_freshness_from_oldest_session(self) -> None:
        """Test data freshness is computed from oldest session."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        now = utc_now()
        oldest = now - timedelta(days=10)
        sessions = [
            make_test_session("s1", started_at=now - timedelta(days=2)),
            make_test_session("s2", started_at=oldest),
            make_test_session("s3", started_at=now),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=[])
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        
        # Assert
        self.assertEqual(result.data_freshness, oldest)

    async def test_dto_serialization_round_trip(self) -> None:
        """Test DTO can be serialized and deserialized."""
        # Arrange
        feature = make_test_feature("feat-1")
        self.ports.storage.features().get_feature = AsyncMock(return_value=feature)
        
        sessions = [make_test_session("s1", workflow="code", cost=1.5)]
        documents = [make_test_document("doc-1")]
        tasks = [make_test_task("task-1")]
        
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        self.ports.storage.entity_links().get_feature_documents = AsyncMock(return_value=documents)
        self.ports.storage.entity_links().get_feature_tasks = AsyncMock(return_value=tasks)
        
        # Act
        result = await self.service.get_forensics(self.context, self.ports, "feat-1")
        dto_dict = result.model_dump()
        reconstructed = FeatureForensicsDTO.model_validate(dto_dict)
        
        # Assert
        self.assertEqual(reconstructed.feature_id, result.feature_id)
        self.assertEqual(reconstructed.status, result.status)
        self.assertEqual(len(reconstructed.linked_sessions), len(result.linked_sessions))
        self.assertEqual(reconstructed.total_cost, result.total_cost)
        self.assertEqual(len(reconstructed.workflow_mix), len(result.workflow_mix))


if __name__ == "__main__":
    unittest.main()

# Made with Bob
