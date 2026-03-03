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

    async def list_by_run_filtered(
        self,
        run_id: str,
        *,
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
            # Failed/error/xpassed first when ASC to prioritize triage.
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

        where_clauses = ["r.run_id = ?"]
        params: list[object] = [run_id]
        if status_tokens:
            placeholders = ",".join("?" for _ in status_tokens)
            where_clauses.append(f"LOWER(r.status) IN ({placeholders})")
            params.extend(status_tokens)
        if token:
            where_clauses.append(
                "("
                "LOWER(r.test_id) LIKE ? "
                "OR LOWER(COALESCE(d.name, '')) LIKE ? "
                "OR LOWER(COALESCE(d.path, '')) LIKE ? "
                "OR LOWER(COALESCE(r.error_message, '')) LIKE ?"
                ")"
            )
            like = f"%{token}%"
            params.extend([like, like, like, like])

        where_sql = " AND ".join(where_clauses)
        count_query = (
            "SELECT COUNT(*) "
            "FROM test_results r "
            "LEFT JOIN test_definitions d ON d.test_id = r.test_id "
            "WHERE "
            + where_sql
        )
        async with self.db.execute(count_query, tuple(params)) as cur:
            row = await cur.fetchone()
            total = int((row[0] if row else 0) or 0)

        data_query = (
            "SELECT r.* "
            "FROM test_results r "
            "LEFT JOIN test_definitions d ON d.test_id = r.test_id "
            "WHERE "
            + where_sql
            + f" ORDER BY {order_clause} LIMIT ? OFFSET ?"
        )
        data_params = [*params, max(1, int(limit)), max(0, int(offset))]
        async with self.db.execute(data_query, tuple(data_params)) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows], total

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
            "r.test_id = ?",
            "tr.project_id = ?",
        ]
        params: list[object] = [test_id, project_id]
        if since:
            where_clauses.append("tr.timestamp >= ?")
            params.append(since)

        where_sql = " AND ".join(where_clauses)
        count_query = (
            "SELECT COUNT(*) "
            "FROM test_results r "
            "JOIN test_runs tr ON tr.run_id = r.run_id "
            f"WHERE {where_sql}"
        )
        async with self.db.execute(count_query, tuple(params)) as cur:
            row = await cur.fetchone()
            total = int((row[0] if row else 0) or 0)

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
            "LIMIT ? OFFSET ?"
        )
        data_params = [*params, max(1, int(limit)), max(0, int(offset))]
        async with self.db.execute(data_query, tuple(data_params)) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows], total

    async def list_latest_by_project(
        self,
        *,
        project_id: str,
        since: str | None = None,
    ) -> list[dict]:
        where_sql = "tr.project_id = ?"
        params: list[object] = [project_id]
        if since:
            where_sql += " AND tr.timestamp >= ?"
            params.append(since)

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
        async with self.db.execute(query, tuple(params)) as cur:
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
