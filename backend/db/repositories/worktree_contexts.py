"""SQLite implementation of WorktreeContextRepository (PCP-501)."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_json_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


_LOCK_RETRY_ATTEMPTS = 8
_LOCK_RETRY_BASE_SECONDS = 0.05


def _is_locked_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "database is locked" in message or "database table is locked" in message


class SqliteWorktreeContextRepository:
    """SQLite-backed planning worktree context storage."""

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def _execute_write(self, sql: str, params: tuple[Any, ...]) -> None:
        for attempt in range(_LOCK_RETRY_ATTEMPTS):
            try:
                await self.db.execute(sql, params)
                return
            except aiosqlite.OperationalError as exc:
                if not _is_locked_error(exc) or attempt >= _LOCK_RETRY_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(_LOCK_RETRY_BASE_SECONDS * (2 ** attempt))

    async def _commit_with_retry(self) -> None:
        for attempt in range(_LOCK_RETRY_ATTEMPTS):
            try:
                await self.db.commit()
                return
            except aiosqlite.OperationalError as exc:
                if not _is_locked_error(exc) or attempt >= _LOCK_RETRY_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(_LOCK_RETRY_BASE_SECONDS * (2 ** attempt))

    async def create(self, data: dict) -> dict:
        now = _now_iso()
        context_id = str(data.get("id") or uuid.uuid4().hex)
        metadata = _parse_json_dict(data.get("metadata_json", data.get("metadata", {})))
        await self._execute_write(
            """
            INSERT INTO planning_worktree_contexts (
                id, project_id, feature_id, phase_number, batch_id,
                branch, worktree_path, base_branch, base_commit_sha,
                status, last_run_id, provider, notes, metadata_json,
                created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                context_id,
                str(data.get("project_id") or ""),
                str(data.get("feature_id") or ""),
                data.get("phase_number"),
                str(data.get("batch_id") or ""),
                str(data.get("branch") or ""),
                str(data.get("worktree_path") or ""),
                str(data.get("base_branch") or ""),
                str(data.get("base_commit_sha") or ""),
                str(data.get("status") or "draft"),
                str(data.get("last_run_id") or ""),
                str(data.get("provider") or "local"),
                str(data.get("notes") or ""),
                json.dumps(metadata),
                str(data.get("created_by") or ""),
                str(data.get("created_at") or now),
                str(data.get("updated_at") or now),
            ),
        )
        await self._commit_with_retry()
        return await self.get_by_id(context_id) or {}

    async def update(self, context_id: str, updates: dict) -> dict | None:
        normalized = dict(updates or {})
        if not normalized:
            return await self.get_by_id(context_id)

        if "metadata" in normalized and "metadata_json" not in normalized:
            normalized["metadata_json"] = normalized.pop("metadata")

        if "metadata_json" in normalized:
            normalized["metadata_json"] = json.dumps(_parse_json_dict(normalized.get("metadata_json")))

        normalized.setdefault("updated_at", _now_iso())
        assignments = ", ".join(f"{column} = ?" for column in normalized.keys())
        params: list[Any] = [normalized[column] for column in normalized.keys()]
        params.append(context_id)
        await self._execute_write(
            f"UPDATE planning_worktree_contexts SET {assignments} WHERE id = ?",
            tuple(params),
        )
        await self._commit_with_retry()
        return await self.get_by_id(context_id)

    async def get_by_id(self, context_id: str) -> dict | None:
        async with self.db.execute(
            "SELECT * FROM planning_worktree_contexts WHERE id = ?", (context_id,)
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_dict(row) if row else None

    async def list(
        self,
        project_id: str,
        *,
        feature_id: str | None = None,
        phase_number: int | None = None,
        batch_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        params: list[Any] = [project_id]
        where = "project_id = ?"
        if feature_id is not None:
            where += " AND feature_id = ?"
            params.append(feature_id)
        if phase_number is not None:
            where += " AND phase_number = ?"
            params.append(phase_number)
        if batch_id is not None:
            where += " AND batch_id = ?"
            params.append(batch_id)
        if status is not None:
            where += " AND status = ?"
            params.append(status)
        params.extend([max(1, int(limit)), max(0, int(offset))])
        async with self.db.execute(
            f"""
            SELECT * FROM planning_worktree_contexts
            WHERE {where}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def count(
        self,
        project_id: str,
        *,
        feature_id: str | None = None,
        phase_number: int | None = None,
        batch_id: str | None = None,
        status: str | None = None,
    ) -> int:
        params: list[Any] = [project_id]
        where = "project_id = ?"
        if feature_id is not None:
            where += " AND feature_id = ?"
            params.append(feature_id)
        if phase_number is not None:
            where += " AND phase_number = ?"
            params.append(phase_number)
        if batch_id is not None:
            where += " AND batch_id = ?"
            params.append(batch_id)
        if status is not None:
            where += " AND status = ?"
            params.append(status)
        async with self.db.execute(
            f"SELECT COUNT(*) FROM planning_worktree_contexts WHERE {where}",
            tuple(params),
        ) as cur:
            row = await cur.fetchone()
        return int((row[0] if row else 0) or 0)

    async def delete(self, context_id: str) -> bool:
        async with self.db.execute(
            "SELECT id FROM planning_worktree_contexts WHERE id = ?", (context_id,)
        ) as cur:
            exists = await cur.fetchone()
        if not exists:
            return False
        await self._execute_write(
            "DELETE FROM planning_worktree_contexts WHERE id = ?", (context_id,)
        )
        await self._commit_with_retry()
        return True

    def _row_to_dict(self, row: aiosqlite.Row) -> dict:
        data = dict(row)
        data["metadata"] = _parse_json_dict(data.pop("metadata_json", {}))
        return data
