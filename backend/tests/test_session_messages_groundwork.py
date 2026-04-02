"""Tests for Phase 3 DB caching groundwork: canonical session_messages seam."""
import unittest
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import aiosqlite

from backend.db import sqlite_migrations
from backend.application.services.sessions import SessionTranscriptService
from backend.services.session_transcript_projection import project_session_messages


class SessionMessagesTableMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_messages_table_exists_after_migrations(self) -> None:
        db = await aiosqlite.connect(":memory:")
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'session_messages'"
        ) as cur:
            row = await cur.fetchone()
        self.assertIsNotNone(row, "session_messages table was not created")

    async def test_session_messages_has_required_columns(self) -> None:
        db = await aiosqlite.connect(":memory:")
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)

        async with db.execute("PRAGMA table_info(session_messages)") as cur:
            cols = {row[1] for row in await cur.fetchall()}

        required = {
            "id", "session_id", "message_index", "source_log_id", "message_id",
            "role", "message_type", "content", "event_timestamp", "agent_name",
            "tool_name", "tool_call_id", "related_tool_call_id", "linked_session_id",
            "entry_uuid", "parent_entry_uuid", "root_session_id",
            "conversation_family_id", "thread_session_id", "parent_session_id",
            "source_provenance", "metadata_json",
        }
        missing = required - cols
        self.assertFalse(missing, f"session_messages missing columns: {missing}")

    async def test_session_messages_unique_index_enforces_per_session_ordering(self) -> None:
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        self.addAsyncCleanup(db.close)

        await sqlite_migrations.run_migrations(db)
        await db.execute(
            "INSERT INTO sessions (id, project_id, created_at, updated_at, source_file) VALUES (?, ?, ?, ?, ?)",
            ("s-1", "proj-1", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", ""),
        )
        await db.execute(
            """INSERT INTO session_messages
               (session_id, message_index, role, message_type, event_timestamp, source_provenance)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("s-1", 0, "user", "message", "2026-01-01T00:00:00Z", "session_log_projection"),
        )
        await db.commit()

        with self.assertRaises(Exception):
            await db.execute(
                """INSERT INTO session_messages
                   (session_id, message_index, role, message_type, event_timestamp, source_provenance)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("s-1", 0, "assistant", "message", "2026-01-01T00:00:01Z", "session_log_projection"),
            )
            await db.commit()


class SessionTranscriptServiceFallbackTests(unittest.IsolatedAsyncioTestCase):
    def _make_ports(self, *, canonical_rows, legacy_rows):
        session_msg_repo = MagicMock()
        session_msg_repo.list_by_session = AsyncMock(return_value=canonical_rows)

        session_repo = MagicMock()
        session_repo.get_logs = AsyncMock(return_value=legacy_rows)

        storage = MagicMock()
        storage.session_messages = MagicMock(return_value=session_msg_repo)
        storage.sessions = MagicMock(return_value=session_repo)

        ports = MagicMock()
        ports.storage = storage
        return ports

    async def test_prefers_canonical_when_present(self) -> None:
        canonical = [
            {
                "session_id": "s-1",
                "message_index": 0,
                "source_log_id": "log-abc",
                "source_provenance": "session_log_projection",
                "role": "user",
                "message_type": "message",
                "content": "hello",
                "event_timestamp": "2026-01-01T00:00:00Z",
                "agent_name": None,
                "tool_name": None,
                "tool_call_id": None,
                "related_tool_call_id": None,
                "linked_session_id": None,
                "entry_uuid": None,
                "parent_entry_uuid": None,
                "message_id": "",
                "metadata_json": None,
            }
        ]
        legacy = [
            {
                "source_log_id": "legacy-1",
                "log_index": 0,
                "timestamp": "2026-01-01T00:00:00Z",
                "speaker": "assistant",
                "type": "message",
                "content": "legacy transcript",
                "metadata_json": None,
            }
        ]
        ports = self._make_ports(canonical_rows=canonical, legacy_rows=legacy)
        svc = SessionTranscriptService()

        result = await svc.list_session_logs({"id": "s-1"}, ports)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "log-abc")
        self.assertEqual(result[0]["speaker"], "user")
        # canonical path maps event_timestamp → timestamp
        self.assertEqual(result[0]["timestamp"], "2026-01-01T00:00:00Z")
        # legacy get_logs should NOT have been called
        ports.storage.sessions().get_logs.assert_not_awaited()

    async def test_canonical_assistant_role_maps_back_to_agent_speaker(self) -> None:
        canonical = [
            {
                "session_id": "s-1",
                "message_index": 0,
                "source_log_id": "log-abc",
                "source_provenance": "claude_code_jsonl",
                "role": "assistant",
                "message_type": "tool",
                "content": "called bash",
                "event_timestamp": "2026-01-01T00:00:00Z",
                "agent_name": None,
                "tool_name": "bash",
                "tool_call_id": "tc-1",
                "related_tool_call_id": None,
                "linked_session_id": None,
                "entry_uuid": None,
                "parent_entry_uuid": None,
                "message_id": "msg-1",
                "metadata_json": None,
            }
        ]
        ports = self._make_ports(canonical_rows=canonical, legacy_rows=[])
        svc = SessionTranscriptService()

        result = await svc.list_session_logs({"id": "s-1"}, ports)

        self.assertEqual(result[0]["speaker"], "agent")
        self.assertEqual(cast(dict[str, Any], result[0]["toolCall"])["name"], "bash")

    async def test_falls_back_to_legacy_logs_when_no_canonical(self) -> None:
        legacy = [
            {
                "source_log_id": "legacy-1",
                "log_index": 0,
                "timestamp": "2026-02-01T00:00:00Z",
                "speaker": "assistant",
                "type": "tool",
                "content": "ran tool",
                "agent_name": None,
                "linked_session_id": None,
                "related_tool_call_id": None,
                "tool_name": "bash",
                "tool_call_id": "tc-1",
                "tool_args": '{"cmd": "ls"}',
                "tool_output": "file.py",
                "tool_status": "success",
                "metadata_json": None,
            }
        ]
        ports = self._make_ports(canonical_rows=[], legacy_rows=legacy)
        svc = SessionTranscriptService()

        result = await svc.list_session_logs({"id": "s-1"}, ports)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "legacy-1")
        self.assertEqual(result[0]["speaker"], "assistant")
        self.assertEqual(result[0]["type"], "tool")
        self.assertIsNotNone(result[0]["toolCall"])
        tool_call = cast(dict[str, Any], result[0]["toolCall"])
        self.assertEqual(tool_call["name"], "bash")

    async def test_empty_session_returns_empty_list(self) -> None:
        ports = self._make_ports(canonical_rows=[], legacy_rows=[])
        svc = SessionTranscriptService()
        result = await svc.list_session_logs({"id": "s-empty"}, ports)
        self.assertEqual(result, [])


