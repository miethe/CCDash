"""Tests for the source_origin session filter (codex-session-ingestion-v1 blocker fix).

Verifies that the end-to-end source_origin filter chain works correctly for the
SQLite repository:

  * ``source_origin='codex'``        → only sessions with platform_type='Codex'
  * ``source_origin='unattributed'`` → only sessions with project_id='' (D2-b sentinel)
  * no ``source_origin``             → all sessions (unfiltered baseline)

SQL predicates mirror ``derive_session_source`` from
``backend/application/services/agent_queries/session_detail.py`` exactly.

Run with (NEVER unscoped — hangs):
    backend/.venv/bin/python -m pytest backend/tests/test_codex_source_filter.py -q
"""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from typing import Any

import aiosqlite

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations


# ── Helpers ──────────────────────────────────────────────────────────────────

_WS = "default-local"
_PID = "proj-abc123"


def _run(coro: Any) -> Any:
    return asyncio.get_event_loop().run_until_complete(coro)


async def _make_db() -> aiosqlite.Connection:
    """Open a temp-file DB, run full migrations, return the connection."""
    tmp = tempfile.mktemp(suffix=".db")
    db = await aiosqlite.connect(tmp)
    db.row_factory = aiosqlite.Row  # required for _row_to_dict to return dicts
    await db.execute("PRAGMA busy_timeout = 30000")
    await run_migrations(db)
    await db.commit()
    return db


async def _insert_session(
    db: aiosqlite.Connection,
    *,
    session_id: str,
    project_id: str,
    platform_type: str,
    source_ref: str | None,
) -> None:
    """Insert a minimal session row directly (avoids the 70-column upsert)."""
    await db.execute(
        """
        INSERT INTO sessions
            (id, project_id, workspace_id, platform_type, source_ref,
             created_at, updated_at, source_file)
        VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), '')
        """,
        (session_id, project_id, _WS, platform_type, source_ref),
    )
    await db.commit()


async def _seed(db: aiosqlite.Connection) -> None:
    """Seed 3 sessions covering the three distinct cases."""
    # Session 1: Codex, attributed to a real project.
    await _insert_session(
        db,
        session_id="sess-codex-attr",
        project_id=_PID,
        platform_type="Codex",
        source_ref=None,
    )
    # Session 2: Codex, unattributed (project_id='' D2-b sentinel).
    await _insert_session(
        db,
        session_id="sess-codex-unattr",
        project_id="",
        platform_type="Codex",
        source_ref=None,
    )
    # Session 3: Claude Code (filesystem), attributed to the same project.
    await _insert_session(
        db,
        session_id="sess-claude",
        project_id=_PID,
        platform_type="Claude Code",
        source_ref="fs:/home/user/.claude/projects/myproject/session.jsonl",
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestSourceOriginFilter(unittest.IsolatedAsyncioTestCase):
    """End-to-end source_origin predicate tests against the SQLite repository."""

    async def asyncSetUp(self) -> None:
        self.db = await _make_db()
        await _seed(self.db)
        self.repo = SqliteSessionRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # ── no filter ────────────────────────────────────────────────────────────

    async def test_no_filter_returns_all(self) -> None:
        rows = await self.repo.list_paginated(0, 100, project_id=None, workspace_id=_WS)
        ids = {r["id"] for r in rows}
        self.assertEqual(ids, {"sess-codex-attr", "sess-codex-unattr", "sess-claude"})

    async def test_no_filter_count_returns_all(self) -> None:
        n = await self.repo.count(project_id=None, workspace_id=_WS)
        self.assertEqual(n, 3)

    # ── source_origin='codex' ────────────────────────────────────────────────

    async def test_codex_filter_returns_only_codex_sessions(self) -> None:
        rows = await self.repo.list_paginated(
            0, 100, project_id=None,
            filters={"source_origin": "codex"},
            workspace_id=_WS,
        )
        ids = {r["id"] for r in rows}
        self.assertEqual(ids, {"sess-codex-attr", "sess-codex-unattr"})

    async def test_codex_filter_count(self) -> None:
        n = await self.repo.count(
            project_id=None,
            filters={"source_origin": "codex"},
            workspace_id=_WS,
        )
        self.assertEqual(n, 2)

    async def test_codex_filter_excludes_claude(self) -> None:
        rows = await self.repo.list_paginated(
            0, 100, project_id=None,
            filters={"source_origin": "codex"},
            workspace_id=_WS,
        )
        ids = {r["id"] for r in rows}
        self.assertNotIn("sess-claude", ids)

    # ── source_origin='unattributed' ─────────────────────────────────────────

    async def test_unattributed_filter_returns_only_empty_project_id(self) -> None:
        rows = await self.repo.list_paginated(
            0, 100, project_id=None,
            filters={"source_origin": "unattributed"},
            workspace_id=_WS,
        )
        ids = {r["id"] for r in rows}
        self.assertEqual(ids, {"sess-codex-unattr"})

    async def test_unattributed_filter_count(self) -> None:
        n = await self.repo.count(
            project_id=None,
            filters={"source_origin": "unattributed"},
            workspace_id=_WS,
        )
        self.assertEqual(n, 1)

    async def test_unattributed_ignores_project_scope(self) -> None:
        """When source_origin='unattributed', the project_id arg is overridden."""
        # Passing a real project_id should still return only the '' sentinel session,
        # not zero rows (which would happen if both predicates conflicted).
        rows = await self.repo.list_paginated(
            0, 100, project_id=_PID,
            filters={"source_origin": "unattributed"},
            workspace_id=_WS,
        )
        ids = {r["id"] for r in rows}
        self.assertEqual(ids, {"sess-codex-unattr"})

    # ── source_origin='filesystem' ───────────────────────────────────────────

    async def test_filesystem_filter_returns_only_fs_sessions(self) -> None:
        rows = await self.repo.list_paginated(
            0, 100, project_id=None,
            filters={"source_origin": "filesystem"},
            workspace_id=_WS,
        )
        ids = {r["id"] for r in rows}
        self.assertEqual(ids, {"sess-claude"})

    async def test_filesystem_filter_count(self) -> None:
        n = await self.repo.count(
            project_id=None,
            filters={"source_origin": "filesystem"},
            workspace_id=_WS,
        )
        self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
