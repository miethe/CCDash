"""Tests for PCP-202 planning REST endpoints (backend/routers/agent.py).

Mirrors the style of test_agent_router.py:
- IsolatedAsyncioTestCase for async handlers
- patch.object on the module-level service singleton and _resolve_app_request
- Assert delegation, not derivation
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.application.services.agent_queries import (
    FeaturePlanningContextDTO,
    PhaseOperationsDTO,
    ProjectPlanningGraphDTO,
    ProjectPlanningSummaryDTO,
)
from backend.routers import agent as agent_router
from backend.runtime.bootstrap import build_runtime_app


class PlanningRouterRegistrationTests(unittest.TestCase):
    """Verify that all four planning endpoints appear in the OpenAPI schema."""

    def test_planning_endpoints_are_registered(self) -> None:
        app = build_runtime_app("test")
        paths = app.openapi()["paths"]

        self.assertIn("/api/agent/planning/summary", paths)
        self.assertIn("/api/agent/planning/graph", paths)
        self.assertIn("/api/agent/planning/features/{feature_id}", paths)
        self.assertIn(
            "/api/agent/planning/features/{feature_id}/phases/{phase_number}",
            paths,
        )

        self.assertIn("get", paths["/api/agent/planning/summary"])
        self.assertIn("get", paths["/api/agent/planning/graph"])
        self.assertIn("get", paths["/api/agent/planning/features/{feature_id}"])
        self.assertIn(
            "get",
            paths["/api/agent/planning/features/{feature_id}/phases/{phase_number}"],
        )


class GetPlanningSummaryTests(unittest.IsolatedAsyncioTestCase):
    """GET /api/agent/planning/summary"""

    async def test_happy_path_delegates_and_returns_dto(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = ProjectPlanningSummaryDTO(
            project_id="proj-1",
            project_name="Project One",
            source_refs=["proj-1"],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ) as resolve_mock:
            with patch.object(
                agent_router.planning_query_service,
                "get_project_planning_summary",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_router.get_planning_summary(
                    project_id="proj-1",
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertIs(result, dto)
        resolve_mock.assert_awaited_once_with(
            request_context,
            core_ports,
            requested_project_id="proj-1",
        )
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            project_id_override="proj-1",
        )

    async def test_project_id_none_passes_through(self) -> None:
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = ProjectPlanningSummaryDTO(project_id="default-proj", source_refs=[])

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_project_planning_summary",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_router.get_planning_summary(
                    project_id=None,
                    request_context=object(),
                    core_ports=object(),
                )

        self.assertIs(result, dto)
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            project_id_override=None,
        )


class GetPlanningGraphTests(unittest.IsolatedAsyncioTestCase):
    """GET /api/agent/planning/graph"""

    async def test_happy_path_returns_dto_unchanged(self) -> None:
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = ProjectPlanningGraphDTO(
            project_id="proj-1",
            feature_id="feat-1",
            depth=2,
            nodes=[{"id": "n1"}],
            edges=[],
            source_refs=["proj-1"],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_project_planning_graph",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_router.get_planning_graph(
                    project_id="proj-1",
                    feature_id="feat-1",
                    depth=2,
                    request_context=object(),
                    core_ports=object(),
                )

        self.assertIs(result, dto)
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            project_id_override="proj-1",
            feature_id="feat-1",
            depth=2,
        )

    async def test_missing_feature_raises_404(self) -> None:
        """Service returns status=error + empty nodes when feature_id is not found."""
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = ProjectPlanningGraphDTO(
            project_id="proj-1",
            feature_id="missing-feat",
            status="error",
            nodes=[],
            source_refs=["missing-feat"],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_project_planning_graph",
                new=AsyncMock(return_value=dto),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    await agent_router.get_planning_graph(
                        project_id=None,
                        feature_id="missing-feat",
                        depth=None,
                        request_context=object(),
                        core_ports=object(),
                    )

        self.assertEqual(ctx.exception.status_code, 404)

    async def test_error_status_without_feature_id_does_not_raise(self) -> None:
        """Project-scope graph errors (no feature_id filter) should not 404."""
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = ProjectPlanningGraphDTO(
            project_id="proj-1",
            status="error",
            nodes=[],
            source_refs=[],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_project_planning_graph",
                new=AsyncMock(return_value=dto),
            ):
                # Should not raise; 404 logic only applies when feature_id was supplied.
                result = await agent_router.get_planning_graph(
                    project_id=None,
                    feature_id=None,
                    depth=None,
                    request_context=object(),
                    core_ports=object(),
                )

        self.assertIs(result, dto)


class GetFeaturePlanningContextTests(unittest.IsolatedAsyncioTestCase):
    """GET /api/agent/planning/features/{feature_id}"""

    async def test_happy_path_returns_dto_unchanged(self) -> None:
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = FeaturePlanningContextDTO(
            feature_id="feat-1",
            feature_name="Feature One",
            source_refs=["feat-1"],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_feature_planning_context",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_router.get_feature_planning_context(
                    feature_id="feat-1",
                    project_id="proj-1",
                    request_context=object(),
                    core_ports=object(),
                )

        self.assertIs(result, dto)
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            feature_id="feat-1",
            project_id_override="proj-1",
        )

    async def test_missing_feature_raises_404(self) -> None:
        """Service returns status=error + empty feature_name for unknown features."""
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = FeaturePlanningContextDTO(
            feature_id="ghost-feat",
            feature_name="",
            status="error",
            source_refs=["ghost-feat"],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_feature_planning_context",
                new=AsyncMock(return_value=dto),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    await agent_router.get_feature_planning_context(
                        feature_id="ghost-feat",
                        project_id=None,
                        request_context=object(),
                        core_ports=object(),
                    )

        self.assertEqual(ctx.exception.status_code, 404)

    async def test_project_id_override_forwarded(self) -> None:
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = FeaturePlanningContextDTO(
            feature_id="feat-2",
            feature_name="Feature Two",
            source_refs=[],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ) as resolve_mock:
            with patch.object(
                agent_router.planning_query_service,
                "get_feature_planning_context",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                await agent_router.get_feature_planning_context(
                    feature_id="feat-2",
                    project_id="override-proj",
                    request_context=object(),
                    core_ports=object(),
                )

        resolve_mock.assert_awaited_once_with(
            unittest.mock.ANY,
            unittest.mock.ANY,
            requested_project_id="override-proj",
        )
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            feature_id="feat-2",
            project_id_override="override-proj",
        )


class GetPhaseOperationsTests(unittest.IsolatedAsyncioTestCase):
    """GET /api/agent/planning/features/{feature_id}/phases/{phase_number}"""

    async def test_happy_path_returns_dto_unchanged(self) -> None:
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = PhaseOperationsDTO(
            feature_id="feat-1",
            phase_number=2,
            phase_token="2",
            phase_title="Implementation",
            source_refs=["feat-1"],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_phase_operations",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_router.get_phase_operations(
                    feature_id="feat-1",
                    phase_number=2,
                    project_id="proj-1",
                    request_context=object(),
                    core_ports=object(),
                )

        self.assertIs(result, dto)
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            feature_id="feat-1",
            phase_number=2,
            project_id_override="proj-1",
        )

    async def test_missing_phase_raises_404(self) -> None:
        """status=error + empty phase_token means the phase was not found."""
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = PhaseOperationsDTO(
            feature_id="feat-1",
            phase_number=99,
            phase_token="",
            status="error",
            source_refs=["feat-1"],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_phase_operations",
                new=AsyncMock(return_value=dto),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    await agent_router.get_phase_operations(
                        feature_id="feat-1",
                        phase_number=99,
                        project_id=None,
                        request_context=object(),
                        core_ports=object(),
                    )

        self.assertEqual(ctx.exception.status_code, 404)

    async def test_missing_feature_raises_404(self) -> None:
        """When the feature itself is not found the service also returns error + empty phase_token."""
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = PhaseOperationsDTO(
            feature_id="ghost-feat",
            phase_number=1,
            phase_token="",
            status="error",
            source_refs=["ghost-feat"],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                agent_router.planning_query_service,
                "get_phase_operations",
                new=AsyncMock(return_value=dto),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    await agent_router.get_phase_operations(
                        feature_id="ghost-feat",
                        phase_number=1,
                        project_id=None,
                        request_context=object(),
                        core_ports=object(),
                    )

        self.assertEqual(ctx.exception.status_code, 404)

    async def test_project_id_override_forwarded(self) -> None:
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = PhaseOperationsDTO(
            feature_id="feat-1",
            phase_number=1,
            phase_token="1",
            source_refs=[],
        )

        with patch.object(
            agent_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ) as resolve_mock:
            with patch.object(
                agent_router.planning_query_service,
                "get_phase_operations",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                await agent_router.get_phase_operations(
                    feature_id="feat-1",
                    phase_number=1,
                    project_id="custom-proj",
                    request_context=object(),
                    core_ports=object(),
                )

        resolve_mock.assert_awaited_once_with(
            unittest.mock.ANY,
            unittest.mock.ANY,
            requested_project_id="custom-proj",
        )
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            feature_id="feat-1",
            phase_number=1,
            project_id_override="custom-proj",
        )

    async def test_request_resolution_exception_propagates(self) -> None:
        with patch.object(
            agent_router,
            "_resolve_app_request",
            new=AsyncMock(side_effect=HTTPException(status_code=404, detail="No active project")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await agent_router.get_phase_operations(
                    feature_id="feat-1",
                    phase_number=1,
                    project_id=None,
                    request_context=object(),
                    core_ports=object(),
                )

        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
