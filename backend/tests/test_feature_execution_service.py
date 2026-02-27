import unittest

from backend.models import Feature, FeaturePhase, LinkedDocument
from backend.services.feature_execution import build_execution_recommendation


class FeatureExecutionRecommendationTests(unittest.TestCase):
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

    def _doc(self, doc_type: str, path: str) -> LinkedDocument:
        return LinkedDocument(id=f"{doc_type}:{path}", title=path, filePath=path, docType=doc_type)

    def test_r1_plan_from_prd_or_report_when_plan_missing(self) -> None:
        feature = self._feature()
        docs = [self._doc("prd", "docs/project_plans/PRDs/enhancements/feat-1.md")]

        recommendation = build_execution_recommendation(feature, docs)

        self.assertEqual(recommendation.ruleId, "R1_PLAN_FROM_PRD_OR_REPORT")
        self.assertTrue(recommendation.primary.command.startswith("/plan:plan-feature "))

    def test_r2_start_phase_1_when_plan_exists_without_completed_phase(self) -> None:
        feature = self._feature(
            phases=[
                FeaturePhase(
                    id="feat-1:phase-1",
                    phase="1",
                    title="Phase 1",
                    status="backlog",
                    progress=0,
                    totalTasks=4,
                    completedTasks=0,
                    deferredTasks=0,
                    tasks=[],
                )
            ]
        )
        docs = [self._doc("implementation_plan", "docs/project_plans/implementation_plans/enhancements/feat-1.md")]

        recommendation = build_execution_recommendation(feature, docs)

        self.assertEqual(recommendation.ruleId, "R2_START_PHASE_1")
        self.assertIn("/dev:execute-phase 1", recommendation.primary.command)

    def test_r3_advances_to_next_phase_when_prior_phase_completed(self) -> None:
        feature = self._feature(
            phases=[
                FeaturePhase(
                    id="feat-1:phase-1",
                    phase="1",
                    title="Phase 1",
                    status="done",
                    progress=100,
                    totalTasks=4,
                    completedTasks=4,
                    deferredTasks=0,
                    tasks=[],
                ),
                FeaturePhase(
                    id="feat-1:phase-2",
                    phase="2",
                    title="Phase 2",
                    status="backlog",
                    progress=0,
                    totalTasks=3,
                    completedTasks=0,
                    deferredTasks=0,
                    tasks=[],
                ),
            ]
        )
        docs = [self._doc("implementation_plan", "docs/project_plans/implementation_plans/enhancements/feat-1.md")]

        recommendation = build_execution_recommendation(feature, docs)

        self.assertEqual(recommendation.ruleId, "R3_ADVANCE_TO_NEXT_PHASE")
        self.assertIn("/dev:execute-phase 2", recommendation.primary.command)

    def test_r3_beats_r4_when_both_apply_priority_tiebreaker(self) -> None:
        feature = self._feature(
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
                ),
                FeaturePhase(
                    id="feat-1:phase-2",
                    phase="2",
                    title="Phase 2",
                    status="review",
                    progress=80,
                    totalTasks=5,
                    completedTasks=3,
                    deferredTasks=0,
                    tasks=[],
                ),
            ]
        )
        docs = [self._doc("implementation_plan", "docs/project_plans/implementation_plans/enhancements/feat-1.md")]

        recommendation = build_execution_recommendation(feature, docs)

        self.assertEqual(recommendation.ruleId, "R3_ADVANCE_TO_NEXT_PHASE")
        self.assertIn("/dev:execute-phase 2", recommendation.primary.command)

    def test_r5_complete_story_when_all_phases_terminal_and_feature_not_final(self) -> None:
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
                ),
                FeaturePhase(
                    id="feat-1:phase-2",
                    phase="2",
                    title="Phase 2",
                    status="deferred",
                    progress=100,
                    totalTasks=2,
                    completedTasks=0,
                    deferredTasks=2,
                    tasks=[],
                ),
            ],
        )

        recommendation = build_execution_recommendation(feature, [])

        self.assertEqual(recommendation.ruleId, "R5_COMPLETE_STORY")
        self.assertEqual(recommendation.primary.command, "/dev:complete-user-story feat-1")

    def test_r6_fallback_quick_feature_when_evidence_is_sparse(self) -> None:
        feature = self._feature()

        recommendation = build_execution_recommendation(feature, [])

        self.assertEqual(recommendation.ruleId, "R6_FALLBACK_QUICK_FEATURE")
        self.assertEqual(recommendation.primary.command, "/dev:quick-feature feat-1")


if __name__ == "__main__":
    unittest.main()
