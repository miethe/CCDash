"""Tests for per-message token usage feature.

Covers:
- Migration: session_messages has the four new token columns.
- Repository: insert with tokenUsage persists columns; insert without tokenUsage
  leaves columns NULL.
- Projection: project_session_messages extracts tokenUsage from metadata.
- Service: _canonical_log_payload emits tokenUsage from DB columns and from
  metadata fallback.
"""
import unittest
from typing import Any

import aiosqlite

from backend.db import sqlite_migrations
from backend.db.repositories.session_messages import SqliteSessionMessageRepository
from backend.application.services.sessions import SessionTranscriptService
from backend.services.session_transcript_projection import project_session_messages


_TOKEN_COLUMNS = {
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
}


async def _make_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await sqlite_migrations.run_migrations(db)
    await db.execute(
        "INSERT INTO sessions (id, project_id, created_at, updated_at, source_file)"
        " VALUES (?, ?, ?, ?, ?)",
        ("s-1", "proj-1", "2026-05-01T00:00:00Z", "2026-05-01T00:00:00Z", ""),
    )
    await db.commit()
    return db


class MigrationTokenColumnsTests(unittest.IsolatedAsyncioTestCase):
    """session_messages has the four new nullable token columns after migrations."""

    async def test_token_columns_exist(self) -> None:
        db = await _make_db()
        self.addAsyncCleanup(db.close)

        async with db.execute("PRAGMA table_info(session_messages)") as cur:
            cols = {row[1] for row in await cur.fetchall()}

        missing = _TOKEN_COLUMNS - cols
        self.assertFalse(missing, f"session_messages missing token columns: {missing}")


class RepositoryTokenPersistenceTests(unittest.IsolatedAsyncioTestCase):
    """Repository insert path writes token columns from tokenUsage dict."""

    async def _insert_and_read(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        db = await _make_db()
        self.addAsyncCleanup(db.close)
        repo = SqliteSessionMessageRepository(db)
        await repo.replace_session_messages("s-1", messages)
        return await repo.list_by_session("s-1")

    async def test_token_usage_written_to_columns(self) -> None:
        rows = await self._insert_and_read([
            {
                "messageIndex": 0,
                "sourceLogId": "log-0",
                "messageId": "",
                "role": "assistant",
                "messageType": "message",
                "content": "Hello",
                "timestamp": "2026-05-01T00:00:00Z",
                "agentName": "",
                "sourceProvenance": "test",
                "tokenUsage": {
                    "inputTokens": 1234,
                    "outputTokens": 567,
                    "cacheReadInputTokens": 800,
                    "cacheCreationInputTokens": 0,
                },
            }
        ])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["input_tokens"], 1234)
        self.assertEqual(row["output_tokens"], 567)
        self.assertEqual(row["cache_read_input_tokens"], 800)
        self.assertEqual(row["cache_creation_input_tokens"], 0)

    async def test_no_token_usage_leaves_columns_null(self) -> None:
        rows = await self._insert_and_read([
            {
                "messageIndex": 0,
                "sourceLogId": "log-0",
                "messageId": "",
                "role": "user",
                "messageType": "message",
                "content": "Hi",
                "timestamp": "2026-05-01T00:00:00Z",
                "agentName": "",
                "sourceProvenance": "test",
                # no tokenUsage key
            }
        ])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIsNone(row["input_tokens"])
        self.assertIsNone(row["output_tokens"])
        self.assertIsNone(row["cache_read_input_tokens"])
        self.assertIsNone(row["cache_creation_input_tokens"])


