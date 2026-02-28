"""PostgreSQL implementation of TestResultRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import asyncpg


class PostgresTestResultRepository:
    """PostgreSQL-backed test result storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, result_data: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        artifacts = result_data.get("artifact_refs", result_data.get("artifact_refs_json", []))
        if isinstance(artifacts, str):
            try:
                artifacts = json.loads(artifacts)
            except Exception:
                artifacts = []
        query = """
            INSERT INTO test_results (
                run_id, test_id, status, duration_ms, error_fingerprint,
                error_message, artifact_refs_json, stdout_ref, stderr_ref, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10)
            ON CONFLICT(run_id, test_id) DO NOTHING
        """
        await self.db.execute(
            query,
            result_data["run_id"],
            result_data["test_id"],
            result_data.get("status", "passed"),
            result_data.get("duration_ms", 0),
            result_data.get("error_fingerprint", ""),
            result_data.get("error_message", ""),
            json.dumps(artifacts or []),
            result_data.get("stdout_ref", ""),
            result_data.get("stderr_ref", ""),
            result_data.get("created_at", now),
        )

    async def get_by_id(self, run_id: str, test_id: str) -> dict | None:
        row = await self.db.fetchrow(
            "SELECT * FROM test_results WHERE run_id = $1 AND test_id = $2",
            run_id,
            test_id,
        )
        return dict(row) if row else None

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None
    ) -> list[dict]:
        if project_id:
            rows = await self.db.fetch(
                """
                SELECT r.*, tr.project_id, tr.timestamp AS run_timestamp
                FROM test_results r
                JOIN test_runs tr ON tr.run_id = r.run_id
                WHERE tr.project_id = $1
                ORDER BY tr.timestamp DESC, r.created_at DESC
                LIMIT $2 OFFSET $3
                """,
                project_id,
                limit,
                offset,
            )
        else:
            rows = await self.db.fetch(
                """
                SELECT r.*, tr.project_id, tr.timestamp AS run_timestamp
                FROM test_results r
                LEFT JOIN test_runs tr ON tr.run_id = r.run_id
                ORDER BY r.created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        return [dict(row) for row in rows]

    async def delete_by_source(self, source_file: str) -> None:
        _ = source_file
