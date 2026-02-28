"""PostgreSQL implementation of TestRunRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import asyncpg


class PostgresTestRunRepository:
    """PostgreSQL-backed test run storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, run_data: dict, project_id: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        resolved_project_id = project_id or run_data.get("project_id") or run_data.get("projectId", "")
        metadata = run_data.get("metadata", run_data.get("metadata_json", {}))
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        query = """
            INSERT INTO test_runs (
                run_id, project_id, timestamp, git_sha, branch, agent_session_id,
                env_fingerprint, trigger, status, total_tests, passed_tests,
                failed_tests, skipped_tests, duration_ms, metadata_json, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15::jsonb, $16)
            ON CONFLICT(run_id) DO UPDATE SET
                project_id=EXCLUDED.project_id,
                timestamp=EXCLUDED.timestamp,
                git_sha=EXCLUDED.git_sha,
                branch=EXCLUDED.branch,
                agent_session_id=EXCLUDED.agent_session_id,
                env_fingerprint=EXCLUDED.env_fingerprint,
                trigger=EXCLUDED.trigger,
                status=EXCLUDED.status,
                total_tests=EXCLUDED.total_tests,
                passed_tests=EXCLUDED.passed_tests,
                failed_tests=EXCLUDED.failed_tests,
                skipped_tests=EXCLUDED.skipped_tests,
                duration_ms=EXCLUDED.duration_ms,
                metadata_json=EXCLUDED.metadata_json
        """
        await self.db.execute(
            query,
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
            json.dumps(metadata or {}),
            run_data.get("created_at", now),
        )

    async def get_by_id(self, run_id: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM test_runs WHERE run_id = $1", run_id)
        return dict(row) if row else None

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None
    ) -> list[dict]:
        if project_id:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM test_runs
                WHERE project_id = $1
                ORDER BY timestamp DESC
                LIMIT $2 OFFSET $3
                """,
                project_id,
                limit,
                offset,
            )
        else:
            rows = await self.db.fetch(
                "SELECT * FROM test_runs ORDER BY timestamp DESC LIMIT $1 OFFSET $2",
                limit,
                offset,
            )
        return [dict(row) for row in rows]

    async def delete_by_source(self, source_file: str) -> None:
        _ = source_file
