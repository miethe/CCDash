"""Tests for the planning writeback router."""
from __future__ import annotations

import contextlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.application.services.agent_queries.cache import clear_cache, get_cache
from backend.application.services.agent_queries import OpenQuestionResolutionDTO, PlanningOpenQuestionItem
from backend.request_scope import get_core_ports, get_request_context
from backend.routers import planning as planning_router
from backend.runtime.bootstrap import build_runtime_app
from backend.tests.test_planning_query_service import _context, _feature, _feature_row, _ports


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


class ResolveOpenQuestionApiIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_cache()

    def test_api_resolves_seeded_open_question_and_emits_invalidation_and_span(self) -> None:
        row = _feature_row(_feature(fid="feat-api-oq", name="API Open Question Feature"))
        data = json.loads(row["data_json"])
        data["openQuestions"] = [
            {"id": "OQ-9", "question": "Which rollout path?", "severity": "high"}
        ]
        row["data_json"] = json.dumps(data)

        features_repo = SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        docs_repo = SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)
        request_context = _context()

        app = FastAPI()
        app.include_router(planning_router.planning_router)
        app.dependency_overrides[get_request_context] = lambda: request_context
        app.dependency_overrides[get_core_ports] = lambda: ports

        cache = get_cache()
        cache["planning-api-stale-entry"] = object()

        class _Span:
            def __init__(self) -> None:
                self.attrs: dict[str, object] = {}

            def set_attribute(self, key: str, value: object) -> None:
                self.attrs[key] = value

        spans: list[tuple[str, dict[str, object], _Span]] = []

        @contextlib.contextmanager
        def _start_span(name: str, attributes: dict[str, object] | None = None):
            span = _Span()
            spans.append((name, dict(attributes or {}), span))
            yield span

        with patch("backend.routers.planning.config.CCDASH_PLANNING_CONTROL_PLANE_ENABLED", True):
            with patch(
                "backend.application.services.agent_queries.planning.otel.start_span",
                new=_start_span,
            ):
                with patch.object(
                    planning_router,
                    "publish_planning_invalidation",
                    new=AsyncMock(),
                ) as publish_mock:
                    client = TestClient(app)
                    response = client.patch(
                        "/api/planning/features/feat-api-oq/open-questions/OQ-9",
                        json={"answer": "Use phased rollout."},
                    )

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["feature_id"], "feat-api-oq")
        self.assertEqual(body["oq"]["oq_id"], "OQ-9")
        self.assertEqual(body["oq"]["answer_text"], "Use phased rollout.")
        self.assertTrue(body["oq"]["resolved"])
        self.assertTrue(body["oq"]["pending_sync"])
        self.assertEqual(list(cache.keys()), [])

        publish_mock.assert_awaited_once_with(
            "project-1",
            feature_id="feat-api-oq",
            reason="open_question_resolved",
            source="planning.resolve_open_question",
            payload={"oqId": "OQ-9", "pendingSync": True},
        )

        self.assertEqual(len(spans), 1)
        name, attributes, span = spans[0]
        self.assertEqual(name, "planning.oq.resolve")
        self.assertEqual(attributes["feature_id"], "feat-api-oq")
        self.assertEqual(attributes["oq_id"], "OQ-9")
        self.assertEqual(attributes["answer_length"], len("Use phased rollout."))
        self.assertEqual(attributes["success"], False)
        self.assertEqual(span.attrs["success"], True)
