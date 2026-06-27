"""Integration tests for FilesystemSource.

Uses an in-memory SQLite DB (same pattern as test_ingest_cursor_repository.py)
and a temporary directory of JSONL session files.
"""
from __future__ import annotations

import json
import logging
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import aiosqlite

from backend.application.ports.ingest import IngestCursor, SessionIngestSource
from backend.db.ingest.filesystem_source import FilesystemSource
from backend.db.repositories.ingest_cursors import SqliteIngestCursorRepository
from backend.db.sqlite_migrations import run_migrations


# ---------------------------------------------------------------------------
# Minimal JSONL fixture helpers
# ---------------------------------------------------------------------------

# The claude_code parser accepts any file with at least one valid JSON line.
# A single assistant-turn message line is sufficient to produce a non-None
# AgentSession.
_MINIMAL_LINE = json.dumps({
    "type": "assistant",
    "message": {
        "id": "msg_fixture",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "hello"}],
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    },
    "uuid": "00000000-0000-0000-0000-000000000001",
    "timestamp": "2026-05-12T10:00:00.000Z",
    "sessionId": "session-fixture-001",
    "isSidechain": False,
    "userType": "external",
    "cwd": "/tmp/project",
    "version": "1.0.0",
    "costUSD": 0.0,
})


def _write_jsonl(path: Path, session_suffix: str = "001") -> None:
    """Write a minimal valid JSONL session file at *path*."""
    line = json.dumps({
        "type": "assistant",
        "message": {
            "id": f"msg_fixture_{session_suffix}",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": f"hello from {session_suffix}"}],
            "model": "claude-sonnet-4-6",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
        "uuid": f"00000000-0000-0000-0000-{session_suffix.zfill(12)}",
        "timestamp": "2026-05-12T10:00:00.000Z",
        "sessionId": f"session-fixture-{session_suffix}",
        "isSidechain": False,
        "userType": "external",
        "cwd": "/tmp/project",
        "version": "1.0.0",
        "costUSD": 0.0,
    })
    path.write_text(line + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Base test class — shares in-memory SQLite + FilesystemSource setup
# ---------------------------------------------------------------------------

class _BaseFilesystemSourceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteIngestCursorRepository(self.db)
        self._tmpdir = TemporaryDirectory()
        self.sessions_dir = Path(self._tmpdir.name)

    async def asyncTearDown(self) -> None:
        self._tmpdir.cleanup()
        await self.db.close()

    def _make_source(self, project_id: str = "proj-fs-test") -> FilesystemSource:
        return FilesystemSource(
            sessions_dir=self.sessions_dir,
            project_id=project_id,
            cursor_repo=self.repo,
            workspace_id="default-local",
        )

    async def _fresh_cursor(self, source: FilesystemSource, project_id: str = "proj-fs-test") -> IngestCursor:
        return await self.repo.get_or_create(
            source_id=source.source_id,
            project_id=project_id,
        )

    async def _collect(self, source: FilesystemSource, cursor: IngestCursor) -> list:
        events = []
        async for event in source.stream(since=cursor):
            events.append(event)
        return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFilesystemSourceStreamBasic(_BaseFilesystemSourceTest):
    async def test_stream_yields_event_per_jsonl_file(self) -> None:
        """Two valid JSONL files → two IngestEvents with correct source_ref/source_id."""
        _write_jsonl(self.sessions_dir / "session-001.jsonl", "001")
        _write_jsonl(self.sessions_dir / "session-002.jsonl", "002")

        source = self._make_source()
        cursor = await self._fresh_cursor(source)
        events = await self._collect(source, cursor)

        self.assertEqual(len(events), 2)
        for event in events:
            self.assertTrue(
                event.source_ref.startswith("fs:"),
                f"source_ref should start with 'fs:' but got {event.source_ref!r}",
            )
        self.assertEqual(source.source_id, "filesystem")

    async def test_stream_skips_files_at_or_below_cursor(self) -> None:
        """Only files with mtime strictly greater than cursor threshold are yielded."""
        old_file = self.sessions_dir / "session-old.jsonl"
        mid_file = self.sessions_dir / "session-mid.jsonl"
        new_file = self.sessions_dir / "session-new.jsonl"

        for path, suffix in [(old_file, "old"), (mid_file, "mid"), (new_file, "new")]:
            _write_jsonl(path, suffix)

        # Deterministic mtimes: old=T+0, mid=T+10, new=T+20
        base_time = 1_000_000.0
        os.utime(old_file, (base_time, base_time))
        os.utime(mid_file, (base_time + 10, base_time + 10))
        os.utime(new_file, (base_time + 20, base_time + 20))

        # Cursor set to mid file's mtime ISO string
        from datetime import datetime, timezone
        mid_iso = datetime.fromtimestamp(base_time + 10, tz=timezone.utc).isoformat()
        cursor = IngestCursor(
            source_id="filesystem",
            project_id="proj-fs-test",
            workspace_id="default-local",
            last_cursor=mid_iso,
            last_ingest_at=None,
            error_count=0,
        )

        source = self._make_source()
        events = await self._collect(source, cursor)

        self.assertEqual(len(events), 1, f"Expected 1 event (new_file only), got {len(events)}")
        self.assertIn("session-new", events[0].source_ref)

    async def test_ack_advances_cursor_in_repository(self) -> None:
        """ack() for all events should advance the repo cursor to the latest event's cursor_value."""
        _write_jsonl(self.sessions_dir / "session-a.jsonl", "aaa")
        _write_jsonl(self.sessions_dir / "session-b.jsonl", "bbb")

        source = self._make_source()
        cursor = await self._fresh_cursor(source)
        events = await self._collect(source, cursor)

        self.assertGreater(len(events), 0)

        for event in events:
            await source.ack(event)

        latest_cursor_value = max(e.cursor_value for e in events)
        updated_cursor = await self.repo.get_or_create(
            source_id=source.source_id,
            project_id="proj-fs-test",
        )
        self.assertEqual(updated_cursor.last_cursor, latest_cursor_value)

    async def test_idempotent_rescan(self) -> None:
        """After full stream + ack, a second stream pass with the updated cursor yields zero events."""
        file_x = self.sessions_dir / "session-x.jsonl"
        file_y = self.sessions_dir / "session-y.jsonl"
        _write_jsonl(file_x, "xxx")
        _write_jsonl(file_y, "yyy")

        # Pin mtimes so the two files are strictly ordered and deterministic.
        base_time = 1_000_000.0
        os.utime(file_x, (base_time, base_time))
        os.utime(file_y, (base_time + 10, base_time + 10))

        source = self._make_source()
        cursor = await self._fresh_cursor(source)
        events = await self._collect(source, cursor)

        self.assertGreater(len(events), 0, "First pass should yield events")

        for event in events:
            await source.ack(event)

        # Second pass with updated cursor
        updated_cursor = await self.repo.get_or_create(
            source_id=source.source_id,
            project_id="proj-fs-test",
        )
        second_pass = await self._collect(source, updated_cursor)
        self.assertEqual(len(second_pass), 0, "Second pass should yield no events after full ack")

    async def test_malformed_jsonl_is_skipped_not_raised(self) -> None:
        """A file that raises during parse is skipped with a warning; valid files are still yielded.

        We trigger a WARNING by patching parse_session_file to raise for one
        specific path (simulating a corrupt/unreadable file that slips past the
        text-decode step).  The two good files must still be yielded and no
        exception may propagate out of stream().
        """
        from unittest.mock import patch

        good1 = self.sessions_dir / "good-001.jsonl"
        good2 = self.sessions_dir / "good-002.jsonl"
        bad_file = self.sessions_dir / "malformed.jsonl"
        _write_jsonl(good1, "g01")
        _write_jsonl(good2, "g02")
        # Write syntactically invalid JSON so parse returns None without raising.
        # The real warning path in FilesystemSource is when parse_session_file()
        # raises; we patch it to raise for the bad path only.
        bad_file.write_bytes(b"\xff\xfe garbage \x00\x01")

        _original_parse = __import__(
            "backend.parsers.sessions", fromlist=["parse_session_file"]
        ).parse_session_file

        def _patched_parse(path):
            if path.name == "malformed.jsonl":
                raise RuntimeError("simulated parse failure")
            return _original_parse(path)

        source = self._make_source()
        cursor = await self._fresh_cursor(source)

        with patch("backend.db.ingest.filesystem_source.parse_session_file", side_effect=_patched_parse):
            with self.assertLogs("backend.db.ingest.filesystem_source", level=logging.WARNING) as cm:
                events = await self._collect(source, cursor)

        # Should not raise; should yield the two good files
        self.assertEqual(len(events), 2)
        # At least one warning should reference the malformed file
        log_text = "\n".join(cm.output)
        self.assertIn("malformed", log_text.lower())

    async def test_source_satisfies_protocol(self) -> None:
        """FilesystemSource is a runtime-checkable SessionIngestSource."""
        source = self._make_source()
        self.assertIsInstance(source, SessionIngestSource)


if __name__ == "__main__":
    unittest.main()
