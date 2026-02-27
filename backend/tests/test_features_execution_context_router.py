import types
import unittest
from unittest.mock import patch

from backend.models import Feature, FeatureExecutionAnalyticsSummary, FeaturePhase, LinkedDocument
from backend.routers import features as features_router


class FeaturesExecutionContextRouterTests(unittest.IsolatedAsyncioTestCase):
    def _feature(self, *, status: str = "backlog", phases: list[FeaturePhase] | None = None) -> Feature:
        return Feature(
            id="feat-1",
            name="Feature One",
            status=status,
            totalTasks=0,
            completedTasks=0,
            category="enhancement",
            tags=[],
            updatedAt="",
            linkedDocs=[],
            phases=phases or [],
            relatedFeatures=[],
        )

    async def test_happy_path_returns_execution_context(self) -> None:
        feature = self._feature(
            phases=[
                FeaturePhase(
                    id="feat-1:phase-1",
                    phase="1",
                    title="Phase 1",
                    status="backlog",
                    progress=0,
                    totalTasks=3,
                    completedTasks=0,
                    deferredTasks=0,
                    tasks=[],
                )
            ]
        )
        docs = [
            LinkedDocument(
                id="plan-1",
                title="Plan",
                filePath="docs/project_plans/implementation_plans/enhancements/feat-1.md",
                docType="implementation_plan",
            )
        ]
        project = types.SimpleNamespace(id="project-1")

        with (
            patch.object(features_router.project_manager, "get_active_project", return_value=project),
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature", return_value=feature),
            patch.object(features_router, "get_feature_linked_sessions", return_value=[]),
            patch.object(features_router, "load_execution_documents", return_value=docs),
            patch.object(
                features_router,
                "load_execution_analytics",
                return_value=FeatureExecutionAnalyticsSummary(sessionCount=0),
            ),
        ):
            payload = await features_router.get_feature_execution_context("feat-1")

        self.assertEqual(payload.feature.id, "feat-1")
        self.assertEqual(payload.recommendations.ruleId, "R2_START_PHASE_1")
        self.assertEqual(len(payload.warnings), 0)

    async def test_no_plan_docs_prefers_r1(self) -> None:
        feature = self._feature()
        docs = [
            LinkedDocument(
                id="prd-1",
                title="PRD",
                filePath="docs/project_plans/PRDs/enhancements/feat-1.md",
                docType="prd",
            )
        ]
        project = types.SimpleNamespace(id="project-1")

        with (
            patch.object(features_router.project_manager, "get_active_project", return_value=project),
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature", return_value=feature),
            patch.object(features_router, "get_feature_linked_sessions", return_value=[]),
            patch.object(features_router, "load_execution_documents", return_value=docs),
            patch.object(
                features_router,
                "load_execution_analytics",
                return_value=FeatureExecutionAnalyticsSummary(sessionCount=0),
            ),
        ):
            payload = await features_router.get_feature_execution_context("feat-1")

        self.assertEqual(payload.recommendations.ruleId, "R1_PLAN_FROM_PRD_OR_REPORT")

    async def test_all_phases_complete_recommends_story_completion(self) -> None:
        feature = self._feature(
            status="review",
            phases=[
                FeaturePhase(
                    id="feat-1:phase-1",
                    phase="1",
                    title="Phase 1",
                    status="done",
                    progress=100,
                    totalTasks=2,
                    completedTasks=2,
                    deferredTasks=0,
                    tasks=[],
                )
            ],
        )
        project = types.SimpleNamespace(id="project-1")

        with (
            patch.object(features_router.project_manager, "get_active_project", return_value=project),
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature", return_value=feature),
            patch.object(features_router, "get_feature_linked_sessions", return_value=[]),
            patch.object(features_router, "load_execution_documents", return_value=[]),
            patch.object(
                features_router,
                "load_execution_analytics",
                return_value=FeatureExecutionAnalyticsSummary(sessionCount=0),
            ),
        ):
            payload = await features_router.get_feature_execution_context("feat-1")

        self.assertEqual(payload.recommendations.ruleId, "R5_COMPLETE_STORY")
        self.assertEqual(payload.recommendations.primary.command, "/dev:complete-user-story feat-1")

    async def test_ambiguous_evidence_falls_back_to_quick_feature(self) -> None:
        feature = self._feature()
        project = types.SimpleNamespace(id="project-1")

        with (
            patch.object(features_router.project_manager, "get_active_project", return_value=project),
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature", return_value=feature),
            patch.object(features_router, "get_feature_linked_sessions", return_value=[]),
            patch.object(features_router, "load_execution_documents", return_value=[]),
            patch.object(
                features_router,
                "load_execution_analytics",
                side_effect=RuntimeError("analytics unavailable"),
            ),
        ):
            payload = await features_router.get_feature_execution_context("feat-1")

        self.assertEqual(payload.recommendations.ruleId, "R6_FALLBACK_QUICK_FEATURE")
        self.assertGreaterEqual(len(payload.warnings), 1)


if __name__ == "__main__":
    unittest.main()
