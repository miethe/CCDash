"""SQLite implementation of TestResultRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite


def _parse_json(value: object, default: list | dict) -> list | dict:
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (list, dict)):
                return parsed
        except Exception:
            return default
    return default


class SqliteTestResultRepository:
    """SQLite-backed test result storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def upsert(self, result_data: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        artifacts = _parse_json(result_data.get("artifact_refs", result_data.get("artifact_refs_json", [])), [])
        # Append-only: conflicts are ignored rather than updated.
        await self.db.execute(
            """
            INSERT INTO test_results (
                run_id, test_id, status, duration_ms, error_fingerprint,
                error_message, artifact_refs_json, stdout_ref, stderr_ref, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, test_id) DO NOTHING
            """,
            (
                result_data["run_id"],
                result_data["test_id"],
                result_data.get("status", "passed"),
                result_data.get("duration_ms", 0),
                result_data.get("error_fingerprint", ""),
                result_data.get("error_message", ""),
                json.dumps(artifacts),
                result_data.get("stdout_ref", ""),
                result_data.get("stderr_ref", ""),
                result_data.get("created_at", now),
            ),
        )
        await self.db.commit()

    async def get_by_id(self, run_id: str, test_id: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM test_results WHERE run_id = ? AND test_id = ?",
            (run_id, test_id),
        ) as cur:
            row = await cur.fetchone()
            return self._row_to_dict(row) if row else None

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None
    ) -> list[dict]:
        if project_id:
            query = """
                SELECT r.*, tr.project_id, tr.timestamp AS run_timestamp
                FROM test_results r
                JOIN test_runs tr ON tr.run_id = r.run_id
                WHERE tr.project_id = ?
                ORDER BY tr.timestamp DESC, r.created_at DESC
                LIMIT ? OFFSET ?
            """
            params = (project_id, limit, offset)
        else:
            query = """
                SELECT r.*, tr.project_id, tr.timestamp AS run_timestamp
                FROM test_results r
                LEFT JOIN test_runs tr ON tr.run_id = r.run_id
                ORDER BY r.created_at DESC
                LIMIT ? OFFSET ?
            """
            params = (limit, offset)

        async with self.db.execute(query, params) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def delete_by_source(self, source_file: str) -> None:
        _ = source_file

    async def get_by_run(self, run_id: str) -> list[dict]:
        async with self.db.execute(
            "SELECT * FROM test_results WHERE run_id = ? ORDER BY test_id",
            (run_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def get_history_for_test(self, test_id: str, limit: int = 200) -> list[dict]:
        async with self.db.execute(
            """
            SELECT r.*, tr.timestamp AS run_timestamp, tr.project_id
            FROM test_results r
            LEFT JOIN test_runs tr ON tr.run_id = r.run_id
            WHERE r.test_id = ?
            ORDER BY tr.timestamp DESC, r.created_at DESC
            LIMIT ?
            """,
            (test_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def get_latest_status(self, test_id: str) -> dict | None:
        async with self.db.execute(
            """
            SELECT r.*, tr.timestamp AS run_timestamp, tr.project_id
            FROM test_results r
            LEFT JOIN test_runs tr ON tr.run_id = r.run_id
            WHERE r.test_id = ?
            ORDER BY tr.timestamp DESC, r.created_at DESC
            LIMIT 1
            """,
            (test_id,),
        ) as cur:
            row = await cur.fetchone()
            return self._row_to_dict(row) if row else None

    def _row_to_dict(self, row: aiosqlite.Row | None) -> dict:
        if row is None:
            return {}
        data = dict(row)
        data["artifact_refs_json"] = _parse_json(data.get("artifact_refs_json", []), [])
        return data
