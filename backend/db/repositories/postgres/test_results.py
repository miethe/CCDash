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

    async def get_by_run(self, run_id: str) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT *
            FROM test_results
            WHERE run_id = $1
            ORDER BY test_id
            """,
            run_id,
        )
        return [dict(row) for row in rows]

    async def list_by_run_filtered(
        self,
        run_id: str,
        *,
        domain_id: str | None = None,
        statuses: list[str] | None = None,
        query: str | None = None,
        sort_by: str = "status",
        sort_order: str = "asc",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        status_tokens = [str(token or "").strip().lower() for token in (statuses or []) if str(token or "").strip()]
        token = str(query or "").strip().lower()
        order = "DESC" if str(sort_order or "").lower() == "desc" else "ASC"
        if sort_by == "duration":
            order_clause = f"r.duration_ms {order}, r.test_id ASC"
        elif sort_by == "name":
            order_clause = f"LOWER(COALESCE(d.name, r.test_id)) {order}, r.test_id ASC"
        elif sort_by == "test_id":
            order_clause = f"LOWER(r.test_id) {order}"
        else:
            status_case = (
                "CASE LOWER(r.status) "
                "WHEN 'error' THEN 0 "
                "WHEN 'failed' THEN 1 "
                "WHEN 'xpassed' THEN 2 "
                "WHEN 'running' THEN 3 "
                "WHEN 'skipped' THEN 4 "
                "WHEN 'xfailed' THEN 5 "
                "WHEN 'unknown' THEN 6 "
                "ELSE 7 END"
            )
            order_clause = f"{status_case} {order}, r.test_id ASC"

        where_clauses = ["r.run_id = $1"]
        params: list[object] = [run_id]
        bind_index = 2

        if domain_id:
            where_clauses.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM test_feature_mappings m
                    WHERE m.test_id = r.test_id
                      AND m.project_id = (
                          SELECT tr.project_id
                          FROM test_runs tr
                          WHERE tr.run_id = r.run_id
                          LIMIT 1
                      )
                      AND m.is_primary = 1
                      AND m.domain_id = ${bind_index}
                )
                """
            )
            params.append(domain_id)
            bind_index += 1

        if status_tokens:
            where_clauses.append(f"LOWER(r.status) = ANY(${bind_index}::text[])")
            params.append(status_tokens)
            bind_index += 1
        if token:
            where_clauses.append(
                "("
                f"LOWER(r.test_id) LIKE ${bind_index} "
                f"OR LOWER(COALESCE(d.name, '')) LIKE ${bind_index} "
                f"OR LOWER(COALESCE(d.path, '')) LIKE ${bind_index} "
                f"OR LOWER(COALESCE(r.error_message, '')) LIKE ${bind_index}"
                ")"
            )
            params.append(f"%{token}%")
            bind_index += 1

        where_sql = " AND ".join(where_clauses)
        count_query = (
            "SELECT COUNT(*)::int AS total "
            "FROM test_results r "
            "LEFT JOIN test_definitions d ON d.test_id = r.test_id "
            f"WHERE {where_sql}"
        )
        count_row = await self.db.fetchrow(count_query, *params)
        total = int((dict(count_row).get("total") if count_row else 0) or 0)

        data_query = (
            "SELECT r.* "
            "FROM test_results r "
            "LEFT JOIN test_definitions d ON d.test_id = r.test_id "
            f"WHERE {where_sql} "
            f"ORDER BY {order_clause} "
            f"LIMIT ${bind_index} OFFSET ${bind_index + 1}"
        )
        data_rows = await self.db.fetch(
            data_query,
            *params,
            max(1, int(limit)),
            max(0, int(offset)),
        )
        return [dict(row) for row in data_rows], total

    async def get_history_for_test(self, test_id: str, limit: int = 200) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT r.*, tr.timestamp AS run_timestamp, tr.project_id
            FROM test_results r
            LEFT JOIN test_runs tr ON tr.run_id = r.run_id
            WHERE r.test_id = $1
            ORDER BY tr.timestamp DESC, r.created_at DESC
            LIMIT $2
            """,
            test_id,
            limit,
        )
        return [dict(row) for row in rows]

    async def get_latest_status(self, test_id: str) -> dict | None:
        row = await self.db.fetchrow(
            """
            SELECT r.*, tr.timestamp AS run_timestamp, tr.project_id
            FROM test_results r
            LEFT JOIN test_runs tr ON tr.run_id = r.run_id
            WHERE r.test_id = $1
            ORDER BY tr.timestamp DESC, r.created_at DESC
            LIMIT 1
            """,
            test_id,
        )
        return dict(row) if row else None

    async def list_history_for_test(
        self,
        *,
        project_id: str,
        test_id: str,
        since: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        where_clauses = [
            "r.test_id = $1",
            "tr.project_id = $2",
        ]
        params: list[object] = [test_id, project_id]
        bind_index = 3
        if since:
            where_clauses.append(f"tr.timestamp >= ${bind_index}")
            params.append(since)
            bind_index += 1

        where_sql = " AND ".join(where_clauses)
        count_query = (
            "SELECT COUNT(*)::int AS total "
            "FROM test_results r "
            "JOIN test_runs tr ON tr.run_id = r.run_id "
            f"WHERE {where_sql}"
        )
        count_row = await self.db.fetchrow(count_query, *params)
        total = int((dict(count_row).get("total") if count_row else 0) or 0)

        data_query = (
            "SELECT "
            "  r.*, "
            "  tr.timestamp AS run_timestamp, "
            "  tr.project_id, "
            "  tr.git_sha AS run_git_sha, "
            "  tr.agent_session_id AS run_agent_session_id "
            "FROM test_results r "
            "JOIN test_runs tr ON tr.run_id = r.run_id "
            f"WHERE {where_sql} "
            "ORDER BY tr.timestamp DESC, r.created_at DESC "
            f"LIMIT ${bind_index} OFFSET ${bind_index + 1}"
        )
        rows = await self.db.fetch(
            data_query,
            *params,
            max(1, int(limit)),
            max(0, int(offset)),
        )
        return [dict(row) for row in rows], total

    async def list_latest_by_project(
        self,
        *,
        project_id: str,
        since: str | None = None,
    ) -> list[dict]:
        where_clauses = ["tr.project_id = $1"]
        params: list[object] = [project_id]
        bind_index = 2
        if since:
            where_clauses.append(f"tr.timestamp >= ${bind_index}")
            params.append(since)
            bind_index += 1

        where_sql = " AND ".join(where_clauses)
        query = (
            "WITH ranked AS ("
            "  SELECT "
            "    r.*, "
            "    tr.project_id AS run_project_id, "
            "    tr.timestamp AS run_timestamp, "
            "    tr.git_sha AS run_git_sha, "
            "    tr.branch AS run_branch, "
            "    tr.agent_session_id AS run_agent_session_id, "
            "    ROW_NUMBER() OVER ("
            "      PARTITION BY r.test_id "
            "      ORDER BY tr.timestamp DESC, r.created_at DESC"
            "    ) AS row_num "
            "  FROM test_results r "
            "  JOIN test_runs tr ON tr.run_id = r.run_id "
            f"  WHERE {where_sql}"
            ") "
            "SELECT * FROM ranked WHERE row_num = 1 "
            "ORDER BY run_timestamp DESC"
        )
        rows = await self.db.fetch(query, *params)
        return [dict(row) for row in rows]
