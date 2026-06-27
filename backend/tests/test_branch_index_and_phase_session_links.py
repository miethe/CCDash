"""Tests for T1-004: branch-aware planning intelligence.

Covers:
  1. idx_sessions_git_branch index existence and column coverage after migration.
  2. IF NOT EXISTS guard: migration runs cleanly twice (idempotent).
  3. SqliteFeatureSessionRepository.list_sessions_by_phase:
       - Returns correct sessions for a seeded fixture with phase_hints.
       - Respects the cap of 20 sessions per phase.
  4. PhaseContextItem.linked_sessions_by_phase is None when no sessions match.
  5. SessionLink DTO fields are correctly populated.

Run:
    backend/.venv/bin/python -m pytest backend/tests/test_branch_index_and_phase_session_links.py -v
"""
from __future__ import annotations

import json
import unittest
from typing import Any

import aiosqlite

from backend.db.sqlite_migrations import run_migrations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _index_exists(db: aiosqlite.Connection, index_name: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    ) as cur:
        return await cur.fetchone() is not None


async def _index_covers_columns(
    db: aiosqlite.Connection, index_name: str, *expected_columns: str
) -> bool:
    async with db.execute(f"PRAGMA index_info({index_name!r})") as cur:
        rows = await cur.fetchall()
    actual_columns = {row[2] for row in rows}
    return set(expected_columns) <= actual_columns


async def _insert_session(
    db: aiosqlite.Connection,
    session_id: str,
    project_id: str,
    git_branch: str = "",
    started_at: str = "2026-06-04T10:00:00",
    status: str = "completed",
    forensics: dict[str, Any] | None = None,
) -> None:
    forensics_json = json.dumps(forensics or {})
    await db.execute(
        """
        INSERT OR IGNORE INTO sessions (
            id, project_id, source_file, created_at, updated_at,
            git_branch, started_at, status, session_forensics_json
        ) VALUES (?, ?, ?, datetime('now'), datetime('now'), ?, ?, ?, ?)
        """,
        (
            session_id,
            project_id,
            f"/path/{session_id}.jsonl",
            git_branch,
            started_at,
            status,
            forensics_json,
        ),
    )


async def _insert_entity_link(
    db: aiosqlite.Connection,
    feature_id: str,
    session_id: str,
    project_id: str,
) -> None:
    await db.execute(
        """
        INSERT OR IGNORE INTO entity_links (
            source_type, source_id, target_type, target_id,
            link_type, created_at, project_id
        ) VALUES ('feature', ?, 'session', ?, 'related', datetime('now'), ?)
        """,
        (feature_id, session_id, project_id),
    )


# ---------------------------------------------------------------------------
# 1. Index existence and column coverage
# ---------------------------------------------------------------------------


class TestBranchIndexMigration(unittest.IsolatedAsyncioTestCase):
    """idx_sessions_git_branch must exist and cover (git_branch, project_id)."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        await run_migrations(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_idx_sessions_git_branch_exists(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_sessions_git_branch"),
            "Missing idx_sessions_git_branch on sessions(git_branch, project_id)",
        )

    async def test_idx_sessions_git_branch_covers_git_branch_column(self) -> None:
        self.assertTrue(
            await _index_covers_columns(self.db, "idx_sessions_git_branch", "git_branch"),
            "idx_sessions_git_branch does not cover git_branch",
        )

    async def test_idx_sessions_git_branch_covers_project_id_column(self) -> None:
        self.assertTrue(
            await _index_covers_columns(self.db, "idx_sessions_git_branch", "project_id"),
            "idx_sessions_git_branch does not cover project_id",
        )


# ---------------------------------------------------------------------------
# 2. IF NOT EXISTS guard: running migration twice must not raise
# ---------------------------------------------------------------------------


class TestBranchIndexIdempotency(unittest.IsolatedAsyncioTestCase):
    """Running run_migrations twice must not raise (IF NOT EXISTS guard)."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_double_migration_does_not_raise(self) -> None:
        await run_migrations(self.db)
        # Second run: should be a clean no-op
        await run_migrations(self.db)
        # Index must still exist after the second run
        self.assertTrue(
            await _index_exists(self.db, "idx_sessions_git_branch"),
            "idx_sessions_git_branch missing after second migration run",
        )


# ---------------------------------------------------------------------------
# 3 & 4. list_sessions_by_phase fixture tests
# ---------------------------------------------------------------------------


