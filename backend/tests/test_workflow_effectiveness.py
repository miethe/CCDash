import types
import unittest

import aiosqlite

from backend import config
from backend.db.factory import (
    get_agentic_intelligence_repository,
    get_session_repository,
    get_session_usage_repository,
    get_test_integrity_repository,
    get_test_run_repository,
)
from backend.db.sqlite_migrations import run_migrations
from backend.services.workflow_effectiveness import (
    _session_workload_tokens,
    detect_failure_patterns,
    get_workflow_effectiveness,
)


class WorkflowEffectivenessTests(unittest.IsolatedAsyncioTestCase):
    def test_session_workload_tokens_prefers_observed_tokens(self) -> None:
        row = {"tokens_in": 10, "tokens_out": 20, "observed_tokens": 95}
        self.assertEqual(_session_workload_tokens(row), 95)

    async def asyncSetUp(self) -> None:
        self._prev_flag = config.CCDASH_TEST_VISUALIZER_ENABLED
        config.CCDASH_TEST_VISUALIZER_ENABLED = True
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.project = types.SimpleNamespace(id="project-1")
        self.session_repo = get_session_repository(self.db)
        self.usage_repo = get_session_usage_repository(self.db)
        self.intelligence_repo = get_agentic_intelligence_repository(self.db)
        self.test_run_repo = get_test_run_repository(self.db)
        self.integrity_repo = get_test_integrity_repository(self.db)
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
                "external_id": "wf_project",
                "display_name": "Phase Execution",
                "resolution_metadata": {
                    "effectiveWorkflowId": "wf_project",
                    "effectiveWorkflowName": "Phase Execution",
                    "swdlSummary": {"artifactRefs": ["skill:symbols"]},
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
                "resolution_metadata": {
                    "artifactType": "skill",
                    "artifactName": "symbols",
                },
            }
        )
        await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "bundle",
                "external_id": "bundle_python",
                "display_name": "Python Essentials",
                "resolution_metadata": {
                    "bundleSummary": {"artifactRefs": ["skill:symbols"]},
                },
            }
        )

        await self.session_repo.upsert(
            {
                "id": "session-1",
                "taskId": "feature-1",
                "status": "completed",
                "model": "gpt-5",
                "durationSeconds": 600,
                "tokensIn": 1200,
                "tokensOut": 2000,
                "modelIOTokens": 3200,
                "cacheReadInputTokens": 300,
                "cacheInputTokens": 300,
                "totalCost": 1.5,
                "qualityRating": 4,
                "startedAt": "2026-03-07T10:00:00+00:00",
                "endedAt": "2026-03-07T10:10:00+00:00",
                "createdAt": "2026-03-07T10:00:00+00:00",
                "updatedAt": "2026-03-07T10:10:00+00:00",
                "sessionForensics": {
                    "queuePressure": {"operationCounts": {"enqueue": 1}},
                    "subagentTopology": {"subagentStartCount": 1},
                    "testExecution": {"runCount": 1, "resultCounts": {"passed": 10}},
                },
            },
            "project-1",
        )
        await self.session_repo.upsert(
            {
                "id": "session-2",
                "taskId": "feature-1",
                "status": "completed",
                "model": "gpt-5",
                "durationSeconds": 14400,
                "tokensIn": 140000,
                "tokensOut": 220000,
                "modelIOTokens": 360000,
                "totalCost": 20.0,
                "qualityRating": 1,
                "startedAt": "2026-03-07T12:00:00+00:00",
                "endedAt": "2026-03-07T14:00:00+00:00",
                "createdAt": "2026-03-07T12:00:00+00:00",
                "updatedAt": "2026-03-07T14:00:00+00:00",
                "sessionForensics": {
                    "queuePressure": {"operationCounts": {"enqueue": 6, "retry": 4}},
                    "subagentTopology": {"subagentStartCount": 5},
                    "testExecution": {"runCount": 0},
                },
            },
            "project-1",
        )

        await self.intelligence_repo.upsert_stack_observation(
            {
                "project_id": "project-1",
                "session_id": "session-1",
                "feature_id": "feature-1",
                "workflow_ref": "phase-execution",
                "confidence": 0.92,
                "evidence": {"commands": ["/dev:execute-phase 3"]},
            },
            components=[
                {
                    "project_id": "project-1",
                    "component_type": "workflow",
                    "component_key": "phase-execution",
                    "status": "resolved",
                    "confidence": 0.95,
                    "external_definition_id": workflow["id"],
                    "external_definition_type": "workflow",
                    "external_definition_external_id": "wf_project",
                    "payload": {"workflowRef": "phase-execution"},
                },
                {
                    "project_id": "project-1",
                    "component_type": "agent",
                    "component_key": "backend-architect",
                    "status": "resolved",
                    "confidence": 0.95,
                    "payload": {"name": "backend-architect"},
                },
                {
                    "project_id": "project-1",
                    "component_type": "skill",
                    "component_key": "symbols",
                    "status": "resolved",
                    "confidence": 0.9,
                    "external_definition_id": skill["id"],
                    "external_definition_type": "artifact",
                    "external_definition_external_id": "symbols",
                    "payload": {"skill": "symbols"},
                },
            ],
        )
        await self.intelligence_repo.upsert_stack_observation(
            {
                "project_id": "project-1",
                "session_id": "session-2",
                "feature_id": "feature-1",
                "workflow_ref": "debug-loop",
                "confidence": 0.6,
                "evidence": {"commands": ["/debug:investigate", "pytest backend/tests/test_router.py"]},
            },
            components=[
                {
                    "project_id": "project-1",
                    "component_type": "agent",
                    "component_key": "ultrathink-debugger",
                    "status": "explicit",
                    "confidence": 0.8,
                    "payload": {"name": "ultrathink-debugger"},
                },
                {
                    "project_id": "project-1",
                    "component_type": "skill",
                    "component_key": "symbols",
                    "status": "explicit",
                    "confidence": 0.8,
                    "payload": {"skill": "symbols"},
                },
            ],
        )

        await self.test_run_repo.upsert(
            {
                "run_id": "run-1",
                "project_id": "project-1",
                "timestamp": "2026-03-07T10:09:00+00:00",
                "agent_session_id": "session-1",
                "total_tests": 10,
                "passed_tests": 10,
                "failed_tests": 0,
            }
        )
        await self.integrity_repo.upsert(
            {
                "signal_id": "signal-1",
                "project_id": "project-1",
                "git_sha": "abc123",
                "file_path": "backend/router.py",
                "signal_type": "test_regression",
                "severity": "high",
                "agent_session_id": "session-2",
                "created_at": "2026-03-07T13:00:00+00:00",
            }
        )
        await self.usage_repo.replace_session_usage(
            "project-1",
            "session-1",
            [
                {
                    "id": "evt-session-1",
                    "root_session_id": "session-1",
                    "linked_session_id": "",
                    "source_log_id": "log-1",
                    "captured_at": "2026-03-07T10:01:00+00:00",
                    "event_kind": "message",
                    "model": "gpt-5",
                    "tool_name": "",
                    "agent_name": "backend-architect",
                    "token_family": "model_input",
                    "delta_tokens": 1200,
                    "cost_usd_model_io": 1.5,
                    "metadata_json": {},
                },
                {
                    "id": "evt-session-1-cache",
                    "root_session_id": "session-1",
                    "linked_session_id": "",
                    "source_log_id": "log-2",
                    "captured_at": "2026-03-07T10:02:00+00:00",
                    "event_kind": "message",
                    "model": "gpt-5",
                    "tool_name": "",
                    "agent_name": "backend-architect",
                    "token_family": "cache_read_input",
                    "delta_tokens": 300,
                    "cost_usd_model_io": 0.0,
                    "metadata_json": {},
                },
            ],
            [
                {
                    "event_id": "evt-session-1",
                    "entity_type": "workflow",
                    "entity_id": "phase-execution",
                    "attribution_role": "primary",
                    "weight": 1.0,
                    "method": "workflow_membership",
                    "confidence": 0.92,
                    "metadata_json": {},
                },
                {
                    "event_id": "evt-session-1",
                    "entity_type": "skill",
                    "entity_id": "symbols",
                    "attribution_role": "supporting",
                    "weight": 1.0,
                    "method": "skill_window",
                    "confidence": 0.7,
                    "metadata_json": {},
                },
                {
                    "event_id": "evt-session-1-cache",
                    "entity_type": "workflow",
                    "entity_id": "phase-execution",
                    "attribution_role": "primary",
                    "weight": 1.0,
                    "method": "workflow_membership",
                    "confidence": 0.92,
                    "metadata_json": {},
                },
            ],
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()
        config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_flag

    async def test_effectiveness_rollups_are_computed_and_persisted(self) -> None:
        payload = await get_workflow_effectiveness(
            self.db,
            self.project,
            period="all",
            scope_type="workflow",
            recompute=True,
            limit=20,
            offset=0,
        )

        by_scope = {(item["scopeType"], item["scopeId"]): item for item in payload["items"]}
        self.assertIn(("workflow", "phase-execution"), by_scope)
        self.assertIn(("workflow", "debug-loop"), by_scope)
        self.assertGreater(
            by_scope[("workflow", "phase-execution")]["successScore"],
            by_scope[("workflow", "debug-loop")]["successScore"],
        )
        self.assertEqual(by_scope[("workflow", "phase-execution")]["attributedTokens"], 1500)
        self.assertAlmostEqual(by_scope[("workflow", "phase-execution")]["attributionCoverage"], 0.375, places=4)
        self.assertAlmostEqual(by_scope[("workflow", "phase-execution")]["attributedCostUsdModelIO"], 1.5, places=4)

        cached = await self.intelligence_repo.list_effectiveness_rollups(
            "project-1",
            scope_type="workflow",
            period="all",
        )
        self.assertEqual(len(cached), 2)
        self.assertEqual(len(payload["metricDefinitions"]), 4)

    async def test_failure_patterns_identify_debug_and_validation_risks(self) -> None:
        payload = await detect_failure_patterns(
            self.db,
            self.project,
            scope_type="workflow",
            limit=20,
            offset=0,
        )

        pattern_types = {item["patternType"] for item in payload["items"]}
        self.assertIn("queue_waste", pattern_types)
        self.assertIn("debug_loop", pattern_types)
        self.assertIn("weak_validation", pattern_types)

    async def test_effectiveness_rollups_include_effective_workflow_and_bundle_scopes(self) -> None:
        effective_payload = await get_workflow_effectiveness(
            self.db,
            self.project,
            period="all",
            scope_type="effective_workflow",
            recompute=True,
            limit=20,
            offset=0,
        )
        bundle_payload = await get_workflow_effectiveness(
            self.db,
            self.project,
            period="all",
            scope_type="bundle",
            recompute=True,
            limit=20,
            offset=0,
        )

        self.assertEqual(effective_payload["items"][0]["scopeId"], "wf_project")
        self.assertEqual(bundle_payload["items"][0]["scopeId"], "bundle_python")


if __name__ == "__main__":
    unittest.main()
