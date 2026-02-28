"""PostgreSQL implementation of TestIntegrityRepository."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import asyncpg


class PostgresTestIntegrityRepository:
    """PostgreSQL-backed integrity signal storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def upsert(self, signal_data: dict, project_id: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        resolved_project_id = project_id or signal_data.get("project_id") or signal_data.get("projectId", "")
        details = signal_data.get("details", signal_data.get("details_json", {}))
        linked_runs = signal_data.get("linked_run_ids", signal_data.get("linked_run_ids_json", []))
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except Exception:
                details = {}
        if isinstance(linked_runs, str):
            try:
                linked_runs = json.loads(linked_runs)
            except Exception:
                linked_runs = []

        query = """
            INSERT INTO test_integrity_signals (
                signal_id, project_id, git_sha, file_path, test_id, signal_type,
                severity, details_json, linked_run_ids_json, agent_session_id, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11)
            ON CONFLICT(signal_id) DO UPDATE SET
                project_id=EXCLUDED.project_id,
                git_sha=EXCLUDED.git_sha,
                file_path=EXCLUDED.file_path,
                test_id=EXCLUDED.test_id,
                signal_type=EXCLUDED.signal_type,
                severity=EXCLUDED.severity,
                details_json=EXCLUDED.details_json,
                linked_run_ids_json=EXCLUDED.linked_run_ids_json,
                agent_session_id=EXCLUDED.agent_session_id
        """
        await self.db.execute(
            query,
            signal_data["signal_id"],
            resolved_project_id,
            signal_data.get("git_sha", ""),
            signal_data.get("file_path", ""),
            signal_data.get("test_id"),
            signal_data.get("signal_type", ""),
            signal_data.get("severity", "medium"),
            json.dumps(details or {}),
            json.dumps(linked_runs or []),
            signal_data.get("agent_session_id", ""),
            signal_data.get("created_at", now),
        )

    async def get_by_id(self, signal_id: str) -> dict | None:
        row = await self.db.fetchrow(
            "SELECT * FROM test_integrity_signals WHERE signal_id = $1",
            signal_id,
        )
        return dict(row) if row else None

    async def list_paginated(
        self, offset: int, limit: int, project_id: str | None = None
    ) -> list[dict]:
        if project_id:
            rows = await self.db.fetch(
                """
                SELECT *
                FROM test_integrity_signals
                WHERE project_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                project_id,
                limit,
                offset,
            )
        else:
            rows = await self.db.fetch(
                "SELECT * FROM test_integrity_signals ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit,
                offset,
            )
        return [dict(row) for row in rows]

    async def delete_by_source(self, source_file: str) -> None:
        _ = source_file