class TestListSessionsByPhase(unittest.IsolatedAsyncioTestCase):
    """list_sessions_by_phase returns correct sessions using phase_hints."""

    PROJECT_ID = "proj-phase-test"
    FEATURE_ID = "feat-001"

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        # Session 1 — linked to feature, has Phase 2 hint (camelCase key)
        await _insert_session(
            self.db,
            session_id="sess-phase2-a",
            project_id=self.PROJECT_ID,
            git_branch="feat/branch-aware",
            started_at="2026-06-04T09:00:00",
            forensics={"phaseHints": ["Phase 2"]},
        )
        await _insert_entity_link(self.db, self.FEATURE_ID, "sess-phase2-a", self.PROJECT_ID)

        # Session 2 — linked to feature, has Phase 2 hint (snake_case key)
        await _insert_session(
            self.db,
            session_id="sess-phase2-b",
            project_id=self.PROJECT_ID,
            git_branch="feat/branch-aware",
            started_at="2026-06-04T08:00:00",
            forensics={"phase_hints": ["Phase 2 - implementation"]},
        )
        await _insert_entity_link(self.db, self.FEATURE_ID, "sess-phase2-b", self.PROJECT_ID)

        # Session 3 — linked to feature, has Phase 1 hint — should NOT appear in phase 2 query
        await _insert_session(
            self.db,
            session_id="sess-phase1",
            project_id=self.PROJECT_ID,
            git_branch="main",
            started_at="2026-06-03T10:00:00",
            forensics={"phaseHints": ["Phase 1"]},
        )
        await _insert_entity_link(self.db, self.FEATURE_ID, "sess-phase1", self.PROJECT_ID)

        # Session 4 — linked to feature, no phase hints — should NOT appear
        await _insert_session(
            self.db,
            session_id="sess-nohints",
            project_id=self.PROJECT_ID,
            forensics={},
        )
        await _insert_entity_link(self.db, self.FEATURE_ID, "sess-nohints", self.PROJECT_ID)

        # Session 5 — NOT linked to feature — should NOT appear
        await _insert_session(
            self.db,
            session_id="sess-unlinked",
            project_id=self.PROJECT_ID,
            forensics={"phaseHints": ["Phase 2"]},
        )

        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _repo(self):
        from backend.db.repositories.feature_sessions import SqliteFeatureSessionRepository
        return SqliteFeatureSessionRepository(self.db)

    async def test_phase2_returns_both_phase2_sessions(self) -> None:
        repo = await self._repo()
        rows = await repo.list_sessions_by_phase(self.PROJECT_ID, self.FEATURE_ID, 2)
        session_ids = {r["session_id"] for r in rows}
        self.assertIn("sess-phase2-a", session_ids, "sess-phase2-a not in phase 2 results")
        self.assertIn("sess-phase2-b", session_ids, "sess-phase2-b not in phase 2 results")

    async def test_phase2_excludes_phase1_sessions(self) -> None:
        repo = await self._repo()
        rows = await repo.list_sessions_by_phase(self.PROJECT_ID, self.FEATURE_ID, 2)
        session_ids = {r["session_id"] for r in rows}
        self.assertNotIn("sess-phase1", session_ids, "sess-phase1 should not appear in phase 2")

    async def test_phase2_excludes_sessions_without_hints(self) -> None:
        repo = await self._repo()
        rows = await repo.list_sessions_by_phase(self.PROJECT_ID, self.FEATURE_ID, 2)
        session_ids = {r["session_id"] for r in rows}
        self.assertNotIn("sess-nohints", session_ids, "nohints session should not appear")

    async def test_phase2_excludes_unlinked_sessions(self) -> None:
        repo = await self._repo()
        rows = await repo.list_sessions_by_phase(self.PROJECT_ID, self.FEATURE_ID, 2)
        session_ids = {r["session_id"] for r in rows}
        self.assertNotIn("sess-unlinked", session_ids, "unlinked session should not appear")

    async def test_phase1_returns_only_phase1_session(self) -> None:
        repo = await self._repo()
        rows = await repo.list_sessions_by_phase(self.PROJECT_ID, self.FEATURE_ID, 1)
        session_ids = {r["session_id"] for r in rows}
        self.assertIn("sess-phase1", session_ids, "sess-phase1 not in phase 1 results")
        self.assertNotIn("sess-phase2-a", session_ids, "phase2 session appeared in phase 1")

    async def test_no_linked_sessions_returns_empty_list(self) -> None:
        repo = await self._repo()
        rows = await repo.list_sessions_by_phase(self.PROJECT_ID, "nonexistent-feature", 2)
        self.assertEqual(rows, [], "Expected empty list for unknown feature")

    async def test_unknown_phase_returns_empty_list(self) -> None:
        repo = await self._repo()
        rows = await repo.list_sessions_by_phase(self.PROJECT_ID, self.FEATURE_ID, 99)
        self.assertEqual(rows, [], "Expected empty list for nonexistent phase number")


