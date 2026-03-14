import types
import unittest

import aiosqlite

from backend.db.factory import get_agentic_intelligence_repository, get_session_repository
from backend.db.sqlite_migrations import run_migrations
from backend.services.workflow_registry import get_workflow_registry_detail, list_workflow_registry


class WorkflowRegistryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.session_repo = get_session_repository(self.db)
        self.intelligence_repo = get_agentic_intelligence_repository(self.db)
        self.project = types.SimpleNamespace(
            id="project-1",
            skillMeat=types.SimpleNamespace(
                webBaseUrl="http://skillmeat-web.local:3000",
                projectId="project-1",
                collectionId="default",
            ),
        )
        await self._seed_definitions()
        await self._seed_sessions_and_observations()
        await self._seed_rollups()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _seed_definitions(self) -> None:
        source = await self.intelligence_repo.upsert_definition_source(
            {
                "project_id": "project-1",
                "source_kind": "skillmeat",
                "enabled": True,
                "base_url": "http://skillmeat.local",
            }
        )
        await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "workflow",
                "external_id": "phase-execution",
                "display_name": "Phase Execution",
                "source_url": "http://skillmeat.local/workflows/phase-execution",
                "fetched_at": "2026-03-10T00:00:00+00:00",
                "resolution_metadata": {
                    "isEffective": True,
                    "effectiveWorkflowId": "phase-execution",
                    "effectiveWorkflowName": "Phase Execution",
                    "workflowScope": "project",
                    "aliases": ["/dev:execute-phase", "dev:execute-phase"],
                    "swdlSummary": {
                        "artifactRefs": ["skill:symbols", "agent:backend-architect"],
                        "contextRefs": ["ctx:planning", "ctx:qa"],
                        "stageOrder": ["plan", "implement", "validate"],
                        "gateCount": 2,
                        "fanOutCount": 1,
                    },
                    "planSummary": {"steps": 3, "lastReviewedAt": "2026-03-11T00:00:00Z"},
                    "resolvedContextModules": [
                        {
                            "contextRef": "ctx:planning",
                            "moduleId": "planning-module",
                            "moduleName": "planning",
                            "status": "resolved",
                            "sourceUrl": "http://skillmeat.local/projects/project-1/memory",
                            "previewSummary": {"totalTokens": 120},
                        }
                    ],
                    "recentExecutions": [
                        {
                            "executionId": "exec-1",
                            "status": "completed",
                            "startedAt": "2026-03-12T09:00:00Z",
                            "sourceUrl": "http://skillmeat.local/workflows/executions?workflow_id=phase-execution",
                            "parameters": {"feature_name": "Workflow Registry"},
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
        await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "workflow",
                "external_id": "planning",
                "display_name": "Planning",
                "source_url": "http://skillmeat.local/workflows/planning",
                "fetched_at": "2026-03-10T00:00:00+00:00",
                "resolution_metadata": {
                    "aliases": ["/plan:plan-feature"],
                    "workflowScope": "project",
                    "swdlSummary": {
                        "artifactRefs": ["skill:planning"],
                        "contextRefs": ["ctx:planning"],
                        "stageOrder": ["draft", "review"],
                        "gateCount": 1,
                        "fanOutCount": 0,
                    },
                    "resolvedContextModules": [
                        {
                            "contextRef": "ctx:planning",
                            "moduleId": "planning-module",
                            "moduleName": "planning",
                            "status": "resolved",
                            "sourceUrl": "http://skillmeat.local/projects/project-1/memory",
                            "previewSummary": {"totalTokens": 80},
                        }
                    ],
                },
            }
        )
        await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "workflow",
                "external_id": "empty-workflow",
                "display_name": "Empty Workflow",
                "source_url": "http://skillmeat.local/workflows/empty-workflow",
                "fetched_at": "2026-03-10T00:00:00+00:00",
                "resolution_metadata": {},
            }
        )
        await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "artifact",
                "external_id": "command:execute-phase",
                "display_name": "/dev:execute-phase",
                "source_url": "http://skillmeat.local/collection?collection=default&artifact=command%3Aexecute-phase",
                "fetched_at": "2026-03-10T00:00:00+00:00",
                "resolution_metadata": {
                    "artifactType": "command",
                    "artifactName": "execute-phase",
                    "aliases": ["/dev:execute-phase"],
                },
            }
        )
        await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "artifact",
                "external_id": "command:quick-feature",
                "display_name": "/dev:quick-feature",
                "source_url": "http://skillmeat.local/collection?collection=default&artifact=command%3Aquick-feature",
                "fetched_at": "2020-01-01T00:00:00+00:00",
                "resolution_metadata": {
                    "artifactType": "command",
                    "artifactName": "quick-feature",
                    "aliases": ["/dev:quick-feature"],
                },
            }
        )
        await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "bundle",
                "external_id": "bundle-python",
                "display_name": "Python Essentials",
                "source_url": "http://skillmeat.local/collection?collection=default",
                "fetched_at": "2026-03-10T00:00:00+00:00",
                "resolution_metadata": {
                    "bundleSummary": {
                        "artifactRefs": ["skill:symbols", "agent:backend-architect"],
                    }
                },
            }
        )

    async def _seed_session(self, session_id: str, workflow_ref: str, started_at: str) -> None:
        await self.session_repo.upsert(
            {
                "id": session_id,
                "taskId": f"feature-{session_id}",
                "status": "completed",
                "model": "gpt-5",
                "startedAt": started_at,
                "endedAt": "2026-03-12T10:00:00+00:00",
                "createdAt": started_at,
                "updatedAt": "2026-03-12T10:00:00+00:00",
                "sessionForensics": {"queuePressure": {"operationCounts": {"enqueue": 1}}},
            },
            "project-1",
        )
        await self.session_repo.upsert_logs(
            session_id,
            [
                {
                    "timestamp": started_at,
                    "speaker": "agent",
                    "type": "command",
                    "content": f"{workflow_ref} docs/plan.md",
                    "metadata": {"args": "docs/plan.md"},
                }
            ],
        )

    async def _seed_sessions_and_observations(self) -> None:
        await self._seed_session("session-hybrid", "/dev:execute-phase", "2026-03-12T09:00:00+00:00")
        await self._seed_session("session-strong", "/plan:plan-feature", "2026-03-12T08:00:00+00:00")
        await self._seed_session("session-weak", "/dev:quick-feature", "2026-03-11T08:00:00+00:00")
        await self._seed_session("session-unresolved", "/dev:mystery-flow", "2026-03-10T08:00:00+00:00")

        await self.intelligence_repo.upsert_stack_observation(
            {
                "project_id": "project-1",
                "session_id": "session-hybrid",
                "feature_id": "feature-session-hybrid",
                "workflow_ref": "/dev:execute-phase",
                "confidence": 0.97,
                "evidence": {
                    "commands": ["/dev:execute-phase 1 docs/plan.md"],
                },
                "updated_at": "2026-03-12T09:05:00+00:00",
            },
            [
                {
                    "component_type": "workflow",
                    "component_key": "/dev:execute-phase",
                    "status": "resolved",
                    "confidence": 0.97,
                    "external_definition_type": "workflow",
                    "external_definition_external_id": "phase-execution",
                    "payload": {"workflowRef": "/dev:execute-phase"},
                },
                {
                    "component_type": "command",
                    "component_key": "/dev:execute-phase",
                    "status": "resolved",
                    "confidence": 0.93,
                    "external_definition_type": "artifact",
                    "external_definition_external_id": "command:execute-phase",
                    "payload": {"command": "/dev:execute-phase"},
                },
                {
                    "component_type": "skill",
                    "component_key": "symbols",
                    "status": "explicit",
                    "confidence": 0.8,
                    "payload": {"skill": "symbols"},
                },
                {
                    "component_type": "agent",
                    "component_key": "backend-architect",
                    "status": "explicit",
                    "confidence": 0.8,
                    "payload": {"name": "backend-architect"},
                },
            ],
            "project-1",
        )

        await self.intelligence_repo.upsert_stack_observation(
            {
                "project_id": "project-1",
                "session_id": "session-strong",
                "feature_id": "feature-session-strong",
                "workflow_ref": "/plan:plan-feature",
                "confidence": 0.95,
                "evidence": {
                    "commands": ["/plan:plan-feature docs/project.md"],
                },
                "updated_at": "2026-03-12T08:05:00+00:00",
            },
            [
                {
                    "component_type": "workflow",
                    "component_key": "/plan:plan-feature",
                    "status": "resolved",
                    "confidence": 0.95,
                    "external_definition_type": "workflow",
                    "external_definition_external_id": "planning",
                    "payload": {"workflowRef": "/plan:plan-feature"},
                }
            ],
            "project-1",
        )

        await self.intelligence_repo.upsert_stack_observation(
            {
                "project_id": "project-1",
                "session_id": "session-weak",
                "feature_id": "feature-session-weak",
                "workflow_ref": "/dev:quick-feature",
                "confidence": 0.88,
                "evidence": {
                    "commands": ["/dev:quick-feature req-12"],
                },
                "updated_at": "2026-03-11T08:05:00+00:00",
            },
            [
                {
                    "component_type": "workflow",
                    "component_key": "/dev:quick-feature",
                    "status": "resolved",
                    "confidence": 0.88,
                    "external_definition_type": "artifact",
                    "external_definition_external_id": "command:quick-feature",
                    "payload": {"workflowRef": "/dev:quick-feature"},
                }
            ],
            "project-1",
        )

        await self.intelligence_repo.upsert_stack_observation(
            {
                "project_id": "project-1",
                "session_id": "session-unresolved",
                "feature_id": "feature-session-unresolved",
                "workflow_ref": "/dev:mystery-flow",
                "confidence": 0.41,
                "evidence": {
                    "commands": ["/dev:mystery-flow"],
                },
                "updated_at": "2026-03-10T08:05:00+00:00",
            },
            [
                {
                    "component_type": "workflow",
                    "component_key": "/dev:mystery-flow",
                    "status": "unresolved",
                    "confidence": 0.41,
                    "payload": {"workflowRef": "/dev:mystery-flow"},
                }
            ],
            "project-1",
        )

    async def _seed_rollups(self) -> None:
        await self.intelligence_repo.upsert_effectiveness_rollup(
            {
                "project_id": "project-1",
                "scope_type": "effective_workflow",
                "scope_id": "phase-execution",
                "period": "all",
                "metrics": {
                    "scopeLabel": "Phase Execution",
                    "sampleSize": 4,
                    "successScore": 0.91,
                    "efficiencyScore": 0.82,
                    "qualityScore": 0.88,
                    "riskScore": 0.19,
                    "attributionCoverage": 0.77,
                    "averageAttributionConfidence": 0.84,
                },
                "evidence_summary": {"representativeSessionIds": ["session-hybrid"]},
            },
            "project-1",
        )
        await self.intelligence_repo.upsert_effectiveness_rollup(
            {
                "project_id": "project-1",
                "scope_type": "workflow",
                "scope_id": "/plan:plan-feature",
                "period": "all",
                "metrics": {
                    "scopeLabel": "Planning",
                    "sampleSize": 2,
                    "successScore": 0.9,
                    "efficiencyScore": 0.86,
                    "qualityScore": 0.89,
                    "riskScore": 0.14,
                    "attributionCoverage": 0.71,
                    "averageAttributionConfidence": 0.8,
                },
                "evidence_summary": {"representativeSessionIds": ["session-strong"]},
            },
            "project-1",
        )

    async def test_registry_lists_all_correlation_states(self) -> None:
        payload = await list_workflow_registry(self.db, self.project, limit=20, offset=0)

        states = {
            item["identity"]["displayLabel"]: item["correlationState"]
            for item in payload["items"]
        }

        self.assertEqual(states["Phase Execution"], "hybrid")
        self.assertEqual(states["Planning"], "strong")
        self.assertEqual(states["/dev:quick-feature"], "weak")
        self.assertEqual(states["/dev:mystery-flow"], "unresolved")
        self.assertEqual(states["Empty Workflow"], "strong")

    async def test_registry_detail_enriches_composition_effectiveness_and_actions(self) -> None:
        detail = await get_workflow_registry_detail(self.db, self.project, registry_id="workflow:phase-execution")

        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["effectiveness"]["scopeType"], "effective_workflow")
        self.assertEqual(detail["composition"]["artifactRefs"], ["skill:symbols", "agent:backend-architect"])
        self.assertEqual(detail["composition"]["stageOrder"], ["plan", "implement", "validate"])
        self.assertEqual(detail["composition"]["bundleAlignment"]["bundleId"], "bundle-python")
        self.assertEqual(detail["recentExecutions"][0]["executionId"], "exec-1")
        self.assertTrue(any(action["id"] == "open-workflow" and not action["disabled"] for action in detail["actions"]))
        self.assertTrue(any(session["sessionId"] == "session-hybrid" for session in detail["representativeSessions"]))

    async def test_registry_surfaces_expected_issue_types(self) -> None:
        weak_detail = await get_workflow_registry_detail(self.db, self.project, registry_id="command:command:quick-feature")
        unresolved_detail = await get_workflow_registry_detail(self.db, self.project, registry_id="observed:/dev:mystery-flow")
        empty_detail = await get_workflow_registry_detail(self.db, self.project, registry_id="workflow:empty-workflow")

        self.assertIsNotNone(weak_detail)
        self.assertIsNotNone(unresolved_detail)
        self.assertIsNotNone(empty_detail)
        assert weak_detail is not None
        assert unresolved_detail is not None
        assert empty_detail is not None

        weak_issue_codes = {issue["code"] for issue in weak_detail["issues"]}
        unresolved_issue_codes = {issue["code"] for issue in unresolved_detail["issues"]}
        empty_issue_codes = {issue["code"] for issue in empty_detail["issues"]}

        self.assertIn("weak_resolution", weak_issue_codes)
        self.assertIn("stale_cache", weak_issue_codes)
        self.assertIn("unresolved_workflow", unresolved_issue_codes)
        self.assertIn("missing_effectiveness", unresolved_issue_codes)
        self.assertIn("missing_composition", empty_issue_codes)
        self.assertIn("no_recent_observations", empty_issue_codes)

    async def test_registry_search_and_state_filters(self) -> None:
        search_payload = await list_workflow_registry(self.db, self.project, search="quick", limit=20, offset=0)
        state_payload = await list_workflow_registry(self.db, self.project, correlation_state="hybrid", limit=20, offset=0)

        self.assertEqual([item["identity"]["displayLabel"] for item in search_payload["items"]], ["/dev:quick-feature"])
        self.assertEqual([item["identity"]["displayLabel"] for item in state_payload["items"]], ["Phase Execution"])


if __name__ == "__main__":
    unittest.main()
