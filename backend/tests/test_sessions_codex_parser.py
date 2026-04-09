import json
import tempfile
import unittest
from pathlib import Path

from backend.parsers.sessions import parse_session_file, scan_sessions


class CodexSessionParserTests(unittest.TestCase):
    def _write_jsonl(self, lines: list[dict], relative_path: str) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
        return path

    def test_codex_session_parses_payload_signals_and_resources(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "turn_context",
                    "timestamp": "2026-02-17T10:00:00Z",
                    "payload": {
                        "type": "turn_context",
                        "cwd": "/tmp/ccdash/workspace",
                        "model": "gpt-5-codex",
                        "cli_version": "0.9.1",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-02-17T10:00:01Z",
                    "payload": {
                        "type": "user_message",
                        "role": "user",
                        "content": "/dev:implement-story docs/project_plans/implementation_plans/features/sample-feature-v1.md",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-02-17T10:00:01Z",
                    "payload": {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "call-1",
                        "arguments": {
                            "command": (
                                "curl https://api.example.com/v1/status && "
                                "psql -h db.example.com -U app appdb && "
                                "docker compose ps && "
                                "rm src/old.ts"
                            )
                        },
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-02-17T10:00:02Z",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "status": "success",
                        "output": "command complete",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-02-17T10:00:03Z",
                    "payload": {
                        "type": "agent_reasoning",
                        "text": "Inspecting command output and next actions",
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-02-17T10:00:04Z",
                    "payload": {
                        "type": "task_complete",
                        "summary": "Task complete",
                    },
                },
            ],
            relative_path=".codex/sessions/2026/02/17/session-abc.jsonl",
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        self.assertEqual(session.platformType, "Codex")
        self.assertEqual(session.platformVersion, "0.9.1")
        self.assertEqual(session.status, "completed")
        self.assertEqual(session.model, "gpt-5-codex")

        tool_logs = [log for log in session.logs if log.type == "tool" and log.toolCall]
        self.assertEqual(len(tool_logs), 1)
        self.assertEqual(tool_logs[0].toolCall.name, "exec_command")
        self.assertEqual(tool_logs[0].toolCall.id, "call-1")
        self.assertEqual(tool_logs[0].toolCall.output, "command complete")
        self.assertEqual(tool_logs[0].toolCall.status, "success")
        command_logs = [log for log in session.logs if log.type == "command"]
        self.assertEqual(len(command_logs), 1)
        self.assertEqual(command_logs[0].content, "/dev:implement-story")
        self.assertEqual(command_logs[0].metadata.get("args"), "docs/project_plans/implementation_plans/features/sample-feature-v1.md")

        file_changes = {item.filePath: item.action for item in session.updatedFiles}
        self.assertEqual(file_changes.get("src/old.ts"), "delete")

        forensics = session.sessionForensics
        entry_context = forensics.get("entryContext", {})
        self.assertIn("call-1", entry_context.get("callIds", []))
        self.assertIn("gpt-5-codex", entry_context.get("models", []))
        self.assertEqual(entry_context.get("payloadTypeCounts", {}).get("function_call"), 1)

        resource_footprint = forensics.get("resourceFootprint", {})
        self.assertGreaterEqual(resource_footprint.get("totalObservations", 0), 3)
        self.assertEqual(resource_footprint.get("categories", {}).get("api"), 1)
        self.assertEqual(resource_footprint.get("categories", {}).get("database"), 1)
        self.assertEqual(resource_footprint.get("categories", {}).get("docker"), 1)

        payload_signals = forensics.get("codexPayloadSignals", {})
        self.assertEqual(payload_signals.get("payloadTypeCounts", {}).get("function_call_output"), 1)
        self.assertEqual(payload_signals.get("toolNameCounts", {}).get("exec_command"), 1)

        message_logs = [log for log in session.logs if log.type == "message"]
        self.assertEqual(len(message_logs), 1)
        self.assertEqual(message_logs[0].metadata.get("sourceProvenance"), "codex.user_message")
        self.assertEqual(message_logs[0].metadata.get("messageRole"), "user")
        self.assertTrue(str(message_logs[0].metadata.get("messageId") or "").startswith("codex-"))

        self.assertEqual(tool_logs[0].metadata.get("sourceProvenance"), "codex.function_call")
        self.assertEqual(tool_logs[0].metadata.get("messageRole"), "assistant")
        self.assertEqual(tool_logs[0].metadata.get("messageId"), "call-1")
        self.assertIn("rm src/old.ts", str(tool_logs[0].metadata.get("toolArgs") or ""))
        self.assertEqual(tool_logs[0].metadata.get("toolOutput"), "command complete")
        self.assertEqual(tool_logs[0].metadata.get("toolStatus"), "success")

        thought_logs = [log for log in session.logs if log.type == "thought"]
        self.assertEqual(len(thought_logs), 1)
        self.assertEqual(thought_logs[0].metadata.get("sourceProvenance"), "codex.agent_reasoning")
        self.assertEqual(thought_logs[0].metadata.get("messageRole"), "assistant")

    def test_codex_pytest_tool_call_captures_test_run_metadata_and_results(self) -> None:
        output_text = (
            "============================= test session starts ==============================\n"
            "platform darwin -- Python 3.12.0, pytest-8.4.2, pluggy-1.6.0\n"
            "rootdir: /Users/miethe/dev/homelab/development/skillmeat\n"
            "configfile: pytest.ini\n"
            "plugins: benchmark-5.2.3, asyncio-1.2.0, anyio-4.11.0, xdist-3.8.0, timeout-2.4.0, cov-7.0.0\n"
            "created: 12/12 workers\n"
            "12 workers [132 items]\n"
            "======================= 130 passed, 2 xfailed in 15.01s ========================\n"
        )
        path = self._write_jsonl(
            [
                {
                    "type": "turn_context",
                    "timestamp": "2026-03-05T11:00:00Z",
                    "payload": {
                        "type": "turn_context",
                        "model": "gpt-5-codex",
                        "cli_version": "0.9.4",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-03-05T11:00:01Z",
                    "payload": {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "call-test-1",
                        "arguments": {
                            "command": "python -m pytest tests/api/test_marketplace_router.py tests/api/test_marketplace_source_security.py -x -q --tb=short 2>&1 | tail -20",
                            "description": "Run marketplace tests to verify agent fixes",
                            "timeout": 120000,
                        },
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-03-05T11:00:04Z",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-test-1",
                        "status": "success",
                        "output": output_text,
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-03-05T11:00:05Z",
                    "payload": {"type": "task_complete"},
                },
            ],
            relative_path=".codex/sessions/2026/03/05/session-test-run.jsonl",
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        tool_logs = [log for log in session.logs if log.type == "tool" and log.toolCall and log.toolCall.id == "call-test-1"]
        self.assertEqual(len(tool_logs), 1)
        metadata = tool_logs[0].metadata
        self.assertEqual(metadata.get("toolCategory"), "test")
        self.assertEqual(metadata.get("testFramework"), "pytest")
        self.assertEqual(metadata.get("testDomain"), "api")
        self.assertEqual(metadata.get("testDescription"), "Run marketplace tests to verify agent fixes")
        self.assertEqual(metadata.get("testTimeoutMs"), 120000)
        self.assertEqual(metadata.get("testStatus"), "passed")
        self.assertEqual(metadata.get("testTotal"), 132)
        self.assertEqual(metadata.get("testWorkers"), 12)
        self.assertEqual(metadata.get("testCollected"), 132)
        self.assertEqual(metadata.get("testPytestVersion"), "8.4.2")
        self.assertEqual(metadata.get("testPythonVersion"), "3.12.0")
        self.assertIn("tests/api/test_marketplace_router.py", metadata.get("testTargets", []))
        self.assertIn("tests/api/test_marketplace_source_security.py", metadata.get("testTargets", []))
        self.assertIn("-x", metadata.get("testFlags", []))
        self.assertIn("-q", metadata.get("testFlags", []))
        self.assertIn("--tb=short", metadata.get("testFlags", []))
        counts = metadata.get("testCounts", {})
        self.assertEqual(counts.get("passed"), 130)
        self.assertEqual(counts.get("xfailed"), 2)

        artifact_types = {artifact.type for artifact in session.linkedArtifacts}
        self.assertIn("test_run", artifact_types)
        self.assertIn("test_domain", artifact_types)
        self.assertIn("test_target", artifact_types)

        test_execution = session.sessionForensics.get("testExecution", {})
        self.assertEqual(test_execution.get("runCount"), 1)
        self.assertEqual(test_execution.get("domainCounts", {}).get("api"), 1)
        self.assertEqual(test_execution.get("statusCounts", {}).get("passed"), 1)
        self.assertEqual(test_execution.get("resultCounts", {}).get("passed"), 130)

    def test_codex_pytest_truncated_output_without_header_still_parses_results(self) -> None:
        output_text = (
            "FAILED tests/api/test_marketplace_router.py::test_requires_auth - assert 401 == 200\n"
            "=========================== short test summary info ============================\n"
            "FAILED tests/api/test_marketplace_router.py::test_requires_auth - assert 401 == 200\n"
            "======================== 1 failed, 21 passed in 13.35s ========================\n"
        )
        path = self._write_jsonl(
            [
                {
                    "type": "turn_context",
                    "timestamp": "2026-03-05T11:10:00Z",
                    "payload": {
                        "type": "turn_context",
                        "model": "gpt-5-codex",
                        "cli_version": "0.9.4",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-03-05T11:10:01Z",
                    "payload": {
                        "type": "function_call",
                        "name": "exec_command",
                        "call_id": "call-test-truncated-1",
                        "arguments": {
                            "command": "python -m pytest tests/api/test_marketplace_router.py -x -q --tb=short 2>&1 | tail -20",
                            "description": "Run API tests after agent changes",
                            "timeout": 120000,
                        },
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-03-05T11:10:04Z",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-test-truncated-1",
                        "status": "success",
                        "output": output_text,
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-03-05T11:10:05Z",
                    "payload": {"type": "task_complete"},
                },
            ],
            relative_path=".codex/sessions/2026/03/05/session-test-truncated-run.jsonl",
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        tool_logs = [log for log in session.logs if log.type == "tool" and log.toolCall and log.toolCall.id == "call-test-truncated-1"]
        self.assertEqual(len(tool_logs), 1)
        metadata = tool_logs[0].metadata
        self.assertEqual(metadata.get("toolCategory"), "test")
        self.assertEqual(metadata.get("testFramework"), "pytest")
        self.assertEqual(metadata.get("testStatus"), "failed")
        self.assertEqual(metadata.get("testTotal"), 22)
        counts = metadata.get("testCounts", {})
        self.assertEqual(counts.get("passed"), 21)
        self.assertEqual(counts.get("failed"), 1)

        test_execution = session.sessionForensics.get("testExecution", {})
        self.assertEqual(test_execution.get("runCount"), 1)
        self.assertEqual(test_execution.get("statusCounts", {}).get("failed"), 1)
        self.assertEqual(test_execution.get("resultCounts", {}).get("passed"), 21)
        self.assertEqual(test_execution.get("resultCounts", {}).get("failed"), 1)

    def test_codex_agent_tool_creates_agent_artifact_and_links_subthread(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "turn_context",
                    "timestamp": "2026-03-05T09:00:00Z",
                    "payload": {
                        "type": "turn_context",
                        "model": "gpt-5-codex",
                        "cli_version": "0.9.3",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-03-05T09:00:01Z",
                    "payload": {
                        "type": "function_call",
                        "name": "Agent",
                        "call_id": "call-agent-1",
                        "arguments": {
                            "description": "TASK-5.1: Replace direct session usage",
                            "prompt": "Migrate router to repository DI.",
                            "subagent_type": "python-backend-engineer",
                            "mode": "bypassPermissions",
                            "run_in_background": True,
                        },
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-03-05T09:00:02Z",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-agent-1",
                        "status": "success",
                        "isAsync": True,
                        "output": {
                            "status": "async_launched",
                            "agentId": "agent-xyz987",
                        },
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-03-05T09:00:03Z",
                    "payload": {
                        "type": "task_complete",
                        "summary": "Task complete",
                    },
                },
            ],
            relative_path=".codex/sessions/2026/03/05/session-agent.jsonl",
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        tool_logs = [log for log in session.logs if log.type == "tool" and log.toolCall and log.toolCall.name == "Agent"]
        self.assertEqual(len(tool_logs), 1)
        metadata = tool_logs[0].metadata
        self.assertEqual(metadata.get("taskId"), "TASK-5.1")
        self.assertEqual(metadata.get("taskSubagentType"), "python-backend-engineer")
        self.assertEqual(metadata.get("taskMode"), "bypassPermissions")
        self.assertEqual(metadata.get("taskRunInBackground"), True)
        self.assertEqual(tool_logs[0].linkedSessionId, "S-agent-xyz987")

        start_logs = [log for log in session.logs if log.type == "subagent_start"]
        self.assertEqual(len(start_logs), 1)
        self.assertEqual(start_logs[0].linkedSessionId, "S-agent-xyz987")
        self.assertEqual(start_logs[0].metadata.get("subagentType"), "python-backend-engineer")

        agent_artifacts = [artifact for artifact in session.linkedArtifacts if artifact.type == "agent"]
        self.assertTrue(any(artifact.title == "python-backend-engineer" for artifact in agent_artifacts))

    def test_scan_sessions_supports_nested_codex_paths(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "turn_context",
                    "timestamp": "2026-02-17T11:00:00Z",
                    "payload": {
                        "type": "turn_context",
                        "model": "gpt-5-codex",
                        "cli_version": "0.9.2",
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-02-17T11:00:01Z",
                    "payload": {
                        "type": "task_complete",
                    },
                },
            ],
            relative_path=".codex/sessions/2026/02/17/session-nested.jsonl",
        )

        sessions_root = path.parents[3]
        sessions = scan_sessions(sessions_root, max_files=20)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].platformType, "Codex")
        self.assertEqual(sessions[0].platformVersion, "0.9.2")


if __name__ == "__main__":
    unittest.main()
