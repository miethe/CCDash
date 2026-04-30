"""Tests for SqliteFeatureRepository.list_feature_cards / count_feature_cards.

These tests use an in-memory SQLite database seeded with ~20 features spanning
3 statuses, 2 categories, varied dates, and varied progress.

The primary regression guarded here is that ``total`` reflects the post-filter,
pre-pagination count — NOT the unfiltered table count.  Previously, status and
category filters were applied in-memory after pagination, making ``total`` wrong.
"""
from __future__ import annotations

import json
import unittest

import aiosqlite

from backend.db.repositories.features import SqliteFeatureRepository
from backend.db.repositories.feature_queries import (
    DateRange,
    FeatureListQuery,
    FeatureSortKey,
    SortDirection,
)
from backend.db.repositories.postgres.features import _build_feature_list_where_clause_pg
from backend.db.sqlite_migrations import run_migrations


# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------

def _make_feature(
    fid: str,
    name: str,
    status: str,
    category: str,
    total_tasks: int,
    completed_tasks: int,
    created_at: str = "2024-01-01T00:00:00Z",
    updated_at: str = "2024-06-01T00:00:00Z",
    completed_at: str = "",
    tags: list[str] | None = None,
    deferred_tasks: int = 0,
    planned_at: str = "",
    started_at: str = "",
) -> dict:
    data: dict = {
        "id": fid,
        "name": name,
        "status": status,
        "category": category,
        "totalTasks": total_tasks,
        "completedTasks": completed_tasks,
        "createdAt": created_at,
        "updatedAt": updated_at,
        "completedAt": completed_at,
        "tags": tags or [],
        "deferredTasks": deferred_tasks,
        "plannedAt": planned_at,
        "startedAt": started_at,
    }
    return data


# 20 features: 7 backlog, 8 in-progress, 5 done; 10 cat-A, 10 cat-B
_SEED_FEATURES = [
    # cat-A, backlog
    _make_feature("F-001", "Alpha Feature", "backlog", "cat-a", 10, 0,
                  updated_at="2024-01-10T00:00:00Z", tags=["ui"]),
    _make_feature("F-002", "Beta Search", "backlog", "cat-a", 5, 1,
                  updated_at="2024-02-01T00:00:00Z"),
    _make_feature("F-003", "Gamma Refactor", "backlog", "cat-a", 0, 0,
                  updated_at="2024-02-15T00:00:00Z"),
    _make_feature("F-004", "Delta Pipeline", "backlog", "cat-a", 20, 0,
                  updated_at="2024-03-01T00:00:00Z"),
    # cat-A, in-progress
    _make_feature("F-005", "Epsilon Auth", "in-progress", "cat-a", 8, 4,
                  updated_at="2024-04-01T00:00:00Z"),
    _make_feature("F-006", "Zeta Logging", "in-progress", "cat-a", 12, 6,
                  updated_at="2024-04-15T00:00:00Z"),
    _make_feature("F-007", "Eta Dashboard", "in-progress", "cat-a", 15, 15,
                  updated_at="2024-05-01T00:00:00Z"),
    _make_feature("F-008", "Theta Cache", "in-progress", "cat-a", 6, 2,
                  updated_at="2024-05-10T00:00:00Z"),
    # cat-A, done
    _make_feature("F-009", "Iota Release", "done", "cat-a", 10, 10,
                  updated_at="2024-05-20T00:00:00Z",
                  completed_at="2024-05-20T00:00:00Z"),
    _make_feature("F-010", "Kappa Deploy", "done", "cat-a", 5, 5,
                  updated_at="2024-06-01T00:00:00Z",
                  completed_at="2024-06-01T00:00:00Z"),
    # cat-B, backlog
    _make_feature("F-011", "Lambda Config", "backlog", "cat-b", 3, 0,
                  updated_at="2024-01-20T00:00:00Z"),
    _make_feature("F-012", "Mu Analytics", "backlog", "cat-b", 7, 1,
                  updated_at="2024-02-05T00:00:00Z"),
    _make_feature("F-013", "Nu Migration", "backlog", "cat-b", 4, 0,
                  updated_at="2024-02-20T00:00:00Z"),
    # cat-B, in-progress
    _make_feature("F-014", "Xi Testing", "in-progress", "cat-b", 9, 5,
                  updated_at="2024-03-15T00:00:00Z"),
    _make_feature("F-015", "Omicron Search", "in-progress", "cat-b", 11, 4,
                  updated_at="2024-04-05T00:00:00Z"),
    _make_feature("F-016", "Pi Integration", "in-progress", "cat-b", 14, 7,
                  updated_at="2024-04-20T00:00:00Z"),
    _make_feature("F-017", "Rho Scheduler", "in-progress", "cat-b", 8, 8,
                  updated_at="2024-05-05T00:00:00Z"),
    # cat-B, done
    _make_feature("F-018", "Sigma Cleanup", "done", "cat-b", 6, 6,
                  updated_at="2024-05-15T00:00:00Z",
                  completed_at="2024-05-15T00:00:00Z"),
    _make_feature("F-019", "Tau Hardening", "done", "cat-b", 4, 4,
                  updated_at="2024-05-25T00:00:00Z",
                  completed_at="2024-05-25T00:00:00Z"),
    _make_feature("F-020", "Upsilon Finalize", "done", "cat-b", 8, 8,
                  updated_at="2024-06-05T00:00:00Z",
                  completed_at="2024-06-05T00:00:00Z",
                  tags=["release"], deferred_tasks=2,
                  planned_at="2024-06-01T00:00:00Z",
                  started_at="2024-06-02T00:00:00Z"),
]


