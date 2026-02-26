import json
import unittest

from backend.db.sync_engine import _build_session_telemetry_events


class SyncEngineTelemetryTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
