"""Tests for the DB-backed project registry (SqliteProjectRepository + DbProjectManager).

Covers:
  (a) list_projects() returns is_active=True project as list[0]
      (ORDER BY is_active DESC, created_at ASC — T0-001).
  (b) Seed projects (default-skillmeat, test-project-1) have is_seed==True;
      non-seed projects have is_seed==False (T0-002).
  (c) Direct-count assertion: repo.count() reflects the number of rows actually
      written, per ADR-007 write-path verification pattern (T0-003).

Run ONLY this module to avoid hanging on unscoped pytest collection:
  backend/.venv/bin/python -m pytest backend/tests/test_projects_registry.py -v
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.db.repositories.projects import SqliteProjectRepository
from backend.models import Project
from backend.project_manager import DbProjectManager, _SEED_PROJECT_IDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECTS_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    path                 TEXT NOT NULL DEFAULT '',
    description          TEXT NOT NULL DEFAULT '',
    repo_url             TEXT NOT NULL DEFAULT '',
    agent_platforms_json TEXT NOT NULL DEFAULT '["Claude Code"]',
    plan_docs_path       TEXT NOT NULL DEFAULT 'docs/project_plans/',
    sessions_path        TEXT NOT NULL DEFAULT '',
    progress_path        TEXT NOT NULL DEFAULT 'progress',
    path_config_json     TEXT NOT NULL DEFAULT '{}',
    test_config_json     TEXT NOT NULL DEFAULT '{}',
    skillmeat_json       TEXT NOT NULL DEFAULT '{}',
    display_json         TEXT,
    is_active            INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_projects_is_active ON projects(is_active);
"""


