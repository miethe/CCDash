"""SQLite implementation of TestIntegrityRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite


def _parse_json(value: object, default: dict | list) -> dict | list:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            return default
    return default


class SqliteTestIntegrityRepository:
    """SQLite-backed integrity signal storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert(self, signal_data: dict, project_id: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        resolved_project_id = project_id or signal_data.get("project_id") or signal_data.get("projectId", "")
        details = _parse_json(signal_data.get("details", signal_data.get("details_json", {})), {})
        linked_runs = _parse_json(
            signal_data.get("linked_run_ids", signal_data.get("linked_run_ids_json", [])),
            [],
        )
        await self.db.execute(
            """
            INSERT INTO test_integrity_signals (
                signal_id, project_id, git_sha, file_path, test_id, signal_type,
                severity, details_json, linked_run_ids_json, agent_session_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(signal_id) DO UPDATE SET
                project_id=excluded.project_id,
                git_sha=excluded.git_sha,
                file_path=excluded.file_path,
                test_id=excluded.test_id,
                signal_type=excluded.signal_type,
                severity=excluded.severity,
                details_json=excluded.details_json,
                linked_run_ids_json=excluded.linked_run_ids_json,
                agent_session_id=excluded.agent_session_id
            """,
            (
                signal_data["signal_id"],
                resolved_project_id,
                signal_data.get("git_sha", ""),
                signal_data.get("file_path", ""),
                signal_data.get("test_id"),
                signal_data.get("signal_type", ""),
                signal_data.get("severity", "medium"),
                json.dumps(details),
                json.dumps(linked_runs),
                signal_data.get("agent_session_id", ""),
                signal_data.get("created_at", now),
            ),
        )
        await self.db.commit()

    async def get_by_id(self, signal_id: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM test_integrity_signals WHERE signal_id = ?",
            (signal_id,),
        ) as cur:
            row = await cur.fetchone()
            return self._row_to_dict(row) if row else None

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None
    ) -> list[dict]:
        if project_id:
            return await self.list_by_project(project_id=project_id, limit=limit, offset=offset)
        async with self.db.execute(
            "SELECT * FROM test_integrity_signals ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def delete_by_source(self, source_file: str) -> None:
        _ = source_file

    async def list_by_project(self, project_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        async with self.db.execute(
            """
            SELECT *
            FROM test_integrity_signals
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (project_id, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def list_by_sha(self, project_id: str, git_sha: str, limit: int = 100) -> list[dict]:
        async with self.db.execute(
            """
            SELECT *
            FROM test_integrity_signals
            WHERE project_id = ? AND git_sha = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project_id, git_sha, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def list_since(self, project_id: str, since: str, limit: int = 100) -> list[dict]:
        async with self.db.execute(
            """
            SELECT *
            FROM test_integrity_signals
            WHERE project_id = ? AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project_id, since, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: aiosqlite.Row | None) -> dict:
        if row is None:
            return {}
        data = dict(row)
        data["details_json"] = _parse_json(data.get("details_json", {}), {})
        data["linked_run_ids_json"] = _parse_json(data.get("linked_run_ids_json", []), [])
        return data
