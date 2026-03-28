import types
import unittest

from backend.application.services.sessions import SessionTranscriptService
from backend.services.session_transcript_projection import project_session_messages


class _FakeSessionRepo:
    def __init__(self, logs):
        self._logs = logs

    async def get_logs(self, session_id):
        _ = session_id
        return list(self._logs)


class _FakeSessionMessageRepo:
    def __init__(self, rows):
        self._rows = rows

    async def list_by_session(self, session_id):
        _ = session_id
        return list(self._rows)


class _FakeStorage:
    def __init__(self, logs, rows):
        self._session_repo = _FakeSessionRepo(logs)
        self._message_repo = _FakeSessionMessageRepo(rows)

    def sessions(self):
        return self._session_repo

    def session_messages(self):
        return self._message_repo


class SessionTranscriptProjectionTests(unittest.IsolatedAsyncioTestCase):
    def test_project_session_messages_preserves_lineage_and_provenance(self) -> None:
        session = {
            "id": "session-1",
            "rootSessionId": "root-1",
            "conversationFamilyId": "family-1",
            "parentSessionId": "parent-1",
        }
        logs = [
            {
                "id": "log-0",
                "timestamp": "2026-03-27T12:00:00Z",
                "speaker": "assistant",
                "type": "tool",
                "content": "ran tool",
                "agentName": "Planner",
                "linkedSessionId": "child-1",
                "relatedToolCallId": "tool-related",
                "metadata": {
                    "entryUuid": "entry-1",
                    "parentUuid": "entry-0",
                    "rawMessageId": "message-1",
                    "sourceProvenance": "claude_code_jsonl",
                },
                "toolCall": {
                    "id": "tool-1",
                    "name": "bash",
                    "args": "echo hi",
                    "output": "hi",
                    "status": "success",
                },
            }
        ]

        projected = project_session_messages(session, logs)

        self.assertEqual(len(projected), 1)
        self.assertEqual(projected[0]["rootSessionId"], "root-1")
        self.assertEqual(projected[0]["conversationFamilyId"], "family-1")
        self.assertEqual(projected[0]["parentSessionId"], "parent-1")
        self.assertEqual(projected[0]["entryUuid"], "entry-1")
        self.assertEqual(projected[0]["parentEntryUuid"], "entry-0")
        self.assertEqual(projected[0]["messageId"], "message-1")
        self.assertEqual(projected[0]["sourceProvenance"], "claude_code_jsonl")

    async def test_session_transcript_service_prefers_canonical_rows(self) -> None:
        service = SessionTranscriptService()
        ports = types.SimpleNamespace(
            storage=_FakeStorage(
                logs=[],
                rows=[
                    {
                        "message_index": 0,
                        "source_log_id": "log-0",
                        "message_id": "message-1",
                        "role": "assistant",
                        "message_type": "message",
                        "content": "hello",
                        "event_timestamp": "2026-03-27T12:00:00Z",
                        "agent_name": "Planner",
                        "linked_session_id": "",
                        "related_tool_call_id": "",
                        "tool_name": None,
                        "tool_call_id": None,
                        "entry_uuid": "entry-1",
                        "parent_entry_uuid": "",
                        "source_provenance": "canonical_table",
                        "metadata_json": "{\"custom\": true}",
                    }
                ],
            )
        )

        logs = await service.list_session_logs({"id": "session-1"}, ports)

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["id"], "log-0")
        self.assertEqual(logs[0]["metadata"]["sourceProvenance"], "canonical_table")
        self.assertEqual(logs[0]["metadata"]["entryUuid"], "entry-1")

    async def test_session_transcript_service_falls_back_to_legacy_logs(self) -> None:
        service = SessionTranscriptService()
        ports = types.SimpleNamespace(
            storage=_FakeStorage(
                logs=[
                    {
                        "log_index": 0,
                        "source_log_id": "log-0",
                        "timestamp": "2026-03-27T12:00:00Z",
                        "speaker": "assistant",
                        "type": "message",
                        "content": "hello",
                        "agent_name": "Planner",
                        "linked_session_id": "",
                        "related_tool_call_id": "",
                        "tool_name": None,
                        "tool_call_id": None,
                        "tool_args": None,
                        "tool_output": None,
                        "tool_status": "success",
                        "metadata_json": "{\"sourceProvenance\": \"legacy\"}",
                    }
                ],
                rows=[],
            )
        )

        logs = await service.list_session_logs({"id": "session-1"}, ports)

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["id"], "log-0")
        self.assertEqual(logs[0]["metadata"]["sourceProvenance"], "legacy")