def _bootstrap_db(db_path: str) -> None:
    """Create the projects table using the canonical DDL from migrations."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_PROJECTS_DDL)
    conn.commit()
    conn.close()


def _make_project_dict(
    pid: str,
    *,
    name: str = "Test Project",
    is_active: bool = False,
) -> dict:
    """Return a minimal project dict suitable for SqliteProjectRepository.upsert()."""
    return {
        "id": pid,
        "name": name,
        "path": "/tmp/fake-path",
        "description": "",
        "repoUrl": "",
        "agentPlatforms": ["Claude Code"],
        "planDocsPath": "docs/project_plans/",
        "sessionsPath": "",
        "progressPath": "progress",
        "pathConfig": {},
        "testConfig": {},
        "skillMeat": {},
        "display": None,
        "is_active": is_active,
    }


# ---------------------------------------------------------------------------
# SqliteProjectRepository unit tests
# ---------------------------------------------------------------------------

class TestSqliteProjectRepositoryOrdering(unittest.TestCase):
    """(a) list_all() returns active project as list[0] (T0-001)."""

    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._tmp.name
        self._tmp.close()
        _bootstrap_db(self._db_path)
        self._repo = SqliteProjectRepository(self._db_path)

    def tearDown(self) -> None:
        self._repo.close()
        Path(self._db_path).unlink(missing_ok=True)

    def test_active_project_is_first_in_list(self) -> None:
        """Active project must be list[0] regardless of insertion order."""
        # Insert inactive project first (older created_at)
        self._repo.upsert(_make_project_dict("proj-inactive", name="Inactive", is_active=False))
        # Insert active project second (newer created_at)
        self._repo.upsert(_make_project_dict("proj-active", name="Active", is_active=True))

        rows = self._repo.list_all()
        self.assertGreaterEqual(len(rows), 2, "Expected at least 2 projects")
        self.assertEqual(
            rows[0]["id"],
            "proj-active",
            "Active project must be first in list_all() output",
        )
        self.assertTrue(
            rows[0]["is_active"],
            "First row must have is_active=True",
        )

    def test_no_active_project_still_lists_all(self) -> None:
        """When no project is active, list_all() still returns all rows."""
        self._repo.upsert(_make_project_dict("proj-alpha", is_active=False))
        self._repo.upsert(_make_project_dict("proj-beta", is_active=False))

        rows = self._repo.list_all()
        ids = {r["id"] for r in rows}
        self.assertIn("proj-alpha", ids)
        self.assertIn("proj-beta", ids)

    def test_set_active_moves_project_to_front(self) -> None:
        """set_active() followed by list_all() places the activated project first."""
        self._repo.upsert(_make_project_dict("proj-a", is_active=False))
        self._repo.upsert(_make_project_dict("proj-b", is_active=False))

        self._repo.set_active("proj-b")
        rows = self._repo.list_all()
        self.assertEqual(rows[0]["id"], "proj-b")


# ---------------------------------------------------------------------------
# Direct-count assertion tests (ADR-007 pattern)
# ---------------------------------------------------------------------------

class TestSqliteProjectRepositoryCount(unittest.TestCase):
    """(c) repo.count() matches rows written (ADR-007 direct-count assertion)."""

    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._tmp.name
        self._tmp.close()
        _bootstrap_db(self._db_path)
        self._repo = SqliteProjectRepository(self._db_path)

    def tearDown(self) -> None:
        self._repo.close()
        Path(self._db_path).unlink(missing_ok=True)

    def test_count_empty_on_fresh_db(self) -> None:
        """Fresh DB has zero project rows."""
        self.assertEqual(self._repo.count(), 0)

    def test_count_after_single_upsert(self) -> None:
        """count() == 1 after inserting one project."""
        self._repo.upsert(_make_project_dict("proj-one"))
        self.assertEqual(self._repo.count(), 1)

    def test_count_after_multiple_upserts(self) -> None:
        """count() reflects the number of distinct projects inserted."""
        self._repo.upsert(_make_project_dict("proj-x"))
        self._repo.upsert(_make_project_dict("proj-y"))
        self._repo.upsert(_make_project_dict("proj-z"))
        self.assertEqual(self._repo.count(), 3)

    def test_upsert_idempotent_does_not_inflate_count(self) -> None:
        """Upserting the same project id twice must NOT create a duplicate row."""
        self._repo.upsert(_make_project_dict("proj-dup"))
        self._repo.upsert(_make_project_dict("proj-dup", name="Updated Name"))
        self.assertEqual(
            self._repo.count(),
            1,
            "ON CONFLICT upsert must keep count at 1 for same id",
        )

    def test_count_after_set_active_unchanged(self) -> None:
        """set_active() must not alter the row count."""
        self._repo.upsert(_make_project_dict("proj-count-active"))
        before = self._repo.count()
        self._repo.set_active("proj-count-active")
        after = self._repo.count()
        self.assertEqual(before, after, "set_active() must not change count()")


# ---------------------------------------------------------------------------
# is_seed computed field tests (T0-002)
# ---------------------------------------------------------------------------

class TestIsSeedField(unittest.TestCase):
    """(b) Seed project ids have is_seed==True; others have is_seed==False."""

    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._tmp.name
        self._tmp.close()
        _bootstrap_db(self._db_path)

        # Build a DbProjectManager pointing at our temp DB, bypassing JSON bootstrap
        self._manager = DbProjectManager.__new__(DbProjectManager)
        self._manager.storage_path = Path(self._db_path)  # dummy — not used for JSON read
        self._manager._path_resolver = None  # not needed for these tests
        self._manager._db_backend = "sqlite"
        self._manager._db_path = self._db_path
        self._manager._db_dsn = ""
        self._manager._repo = None
        self._manager._projects = None
        self._manager._active_project_id = None
        self._manager._snapshot_loaded = False

        # Seed the DB directly via the repo
        repo = SqliteProjectRepository(self._db_path)
        repo.upsert(_make_project_dict("default-skillmeat", name="SkillMeat Default", is_active=True))
        repo.upsert(_make_project_dict("test-project-1", name="Test Project 1", is_active=False))
        repo.upsert(_make_project_dict("user-real-project", name="Real User Project", is_active=False))
        repo.close()

    def tearDown(self) -> None:
        Path(self._db_path).unlink(missing_ok=True)

    def test_seed_project_ids_constant(self) -> None:
        """_SEED_PROJECT_IDS must contain the two canonical seed ids."""
        self.assertIn("default-skillmeat", _SEED_PROJECT_IDS)
        self.assertIn("test-project-1", _SEED_PROJECT_IDS)

    def test_default_skillmeat_is_seed_true(self) -> None:
        """default-skillmeat project must have is_seed=True."""
        projects = self._manager.list_projects()
        by_id = {p.id: p for p in projects}
        self.assertIn("default-skillmeat", by_id, "default-skillmeat must be present")
        self.assertTrue(
            by_id["default-skillmeat"].is_seed,
            "default-skillmeat must have is_seed=True",
        )

    def test_test_project_1_is_seed_true(self) -> None:
        """test-project-1 must have is_seed=True."""
        projects = self._manager.list_projects()
        by_id = {p.id: p for p in projects}
        self.assertIn("test-project-1", by_id, "test-project-1 must be present")
        self.assertTrue(
            by_id["test-project-1"].is_seed,
            "test-project-1 must have is_seed=True",
        )

    def test_non_seed_project_is_seed_false(self) -> None:
        """A user project with a non-seed id must have is_seed=False."""
        projects = self._manager.list_projects()
        by_id = {p.id: p for p in projects}
        self.assertIn("user-real-project", by_id, "user-real-project must be present")
        self.assertFalse(
            by_id["user-real-project"].is_seed,
            "user-real-project must have is_seed=False",
        )

    def test_active_project_is_first(self) -> None:
        """Active project (default-skillmeat, is_active=True) must be list[0]."""
        projects = self._manager.list_projects()
        self.assertGreater(len(projects), 0, "list_projects() must return at least one project")
        first = projects[0]
        self.assertEqual(
            first.id,
            "default-skillmeat",
            "Active project must be list[0] — ORDER BY is_active DESC must hold",
        )

    def test_is_seed_is_model_computed_not_db_column(self) -> None:
        """is_seed must be computed from the id allowlist, not read from the DB."""
        # Even if we add a project with a non-seed id after bootstrap, it stays False
        repo = SqliteProjectRepository(self._db_path)
        repo.upsert(_make_project_dict("brand-new-id", name="Brand New"))
        repo.close()

        # Reload manager snapshot
        self._manager._snapshot_loaded = False
        projects = self._manager.list_projects()
        by_id = {p.id: p for p in projects}
        self.assertFalse(
            by_id["brand-new-id"].is_seed,
            "Dynamically added project must not be considered a seed",
        )


# ---------------------------------------------------------------------------
# get_active() regression
# ---------------------------------------------------------------------------

class TestGetActiveProject(unittest.TestCase):
    """get_active() must return the correct row after ORDER BY change."""

    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._tmp.name
        self._tmp.close()
        _bootstrap_db(self._db_path)
        self._repo = SqliteProjectRepository(self._db_path)

    def tearDown(self) -> None:
        self._repo.close()
        Path(self._db_path).unlink(missing_ok=True)

    def test_get_active_returns_active_row(self) -> None:
        """get_active() must return the project flagged is_active=1."""
        self._repo.upsert(_make_project_dict("proj-inactive-1", is_active=False))
        self._repo.upsert(_make_project_dict("proj-active-1", is_active=True))
        self._repo.upsert(_make_project_dict("proj-inactive-2", is_active=False))

        active = self._repo.get_active()
        self.assertIsNotNone(active, "get_active() must return a project when one is active")
        self.assertEqual(active["id"], "proj-active-1")
        self.assertTrue(active["is_active"])

    def test_get_active_returns_none_when_no_active(self) -> None:
        """get_active() returns None when no project has is_active=1."""
        self._repo.upsert(_make_project_dict("proj-no-active-a", is_active=False))
        self._repo.upsert(_make_project_dict("proj-no-active-b", is_active=False))

        active = self._repo.get_active()
        self.assertIsNone(active, "get_active() must return None when no active project exists")

    def test_set_active_clears_previous_active(self) -> None:
        """After set_active(new), old active project must have is_active=0."""
        self._repo.upsert(_make_project_dict("proj-old-active", is_active=True))
        self._repo.upsert(_make_project_dict("proj-new-active", is_active=False))

        self._repo.set_active("proj-new-active")

        active = self._repo.get_active()
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], "proj-new-active")

        # Direct count check: exactly 1 active row
        conn = sqlite3.connect(self._db_path)
        row = conn.execute("SELECT COUNT(*) FROM projects WHERE is_active = 1").fetchone()
        conn.close()
        self.assertEqual(row[0], 1, "Exactly one project must be active after set_active()")


if __name__ == "__main__":
    unittest.main()
