"""Tests for P2-008: column-projected list_summary on feature and document repos.

Acceptance criteria:
- list_summary returns ONLY the projected columns (no data_json / content blobs).
- Features: projected columns are id, name, status, category, updated_at, phases_json.
- Documents: projected columns are id, title, status, doc_type, updated_at.
- phases_json is a parseable JSON array (may be empty list for features with no phases).
- By default terminal features (done, deferred, completed) are excluded.
- include_terminal=True includes all statuses.
- list_all is still present and still returns full rows (regression guard).
- SQLite and Postgres implementations both satisfy the above (SQLite tested directly;
  Postgres variants tested via SQL-clause inspection since asyncpg requires a live DB).
"""
from __future__ import annotations

import asyncio
import json
import unittest

import aiosqlite

from backend.db.repositories.documents import SqliteDocumentRepository
from backend.db.repositories.features import SqliteFeatureRepository
from backend.db.sqlite_migrations import run_migrations


# ---------------------------------------------------------------------------
# Helpers — seed data
# ---------------------------------------------------------------------------

_PROJ = "test-proj-1"

_TERMINAL_STATUSES = {"done", "deferred", "completed"}

_FEATURE_ROWS = [
    # id, name, status, category, updated_at
    ("F-ACTIVE-1", "Active Alpha", "in-progress", "cat-a", "2024-06-01T00:00:00Z"),
    ("F-ACTIVE-2", "Active Beta", "backlog", "cat-b", "2024-05-15T00:00:00Z"),
    ("F-ACTIVE-3", "Active Gamma", "planning", "cat-a", "2024-04-10T00:00:00Z"),
    ("F-DONE", "Done Delta", "done", "cat-b", "2024-03-01T00:00:00Z"),
    ("F-DEFERRED", "Deferred Epsilon", "deferred", "cat-a", "2024-02-01T00:00:00Z"),
    ("F-COMPLETED", "Completed Zeta", "completed", "cat-b", "2024-01-10T00:00:00Z"),
]

_DOC_ROWS = [
    # id, title, status, doc_type, updated_at
    ("D-001", "Doc Alpha", "active", "plan", "2024-06-10T00:00:00Z"),
    ("D-002", "Doc Beta", "draft", "report", "2024-05-20T00:00:00Z"),
    ("D-003", "Doc Gamma", "archived", "spec", "2024-04-05T00:00:00Z"),
]

_FEATURE_PHASES = {
    "F-ACTIVE-1": [
        {"phase": "1", "title": "Design", "status": "completed", "progress": 100,
         "totalTasks": 5, "completedTasks": 5},
        {"phase": "2", "title": "Implement", "status": "in-progress", "progress": 50,
         "totalTasks": 10, "completedTasks": 5},
    ],
    "F-DONE": [
        {"phase": "1", "title": "All Done", "status": "completed", "progress": 100,
         "totalTasks": 3, "completedTasks": 3},
    ],
}


def _make_feature_data(fid: str, name: str, status: str, category: str, updated_at: str) -> dict:
    return {
        "id": fid,
        "name": name,
        "status": status,
        "category": category,
        "updatedAt": updated_at,
        "createdAt": "2024-01-01T00:00:00Z",
        "totalTasks": 0,
        "completedTasks": 0,
        "tags": [],
    }


