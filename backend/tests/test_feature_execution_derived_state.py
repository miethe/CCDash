import json
import unittest
from unittest.mock import patch

from backend.models import Feature, LinkedDocument, LinkedFeatureRef
from backend.services import feature_execution


class _FeatureRepo:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def list_all(self, project_id: str) -> list[dict]:
        return list(self._rows)


class _DocumentRepo:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def list_all(self, project_id: str) -> list[dict]:
        return list(self._rows)


class FeatureExecutionDerivedStateTests(unittest.IsolatedAsyncioTestCase):
    def _feature(
        self,
        feature_id: str,
        *,
        status: str = "backlog",
        family: str = "",
        sequence_order: int | None = None,
        blocked_by: list[str] | None = None,
    ) -> Feature:
        linked_docs = []
        if family or sequence_order is not None:
            linked_docs.append(
                LinkedDocument(
                    id=f"plan:{feature_id}",
                    title=f"{feature_id} plan",
                    filePath=f"docs/project_plans/implementation_plans/enhancements/{feature_id}.md",
                    docType="implementation_plan",
                    featureFamily=family,
                    sequenceOrder=sequence_order,
                )
            )
        return Feature(
            id=feature_id,
            name=feature_id.replace("-", " ").title(),
            status=status,
            totalTasks=0,
            completedTasks=0,
            category="enhancement",
            tags=[],
            featureFamily=family,
            updatedAt="",
            linkedDocs=linked_docs,
            linkedFeatures=[
                LinkedFeatureRef(feature=dependency, type="blocked_by", source="blocked_by")
                for dependency in (blocked_by or [])
            ],
            phases=[],
            relatedFeatures=[],
        )

    def _feature_row(
        self,
        feature_id: str,
        *,
        status: str = "backlog",
        family: str = "",
        sequence_order: int | None = None,
        blocked_by: list[str] | None = None,
    ) -> dict:
        linked_docs: list[dict] = []
        if family or sequence_order is not None:
            linked_docs.append(
                {
                    "id": f"plan:{feature_id}",
                    "title": f"{feature_id} plan",
                    "filePath": f"docs/project_plans/implementation_plans/enhancements/{feature_id}.md",
                    "docType": "implementation_plan",
                    "featureFamily": family,
                    "sequenceOrder": sequence_order,
                }
            )
        return {
            "id": feature_id,
            "name": feature_id.replace("-", " ").title(),
            "status": status,
            "category": "enhancement",
            "project_id": "project-1",
            "total_tasks": 0,
            "completed_tasks": 0,
            "updated_at": "",
            "data_json": json.dumps(
                {
                    "featureFamily": family,
                    "linkedDocs": linked_docs,
                    "linkedFeatures": [
                        {"feature": dependency, "type": "blocked_by", "source": "blocked_by"}
                        for dependency in (blocked_by or [])
                    ],
                    "phases": [],
                    "relatedFeatures": [],
                }
            ),
        }

    async def test_missing_dependency_evidence_returns_blocked_unknown(self) -> None:
        feature = self._feature("feature-dependent-v1", blocked_by=["feature-missing-v1"])
        feature_rows = [self._feature_row("feature-dependent-v1", blocked_by=["feature-missing-v1"])]

        with (
            patch.object(feature_execution, "get_feature_repository", return_value=_FeatureRepo(feature_rows)),
            patch.object(feature_execution, "get_document_repository", return_value=_DocumentRepo([])),
        ):
            derived = await feature_execution.load_feature_execution_derived_states(object(), "project-1", [feature])

        state = derived["feature-dependent-v1"]
        self.assertEqual(state.dependencyState.state, "blocked_unknown")
        self.assertEqual(state.executionGate.state, "unknown_dependency_state")
        self.assertEqual(state.dependencyState.firstBlockingDependencyId, "feature-missing")

    async def test_family_predecessor_becomes_recommended_item(self) -> None:
        current = self._feature("feature-c-v1", family="dependency-family", sequence_order=2)
        feature_rows = [
            self._feature_row("feature-a-v1", status="done", family="dependency-family", sequence_order=0),
            self._feature_row("feature-b-v1", family="dependency-family", sequence_order=1),
            self._feature_row("feature-c-v1", family="dependency-family", sequence_order=2),
        ]

        with (
            patch.object(feature_execution, "get_feature_repository", return_value=_FeatureRepo(feature_rows)),
            patch.object(feature_execution, "get_document_repository", return_value=_DocumentRepo([])),
        ):
            derived = await feature_execution.load_feature_execution_derived_states(object(), "project-1", [current])

        state = derived["feature-c-v1"]
        self.assertEqual(state.executionGate.state, "waiting_on_family_predecessor")
        self.assertIsNotNone(state.recommendedFamilyItem)
        self.assertEqual(state.recommendedFamilyItem.featureId, "feature-b-v1")
        self.assertEqual(state.familySummary.nextRecommendedFeatureId, "feature-b-v1")

    async def test_blocked_first_family_item_does_not_skip_ahead(self) -> None:
        current = self._feature("feature-b-v1", family="dependency-family", sequence_order=1)
        feature_rows = [
            self._feature_row(
                "feature-a-v1",
                family="dependency-family",
                sequence_order=0,
                blocked_by=["feature-missing-v1"],
            ),
            self._feature_row("feature-b-v1", family="dependency-family", sequence_order=1),
        ]

        with (
            patch.object(feature_execution, "get_feature_repository", return_value=_FeatureRepo(feature_rows)),
            patch.object(feature_execution, "get_document_repository", return_value=_DocumentRepo([])),
        ):
            derived = await feature_execution.load_feature_execution_derived_states(object(), "project-1", [current])

        state = derived["feature-b-v1"]
        self.assertEqual(state.executionGate.state, "waiting_on_family_predecessor")
        self.assertIsNone(state.recommendedFamilyItem)
        self.assertEqual(state.familySummary.nextRecommendedFeatureId, "")


if __name__ == "__main__":
    unittest.main()
