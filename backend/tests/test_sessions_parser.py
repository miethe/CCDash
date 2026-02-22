import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from backend.parsers.sessions import parse_session_file


class SessionParserTests(unittest.TestCase):
    def _write_jsonl(self, lines: list[dict], relative_path: str = "session.jsonl") -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
        return path

    def test_tool_use_and_result_are_merged(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T10:00:00Z",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet",
                        "usage": {"input_tokens": 10, "output_tokens": 20},
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_1",
                                "name": "Read",
                                "input": {"file_path": "/tmp/project/README.md"},
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-02-16T10:00:01Z",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_1",
                                "is_error": False,
                                "content": "Read output",
                            }
                        ],
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        tools = [l for l in session.logs if l.type == "tool"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].toolCall.id, "toolu_1")
        self.assertEqual(tools[0].toolCall.output, "Read output")
        self.assertEqual(tools[0].toolCall.status, "success")
        self.assertGreaterEqual(session.toolsUsed[0].totalMs, 1000)

    def test_agent_message_usage_is_persisted_on_message_log_metadata(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T10:00:00Z",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet",
                        "usage": {"input_tokens": 12, "output_tokens": 34},
                        "content": [
                            {"type": "text", "text": "Working on it."},
                        ],
                    },
                }
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        message_logs = [log for log in session.logs if log.type == "message"]
        self.assertEqual(len(message_logs), 1)
        self.assertEqual(message_logs[0].metadata.get("inputTokens"), 12)
        self.assertEqual(message_logs[0].metadata.get("outputTokens"), 34)
        self.assertEqual(message_logs[0].metadata.get("totalTokens"), 46)

    def test_unmatched_tool_result_becomes_system_log(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "user",
                    "timestamp": "2026-02-16T10:00:00Z",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "missing",
                                "is_error": True,
                                "content": "error output",
                            }
                        ],
                    },
                }
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        system_logs = [l for l in session.logs if l.type == "system"]
        self.assertGreaterEqual(len(system_logs), 1)
        self.assertEqual(system_logs[0].relatedToolCallId, "missing")

    def test_agent_progress_creates_subagent_start_link(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T10:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_task_1",
                                "name": "Task",
                                "input": {"subagent_type": "Explore"},
                            }
                        ],
                    },
                },
                {
                    "type": "progress",
                    "timestamp": "2026-02-16T10:00:01Z",
                    "parentToolUseID": "toolu_task_1",
                    "data": {
                        "type": "agent_progress",
                        "agentId": "a123",
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        starts = [l for l in session.logs if l.type == "subagent_start"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0].linkedSessionId, "S-agent-a123")

        task_tools = [l for l in session.logs if l.type == "tool" and l.toolCall and l.toolCall.name == "Task"]
        self.assertEqual(task_tools[0].linkedSessionId, "S-agent-a123")

    def test_async_task_tool_result_creates_subagent_start_link(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T10:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_task_2",
                                "name": "Task",
                                "input": {"subagent_type": "Explore"},
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-02-16T10:00:01Z",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_task_2",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Async agent launched successfully.\nagentId: a456\n",
                                    }
                                ],
                                "is_error": False,
                            }
                        ],
                    },
                    "toolUseResult": {
                        "isAsync": True,
                        "status": "async_launched",
                        "agentId": "a456",
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        starts = [l for l in session.logs if l.type == "subagent_start"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0].linkedSessionId, "S-agent-a456")

        task_tools = [l for l in session.logs if l.type == "tool" and l.toolCall and l.toolCall.name == "Task"]
        self.assertEqual(task_tools[0].linkedSessionId, "S-agent-a456")

    def test_thinking_becomes_thought_log_and_extracts_artifacts_and_files(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "user",
                    "timestamp": "2026-02-16T10:00:00Z",
                    "message": {
                        "role": "user",
                        "content": "<command-name>/dev:quick-feature</command-name>",
                    },
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T10:00:01Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "thinking", "thinking": "internal thought"},
                            {
                                "type": "tool_use",
                                "id": "toolu_skill_1",
                                "name": "Skill",
                                "input": {"skill": "symbols"},
                            },
                            {
                                "type": "tool_use",
                                "id": "toolu_write_1",
                                "name": "Write",
                                "input": {"file_path": "/Users/me/project/AGENTS.md"},
                            },
                        ],
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        thought_logs = [l for l in session.logs if l.type == "thought"]
        self.assertEqual(len(thought_logs), 1)

        self.assertTrue(any(f.filePath.endswith("AGENTS.md") for f in session.updatedFiles))

        artifact_types = {a.type for a in session.linkedArtifacts}
        self.assertIn("command", artifact_types)
        self.assertIn("skill", artifact_types)
        self.assertIn("manifest", artifact_types)

    def test_command_args_paths_are_not_tracked_as_file_actions(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "user",
                    "timestamp": "2026-02-16T10:00:00Z",
                    "message": {
                        "role": "user",
                        "content": (
                            "<command-name>/dev:execute-phase</command-name>\n"
                            "<command-args>1 docs/project_plans/implementation_plans/features/example-v1.md</command-args>"
                        ),
                    },
                }
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        file_paths = [f.filePath for f in session.updatedFiles]
        self.assertEqual(file_paths, [])

    def test_file_actions_include_read_update_and_delete_with_metadata(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T10:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_read_1",
                                "name": "Read",
                                "input": {"file_path": "docs/project_plans/README.md"},
                            },
                            {
                                "type": "tool_use",
                                "id": "toolu_edit_1",
                                "name": "Edit",
                                "input": {"file_path": "backend/main.py", "old_string": "a", "new_string": "b"},
                            },
                            {
                                "type": "tool_use",
                                "id": "toolu_delete_1",
                                "name": "DeleteFile",
                                "input": {"path": "components/obsolete.tsx"},
                            },
                        ],
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        by_path = {f.filePath: f for f in session.updatedFiles}
        self.assertEqual(by_path["docs/project_plans/README.md"].action, "read")
        self.assertEqual(by_path["docs/project_plans/README.md"].fileType, "Plan")
        self.assertEqual(by_path["backend/main.py"].action, "update")
        self.assertEqual(by_path["backend/main.py"].fileType, "Backend code")
        self.assertEqual(by_path["components/obsolete.tsx"].action, "delete")
        self.assertEqual(by_path["components/obsolete.tsx"].fileType, "Frontend code")
        self.assertEqual(by_path["backend/main.py"].timestamp, "2026-02-16T10:00:00Z")

    def test_bash_git_output_extracts_commit_hashes(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T10:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_git_1",
                                "name": "Bash",
                                "input": {"command": "git commit -m \"feat: add tests\""},
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-02-16T10:00:01Z",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_git_1",
                                "is_error": False,
                                "content": "[feat/example a1b2c3d4] feat: add tests\\n 1 file changed",
                            }
                        ],
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        self.assertIn("a1b2c3d4", session.gitCommitHashes)
        self.assertEqual(session.gitCommitHash, "a1b2c3d4")

        tool_logs = [l for l in session.logs if l.type == "tool" and l.toolCall and l.toolCall.name == "Bash"]
        self.assertEqual(len(tool_logs), 1)
        self.assertEqual(tool_logs[0].metadata.get("toolCategory"), "git")

    def test_execute_phase_range_command_metadata_is_parsed(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "user",
                    "timestamp": "2026-02-16T11:00:00Z",
                    "message": {
                        "role": "user",
                        "content": (
                            "<command-name>/dev:execute-phase</command-name>\n"
                            "<command-args>1 & 2 docs/project_plans/implementation_plans/features/example-v1.md</command-args>"
                        ),
                    },
                }
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        command_logs = [l for l in session.logs if l.type == "command"]
        self.assertEqual(len(command_logs), 1)
        parsed = command_logs[0].metadata.get("parsedCommand", {})
        self.assertEqual(parsed.get("phaseToken"), "1 & 2")
        self.assertEqual(parsed.get("phases"), ["1", "2"])
        self.assertEqual(parsed.get("featureSlug"), "example-v1")
        self.assertEqual(parsed.get("featureSlugCanonical"), "example")

    def test_summary_pr_link_custom_title_and_queue_operation_ingested(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "custom-title",
                    "timestamp": "2026-02-16T12:00:00Z",
                    "title": "Implement cache fixes",
                },
                {
                    "type": "summary",
                    "timestamp": "2026-02-16T12:00:01Z",
                    "summary": "Implemented command parser updates",
                },
                {
                    "type": "pr-link",
                    "timestamp": "2026-02-16T12:00:02Z",
                    "prNumber": 42,
                    "prUrl": "https://github.com/acme/repo/pull/42",
                    "prRepository": "acme/repo",
                },
                {
                    "type": "queue-operation",
                    "timestamp": "2026-02-16T12:00:03Z",
                    "content": "<task-id>TASK-1.2</task-id><status>done</status><summary>Phase complete</summary>",
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        artifact_types = {a.type for a in session.linkedArtifacts}
        self.assertIn("custom_title", artifact_types)
        self.assertIn("summary", artifact_types)
        self.assertIn("pr_link", artifact_types)
        self.assertIn("task_notification", artifact_types)

        system_event_types = {
            str(log.metadata.get("eventType"))
            for log in session.logs
            if log.type == "system" and isinstance(log.metadata, dict)
        }
        self.assertIn("custom-title", system_event_types)
        self.assertIn("summary", system_event_types)
        self.assertIn("pr-link", system_event_types)
        self.assertIn("queue-operation", system_event_types)

    def test_bash_progress_is_linked_to_bash_tool_call(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T13:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_bash_progress",
                                "name": "Bash",
                                "input": {"command": "git commit -m \"feat: parser\""},
                            }
                        ],
                    },
                },
                {
                    "type": "progress",
                    "timestamp": "2026-02-16T13:00:01Z",
                    "parentToolUseID": "toolu_bash_progress",
                    "data": {
                        "type": "bash_progress",
                        "command": "git commit -m \"feat: parser\"",
                        "output": "[feature/main abc1234] feat: parser\n1 file changed",
                        "elapsedTimeSeconds": 1.2,
                        "totalLines": 2,
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        self.assertIn("abc1234", session.gitCommitHashes)
        tool_logs = [l for l in session.logs if l.type == "tool" and l.toolCall and l.toolCall.name == "Bash"]
        self.assertEqual(len(tool_logs), 1)
        self.assertTrue(tool_logs[0].metadata.get("bashProgressLinked"))
        self.assertEqual(tool_logs[0].metadata.get("bashElapsedSeconds"), 1.2)
        self.assertEqual(tool_logs[0].metadata.get("bashTotalLines"), 2)

    def test_recent_session_without_terminal_marker_is_active(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "user",
                    "timestamp": "2026-02-16T14:00:00Z",
                    "message": {"role": "user", "content": "working"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T14:00:01Z",
                    "message": {"role": "assistant", "content": [{"type": "text", "text": "in progress"}]},
                },
            ]
        )
        now = time.time()
        os.utime(path, (now, now))

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.status, "active")

    def test_stale_session_without_terminal_marker_is_completed(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "user",
                    "timestamp": "2026-02-16T14:05:00Z",
                    "message": {"role": "user", "content": "old session"},
                },
            ]
        )
        old = time.time() - (3 * 3600)
        os.utime(path, (old, old))

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.status, "completed")

    def test_terminal_system_entry_marks_session_completed(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T14:10:00Z",
                    "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
                },
                {
                    "type": "system",
                    "timestamp": "2026-02-16T14:10:02Z",
                    "subtype": "turn_duration",
                    "durationMs": 1200,
                    "isMeta": True,
                },
            ]
        )
        now = time.time()
        os.utime(path, (now, now))

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.status, "completed")


if __name__ == "__main__":
    unittest.main()
