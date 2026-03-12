import unittest

import aiosqlite

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.repositories.usage_attribution import SqliteSessionUsageRepository
from backend.db.sqlite_migrations import run_migrations
from backend.services.session_usage_analytics import (
    get_session_scope_attribution_metrics,
    get_session_usage_attribution_details,
    get_usage_attribution_calibration,
    get_usage_attribution_drilldown,
    get_usage_attribution_rollup,
)


class SessionUsageAnalyticsServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.session_repo = SqliteSessionRepository(self.db)
        self.usage_repo = SqliteSessionUsageRepository(self.db)
        await self.session_repo.upsert(
            {
                "id": "S-1",
                "taskId": "feature-1",
                "status": "completed",
                "model": "claude-opus-4-6",
                "platformType": "Claude Code",
                "durationSeconds": 10,
                "tokensIn": 60,
                "tokensOut": 40,
                "modelIOTokens": 100,
                "cacheCreationInputTokens": 0,
                "cacheReadInputTokens": 20,
                "cacheInputTokens": 20,
                "observedTokens": 120,
                "totalCost": 1.0,
                "startedAt": "2026-03-10T10:00:00Z",
                "endedAt": "2026-03-10T10:00:10Z",
                "createdAt": "2026-03-10T10:00:00Z",
                "updatedAt": "2026-03-10T10:00:10Z",
                "sourceFile": "sessions/test.jsonl",
                "rootSessionId": "S-1",
                "threadKind": "root",
                "conversationFamilyId": "S-1",
                "sessionType": "session",
            },
            "project-1",
        )
        await self.usage_repo.replace_session_usage(
            "project-1",
            "S-1",
            [
                {
                    "id": "evt-1",
                    "root_session_id": "S-1",
                    "linked_session_id": "",
                    "source_log_id": "log-1",
                    "captured_at": "2026-03-10T10:00:01Z",
                    "event_kind": "message",
                    "model": "claude-opus-4-6",
                    "tool_name": "",
                    "agent_name": "planner",
                    "token_family": "model_input",
                    "delta_tokens": 60,
                    "cost_usd_model_io": 0.6,
                    "metadata_json": {"logIndex": 1},
                },
                {
                    "id": "evt-2",
                    "root_session_id": "S-1",
                    "linked_session_id": "",
                    "source_log_id": "log-2",
                    "captured_at": "2026-03-10T10:00:02Z",
                    "event_kind": "message",
                    "model": "claude-opus-4-6",
                    "tool_name": "",
                    "agent_name": "executor",
                    "token_family": "model_output",
                    "delta_tokens": 40,
                    "cost_usd_model_io": 0.4,
                    "metadata_json": {"logIndex": 2},
                },
                {
                    "id": "evt-3",
                    "root_session_id": "S-1",
                    "linked_session_id": "",
                    "source_log_id": "log-3",
                    "captured_at": "2026-03-10T10:00:03Z",
                    "event_kind": "message",
                    "model": "claude-opus-4-6",
                    "tool_name": "",
                    "agent_name": "planner",
                    "token_family": "cache_read_input",
                    "delta_tokens": 20,
                    "cost_usd_model_io": 0.0,
                    "metadata_json": {"logIndex": 3},
                },
            ],
            [
                {
                    "event_id": "evt-1",
                    "entity_type": "skill",
                    "entity_id": "symbols",
                    "attribution_role": "primary",
                    "weight": 1.0,
                    "method": "explicit_skill_invocation",
                    "confidence": 1.0,
                    "metadata_json": {"sourceLogId": "log-1"},
                },
                {
                    "event_id": "evt-1",
                    "entity_type": "feature",
                    "entity_id": "feature-1",
                    "attribution_role": "supporting",
                    "weight": 1.0,
                    "method": "feature_inheritance",
                    "confidence": 0.8,
                    "metadata_json": {"sourceLogId": "log-1"},
                },
                {
                    "event_id": "evt-2",
                    "entity_type": "agent",
                    "entity_id": "executor",
                    "attribution_role": "primary",
                    "weight": 1.0,
                    "method": "explicit_agent_ownership",
                    "confidence": 0.95,
                    "metadata_json": {"sourceLogId": "log-2"},
                },
                {
                    "event_id": "evt-2",
                    "entity_type": "command",
                    "entity_id": "/dev:execute-phase",
                    "attribution_role": "supporting",
                    "weight": 1.0,
                    "method": "explicit_command_context",
                    "confidence": 0.72,
                    "metadata_json": {"sourceLogId": "log-2"},
                },
                {
                    "event_id": "evt-3",
                    "entity_type": "skill",
                    "entity_id": "symbols",
                    "attribution_role": "primary",
                    "weight": 1.0,
                    "method": "skill_window",
                    "confidence": 0.64,
                    "metadata_json": {"sourceLogId": "log-3"},
                },
            ],
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_rollup_and_drilldown_include_exclusive_and_supporting_totals(self) -> None:
        rollup = await get_usage_attribution_rollup(self.db, project_id="project-1", limit=10)
        self.assertEqual(rollup["summary"]["totalExclusiveModelIOTokens"], 100)
        skill_row = next(row for row in rollup["rows"] if row["entityType"] == "skill")
        self.assertEqual(skill_row["entityId"], "symbols")
        self.assertEqual(skill_row["exclusiveTokens"], 80)
        self.assertEqual(skill_row["exclusiveModelIOTokens"], 60)
        self.assertEqual(skill_row["exclusiveCacheInputTokens"], 20)
        self.assertEqual(skill_row["primaryEventCount"], 2)

        drilldown = await get_usage_attribution_drilldown(
            self.db,
            project_id="project-1",
            entity_type="skill",
            entity_id="symbols",
            limit=10,
        )
        self.assertEqual(drilldown["total"], 2)
        self.assertEqual(drilldown["items"][0]["entityId"], "symbols")
        self.assertEqual(drilldown["summary"]["totalExclusiveTokens"], 80)

    async def test_calibration_and_session_details_reconcile_primary_model_io(self) -> None:
        calibration = await get_usage_attribution_calibration(self.db, project_id="project-1")
        self.assertEqual(calibration["eventCount"], 3)
        self.assertEqual(calibration["primaryAttributedEventCount"], 3)
        self.assertEqual(calibration["exclusiveModelIOTokens"], 100)
        self.assertEqual(calibration["modelIOGap"], 0)
        self.assertEqual(calibration["exclusiveCacheInputTokens"], 20)
        self.assertEqual(calibration["cacheGap"], 0)

        details = await get_session_usage_attribution_details(self.db, project_id="project-1", session_id="S-1")
        self.assertEqual(len(details["usageEvents"]), 3)
        self.assertEqual(len(details["usageAttributions"]), 5)
        self.assertEqual(details["usageAttributionCalibration"]["modelIOGap"], 0)
        self.assertEqual(details["usageAttributionSummary"]["summary"]["totalExclusiveTokens"], 120)

    async def test_session_scope_metrics_support_workflow_rollups(self) -> None:
        metrics = await get_session_scope_attribution_metrics(
            self.db,
            project_id="project-1",
            session_ids=["S-1"],
        )
        skill_metrics = metrics[("S-1", "skill", "symbols")]
        self.assertEqual(skill_metrics["exclusiveTokens"], 80)
        self.assertEqual(skill_metrics["supportingTokens"], 0)
        self.assertEqual(skill_metrics["exclusiveModelIOTokens"], 60)
        self.assertAlmostEqual(skill_metrics["attributionCoverage"], 0.6, places=4)
