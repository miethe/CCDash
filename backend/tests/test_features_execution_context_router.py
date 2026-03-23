import types
import unittest
from unittest.mock import patch

from backend.models import (
    ExecutionGateState,
    Feature,
    FeatureDependencyEvidence,
    FeatureDependencyState,
    FeatureExecutionAnalyticsSummary,
    FeatureExecutionDerivedState,
    FeatureFamilyPosition,
    FeatureFamilySummary,
    FeaturePhase,
    LinkedDocument,
)
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

    def _stack_payload(self) -> dict:
        return {
            "recommendedStack": None,
            "stackAlternatives": [],
            "stackEvidence": [],
            "definitionResolutionWarnings": [],
        }

    def _derived_state(self) -> FeatureExecutionDerivedState:
        dependency_state = FeatureDependencyState(
            state="blocked",
            dependencyCount=1,
            resolvedDependencyCount=1,
            blockedDependencyCount=1,
            unknownDependencyCount=0,
            blockingFeatureIds=["feat-0"],
            firstBlockingDependencyId="feat-0",
            blockingReason="feat-0 must complete first.",
            dependencies=[],
        )
        family_summary = FeatureFamilySummary(
            featureFamily="family-a",
            totalItems=2,
            sequencedItems=2,
            unsequencedItems=0,
            currentFeatureId="feat-1",
            currentFeatureName="Feature One",
            currentPosition=2,
            currentSequencedPosition=2,
            nextRecommendedFeatureId="feat-0",
            items=[],
        )
        family_position = FeatureFamilyPosition(
            familyKey="family-a",
            currentIndex=2,
            sequencedIndex=2,
            totalItems=2,
            sequencedItems=2,
            unsequencedItems=0,
            display="2 of 2",
            currentItemId="feat-1",
            nextItemId="feat-0",
            nextItemLabel="Feature Zero",
        )
        return FeatureExecutionDerivedState(
            dependencyState=dependency_state,
            familySummary=family_summary,
            familyPosition=family_position,
            executionGate=ExecutionGateState(
                state="blocked_dependency",
                blockingDependencyId="feat-0",
                firstExecutableFamilyItemId="",
                recommendedFamilyItemId="feat-0",
                familyPosition=family_position,
                dependencyState=dependency_state,
                familySummary=family_summary,
                reason="feat-0 must complete first.",
                waitingOnFamilyPredecessor=False,
                isReady=False,
            ),
            recommendedFamilyItem=None,
        )

    def _ready_derived_state(self) -> FeatureExecutionDerivedState:
        dependency_state = FeatureDependencyState(
            state="unblocked",
            dependencyCount=0,
            resolvedDependencyCount=0,
            blockedDependencyCount=0,
            unknownDependencyCount=0,
            dependencies=[],
        )
        family_summary = FeatureFamilySummary(
            featureFamily="family-a",
            totalItems=1,
            sequencedItems=1,
            unsequencedItems=0,
            currentFeatureId="feat-1",
            currentFeatureName="Feature One",
            currentPosition=1,
            currentSequencedPosition=1,
            nextRecommendedFeatureId="",
            items=[],
        )
        family_position = FeatureFamilyPosition(
            familyKey="family-a",
            currentIndex=1,
            sequencedIndex=1,
            totalItems=1,
            sequencedItems=1,
            unsequencedItems=0,
            display="1 of 1",
            currentItemId="feat-1",
            nextItemId="",
            nextItemLabel="",
        )
        return FeatureExecutionDerivedState(
            dependencyState=dependency_state,
            familySummary=family_summary,
            familyPosition=family_position,
            executionGate=ExecutionGateState(
                state="ready",
                blockingDependencyId="",
                firstExecutableFamilyItemId="feat-1",
                recommendedFamilyItemId="feat-1",
                familyPosition=family_position,
                dependencyState=dependency_state,
                familySummary=family_summary,
                reason="Dependency and family ordering are clear.",
                waitingOnFamilyPredecessor=False,
                isReady=True,
            ),
            recommendedFamilyItem=None,
        )

    def _blocked_unknown_derived_state(self) -> FeatureExecutionDerivedState:
        dependency = FeatureDependencyEvidence(
            dependencyFeatureId="feat-unknown",
            dependencyFeatureName="Unknown Feature",
            dependencyStatus="unknown",
            dependencyCompletionEvidence=[],
            blockingDocumentIds=[],
            blockingReason="Dependency feature could not be resolved.",
            resolved=False,
            state="blocked_unknown",
        )
        dependency_state = FeatureDependencyState(
            state="blocked_unknown",
            dependencyCount=1,
            resolvedDependencyCount=0,
            blockedDependencyCount=0,
            unknownDependencyCount=1,
            blockingFeatureIds=["feat-unknown"],
            blockingDocumentIds=[],
            firstBlockingDependencyId="feat-unknown",
            blockingReason="Dependency feature could not be resolved.",
            completionEvidence=[],
            dependencies=[dependency],
        )
        family_summary = FeatureFamilySummary(
            featureFamily="family-a",
            totalItems=1,
            sequencedItems=1,
            unsequencedItems=0,
            currentFeatureId="feat-1",
            currentFeatureName="Feature One",
            currentPosition=1,
            currentSequencedPosition=1,
            nextRecommendedFeatureId="",
            items=[],
        )
        family_position = FeatureFamilyPosition(
            familyKey="family-a",
            currentIndex=1,
            sequencedIndex=1,
            totalItems=1,
            sequencedItems=1,
            unsequencedItems=0,
            display="1 of 1",
            currentItemId="feat-1",
            nextItemId="",
            nextItemLabel="",
        )
        return FeatureExecutionDerivedState(
            dependencyState=dependency_state,
            familySummary=family_summary,
            familyPosition=family_position,
            executionGate=ExecutionGateState(
                state="unknown_dependency_state",
                blockingDependencyId="feat-unknown",
                firstExecutableFamilyItemId="",
                recommendedFamilyItemId="",
                familyPosition=family_position,
                dependencyState=dependency_state,
                familySummary=family_summary,
                reason="Dependency evidence is incomplete.",
                waitingOnFamilyPredecessor=False,
                isReady=False,
            ),
            recommendedFamilyItem=None,
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
            patch.object(features_router, "load_feature_execution_derived_state", return_value=self._ready_derived_state()),
            patch.object(features_router, "build_stack_recommendations", return_value=self._stack_payload()),
        ):
            payload = await features_router.get_feature_execution_context("feat-1")

        self.assertEqual(payload.feature.id, "feat-1")
        self.assertEqual(payload.recommendations.ruleId, "R2_START_PHASE_1")
        self.assertEqual(payload.dependencyState.state, "unblocked")
        self.assertEqual(payload.executionGate.state, "ready")
        self.assertIsNone(payload.recommendedFamilyItem)
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
            patch.object(features_router, "build_stack_recommendations", return_value=self._stack_payload()),
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
            patch.object(features_router, "build_stack_recommendations", return_value=self._stack_payload()),
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
            patch.object(features_router, "build_stack_recommendations", return_value=self._stack_payload()),
        ):
            payload = await features_router.get_feature_execution_context("feat-1")

        self.assertEqual(payload.recommendations.ruleId, "R6_FALLBACK_QUICK_FEATURE")
        self.assertGreaterEqual(len(payload.warnings), 1)

    async def test_execution_context_includes_derived_dependency_and_family_fields(self) -> None:
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
                return_value=FeatureExecutionAnalyticsSummary(sessionCount=0),
            ),
            patch.object(features_router, "load_feature_execution_derived_state", return_value=self._derived_state()),
            patch.object(features_router, "build_stack_recommendations", return_value=self._stack_payload()),
        ):
            payload = await features_router.get_feature_execution_context("feat-1")

        self.assertIsNotNone(payload.dependencyState)
        self.assertEqual(payload.dependencyState.state, "blocked")
        self.assertIsNotNone(payload.executionGate)
        self.assertEqual(payload.executionGate.state, "blocked_dependency")
        self.assertIsNotNone(payload.familySummary)
        self.assertEqual(payload.familySummary.nextRecommendedFeatureId, "feat-0")

    async def test_execution_context_reports_blocked_unknown_dependency_state(self) -> None:
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
                return_value=FeatureExecutionAnalyticsSummary(sessionCount=0),
            ),
            patch.object(features_router, "load_feature_execution_derived_state", return_value=self._blocked_unknown_derived_state()),
            patch.object(features_router, "build_stack_recommendations", return_value=self._stack_payload()),
        ):
            payload = await features_router.get_feature_execution_context("feat-1")

        self.assertEqual(payload.dependencyState.state, "blocked_unknown")
        self.assertEqual(payload.executionGate.state, "unknown_dependency_state")
        self.assertIsNotNone(payload.dependencyState.dependencies)
        self.assertEqual(payload.dependencyState.dependencies[0].state, "blocked_unknown")

    async def test_stack_recommendations_can_be_disabled_per_project(self) -> None:
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
                return_value=FeatureExecutionAnalyticsSummary(sessionCount=0),
            ),
            patch.object(features_router, "stack_recommendations_enabled", return_value=False),
            patch.object(features_router, "build_stack_recommendations") as build_stack_recommendations,
        ):
            payload = await features_router.get_feature_execution_context("feat-1")

        build_stack_recommendations.assert_not_called()
        self.assertTrue(any("disabled for this project" in warning.message for warning in payload.warnings))


if __name__ == "__main__":
    unittest.main()
