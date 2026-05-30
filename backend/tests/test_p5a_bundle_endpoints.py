"""Integration tests for P5a fat-read bundle endpoints (T5-001 through T5-004).

Tests cover:
- Route registration in OpenAPI schema
- Handler delegation pattern (handler → service, correct args)
- Response shape (sessions list, task_counts dict, meta envelope, DTO fields)
- Resilience: missing sub-fields default to empty collections
- Planning view with/without include= params
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.application.services.agent_queries import (
    AnalyticsOverviewBundleDTO,
    DashboardBundleDTO,
    PlanningViewBundleDTO,
    ProjectPlanningGraphDTO,
    ProjectPlanningSummaryDTO,
)
from backend.application.services.agent_queries.models import (
    AnalyticsKPIsDTO,
    PlanningAgentSessionBoardDTO,
    SessionCardDTO,
)
from backend.routers import agent as agent_module
from backend.routers import analytics as analytics_module
from backend.routers import client_v1 as client_v1_module
from backend.runtime.bootstrap import build_runtime_app


# ── Helper factories ──────────────────────────────────────────────────────────


def _make_dashboard_dto(
    project_id: str = "project-1",
    sessions: list | None = None,
    task_counts: dict | None = None,
) -> DashboardBundleDTO:
    return DashboardBundleDTO(
        project_id=project_id,
        sessions=sessions or [
            SessionCardDTO(
                session_id="session-1",
                title="Test session",
                status="completed",
                started_at="2026-05-01T10:00:00Z",
            )
        ],
        task_counts=task_counts or {"pending": 3, "completed": 7},
        source_refs=[project_id],
    )


def _make_planning_bundle_dto(
    project_id: str = "project-1",
    with_graph: bool = False,
    with_board: bool = False,
) -> PlanningViewBundleDTO:
    summary = ProjectPlanningSummaryDTO(
        project_id=project_id,
        total_feature_count=5,
        source_refs=[],
    )
    graph = ProjectPlanningGraphDTO(
        project_id=project_id,
        node_count=3,
        edge_count=2,
        source_refs=[],
    ) if with_graph else None
    board = PlanningAgentSessionBoardDTO(
        project_id=project_id,
        total_card_count=2,
        source_refs=[],
    ) if with_board else None
    return PlanningViewBundleDTO(
        project_id=project_id,
        summary=summary,
        graph=graph,
        session_board=board,
        source_refs=[project_id],
    )


def _make_analytics_bundle_dto(project_id: str = "project-1") -> AnalyticsOverviewBundleDTO:
    return AnalyticsOverviewBundleDTO(
        project_id=project_id,
        kpis=AnalyticsKPIsDTO(
            session_count=42,
            session_cost=1.23,
            session_tokens=9876,
        ),
        top_models=[],
        range={"start": "", "end": ""},
        source_refs=[project_id],
    )


# ── Route registration tests ─────────────────────────────────────────────────


class TestBundleRouteRegistration(unittest.TestCase):
    """Verify all three bundle routes are present in OpenAPI spec."""

    def setUp(self) -> None:
        self.app = build_runtime_app("test")
        self.paths = self.app.openapi()["paths"]

    def test_dashboard_bundle_route_registered(self) -> None:
        self.assertIn("/api/v1/dashboard", self.paths)
        self.assertIn("get", self.paths["/api/v1/dashboard"])

    def test_planning_view_bundle_route_registered(self) -> None:
        self.assertIn("/api/agent/planning/view", self.paths)
        self.assertIn("get", self.paths["/api/agent/planning/view"])

    def test_analytics_overview_bundle_route_registered(self) -> None:
        self.assertIn("/api/analytics/overview-bundle", self.paths)
        self.assertIn("get", self.paths["/api/analytics/overview-bundle"])


# ── T5-002: Dashboard bundle endpoint ────────────────────────────────────────


class TestDashboardBundleEndpoint(unittest.IsolatedAsyncioTestCase):
    """Tests for GET /api/v1/dashboard (T5-002)."""

    async def test_handler_delegates_to_service_and_wraps_in_envelope(self) -> None:
        request_context = object()
        core_ports = object()
        dto = _make_dashboard_dto()

        with patch.object(
            client_v1_module._dashboard_query_service,
            "get_dashboard_bundle",
            new=AsyncMock(return_value=dto),
        ) as service_mock:
            result = await client_v1_module.dashboard_bundle(
                project_id="project-1",
                bypass_cache=False,
                request_context=request_context,
                core_ports=core_ports,
            )

        # Envelope wraps the DTO
        self.assertIs(result.data, dto)
        self.assertIsNotNone(result.meta)
        self.assertIsNotNone(result.meta.generated_at)

        service_mock.assert_awaited_once_with(
            request_context,
            core_ports,
            project_id_override="project-1",
            bypass_cache=False,
        )

    async def test_response_shape_contains_sessions_and_task_counts(self) -> None:
        request_context = object()
        core_ports = object()
        dto = _make_dashboard_dto(
            sessions=[SessionCardDTO(session_id="s-1", status="completed")],
            task_counts={"pending": 2, "done": 5},
        )

        with patch.object(
            client_v1_module._dashboard_query_service,
            "get_dashboard_bundle",
            new=AsyncMock(return_value=dto),
        ):
            result = await client_v1_module.dashboard_bundle(
                project_id=None,
                bypass_cache=False,
                request_context=request_context,
                core_ports=core_ports,
            )

        self.assertIsInstance(result.data.sessions, list)
        self.assertEqual(len(result.data.sessions), 1)
        self.assertEqual(result.data.sessions[0].session_id, "s-1")
        self.assertIsInstance(result.data.task_counts, dict)
        self.assertEqual(result.data.task_counts["pending"], 2)
        self.assertEqual(result.data.task_counts["done"], 5)

    async def test_missing_sessions_defaults_to_empty_list(self) -> None:
        """Resilience: sessions missing → FE should treat as []."""
        request_context = object()
        core_ports = object()
        dto = DashboardBundleDTO(
            project_id="project-1",
            # sessions field omitted → default_factory → []
            task_counts={"pending": 1},
        )

        with patch.object(
            client_v1_module._dashboard_query_service,
            "get_dashboard_bundle",
            new=AsyncMock(return_value=dto),
        ):
            result = await client_v1_module.dashboard_bundle(
                project_id=None,
                bypass_cache=False,
                request_context=request_context,
                core_ports=core_ports,
            )

        self.assertEqual(result.data.sessions, [])

    async def test_missing_task_counts_defaults_to_empty_dict(self) -> None:
        """Resilience: task_counts missing → FE should treat as {}."""
        request_context = object()
        core_ports = object()
        dto = DashboardBundleDTO(
            project_id="project-1",
            sessions=[SessionCardDTO(session_id="s-1")],
            # task_counts field omitted → default_factory → {}
        )

        with patch.object(
            client_v1_module._dashboard_query_service,
            "get_dashboard_bundle",
            new=AsyncMock(return_value=dto),
        ):
            result = await client_v1_module.dashboard_bundle(
                project_id=None,
                bypass_cache=False,
                request_context=request_context,
                core_ports=core_ports,
            )

        self.assertEqual(result.data.task_counts, {})


# ── T5-003: Planning view bundle endpoint ────────────────────────────────────


class TestPlanningViewBundleEndpoint(unittest.IsolatedAsyncioTestCase):
    """Tests for GET /api/agent/planning/view (T5-003)."""

    async def test_handler_delegates_to_service_summary_only(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = _make_planning_bundle_dto()

        with patch.object(
            agent_module, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ) as resolve_mock:
            with patch.object(
                agent_module.planning_query_service,
                "get_planning_view_bundle",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_module.get_planning_view_bundle(
                    project_id=None,
                    include=None,
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertIs(result, dto)
        resolve_mock.assert_awaited_once_with(
            request_context, core_ports, requested_project_id=None
        )
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            project_id_override=None,
            include=[],
        )

    async def test_response_contains_summary_always(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = _make_planning_bundle_dto()

        with patch.object(agent_module, "_resolve_app_request", new=AsyncMock(return_value=app_request)):
            with patch.object(
                agent_module.planning_query_service,
                "get_planning_view_bundle",
                new=AsyncMock(return_value=dto),
            ):
                result = await agent_module.get_planning_view_bundle(
                    project_id=None,
                    include=None,
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertIsNotNone(result.summary)
        self.assertIsNone(result.graph)
        self.assertIsNone(result.session_board)

    async def test_include_graph_returns_graph_payload(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = _make_planning_bundle_dto(with_graph=True)

        with patch.object(agent_module, "_resolve_app_request", new=AsyncMock(return_value=app_request)):
            with patch.object(
                agent_module.planning_query_service,
                "get_planning_view_bundle",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_module.get_planning_view_bundle(
                    project_id=None,
                    include=["graph"],
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertIsNotNone(result.graph)
        # confirm include= was forwarded
        _, kwargs = service_mock.call_args
        self.assertIn("graph", kwargs["include"])

    async def test_include_session_board_returns_board_payload(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = _make_planning_bundle_dto(with_board=True)

        with patch.object(agent_module, "_resolve_app_request", new=AsyncMock(return_value=app_request)):
            with patch.object(
                agent_module.planning_query_service,
                "get_planning_view_bundle",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_module.get_planning_view_bundle(
                    project_id=None,
                    include=["session_board"],
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertIsNotNone(result.session_board)
        _, kwargs = service_mock.call_args
        self.assertIn("session_board", kwargs["include"])

    async def test_include_graph_and_session_board_together(self) -> None:
        request_context = object()
        core_ports = object()
        app_request = SimpleNamespace(context=object(), ports=object())
        dto = _make_planning_bundle_dto(with_graph=True, with_board=True)

        with patch.object(agent_module, "_resolve_app_request", new=AsyncMock(return_value=app_request)):
            with patch.object(
                agent_module.planning_query_service,
                "get_planning_view_bundle",
                new=AsyncMock(return_value=dto),
            ) as service_mock:
                result = await agent_module.get_planning_view_bundle(
                    project_id=None,
                    include=["graph", "session_board"],
                    request_context=request_context,
                    core_ports=core_ports,
                )

        self.assertIsNotNone(result.graph)
        self.assertIsNotNone(result.session_board)
        _, kwargs = service_mock.call_args
        self.assertIn("graph", kwargs["include"])
        self.assertIn("session_board", kwargs["include"])


# ── T5-004: Analytics overview bundle endpoint ───────────────────────────────


class TestAnalyticsOverviewBundleEndpoint(unittest.IsolatedAsyncioTestCase):
    """Tests for GET /api/analytics/overview-bundle (T5-004)."""

    def _make_app_request(self) -> SimpleNamespace:
        return SimpleNamespace(context=object(), ports=object())

    async def test_handler_delegates_to_service_and_returns_dto(self) -> None:
        request_context = MagicMock()
        request_context.project = None
        core_ports = MagicMock()
        app_request = self._make_app_request()
        dto = _make_analytics_bundle_dto()

        with patch.object(
            analytics_module, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                analytics_module, "_require_analytics_authorization", new=AsyncMock()
            ):
                with patch.object(
                    analytics_module._analytics_bundle_query_service,
                    "get_analytics_overview_bundle",
                    new=AsyncMock(return_value=dto),
                ) as service_mock:
                    result = await analytics_module.get_analytics_overview_bundle(
                        project_id="project-1",
                        bypass_cache=False,
                        request_context=request_context,
                        core_ports=core_ports,
                    )

        self.assertIs(result, dto)
        service_mock.assert_awaited_once_with(
            app_request.context,
            app_request.ports,
            project_id_override="project-1",
            bypass_cache=False,
        )

    async def test_response_shape_contains_kpis_and_top_models(self) -> None:
        request_context = MagicMock()
        request_context.project = None
        core_ports = MagicMock()
        app_request = self._make_app_request()
        dto = _make_analytics_bundle_dto()

        with patch.object(
            analytics_module, "_resolve_app_request", new=AsyncMock(return_value=app_request)
        ):
            with patch.object(
                analytics_module, "_require_analytics_authorization", new=AsyncMock()
            ):
                with patch.object(
                    analytics_module._analytics_bundle_query_service,
                    "get_analytics_overview_bundle",
                    new=AsyncMock(return_value=dto),
                ):
                    result = await analytics_module.get_analytics_overview_bundle(
                        project_id=None,
                        bypass_cache=False,
                        request_context=request_context,
                        core_ports=core_ports,
                    )

        self.assertIsNotNone(result.kpis)
        self.assertIsInstance(result.kpis.session_count, int)
        self.assertEqual(result.kpis.session_count, 42)
        self.assertIsInstance(result.top_models, list)
        self.assertIsInstance(result.range, dict)

    async def test_tabs_are_not_included_in_bundle(self) -> None:
        """Above-fold only: the DTO must not expose detailed tab fields."""
        dto_fields = set(AnalyticsOverviewBundleDTO.model_fields.keys())

        # Tab-level fields must NOT be present
        tab_fields = {"workflow_effectiveness", "session_intelligence", "failure_patterns"}
        overlap = tab_fields & dto_fields
        self.assertEqual(
            overlap,
            set(),
            f"Tab-level fields leaked into bundle DTO: {overlap}",
        )


# ── DashboardBundleDTO unit: field shape ─────────────────────────────────────


class TestDashboardBundleDTOShape(unittest.TestCase):
    """Unit tests for DashboardBundleDTO field contracts."""

    def test_dto_has_sessions_and_task_counts_fields(self) -> None:
        dto = DashboardBundleDTO(project_id="project-1")
        self.assertIsInstance(dto.sessions, list)
        self.assertIsInstance(dto.task_counts, dict)

    def test_session_card_dto_field_defaults(self) -> None:
        card = SessionCardDTO(session_id="s-1")
        self.assertEqual(card.session_id, "s-1")
        self.assertEqual(card.title, "")
        self.assertEqual(card.status, "")
        self.assertEqual(card.total_cost, 0.0)
        self.assertEqual(card.total_tokens, 0)
        self.assertEqual(card.feature_id, "")
        self.assertEqual(card.root_session_id, "")

    def test_task_counts_missing_key_is_zero_by_convention(self) -> None:
        dto = DashboardBundleDTO(
            project_id="project-1",
            task_counts={"pending": 2},
        )
        # FE pattern: taskCounts ?? {} then taskCounts["nonexistent"] ?? 0
        self.assertEqual(dto.task_counts.get("nonexistent", 0), 0)


# ── PlanningViewBundleDTO unit: field shape ──────────────────────────────────


class TestPlanningViewBundleDTOShape(unittest.TestCase):
    """Unit tests for PlanningViewBundleDTO field contracts."""

    def test_dto_has_summary_graph_session_board_fields(self) -> None:
        dto = PlanningViewBundleDTO(project_id="project-1")
        # All optional fields default to None
        self.assertIsNone(dto.summary)
        self.assertIsNone(dto.graph)
        self.assertIsNone(dto.session_board)

    def test_summary_always_present_when_populated(self) -> None:
        summary = ProjectPlanningSummaryDTO(project_id="project-1", source_refs=[])
        dto = PlanningViewBundleDTO(project_id="project-1", summary=summary)
        self.assertIsNotNone(dto.summary)
        self.assertIsNone(dto.graph)


# ── AnalyticsOverviewBundleDTO unit: field shape ─────────────────────────────


class TestAnalyticsOverviewBundleDTOShape(unittest.TestCase):
    """Unit tests for AnalyticsOverviewBundleDTO field contracts."""

    def test_dto_has_kpis_top_models_range(self) -> None:
        dto = AnalyticsOverviewBundleDTO(project_id="project-1")
        self.assertIsInstance(dto.kpis, AnalyticsKPIsDTO)
        self.assertIsInstance(dto.top_models, list)
        self.assertIsInstance(dto.range, dict)

    def test_kpis_default_values_are_zero(self) -> None:
        kpis = AnalyticsKPIsDTO()
        for field_name, field_info in AnalyticsKPIsDTO.model_fields.items():
            value = getattr(kpis, field_name)
            # All numeric fields should default to 0 or 0.0
            self.assertIn(value, (0, 0.0), f"Field {field_name!r} unexpected default {value!r}")


if __name__ == "__main__":
    unittest.main()