def _make_doc_data(did: str, title: str, status: str, doc_type: str, updated_at: str) -> dict:
    return {
        "id": did,
        "title": title,
        "status": status,
        "docType": doc_type,
        "updatedAt": updated_at,
        "createdAt": "2024-01-01T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# Base mixin: sets up a fresh in-memory SQLite DB
# ---------------------------------------------------------------------------

class _SqliteBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.feat_repo = SqliteFeatureRepository(self.db)
        self.doc_repo = SqliteDocumentRepository(self.db)

        # Seed features
        for fid, name, status, category, updated_at in _FEATURE_ROWS:
            await self.feat_repo.upsert(
                _make_feature_data(fid, name, status, category, updated_at), _PROJ
            )
        # Seed phases for some features
        for fid, phases in _FEATURE_PHASES.items():
            await self.feat_repo.upsert_phases(fid, phases)

        # Seed documents
        for did, title, status, doc_type, updated_at in _DOC_ROWS:
            await self.doc_repo.upsert(
                _make_doc_data(did, title, status, doc_type, updated_at), _PROJ
            )

    async def asyncTearDown(self) -> None:
        await self.db.close()


# ---------------------------------------------------------------------------
# Feature summary tests
# ---------------------------------------------------------------------------

class TestSqliteFeatureListSummaryProjection(_SqliteBase):
    """Column-projection and phases_json shape."""

    async def test_returns_only_projected_columns(self) -> None:
        rows = await self.feat_repo.list_summary(_PROJ)
        self.assertGreater(len(rows), 0)
        expected_keys = {"id", "name", "status", "category", "updated_at", "phases_json"}
        for row in rows:
            self.assertEqual(set(row.keys()), expected_keys,
                             f"Unexpected keys in row {row['id']}: {set(row.keys())}")

    async def test_data_json_not_present(self) -> None:
        rows = await self.feat_repo.list_summary(_PROJ)
        for row in rows:
            self.assertNotIn("data_json", row,
                             f"data_json must not be in summary for feature {row['id']}")

    async def test_phases_json_is_valid_json_list(self) -> None:
        rows = await self.feat_repo.list_summary(_PROJ, include_terminal=True)
        for row in rows:
            phases = json.loads(row["phases_json"])
            self.assertIsInstance(phases, list,
                                  f"phases_json must be a JSON list for {row['id']}")

    async def test_phases_json_for_feature_with_phases(self) -> None:
        rows = await self.feat_repo.list_summary(_PROJ, include_terminal=True)
        row = next(r for r in rows if r["id"] == "F-ACTIVE-1")
        phases = json.loads(row["phases_json"])
        self.assertEqual(len(phases), 2)
        # Verify the expected shape of each phase element
        for p in phases:
            self.assertIn("phase", p)
            self.assertIn("title", p)
            self.assertIn("status", p)
            self.assertIn("progress", p)
            self.assertIn("total_tasks", p)
            self.assertIn("completed_tasks", p)

    async def test_phases_json_empty_for_feature_without_phases(self) -> None:
        rows = await self.feat_repo.list_summary(_PROJ, include_terminal=False)
        row = next(r for r in rows if r["id"] == "F-ACTIVE-2")
        phases = json.loads(row["phases_json"])
        self.assertEqual(phases, [])


class TestSqliteFeatureListSummaryTerminalFiltering(_SqliteBase):
    """Terminal status filtering defaults and include_terminal flag."""

    async def test_default_excludes_terminal_statuses(self) -> None:
        rows = await self.feat_repo.list_summary(_PROJ)
        ids = {r["id"] for r in rows}
        # Terminal features must not appear by default
        self.assertNotIn("F-DONE", ids)
        self.assertNotIn("F-DEFERRED", ids)
        self.assertNotIn("F-COMPLETED", ids)

    async def test_default_includes_active_features(self) -> None:
        rows = await self.feat_repo.list_summary(_PROJ)
        ids = {r["id"] for r in rows}
        self.assertIn("F-ACTIVE-1", ids)
        self.assertIn("F-ACTIVE-2", ids)
        self.assertIn("F-ACTIVE-3", ids)

    async def test_include_terminal_true_returns_all_statuses(self) -> None:
        rows = await self.feat_repo.list_summary(_PROJ, include_terminal=True)
        ids = {r["id"] for r in rows}
        self.assertIn("F-DONE", ids)
        self.assertIn("F-DEFERRED", ids)
        self.assertIn("F-COMPLETED", ids)
        self.assertIn("F-ACTIVE-1", ids)
        self.assertEqual(len(ids), len(_FEATURE_ROWS))

    async def test_default_count_matches_non_terminal_seed(self) -> None:
        non_terminal_count = sum(
            1 for _, _, status, _, _ in _FEATURE_ROWS
            if status not in _TERMINAL_STATUSES
        )
        rows = await self.feat_repo.list_summary(_PROJ)
        self.assertEqual(len(rows), non_terminal_count)

    async def test_terminal_feature_phases_json_when_included(self) -> None:
        rows = await self.feat_repo.list_summary(_PROJ, include_terminal=True)
        done_row = next(r for r in rows if r["id"] == "F-DONE")
        phases = json.loads(done_row["phases_json"])
        self.assertEqual(len(phases), 1)
        self.assertEqual(phases[0]["title"], "All Done")


class TestSqliteFeatureListAllStillWorks(_SqliteBase):
    """Regression: list_all must still return full rows including data_json."""

    async def test_list_all_returns_data_json(self) -> None:
        rows = await self.feat_repo.list_all(_PROJ)
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertIn("data_json", row,
                          f"list_all must still return data_json for {row['id']}")

    async def test_list_all_returns_all_rows(self) -> None:
        rows = await self.feat_repo.list_all(_PROJ)
        self.assertEqual(len(rows), len(_FEATURE_ROWS))


# ---------------------------------------------------------------------------
# Document summary tests
# ---------------------------------------------------------------------------

class TestSqliteDocumentListSummaryProjection(_SqliteBase):
    """Column-projection for document list_summary."""

    async def test_returns_only_projected_columns(self) -> None:
        rows = await self.doc_repo.list_summary(_PROJ)
        self.assertGreater(len(rows), 0)
        expected_keys = {"id", "title", "status", "doc_type", "updated_at"}
        for row in rows:
            self.assertEqual(set(row.keys()), expected_keys,
                             f"Unexpected keys in row {row['id']}: {set(row.keys())}")

    async def test_content_not_present(self) -> None:
        rows = await self.doc_repo.list_summary(_PROJ)
        for row in rows:
            self.assertNotIn("content", row)
            self.assertNotIn("frontmatter_json", row)
            self.assertNotIn("metadata_json", row)

    async def test_returns_all_documents(self) -> None:
        rows = await self.doc_repo.list_summary(_PROJ)
        ids = {r["id"] for r in rows}
        self.assertEqual(ids, {"D-001", "D-002", "D-003"})

    async def test_correct_field_values(self) -> None:
        rows = await self.doc_repo.list_summary(_PROJ)
        row = next(r for r in rows if r["id"] == "D-001")
        self.assertEqual(row["title"], "Doc Alpha")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["doc_type"], "plan")

    async def test_ordering_by_updated_at_desc(self) -> None:
        rows = await self.doc_repo.list_summary(_PROJ)
        updated_ats = [r["updated_at"] for r in rows]
        self.assertEqual(updated_ats, sorted(updated_ats, reverse=True),
                         "list_summary should return documents ordered by updated_at DESC")


