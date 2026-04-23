"""P1-006: Assert that expected Phase-1 indexes exist after migration.

Each test queries sqlite_master to confirm the index was created by
run_migrations().  Postgres parity is skipped (migration path not
in-code for Postgres at the time of Phase 1).

Run:
    backend/.venv/bin/python -m pytest backend/tests/test_phase_1_indexes.py -v
"""
from __future__ import annotations

import unittest

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


# ---------------------------------------------------------------------------
# P1-006 index assertions
# ---------------------------------------------------------------------------

class TestPhase1Indexes(unittest.IsolatedAsyncioTestCase):
    """Assert every new P1-006 index is present after migration."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        await run_migrations(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # New indexes added by P1-006 migration

    async def test_idx_features_status_updated(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_features_status_updated"),
            "Missing idx_features_status_updated on features(project_id, status, updated_at)",
        )

    async def test_idx_features_category(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_features_category"),
            "Missing idx_features_category on features(project_id, category)",
        )

    async def test_idx_features_completed_at(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_features_completed_at"),
            "Missing idx_features_completed_at on features(project_id, completed_at)",
        )

    async def test_idx_features_created_at(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_features_created_at"),
            "Missing idx_features_created_at on features(project_id, created_at)",
        )

    async def test_idx_links_feature_session(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_links_feature_session"),
            "Missing idx_links_feature_session on entity_links"
            "(source_type, source_id, target_type, link_type)",
        )

    async def test_idx_sessions_updated_at(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_sessions_updated_at"),
            "Missing idx_sessions_updated_at on sessions(project_id, updated_at)",
        )

    # Pre-existing indexes — regression guard

    async def test_preexisting_idx_features_project(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_features_project"),
            "Regression: idx_features_project was removed",
        )

    async def test_preexisting_idx_phases_feature(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_phases_feature"),
            "Regression: idx_phases_feature was removed",
        )

    async def test_preexisting_idx_links_source(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_links_source"),
            "Regression: idx_links_source was removed",
        )

    async def test_preexisting_idx_sessions_root(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_sessions_root"),
            "Regression: idx_sessions_root was removed",
        )
