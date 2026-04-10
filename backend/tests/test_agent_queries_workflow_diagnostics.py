"""Unit tests for WorkflowDiagnosticsQueryService."""

import unittest
from unittest.mock import AsyncMock

from backend.application.services.agent_queries.models import WorkflowDiagnosticsDTO
from backend.application.services.agent_queries.workflow_intelligence import WorkflowDiagnosticsQueryService
from backend.tests.fixtures.agent_queries_fixtures import (
    make_mock_ports,
    make_request_context,
    make_test_session,
)


class WorkflowDiagnosticsQueryServiceTests(unittest.IsolatedAsyncioTestCase):
    """Test suite for WorkflowDiagnosticsQueryService."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.service = WorkflowDiagnosticsQueryService()
        self.context = make_request_context("test-project")
        self.ports = make_mock_ports("test-project")

    async def test_happy_path_project_scope(self) -> None:
        """Test service with project-scoped workflow analysis."""
        # Arrange
        sessions = [
            make_test_session("s1", "completed", "code", 2.0, 5000, 600),
            make_test_session("s2", "completed", "code", 1.5, 3000, 400),
            make_test_session("s3", "failed", "code", 0.5, 1000, 200, error_message="Timeout"),
            make_test_session("s4", "completed", "architect", 1.0, 2000, 300),
            make_test_session("s5", "completed", "debug", 0.8, 1500, 250),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert
        self.assertIsInstance(result, WorkflowDiagnosticsDTO)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.project_id, "test-project")
        
        # Workflows analyzed
        self.assertEqual(len(result.workflows), 3)
        workflow_ids = [w.workflow_id for w in result.workflows]
        self.assertIn("code", workflow_ids)
        self.assertIn("architect", workflow_ids)
        self.assertIn("debug", workflow_ids)
        
        # Top performers
        self.assertGreater(len(result.top_performers), 0)
        self.assertLessEqual(len(result.top_performers), 3)
        
        # Problem workflows
        self.assertGreaterEqual(len(result.problem_workflows), 0)

    async def test_happy_path_feature_scope(self) -> None:
        """Test service with feature-scoped workflow analysis."""
        # Arrange
        sessions = [
            make_test_session("s1", "completed", "code", 1.0, 2000, 300),
            make_test_session("s2", "completed", "architect", 0.5, 1000, 200),
        ]
        self.ports.storage.entity_links().get_feature_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports, feature_id="feat-1")
        
        # Assert
        self.assertEqual(result.status, "ok")
        self.assertIn("scope:feature=feat-1", result.source_refs)
        self.assertEqual(len(result.workflows), 2)

    async def test_partial_degradation_sessions_unavailable(self) -> None:
        """Test graceful degradation when sessions are unavailable."""
        # Arrange
        self.ports.storage.sessions().list_sessions = AsyncMock(
            side_effect=Exception("Database error")
        )
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert
        self.assertEqual(result.status, "partial")
        # Check that error is in source_refs (may be at different index)
        self.assertTrue(any("sessions:error=" in ref for ref in result.source_refs))
        self.assertEqual(len(result.workflows), 0)

    async def test_empty_data_returns_valid_dto(self) -> None:
        """Test service handles empty session data."""
        # Arrange
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=[])
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.workflows), 0)
        self.assertEqual(len(result.top_performers), 0)
        self.assertEqual(len(result.problem_workflows), 0)

    async def test_effectiveness_score_calculation(self) -> None:
        """Test effectiveness score is calculated correctly."""
        # Arrange
        sessions = [
            make_test_session("s1", "completed", "code", 1.0, 2000, 1800),  # Success, moderate cost, slow
            make_test_session("s2", "completed", "code", 1.0, 2000, 1800),
            make_test_session("s3", "failed", "code", 0.5, 1000, 900),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert
        code_workflow = next(w for w in result.workflows if w.workflow_id == "code")
        self.assertGreater(code_workflow.effectiveness_score, 0.0)
        self.assertLessEqual(code_workflow.effectiveness_score, 1.0)
        # Success rate is 2/3, so effectiveness should reflect that
        self.assertGreater(code_workflow.effectiveness_score, 0.3)

    async def test_success_failure_ratio_computation(self) -> None:
        """Test success and failure counts are computed correctly."""
        # Arrange
        sessions = [
            make_test_session("s1", "completed", "code"),
            make_test_session("s2", "completed", "code"),
            make_test_session("s3", "failed", "code"),
            make_test_session("s4", "error", "code"),
            make_test_session("s5", "cancelled", "code"),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert
        code_workflow = result.workflows[0]
        self.assertEqual(code_workflow.session_count, 5)
        self.assertEqual(code_workflow.success_count, 2)
        self.assertEqual(code_workflow.failure_count, 3)

    async def test_cost_efficiency_metrics(self) -> None:
        """Test cost efficiency is computed correctly."""
        # Arrange
        sessions = [
            make_test_session("s1", "completed", "cheap", 0.1, 500, 300),
            make_test_session("s2", "completed", "expensive", 10.0, 20000, 300),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert
        cheap = next(w for w in result.workflows if w.workflow_id == "cheap")
        expensive = next(w for w in result.workflows if w.workflow_id == "expensive")
        # Cheaper workflow should have higher cost efficiency
        self.assertGreater(cheap.cost_efficiency, expensive.cost_efficiency)

    async def test_top_performers_identification(self) -> None:
        """Test top performers are identified by effectiveness score."""
        # Arrange
        sessions = [
            # High effectiveness: high success, low cost, fast
            make_test_session("s1", "completed", "excellent", 0.5, 1000, 300),
            make_test_session("s2", "completed", "excellent", 0.5, 1000, 300),
            # Medium effectiveness
            make_test_session("s3", "completed", "good", 2.0, 4000, 1800),
            make_test_session("s4", "failed", "good", 1.0, 2000, 900),
            # Low effectiveness: many failures
            make_test_session("s5", "failed", "poor", 1.0, 2000, 600),
            make_test_session("s6", "failed", "poor", 1.0, 2000, 600),
            make_test_session("s7", "completed", "poor", 1.0, 2000, 600),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert
        self.assertGreater(len(result.top_performers), 0)
        self.assertLessEqual(len(result.top_performers), 3)
        # Top performer should be "excellent"
        self.assertEqual(result.top_performers[0].workflow_id, "excellent")

    async def test_problem_workflows_identification(self) -> None:
        """Test problem workflows are identified correctly."""
        # Arrange
        sessions = [
            # Good workflow
            make_test_session("s1", "completed", "good", 1.0, 2000, 300),
            make_test_session("s2", "completed", "good", 1.0, 2000, 300),
            # Problem workflow: high failure rate, low effectiveness
            make_test_session("s3", "failed", "problematic", 1.0, 2000, 600),
            make_test_session("s4", "failed", "problematic", 1.0, 2000, 600),
            make_test_session("s5", "failed", "problematic", 1.0, 2000, 600),
            make_test_session("s6", "completed", "problematic", 1.0, 2000, 600),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert
        self.assertGreater(len(result.problem_workflows), 0)
        problem_ids = [w.workflow_id for w in result.problem_workflows]
        self.assertIn("problematic", problem_ids)

    async def test_common_failures_extraction(self) -> None:
        """Test common failure patterns are extracted."""
        # Arrange
        sessions = [
            make_test_session("s1", "failed", "code", error_message="Timeout error"),
            make_test_session("s2", "failed", "code", error_message="Timeout error"),
            make_test_session("s3", "failed", "code", error_message="Permission denied"),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert
        code_workflow = result.workflows[0]
        self.assertGreater(len(code_workflow.common_failures), 0)
        self.assertIn("Timeout error", code_workflow.common_failures)

    async def test_representative_sessions_selection(self) -> None:
        """Test representative sessions are selected (first 3)."""
        # Arrange
        sessions = [
            make_test_session("s1", "completed", "code"),
            make_test_session("s2", "completed", "code"),
            make_test_session("s3", "completed", "code"),
            make_test_session("s4", "completed", "code"),
            make_test_session("s5", "completed", "code"),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert
        code_workflow = result.workflows[0]
        self.assertEqual(len(code_workflow.representative_sessions), 3)
        self.assertEqual(code_workflow.representative_sessions[0].session_id, "s1")
        self.assertEqual(code_workflow.representative_sessions[1].session_id, "s2")
        self.assertEqual(code_workflow.representative_sessions[2].session_id, "s3")

    async def test_workflows_sorted_by_effectiveness(self) -> None:
        """Test workflows are sorted by effectiveness score."""
        # Arrange
        sessions = [
            make_test_session("s1", "completed", "best", 0.5, 1000, 300),
            make_test_session("s2", "completed", "best", 0.5, 1000, 300),
            make_test_session("s3", "completed", "medium", 2.0, 4000, 1800),
            make_test_session("s4", "failed", "worst", 3.0, 6000, 3600),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert
        self.assertEqual(len(result.workflows), 3)
        # Workflows should be sorted by effectiveness (descending)
        for i in range(len(result.workflows) - 1):
            self.assertGreaterEqual(
                result.workflows[i].effectiveness_score,
                result.workflows[i + 1].effectiveness_score
            )

    async def test_data_freshness_from_oldest_session(self) -> None:
        """Test data freshness is computed from oldest session."""
        # Arrange
        from datetime import timedelta
        from backend.tests.fixtures.agent_queries_fixtures import utc_now
        
        now = utc_now()
        oldest = now - timedelta(days=10)
        sessions = [
            make_test_session("s1", started_at=now - timedelta(days=2)),
            make_test_session("s2", started_at=oldest),
            make_test_session("s3", started_at=now),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert
        self.assertEqual(result.data_freshness, oldest)

    async def test_dto_serialization_round_trip(self) -> None:
        """Test DTO can be serialized and deserialized."""
        # Arrange
        sessions = [
            make_test_session("s1", "completed", "code", 1.0, 2000, 300),
            make_test_session("s2", "failed", "code", 0.5, 1000, 200),
        ]
        self.ports.storage.sessions().list_sessions = AsyncMock(return_value=sessions)
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        dto_dict = result.model_dump()
        reconstructed = WorkflowDiagnosticsDTO.model_validate(dto_dict)
        
        # Assert
        self.assertEqual(reconstructed.project_id, result.project_id)
        self.assertEqual(reconstructed.status, result.status)
        self.assertEqual(len(reconstructed.workflows), len(result.workflows))
        self.assertEqual(
            reconstructed.workflows[0].effectiveness_score,
            result.workflows[0].effectiveness_score
        )

    async def test_no_project_available_error_handling(self) -> None:
        """Test handling when no project is available."""
        # Arrange: Mock registry to return None
        self.ports.workspace_registry.get_active_project = lambda: None
        self.ports.workspace_registry.get_project = lambda project_id: None
        
        # Act
        result = await self.service.get_diagnostics(self.context, self.ports)
        
        # Assert - Service should handle gracefully and use context project as fallback
        # Since context has a valid project, it won't return error status
        self.assertIsInstance(result, WorkflowDiagnosticsDTO)
        self.assertEqual(result.project_id, "test-project")  # Falls back to context project


if __name__ == "__main__":
    unittest.main()

# Made with Bob