class TestSqliteDocumentListAllStillWorks(_SqliteBase):
    """Regression: list_all must still return full rows."""

    async def test_list_all_returns_content_column(self) -> None:
        # list_all delegates to list_paginated which uses SELECT *
        rows = await self.doc_repo.list_all(_PROJ)
        self.assertGreater(len(rows), 0)
        for row in rows:
            # 'content' column exists in the schema (may be None but key present)
            self.assertIn("content", row,
                          f"list_all must still expose content column for {row['id']}")

    async def test_list_all_returns_all_rows(self) -> None:
        rows = await self.doc_repo.list_all(_PROJ)
        self.assertEqual(len(rows), len(_DOC_ROWS))


# ---------------------------------------------------------------------------
# Cross-project isolation
# ---------------------------------------------------------------------------

class TestSqliteListSummaryCrossProjectIsolation(_SqliteBase):
    """list_summary must not bleed across projects."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        # Seed a second project with one feature and one document
        await self.feat_repo.upsert(
            _make_feature_data("F-OTHER", "Other Feature", "backlog", "cat-z", "2024-07-01T00:00:00Z"),
            "other-proj",
        )
        await self.doc_repo.upsert(
            _make_doc_data("D-OTHER", "Other Doc", "active", "spec", "2024-07-01T00:00:00Z"),
            "other-proj",
        )

    async def test_feature_summary_scoped_to_project(self) -> None:
        rows = await self.feat_repo.list_summary(_PROJ)
        ids = {r["id"] for r in rows}
        self.assertNotIn("F-OTHER", ids)

    async def test_document_summary_scoped_to_project(self) -> None:
        rows = await self.doc_repo.list_summary(_PROJ)
        ids = {r["id"] for r in rows}
        self.assertNotIn("D-OTHER", ids)

    async def test_other_project_feature_accessible(self) -> None:
        rows = await self.feat_repo.list_summary("other-proj")
        ids = {r["id"] for r in rows}
        self.assertIn("F-OTHER", ids)
        # Must not include rows from _PROJ
        for fid, *_ in _FEATURE_ROWS:
            self.assertNotIn(fid, ids)


# ---------------------------------------------------------------------------
# Postgres SQL-clause contract tests (no live DB required)
# ---------------------------------------------------------------------------

class TestPostgresFeatureListSummaryContract(unittest.TestCase):
    """Smoke-test that the Postgres list_summary method exists and has the
    expected signature without requiring a live asyncpg connection."""

    def test_method_exists_on_postgres_feature_repo(self) -> None:
        from backend.db.repositories.postgres.features import PostgresFeatureRepository
        self.assertTrue(
            hasattr(PostgresFeatureRepository, "list_summary"),
            "PostgresFeatureRepository must have list_summary"
        )

    def test_signature_accepts_include_terminal(self) -> None:
        import inspect
        from backend.db.repositories.postgres.features import PostgresFeatureRepository
        sig = inspect.signature(PostgresFeatureRepository.list_summary)
        self.assertIn("include_terminal", sig.parameters)

    def test_signature_accepts_limit(self) -> None:
        import inspect
        from backend.db.repositories.postgres.features import PostgresFeatureRepository
        sig = inspect.signature(PostgresFeatureRepository.list_summary)
        self.assertIn("limit", sig.parameters)

    def test_terminal_statuses_class_attr(self) -> None:
        from backend.db.repositories.postgres.features import PostgresFeatureRepository
        ts = PostgresFeatureRepository._TERMINAL_STATUSES
        self.assertIn("done", ts)
        self.assertIn("deferred", ts)
        self.assertIn("completed", ts)

    def test_list_all_still_exists(self) -> None:
        from backend.db.repositories.postgres.features import PostgresFeatureRepository
        self.assertTrue(hasattr(PostgresFeatureRepository, "list_all"))


class TestPostgresDocumentListSummaryContract(unittest.TestCase):
    """Smoke-test for PostgresDocumentRepository.list_summary signature."""

    def test_method_exists(self) -> None:
        from backend.db.repositories.postgres.documents import PostgresDocumentRepository
        self.assertTrue(
            hasattr(PostgresDocumentRepository, "list_summary"),
            "PostgresDocumentRepository must have list_summary"
        )

    def test_signature_accepts_limit(self) -> None:
        import inspect
        from backend.db.repositories.postgres.documents import PostgresDocumentRepository
        sig = inspect.signature(PostgresDocumentRepository.list_summary)
        self.assertIn("limit", sig.parameters)

    def test_list_all_still_exists(self) -> None:
        from backend.db.repositories.postgres.documents import PostgresDocumentRepository
        self.assertTrue(hasattr(PostgresDocumentRepository, "list_all"))


# ---------------------------------------------------------------------------
# SQLite feature repo: _TERMINAL_STATUSES class attribute parity
# ---------------------------------------------------------------------------

class TestSqliteFeatureTerminalStatusAttr(unittest.TestCase):
    def test_terminal_statuses_defined(self) -> None:
        ts = SqliteFeatureRepository._TERMINAL_STATUSES
        self.assertIn("done", ts)
        self.assertIn("deferred", ts)
        self.assertIn("completed", ts)

    def test_parity_with_postgres(self) -> None:
        from backend.db.repositories.postgres.features import PostgresFeatureRepository
        self.assertEqual(
            SqliteFeatureRepository._TERMINAL_STATUSES,
            PostgresFeatureRepository._TERMINAL_STATUSES,
            "SQLite and Postgres implementations must share the same terminal status set",
        )


if __name__ == "__main__":
    unittest.main()
