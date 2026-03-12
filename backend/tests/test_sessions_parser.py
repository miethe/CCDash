import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.parsers.sessions import parse_session_file
from backend.parsers.platforms.claude_code import parser as claude_parser


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

    def test_usage_summary_tracks_nested_usage_fields_and_tool_caller_metadata(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-03-08T10:00:00Z",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-4-6",
                        "id": "msg_usage_1",
                        "type": "message",
                        "stop_reason": "tool_use",
                        "stop_sequence": "</tool>",
                        "usage": {
                            "input_tokens": 2,
                            "cache_creation_input_tokens": 10,
                            "cache_read_input_tokens": 20,
                            "cache_creation": {
                                "ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 10,
                            },
                            "output_tokens": 5,
                            "service_tier": "standard",
                            "inference_geo": "us",
                            "server_tool_use": {
                                "web_search_requests": 1,
                                "web_fetch_requests": 2,
                            },
                            "iterations": [{"index": 1}],
                            "speed": "standard",
                        },
                        "content": [
                            {"type": "text", "text": "Searching for context."},
                            {
                                "type": "tool_use",
                                "id": "toolu_usage_1",
                                "name": "Grep",
                                "input": {"pattern": "usage", "path": "/tmp/project"},
                                "caller": {"type": "direct", "invoked_by": "assistant"},
                            },
                        ],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-03-08T10:00:01Z",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_usage_1",
                                "is_error": False,
                                "content": "backend/parsers/platforms/claude_code/parser.py",
                            }
                        ],
                    },
                    "toolUseResult": {
                        "status": "completed",
                        "totalTokens": 99,
                        "totalDurationMs": 1500,
                        "totalToolUseCount": 3,
                        "usage": {
                            "input_tokens": 7,
                            "cache_creation_input_tokens": 13,
                            "cache_read_input_tokens": 17,
                            "cache_creation": {
                                "ephemeral_5m_input_tokens": 13,
                                "ephemeral_1h_input_tokens": 0,
                            },
                            "output_tokens": 11,
                            "service_tier": "standard",
                            "inference_geo": "us",
                            "server_tool_use": {
                                "web_search_requests": 4,
                            },
                            "iterations": [{"index": 1}, {"index": 2}],
                            "speed": "fast",
                        },
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        message_logs = [log for log in session.logs if log.type == "message"]
        self.assertEqual(len(message_logs), 1)
        self.assertEqual(message_logs[0].metadata.get("inputTokens"), 2)
        self.assertEqual(message_logs[0].metadata.get("outputTokens"), 5)
        self.assertEqual(message_logs[0].metadata.get("totalTokens"), 7)
        self.assertEqual(message_logs[0].metadata.get("cache_creation_input_tokens"), 10)
        self.assertEqual(message_logs[0].metadata.get("cache_read_input_tokens"), 20)
        self.assertEqual(message_logs[0].metadata.get("service_tier"), "standard")
        self.assertEqual(message_logs[0].metadata.get("inference_geo"), "us")
        self.assertEqual(message_logs[0].metadata.get("speed"), "standard")
        self.assertEqual(message_logs[0].metadata.get("iterationCount"), 1)
        self.assertEqual(message_logs[0].metadata.get("stopReason"), "tool_use")
        self.assertEqual(message_logs[0].metadata.get("stopSequence"), "</tool>")
        self.assertEqual(
            message_logs[0].metadata.get("server_tool_use"),
            {"web_search_requests": 1, "web_fetch_requests": 2},
        )

        tool_logs = [log for log in session.logs if log.type == "tool" and log.toolCall]
        self.assertEqual(len(tool_logs), 1)
        self.assertEqual(tool_logs[0].metadata.get("callerType"), "direct")
        self.assertEqual(
            tool_logs[0].metadata.get("caller"),
            {"type": "direct", "invoked_by": "assistant"},
        )

        usage_summary = session.sessionForensics.get("usageSummary", {})
        self.assertEqual(usage_summary.get("assistantMessageCount"), 1)
        self.assertEqual(usage_summary.get("assistantMessagesWithUsage"), 1)
        self.assertEqual(usage_summary.get("messageTotals", {}).get("inputTokens"), 2)
        self.assertEqual(usage_summary.get("messageTotals", {}).get("outputTokens"), 5)
        self.assertEqual(usage_summary.get("messageTotals", {}).get("cacheCreationInputTokens"), 10)
        self.assertEqual(usage_summary.get("messageTotals", {}).get("cacheReadInputTokens"), 20)
        self.assertEqual(usage_summary.get("messageTotals", {}).get("allInputTokens"), 32)
        self.assertEqual(usage_summary.get("messageTotals", {}).get("allTokens"), 37)
        self.assertEqual(
            usage_summary.get("cacheCreationTotals", {}).get("ephemeral_1h_input_tokens"),
            10,
        )
        self.assertEqual(
            usage_summary.get("serverToolUseTotals", {}).get("web_fetch_requests"),
            2,
        )
        self.assertEqual(usage_summary.get("iterationCount"), 1)
        self.assertEqual(usage_summary.get("speedCounts", {}).get("standard"), 1)
        self.assertEqual(usage_summary.get("serviceTierCounts", {}).get("standard"), 1)
        self.assertEqual(usage_summary.get("inferenceGeoCounts", {}).get("us"), 1)
        self.assertEqual(
            usage_summary.get("toolResultReportedTotals", {}).get("totalTokens"),
            99,
        )
        self.assertEqual(
            usage_summary.get("toolResultReportedTotals", {}).get("totalDurationMs"),
            1500,
        )
        self.assertEqual(
            usage_summary.get("toolResultReportedTotals", {}).get("totalToolUseCount"),
            3,
        )
        self.assertEqual(
            usage_summary.get("toolResultUsageTotals", {}).get("inputTokens"),
            7,
        )
        self.assertEqual(
            usage_summary.get("toolResultUsageTotals", {}).get("outputTokens"),
            11,
        )
        self.assertEqual(
            usage_summary.get("toolResultUsageTotals", {}).get("cacheCreationInputTokens"),
            13,
        )
        self.assertEqual(
            usage_summary.get("toolResultUsageTotals", {}).get("cacheReadInputTokens"),
            17,
        )
        self.assertEqual(
            usage_summary.get("toolResultUsageTotals", {}).get("allTokens"),
            48,
        )
        self.assertEqual(
            usage_summary.get("toolResultServerToolUseTotals", {}).get("web_search_requests"),
            4,
        )
        self.assertEqual(usage_summary.get("toolResultIterationCount"), 2)
        self.assertEqual(usage_summary.get("toolResultSpeedCounts", {}).get("fast"), 1)

        entry_context = session.sessionForensics.get("entryContext", {})
        self.assertEqual(entry_context.get("messageStopReasonCounts", {}).get("tool_use"), 1)
        self.assertEqual(entry_context.get("messageStopSequenceCounts", {}).get("</tool>"), 1)
        self.assertEqual(entry_context.get("toolCallerTypeCounts", {}).get("direct"), 1)

    def test_relay_mirror_usage_is_tracked_but_excluded_from_observed_totals(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-03-08T10:00:00Z",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-4-6",
                        "usage": {
                            "input_tokens": 3,
                            "output_tokens": 7,
                            "cache_creation_input_tokens": 11,
                            "cache_read_input_tokens": 13,
                        },
                        "content": [{"type": "text", "text": "Primary assistant message."}],
                    },
                },
                {
                    "type": "progress",
                    "timestamp": "2026-03-08T10:00:01Z",
                    "data": {
                        "type": "agent_progress",
                        "message": {
                            "message": {
                                "usage": {
                                    "input_tokens": 100,
                                    "output_tokens": 200,
                                    "cache_creation_input_tokens": 300,
                                    "cache_read_input_tokens": 400,
                                }
                            }
                        },
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        usage_summary = session.sessionForensics.get("usageSummary", {})
        self.assertEqual(usage_summary.get("messageTotals", {}).get("allTokens"), 34)
        self.assertEqual(usage_summary.get("relayMirrorTotals", {}).get("excludedCount"), 1)
        self.assertEqual(usage_summary.get("relayMirrorTotals", {}).get("allTokens"), 1000)
        self.assertEqual(
            usage_summary.get("relayMirrorTotals", {}).get("policy"),
            "excluded_from_observed_tokens_until_attribution",
        )

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

    def test_hook_progress_creates_hook_artifact_with_metadata(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "progress",
                    "timestamp": "2026-03-05T11:00:00Z",
                    "data": {
                        "type": "hook_progress",
                        "hookName": "notebooklm-sync-hook.sh",
                        "hookEvent": "post-tool",
                        "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/notebooklm-sync-hook.sh --session abc",
                    },
                }
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        hook_logs = [
            log
            for log in session.logs
            if log.type == "system" and log.metadata.get("eventType") == "hook_progress"
        ]
        self.assertEqual(len(hook_logs), 1)
        self.assertEqual(hook_logs[0].metadata.get("hookName"), "notebooklm-sync-hook.sh")
        self.assertEqual(hook_logs[0].metadata.get("hookEvent"), "post-tool")
        self.assertIn(".claude/hooks/notebooklm-sync-hook.sh", str(hook_logs[0].metadata.get("hookPath") or ""))

        hook_artifacts = [a for a in session.linkedArtifacts if a.type == "hook"]
        self.assertEqual(len(hook_artifacts), 1)
        self.assertEqual(hook_artifacts[0].title, "notebooklm-sync-hook.sh")
        self.assertEqual(hook_artifacts[0].source, "hook_progress")

        hook_forensics = session.sessionForensics.get("entryContext", {}).get("hookInvocations", [])
        self.assertEqual(len(hook_forensics), 1)
        self.assertEqual(hook_forensics[0].get("hookName"), "notebooklm-sync-hook.sh")

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

    def test_detects_fork_and_materializes_derived_session(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "user",
                    "timestamp": "2026-03-01T10:00:00Z",
                    "uuid": "u0",
                    "message": {"role": "user", "content": "Start task"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-03-01T10:00:01Z",
                    "uuid": "a1",
                    "parentUuid": "u0",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet-4-0-20251001",
                        "content": [{"type": "text", "text": "Plan options"}],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-03-01T10:00:02Z",
                    "uuid": "u2",
                    "parentUuid": "a1",
                    "message": {"role": "user", "content": "Take option A"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-03-01T10:00:03Z",
                    "uuid": "a2",
                    "parentUuid": "u2",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet-4-0-20251001",
                        "content": [{"type": "text", "text": "Implementing A"}],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-03-01T10:00:04Z",
                    "uuid": "u3",
                    "parentUuid": "a1",
                    "message": {"role": "user", "content": "Fork to option B"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-03-01T10:00:05Z",
                    "uuid": "a3",
                    "parentUuid": "u3",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet-4-0-20251001",
                        "content": [{"type": "text", "text": "Implementing B"}],
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        expected_fork_id = claude_parser._make_fork_session_id("session", "u3")
        self.assertEqual(session.threadKind, "root")
        self.assertEqual(session.forkCount, 1)
        self.assertEqual(session.conversationFamilyId, session.id)
        self.assertEqual(len(session.forks or []), 1)
        self.assertEqual(str((session.forks or [])[0].get("sessionId") or ""), expected_fork_id)

        fork_note_logs = [
            log for log in session.logs
            if log.type == "system" and log.metadata.get("eventType") == "fork_start"
        ]
        self.assertEqual(len(fork_note_logs), 1)
        self.assertEqual(fork_note_logs[0].linkedSessionId, expected_fork_id)

        derived_sessions = session.derivedSessions or []
        self.assertEqual(len(derived_sessions), 1)
        fork_session = derived_sessions[0]
        self.assertEqual(fork_session["id"], expected_fork_id)
        self.assertEqual(fork_session["threadKind"], "fork")
        self.assertEqual(fork_session["forkParentSessionId"], session.id)
        self.assertTrue(any(log.get("content") == "Fork to option B" for log in fork_session.get("logs", [])))

        relationships = session.sessionRelationships or []
        fork_relationships = [r for r in relationships if r.get("relationshipType") == "fork"]
        self.assertEqual(len(fork_relationships), 1)
        self.assertEqual(fork_relationships[0]["childSessionId"], expected_fork_id)

    def test_task_tool_extracts_metadata_from_description_and_prompt(self) -> None:
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
                                "id": "toolu_task_3",
                                "name": "Task",
                                "input": {
                                    "description": "SSO-1.5: Frontend text_score display",
                                    "prompt": "Implement UI text_score rendering and edge-state handling.",
                                    "subagent_type": "ui-engineer-enhanced",
                                    "mode": "acceptEdits",
                                    "model": "sonnet",
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

        task_tools = [l for l in session.logs if l.type == "tool" and l.toolCall and l.toolCall.name == "Task"]
        self.assertEqual(len(task_tools), 1)
        metadata = task_tools[0].metadata
        self.assertEqual(metadata.get("taskId"), "SSO-1.5")
        self.assertEqual(metadata.get("taskDescription"), "SSO-1.5: Frontend text_score display")
        self.assertEqual(metadata.get("taskSubagentType"), "ui-engineer-enhanced")
        self.assertEqual(metadata.get("taskMode"), "acceptEdits")
        self.assertEqual(metadata.get("taskModel"), "sonnet")
        self.assertTrue(str(metadata.get("taskPromptPreview") or "").startswith("Implement UI text_score"))

        task_artifacts = [a for a in session.linkedArtifacts if a.type == "task"]
        self.assertEqual(len(task_artifacts), 1)
        self.assertEqual(task_artifacts[0].title, "SSO-1.5")

    def test_agent_tool_extracts_metadata_and_links_subthread(self) -> None:
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-03-05T10:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_agent_1",
                                "name": "Agent",
                                "input": {
                                    "description": "TASK-5.1: Replace direct session usage",
                                    "prompt": "Migrate router to repository DI.",
                                    "subagent_type": "python-backend-engineer",
                                    "mode": "bypassPermissions",
                                    "run_in_background": True,
                                },
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-03-05T10:00:01Z",
                    "toolUseResult": {
                        "status": "async_launched",
                        "isAsync": True,
                        "agentId": "abc123",
                    },
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_agent_1",
                                "content": [{"type": "text", "text": "agentId: abc123"}],
                                "is_error": False,
                            }
                        ],
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        agent_tools = [l for l in session.logs if l.type == "tool" and l.toolCall and l.toolCall.name == "Agent"]
        self.assertEqual(len(agent_tools), 1)
        metadata = agent_tools[0].metadata
        self.assertEqual(metadata.get("taskId"), "TASK-5.1")
        self.assertEqual(metadata.get("taskDescription"), "TASK-5.1: Replace direct session usage")
        self.assertEqual(metadata.get("taskSubagentType"), "python-backend-engineer")
        self.assertEqual(metadata.get("taskMode"), "bypassPermissions")
        self.assertEqual(metadata.get("taskRunInBackground"), True)
        self.assertEqual(agent_tools[0].linkedSessionId, "S-agent-abc123")

        starts = [l for l in session.logs if l.type == "subagent_start"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0].linkedSessionId, "S-agent-abc123")

        agent_titles = {a.title for a in session.linkedArtifacts if a.type == "agent"}
        self.assertIn("python-backend-engineer", agent_titles)

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

    def test_bash_pytest_tool_result_captures_test_run_metadata_and_forensics(self) -> None:
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
                    "type": "assistant",
                    "timestamp": "2026-03-05T12:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_pytest_1",
                                "name": "Bash",
                                "input": {
                                    "command": "python -m pytest tests/api/test_marketplace_router.py tests/api/test_marketplace_source_security.py -x -q --tb=short 2>&1 | tail -20",
                                    "description": "Run marketplace tests to verify agent fixes",
                                    "timeout": 120000,
                                },
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-03-05T12:00:03Z",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_pytest_1",
                                "content": output_text,
                                "is_error": False,
                            }
                        ],
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        tool_logs = [l for l in session.logs if l.type == "tool" and l.toolCall and l.toolCall.id == "toolu_pytest_1"]
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

        artifact_types = {a.type for a in session.linkedArtifacts}
        self.assertIn("test_run", artifact_types)
        self.assertIn("test_domain", artifact_types)
        self.assertIn("test_target", artifact_types)

        test_execution = session.sessionForensics.get("testExecution", {})
        self.assertEqual(test_execution.get("runCount"), 1)
        self.assertEqual(test_execution.get("domainCounts", {}).get("api"), 1)
        self.assertEqual(test_execution.get("statusCounts", {}).get("passed"), 1)
        self.assertEqual(test_execution.get("resultCounts", {}).get("passed"), 130)
        analysis_signals = session.sessionForensics.get("analysisSignals", {})
        self.assertTrue(bool(analysis_signals.get("hasTestRunSignals")))

    def test_bash_pytest_truncated_output_without_header_still_parses_results(self) -> None:
        output_text = (
            "FAILED tests/api/test_marketplace_router.py::test_requires_auth - assert 401 == 200\n"
            "=========================== short test summary info ============================\n"
            "FAILED tests/api/test_marketplace_router.py::test_requires_auth - assert 401 == 200\n"
            "======================== 1 failed, 21 passed in 13.35s ========================\n"
        )
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-03-05T13:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_pytest_truncated_1",
                                "name": "Bash",
                                "input": {
                                    "command": "python -m pytest tests/api/test_marketplace_router.py -x -q --tb=short 2>&1 | tail -20",
                                    "description": "Run API tests after agent changes",
                                    "timeout": 120000,
                                },
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2026-03-05T13:00:03Z",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_pytest_truncated_1",
                                "content": output_text,
                                "is_error": False,
                            }
                        ],
                    },
                },
            ]
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        tool_logs = [l for l in session.logs if l.type == "tool" and l.toolCall and l.toolCall.id == "toolu_pytest_truncated_1"]
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

    def test_statusline_sidecar_sets_context_and_reported_cost_fields(self) -> None:
        raw_session_id = "22222222-3333-4444-5555-666666666666"
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-03-12T12:00:00Z",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet-4-5-20260101",
                        "usage": {"input_tokens": 10, "output_tokens": 5},
                        "content": [{"type": "text", "text": "Working."}],
                    },
                }
            ],
            relative_path=f".claude/projects/demo/{raw_session_id}.jsonl",
        )
        claude_root = path.parents[2]
        session_env_dir = claude_root / "session-env" / raw_session_id
        session_env_dir.mkdir(parents=True, exist_ok=True)
        (session_env_dir / "statusline.json").write_text(
            json.dumps(
                {
                    "session_id": raw_session_id,
                    "transcript_path": str(path),
                    "model": {
                        "id": "claude-sonnet-4-5-20260101",
                        "display_name": "Claude Sonnet 4.5",
                    },
                    "cost": {"total_cost_usd": 0.42},
                    "context_window": {
                        "total_input_tokens": 1234,
                        "total_output_tokens": 55,
                        "context_window_size": 200000,
                    },
                }
            ),
            encoding="utf-8",
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        self.assertEqual(session.currentContextTokens, 1234)
        self.assertEqual(session.contextWindowSize, 200000)
        self.assertAlmostEqual(session.contextUtilizationPct, 0.62)
        self.assertEqual(session.contextMeasurementSource, "hook_context_window")
        self.assertEqual(session.reportedCostUsd, 0.42)
        self.assertEqual(session.totalCost, 0.42)

        sidecars = session.sessionForensics.get("sidecars", {})
        latest_snapshot = sidecars.get("sessionEnv", {}).get("latestStatuslineSnapshot", {})
        self.assertEqual(latest_snapshot.get("modelId"), "claude-sonnet-4-5-20260101")

    def test_transcript_usage_fallback_sets_context_fields_without_sidecar(self) -> None:
        raw_session_id = "33333333-4444-5555-6666-777777777777"
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-03-12T12:00:00Z",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet-4-5-20260101",
                        "usage": {
                            "input_tokens": 10,
                            "output_tokens": 5,
                            "cache_creation_input_tokens": 20,
                            "cache_read_input_tokens": 30,
                        },
                        "content": [{"type": "text", "text": "First pass."}],
                    },
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-03-12T12:01:00Z",
                    "message": {
                        "role": "assistant",
                        "model": "claude-sonnet-4-5-20260101",
                        "usage": {
                            "input_tokens": 12,
                            "output_tokens": 6,
                            "cache_creation_input_tokens": 40,
                            "cache_read_input_tokens": 50,
                        },
                        "content": [{"type": "text", "text": "Second pass."}],
                    },
                },
            ],
            relative_path=f".claude/projects/demo/{raw_session_id}.jsonl",
        )

        session = parse_session_file(path)
        self.assertIsNotNone(session)
        assert session is not None

        self.assertEqual(session.currentContextTokens, 102)
        self.assertEqual(session.contextWindowSize, 200000)
        self.assertAlmostEqual(session.contextUtilizationPct, 0.05)
        self.assertEqual(session.contextMeasurementSource, "transcript_latest_assistant_usage")
        self.assertEqual(session.contextMeasuredAt, "2026-03-12T12:01:00Z")
        self.assertIsNone(session.reportedCostUsd)

    def test_extended_forensics_signals_include_resources_queue_tool_results_and_platform_telemetry(self) -> None:
        raw_session_id = "99999999-aaaa-bbbb-cccc-111111111111"
        working_directory = "/tmp/ccdash/workspace"
        path = self._write_jsonl(
            [
                {
                    "type": "assistant",
                    "timestamp": "2026-02-16T17:00:00Z",
                    "cwd": working_directory,
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_task_forensics",
                                "name": "Task",
                                "input": {"description": "F-1: analyze forensics"},
                            },
                            {
                                "type": "tool_use",
                                "id": "toolu_bash_forensics",
                                "name": "Bash",
                                "input": {
                                    "command": (
                                        "curl http://localhost:3000/health && "
                                        "psql -h db.example.com -U app appdb && "
                                        "docker compose ps"
                                    )
                                },
                            },
                        ],
                    },
                },
                {
                    "type": "progress",
                    "timestamp": "2026-02-16T17:00:01Z",
                    "parentToolUseID": "toolu_task_forensics",
                    "data": {
                        "type": "agent_progress",
                        "agentId": "agent-77",
                    },
                },
                {
                    "type": "progress",
                    "timestamp": "2026-02-16T17:00:02Z",
                    "data": {"type": "waiting_for_task"},
                },
                {
                    "type": "queue-operation",
                    "timestamp": "2026-02-16T17:00:03Z",
                    "operation": "enqueue",
                    "data": {
                        "taskId": "QUEUE-1",
                        "status": "queued",
                        "summary": "Queued analysis task",
                        "taskType": "analysis",
                        "outputFile": "task-output.log",
                        "toolUseId": "toolu_task_forensics",
                    },
                },
            ],
            relative_path=f".claude/projects/demo/{raw_session_id}.jsonl",
        )

        sidecar_root = path.parent / raw_session_id
        tool_results_dir = sidecar_root / "tool-results"
        tool_results_dir.mkdir(parents=True, exist_ok=True)
        (tool_results_dir / "result-1.txt").write_text("ok\nline2\n", encoding="utf-8")

        tmp_home = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_home.cleanup)
        home_path = Path(tmp_home.name)
        (home_path / ".claude.json").write_text(
            json.dumps(
                {
                    "numStartups": 5,
                    "promptQueueUseCount": 2,
                    "projects": {
                        working_directory: {
                            "mcpServers": {"postgres": {"type": "stdio"}, "github": {"type": "stdio"}},
                            "disabledMcpServers": ["legacy"],
                            "enabledMcpjsonServers": ["filesystem"],
                            "lastTotalWebSearchRequests": 7,
                            "projectOnboardingSeenCount": 2,
                            "hasCompletedProjectOnboarding": True,
                        }
                    },
                    "cachedGrowthBookFeatures": {"f1": True},
                    "cachedStatsigGates": {"g1": True},
                    "tipsHistory": {"tip-1": True},
                    "toolUsage": {"Bash": 4},
                    "skillUsage": {"symbols": 3},
                }
            ),
            encoding="utf-8",
        )

        claude_parser._load_global_claude_config.cache_clear()
        with patch.dict(os.environ, {"HOME": str(home_path)}):
            claude_parser._load_global_claude_config.cache_clear()
            session = parse_session_file(path)
        claude_parser._load_global_claude_config.cache_clear()

        self.assertIsNotNone(session)
        assert session is not None

        forensics = session.sessionForensics
        sidecars = forensics.get("sidecars", {})
        tool_results = sidecars.get("toolResults", {})
        self.assertTrue(tool_results.get("exists"))
        self.assertEqual(tool_results.get("fileCount"), 1)
        self.assertGreater(tool_results.get("totalBytes", 0), 0)

        queue_pressure = forensics.get("queuePressure", {})
        self.assertEqual(queue_pressure.get("waitingForTaskCount"), 1)
        self.assertEqual(queue_pressure.get("operationCounts", {}).get("enqueue"), 1)
        self.assertEqual(queue_pressure.get("taskTypeCounts", {}).get("analysis"), 1)

        resources = forensics.get("resourceFootprint", {})
        self.assertGreaterEqual(resources.get("totalObservations", 0), 3)
        self.assertEqual(resources.get("categories", {}).get("database"), 1)
        self.assertEqual(resources.get("categories", {}).get("api"), 1)
        self.assertEqual(resources.get("categories", {}).get("docker"), 1)

        subagent_topology = forensics.get("subagentTopology", {})
        self.assertEqual(subagent_topology.get("taskToolCallCount"), 1)
        self.assertEqual(subagent_topology.get("subagentStartCount"), 1)
        self.assertIn("S-agent-77", subagent_topology.get("linkedSessionIds", []))

        tool_result_intensity = forensics.get("toolResultIntensity", {})
        self.assertEqual(tool_result_intensity.get("fileCount"), 1)
        self.assertGreater(tool_result_intensity.get("totalBytes", 0), 0)

        telemetry = forensics.get("platformTelemetry", {})
        project_telemetry = telemetry.get("project", {})
        self.assertEqual(telemetry.get("numStartups"), 5)
        self.assertEqual(project_telemetry.get("mcpServerCount"), 2)
        self.assertIn("postgres", project_telemetry.get("mcpServerNames", []))
        self.assertEqual(project_telemetry.get("lastTotalWebSearchRequests"), 7)

        analysis_signals = forensics.get("analysisSignals", {})
        self.assertTrue(analysis_signals.get("hasQueuePressureSignals"))
        self.assertTrue(analysis_signals.get("hasResourceSignals"))
        self.assertTrue(analysis_signals.get("hasToolResultSignals"))
        self.assertTrue(analysis_signals.get("hasSubagentSignals"))


if __name__ == "__main__":
    unittest.main()