class CanonicalPayloadProvenanceTests(unittest.TestCase):
    def _svc(self):
        return SessionTranscriptService()

    def test_canonical_payload_sets_source_provenance_in_metadata(self) -> None:
        svc = self._svc()
        row = {
            "source_log_id": "log-x",
            "message_index": 0,
            "source_provenance": "live_ingest",
            "role": "assistant",
            "message_type": "message",
            "content": "hi",
            "event_timestamp": "2026-03-01T00:00:00Z",
            "agent_name": None,
            "tool_name": None,
            "tool_call_id": None,
            "related_tool_call_id": None,
            "linked_session_id": None,
            "entry_uuid": "uuid-a",
            "parent_entry_uuid": "uuid-parent",
            "message_id": "msg-1",
            "metadata_json": None,
        }
        payload = svc._canonical_log_payload(row)
        meta = cast(dict[str, Any], payload["metadata"])

        self.assertEqual(meta["sourceProvenance"], "live_ingest")
        self.assertEqual(meta["entryUuid"], "uuid-a")
        self.assertEqual(meta["parentUuid"], "uuid-parent")
        self.assertEqual(meta["rawMessageId"], "msg-1")

    def test_canonical_payload_does_not_overwrite_existing_metadata_provenance(self) -> None:
        import json
        svc = self._svc()
        row = {
            "source_log_id": "log-y",
            "message_index": 1,
            "source_provenance": "session_log_projection",
            "role": "user",
            "message_type": "message",
            "content": "text",
            "event_timestamp": "2026-03-01T00:00:01Z",
            "agent_name": None,
            "tool_name": None,
            "tool_call_id": None,
            "related_tool_call_id": None,
            "linked_session_id": None,
            "entry_uuid": None,
            "parent_entry_uuid": None,
            "message_id": "",
            "metadata_json": json.dumps({"sourceProvenance": "custom_source"}),
        }
        payload = svc._canonical_log_payload(row)
        meta = cast(dict[str, Any], payload["metadata"])
        # pre-existing value in metadata_json must not be overwritten by source_provenance column
        self.assertEqual(meta["sourceProvenance"], "custom_source")

    def test_legacy_payload_omits_tool_call_when_no_tool_fields(self) -> None:
        svc = self._svc()
        row = {
            "source_log_id": "log-z",
            "log_index": 0,
            "timestamp": "2026-03-01T00:00:00Z",
            "speaker": "user",
            "type": "message",
            "content": "hello",
            "agent_name": None,
            "linked_session_id": None,
            "related_tool_call_id": None,
            "tool_name": None,
            "tool_call_id": None,
            "tool_args": None,
            "tool_output": None,
            "tool_status": None,
            "metadata_json": None,
        }
        payload = svc._legacy_log_payload(row)
        self.assertIsNone(payload["toolCall"])


