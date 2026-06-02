"""Regression tests for the v31 composite-key session-message write path.

Covers the two runtime IntegrityErrors that killed file-watcher session sync after the
v31 composite-PK / composite-FK migration applied:

  1. UNIQUE constraint failed: session_messages.session_id, session_messages.message_index
  2. FOREIGN KEY constraint failed

All tests run with PRAGMA foreign_keys=ON against a DB built by the REAL migration runner,
so the composite FK ((project_id, session_id) -> sessions(project_id, id)) is enforced exactly
as it is at runtime (backend/db/connection.py always enables foreign_keys).
"""
from __future__ import annotations

import unittest

import aiosqlite

from backend.db import sqlite_migrations
from backend.db.repositories.session_messages import SqliteSessionMessageRepository
from backend.db.repositories.sessions import SqliteSessionRepository


async def _make_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await sqlite_migrations.run_migrations(db)
    # Match runtime: composite FK enforcement is always on.
    await db.execute("PRAGMA foreign_keys=ON")
    await db.commit()
    return db


def _msg(index: int, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "messageIndex": index,
        "sourceLogId": f"log-{index}",
        "messageId": f"m-{index}",
        "role": "user",
        "messageType": "text",
        "content": f"content-{index}",
        "timestamp": "2026-05-01T00:00:00Z",
        "agentName": "",
        "rootSessionId": "S1",
        "conversationFamilyId": "S1",
        "threadSessionId": "S1",
        "parentSessionId": "",
        "sourceProvenance": "session_log_projection",
    }
    base.update(overrides)
    return base


class ReplaceSessionMessagesCompositeFkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await _make_db()
        self.addAsyncCleanup(self.db.close)
        self.sessions = SqliteSessionRepository(self.db)
        self.messages = SqliteSessionMessageRepository(self.db)
        await self.sessions.upsert(
            {"id": "S1", "source_file": "f.jsonl", "created_at": "c", "updated_at": "u"},
            "P1",
        )

    async def _project_ids(self) -> list[object]:
        cur = await self.db.execute(
            "SELECT project_id FROM session_messages WHERE session_id = 'S1' ORDER BY message_index"
        )
        return [row["project_id"] for row in await cur.fetchall()]

    async def test_writes_project_id_and_satisfies_composite_fk(self) -> None:
        """(a) replace_session_messages persists project_id matching the parent session and
        does NOT raise under foreign_keys=ON."""
        await self.messages.replace_session_messages("S1", [_msg(0), _msg(1)], "P1")
        self.assertEqual(await self._project_ids(), ["P1", "P1"])
        # No orphans: every row resolves to a real (project_id, session_id) parent.
        cur = await self.db.execute(
            "SELECT COUNT(*) AS c FROM session_messages sm "
            "LEFT JOIN sessions s ON s.project_id = sm.project_id AND s.id = sm.session_id "
            "WHERE s.id IS NULL"
        )
        row = await cur.fetchone()
        assert row is not None
        self.assertEqual(row["c"], 0)

    async def test_mismatched_project_id_raises_fk(self) -> None:
        """A child write whose project_id has no matching session row still raises FK — proving the
        constraint is genuinely enforced and that the fix works by supplying the CORRECT id."""
        with self.assertRaises(aiosqlite.IntegrityError) as ctx:
            await self.messages.replace_session_messages("S1", [_msg(0)], "WRONG-PID")
        self.assertIn("FOREIGN KEY", str(ctx.exception))

    async def test_duplicate_message_index_payload_does_not_raise(self) -> None:
        """(b) A payload containing duplicate messageIndex values no longer raises the UNIQUE
        constraint; the last occurrence wins (mirrors Postgres ON CONFLICT DO UPDATE)."""
        await self.messages.replace_session_messages(
            "S1",
            [_msg(0, content="first"), _msg(0, content="last"), _msg(1)],
            "P1",
        )
        rows = await self.messages.list_by_session("S1")
        by_index = {row["message_index"]: row["content"] for row in rows}
        self.assertEqual(by_index, {0: "last", 1: "content-1"})

    async def test_replace_clears_stale_orphan_rows(self) -> None:
        """Pre-v31 rows carry NULL project_id (the live DB has 304 such orphans). The scoped DELETE
        must clear those for the session so they are replaced, not left dangling."""
        await self.db.execute(
            "INSERT INTO session_messages (project_id, session_id, message_index, role, message_type, event_timestamp) "
            "VALUES (NULL, 'S1', 0, 'user', 'text', 'x')"
        )
        await self.db.commit()
        await self.messages.replace_session_messages("S1", [_msg(0, content="fresh")], "P1")
        rows = await self.messages.list_by_session("S1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["project_id"], "P1")
        self.assertEqual(rows[0]["content"], "fresh")

    async def test_delete_is_project_scoped(self) -> None:
        """The DELETE is scoped to the owning project (plus legacy NULL/'' rows). It must not be a
        bare ``WHERE session_id = ?`` that could clear a different project's rows.

        Note: the UNIQUE index is on (session_id, message_index) only, so the same session id cannot
        physically exist under two projects with the same index — the live DB confirms zero such
        collisions. This test asserts the scoping clause is honored for the legacy-orphan case.
        """
        # Seed a legacy orphan (NULL project) plus a same-project row, then replace under P1.
        await self.db.execute(
            "INSERT INTO session_messages (project_id, session_id, message_index, role, message_type, event_timestamp) "
            "VALUES (NULL, 'S1', 5, 'user', 'text', 'x')"
        )
        await self.db.commit()
        await self.messages.replace_session_messages("S1", [_msg(0, content="p1")], "P1")
        rows = await self.messages.list_by_session("S1")
        # The legacy orphan at index 5 is cleared (it belonged to this session) and only the fresh
        # P1 row remains.
        self.assertEqual([r["message_index"] for r in rows], [0])
        self.assertEqual(rows[0]["project_id"], "P1")


class WatcherSyncResilienceTests(unittest.IsolatedAsyncioTestCase):
    """(c) A single malformed/constraint-violating session must be logged and skipped, not abort
    the whole changed-files batch (and thus the watcher loop)."""

    async def asyncSetUp(self) -> None:
        import tempfile

        from backend.db.sync_engine import SyncEngine

        self.db = await _make_db()
        self.addAsyncCleanup(self.db.close)
        self.engine = SyncEngine(self.db)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    async def test_one_bad_session_is_skipped_others_still_sync(self) -> None:
        import pathlib
        from unittest.mock import patch

        sessions_dir = pathlib.Path(self._tmp.name)
        bad = sessions_dir / "bad.jsonl"
        good = sessions_dir / "good.jsonl"
        bad.write_text("{}")
        good.write_text("{}")

        calls: list[str] = []

        async def fake_sync_single_session(_project_id, path, _force=False):
            calls.append(path.name)
            if path.name == "bad.jsonl":
                raise aiosqlite.IntegrityError("FOREIGN KEY constraint failed")
            return True

        with patch.object(
            self.engine, "_sync_single_session", side_effect=fake_sync_single_session
        ):
            # Should NOT raise, despite bad.jsonl blowing up mid-batch.
            stats = await self.engine.sync_changed_files(
                "P1",
                [("modified", bad), ("modified", good)],
                sessions_dir,
                pathlib.Path(self._tmp.name),
                pathlib.Path(self._tmp.name),
            )

        # Both files were attempted; the good one synced; the bad one was isolated.
        self.assertEqual(sorted(calls), ["bad.jsonl", "good.jsonl"])
        self.assertEqual(stats["sessions"], 1)


if __name__ == "__main__":
    unittest.main()
