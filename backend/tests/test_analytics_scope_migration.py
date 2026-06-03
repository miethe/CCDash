"""Migration upgrade test: v32 → v33 analytics_entries scope split.

Simulates a database that was created at schema version 32 (no scope/scope_id
columns, old 3-column unique index) and verifies that running run_migrations():
  (a) adds scope and scope_id columns to analytics_entries
  (b) pre-existing rows survive and get scope='project', scope_id=''
  (c) the new index allows a project row and a feature row for the same
      (project_id, metric_type, date) to coexist without a uniqueness collision
  (d) schema_version MAX(version) == 33
"""
from __future__ import annotations

import unittest

import aiosqlite

from backend.db.sqlite_migrations import SCHEMA_VERSION, run_migrations


# Hand-crafted DDL that matches the analytics_entries shape at v32:
# - id, project_id, metric_type, value, captured_at, period, metadata_json
# - OLD unique index: (project_id, metric_type, date(captured_at)) WHERE period='point'
# - schema_version table seeded with version=32
_V32_DDL = """
CREATE TABLE IF NOT EXISTS metric_types (
    id              TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL DEFAULT '',
    unit            TEXT NOT NULL DEFAULT 'count',
    value_type      TEXT NOT NULL DEFAULT 'float',
    aggregation     TEXT NOT NULL DEFAULT 'sum',
    description     TEXT
);

INSERT OR IGNORE INTO metric_types (id, display_name, unit, value_type, aggregation)
    VALUES ('session_count', 'Session Count', 'count', 'integer', 'sum');

CREATE TABLE IF NOT EXISTS analytics_entries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL,
    metric_type  TEXT NOT NULL,
    value        REAL NOT NULL DEFAULT 0.0,
    captured_at  TEXT NOT NULL,
    period       TEXT NOT NULL DEFAULT 'point',
    metadata_json TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_analytics_point_daily
    ON analytics_entries(project_id, metric_type, date(captured_at))
    WHERE period = 'point';

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied TEXT DEFAULT (datetime('now'))
);

INSERT INTO schema_version (version) VALUES (32);
"""

# Two existing point rows at different days so we can confirm both survive.
_V32_SEED = """
INSERT INTO analytics_entries (project_id, metric_type, value, captured_at, period)
    VALUES
        ('P', 'session_count', 7.0, '2026-05-01T10:00:00Z', 'point'),
        ('P', 'session_count', 9.0, '2026-05-02T10:00:00Z', 'point');
"""


class AnalyticsScopeMigrationTest(unittest.IsolatedAsyncioTestCase):
    """Verify v32→v33 migration on an existing analytics_entries table."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row

        # Bootstrap the v32 schema + seed data
        await self.db.executescript(_V32_DDL)
        await self.db.executescript(_V32_SEED)
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _col_names(self, table: str) -> list[str]:
        async with self.db.execute(f"PRAGMA table_info({table})") as cur:
            rows = await cur.fetchall()
        return [r[1] for r in rows]  # column index 1 = name

    async def _max_schema_version(self) -> int:
        async with self.db.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
        assert row is not None
        return int(row[0])

    # ------------------------------------------------------------------
    # Main migration upgrade test
    # ------------------------------------------------------------------
    async def test_v32_to_v33_migration(self) -> None:
        # Confirm starting state: no scope columns
        cols_before = await self._col_names("analytics_entries")
        self.assertNotIn(
            "scope", cols_before, "scope column must not exist before migration"
        )
        self.assertNotIn(
            "scope_id", cols_before, "scope_id column must not exist before migration"
        )

        # Run the real migration runner
        await run_migrations(self.db)

        # ── (a) scope and scope_id columns now exist ──────────────────────────
        cols_after = await self._col_names("analytics_entries")
        self.assertIn("scope", cols_after, "scope column must exist after migration")
        self.assertIn(
            "scope_id", cols_after, "scope_id column must exist after migration"
        )

        # ── (b) pre-existing rows survived and got default scope values ───────
        async with self.db.execute(
            "SELECT COUNT(*) FROM analytics_entries"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        self.assertEqual(row[0], 2, "Both pre-existing rows must survive migration")

        async with self.db.execute(
            "SELECT COUNT(*) FROM analytics_entries WHERE scope = 'project' AND scope_id = ''"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        self.assertEqual(
            row[0],
            2,
            "All pre-existing rows must have scope='project', scope_id='' after migration",
        )

        # ── (c) new index allows project + feature rows for same metric+day ──
        # Insert a project-scope row on a new day
        await self.db.execute(
            "INSERT INTO analytics_entries"
            " (project_id, metric_type, value, captured_at, period, scope, scope_id)"
            " VALUES ('P', 'session_count', 10.0, '2026-06-01T10:00:00Z', 'point', 'project', '')"
        )
        # Insert a feature-scope row on the SAME day — must NOT collide
        await self.db.execute(
            "INSERT INTO analytics_entries"
            " (project_id, metric_type, value, captured_at, period, scope, scope_id)"
            " VALUES ('P', 'session_count', 3.0, '2026-06-01T11:00:00Z', 'point', 'feature', 'F1')"
        )
        await self.db.commit()

        async with self.db.execute(
            "SELECT COUNT(*) FROM analytics_entries"
            " WHERE date(captured_at) = '2026-06-01' AND project_id = 'P'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        self.assertEqual(
            row[0],
            2,
            "Both project-scope and feature-scope rows for 2026-06-01 must coexist",
        )

        # ── (d) schema version == 33 ──────────────────────────────────────────
        max_ver = await self._max_schema_version()
        self.assertEqual(
            max_ver,
            SCHEMA_VERSION,
            f"schema_version must be {SCHEMA_VERSION} after migration, got {max_ver}",
        )


if __name__ == "__main__":
    unittest.main()
