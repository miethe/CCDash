"""SQLite implementation of TestRunRepository."""
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


class SqliteTestRunRepository:
    """SQLite-backed test run storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert(self, run_data: dict, project_id: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        resolved_project_id = project_id or run_data.get("project_id") or run_data.get("projectId", "")
        metadata = _parse_json(run_data.get("metadata", run_data.get("metadata_json", {})), {})
        await self.db.execute(
            """
            INSERT INTO test_runs (
                run_id, project_id, timestamp, git_sha, branch, agent_session_id,
                env_fingerprint, trigger, status, total_tests, passed_tests,
                failed_tests, skipped_tests, duration_ms, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                project_id=excluded.project_id,
                timestamp=excluded.timestamp,
                git_sha=excluded.git_sha,
                branch=excluded.branch,
                agent_session_id=excluded.agent_session_id,
                env_fingerprint=excluded.env_fingerprint,
                trigger=excluded.trigger,
                status=excluded.status,
                total_tests=excluded.total_tests,
                passed_tests=excluded.passed_tests,
                failed_tests=excluded.failed_tests,
                skipped_tests=excluded.skipped_tests,
                duration_ms=excluded.duration_ms,
                metadata_json=excluded.metadata_json
            """,
            (
                run_data["run_id"],
                resolved_project_id,
                run_data.get("timestamp", now),
                run_data.get("git_sha", ""),
                run_data.get("branch", ""),
                run_data.get("agent_session_id", ""),
                run_data.get("env_fingerprint", ""),
                run_data.get("trigger", "local"),
                run_data.get("status", "complete"),
                run_data.get("total_tests", 0),
                run_data.get("passed_tests", 0),
                run_data.get("failed_tests", 0),
                run_data.get("skipped_tests", 0),
                run_data.get("duration_ms", 0),
                json.dumps(metadata),
                run_data.get("created_at", now),
            ),
        )
        await self.db.commit()

    async def get_by_id(self, run_id: str) -> dict | None:
        async with self.db.execute("SELECT * FROM test_runs WHERE run_id = ?", (run_id,)) as cur:
            row = await cur.fetchone()
            return self._row_to_dict(row) if row else None

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None
    ) -> list[dict]:
        if project_id:
            return await self.list_by_project(project_id=project_id, limit=limit, offset=offset)

        async with self.db.execute(
            "SELECT * FROM test_runs ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def delete_by_source(self, source_file: str) -> None:
        _ = source_file

    async def list_by_project(self, project_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM test_runs WHERE project_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (project_id, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def list_by_session(
        self,
        project_id: str,
        agent_session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        async with self.db.execute(
            """
            SELECT *
            FROM test_runs
            WHERE project_id = ? AND agent_session_id = ?
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            (project_id, agent_session_id, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def get_latest_for_feature(self, project_id: str, feature_id: str) -> dict | None:
        async with self.db.execute(
            """
            SELECT DISTINCT tr.*
            FROM test_runs tr
            JOIN test_results r ON r.run_id = tr.run_id
            JOIN test_feature_mappings m ON m.test_id = r.test_id
            WHERE tr.project_id = ? AND m.project_id = ? AND m.feature_id = ?
            ORDER BY tr.timestamp DESC
            LIMIT 1
            """,
            (project_id, project_id, feature_id),
        ) as cur:
            row = await cur.fetchone()
            return self._row_to_dict(row) if row else None

    def _row_to_dict(self, row: aiosqlite.Row | None) -> dict:
        if row is None:
            return {}
        data = dict(row)
        data["metadata_json"] = _parse_json(data.get("metadata_json", {}), {})
        return data
