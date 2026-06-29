"""Tests for Phase 1 of codex-session-ingestion-v1: cwd→project attribution.

Tests:
  - resolve_project_for_cwd: exact match, nested-worktree longest-prefix,
    no match, empty cwd, multiple candidates
  - repo_path column persists via SqliteProjectRepository (direct-count
    assertion per ADR-007)

Run with:
    backend/.venv/bin/python -m pytest backend/tests/test_codex_attribution_resolver.py -v

NEVER run unscoped `pytest backend/tests` — test_runtime_bootstrap hangs.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Module under test
from backend.db.cwd_resolver import resolve_project_for_cwd

# For the DB persistence test
from backend.db.repositories.projects import SqliteProjectRepository


# ─────────────────────────────────────────────────────────────────────────────
# Pure resolver tests (no DB)
# ─────────────────────────────────────────────────────────────────────────────


class TestResolveProjectForCwdPure(unittest.TestCase):
    """Whitebox tests for the pure resolver function."""

    def _make_project(self, project_id: str, repo_path: str | None) -> dict:
        return {"id": project_id, "repo_path": repo_path}

    def test_exact_match_returns_project_id(self):
        """Exact cwd == repo_path match returns the correct project_id."""
        projects = [self._make_project("p1", "/home/user/myrepo")]
        result = resolve_project_for_cwd("/home/user/myrepo", projects)
        self.assertEqual(result, "p1")

    def test_exact_match_with_trailing_slash_normalized(self):
        """Trailing slashes on cwd are normalized before matching."""
        projects = [self._make_project("p1", "/home/user/myrepo")]
        result = resolve_project_for_cwd("/home/user/myrepo/", projects)
        self.assertEqual(result, "p1")

    def test_nested_cwd_longest_prefix_wins(self):
        """A cwd under a repo path resolves to the correct project."""
        projects = [self._make_project("p1", "/a/b/repo")]
        result = resolve_project_for_cwd("/a/b/repo/sub/dir", projects)
        self.assertEqual(result, "p1")

    def test_nested_worktree_shortest_match_does_not_win(self):
        """Longest-prefix match means the most-specific project wins.

        Given:
          p1  repo_path = /a/b/repo
          p2  repo_path = /a/b/repo/.claude/worktrees/feat-foo

        cwd = /a/b/repo/.claude/worktrees/feat-foo/src
        Expected: p2 (longer prefix).
        """
        projects = [
            self._make_project("p1", "/a/b/repo"),
            self._make_project("p2", "/a/b/repo/.claude/worktrees/feat-foo"),
        ]
        result = resolve_project_for_cwd(
            "/a/b/repo/.claude/worktrees/feat-foo/src", projects
        )
        self.assertEqual(result, "p2")

    def test_adjacent_repo_does_not_match(self):
        """A path that starts with the same string but is a sibling, not child."""
        # /a/b/repo2 must NOT match /a/b/repo
        projects = [self._make_project("p1", "/a/b/repo")]
        result = resolve_project_for_cwd("/a/b/repo2/file.py", projects)
        self.assertIsNone(result)

    def test_no_match_returns_none(self):
        """A cwd that matches no registered repo_path returns None."""
        projects = [self._make_project("p1", "/a/b/repo")]
        result = resolve_project_for_cwd("/completely/different/path", projects)
        self.assertIsNone(result)

    def test_empty_cwd_returns_none(self):
        """Empty string cwd returns None without error."""
        projects = [self._make_project("p1", "/a/b/repo")]
        result = resolve_project_for_cwd("", projects)
        self.assertIsNone(result)

    def test_no_projects_returns_none(self):
        """Empty project list returns None."""
        result = resolve_project_for_cwd("/a/b/repo", [])
        self.assertIsNone(result)

    def test_project_without_repo_path_is_skipped(self):
        """Projects with null/empty repo_path are silently skipped."""
        projects = [
            self._make_project("p1", None),
            self._make_project("p2", ""),
            self._make_project("p3", "/a/b/repo"),
        ]
        result = resolve_project_for_cwd("/a/b/repo/src", projects)
        self.assertEqual(result, "p3")

    def test_multiple_candidates_longest_prefix_wins(self):
        """Among multiple prefix-matching projects, the longest wins."""
        projects = [
            self._make_project("p_root", "/home/user"),
            self._make_project("p_sub", "/home/user/projects/myrepo"),
            self._make_project("p_other", "/home/user/other"),
        ]
        result = resolve_project_for_cwd(
            "/home/user/projects/myrepo/src/module", projects
        )
        self.assertEqual(result, "p_sub")


# ─────────────────────────────────────────────────────────────────────────────
# DB persistence test — repo_path column write + direct-count assertion (ADR-007)
# ─────────────────────────────────────────────────────────────────────────────


def _bootstrap_projects_table(conn: sqlite3.Connection) -> None:
    """Create the minimal projects table with repo_path for test isolation.

    We do NOT run full migrations here (they touch session tables and other
    state), so we create just the projects table with the shape needed for
    the repository under test.
    """
    conn.execute(
        """
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
            repo_path            TEXT,
            created_at           TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


