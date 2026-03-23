import json
import types
import unittest
from unittest.mock import patch

from backend.models import (
    ExecutionGateState,
    FeatureDependencyEvidence,
    FeatureDependencyState,
    FeatureExecutionDerivedState,
    FeatureFamilyItem,
    FeatureFamilyPosition,
    FeatureFamilySummary,
)
from backend.routers import features as features_router


class _FeatureRepo:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self._by_id = {str(row.get("id")): row for row in rows}

    async def get_by_id(self, feature_id: str) -> dict | None:
        return self._by_id.get(feature_id)

    async def get_phases(self, feature_id: str) -> list[dict]:
        return []

    async def list_paginated(self, project_id: str, offset: int, limit: int) -> list[dict]:
        return list(self._rows[offset : offset + limit])

    async def count(self, project_id: str) -> int:
        return len(self._rows)


class FeatureRouterDependencyStateTests(unittest.IsolatedAsyncioTestCase):
    def _row(self, feature_id: str) -> dict:
        return {
            "id": feature_id,
            "name": feature_id.replace("-", " ").title(),
            "status": "backlog",
            "category": "enhancement",
            "project_id": "project-1",
            "total_tasks": 0,
            "completed_tasks": 0,
            "updated_at": "",
            "data_json": json.dumps(
                {
                    "linkedDocs": [],
                    "linkedFeatures": [],
                    "primaryDocuments": {},
                    "documentCoverage": {},
                    "qualitySignals": {},
                    "phases": [],
                    "relatedFeatures": [],
                }
            ),
        }

    def _derived_state(
        self,
        feature_id: str,
        *,
        dependency_state: str = "blocked",
        gate_state: str = "blocked_dependency",
        recommended_family_item: FeatureFamilyItem | None = None,
        next_recommended_feature_id: str = "feature-a-v1",
    ) -> FeatureExecutionDerivedState:
        dependency = FeatureDependencyEvidence(
            dependencyFeatureId="feature-a-v1",
            dependencyFeatureName="Feature A V1",
            dependencyStatus="in-progress",
            dependencyCompletionEvidence=[],
            blockingDocumentIds=[],
            blockingReason="Feature A must complete first.",
            resolved=True,
            state="blocked",
        )
        family_item = FeatureFamilyItem(
            featureId="feature-a-v1",
            featureName="Feature A V1",
            featureStatus="in-progress",
            featureFamily="dependency-family",
            sequenceOrder=0,
            familyIndex=1,
            totalFamilyItems=2,
            isCurrent=False,
            isSequenced=True,
            isBlocked=True,
            isBlockedUnknown=False,
            isExecutable=False,
            dependencyState=FeatureDependencyState(state=dependency_state, dependencyCount=1, blockedDependencyCount=1, dependencies=[dependency]),
            primaryDocId="plan:feature-a-v1",
            primaryDocPath="docs/project_plans/implementation_plans/enhancements/feature-a-v1.md",
        )
        family_summary = FeatureFamilySummary(
            featureFamily="dependency-family",
            totalItems=2,
            sequencedItems=2,
            unsequencedItems=0,
            currentFeatureId=feature_id,
            currentFeatureName=feature_id.replace("-", " ").title(),
            currentPosition=2,
            currentSequencedPosition=2,
            nextRecommendedFeatureId=next_recommended_feature_id,
            nextRecommendedFamilyItem=recommended_family_item or family_item,
            items=[family_item],
        )
        family_position = FeatureFamilyPosition(
            familyKey="dependency-family",
            currentIndex=2,
            sequencedIndex=2,
            totalItems=2,
            sequencedItems=2,
            unsequencedItems=0,
            display="2 of 2",
            currentItemId=feature_id,
            nextItemId=next_recommended_feature_id,
            nextItemLabel=(recommended_family_item.featureName if recommended_family_item else "Feature A V1") if next_recommended_feature_id else "",
        )
        dependency_state_model = FeatureDependencyState(
            state=dependency_state,
            dependencyCount=1,
            resolvedDependencyCount=1,
            blockedDependencyCount=1,
            unknownDependencyCount=0,
            blockingFeatureIds=["feature-a-v1"],
            blockingDocumentIds=[],
            firstBlockingDependencyId="feature-a-v1",
            blockingReason="Feature A must complete first.",
            completionEvidence=[],
            dependencies=[dependency],
        )
        return FeatureExecutionDerivedState(
            dependencyState=dependency_state_model,
            familySummary=family_summary,
            familyPosition=family_position,
            executionGate=ExecutionGateState(
                state=gate_state,
                blockingDependencyId="feature-a-v1" if gate_state != "unknown_dependency_state" else "feature-unknown",
                firstExecutableFamilyItemId=recommended_family_item.featureId if recommended_family_item else "",
                recommendedFamilyItemId=recommended_family_item.featureId if recommended_family_item else next_recommended_feature_id,
                familyPosition=family_position,
                dependencyState=dependency_state_model,
                familySummary=family_summary,
                reason="Feature A must complete first.",
                waitingOnFamilyPredecessor=False,
                isReady=False,
            ),
            recommendedFamilyItem=recommended_family_item,
        )

    async def test_get_feature_applies_derived_fields(self) -> None:
        repo = _FeatureRepo([self._row("feature-b-v1")])

        with (
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature_repository", return_value=repo),
            patch.object(features_router, "load_feature_execution_derived_state", return_value=self._derived_state("feature-b-v1")),
        ):
            feature = await features_router.get_feature("feature-b-v1", include_tasks=False)

        self.assertEqual(feature.dependencyState.state, "blocked")
        self.assertEqual(feature.blockingFeatures[0].dependencyFeatureId, "feature-a-v1")
        self.assertEqual(feature.familySummary.nextRecommendedFeatureId, "feature-a-v1")
        self.assertEqual(feature.executionGate.state, "blocked_dependency")

    async def test_list_features_applies_derived_fields(self) -> None:
        rows = [self._row("feature-b-v1")]
        repo = _FeatureRepo(rows)
        project = types.SimpleNamespace(id="project-1")

        with (
            patch.object(features_router.project_manager, "get_active_project", return_value=project),
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature_repository", return_value=repo),
            patch.object(
                features_router,
                "load_feature_execution_derived_states",
                return_value={"feature-b-v1": self._derived_state("feature-b-v1")},
            ),
        ):
            response = await features_router.list_features(offset=0, limit=200)

        self.assertEqual(response.items[0].dependencyState.state, "blocked")
        self.assertEqual(response.items[0].blockingFeatures[0].dependencyFeatureId, "feature-a-v1")
        self.assertEqual(response.items[0].nextRecommendedFamilyItem.featureId, "feature-a-v1")

    async def test_get_feature_applies_blocked_unknown_derived_fields(self) -> None:
        repo = _FeatureRepo([self._row("feature-b-v1")])
        derived = self._derived_state(
            "feature-b-v1",
            dependency_state="blocked_unknown",
            gate_state="unknown_dependency_state",
            recommended_family_item=None,
            next_recommended_feature_id="",
        )
        derived.dependencyState.state = "blocked_unknown"
        derived.dependencyState.unknownDependencyCount = 1
        derived.dependencyState.blockedDependencyCount = 0
        derived.dependencyState.firstBlockingDependencyId = "feature-unknown"
        derived.dependencyState.blockingReason = "Dependency could not be resolved."
        derived.executionGate.blockingDependencyId = "feature-unknown"
        derived.executionGate.reason = "Dependency evidence is incomplete."
        derived.familySummary.nextRecommendedFeatureId = ""
        derived.familySummary.nextRecommendedFamilyItem = None

        with (
            patch.object(features_router.connection, "get_connection", return_value=object()),
            patch.object(features_router, "get_feature_repository", return_value=repo),
            patch.object(features_router, "load_feature_execution_derived_state", return_value=derived),
        ):
            feature = await features_router.get_feature("feature-b-v1", include_tasks=False)

        self.assertEqual(feature.dependencyState.state, "blocked_unknown")
        self.assertEqual(feature.executionGate.state, "unknown_dependency_state")
        self.assertEqual(feature.blockingFeatures[0].state, "blocked_unknown")
        self.assertEqual(feature.familySummary.nextRecommendedFeatureId, "")


if __name__ == "__main__":
    unittest.main()