class TestFeatureListQuery(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteFeatureRepository(self.db)
        for f in _SEED_FEATURES:
            await self.repo.upsert(f, "proj-1")

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _link_session(
        self,
        feature_id: str,
        session_id: str,
        *,
        started_at: str,
        updated_at: str,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO sessions (
                id, project_id, task_id, status, model,
                created_at, updated_at, started_at, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                "proj-1",
                feature_id,
                "completed",
                "claude-sonnet",
                started_at,
                updated_at,
                started_at,
                f"{session_id}.jsonl",
            ),
        )
        await self.db.execute(
            """
            INSERT INTO entity_links (
                source_type, source_id, target_type, target_id, link_type, created_at
            ) VALUES ('feature', ?, 'session', ?, 'related', ?)
            """,
            (feature_id, session_id, updated_at),
        )
        await self.db.commit()

    # ── empty filter matches all ─────────────────────────────────────────────

    async def test_empty_filter_returns_all(self) -> None:
        q = FeatureListQuery(limit=200, offset=0)
        page = await self.repo.list_feature_cards("proj-1", q)
        self.assertEqual(page.total, 20)
        self.assertEqual(len(page.rows), 20)
        self.assertFalse(page.has_more)

    # ── status filter ────────────────────────────────────────────────────────

    async def test_status_filter_single(self) -> None:
        q = FeatureListQuery(status=["done"], limit=200)
        page = await self.repo.list_feature_cards("proj-1", q)
        self.assertEqual(page.total, 5)
        self.assertEqual(len(page.rows), 5)
        for row in page.rows:
            self.assertEqual(row["status"], "done")

    async def test_status_filter_multi(self) -> None:
        q = FeatureListQuery(status=["in-progress", "done"], limit=200)
        page = await self.repo.list_feature_cards("proj-1", q)
        self.assertEqual(page.total, 13)  # 8 in-progress + 5 done

    # ── REGRESSION: total must reflect filter, not full table ────────────────

    async def test_total_reflects_filter_not_full_table(self) -> None:
        """Regression: filtered total must NOT equal the full 20-row table count."""
        q = FeatureListQuery(status=["backlog"], limit=200)
        page = await self.repo.list_feature_cards("proj-1", q)
        self.assertNotEqual(page.total, 20, "total must NOT be the unfiltered count")
        self.assertEqual(page.total, 7)  # 4 cat-A + 3 cat-B backlog

    # ── status + offset pagination ───────────────────────────────────────────

    async def test_status_filter_pagination_page2(self) -> None:
        """Page 2 with status filter: total must be correct and rows must be offset."""
        q_page1 = FeatureListQuery(status=["in-progress"], limit=5, offset=0)
        page1 = await self.repo.list_feature_cards("proj-1", q_page1)
        self.assertEqual(page1.total, 8)
        self.assertEqual(len(page1.rows), 5)
        self.assertTrue(page1.has_more)

        q_page2 = FeatureListQuery(status=["in-progress"], limit=5, offset=5)
        page2 = await self.repo.list_feature_cards("proj-1", q_page2)
        self.assertEqual(page2.total, 8)  # total is stable across pages
        self.assertEqual(len(page2.rows), 3)
        self.assertFalse(page2.has_more)

        # No row overlap between pages
        ids_p1 = {r["id"] for r in page1.rows}
        ids_p2 = {r["id"] for r in page2.rows}
        self.assertFalse(ids_p1 & ids_p2, "pages must not overlap")

    # ── combined status + category + date range ──────────────────────────────

    async def test_combined_status_category_date_narrows(self) -> None:
        # in-progress cat-a features updated at or after 2024-04-01
        q = FeatureListQuery(
            status=["in-progress"],
            category=["cat-a"],
            updated=DateRange(from_date="2024-04-01T00:00:00Z"),
            limit=200,
        )
        page = await self.repo.list_feature_cards("proj-1", q)
        # F-005 (2024-04-01), F-006 (2024-04-15), F-007 (2024-05-01), F-008 (2024-05-10)
        self.assertEqual(page.total, 4)
        self.assertNotEqual(page.total, 20, "combined filter must narrow total below 20")
        for row in page.rows:
            self.assertEqual(row["status"], "in-progress")
            self.assertEqual(row["category"].lower(), "cat-a")

    # ── sort by progress DESC + feature_id ASC tiebreaker ───────────────────

    async def test_sort_by_progress_desc_deterministic(self) -> None:
        """Sort by PROGRESS DESC with tiebreaker must be deterministic."""
        q1 = FeatureListQuery(
            sort_by=FeatureSortKey.PROGRESS,
            sort_direction=SortDirection.DESC,
            limit=200,
        )
        q2 = FeatureListQuery(
            sort_by=FeatureSortKey.PROGRESS,
            sort_direction=SortDirection.DESC,
            limit=200,
        )
        page1 = await self.repo.list_feature_cards("proj-1", q1)
        page2 = await self.repo.list_feature_cards("proj-1", q2)
        ids1 = [r["id"] for r in page1.rows]
        ids2 = [r["id"] for r in page2.rows]
        self.assertEqual(ids1, ids2, "sort must be deterministic across identical queries")

        # Verify descending progress order: ratio = completed_tasks / total_tasks
        def _prog(r: dict) -> float:
            t = r.get("total_tasks", 0)
            c = r.get("completed_tasks", 0)
            return c / t if t else 0.0

        prev = 2.0
        for row in page1.rows:
            prog = _prog(row)
            self.assertLessEqual(
                prog, prev + 1e-9,
                f"row {row['id']} has progress {prog} > previous {prev}",
            )
            prev = prog

    async def test_sort_by_latest_activity_uses_linked_session_rollup(self) -> None:
        await self._link_session(
            "F-001",
            "S-latest",
            started_at="2026-04-01T00:00:00Z",
            updated_at="2026-04-02T00:00:00Z",
        )

        q = FeatureListQuery(sort_by=FeatureSortKey.LATEST_ACTIVITY, limit=5)
        page = await self.repo.list_feature_cards("proj-1", q)

        self.assertEqual(page.rows[0]["id"], "F-001")

    async def test_sort_by_session_count_uses_linked_session_rollup(self) -> None:
        for idx in range(3):
            await self._link_session(
                "F-002",
                f"S-count-{idx}",
                started_at=f"2024-01-0{idx + 1}T00:00:00Z",
                updated_at=f"2024-01-0{idx + 1}T00:00:00Z",
            )
        await self._link_session(
            "F-003",
            "S-count-low",
            started_at="2024-01-10T00:00:00Z",
            updated_at="2024-01-10T00:00:00Z",
        )

        q = FeatureListQuery(sort_by=FeatureSortKey.SESSION_COUNT, limit=5)
        page = await self.repo.list_feature_cards("proj-1", q)

        self.assertEqual(page.rows[0]["id"], "F-002")

    # ── q search matches both id and name ────────────────────────────────────

    async def test_q_matches_feature_id(self) -> None:
        # "F-020" should match on id
        q = FeatureListQuery(q="F-020", limit=200)
        page = await self.repo.list_feature_cards("proj-1", q)
        self.assertEqual(page.total, 1)
        self.assertEqual(page.rows[0]["id"], "F-020")

    async def test_q_matches_name(self) -> None:
        # "Search" appears in "Beta Search" (F-002) and "Omicron Search" (F-015)
        q = FeatureListQuery(q="Search", limit=200)
        page = await self.repo.list_feature_cards("proj-1", q)
        ids = {r["id"] for r in page.rows}
        self.assertIn("F-002", ids)
        self.assertIn("F-015", ids)
        self.assertEqual(page.total, len(page.rows))

    # ── count_feature_cards parity ───────────────────────────────────────────

    async def test_count_feature_cards_parity(self) -> None:
        q = FeatureListQuery(status=["done"], category=["cat-b"], limit=200)
        count = await self.repo.count_feature_cards("proj-1", q)
        page = await self.repo.list_feature_cards("proj-1", q)
        self.assertEqual(count, page.total)

    # ── has_deferred filter ──────────────────────────────────────────────────

    async def test_has_deferred_true(self) -> None:
        # Only F-020 has deferredTasks > 0
        q = FeatureListQuery(has_deferred=True, limit=200)
        page = await self.repo.list_feature_cards("proj-1", q)
        self.assertEqual(page.total, 1)
        self.assertEqual(page.rows[0]["id"], "F-020")

    async def test_promoted_columns_are_used_after_data_json_changes(self) -> None:
        await self.db.execute(
            "UPDATE features SET data_json = ? WHERE id = ?",
            (
                json.dumps({
                    "id": "F-020",
                    "name": "Upsilon Finalize",
                    "status": "done",
                    "category": "cat-b",
                    "totalTasks": 8,
                    "completedTasks": 8,
                    "tags": [],
                    "deferredTasks": 0,
                    "plannedAt": "",
                    "startedAt": "",
                }),
                "F-020",
            ),
        )
        await self.db.commit()

        q = FeatureListQuery(
            tags=["release"],
            has_deferred=True,
            planned=DateRange(
                from_date="2024-06-01T00:00:00Z",
                to_date="2024-06-30T00:00:00Z",
            ),
            started=DateRange(
                from_date="2024-06-02T00:00:00Z",
                to_date="2024-06-30T00:00:00Z",
            ),
            limit=200,
        )
        page = await self.repo.list_feature_cards("proj-1", q)
        self.assertEqual(page.total, 1)
        self.assertEqual(page.rows[0]["id"], "F-020")

    def test_postgres_query_builder_uses_promoted_columns(self) -> None:
        q = FeatureListQuery(
            tags=["release"],
            has_deferred=True,
            planned=DateRange(
                from_date="2024-06-01T00:00:00Z",
                to_date="2024-06-30T00:00:00Z",
            ),
            started=DateRange(
                from_date="2024-06-02T00:00:00Z",
                to_date="2024-06-30T00:00:00Z",
            ),
            limit=200,
        )
        where_sql, params = _build_feature_list_where_clause_pg("proj-1", q)

        self.assertIn("tags_json", where_sql)
        self.assertIn("deferred_tasks", where_sql)
        self.assertIn("planned_at", where_sql)
        self.assertIn("started_at", where_sql)
        self.assertNotIn("data_json", where_sql)
        self.assertEqual(params[0], "proj-1")

    # ── completed date range ─────────────────────────────────────────────────

    async def test_completed_date_range(self) -> None:
        q = FeatureListQuery(
            completed=DateRange(
                from_date="2024-05-20T00:00:00Z",
                to_date="2024-05-25T00:00:00Z",
            ),
            limit=200,
        )
        page = await self.repo.list_feature_cards("proj-1", q)
        ids = {r["id"] for r in page.rows}
        # F-009 completed 2024-05-20, F-018 completed 2024-05-15 (out), F-019 2024-05-25
        self.assertIn("F-009", ids)
        self.assertIn("F-019", ids)
        self.assertNotIn("F-020", ids)  # completed 2024-06-05

    # ── numeric range filters ────────────────────────────────────────────────

    async def test_task_count_range(self) -> None:
        q = FeatureListQuery(task_count_min=10, task_count_max=12, limit=200)
        page = await self.repo.list_feature_cards("proj-1", q)
        for row in page.rows:
            self.assertGreaterEqual(row["total_tasks"], 10)
            self.assertLessEqual(row["total_tasks"], 12)

    # ── category case-insensitive ────────────────────────────────────────────

    async def test_category_case_insensitive(self) -> None:
        q_lower = FeatureListQuery(category=["cat-a"], limit=200)
        q_upper = FeatureListQuery(category=["CAT-A"], limit=200)
        page_lower = await self.repo.list_feature_cards("proj-1", q_lower)
        page_upper = await self.repo.list_feature_cards("proj-1", q_upper)
        self.assertEqual(page_lower.total, page_upper.total)
        self.assertEqual(page_lower.total, 10)

    # ── project isolation ────────────────────────────────────────────────────

    async def test_different_project_returns_empty(self) -> None:
        q = FeatureListQuery(limit=200)
        page = await self.repo.list_feature_cards("proj-other", q)
        self.assertEqual(page.total, 0)
        self.assertEqual(len(page.rows), 0)


# ---------------------------------------------------------------------------
# Postgres parity (skipped unless CCDASH_DB_BACKEND=postgres)
# ---------------------------------------------------------------------------

import os
import pytest


@pytest.mark.skipif(
    os.environ.get("CCDASH_DB_BACKEND") != "postgres",
    reason="Postgres parity tests require CCDASH_DB_BACKEND=postgres and a live DB",
)
class TestFeatureListQueryPostgresParity:
    """Parity smoke tests for PostgresFeatureRepository.list_feature_cards.

    These tests are intentionally thin — the logic is shared via
    _build_feature_list_where_clause_pg; unit coverage lives in the SQLite suite above.
    """

    def test_placeholder(self) -> None:
        # Populated in a follow-up once asyncpg test fixture scaffold is in place.
        pass