class TestRepoPathPersistence(unittest.TestCase):
    """ADR-007 direct-count assertion: repo_path is persisted and readable."""

    def _make_repo(self, db_path: str) -> SqliteProjectRepository:
        repo = SqliteProjectRepository(db_path)
        # Bootstrap the table directly so we don't need full migration stack.
        conn = repo._get_conn()
        _bootstrap_projects_table(conn)
        return repo

    def test_repo_path_persists_on_upsert(self):
        """repo_path written via upsert is readable back from the projects table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            repo = self._make_repo(db_path)

            project_dict = {
                "id": "proj-test-001",
                "name": "Test Project",
                "path": "/home/user/myrepo",
                "description": "",
                "repoUrl": "",
                "repoPath": "/home/user/myrepo",
                "agentPlatforms": ["Claude Code"],
                "planDocsPath": "docs/project_plans/",
                "sessionsPath": "",
                "progressPath": "progress",
                "pathConfig": {},
                "testConfig": {},
                "skillMeat": {},
                "display": None,
                "is_active": False,
            }
            repo.upsert(project_dict)

            # Direct-count assertion: exactly 1 row with the correct repo_path.
            conn = repo._get_conn()
            row = conn.execute(
                "SELECT COUNT(*) FROM projects WHERE id = ? AND repo_path = ?",
                ("proj-test-001", "/home/user/myrepo"),
            ).fetchone()
            self.assertEqual(row[0], 1, "repo_path must persist exactly one row")

    def test_repo_path_null_when_not_provided(self):
        """When repoPath is absent/None, repo_path column stores NULL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_null.db")
            repo = self._make_repo(db_path)

            project_dict = {
                "id": "proj-no-repopath",
                "name": "No RepoPath",
                "path": "/home/user/norepo",
                "description": "",
                "repoUrl": "",
                # repoPath intentionally absent (pre-v38 style record)
                "agentPlatforms": ["Claude Code"],
                "planDocsPath": "docs/project_plans/",
                "sessionsPath": "",
                "progressPath": "progress",
                "pathConfig": {},
                "testConfig": {},
                "skillMeat": {},
                "display": None,
                "is_active": False,
            }
            repo.upsert(project_dict)

            conn = repo._get_conn()
            row = conn.execute(
                "SELECT repo_path FROM projects WHERE id = ?",
                ("proj-no-repopath",),
            ).fetchone()
            self.assertIsNotNone(row, "row must exist")
            self.assertIsNone(row[0], "repo_path must be NULL when not provided")

    def test_resolver_round_trip_via_db(self):
        """End-to-end: upsert project with repo_path, read back, resolver matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_rt.db")
            repo = self._make_repo(db_path)

            project_dict = {
                "id": "proj-rt-001",
                "name": "Round Trip",
                "path": "/code/skillmeat",
                "description": "",
                "repoUrl": "",
                "repoPath": "/code/skillmeat",
                "agentPlatforms": ["Claude Code"],
                "planDocsPath": "docs/project_plans/",
                "sessionsPath": "",
                "progressPath": "progress",
                "pathConfig": {},
                "testConfig": {},
                "skillMeat": {},
                "display": None,
                "is_active": False,
            }
            repo.upsert(project_dict)

            # Read back all projects and run the resolver.
            all_projects = repo.list_all()
            result = resolve_project_for_cwd("/code/skillmeat/src/module", all_projects)
            self.assertEqual(result, "proj-rt-001")


if __name__ == "__main__":
    unittest.main()
