import types
import unittest

import aiosqlite

from backend import config
from backend.db.factory import get_agentic_intelligence_repository, get_session_repository
from backend.db.sqlite_migrations import run_migrations
from backend.models import Feature, FeaturePhase, LinkedDocument
from backend.services.feature_execution import build_execution_recommendation
from backend.services.stack_recommendations import build_stack_recommendations


class StackRecommendationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._prev_test_visualizer = config.CCDASH_TEST_VISUALIZER_ENABLED
        config.CCDASH_TEST_VISUALIZER_ENABLED = True
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.project = types.SimpleNamespace(id="project-1")
        self.session_repo = get_session_repository(self.db)
        self.intelligence_repo = get_agentic_intelligence_repository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_test_visualizer

    def _feature(self) -> Feature:
        return Feature(
            id="feature-current",
            name="Current Feature",
            status="backlog",
            totalTasks=0,
            completedTasks=0,
            category="enhancement",
            tags=[],
            updatedAt="",
            linkedDocs=[],
            phases=[
                FeaturePhase(
                    id="feature-current:phase-1",
                    phase="1",
                    title="Phase 1",
                    status="backlog",
                    progress=0,
                    totalTasks=3,
                    completedTasks=0,
                    deferredTasks=0,
                    tasks=[],
                )
            ],
            relatedFeatures=[],
        )

    def _plan_doc(self) -> list[LinkedDocument]:
        return [
            LinkedDocument(
                id="plan-1",
                title="Plan",
                filePath="docs/project_plans/implementation_plans/enhancements/feature-current.md",
                docType="implementation_plan",
            )
        ]

    async def _seed_session(
        self,
        *,
        session_id: str,
        feature_id: str,
        status: str,
        quality_rating: int,
        duration_seconds: int,
        total_cost: float,
        started_at: str,
        ended_at: str,
    ) -> None:
        await self.session_repo.upsert(
            {
                "id": session_id,
                "taskId": feature_id,
                "status": status,
                "model": "gpt-5",
                "durationSeconds": duration_seconds,
                "tokensIn": 1200,
                "tokensOut": 2400,
                "totalCost": total_cost,
                "qualityRating": quality_rating,
                "startedAt": started_at,
                "endedAt": ended_at,
                "createdAt": started_at,
                "updatedAt": ended_at,
                "sessionForensics": {
                    "queuePressure": {"operationCounts": {"enqueue": 1}},
                    "subagentTopology": {"subagentStartCount": 1},
                    "testExecution": {"runCount": 1, "resultCounts": {"passed": 8, "failed": 0}},
                },
            },
            "project-1",
        )

    async def _seed_definitions(self) -> tuple[dict, dict]:
        source = await self.intelligence_repo.upsert_definition_source(
            {
                "project_id": "project-1",
                "source_kind": "skillmeat",
                "enabled": True,
                "base_url": "http://skillmeat.local",
            }
        )
        workflow = await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "workflow",
                "external_id": "phase-execution",
                "display_name": "Phase Execution",
                "source_url": "http://skillmeat.local/workflows/phase-execution",
                "resolution_metadata": {
                    "isEffective": True,
                    "effectiveWorkflowId": "phase-execution",
                    "effectiveWorkflowName": "Phase Execution",
                    "swdlSummary": {"artifactRefs": ["skill:symbols"], "contextRefs": ["ctx:planning"]},
                    "contextSummary": {"referenced": 1, "resolved": 1, "previewed": 1, "previewTokenFootprint": 97},
                    "resolvedContextModules": [
                        {
                            "contextRef": "ctx:planning",
                            "moduleId": "module-planning",
                            "moduleName": "planning",
                            "status": "resolved",
                            "sourceUrl": "http://skillmeat.local/projects/project-1/memory",
                            "previewSummary": {"totalTokens": 97},
                        }
                    ],
                    "recentExecutions": [
                        {
                            "executionId": "exec_1",
                            "status": "completed",
                            "startedAt": "2026-03-07T14:00:00Z",
                            "parameters": {"feature_name": "Current Feature"},
                            "sourceUrl": "http://skillmeat.local/workflows/executions?workflow_id=phase-execution",
                        }
                    ],
                    "executionSummary": {
                        "count": 1,
                        "completed": 1,
                        "sourceUrl": "http://skillmeat.local/workflows/executions?workflow_id=phase-execution",
                        "liveUpdateHint": "idle",
                    },
                },
            }
        )
        skill = await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "artifact",
                "external_id": "symbols",
                "display_name": "symbols",
                "source_url": "http://skillmeat.local/artifacts/symbols",
            }
        )
        await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "bundle",
                "external_id": "bundle_python",
                "display_name": "Python Essentials",
                "source_url": "http://skillmeat.local/collection",
                "resolution_metadata": {
                    "bundleSummary": {"artifactRefs": ["skill:symbols"]},
                },
            }
        )
        return workflow, skill

    async def _seed_observations(self, *, with_definitions: bool) -> None:
        workflow = None
        skill = None
        if with_definitions:
            workflow, skill = await self._seed_definitions()

        await self._seed_session(
            session_id="session-1",
            feature_id="feature-legacy-1",
            status="completed",
            quality_rating=5,
            duration_seconds=600,
            total_cost=1.5,
            started_at="2026-03-07T10:00:00+00:00",
            ended_at="2026-03-07T10:10:00+00:00",
        )
        await self._seed_session(
            session_id="session-2",
            feature_id="feature-legacy-2",
            status="completed",
            quality_rating=4,
            duration_seconds=900,
            total_cost=2.5,
            started_at="2026-03-07T11:00:00+00:00",
            ended_at="2026-03-07T11:15:00+00:00",
        )
        await self._seed_session(
            session_id="session-3",
            feature_id="feature-debug",
            status="failed",
            quality_rating=1,
            duration_seconds=3600,
            total_cost=9.0,
            started_at="2026-03-07T12:00:00+00:00",
            ended_at="2026-03-07T13:00:00+00:00",
        )

        phase_components = [
            {
                "project_id": "project-1",
                "component_type": "workflow",
                "component_key": "phase-execution",
                "status": "resolved" if with_definitions else "inferred",
                "confidence": 0.95,
                "external_definition_id": workflow["id"] if workflow else None,
                "external_definition_type": "workflow" if with_definitions else "",
                "external_definition_external_id": "phase-execution" if with_definitions else "",
                "payload": {"workflowRef": "phase-execution"},
            },
            {
                "project_id": "project-1",
                "component_type": "agent",
                "component_key": "backend-architect",
                "status": "explicit",
                "confidence": 0.9,
                "payload": {"name": "backend-architect"},
            },
            {
                "project_id": "project-1",
                "component_type": "skill",
                "component_key": "symbols",
                "status": "resolved" if with_definitions else "explicit",
                "confidence": 0.9,
                "external_definition_id": skill["id"] if skill else None,
                "external_definition_type": "artifact" if with_definitions else "",
                "external_definition_external_id": "symbols" if with_definitions else "",
                "payload": {"skill": "symbols"},
            },
        ]

        for session_id, feature_id in (("session-1", "feature-legacy-1"), ("session-2", "feature-legacy-2")):
            await self.intelligence_repo.upsert_stack_observation(
                {
                    "project_id": "project-1",
                    "session_id": session_id,
                    "feature_id": feature_id,
                    "workflow_ref": "phase-execution",
                    "confidence": 0.92,
                    "evidence": {"commands": ["/dev:execute-phase 2 docs/project_plans/implementation_plans/enhancements/example.md"]},
                },
                components=phase_components,
            )

        await self.intelligence_repo.upsert_stack_observation(
            {
                "project_id": "project-1",
                "session_id": "session-3",
                "feature_id": "feature-debug",
                "workflow_ref": "debug-loop",
                "confidence": 0.6,
                "evidence": {"commands": ["/debug:investigate"]},
            },
            components=[
                {
                    "project_id": "project-1",
                    "component_type": "workflow",
                    "component_key": "debug-loop",
                    "status": "inferred",
                    "confidence": 0.7,
                    "payload": {"workflowRef": "debug-loop"},
                },
                {
                    "project_id": "project-1",
                    "component_type": "agent",
                    "component_key": "ultrathink-debugger",
                    "status": "explicit",
                    "confidence": 0.8,
                    "payload": {"name": "ultrathink-debugger"},
                },
            ],
        )

    async def test_build_stack_recommendations_returns_ranked_stack_and_similar_work(self) -> None:
        await self._seed_observations(with_definitions=True)
        feature = self._feature()
        recommendation = build_execution_recommendation(feature, self._plan_doc())

        payload = await build_stack_recommendations(
            self.db,
            self.project,
            feature=feature,
            sessions=[],
            recommendation=recommendation,
        )

        self.assertIsNotNone(payload["recommendedStack"])
        self.assertEqual(payload["recommendedStack"].workflowRef, "phase-execution")
        self.assertGreaterEqual(payload["recommendedStack"].sampleSize, 2)
        self.assertTrue(any(component.definition for component in payload["recommendedStack"].components if component.componentType in {"workflow", "skill"}))
        self.assertGreaterEqual(len(payload["stackAlternatives"]), 1)
        similar_work_evidence = next(item for item in payload["stackEvidence"] if item.sourceType == "similar_work")
        self.assertLessEqual(len(similar_work_evidence.similarWork), 3)
        self.assertGreaterEqual(len(similar_work_evidence.similarWork), 1)
        self.assertTrue(similar_work_evidence.similarWork[0].reasons)
        evidence_types = {item.sourceType for item in payload["stackEvidence"]}
        self.assertIn("effective_workflow", evidence_types)
        self.assertIn("context_preview", evidence_types)
        self.assertIn("bundle_alignment", evidence_types)
        self.assertIn("workflow_execution", evidence_types)
        context_evidence = next(item for item in payload["stackEvidence"] if item.sourceType == "context_preview")
        self.assertEqual(context_evidence.metrics["resolved"], 1)
        self.assertEqual(context_evidence.metrics["resolvedContexts"][0]["moduleName"], "planning")
        effective_evidence = next(item for item in payload["stackEvidence"] if item.sourceType == "effective_workflow")
        self.assertEqual(effective_evidence.metrics["effectiveWorkflowId"], "phase-execution")
        self.assertEqual(effective_evidence.metrics["sourceUrl"], "http://skillmeat.local/workflows/phase-execution")
        self.assertEqual(payload["definitionResolutionWarnings"], [])

    async def test_build_stack_recommendations_warns_when_definitions_are_missing(self) -> None:
        await self._seed_observations(with_definitions=False)
        feature = self._feature()
        recommendation = build_execution_recommendation(feature, self._plan_doc())

        payload = await build_stack_recommendations(
            self.db,
            self.project,
            feature=feature,
            sessions=[],
            recommendation=recommendation,
        )

        self.assertIsNotNone(payload["recommendedStack"])
        self.assertEqual(payload["recommendedStack"].workflowRef, "phase-execution")
        self.assertGreaterEqual(len(payload["definitionResolutionWarnings"]), 1)
        self.assertIn("local CCDash observations", payload["definitionResolutionWarnings"][0].message)


if __name__ == "__main__":
    unittest.main()
