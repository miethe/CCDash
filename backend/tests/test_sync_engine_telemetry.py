import json
import unittest

from backend.db.sync_engine import _build_session_telemetry_events
from backend.db.sync_engine import _build_session_commit_correlations
from backend.db.sync_engine import _derive_claude_usage_fields


class SyncEngineTelemetryTests(unittest.TestCase):
    def test_derive_claude_usage_fields_maps_usage_summary(self) -> None:
        session_payload = {
            "platformType": "Claude Code",
            "tokensIn": 120,
            "tokensOut": 80,
            "sessionForensics": {
                "platform": "claude_code",
                "usageSummary": {
                    "messageTotals": {
                        "inputTokens": 120,
                        "outputTokens": 80,
                        "cacheCreationInputTokens": 25,
                        "cacheReadInputTokens": 75,
                        "allInputTokens": 220,
                        "allTokens": 300,
                    },
                    "toolResultReportedTotals": {"totalTokens": 610},
                    "toolResultUsageTotals": {
                        "inputTokens": 7,
                        "outputTokens": 11,
                        "cacheCreationInputTokens": 13,
                        "cacheReadInputTokens": 17,
                    },
                },
            },
        }

        usage_fields = _derive_claude_usage_fields(session_payload)

        self.assertEqual(usage_fields["model_io_tokens"], 200)
        self.assertEqual(usage_fields["cache_creation_input_tokens"], 25)
        self.assertEqual(usage_fields["cache_read_input_tokens"], 75)
        self.assertEqual(usage_fields["cache_input_tokens"], 220)
        self.assertEqual(usage_fields["observed_tokens"], 300)
        self.assertEqual(usage_fields["tool_reported_tokens"], 610)
        self.assertEqual(usage_fields["tool_result_input_tokens"], 7)
        self.assertEqual(usage_fields["tool_result_output_tokens"], 11)
        self.assertEqual(usage_fields["tool_result_cache_creation_input_tokens"], 13)
        self.assertEqual(usage_fields["tool_result_cache_read_input_tokens"], 17)

    def test_derive_claude_usage_fields_preserves_existing_non_claude_values(self) -> None:
        session_payload = {
            "platformType": "Codex CLI",
            "modelIOTokens": 9,
            "cacheCreationInputTokens": 4,
            "cacheReadInputTokens": 5,
            "cacheInputTokens": 9,
            "observedTokens": 18,
            "toolReportedTokens": 27,
            "toolResultInputTokens": 3,
            "toolResultOutputTokens": 6,
            "toolResultCacheCreationInputTokens": 1,
            "toolResultCacheReadInputTokens": 2,
        }

        usage_fields = _derive_claude_usage_fields(session_payload)

        self.assertEqual(usage_fields["model_io_tokens"], 9)
        self.assertEqual(usage_fields["cache_creation_input_tokens"], 4)
        self.assertEqual(usage_fields["cache_read_input_tokens"], 5)
        self.assertEqual(usage_fields["cache_input_tokens"], 9)
        self.assertEqual(usage_fields["observed_tokens"], 18)
        self.assertEqual(usage_fields["tool_reported_tokens"], 27)

    def test_build_session_telemetry_events_captures_dimensions(self) -> None:
        session_payload = {
            "id": "S-123",
            "rootSessionId": "S-123",
            "taskId": "TASK-9.1",
            "gitCommitHash": "abc123",
            "model": "gpt-5",
            "status": "completed",
            "tokensIn": 120,
            "tokensOut": 80,
            "totalCost": 1.25,
            "durationSeconds": 30,
            "sessionMetadata": {"relatedPhases": ["phase-2"]},
            "startedAt": "2026-02-22T10:00:00Z",
        }
        logs = [
            {
                "type": "tool",
                "timestamp": "2026-02-22T10:00:01Z",
                "agentName": "planner",
                "toolCall": {"name": "Skill", "status": "success"},
                "metadata": {"toolLabel": "symbols", "inputTokens": 10, "outputTokens": 5},
            }
        ]
        tools = [{"name": "Read", "count": 2, "successRate": 1.0, "totalMs": 450}]
        files = [{"filePath": "docs/plan.md", "additions": 5, "deletions": 1, "action": "update"}]
        artifacts = [{"id": "ART-1", "title": "PR", "url": "https://github.com/org/repo/pull/321"}]

        events = _build_session_telemetry_events(
            "project-1",
            session_payload,
            logs,
            tools,
            files,
            artifacts,
            source="sync",
        )

        event_types = {event["event_type"] for event in events}
        self.assertIn("session.lifecycle", event_types)
        self.assertIn("log.tool", event_types)
        self.assertIn("tool.aggregate", event_types)
        self.assertIn("file.update", event_types)
        self.assertIn("artifact.linked", event_types)

        lifecycle = next(event for event in events if event["event_type"] == "session.lifecycle")
        self.assertEqual(lifecycle["pr_number"], "321")
        self.assertEqual(lifecycle["phase"], "phase-2")
        self.assertEqual(lifecycle["token_input"], 120)
        self.assertEqual(lifecycle["token_output"], 80)
        self.assertAlmostEqual(lifecycle["cost_usd"], 1.25)

        log_event = next(event for event in events if event["event_type"] == "log.tool")
        self.assertEqual(log_event["skill"], "symbols")
        self.assertEqual(log_event["agent"], "planner")
        self.assertEqual(log_event["token_input"], 10)
        self.assertEqual(log_event["token_output"], 5)

    def test_build_session_telemetry_events_supports_db_row_shapes(self) -> None:
        session_payload = {
            "id": "S-200",
            "root_session_id": "S-100",
            "task_id": "TASK-2",
            "git_commit_hash": "def456",
            "model": "claude-sonnet",
            "started_at": "2026-02-22T11:00:00Z",
        }
        logs = [
            {
                "log_index": 3,
                "type": "message",
                "timestamp": "2026-02-22T11:00:01Z",
                "metadata_json": json.dumps({"inputTokens": 2, "outputTokens": 3}),
            }
        ]

        events = _build_session_telemetry_events(
            "project-2",
            session_payload,
            logs,
            tools=[],
            files=[],
            artifacts=[],
            source="backfill",
        )

        lifecycle = next(event for event in events if event["event_type"] == "session.lifecycle")
        self.assertEqual(lifecycle["root_session_id"], "S-100")
        self.assertEqual(lifecycle["task_id"], "TASK-2")
        self.assertEqual(lifecycle["commit_hash"], "def456")

        message = next(event for event in events if event["event_type"] == "log.message")
        self.assertEqual(message["source_key"], "log:S-200:3")
        self.assertEqual(message["token_input"], 2)
        self.assertEqual(message["token_output"], 3)

    def test_build_session_commit_correlations_assigns_windows_to_commits(self) -> None:
        session_payload = {
            "id": "S-500",
            "rootSessionId": "S-500",
            "featureId": "feature-one-v1",
            "taskId": "TASK-2.1",
            "startedAt": "2026-02-26T09:00:00Z",
            "totalCost": 3.0,
        }
        logs = [
            {
                "id": "log-1",
                "type": "tool",
                "timestamp": "2026-02-26T09:00:01Z",
                "metadata": {
                    "inputTokens": 10,
                    "outputTokens": 6,
                    "taskDescription": "Implement TASK-2.1 in phase 2",
                },
            },
            {
                "id": "log-2",
                "type": "command",
                "timestamp": "2026-02-26T09:00:02Z",
                "content": "/dev:execute-phase",
                "metadata": {
                    "parsedCommand": {
                        "phaseToken": "2",
                        "phases": ["2"],
                        "featureSlugCanonical": "feature-one",
                    }
                },
            },
            {
                "id": "log-3",
                "type": "tool",
                "timestamp": "2026-02-26T09:00:03Z",
                "metadata": {"commitHashes": ["abc1234"]},
            },
            {
                "id": "log-4",
                "type": "tool",
                "timestamp": "2026-02-26T09:00:04Z",
                "metadata": {
                    "inputTokens": 4,
                    "outputTokens": 3,
                    "taskDescription": "Finalize TASK-2.2 updates",
                },
            },
            {
                "id": "log-5",
                "type": "tool",
                "timestamp": "2026-02-26T09:00:05Z",
                "metadata": {"commitHashes": ["def5678"]},
            },
        ]
        files = [
            {"sourceLogId": "log-1", "filePath": "backend/main.py", "additions": 5, "deletions": 1},
            {"sourceLogId": "log-4", "filePath": "backend/api.py", "additions": 2, "deletions": 0},
        ]

        rows, latest = _build_session_commit_correlations(
            "project-1",
            session_payload,
            logs,
            files,
            source="sync",
            baseline_commit_hash="",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["commit_hash"], "abc1234")
        self.assertEqual(rows[1]["commit_hash"], "def5678")
        self.assertEqual(rows[0]["file_count"], 1)
        self.assertEqual(rows[1]["file_count"], 1)
        self.assertGreater(rows[0]["token_input"], 0)
        self.assertGreater(rows[1]["token_input"], 0)
        self.assertEqual(latest, "def5678")

    def test_build_session_commit_correlations_uses_baseline_when_no_new_commit(self) -> None:
        session_payload = {
            "id": "S-501",
            "startedAt": "2026-02-26T10:00:00Z",
        }
        logs = [
            {
                "id": "log-1",
                "type": "command",
                "timestamp": "2026-02-26T10:00:01Z",
                "content": "/dev:execute-phase 3",
                "metadata": {"inputTokens": 2, "outputTokens": 1},
            }
        ]

        rows, latest = _build_session_commit_correlations(
            "project-1",
            session_payload,
            logs,
            files=[],
            source="sync",
            baseline_commit_hash="c0ffee1",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["commit_hash"], "c0ffee1")
        self.assertEqual(latest, "c0ffee1")


if __name__ == "__main__":
    unittest.main()
