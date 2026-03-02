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
