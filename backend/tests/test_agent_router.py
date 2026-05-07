import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.application.services.agent_queries import (
    AARReportDTO,
    ArtifactRankingsDTO,
    ArtifactRecommendationsDTO,
    FeatureForensicsDTO,
    ProjectStatusDTO,
    SnapshotDiagnosticsDTO,
    WorkflowDiagnosticsDTO,
)
from backend.routers import agent as agent_router
from backend.runtime.bootstrap import build_runtime_app


class AgentRouterTests(unittest.IsolatedAsyncioTestCase):
    def test_router_registration_exposes_api_agent_paths(self) -> None:
        app = build_runtime_app("test")
        paths = app.openapi()["paths"]

        self.assertIn("/api/agent/project-status", paths)
        self.assertIn("/api/agent/feature-forensics/{feature_id}", paths)
        self.assertIn("/api/agent/workflow-diagnostics", paths)
        self.assertIn("/api/agent/artifact-intelligence/snapshot-diagnostics", paths)
        self.assertIn("/api/agent/artifact-intelligence/rankings", paths)
        self.assertIn("/api/agent/artifact-intelligence/recommendations", paths)
        self.assertIn("/api/agent/reports/aar", paths)
        self.assertIn("get", paths["/api/agent/project-status"])
        self.assertIn("get", paths["/api/agent/feature-forensics/{feature_id}"])
        self.assertIn("get", paths["/api/agent/workflow-diagnostics"])
        self.assertIn("get", paths["/api/agent/artifact-intelligence/snapshot-diagnostics"])
        self.assertIn("get", paths["/api/agent/artifact-intelligence/rankings"])
        self.assertIn("get", paths["/api/agent/artifact-intelligence/recommendations"])
        self.assertIn("post", paths["/api/agent/reports/aar"])

    async def test_get_project_status_delegates_once_and_returns_dto_unchanged(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = ProjectStatusDTO(project_id="project-1", project_name="Project 1", source_refs=["project-1"])

        with patch.object(agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)) as resolve_mock:
            with patch.object(
                agent_router.project_status_query_service,
                "get_status",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_router.get_project_status(
                    project_id="project-1",
                    bypass_cache=False,
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertIs(result, dto)
        resolve_mock.assert_awaited_once_with(
            request_context,
            core_ports,
            requested_project_id="project-1",
        )
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            project_id_override="project-1",
            bypass_cache=False,
        )

    async def test_get_feature_forensics_delegates_once_and_returns_dto_unchanged(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = FeatureForensicsDTO(feature_id="feature-1", feature_slug="feature-one", source_refs=["feature-1"])

        with patch.object(agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)) as resolve_mock:
            with patch.object(
                agent_router.feature_forensics_query_service,
                "get_forensics",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_router.get_feature_forensics(
                    feature_id="feature-1",
                    bypass_cache=False,
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertIs(result, dto)
        resolve_mock.assert_awaited_once_with(request_context, core_ports)
        service_mock.assert_awaited_once_with(
            app_request.context, app_request.ports, "feature-1", bypass_cache=False
        )

    async def test_get_workflow_diagnostics_delegates_once_and_returns_dto_unchanged(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = WorkflowDiagnosticsDTO(project_id="project-1", feature_id="feature-2", source_refs=["feature-2"])

        with patch.object(agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)) as resolve_mock:
            with patch.object(
                agent_router.workflow_diagnostics_query_service,
                "get_diagnostics",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_router.get_workflow_diagnostics(
                    feature_id="feature-2",
                    bypass_cache=False,
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertIs(result, dto)
        resolve_mock.assert_awaited_once_with(request_context, core_ports)
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            feature_id="feature-2",
            bypass_cache=False,
        )

    async def test_get_artifact_snapshot_diagnostics_delegates_once_and_returns_dto_unchanged(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = SnapshotDiagnosticsDTO(project_id="project-1", snapshot_age_seconds=120, source_refs=["project-1"])

        with patch.object(agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)) as resolve_mock:
            with patch.object(
                agent_router.artifact_intelligence_query_service,
                "get_snapshot_diagnostics",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_router.get_artifact_snapshot_diagnostics(
                    project_id="project-1",
                    bypass_cache=False,
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertIs(result, dto)
        resolve_mock.assert_awaited_once_with(
            request_context,
            core_ports,
            requested_project_id="project-1",
        )
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            project_id_override="project-1",
            bypass_cache=False,
        )

    async def test_get_artifact_rankings_delegates_once_and_returns_dto_unchanged(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = ArtifactRankingsDTO(project_id="project-1", total=1, rows=[{"artifact_id": "skill-a"}])

        with patch.object(agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)) as resolve_mock:
            with patch.object(
                agent_router.artifact_intelligence_query_service,
                "get_rankings",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_router.get_artifact_rankings(
                    project_id="project-1",
                    period="30d",
                    collection_id="collection-a",
                    user_scope="user-a",
                    artifact_uuid="uuid-a",
                    artifact_id=None,
                    version_id="v1",
                    workflow_id="workflow-a",
                    artifact_type="skill",
                    recommendation_type="optimization_target",
                    limit=25,
                    bypass_cache=False,
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertIs(result, dto)
        resolve_mock.assert_awaited_once_with(request_context, core_ports, requested_project_id="project-1")
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            project_id_override="project-1",
            period="30d",
            collection_id="collection-a",
            user_scope="user-a",
            artifact_uuid="uuid-a",
            artifact_id=None,
            version_id="v1",
            workflow_id="workflow-a",
            artifact_type="skill",
            recommendation_type="optimization_target",
            limit=25,
            bypass_cache=False,
        )

    async def test_get_artifact_recommendations_delegates_once_and_returns_dto_unchanged(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = ArtifactRecommendationsDTO(
            project_id="project-1",
            total=1,
            recommendations=[{"type": "optimization_target"}],
        )

        with patch.object(agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)) as resolve_mock:
            with patch.object(
                agent_router.artifact_intelligence_query_service,
                "get_recommendations",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_router.get_artifact_recommendations(
                    project_id="project-1",
                    period="30d",
                    collection_id="collection-a",
                    user_scope="user-a",
                    workflow_id="workflow-a",
                    recommendation_type="optimization_target",
                    min_confidence=0.7,
                    limit=50,
                    bypass_cache=False,
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertIs(result, dto)
        resolve_mock.assert_awaited_once_with(request_context, core_ports, requested_project_id="project-1")
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            project_id_override="project-1",
            period="30d",
            collection_id="collection-a",
            user_scope="user-a",
            workflow_id="workflow-a",
            recommendation_type="optimization_target",
            min_confidence=0.7,
            limit=50,
            bypass_cache=False,
        )

    async def test_generate_aar_report_delegates_once_and_only_forwards_feature_id(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = AARReportDTO(feature_id="feature-3", feature_slug="feature-three", source_refs=["feature-3"])
        req = agent_router.AARReportRequest(feature_id="feature-3")

        with patch.object(agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)) as resolve_mock:
            with patch.object(
                agent_router.reporting_query_service,
                "generate_aar",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_router.generate_aar_report(
                    req=req,
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertEqual(req.model_dump(), {"feature_id": "feature-3", "bypass_cache": False})
        self.assertIs(result, dto)
        resolve_mock.assert_awaited_once_with(request_context, core_ports)
        service_mock.assert_awaited_once_with(
            app_request.context, app_request.ports, "feature-3", bypass_cache=False
        )

    async def test_http_exception_from_request_resolution_is_propagated(self) -> None:
        request_context = object()
        core_ports = object()

        with patch.object(
            agent_router,
            "_resolve_app_request",
            new=AsyncMock(side_effect=HTTPException(status_code=404, detail="No active project")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await agent_router.get_project_status(
                    project_id=None,
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "No active project")


if __name__ == "__main__":
    unittest.main()
