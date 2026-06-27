"""Regression tests for analytics scope split (v33).

Asserts that project-scope and feature-scope analytics rows are distinct,
that within-scope upsert deduplication works correctly, and that
get_latest_entries / get_trends honour the scope parameter.
"""
from __future__ import annotations

import unittest

import aiosqlite

from backend.db.repositories.analytics import SqliteAnalyticsRepository
from backend.db.sqlite_migrations import run_migrations

# Two distinct ISO-8601 dates used in trend tests (different calendar days).
DAY1 = "2026-06-01T10:00:00+00:00"
DAY2 = "2026-06-02T10:00:00+00:00"
PROJECT_ID = "P"
FEATURE_ID = "F1"
METRIC = "session_count"


class AnalyticsScopeSplitTest(unittest.IsolatedAsyncioTestCase):
    """End-to-end scope split assertions against the real v33 migration."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteAnalyticsRepository(self.db)

        # Confirm metric_types seeded (needed for FK if enforced)
        async with self.db.execute("SELECT id FROM metric_types LIMIT 1") as cur:
            row = await cur.fetchone()
        # Use the metric name string directly; SQLite repo accepts it.
        self.metric = METRIC

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    def _entry(
        self,
        value: float,
        captured_at: str = DAY1,
        *,
        scope: str = "project",
        scope_id: str = "",
    ) -> dict:
        return {
            "project_id": PROJECT_ID,
            "metric_type": self.metric,
            "value": value,
            "captured_at": captured_at,
            "period": "point",
            "metadata_json": None,
            "scope": scope,
            "scope_id": scope_id,
        }

    async def _count_rows(self) -> int:
        async with self.db.execute("SELECT COUNT(*) FROM analytics_entries") as cur:
            row = await cur.fetchone()
        assert row is not None
        return row[0]

    async def _all_rows(self) -> list[dict]:
        async with self.db.execute(
            "SELECT value, scope, scope_id FROM analytics_entries"
        ) as cur:
            rows = await cur.fetchall()
        return [{"value": r[0], "scope": r[1], "scope_id": r[2]} for r in rows]

    # ------------------------------------------------------------------
    # Test 1: distinct rows — project and feature do NOT overwrite each other
    # ------------------------------------------------------------------
    async def test_project_and_feature_rows_are_distinct(self) -> None:
        await self.repo.insert_entry(self._entry(10.0))
        await self.repo.insert_entry(
            self._entry(3.0, scope="feature", scope_id=FEATURE_ID)
        )

        rows = await self._all_rows()
        self.assertEqual(len(rows), 2, f"Expected 2 rows, got: {rows}")
        values = {r["scope"]: r["value"] for r in rows}
        self.assertEqual(values["project"], 10.0)
        self.assertEqual(values["feature"], 3.0)

    # ------------------------------------------------------------------
    # Test 2: same-day upsert deduplicates WITHIN a scope
    # ------------------------------------------------------------------
    async def test_same_day_upsert_deduplicates_within_scope(self) -> None:
        # First project insert
        await self.repo.insert_entry(self._entry(10.0))
        # Second project insert same day → upsert should update, not append
        await self.repo.insert_entry(self._entry(12.0))

        async with self.db.execute(
            "SELECT COUNT(*), value FROM analytics_entries WHERE scope='project'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        self.assertEqual(row[0], 1, "Upsert should keep only ONE project-scope row")
        self.assertEqual(row[1], 12.0, "Upserted value should be 12.0")

        # First feature insert
        await self.repo.insert_entry(
            self._entry(3.0, scope="feature", scope_id=FEATURE_ID)
        )
        # Second feature insert same day → upsert
        await self.repo.insert_entry(
            self._entry(5.0, scope="feature", scope_id=FEATURE_ID)
        )

        async with self.db.execute(
            "SELECT COUNT(*), value FROM analytics_entries WHERE scope='feature' AND scope_id=?",
            (FEATURE_ID,),
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        self.assertEqual(row[0], 1, "Upsert should keep only ONE feature-scope row")
        self.assertEqual(row[1], 5.0, "Upserted feature value should be 5.0")

    # ------------------------------------------------------------------
    # Test 3: get_latest_entries defaults to project scope
    # ------------------------------------------------------------------
    async def test_get_latest_entries_defaults_to_project_scope(self) -> None:
        await self.repo.insert_entry(self._entry(12.0))
        await self.repo.insert_entry(
            self._entry(5.0, scope="feature", scope_id=FEATURE_ID)
        )

        result = await self.repo.get_latest_entries(PROJECT_ID, [METRIC])
        self.assertIn(METRIC, result, "Metric must be present in result")
        self.assertEqual(
            result[METRIC],
            12.0,
            f"Default scope=project should return 12.0, got {result[METRIC]!r}",
        )

    # ------------------------------------------------------------------
    # Test 4: get_latest_entries can target a feature
    # ------------------------------------------------------------------
    async def test_get_latest_entries_targets_feature_scope(self) -> None:
        await self.repo.insert_entry(self._entry(12.0))
        await self.repo.insert_entry(
            self._entry(5.0, scope="feature", scope_id=FEATURE_ID)
        )

        result = await self.repo.get_latest_entries(
            PROJECT_ID, [METRIC], scope="feature", scope_id=FEATURE_ID
        )
        self.assertIn(METRIC, result)
        self.assertEqual(
            result[METRIC],
            5.0,
            f"scope='feature', scope_id='F1' should return 5.0, got {result[METRIC]!r}",
        )

    # ------------------------------------------------------------------
    # Test 5: get_trends respects scope
    # ------------------------------------------------------------------
    async def test_get_trends_respects_scope(self) -> None:
        # Insert two project points on different days
        await self.repo.insert_entry(self._entry(10.0, captured_at=DAY1))
        await self.repo.insert_entry(self._entry(20.0, captured_at=DAY2))

        # Insert a feature point on DAY1 only
        await self.repo.insert_entry(
            self._entry(3.0, captured_at=DAY1, scope="feature", scope_id=FEATURE_ID)
        )

        # get_trends for project scope returns only project points
        project_series = await self.repo.get_trends(
            PROJECT_ID, METRIC, period="point"
        )
        self.assertEqual(
            len(project_series),
            2,
            f"Project scope should yield 2 points, got: {project_series}",
        )
        proj_values = [r["value"] for r in project_series]
        self.assertIn(10.0, proj_values)
        self.assertIn(20.0, proj_values)

        # get_trends for feature scope returns only the feature point
        feature_series = await self.repo.get_trends(
            PROJECT_ID, METRIC, period="point", scope="feature", scope_id=FEATURE_ID
        )
        self.assertEqual(
            len(feature_series),
            1,
            f"Feature scope should yield 1 point, got: {feature_series}",
        )
        self.assertEqual(feature_series[0]["value"], 3.0)


if __name__ == "__main__":
    unittest.main()
