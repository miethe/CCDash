"""Tests for the cold-start backfill scan (node_01M1S7WBNENWWQKETMAD6FHWQ4).

``iter_changed_files`` (watchfiles-backed or mtime-poll fallback) only ever
yields a path on a create/modify EVENT — a session file that already existed
before the daemon started, and has not been touched since, is otherwise never
seen. This is what made a dormant session under a nested project subdirectory
invisible regardless of that subdirectory's identity. ``_backfill_existing_sessions``
closes that gap with a one-time recursive scan run before the tail coroutine
starts; ``_mtime_poll``'s glob is switched to ``rglob`` for the same reason.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from ccdash_cli.daemon import runner as _runner
from ccdash_cli.daemon.config import DaemonConfig
from ccdash_cli.daemon.wal import WalBuffer


def _make_config(tmp_path: Path) -> DaemonConfig:
    return DaemonConfig(
        server_url="http://testserver",
        token="test-token",
        project_id="proj-1",
        sessions_dir=tmp_path / "sessions",
        flush_interval_seconds=5.0,
        max_batch_events=100,
        buffer_root=tmp_path / "buffer",
        deadletter_root=tmp_path / "deadletter",
        status_path=tmp_path / "daemon.status",
        max_retries=3,
    )


class _FakeSession:
    """Stand-in for the parsed AgentSession model."""

    def __init__(self, session_id: str) -> None:
        self._id = session_id

    def model_dump(self) -> dict:
        return {"id": self._id}


def test_backfill_scan_finds_nested_project_subdirectories(tmp_path: Path) -> None:
    """A pre-existing file two directories deep is discovered and enqueued.

    Mirrors the real layout: sessions_dir/<project-slug>/<session-id>.jsonl,
    with the file's mtime NEVER touched after creation (i.e. never fired a
    watchfiles/mtime-poll change event).
    """
    config = _make_config(tmp_path)
    project_dir = config.sessions_dir / "-some-nested-project-worktree"
    project_dir.mkdir(parents=True)
    session_file = project_dir / "a0ac7283-ef53-4b20-bf58-9ce69a95a5fa.jsonl"
    session_file.write_text('{"type": "user"}\n')

    wal = WalBuffer(config.buffer_root)
    queue: list[dict] = []

    def _fake_parse(path: Path):
        assert path == session_file
        return _FakeSession("a0ac7283-ef53-4b20-bf58-9ce69a95a5fa")

    with patch.object(_runner, "_import_parse_session_file", return_value=_fake_parse):
        asyncio.run(_runner._backfill_existing_sessions(config, wal, queue))

    assert len(queue) == 1
    assert queue[0]["payload"]["id"] == "a0ac7283-ef53-4b20-bf58-9ce69a95a5fa"


def test_backfill_scan_no_files_is_a_noop(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.sessions_dir.mkdir(parents=True)
    wal = WalBuffer(config.buffer_root)
    queue: list[dict] = []

    with patch.object(
        _runner, "_import_parse_session_file", return_value=lambda p: None
    ):
        asyncio.run(_runner._backfill_existing_sessions(config, wal, queue))

    assert queue == []


def test_backfill_scan_missing_import_is_non_fatal(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    wal = WalBuffer(config.buffer_root)
    queue: list[dict] = []

    with patch.object(
        _runner, "_import_parse_session_file", side_effect=ImportError("no backend")
    ):
        # Must not raise.
        asyncio.run(_runner._backfill_existing_sessions(config, wal, queue))

    assert queue == []


def test_mtime_poll_recurses_into_project_subdirectories(tmp_path: Path) -> None:
    """The mtime-poll fallback must not miss files under a subdirectory."""
    from ccdash_cli.daemon.tail import _mtime_poll

    sessions_dir = tmp_path / "sessions"
    nested = sessions_dir / "-some-project"
    nested.mkdir(parents=True)
    (nested / "session-1.jsonl").write_text('{"type": "user"}\n')

    async def _collect_first() -> Path:
        async for path in _mtime_poll(sessions_dir, poll_interval=0.01):
            return path
        raise AssertionError("no path yielded")

    found = asyncio.run(asyncio.wait_for(_collect_first(), timeout=2.0))
    assert found == nested / "session-1.jsonl"
