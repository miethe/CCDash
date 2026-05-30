import unittest

from backend.application.services.planning_command_resolver import PlanningCommandResolver
from backend.models import Feature, FeaturePhase, LinkedDocument


class PlanningCommandResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = PlanningCommandResolver()

    def _feature(
        self,
        *,
        status: str = "backlog",
        phases: list[FeaturePhase] | None = None,
        docs: list[LinkedDocument] | None = None,
    ) -> Feature:
        return Feature(
            id="feat-1",
            name="Feature One",
            status=status,
            totalTasks=0,
            completedTasks=0,
            category="enhancement",
            tags=[],
            updatedAt="",
            linkedDocs=docs or [],
            phases=phases or [],
            relatedFeatures=[],
        )

    def _doc(self, doc_type: str, path: str) -> LinkedDocument:
        return LinkedDocument(id=f"{doc_type}:{path}", title=path, filePath=path, docType=doc_type)

    def _phase(self, number: int, status: str) -> FeaturePhase:
        return FeaturePhase(
            id=f"feat-1:phase-{number}",
            phase=str(number),
            title=f"Phase {number}",
            status=status,
            progress=100 if status in {"done", "completed"} else 0,
            totalTasks=2,
            completedTasks=2 if status in {"done", "completed"} else 0,
            deferredTasks=0,
            tasks=[],
        )

    def test_spike_artifact_uses_spike_rule(self) -> None:
        feature = self._feature(docs=[self._doc("spike", "docs/project_plans/spikes/feat-1.md")])

        result = self.resolver.resolve(feature)

        self.assertEqual(result.rule_id, "PCC-CMD-001")
        self.assertEqual(result.command, "/plan:spike docs/project_plans/spikes/feat-1.md")
        self.assertEqual(result.target_artifact_doc_type, "spike")

    def test_exploration_artifact_uses_explore_rule(self) -> None:
        feature = self._feature(
            docs=[
                self._doc(
                    "exploration_charter",
                    "docs/project_plans/exploration/feat-1/feat-1-charter.md",
                )
            ]
        )

        result = self.resolver.resolve(feature)

        self.assertEqual(result.rule_id, "PCC-CMD-002")
        self.assertTrue(result.command.startswith("/plan:explore "))

    def test_seed_doc_without_plan_uses_plan_feature_rule(self) -> None:
        feature = self._feature(docs=[self._doc("prd", "docs/project_plans/PRDs/enhancements/feat-1.md")])

        result = self.resolver.resolve(feature)

        self.assertEqual(result.rule_id, "PCC-CMD-003")
        self.assertEqual(result.command, "/plan:plan-feature docs/project_plans/PRDs/enhancements/feat-1.md")

    def test_contract_rule_is_capability_gated_with_fallback_warning(self) -> None:
        feature = self._feature(
            docs=[self._doc("feature_contract", "docs/project_plans/feature_contracts/enhancements/feat-1.md")]
        )

        result = self.resolver.resolve(feature)

        self.assertEqual(result.rule_id, "PCC-CMD-004")
        self.assertEqual(result.command, "/dev:quick-feature feat-1")
        self.assertIn("workflow:/dev:execute-contract", [cap.name for cap in result.required_capabilities])
        self.assertTrue(result.warnings)
        self.assertEqual(result.alternatives[0].rule_id, "PCC-CMD-004")
        self.assertEqual(
            result.alternatives[0].command,
            "/dev:execute-contract docs/project_plans/feature_contracts/enhancements/feat-1.md",
        )

    def test_plan_without_completed_phase_starts_phase_one(self) -> None:
        feature = self._feature(
            phases=[self._phase(1, "backlog")],
            docs=[self._doc("implementation_plan", "docs/project_plans/implementation_plans/enhancements/feat-1.md")],
        )

        result = self.resolver.resolve(feature)

        self.assertEqual(result.rule_id, "PCC-CMD-005")
        self.assertEqual(result.phase, 1)
        self.assertIn("/dev:execute-phase 1", result.command)

    def test_active_phase_resumes_active_phase(self) -> None:
        feature = self._feature(
            phases=[self._phase(1, "done"), self._phase(2, "review")],
            docs=[self._doc("implementation_plan", "docs/project_plans/implementation_plans/enhancements/feat-1.md")],
        )

        result = self.resolver.resolve(feature)

        self.assertEqual(result.rule_id, "PCC-CMD-006")
        self.assertEqual(result.phase, 2)

    def test_completed_phase_advances_to_next_phase(self) -> None:
        feature = self._feature(
            phases=[self._phase(1, "done"), self._phase(2, "backlog")],
            docs=[self._doc("implementation_plan", "docs/project_plans/implementation_plans/enhancements/feat-1.md")],
        )

        result = self.resolver.resolve(feature)

        self.assertEqual(result.rule_id, "PCC-CMD-007")
        self.assertEqual(result.phase, 2)

    def test_all_terminal_phases_complete_user_story(self) -> None:
        feature = self._feature(
            status="review",
            phases=[self._phase(1, "done"), self._phase(2, "deferred")],
            docs=[self._doc("implementation_plan", "docs/project_plans/implementation_plans/enhancements/feat-1.md")],
        )

        result = self.resolver.resolve(feature)

        self.assertEqual(result.rule_id, "PCC-CMD-008")
        self.assertEqual(result.command, "/dev:complete-user-story feat-1")

    def test_missing_artifacts_falls_back_to_quick_feature(self) -> None:
        feature = self._feature()

        result = self.resolver.resolve(feature)

        self.assertEqual(result.rule_id, "PCC-CMD-009")
        self.assertEqual(result.command, "/dev:quick-feature feat-1")
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
