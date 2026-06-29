"""Synchronous SQLite repository for the projects table (P3-001).

Uses stdlib sqlite3 (not aiosqlite) so the registry can serve the
synchronous WorkspaceRegistry Protocol without any event-loop gymnastics.
This module is intentionally *not* imported from the async repository barrel
(__init__.py) – callers import it directly by module path.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.db.repositories.base import retry_on_locked_sync

logger = logging.getLogger("ccdash.db.repositories.projects")


class SqliteProjectRepository:
    """Synchronous sqlite3-backed repository for the ``projects`` table.

    Thread-safety note: sqlite3 connections are *not* thread-safe by default.
    This repository is designed to be instantiated once per process and used
    from a single thread (the main sync registry thread).  It uses
    ``check_same_thread=False`` so that brief cross-thread reads during
    startup don't crash, but callers should treat write operations as
    process-local serialised operations (which they are – registry writes are
    rare admin ops, not hot-path).
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                timeout=30,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            # Tell SQLite to wait up to 30 s before raising "database is locked"
            # instead of failing immediately.  This complements the Python-level
            # retry loop in _commit_with_retry for the cases where the OS-level
            # busy handler fires first.
            self._conn.execute("PRAGMA busy_timeout = 30000")
        return self._conn

    # ------------------------------------------------------------------
    # Locked-DB commit with exponential-backoff retry
    # ------------------------------------------------------------------

    def _commit_with_retry(self) -> None:
        """Commit the current transaction, retrying up to 3 times on lock.

        Delegates to the shared :func:`retry_on_locked_sync` helper so that
        retry/counter semantics are consistent with all other sync repositories.
        """
        conn = self._get_conn()
        retry_on_locked_sync(conn.commit, repo="projects")

    def _flush_to_db(self, rows: list[dict]) -> None:
        """Write *rows* (already formatted by ``_project_to_row``) in one
        transaction, retrying the commit on a locked database.

        All upserts execute inside a single implicit transaction; the commit
        at the end is retried with exponential backoff.
        """
        conn = self._get_conn()
        for row in rows:
            conn.execute(
                """
                INSERT INTO projects (
                    id, name, path, description, repo_url,
                    agent_platforms_json, plan_docs_path, sessions_path, progress_path,
                    path_config_json, test_config_json, skillmeat_json, display_json,
                    is_active, repo_path, updated_at
                ) VALUES (
                    :id, :name, :path, :description, :repo_url,
                    :agent_platforms_json, :plan_docs_path, :sessions_path, :progress_path,
                    :path_config_json, :test_config_json, :skillmeat_json, :display_json,
                    :is_active, :repo_path, :updated_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    path=excluded.path,
                    description=excluded.description,
                    repo_url=excluded.repo_url,
                    agent_platforms_json=excluded.agent_platforms_json,
                    plan_docs_path=excluded.plan_docs_path,
                    sessions_path=excluded.sessions_path,
                    progress_path=excluded.progress_path,
                    path_config_json=excluded.path_config_json,
                    test_config_json=excluded.test_config_json,
                    skillmeat_json=excluded.skillmeat_json,
                    display_json=excluded.display_json,
                    is_active=excluded.is_active,
                    repo_path=excluded.repo_path,
                    updated_at=excluded.updated_at
                """,
                row,
            )
        self._commit_with_retry()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ------------------------------------------------------------------
    # Table bootstrap  (migration-guard; no inline DDL)
    # ------------------------------------------------------------------

    def ensure_table(self) -> None:
        """Assert the projects table exists; raise if migrations have not run.

        The canonical DDL lives in sqlite_migrations.py (migration v30).
        P1 of the DB-remediation plan guarantees that migrations run before
        any repository method is called in production and worker paths.

        This guard verifies that invariant at runtime rather than silently
        re-creating the schema, which would mask migration failures and create
        schema drift.

        Intentional exceptions (tables that still self-create outside
        migrations, NOT refactored in T3-010):
          - planning_worktree_contexts / filesystem_scan_manifest:
            created by _ensure_planning_worktree_contexts_table() in
            sqlite_migrations.py (stored in _PLANNING_WORKTREE_CONTEXTS_DDL,
            not in the main _TABLES block).  NOT returned by
            get_sqlite_migration_tables(); self-creation is intentional.
          - test_runs / test_definitions / test_case_results /
            test_case_failure_samples / test_flakiness_observations:
            created by _ensure_test_visualizer_tables() in
            sqlite_migrations.py (stored in _TEST_VISUALIZER_TABLES).
            These ARE returned by get_sqlite_migration_tables() (governance
            scans _TEST_VISUALIZER_TABLES), but are gated by the
            CCDASH_TEST_VISUALIZER_ENABLED flag and called from the migration
            runner rather than inline in a repository.
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='projects'"
        ).fetchone()
        if row is None:
            logger.warning(
                "ensure_table: 'projects' table is absent — migrations have not run. "
                "Run the migration runner before starting the application."
            )
            raise RuntimeError(
                "projects table does not exist; migrations must run before "
                "SqliteProjectRepository is used.  "
                "Ensure run_migrations() has been called (see sqlite_migrations.py)."
            )

    # ------------------------------------------------------------------
    # Row ↔ dict helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        # Decode JSON blobs back to Python objects
        for col in ("agent_platforms_json", "path_config_json", "test_config_json",
                    "skillmeat_json", "display_json"):
            raw = d.get(col)
            if raw:
                try:
                    d[col] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    pass
        d["is_active"] = bool(d.get("is_active", 0))
        return d

    @staticmethod
    def _project_to_row(project_dict: dict) -> dict:
        """Convert a Project.model_dump() payload to flat column values."""
        now = datetime.now(timezone.utc).isoformat()

        def _json(v):
            if v is None:
                return None
            if isinstance(v, str):
                return v
            return json.dumps(v)

        return {
            "id": project_dict["id"],
            "name": project_dict["name"],
            "path": project_dict.get("path", ""),
            "description": project_dict.get("description", ""),
            "repo_url": project_dict.get("repoUrl", ""),
            "agent_platforms_json": _json(project_dict.get("agentPlatforms", ["Claude Code"])),
            "plan_docs_path": project_dict.get("planDocsPath", "docs/project_plans/"),
            "sessions_path": project_dict.get("sessionsPath", ""),
            "progress_path": project_dict.get("progressPath", "progress"),
            "path_config_json": _json(project_dict.get("pathConfig", {})),
            "test_config_json": _json(project_dict.get("testConfig", {})),
            "skillmeat_json": _json(project_dict.get("skillMeat", {})),
            "display_json": _json(project_dict.get("display")),
            "is_active": 1 if project_dict.get("is_active", False) else 0,
            "repo_path": project_dict.get("repoPath") or None,
            "updated_at": now,
        }

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_all(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY is_active DESC, created_at ASC"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_id(self, project_id: str) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_active(self) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM projects WHERE is_active = 1 LIMIT 1"
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def upsert(self, project_dict: dict) -> None:
        """Insert or update a single project row, retrying commit on lock."""
        self._flush_to_db([self._project_to_row(project_dict)])

    def set_active(self, project_id: str) -> None:
        """Set exactly one project as active (clears all others first)."""
        conn = self._get_conn()
        conn.execute("UPDATE projects SET is_active = 0")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE projects SET is_active = 1, updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        self._commit_with_retry()

    def count(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM projects").fetchone()
        return row[0] if row else 0
