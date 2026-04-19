import json
import unittest
from unittest.mock import patch

from backend.models import Feature, FeatureExecutionAnalyticsSummary, FeaturePhase, LinkedDocument
from backend.services.feature_execution import build_execution_context, build_execution_recommendation, load_feature_execution_derived_state


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


class FeatureExecutionDerivedStateTests(unittest.IsolatedAsyncioTestCase):
    def _feature(
        self,
        feature_id: str,
        *,
        name: str,
        status: str,
        family: str = "",
        linked_features: list[dict] | None = None,
        phases: list[FeaturePhase] | None = None,
    ) -> Feature:
        return Feature(
            id=feature_id,
            name=name,
            status=status,
            totalTasks=0,
            completedTasks=0,
            category="enhancement",
            tags=[],
            updatedAt="",
            linkedDocs=[],
            linkedFeatures=linked_features or [],
            featureFamily=family,
            phases=phases or [],
            relatedFeatures=[],
        )

    def _feature_row(
        self,
        feature_id: str,
        *,
        name: str,
        status: str,
        family: str = "",
        linked_features: list[dict] | None = None,
        phases: list[dict] | None = None,
    ) -> dict:
        normalized_linked_features = [
            ref.model_dump() if hasattr(ref, "model_dump") else dict(ref)
            for ref in (linked_features or [])
        ]
        data = {
            "id": feature_id,
            "name": name,
            "status": status,
            "featureFamily": family,
            "linkedFeatures": normalized_linked_features,
            "phases": phases or [],
            "linkedDocs": [],
            "relatedFeatures": [],
        }
        return {
            "id": feature_id,
            "name": name,
            "status": status,
            "category": "enhancement",
            "total_tasks": 0,
            "completed_tasks": 0,
            "updated_at": "",
            "data_json": json.dumps(data),
        }

    def _doc_row(
        self,
        *,
        doc_id: str,
        feature_slug: str,
        doc_type: str,
        status: str,
        sequence_order: int | None = None,
        file_path: str | None = None,
        blocked_by: list[str] | None = None,
        related_refs: list[str] | None = None,
        prd_ref: str = "",
        lineage_parent: str = "",
        lineage_type: str = "",
    ) -> dict:
        metadata = {}
        frontmatter = {}
        if sequence_order is not None:
            metadata["sequenceOrder"] = sequence_order
            frontmatter["sequence_order"] = sequence_order
        if blocked_by:
            frontmatter["blocked_by"] = blocked_by
        if related_refs:
            frontmatter["relatedRefs"] = related_refs
        if prd_ref:
            frontmatter["prd_ref"] = prd_ref
        if lineage_parent:
            frontmatter["lineage_parent"] = lineage_parent
        if lineage_type:
            frontmatter["lineage_type"] = lineage_type
        return {
            "id": doc_id,
            "title": file_path or doc_id,
            "file_path": file_path or f"docs/{doc_id}.md",
            "doc_type": doc_type,
            "status": status,
            "prd_ref": prd_ref,
            "feature_slug_canonical": feature_slug,
            "metadata_json": json.dumps(metadata),
            "frontmatter_json": json.dumps(frontmatter),
        }

    async def _load_state(self, current_feature: Feature, feature_rows: list[dict], doc_rows: list[dict]):
        class _FeatureRepo:
            def __init__(self, rows: list[dict]) -> None:
                self.rows = rows

            async def list_all(self, project_id: str | None = None) -> list[dict]:
                return self.rows

        class _DocumentRepo:
            def __init__(self, rows: list[dict]) -> None:
                self.rows = rows

            async def list_all(self, project_id: str | None = None) -> list[dict]:
                return self.rows

        project = "project-1"
        with (
            patch("backend.services.feature_execution.get_feature_repository", return_value=_FeatureRepo(feature_rows)),
            patch("backend.services.feature_execution.get_document_repository", return_value=_DocumentRepo(doc_rows)),
        ):
            return await load_feature_execution_derived_state(object(), project, current_feature, [])

    async def test_dependency_completion_uses_reconciliation_equivalence_from_owned_plan_docs(self) -> None:
        current = self._feature(
            "feat-current",
            name="Current",
            status="backlog",
            family="alpha",
            linked_features=[{"feature": "feat-dependency", "type": "blocked_by", "source": "blocked_by"}],
        )
        feature_rows = [
            self._feature_row("feat-current", name="Current", status="backlog", family="alpha", linked_features=current.linkedFeatures),
            self._feature_row("feat-dependency", name="Dependency", status="backlog", family="alpha"),
        ]
        doc_rows = [
            self._doc_row(
                doc_id="doc-dep-plan",
                feature_slug="feat-dependency",
                doc_type="implementation_plan",
                status="completed",
                sequence_order=1,
            )
        ]

        state = await self._load_state(current, feature_rows, doc_rows)

        self.assertEqual(state.dependencyState.state, "unblocked")
        self.assertIn("implementation_plan_completion_equivalent", state.dependencyState.completionEvidence)
        self.assertEqual(state.executionGate.state, "ready")

    async def test_missing_dependency_feature_surfaces_blocked_unknown(self) -> None:
        current = self._feature(
            "feat-current",
            name="Current",
            status="backlog",
            family="alpha",
            linked_features=[{"feature": "feat-missing", "type": "blocked_by", "source": "blocked_by"}],
        )
        feature_rows = [self._feature_row("feat-current", name="Current", status="backlog", family="alpha", linked_features=current.linkedFeatures)]

        state = await self._load_state(current, feature_rows, [])

        self.assertEqual(state.dependencyState.state, "blocked_unknown")
        self.assertEqual(state.executionGate.state, "unknown_dependency_state")
        self.assertEqual(state.dependencyState.firstBlockingDependencyId, "feat-missing")

    async def test_family_order_places_sequenced_items_before_unsequenced_items(self) -> None:
        current = self._feature("feat-2", name="Second", status="backlog", family="alpha")
        feature_rows = [
            self._feature_row("feat-1", name="First", status="done", family="alpha"),
            self._feature_row("feat-2", name="Second", status="backlog", family="alpha"),
            self._feature_row("feat-3", name="Third", status="backlog", family="alpha"),
        ]
        doc_rows = [
            self._doc_row(doc_id="doc-1", feature_slug="feat-1", doc_type="implementation_plan", status="completed", sequence_order=1),
            self._doc_row(doc_id="doc-2", feature_slug="feat-2", doc_type="implementation_plan", status="pending", sequence_order=2),
            self._doc_row(doc_id="doc-3", feature_slug="feat-3", doc_type="implementation_plan", status="pending"),
        ]

        state = await self._load_state(current, feature_rows, doc_rows)

        self.assertEqual([item.featureId for item in state.familySummary.items], ["feat-1", "feat-2", "feat-3"])
        self.assertEqual(state.familyPosition.display, "2 of 3")
        self.assertEqual(state.executionGate.state, "ready")
        self.assertEqual(state.recommendedFamilyItem.featureId if state.recommendedFamilyItem else "", "feat-2")

    async def test_execution_gate_waits_on_family_predecessor_when_earlier_item_is_incomplete(self) -> None:
        current = self._feature("feat-2", name="Second", status="backlog", family="alpha")
        feature_rows = [
            self._feature_row("feat-1", name="First", status="backlog", family="alpha"),
            self._feature_row("feat-2", name="Second", status="backlog", family="alpha"),
        ]
        doc_rows = [
            self._doc_row(doc_id="doc-1", feature_slug="feat-1", doc_type="implementation_plan", status="pending", sequence_order=1),
            self._doc_row(doc_id="doc-2", feature_slug="feat-2", doc_type="implementation_plan", status="pending", sequence_order=2),
        ]

        state = await self._load_state(current, feature_rows, doc_rows)

        self.assertEqual(state.dependencyState.state, "unblocked")
        self.assertEqual(state.executionGate.state, "waiting_on_family_predecessor")
        self.assertEqual(state.executionGate.firstExecutableFamilyItemId, "feat-1")
        self.assertEqual(state.executionGate.recommendedFamilyItemId, "feat-1")

    async def test_feature_planning_status_infers_completion_from_phase_tasks(self) -> None:
        phase = FeaturePhase(
            id="feat-current:phase-1",
            phase="1",
            title="Phase 1",
            status="backlog",
            progress=100,
            totalTasks=3,
            completedTasks=3,
            deferredTasks=0,
            tasks=[],
        )
        current = self._feature("feat-current", name="Current", status="backlog", family="alpha", phases=[phase])
        feature_rows = [
            self._feature_row(
                "feat-current",
                name="Current",
                status="backlog",
                family="alpha",
                phases=[phase.model_dump()],
            )
        ]

        await self._load_state(current, feature_rows, [])

        assert current.planningStatus is not None
        self.assertEqual(current.planningStatus.rawStatus, "backlog")
        self.assertEqual(current.planningStatus.effectiveStatus, "done")
        self.assertEqual(current.planningStatus.provenance.source, "inferred_complete")
        self.assertEqual(current.planningStatus.mismatchState.state, "derived")
        self.assertIsNotNone(current.phases[0].planningStatus)
        self.assertEqual(current.phases[0].planningStatus.effectiveStatus, "done")

    async def test_feature_planning_status_reverses_raw_done_when_phase_is_incomplete(self) -> None:
        phase = FeaturePhase(
            id="feat-current:phase-1",
            phase="1",
            title="Phase 1",
            status="backlog",
            progress=0,
            totalTasks=3,
            completedTasks=0,
            deferredTasks=0,
            tasks=[],
        )
        current = self._feature("feat-current", name="Current", status="done", family="alpha", phases=[phase])
        feature_rows = [
            self._feature_row(
                "feat-current",
                name="Current",
                status="done",
                family="alpha",
                phases=[phase.model_dump()],
            )
        ]

        await self._load_state(current, feature_rows, [])

        assert current.planningStatus is not None
        self.assertEqual(current.planningStatus.rawStatus, "done")
        self.assertEqual(current.planningStatus.effectiveStatus, "backlog")
        self.assertEqual(current.planningStatus.provenance.source, "derived")
        self.assertEqual(current.planningStatus.mismatchState.state, "reversed")

    async def test_execution_context_builds_planning_graph_from_lineage_family_and_dependency_relationships(self) -> None:
        prd_path = "docs/project_plans/PRDs/enhancements/feat-2.md"
        design_path = "docs/project_plans/design-specs/feat-2-architecture.md"
        plan_path = "docs/project_plans/implementation_plans/enhancements/feat-2.md"
        progress_path = ".claude/progress/feat-2/phase-1-progress.md"
        report_path = "docs/project_plans/reports/enhancements/feat-2.md"
        dependency_plan_path = "docs/project_plans/implementation_plans/enhancements/feat-1.md"

        current = self._feature(
            "feat-2",
            name="Second",
            status="backlog",
            family="alpha",
            linked_features=[{"feature": "feat-1", "type": "blocked_by", "source": "blocked_by"}],
        )
        feature_rows = [
            self._feature_row("feat-1", name="First", status="done", family="alpha"),
            self._feature_row(
                "feat-2",
                name="Second",
                status="backlog",
                family="alpha",
                linked_features=current.linkedFeatures,
            ),
        ]
        doc_rows = [
            self._doc_row(
                doc_id="dep-plan",
                feature_slug="feat-1",
                doc_type="implementation_plan",
                status="completed",
                sequence_order=1,
                file_path=dependency_plan_path,
            ),
            self._doc_row(
                doc_id="feat-prd",
                feature_slug="feat-2",
                doc_type="prd",
                status="pending",
                file_path=prd_path,
            ),
            self._doc_row(
                doc_id="feat-design",
                feature_slug="feat-2",
                doc_type="design_doc",
                status="review",
                file_path=design_path,
                related_refs=[plan_path],
            ),
            self._doc_row(
                doc_id="feat-plan",
                feature_slug="feat-2",
                doc_type="implementation_plan",
                status="pending",
                sequence_order=2,
                file_path=plan_path,
                blocked_by=[dependency_plan_path],
                related_refs=[report_path],
                prd_ref=prd_path,
                lineage_parent=design_path,
                lineage_type="implementation_of",
            ),
            self._doc_row(
                doc_id="feat-progress",
                feature_slug="feat-2",
                doc_type="progress",
                status="in_progress",
                file_path=progress_path,
                related_refs=[plan_path],
            ),
            self._doc_row(
                doc_id="feat-report",
                feature_slug="feat-2",
                doc_type="report",
                status="review",
                file_path=report_path,
                related_refs=[plan_path],
            ),
        ]

        derived_state = await self._load_state(current, feature_rows, doc_rows)
        documents = [
            LinkedDocument(id="feat-prd", title="PRD", filePath=prd_path, docType="prd"),
            LinkedDocument(
                id="feat-design",
                title="Design",
                filePath=design_path,
                docType="design_doc",
                relatedRefs=[plan_path],
            ),
            LinkedDocument(
                id="feat-plan",
                title="Plan",
                filePath=plan_path,
                docType="implementation_plan",
                blockedBy=[dependency_plan_path],
                relatedRefs=[report_path],
                prdRef=prd_path,
                lineageParent=design_path,
                lineageType="implementation_of",
                sequenceOrder=2,
            ),
            LinkedDocument(
                id="feat-progress",
                title="Progress",
                filePath=progress_path,
                docType="progress",
                relatedRefs=[plan_path],
            ),
            LinkedDocument(
                id="feat-report",
                title="Report",
                filePath=report_path,
                docType="report",
                relatedRefs=[plan_path],
            ),
        ]

        context = build_execution_context(
            feature=current,
            documents=documents,
            sessions=[],
            analytics=FeatureExecutionAnalyticsSummary(sessionCount=0),
            derived_state=derived_state,
        )

        assert context.planningGraph is not None
        edge_set = {(edge.sourceId, edge.targetId, edge.relationType) for edge in context.planningGraph.edges}
        self.assertIn(("feat-prd", "feat-plan", "implements"), edge_set)
        self.assertIn(("feat-design", "feat-plan", "implements"), edge_set)
        self.assertIn(("feat-plan", "feat-progress", "tracked_by"), edge_set)
        self.assertIn(("feat-plan", "feat-report", "executed_by"), edge_set)
        self.assertIn(("dep-plan", "feat-plan", "family_member_of"), edge_set)
        self.assertIn(("dep-plan", "feat-plan", "blocked_by"), edge_set)


if __name__ == "__main__":
    unittest.main()