# ---------------------------------------------------------------------------
# 5. Cap enforcement: at most 20 sessions per phase
# ---------------------------------------------------------------------------


class TestListSessionsByPhaseCap(unittest.IsolatedAsyncioTestCase):
    """list_sessions_by_phase must return at most 20 sessions regardless of
    how many are seeded."""

    PROJECT_ID = "proj-cap-test"
    FEATURE_ID = "feat-cap"
    SESSION_COUNT = 30  # more than the cap of 20

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        for i in range(self.SESSION_COUNT):
            sid = f"sess-cap-{i:03d}"
            await _insert_session(
                self.db,
                session_id=sid,
                project_id=self.PROJECT_ID,
                started_at=f"2026-06-04T{(i % 24):02d}:00:00",
                forensics={"phaseHints": ["Phase 3"]},
            )
            await _insert_entity_link(self.db, self.FEATURE_ID, sid, self.PROJECT_ID)
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_cap_of_20_enforced(self) -> None:
        from backend.db.repositories.feature_sessions import SqliteFeatureSessionRepository
        repo = SqliteFeatureSessionRepository(self.db)
        rows = await repo.list_sessions_by_phase(self.PROJECT_ID, self.FEATURE_ID, 3)
        self.assertLessEqual(
            len(rows),
            20,
            f"Expected at most 20 rows; got {len(rows)}",
        )

    async def test_cap_returns_20_when_30_available(self) -> None:
        from backend.db.repositories.feature_sessions import SqliteFeatureSessionRepository
        repo = SqliteFeatureSessionRepository(self.db)
        rows = await repo.list_sessions_by_phase(self.PROJECT_ID, self.FEATURE_ID, 3)
        self.assertEqual(
            len(rows),
            20,
            f"Expected exactly 20 rows; got {len(rows)}",
        )


# ---------------------------------------------------------------------------
# 6. PhaseContextItem.linked_sessions_by_phase is None when no results
# ---------------------------------------------------------------------------


class TestPhaseContextItemLinkedSessionsNone(unittest.IsolatedAsyncioTestCase):
    """linked_sessions_by_phase must be None when the query returns no sessions."""

    async def test_field_defaults_to_none(self) -> None:
        from backend.application.services.agent_queries.models import PhaseContextItem
        item = PhaseContextItem()
        self.assertIsNone(
            item.linked_sessions_by_phase,
            "linked_sessions_by_phase must default to None",
        )

    async def test_field_accepts_dict_value(self) -> None:
        from backend.application.services.agent_queries.models import (
            PhaseContextItem,
            SessionLink,
        )
        link = SessionLink(
            session_id="sess-xyz",
            agent_name="sonnet-4-6",
            start_time="2026-06-04T10:00:00",
            transcript_href="#/sessions/sess-xyz",
        )
        item = PhaseContextItem(linked_sessions_by_phase={2: [link]})
        self.assertIsNotNone(item.linked_sessions_by_phase)
        assert item.linked_sessions_by_phase is not None
        self.assertIn(2, item.linked_sessions_by_phase)
        self.assertEqual(item.linked_sessions_by_phase[2][0].session_id, "sess-xyz")

    async def test_session_link_fields(self) -> None:
        from backend.application.services.agent_queries.models import SessionLink
        link = SessionLink(
            session_id="sess-abc",
            agent_name="claude-opus",
            start_time="2026-06-04T09:30:00",
            transcript_href="#/sessions/sess-abc",
        )
        self.assertEqual(link.session_id, "sess-abc")
        self.assertEqual(link.agent_name, "claude-opus")
        self.assertEqual(link.start_time, "2026-06-04T09:30:00")
        self.assertEqual(link.transcript_href, "#/sessions/sess-abc")

    async def test_session_link_optional_fields_default_none(self) -> None:
        from backend.application.services.agent_queries.models import SessionLink
        link = SessionLink(session_id="sess-minimal")
        self.assertIsNone(link.agent_name)
        self.assertIsNone(link.start_time)
        self.assertIsNone(link.transcript_href)
