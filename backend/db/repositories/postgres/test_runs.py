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

    async def list_by_project(self, project_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
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
        return [dict(row) for row in rows]

    async def list_filtered(
        self,
        project_id: str,
        *,
        agent_session_id: str | None = None,
        feature_id: str | None = None,
        git_sha: str | None = None,
        since: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        where_clauses = ["tr.project_id = $1"]
        params: list[object] = [project_id]
        bind_index = 2

        if agent_session_id:
            where_clauses.append(f"tr.agent_session_id = ${bind_index}")
            params.append(agent_session_id)
            bind_index += 1
        if git_sha:
            where_clauses.append(f"tr.git_sha = ${bind_index}")
            params.append(git_sha)
            bind_index += 1
        if since:
            where_clauses.append(f"tr.timestamp >= ${bind_index}")
            params.append(since)
            bind_index += 1
        if feature_id:
            where_clauses.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM test_results r
                    JOIN test_feature_mappings m
                      ON m.project_id = tr.project_id
                     AND m.test_id = r.test_id
                     AND m.is_primary = 1
                    WHERE r.run_id = tr.run_id
                      AND m.feature_id = ${bind_index}
                )
                """
            )
            params.append(feature_id)
            bind_index += 1

        where_sql = " AND ".join(where_clauses)
        count_row = await self.db.fetchrow(
            f"SELECT COUNT(*)::int AS total FROM test_runs tr WHERE {where_sql}",
            *params,
        )
        total = int((dict(count_row).get("total") if count_row else 0) or 0)

        data_query = (
            "SELECT tr.* "
            "FROM test_runs tr "
            f"WHERE {where_sql} "
            "ORDER BY tr.timestamp DESC "
            f"LIMIT ${bind_index} OFFSET ${bind_index + 1}"
        )
        rows = await self.db.fetch(
            data_query,
            *params,
            max(1, int(limit)),
            max(0, int(offset)),
        )
        return [dict(row) for row in rows], total

    async def list_by_session(
        self,
        project_id: str,
        agent_session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT *
            FROM test_runs
            WHERE project_id = $1 AND agent_session_id = $2
            ORDER BY timestamp DESC
            LIMIT $3 OFFSET $4
            """,
            project_id,
            agent_session_id,
            limit,
            offset,
        )
        return [dict(row) for row in rows]

    async def get_latest_for_feature(self, project_id: str, feature_id: str) -> dict | None:
        row = await self.db.fetchrow(
            """
            SELECT DISTINCT tr.*
            FROM test_runs tr
            JOIN test_results r ON r.run_id = tr.run_id
            JOIN test_feature_mappings m ON m.test_id = r.test_id
            WHERE tr.project_id = $1 AND m.project_id = $1 AND m.feature_id = $2
            ORDER BY tr.timestamp DESC
            LIMIT 1
            """,
            project_id,
            feature_id,
        )
        return dict(row) if row else None
