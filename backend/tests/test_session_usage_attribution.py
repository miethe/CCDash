import unittest

import aiosqlite

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.repositories.usage_attribution import SqliteSessionUsageRepository
from backend.db.sqlite_migrations import run_migrations
from backend.services.session_usage_attribution import (
    build_session_usage_attributions,
    build_session_usage_events,
)


class SessionUsageAttributionBuilderTests(unittest.TestCase):
    def test_build_session_usage_events_reconciles_families_and_allocates_model_cost(self) -> None:
        session_payload = {
            "id": "S-100",
            "rootSessionId": "S-100",
            "model": "claude-opus-4-6",
            "startedAt": "2026-03-10T10:00:00Z",
            "endedAt": "2026-03-10T10:10:00Z",
            "totalCost": 1.5,
            "sessionForensics": {
                "usageSummary": {
                    "relayMirrorTotals": {
                        "excludedCount": 1,
                        "inputTokens": 100,
                        "outputTokens": 200,
                        "cacheCreationInputTokens": 300,
                        "cacheReadInputTokens": 400,
                        "policy": "excluded_from_observed_tokens_until_attribution",
                    }
                }
            },
        }
        logs = [
            {
                "id": "log-1",
                "timestamp": "2026-03-10T10:00:01Z",
                "type": "message",
                "agentName": "planner",
                "metadata": {
                    "model": "claude-opus-4-6",
                    "inputTokens": 10,
                    "outputTokens": 20,
                    "cache_creation_input_tokens": 5,
                    "cache_read_input_tokens": 15,
                },
            },
            {
                "id": "log-2",
                "timestamp": "2026-03-10T10:00:05Z",
                "type": "tool",
                "agentName": "executor",
                "toolCall": {"name": "Bash"},
                "metadata": {
                    "bashCommand": "pnpm test",
                    "toolUseResult_usage": {
                        "input_tokens": 3,
                        "output_tokens": 4,
                        "cache_creation_input_tokens": 1,
                        "cache_read_input_tokens": 2,
                    },
                    "toolUseResult_totalTokens": 10,
                },
            },
        ]

        events = build_session_usage_events("project-1", session_payload, logs)
        totals = {
            family: sum(int(event["delta_tokens"]) for event in events if event["token_family"] == family)
            for family in {
                "model_input",
                "model_output",
                "cache_creation_input",
                "cache_read_input",
                "tool_result_input",
                "tool_result_output",
                "tool_result_cache_creation_input",
                "tool_result_cache_read_input",
                "tool_reported_total",
                "relay_mirror_input",
                "relay_mirror_output",
                "relay_mirror_cache_creation_input",
                "relay_mirror_cache_read_input",
            }
        }

        self.assertEqual(totals["model_input"], 10)
        self.assertEqual(totals["model_output"], 20)
        self.assertEqual(totals["cache_creation_input"], 5)
        self.assertEqual(totals["cache_read_input"], 15)
        self.assertEqual(totals["tool_result_input"], 3)
        self.assertEqual(totals["tool_result_output"], 4)
        self.assertEqual(totals["tool_result_cache_creation_input"], 1)
        self.assertEqual(totals["tool_result_cache_read_input"], 2)
        self.assertEqual(totals["tool_reported_total"], 10)
        self.assertEqual(totals["relay_mirror_input"], 100)
        self.assertEqual(totals["relay_mirror_output"], 200)
        self.assertEqual(totals["relay_mirror_cache_creation_input"], 300)
        self.assertEqual(totals["relay_mirror_cache_read_input"], 400)

        model_cost = sum(float(event["cost_usd_model_io"]) for event in events)
        self.assertAlmostEqual(model_cost, 1.5, places=6)
        tool_result_cost = sum(
            float(event["cost_usd_model_io"])
            for event in events
            if str(event["event_kind"]).startswith("tool_result")
        )
        self.assertEqual(tool_result_cost, 0.0)

    def test_build_session_usage_attributions_prefers_explicit_primary_and_adds_supporting_links(self) -> None:
        session_payload = {
            "id": "S-200",
            "rootSessionId": "S-200",
            "threadKind": "root",
            "featureId": "claude-code-session-usage-attribution-v2",
            "sessionForensics": {
                "entryContext": {
                    "skillLoads": [
                        {"skill": "symbols", "sourceLogId": "log-10"},
                    ]
                }
            },
        }
        logs = [
            {
                "id": "log-5",
                "log_index": 5,
                "timestamp": "2026-03-10T10:00:00Z",
                "type": "command",
                "content": "/dev:execute-phase",
                "metadata": {
                    "args": "1-3 docs/project_plans/implementation_plans/enhancements/claude-code-session-usage-attribution-v2.md",
                    "parsedCommand": {
                        "featureSlugCanonical": "claude-code-session-usage-attribution-v2",
                    },
                },
            },
            {
                "id": "log-10",
                "log_index": 10,
                "timestamp": "2026-03-10T10:00:05Z",
                "type": "tool",
                "tool_name": "Skill",
                "metadata": {"toolLabel": "symbols"},
            },
            {
                "id": "log-11",
                "log_index": 11,
                "timestamp": "2026-03-10T10:00:06Z",
                "type": "tool",
                "tool_name": "Bash",
                "agent_name": "executor",
                "linked_session_id": "agent-sub-1",
                "metadata": {"bashCommand": "pnpm test"},
            },
        ]
        artifacts = [
            {
                "id": "ART-1",
                "title": "Test run artifact",
                "type": "test_run",
                "source_log_id": "log-11",
            }
        ]
        usage_events = [
            {
                "id": "evt-skill",
                "source_log_id": "log-10",
                "linked_session_id": "",
                "agent_name": "",
                "metadata_json": {},
            },
            {
                "id": "evt-subthread",
                "source_log_id": "log-11",
                "linked_session_id": "agent-sub-1",
                "agent_name": "executor",
                "metadata_json": {},
            },
        ]

        attributions = build_session_usage_attributions(session_payload, logs, artifacts, usage_events)

        primary_rows = {
            row["event_id"]: row
            for row in attributions
            if row["attribution_role"] == "primary"
        }
        self.assertEqual(primary_rows["evt-skill"]["entity_type"], "skill")
        self.assertEqual(primary_rows["evt-skill"]["method"], "explicit_skill_invocation")
        self.assertEqual(primary_rows["evt-subthread"]["entity_type"], "subthread")
        self.assertEqual(primary_rows["evt-subthread"]["entity_id"], "agent-sub-1")

        supporting_pairs = {
            (row["event_id"], row["entity_type"], row["method"])
            for row in attributions
            if row["attribution_role"] == "supporting"
        }
        self.assertIn(("evt-skill", "workflow", "workflow_membership"), supporting_pairs)
        self.assertIn(("evt-skill", "feature", "feature_inheritance"), supporting_pairs)
        self.assertIn(("evt-subthread", "agent", "explicit_agent_ownership"), supporting_pairs)
        self.assertIn(("evt-subthread", "command", "explicit_command_context"), supporting_pairs)
        self.assertIn(("evt-subthread", "artifact", "explicit_artifact_link"), supporting_pairs)
        self.assertIn(("evt-subthread", "skill", "skill_window"), supporting_pairs)


class SessionUsageRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.session_repo = SqliteSessionRepository(self.db)
        self.usage_repo = SqliteSessionUsageRepository(self.db)
        await self.session_repo.upsert(
            {
                "id": "S-300",
                "taskId": "",
                "status": "completed",
                "model": "claude-sonnet",
                "platformType": "Claude Code",
                "durationSeconds": 1,
                "tokensIn": 1,
                "tokensOut": 1,
                "totalCost": 0.0,
                "startedAt": "2026-03-10T10:00:00Z",
                "endedAt": "2026-03-10T10:00:01Z",
                "createdAt": "2026-03-10T10:00:00Z",
                "updatedAt": "2026-03-10T10:00:01Z",
                "sourceFile": "sessions/test.jsonl",
                "rootSessionId": "S-300",
                "threadKind": "root",
                "conversationFamilyId": "S-300",
            },
            "project-1",
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_replace_session_usage_round_trips_events_and_attributions(self) -> None:
        await self.usage_repo.replace_session_usage(
            "project-1",
            "S-300",
            [
                {
                    "id": "evt-1",
                    "root_session_id": "S-300",
                    "linked_session_id": "",
                    "source_log_id": "log-1",
                    "captured_at": "2026-03-10T10:00:00Z",
                    "event_kind": "message",
                    "model": "claude-sonnet",
                    "tool_name": "",
                    "agent_name": "planner",
                    "token_family": "model_input",
                    "delta_tokens": 12,
                    "cost_usd_model_io": 0.12,
                    "metadata_json": {"logIndex": 1},
                }
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
                }
            ],
        )

        events = await self.usage_repo.get_session_usage_events("S-300")
        attributions = await self.usage_repo.get_session_usage_attributions("S-300")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source_log_id"], "log-1")
        self.assertEqual(events[0]["token_family"], "model_input")
        self.assertEqual(len(attributions), 1)
        self.assertEqual(attributions[0]["entity_type"], "skill")
        self.assertEqual(await self.usage_repo.count_usage_events("project-1"), 1)
