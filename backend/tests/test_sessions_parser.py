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

    def test_platform_version_is_captured_and_transition_is_logged(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "user",
                    "timestamp": "2026-02-16T10:00:00Z",
                    "version": "2.1.51",
                    "message": {"role": "user", "content": "Start"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T10:00:01Z",
                    "version": "2.1.51",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet",
                        "content": [{"type": "text", "text": "Working"}],
                    },
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T10:00:02Z",
                    "version": "2.1.52",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet",
                        "content": [{"type": "text", "text": "Upgraded"}],
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        self.assertEqual(session.platformType, "Claude Code")
        self.assertEqual(session.platformVersion, "2.1.52")
        self.assertEqual(session.platformVersions, ["2.1.51", "2.1.52"])
        self.assertEqual(len(session.platformVersionTransitions), 1)
        self.assertEqual(session.platformVersionTransitions[0].fromVersion, "2.1.51")
        self.assertEqual(session.platformVersionTransitions[0].toVersion, "2.1.52")
        self.assertTrue(session.platformVersionTransitions[0].sourceLogId)

        transition_logs = [
            log for log in session.logs
            if log.type == "system" and log.metadata.get("eventType") == "platform-version-change"
        ]
        self.assertEqual(len(transition_logs), 1)

    def test_platform_defaults_to_claude_code_when_unavailable(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T10:00:00Z",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet",
                        "content": [{"type": "text", "text": "hello"}],
                    },
                }
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        self.assertEqual(session.platformType, "Claude Code")
        self.assertEqual(session.platformVersion, "")
        self.assertEqual(session.platformVersions, [])
        self.assertEqual(session.platformVersionTransitions, [])

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

    def test_skill_load_message_is_linked_to_skill_tool_call(self) -> None:
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
                                "id": "toolu_skill_1",
                                "name": "Skill",
                                "input": {"skill": "dev-execution"},
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-02-16T10:00:01Z",
                    "sourceToolUseID": "toolu_skill_1",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "<command-name>dev-execution</command-name>\n<skill-format>true</skill-format>",
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Base directory for this skill: "
                                    "/Users/miethe/dev/homelab/development/skillmeat/.claude/skills/dev-execution\n\n"
                                    "Dev execution orchestration guidance."
                                ),
                            },
                        ],
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        skill_artifacts = [a for a in session.linkedArtifacts if a.type == "skill" and a.title == "dev-execution"]
        self.assertEqual(len(skill_artifacts), 1)
        self.assertEqual(
            skill_artifacts[0].url,
            "/Users/miethe/dev/homelab/development/skillmeat/.claude/skills/dev-execution",
        )
        self.assertEqual(skill_artifacts[0].source, "tool+skill-load")

        command_logs = [l for l in session.logs if l.type == "command" and l.content == "dev-execution"]
        self.assertEqual(len(command_logs), 1)
        self.assertTrue(command_logs[0].metadata.get("skillFormat"))
        self.assertEqual(command_logs[0].metadata.get("skill"), "dev-execution")

        skill_loads = session.sessionForensics.get("entryContext", {}).get("skillLoads", [])
        self.assertEqual(len(skill_loads), 1)
        self.assertEqual(skill_loads[0].get("skill"), "dev-execution")

    def test_skill_format_message_without_skill_tool_still_creates_skill_artifact(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "user",
                    "timestamp": "2026-02-16T11:00:00Z",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "<command-name>artifact-tracking</command-name>\n<skill-format>true</skill-format>",
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Base directory for this skill: "
                                    "/Users/miethe/dev/homelab/development/skillmeat/.claude/skills/artifact-tracking\n\n"
                                    "Token-efficient artifact tracking skill."
                                ),
                            },
                        ],
                    },
                }
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        skill_artifacts = [a for a in session.linkedArtifacts if a.type == "skill" and a.title == "artifact-tracking"]
        self.assertEqual(len(skill_artifacts), 1)
        self.assertEqual(
            skill_artifacts[0].url,
            "/Users/miethe/dev/homelab/development/skillmeat/.claude/skills/artifact-tracking",
        )
        self.assertEqual(skill_artifacts[0].source, "skill-load")

    def test_manage_plan_status_bash_command_is_extracted(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T12:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_bash_1",
                                "name": "Bash",
                                "input": {
                                    "command": (
                                        "python .claude/skills/artifact-tracking/scripts/manage-plan-status.py "
                                        "--file docs/project_plans/implementation_plans/features/similar-artifacts-v1.md "
                                        "--status in-progress"
                                    )
                                },
                            }
                        ],
                    },
                }
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        artifact_types = {a.type for a in session.linkedArtifacts}
        self.assertIn("plan_status_update", artifact_types)
        self.assertIn("plan_file", artifact_types)

        bash_logs = [l for l in session.logs if l.type == "tool" and l.toolCall and l.toolCall.name == "Bash"]
        self.assertEqual(len(bash_logs), 1)
        plan_status = bash_logs[0].metadata.get("planStatus", {})
        self.assertEqual(plan_status.get("operation"), "update")
        self.assertEqual(plan_status.get("status"), "in-progress")
        self.assertEqual(
            plan_status.get("file"),
            "docs/project_plans/implementation_plans/features/similar-artifacts-v1.md",
        )

        plan_updates = session.sessionForensics.get("entryContext", {}).get("planStatusUpdates", [])
        self.assertEqual(len(plan_updates), 1)
        self.assertEqual(plan_updates[0].get("status"), "in-progress")

    def test_batch_message_is_parsed_into_batch_artifacts(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T13:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Statuses updated. Now executing **Batch 1** — two independent tasks in parallel:\n"
                                    "- **SA-P1-001**: DuplicatePair.ignored migration (`data-layer-expert`)\n"
                                    "- **SA-P1-002**: SimilarityResult dataclass (`python-backend-engineer`)"
                                ),
                            }
                        ],
                    },
                }
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        batch_logs = [l for l in session.logs if l.type == "message" and "batchExecution" in l.metadata]
        self.assertEqual(len(batch_logs), 1)
        batch = batch_logs[0].metadata.get("batchExecution", {})
        self.assertEqual(batch.get("batchId"), "1")
        self.assertEqual(batch.get("taskCount"), 2)

        task_ids = {str(task.get("taskId")) for task in batch.get("tasks", [])}
        self.assertEqual(task_ids, {"SA-P1-001", "SA-P1-002"})

        artifact_types = {a.type for a in session.linkedArtifacts}
        self.assertIn("task_batch", artifact_types)
        self.assertIn("batch_task", artifact_types)

        batch_events = session.sessionForensics.get("entryContext", {}).get("batchExecutions", [])
        self.assertEqual(len(batch_events), 1)
        self.assertEqual(batch_events[0].get("batchId"), "1")

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
        artifact_types = {a.type for a in session.linkedArtifacts}
        self.assertIn("command", artifact_types)
        self.assertNotIn("command_path", artifact_types)
        self.assertNotIn("feature_slug", artifact_types)
        self.assertNotIn("command_phase", artifact_types)
        self.assertNotIn("request", artifact_types)

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

    def test_thinking_level_from_explicit_metadata(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T15:00:00Z",
                    "thinkingMetadata": {"level": "High", "maxThinkingTokens": 32000},
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "done"}],
                    },
                }
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.thinkingLevel, "high")
        self.assertEqual(session.sessionForensics.get("thinking", {}).get("source"), "thinkingMetadata.level")

    def test_thinking_level_from_max_tokens(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T15:05:00Z",
                    "thinkingMetadata": {"maxThinkingTokens": 12000},
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "done"}],
                    },
                }
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.thinkingLevel, "medium")
        self.assertEqual(
            session.sessionForensics.get("thinking", {}).get("source"),
            "thinkingMetadata.maxThinkingTokens",
        )

    def test_sidecar_data_is_linked_for_todos_tasks_teams_and_session_env(self) -> None:
        raw_session_id = "11111111-2222-3333-4444-555555555555"
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T16:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "working"}],
                    },
                }
            ],
            relative_path=f".claude/projects/demo/{raw_session_id}.jsonl",
        )
        claude_root = path.parents[2]

        todo_dir = claude_root / "todos"
        todo_dir.mkdir(parents=True, exist_ok=True)
        (todo_dir / f"{raw_session_id}-agent-ui-agent.json").write_text(
            json.dumps(
                [
                    {
                        "content": "Implement feature",
                        "status": "in_progress",
                        "activeForm": "Implementing feature",
                    }
                ]
            ),
            encoding="utf-8",
        )

        task_dir = claude_root / "tasks" / raw_session_id
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / ".highwatermark").write_text("2", encoding="utf-8")
        (task_dir / ".lock").write_text("", encoding="utf-8")
        (task_dir / "1.json").write_text(
            json.dumps(
                {
                    "id": "1",
                    "subject": "Implement parser enhancement",
                    "description": "Add session sidecar parsing",
                    "activeForm": "Implementing parser enhancement",
                    "status": "completed",
                    "blocks": [],
                    "blockedBy": [],
                }
            ),
            encoding="utf-8",
        )

        team_inbox_dir = claude_root / "teams" / raw_session_id / "inboxes"
        team_inbox_dir.mkdir(parents=True, exist_ok=True)
        (team_inbox_dir / "ui-engineer.json").write_text(
            json.dumps(
                [
                    {
                        "from": "team-lead",
                        "text": json.dumps(
                            {
                                "type": "task_assignment",
                                "taskId": "1",
                                "subject": "Build dashboard",
                                "description": "Create dashboard UI",
                                "assignedBy": "team-lead",
                            }
                        ),
                        "timestamp": "2026-02-16T16:00:01Z",
                        "read": False,
                    }
                ]
            ),
            encoding="utf-8",
        )

        session_env_dir = claude_root / "session-env" / raw_session_id
        session_env_dir.mkdir(parents=True, exist_ok=True)
        (session_env_dir / "env.txt").write_text("FOO=bar\n", encoding="utf-8")

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        sidecars = session.sessionForensics.get("sidecars", {})
        todos = sidecars.get("todos", {})
        tasks = sidecars.get("tasks", {})
        teams = sidecars.get("teams", {})
        session_env = sidecars.get("sessionEnv", {})

        self.assertEqual(todos.get("totalItems"), 1)
        self.assertEqual(tasks.get("highWatermarkValue"), 2)
        self.assertTrue(tasks.get("lockPresent"))
        self.assertEqual(tasks.get("tasks", [])[0].get("description"), "Add session sidecar parsing")
        self.assertEqual(teams.get("totalMessages"), 1)
        self.assertIn("ui-engineer", teams.get("teamMembers", []))
        self.assertEqual(teams.get("inboxes", [])[0].get("messages", [])[0].get("assignedBy"), "team-lead")
        self.assertTrue(session_env.get("exists"))
        self.assertEqual(session_env.get("fileCount"), 1)

        artifact_types = {artifact.type for artifact in session.linkedArtifacts}
        self.assertIn("todo_file", artifact_types)
        self.assertIn("task_dir", artifact_types)
        self.assertIn("team_inbox", artifact_types)
        self.assertIn("session_env", artifact_types)


if __name__ == "__main__":
    unittest.main()
