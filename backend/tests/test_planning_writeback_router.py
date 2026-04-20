"""Tests for the planning writeback router."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.application.services.agent_queries import OpenQuestionResolutionDTO, PlanningOpenQuestionItem
from backend.routers import planning as planning_router
from backend.runtime.bootstrap import build_runtime_app


class PlanningWritebackRouterRegistrationTests(unittest.TestCase):
    def test_planning_writeback_endpoint_is_registered(self) -> None:
        app = build_runtime_app("test")
        paths = app.openapi()["paths"]
        self.assertIn("/api/planning/features/{feature_id}/open-questions/{oq_id}", paths)
        self.assertIn("patch", paths["/api/planning/features/{feature_id}/open-questions/{oq_id}"])


class ResolveOpenQuestionRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_happy_path_returns_202_and_publishes_invalidation(self) -> None:
        app_request = SimpleNamespace(
            context=SimpleNamespace(project=SimpleNamespace(project_id="proj-1")),
            ports=object(),
        )
        dto = OpenQuestionResolutionDTO(
            feature_id="feat-1",
            oq=PlanningOpenQuestionItem(
                oq_id="OQ-1",
                question="Need answer?",
                answer_text="Done",
                resolved=True,
                pending_sync=True,
            ),
        )

        with patch.object(
            planning_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ) as resolve_mock:
            with patch.object(
                planning_router.planning_query_service,
                "resolve_open_question",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                with patch.object(
                    planning_router,
                    "publish_planning_invalidation",
                    new=AsyncMock(),
                ) as publish_mock:
                    response = await planning_router.resolve_open_question(
                        req=planning_router.ResolveOpenQuestionRequest(answer="Done"),
                        feature_id="feat-1",
                        oq_id="OQ-1",
                        request_context=object(),
                        core_ports=object(),
                    )

        self.assertEqual(response.status_code, 202)
        resolve_mock.assert_awaited_once()
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            feature_id="feat-1",
            oq_id="OQ-1",
            answer_text="Done",
        )
        publish_mock.assert_awaited_once_with(
            "proj-1",
            feature_id="feat-1",
            reason="open_question_resolved",
            source="planning.resolve_open_question",
            payload={"oqId": "OQ-1", "pendingSync": True},
        )

    async def test_validation_error_becomes_400(self) -> None:
        app_request = SimpleNamespace(
            context=SimpleNamespace(project=SimpleNamespace(project_id="proj-1")),
            ports=object(),
        )
        with patch.object(
            planning_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                planning_router.planning_query_service,
                "resolve_open_question",
                new=AsyncMock(side_effect=ValueError("answer must not be empty")),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    await planning_router.resolve_open_question(
                        req=planning_router.ResolveOpenQuestionRequest(answer=""),
                        feature_id="feat-1",
                        oq_id="OQ-1",
                        request_context=object(),
                        core_ports=object(),
                    )

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_missing_open_question_becomes_404(self) -> None:
        app_request = SimpleNamespace(
            context=SimpleNamespace(project=SimpleNamespace(project_id="proj-1")),
            ports=object(),
        )
        with patch.object(
            planning_router, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                planning_router.planning_query_service,
                "resolve_open_question",
                new=AsyncMock(side_effect=LookupError("missing")),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    await planning_router.resolve_open_question(
                        req=planning_router.ResolveOpenQuestionRequest(answer="Done"),
                        feature_id="feat-1",
                        oq_id="OQ-404",
                        request_context=object(),
                        core_ports=object(),
                    )

        self.assertEqual(ctx.exception.status_code, 404)
