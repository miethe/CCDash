"""Tests for GET /api/v1/sessions/{id}/tool-calls (itt-node-session-cost-join, AC2).

Covers ``backend.routers._client_v1_sessions.get_session_tool_calls_v1``:
  * project_id required -> HTTP 400 when absent.
  * unknown session -> HTTP 404.
  * {items, cursor, limit, nextCursor} envelope shape (same shape as
    /transcript), narrowed to entries carrying a non-null toolCall.
  * ``tool`` query param further narrows to an exact toolCall.name match.
  * redaction (agent_queries.redaction) is applied to toolCall.args/output
    before egress -- a known secret in a seeded Bash tool call must not
    survive to the response.
  * pagination: cursor round-trips and nextCursor is None on the last page.

Run as a named module:
    backend/.venv/bin/python -m pytest backend/tests/test_session_tool_calls_endpoint.py -v
"""
from __future__ import annotations

import unittest

import aiosqlite
from fastapi import HTTPException

from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.application.services.agent_queries.redaction import REDACTED_PLACEHOLDER
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations
from backend.routers._client_v1_sessions import (
    _decode_offset_cursor,
    _encode_offset_cursor,
    get_session_tool_calls_v1,
)

PROJECT_ID = "proj-alpha"
SESSION_ID = "sess-tool-calls-001"


class FakeCorePortsFactory:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._storage = LocalStorageUnitOfWork(db)

    @property
    def storage(self) -> LocalStorageUnitOfWork:
        return self._storage


def _log(idx: int, *, tool_call: dict | None = None, content: str = "") -> dict:
    return {
        "id": f"log-{idx}",
        "timestamp": f"2026-08-01T00:0{idx}:00Z",
        "speaker": "assistant",
        "type": "message",
        "content": content or f"log content {idx}",
        "agentName": None,
        "linkedSessionId": None,
        "relatedToolCallId": None,
        "metadata": {},
        "toolCall": tool_call,
    }


def _tool_call(name: str, *, args: object = "", output: object = "") -> dict:
    return {
        "id": f"tc-{name}",
        "name": name,
        "args": args,
        "output": output,
        "status": "success",
        "isError": False,
    }


