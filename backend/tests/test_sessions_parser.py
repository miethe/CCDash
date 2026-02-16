import json
import tempfile
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

    def test_command_args_paths_are_tracked_as_files(self) -> None:
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
        self.assertIn("docs/project_plans/implementation_plans/features/example-v1.md", file_paths)

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


if __name__ == "__main__":
    unittest.main()
