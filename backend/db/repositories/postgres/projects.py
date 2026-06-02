"""Synchronous PostgreSQL repository for the projects table (P3-001).

Uses psycopg2 (synchronous) so the registry can serve the synchronous
WorkspaceRegistry Protocol without event-loop gymnastics.
psycopg2 is an optional dependency; import errors are surfaced only when
DB_BACKEND == "postgres" (i.e. when this class is actually instantiated).

This module is *not* imported from the postgres repository barrel
(__init__.py) – callers import it directly by module path.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("ccdash.db.repositories.postgres.projects")


class PostgresProjectRepository:
    """Synchronous psycopg2-backed repository for the ``projects`` table.

    Connection is created lazily on first use.  The connection string is
    derived from the existing ``CCDASH_DATABASE_URL`` env var (same source
    as the async asyncpg pool used by the rest of the backend).
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None  # psycopg2 connection

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            try:
                import psycopg2
                import psycopg2.extras
            except ImportError as exc:
                raise ImportError(
                    "psycopg2 is required for the Postgres project repository.  "
                    "Install it with: pip install psycopg2-binary"
                ) from exc
            self._conn = psycopg2.connect(self._dsn)
            self._conn.autocommit = False
        return self._conn

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None

    # ------------------------------------------------------------------
    # Table bootstrap  (idempotent; safety-net for isolated tests)
    # ------------------------------------------------------------------

    def ensure_table(self) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id                   TEXT PRIMARY KEY,
                    name                 TEXT NOT NULL,
                    path                 TEXT NOT NULL DEFAULT '',
                    description          TEXT NOT NULL DEFAULT '',
                    repo_url             TEXT NOT NULL DEFAULT '',
                    agent_platforms_json JSONB NOT NULL DEFAULT '["Claude Code"]'::jsonb,
                    plan_docs_path       TEXT NOT NULL DEFAULT 'docs/project_plans/',
                    sessions_path        TEXT NOT NULL DEFAULT '',
                    progress_path        TEXT NOT NULL DEFAULT 'progress',
                    path_config_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
                    test_config_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
                    skillmeat_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
                    display_json         JSONB,
                    is_active            BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at           TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at           TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_projects_is_active ON projects(is_active)"
            )
        conn.commit()

    # ------------------------------------------------------------------
    # Row ↔ dict helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row, col_names: list[str]) -> dict:
        d = dict(zip(col_names, row))
        # psycopg2 may already deserialise JSONB to Python objects
        # If a column came back as a string, parse it.
        for col in ("agent_platforms_json", "path_config_json", "test_config_json",
                    "skillmeat_json", "display_json"):
            v = d.get(col)
            if isinstance(v, str):
                try:
                    d[col] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    pass
        # Normalise is_active to Python bool
        d["is_active"] = bool(d.get("is_active", False))
        return d

    @staticmethod
    def _project_to_values(project_dict: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()

        def _jsonify(v):
            if v is None:
                return None
            if isinstance(v, str):
                try:
                    json.loads(v)  # already valid JSON string
                    return v
                except (json.JSONDecodeError, TypeError):
                    return json.dumps(v)
            return json.dumps(v)

        return {
            "id": project_dict["id"],
            "name": project_dict["name"],
            "path": project_dict.get("path", ""),
            "description": project_dict.get("description", ""),
            "repo_url": project_dict.get("repoUrl", ""),
            "agent_platforms_json": _jsonify(project_dict.get("agentPlatforms", ["Claude Code"])),
            "plan_docs_path": project_dict.get("planDocsPath", "docs/project_plans/"),
            "sessions_path": project_dict.get("sessionsPath", ""),
            "progress_path": project_dict.get("progressPath", "progress"),
            "path_config_json": _jsonify(project_dict.get("pathConfig", {})),
            "test_config_json": _jsonify(project_dict.get("testConfig", {})),
            "skillmeat_json": _jsonify(project_dict.get("skillMeat", {})),
            "display_json": _jsonify(project_dict.get("display")),
            "is_active": bool(project_dict.get("is_active", False)),
            "updated_at": now,
        }

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_all(self) -> list[dict]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM projects ORDER BY created_at ASC")
            col_names = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
        return [self._row_to_dict(r, col_names) for r in rows]

    def get_by_id(self, project_id: str) -> Optional[dict]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
            col_names = [desc[0] for desc in cur.description]
            row = cur.fetchone()
        return self._row_to_dict(row, col_names) if row else None

    def get_active(self) -> Optional[dict]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM projects WHERE is_active = TRUE LIMIT 1")
            col_names = [desc[0] for desc in cur.description]
            row = cur.fetchone()
        return self._row_to_dict(row, col_names) if row else None

    def upsert(self, project_dict: dict) -> None:
        v = self._project_to_values(project_dict)
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO projects (
                    id, name, path, description, repo_url,
                    agent_platforms_json, plan_docs_path, sessions_path, progress_path,
                    path_config_json, test_config_json, skillmeat_json, display_json,
                    is_active, updated_at
                ) VALUES (
                    %(id)s, %(name)s, %(path)s, %(description)s, %(repo_url)s,
                    %(agent_platforms_json)s::jsonb, %(plan_docs_path)s, %(sessions_path)s,
                    %(progress_path)s,
                    %(path_config_json)s::jsonb, %(test_config_json)s::jsonb,
                    %(skillmeat_json)s::jsonb, %(display_json)s::jsonb,
                    %(is_active)s, %(updated_at)s
                )
                ON CONFLICT(id) DO UPDATE SET
                    name=EXCLUDED.name,
                    path=EXCLUDED.path,
                    description=EXCLUDED.description,
                    repo_url=EXCLUDED.repo_url,
                    agent_platforms_json=EXCLUDED.agent_platforms_json,
                    plan_docs_path=EXCLUDED.plan_docs_path,
                    sessions_path=EXCLUDED.sessions_path,
                    progress_path=EXCLUDED.progress_path,
                    path_config_json=EXCLUDED.path_config_json,
                    test_config_json=EXCLUDED.test_config_json,
                    skillmeat_json=EXCLUDED.skillmeat_json,
                    display_json=EXCLUDED.display_json,
                    is_active=EXCLUDED.is_active,
                    updated_at=EXCLUDED.updated_at
                """,
                v,
            )
        conn.commit()

    def set_active(self, project_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("UPDATE projects SET is_active = FALSE")
            cur.execute(
                "UPDATE projects SET is_active = TRUE, updated_at = %s WHERE id = %s",
                (now, project_id),
            )
        conn.commit()

    def count(self) -> int:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM projects")
            row = cur.fetchone()
        return row[0] if row else 0