class ProjectSessionMessagesProjectionTests(unittest.TestCase):
    def test_projects_lineage_fields_from_session_row(self) -> None:
        session_row = {
            "id": "child-1",
            "rootSessionId": "root-1",
            "conversationFamilyId": "family-1",
            "parentSessionId": "parent-1",
        }
        logs = [
            {
                "id": "log-1",
                "speaker": "user",
                "type": "message",
                "content": "hi",
                "timestamp": "2026-03-01T00:00:00Z",
                "agentName": "",
                "metadata": {},
            }
        ]
        projected = project_session_messages(session_row, logs)

        self.assertEqual(len(projected), 1)
        msg = projected[0]
        self.assertEqual(msg["rootSessionId"], "root-1")
        self.assertEqual(msg["conversationFamilyId"], "family-1")
        self.assertEqual(msg["role"], "user")
        self.assertEqual(msg["threadSessionId"], "child-1")
        self.assertEqual(msg["parentSessionId"], "parent-1")
        self.assertEqual(msg["messageIndex"], 0)
        self.assertEqual(msg["sourceLogId"], "log-1")

    def test_projects_tool_call_into_metadata(self) -> None:
        session_row = {"id": "s-tool"}
        logs = [
            {
                "id": "log-tool",
                "speaker": "assistant",
                "type": "tool",
                "content": "",
                "timestamp": "2026-03-01T00:00:00Z",
                "agentName": "",
                "metadata": {},
                "toolCall": {
                    "name": "bash",
                    "id": "tc-1",
                    "args": '{"cmd": "ls"}',
                    "output": "file.py",
                    "status": "success",
                },
            }
        ]
        projected = project_session_messages(session_row, logs)
        msg = projected[0]

        self.assertEqual(msg["toolName"], "bash")
        self.assertEqual(msg["toolCallId"], "tc-1")
        meta = cast(dict[str, Any], msg["metadata"])
        self.assertEqual(meta["toolArgs"], '{"cmd": "ls"}')
        self.assertEqual(meta["toolOutput"], "file.py")

    def test_uses_session_id_as_fallback_for_root_and_family(self) -> None:
        session_row = {"id": "standalone"}
        projected = project_session_messages(session_row, [])
        self.assertEqual(projected, [])

        # Verify lineage defaults when session lacks parent info by projecting one log
        logs = [{"id": "l1", "speaker": "user", "type": "message", "content": "", "timestamp": "", "agentName": "", "metadata": {}}]
        projected = project_session_messages(session_row, logs)
        msg = projected[0]
        self.assertEqual(msg["rootSessionId"], "standalone")
        self.assertEqual(msg["conversationFamilyId"], "standalone")
        self.assertEqual(msg["parentSessionId"], "")