class ProjectionTokenExtractionTests(unittest.TestCase):
    """project_session_messages extracts tokenUsage from metadata fields."""

    def _project(self, logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        session = {
            "id": "s-1",
            "rootSessionId": "s-1",
            "conversationFamilyId": "s-1",
            "parentSessionId": "",
        }
        return project_session_messages(session, logs)

    def test_token_usage_extracted_when_present(self) -> None:
        logs = [
            {
                "id": "log-0",
                "timestamp": "2026-05-01T00:00:00Z",
                "speaker": "agent",
                "type": "message",
                "content": "Reply",
                "metadata": {
                    "inputTokens": 1000,
                    "outputTokens": 200,
                    "cache_read_input_tokens": 500,
                    "cache_creation_input_tokens": 0,
                },
            }
        ]
        projected = self._project(logs)
        self.assertEqual(len(projected), 1)
        tu = projected[0].get("tokenUsage")
        self.assertIsNotNone(tu)
        self.assertEqual(tu["inputTokens"], 1000)
        self.assertEqual(tu["outputTokens"], 200)
        self.assertEqual(tu["cacheReadInputTokens"], 500)
        self.assertEqual(tu["cacheCreationInputTokens"], 0)

    def test_no_token_usage_when_metadata_absent(self) -> None:
        logs = [
            {
                "id": "log-0",
                "timestamp": "2026-05-01T00:00:00Z",
                "speaker": "user",
                "type": "message",
                "content": "Hello",
                "metadata": {},
            }
        ]
        projected = self._project(logs)
        self.assertIsNone(projected[0].get("tokenUsage"))


class CanonicalLogPayloadTokenUsageTests(unittest.TestCase):
    """_canonical_log_payload emits tokenUsage from DB columns and from metadata fallback."""

    def _service(self) -> SessionTranscriptService:
        return SessionTranscriptService()

    def test_token_usage_from_db_columns(self) -> None:
        svc = self._service()
        row: dict[str, Any] = {
            "source_log_id": "log-0",
            "message_index": 0,
            "event_timestamp": "2026-05-01T00:00:00Z",
            "role": "assistant",
            "message_type": "message",
            "content": "Hi",
            "agent_name": None,
            "linked_session_id": None,
            "related_tool_call_id": None,
            "tool_name": None,
            "tool_call_id": None,
            "entry_uuid": None,
            "parent_entry_uuid": None,
            "message_id": None,
            "metadata_json": None,
            "input_tokens": 1234,
            "output_tokens": 567,
            "cache_read_input_tokens": 800,
            "cache_creation_input_tokens": 10,
        }
        payload = svc._canonical_log_payload(row)
        tu = payload.get("tokenUsage")
        self.assertIsNotNone(tu)
        self.assertEqual(tu["inputTokens"], 1234)
        self.assertEqual(tu["outputTokens"], 567)
        self.assertEqual(tu["cacheReadInputTokens"], 800)
        self.assertEqual(tu["cacheCreationInputTokens"], 10)

    def test_token_usage_null_when_no_columns_and_no_metadata(self) -> None:
        svc = self._service()
        row: dict[str, Any] = {
            "source_log_id": "log-0",
            "message_index": 0,
            "event_timestamp": "2026-05-01T00:00:00Z",
            "role": "user",
            "message_type": "message",
            "content": "Hello",
            "agent_name": None,
            "linked_session_id": None,
            "related_tool_call_id": None,
            "tool_name": None,
            "tool_call_id": None,
            "entry_uuid": None,
            "parent_entry_uuid": None,
            "message_id": None,
            "metadata_json": None,
            "input_tokens": None,
            "output_tokens": None,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
        }
        payload = svc._canonical_log_payload(row)
        self.assertIsNone(payload.get("tokenUsage"))

    def test_token_usage_fallback_from_metadata(self) -> None:
        """Pre-migration rows without dedicated columns fall back to metadata_json."""
        import json
        svc = self._service()
        metadata = {
            "inputTokens": 500,
            "outputTokens": 100,
            "cache_read_input_tokens": 200,
            "cache_creation_input_tokens": 0,
        }
        row: dict[str, Any] = {
            "source_log_id": "log-0",
            "message_index": 0,
            "event_timestamp": "2026-05-01T00:00:00Z",
            "role": "assistant",
            "message_type": "message",
            "content": "Reply",
            "agent_name": None,
            "linked_session_id": None,
            "related_tool_call_id": None,
            "tool_name": None,
            "tool_call_id": None,
            "entry_uuid": None,
            "parent_entry_uuid": None,
            "message_id": None,
            "metadata_json": json.dumps(metadata),
            # columns absent (None) → fallback to metadata
            "input_tokens": None,
            "output_tokens": None,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
        }
        payload = svc._canonical_log_payload(row)
        tu = payload.get("tokenUsage")
        self.assertIsNotNone(tu)
        self.assertEqual(tu["inputTokens"], 500)
        self.assertEqual(tu["outputTokens"], 100)

    def test_token_usage_explicit_null_in_payload(self) -> None:
        """tokenUsage key must be present and null (not absent) for messages without data."""
        svc = self._service()
        row: dict[str, Any] = {
            "source_log_id": "log-0",
            "message_index": 0,
            "event_timestamp": "2026-05-01T00:00:00Z",
            "role": "user",
            "message_type": "message",
            "content": "Hello",
            "agent_name": None,
            "linked_session_id": None,
            "related_tool_call_id": None,
            "tool_name": None,
            "tool_call_id": None,
            "entry_uuid": None,
            "parent_entry_uuid": None,
            "message_id": None,
            "metadata_json": None,
            "input_tokens": None,
            "output_tokens": None,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
        }
        payload = svc._canonical_log_payload(row)
        self.assertIn("tokenUsage", payload)
        self.assertIsNone(payload["tokenUsage"])


if __name__ == "__main__":
    unittest.main()
