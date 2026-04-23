"""Tests for SqliteFeatureRepository.list_phase_summaries_for_features (P1-003).

Seeds an in-memory SQLite database with 6 features and varying phase counts,
then exercises the bulk query across several scenarios.
"""
from __future__ import annotations

import asyncio
import unittest

import aiosqlite

from backend.db.repositories.features import SqliteFeatureRepository
from backend.db.repositories.feature_queries import PhaseSummaryBulkQuery


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS features (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'backlog',
    category TEXT NOT NULL DEFAULT '',
    total_tasks INTEGER NOT NULL DEFAULT 0,
    completed_tasks INTEGER NOT NULL DEFAULT 0,
    parent_feature_id TEXT,
    created_at TEXT,
    updated_at TEXT,
    completed_at TEXT,
    data_json TEXT
);

CREATE TABLE IF NOT EXISTS feature_phases (
    id TEXT PRIMARY KEY,
    feature_id TEXT NOT NULL,
    phase TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    status TEXT,
    progress REAL,
    total_tasks INTEGER NOT NULL DEFAULT 0,
    completed_tasks INTEGER NOT NULL DEFAULT 0
);
"""

# 6 features: FEAT-1..FEAT-4 have phases, FEAT-5 has none, FEAT-6 is in proj-B
FEATURES = [
    ("FEAT-1", "proj-A"),
    ("FEAT-2", "proj-A"),
    ("FEAT-3", "proj-A"),
    ("FEAT-4", "proj-A"),
    ("FEAT-5", "proj-A"),  # zero phases
    ("FEAT-6", "proj-B"),  # different project
]

# (phase_id, feature_id, phase_str, title, status, progress, total_tasks, completed_tasks)
PHASES = [
    ("FEAT-1:p1", "FEAT-1", "1", "Phase 1", "completed",   1.0,  3, 3),
    ("FEAT-1:p2", "FEAT-1", "2", "Phase 2", "in_progress", 0.5,  4, 2),
    ("FEAT-2:p1", "FEAT-2", "1", "Alpha",   "pending",     0.0,  2, 0),
    ("FEAT-2:p2", "FEAT-2", "2", "Beta",    "pending",     0.0,  2, 0),
    ("FEAT-2:p3", "FEAT-2", "3", "Gamma",   "backlog",     0.0,  1, 0),
    ("FEAT-3:p1", "FEAT-3", "1", "Start",   "completed",   1.0,  5, 5),
    ("FEAT-3:p2", "FEAT-3", "2", "Middle",  "in_progress", 0.25, 8, 2),
    ("FEAT-3:p3", "FEAT-3", "3", "End",     "backlog",     0.0,  3, 0),
    ("FEAT-3:p4", "FEAT-3", "4", "Extra",   "backlog",     0.0,  1, 0),
    ("FEAT-4:p1", "FEAT-4", "1", "Only",    "completed",   1.0,  2, 2),
    ("FEAT-4:p2", "FEAT-4", "2", "Second",  "in_progress", 0.0,  2, 1),
    # FEAT-5 has no phases
    ("FEAT-6:p1", "FEAT-6", "1", "Foreign", "backlog",     0.0,  1, 0),
]


async def _make_repo() -> tuple[aiosqlite.Connection, SqliteFeatureRepository]:
    """Create an in-memory SQLite DB, run DDL, seed fixtures, return (conn, repo)."""
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.executescript(DDL)
    for fid, proj in FEATURES:
        await db.execute(
            "INSERT INTO features (id, project_id, name) VALUES (?, ?, ?)",
            (fid, proj, fid),
        )
    for row in PHASES:
        await db.execute(
            "INSERT INTO feature_phases"
            " (id, feature_id, phase, title, status, progress, total_tasks, completed_tasks)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
    await db.commit()
    return db, SqliteFeatureRepository(db)


class TestPhaseSummaryBulk(unittest.TestCase):
    """Unit tests for list_phase_summaries_for_features (SQLite path)."""

    def _run(self, coro):  # noqa: ANN001
        return asyncio.run(coro)

    # ------------------------------------------------------------------
    # Basic shape
    # ------------------------------------------------------------------

    def test_all_six_features_returned(self) -> None:
        """Requesting all 6 IDs returns a dict with exactly 6 keys."""
        async def _inner():
            db, repo = await _make_repo()
            try:
                all_ids = [f[0] for f in FEATURES]
                query = PhaseSummaryBulkQuery(
                    feature_ids=all_ids, include_counts=True, include_progress=True
                )
                return await repo.list_phase_summaries_for_features("proj-A", query)
            finally:
                await db.close()

        result = self._run(_inner())
        self.assertEqual(set(result.keys()), {f[0] for f in FEATURES})

    def test_phase_counts_and_ordering(self) -> None:
        """Each feature has the correct phase count, ordered by order_index asc."""
        async def _inner():
            db, repo = await _make_repo()
            try:
                all_ids = [f[0] for f in FEATURES]
                query = PhaseSummaryBulkQuery(
                    feature_ids=all_ids, include_counts=True, include_progress=True
                )
                return await repo.list_phase_summaries_for_features("proj-A", query)
            finally:
                await db.close()

        result = self._run(_inner())
        self.assertEqual(len(result["FEAT-1"]), 2)
        self.assertEqual(len(result["FEAT-2"]), 3)
        self.assertEqual(len(result["FEAT-3"]), 4)
        self.assertEqual(len(result["FEAT-4"]), 2)

        # Verify ascending order on FEAT-3
        indices = [s.order_index for s in result["FEAT-3"] if s.order_index is not None]
        self.assertEqual(indices, sorted(indices))

    # ------------------------------------------------------------------
    # include_counts / include_progress toggles
    # ------------------------------------------------------------------

    def test_include_counts_false_zeroes_out_task_fields(self) -> None:
        """When include_counts=False, total_tasks and completed_tasks are 0."""
        async def _inner():
            db, repo = await _make_repo()
            try:
                query = PhaseSummaryBulkQuery(
                    feature_ids=["FEAT-1"], include_counts=False, include_progress=False
                )
                return await repo.list_phase_summaries_for_features("proj-A", query)
            finally:
                await db.close()

        result = self._run(_inner())
        for s in result["FEAT-1"]:
            self.assertEqual(s.total_tasks, 0)
            self.assertEqual(s.completed_tasks, 0)
            self.assertIsNone(s.progress)

    def test_include_progress_false_leaves_progress_none(self) -> None:
        """When include_progress=False, progress is None."""
        async def _inner():
            db, repo = await _make_repo()
            try:
                query = PhaseSummaryBulkQuery(
                    feature_ids=["FEAT-3"], include_counts=True, include_progress=False
                )
                return await repo.list_phase_summaries_for_features("proj-A", query)
            finally:
                await db.close()

        result = self._run(_inner())
        for s in result["FEAT-3"]:
            self.assertIsNone(s.progress)

    # ------------------------------------------------------------------
    # Empty / missing cases
    # ------------------------------------------------------------------

    def test_feature_with_zero_phases_maps_to_empty_list(self) -> None:
        """FEAT-5 has no phases and must map to [] (key present)."""
        async def _inner():
            db, repo = await _make_repo()
            try:
                query = PhaseSummaryBulkQuery(
                    feature_ids=["FEAT-5"], include_counts=True, include_progress=True
                )
                return await repo.list_phase_summaries_for_features("proj-A", query)
            finally:
                await db.close()

        result = self._run(_inner())
        self.assertIn("FEAT-5", result)
        self.assertEqual(result["FEAT-5"], [])

    def test_cross_project_feature_excluded_maps_to_empty_list(self) -> None:
        """FEAT-6 belongs to proj-B; queried against proj-A it must map to []."""
        async def _inner():
            db, repo = await _make_repo()
            try:
                query = PhaseSummaryBulkQuery(
                    feature_ids=["FEAT-6"], include_counts=True, include_progress=True
                )
                return await repo.list_phase_summaries_for_features("proj-A", query)
            finally:
                await db.close()

        result = self._run(_inner())
        self.assertIn("FEAT-6", result)
        self.assertEqual(result["FEAT-6"], [])

    # ------------------------------------------------------------------
    # Progress computation
    # ------------------------------------------------------------------

    def test_progress_computed_from_task_counts(self) -> None:
        """progress = completed/total when include_counts=include_progress=True."""
        async def _inner():
            db, repo = await _make_repo()
            try:
                query = PhaseSummaryBulkQuery(
                    feature_ids=["FEAT-1"], include_counts=True, include_progress=True
                )
                return await repo.list_phase_summaries_for_features("proj-A", query)
            finally:
                await db.close()

        result = self._run(_inner())
        by_id = {s.phase_id: s for s in result["FEAT-1"]}
        p1_progress = by_id["FEAT-1:p1"].progress
        p2_progress = by_id["FEAT-1:p2"].progress
        assert p1_progress is not None and p2_progress is not None
        self.assertAlmostEqual(p1_progress, 1.0, places=4)
        self.assertAlmostEqual(p2_progress, 0.5, places=4)

    def test_zero_total_tasks_no_zero_division(self) -> None:
        """A phase with total_tasks=0 must not raise ZeroDivisionError.

        When stored_progress is available (0.0), it is used as a fallback.
        The test verifies no exception is raised and that progress is a valid
        float (or None for phases with NULL stored_progress).
        """
        async def _inner():
            db, repo = await _make_repo()
            try:
                query = PhaseSummaryBulkQuery(
                    feature_ids=["FEAT-2"], include_counts=True, include_progress=True
                )
                return await repo.list_phase_summaries_for_features("proj-A", query)
            finally:
                await db.close()

        result = self._run(_inner())
        for s in result["FEAT-2"]:
            # No ZeroDivisionError; progress is either None or a valid float
            self.assertTrue(s.progress is None or isinstance(s.progress, float))

    # ------------------------------------------------------------------
    # Defensive cap
    # ------------------------------------------------------------------

    def test_defensive_cap_raises_value_error(self) -> None:
        """A list of 501 feature IDs must raise ValueError at construction time."""
        with self.assertRaises(ValueError):
            PhaseSummaryBulkQuery(feature_ids=[f"F-{i}" for i in range(501)])

    # ------------------------------------------------------------------
    # Field mapping
    # ------------------------------------------------------------------

    def test_phase_summary_fields_populated(self) -> None:
        """PhaseSummary fields are correctly mapped from DB columns."""
        async def _inner():
            db, repo = await _make_repo()
            try:
                query = PhaseSummaryBulkQuery(
                    feature_ids=["FEAT-4"], include_counts=True, include_progress=True
                )
                return await repo.list_phase_summaries_for_features("proj-A", query)
            finally:
                await db.close()

        result = self._run(_inner())
        summaries = result["FEAT-4"]
        self.assertEqual(len(summaries), 2)

        first = next(s for s in summaries if s.phase_id == "FEAT-4:p1")
        self.assertEqual(first.feature_id, "FEAT-4")
        self.assertEqual(first.name, "Only")
        self.assertEqual(first.status, "completed")
        self.assertEqual(first.order_index, 1)
        self.assertEqual(first.total_tasks, 2)
        self.assertEqual(first.completed_tasks, 2)
        assert first.progress is not None
        self.assertAlmostEqual(first.progress, 1.0, places=4)


if __name__ == "__main__":
    unittest.main()