class TestSessionToolCallsEndpoint(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.ports = FakeCorePortsFactory(self.db)
        self.session_repo = SqliteSessionRepository(self.db)
        await self.session_repo.upsert({"id": SESSION_ID, "status": "completed"}, PROJECT_ID)
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _seed_logs(self, logs: list[dict]) -> None:
        await self.session_repo.upsert_logs(SESSION_ID, logs, PROJECT_ID)
        await self.db.commit()

    # ── Required project_id / unknown session ────────────────────────────────

    async def test_missing_project_id_raises_400(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await get_session_tool_calls_v1(
                SESSION_ID, None, None, None, 200, None, self.ports
            )
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_unknown_session_raises_404(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await get_session_tool_calls_v1(
                "does-not-exist", PROJECT_ID, None, None, 200, None, self.ports
            )
        self.assertEqual(ctx.exception.status_code, 404)

    # ── Filtering to tool-call rows ───────────────────────────────────────────

    async def test_only_toolcall_bearing_entries_are_returned(self) -> None:
        await self._seed_logs(
            [
                _log(1, content="plain message, no tool call"),
                _log(2, tool_call=_tool_call("Read")),
                _log(3, content="another plain message"),
                _log(4, tool_call=_tool_call("Write")),
            ]
        )

        envelope = await get_session_tool_calls_v1(
            SESSION_ID, PROJECT_ID, None, None, 200, None, self.ports
        )

        names = [item["toolCall"]["name"] for item in envelope.data.items]
        self.assertEqual(names, ["Read", "Write"])

    async def test_tool_filter_narrows_to_exact_name_match(self) -> None:
        await self._seed_logs(
            [
                _log(1, tool_call=_tool_call("Read")),
                _log(2, tool_call=_tool_call("Write")),
                _log(3, tool_call=_tool_call("Read")),
            ]
        )

        envelope = await get_session_tool_calls_v1(
            SESSION_ID, PROJECT_ID, "Read", None, 200, None, self.ports
        )

        names = [item["toolCall"]["name"] for item in envelope.data.items]
        self.assertEqual(names, ["Read", "Read"])

    async def test_no_tool_calls_yields_empty_items_not_error(self) -> None:
        await self._seed_logs([_log(1, content="just a message")])

        envelope = await get_session_tool_calls_v1(
            SESSION_ID, PROJECT_ID, None, None, 200, None, self.ports
        )

        self.assertEqual(envelope.data.items, [])
        self.assertIsNone(envelope.data.nextCursor)

    # ── Envelope shape ─────────────────────────────────────────────────────────

    async def test_envelope_shape_matches_transcript_contract(self) -> None:
        await self._seed_logs([_log(1, tool_call=_tool_call("Bash"))])

        envelope = await get_session_tool_calls_v1(
            SESSION_ID, PROJECT_ID, None, None, 200, None, self.ports
        )

        self.assertEqual(envelope.data.sessionId, SESSION_ID)
        self.assertEqual(envelope.data.projectId, PROJECT_ID)
        self.assertIsInstance(envelope.data.items, list)
        self.assertIsInstance(envelope.data.cursor, str)
        self.assertEqual(envelope.data.limit, 200)
        self.assertIsNone(envelope.data.nextCursor)

    # ── Pagination ─────────────────────────────────────────────────────────────

    async def test_pagination_walks_raw_log_stream_with_next_cursor(self) -> None:
        # 3 raw log rows, all tool calls, requested with limit=1 -> 3 pages.
        await self._seed_logs(
            [
                _log(1, tool_call=_tool_call("A")),
                _log(2, tool_call=_tool_call("B")),
                _log(3, tool_call=_tool_call("C")),
            ]
        )

        page1 = await get_session_tool_calls_v1(
            SESSION_ID, PROJECT_ID, None, None, 1, None, self.ports
        )
        self.assertEqual(len(page1.data.items), 1)
        self.assertIsNotNone(page1.data.nextCursor)

        page2 = await get_session_tool_calls_v1(
            SESSION_ID, PROJECT_ID, None, page1.data.nextCursor, 1, None, self.ports
        )
        self.assertEqual(len(page2.data.items), 1)
        self.assertIsNotNone(page2.data.nextCursor)

        page3 = await get_session_tool_calls_v1(
            SESSION_ID, PROJECT_ID, None, page2.data.nextCursor, 1, None, self.ports
        )
        self.assertEqual(len(page3.data.items), 1)
        self.assertIsNone(page3.data.nextCursor)

        all_names = [
            p.data.items[0]["toolCall"]["name"] for p in (page1, page2, page3)
        ]
        self.assertEqual(all_names, ["A", "B", "C"])

    def test_cursor_encode_decode_round_trip(self) -> None:
        for offset in (0, 1, 42, 999):
            self.assertEqual(_decode_offset_cursor(_encode_offset_cursor(offset)), offset)

    def test_cursor_decode_garbage_returns_zero(self) -> None:
        self.assertEqual(_decode_offset_cursor("not-a-real-cursor"), 0)
        self.assertEqual(_decode_offset_cursor(None), 0)

    # ── Redaction ────────────────────────────────────────────────────────────

    async def test_redaction_scrubs_secret_in_bash_tool_call_args(self) -> None:
        secret = "AKIAABCDEFGHIJKLMNOP"  # matches the aws_access_key_id pattern
        # tool_args is a plain TEXT column on the legacy session_logs table
        # (see SqliteSessionRepository.upsert_logs) -- args round-trips as a
        # raw string, the same shape a real Bash tool call carries.
        await self._seed_logs(
            [
                _log(
                    1,
                    tool_call=_tool_call(
                        "Bash", args=f"export TOKEN={secret}"
                    ),
                )
            ]
        )

        envelope = await get_session_tool_calls_v1(
            SESSION_ID, PROJECT_ID, None, None, 200, None, self.ports
        )

        item = envelope.data.items[0]
        rendered = str(item["toolCall"]["args"])
        self.assertNotIn(secret, rendered)
        self.assertIn(REDACTED_PLACEHOLDER, rendered)
        self.assertGreater(envelope.data.redactedFieldCount, 0)


if __name__ == "__main__":
    unittest.main()
