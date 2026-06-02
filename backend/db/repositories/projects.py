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
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ------------------------------------------------------------------
    # Table bootstrap  (idempotent; runs once on first use)
    # ------------------------------------------------------------------

    def ensure_table(self) -> None:
        """Create the projects table if it does not already exist.

        The canonical DDL lives in sqlite_migrations.py (v30).  This is a
        safety-net so the repository works even when the async migration path
        hasn't run yet (e.g. in isolated unit tests).
        """
        conn = self._get_conn()
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
                created_at           TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_projects_is_active ON projects(is_active)"
        )
        conn.commit()

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
            "updated_at": now,
        }

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_all(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY created_at ASC"
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
        row = self._project_to_row(project_dict)
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO projects (
                id, name, path, description, repo_url,
                agent_platforms_json, plan_docs_path, sessions_path, progress_path,
                path_config_json, test_config_json, skillmeat_json, display_json,
                is_active, updated_at
            ) VALUES (
                :id, :name, :path, :description, :repo_url,
                :agent_platforms_json, :plan_docs_path, :sessions_path, :progress_path,
                :path_config_json, :test_config_json, :skillmeat_json, :display_json,
                :is_active, :updated_at
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
                updated_at=excluded.updated_at
            """,
            row,
        )
        conn.commit()

    def set_active(self, project_id: str) -> None:
        """Set exactly one project as active (clears all others first)."""
        conn = self._get_conn()
        conn.execute("UPDATE projects SET is_active = 0")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE projects SET is_active = 1, updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        conn.commit()

    def count(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM projects").fetchone()
        return row[0] if row else 0
