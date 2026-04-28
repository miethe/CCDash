"""Assert that the three composite indexes added for query-gap remediation exist after migration.

Each test queries sqlite_master to confirm the index was created by run_migrations().
Covers:
  - idx_sessions_conversation_family  ON sessions(conversation_family_id)
  - idx_features_project_status       ON features(project_id, status)
  - idx_phases_feature_status         ON feature_phases(feature_id, status)

Run:
    backend/.venv/bin/python -m pytest backend/tests/test_composite_index_migration.py -v
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


async def _index_covers_columns(
    db: aiosqlite.Connection, index_name: str, *expected_columns: str
) -> bool:
    """Return True if all expected_columns appear in the index's PRAGMA info."""
    async with db.execute(f"PRAGMA index_info({index_name!r})") as cur:
        rows = await cur.fetchall()
    actual_columns = {row[2] for row in rows}  # column (2) is the name
    return set(expected_columns) <= actual_columns


# ---------------------------------------------------------------------------
# New composite index assertions
# ---------------------------------------------------------------------------

class TestCompositeIndexMigration(unittest.IsolatedAsyncioTestCase):
    """Verify that all three gap-remediation indexes are present after migration."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        await run_migrations(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # --- idx_sessions_conversation_family ---

    async def test_idx_sessions_conversation_family_exists(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_sessions_conversation_family"),
            "Missing idx_sessions_conversation_family on sessions(conversation_family_id)",
        )

    async def test_idx_sessions_conversation_family_covers_column(self) -> None:
        self.assertTrue(
            await _index_covers_columns(
                self.db, "idx_sessions_conversation_family", "conversation_family_id"
            ),
            "idx_sessions_conversation_family does not cover conversation_family_id",
        )

    # --- idx_features_project_status ---

    async def test_idx_features_project_status_exists(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_features_project_status"),
            "Missing idx_features_project_status on features(project_id, status)",
        )

    async def test_idx_features_project_status_covers_columns(self) -> None:
        self.assertTrue(
            await _index_covers_columns(
                self.db, "idx_features_project_status", "project_id", "status"
            ),
            "idx_features_project_status does not cover (project_id, status)",
        )

    # --- idx_phases_feature_status ---

    async def test_idx_phases_feature_status_exists(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_phases_feature_status"),
            "Missing idx_phases_feature_status on feature_phases(feature_id, status)",
        )

    async def test_idx_phases_feature_status_covers_columns(self) -> None:
        self.assertTrue(
            await _index_covers_columns(
                self.db, "idx_phases_feature_status", "feature_id", "status"
            ),
            "idx_phases_feature_status does not cover (feature_id, status)",
        )

    # --- Regression guard: pre-existing single-column indexes must still exist ---

    async def test_preexisting_idx_features_project_not_removed(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_features_project"),
            "Regression: idx_features_project was removed",
        )

    async def test_preexisting_idx_phases_feature_not_removed(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_phases_feature"),
            "Regression: idx_phases_feature was removed",
        )

    async def test_preexisting_idx_sessions_family_not_removed(self) -> None:
        self.assertTrue(
            await _index_exists(self.db, "idx_sessions_family"),
            "Regression: idx_sessions_family was removed",
        )
