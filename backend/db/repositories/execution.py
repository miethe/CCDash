"""SQLite implementation of ExecutionRepository."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from backend.application.live_updates.domain_events import (
    publish_execution_run_events,
    publish_execution_run_snapshot,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_bool_int(value: object) -> int:
    return 1 if bool(value) else 0


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


_RUN_EVENT_LOCKS: dict[str, asyncio.Lock] = {}
_LOCK_RETRY_ATTEMPTS = 8
_LOCK_RETRY_BASE_SECONDS = 0.05


def _is_locked_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "database is locked" in message or "database table is locked" in message


class SqliteExecutionRepository:
    """SQLite-backed execution run/event/approval storage."""

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

    async def create_run(self, run_data: dict) -> dict:
        now = _now_iso()
        metadata = _parse_json_dict(run_data.get("metadata_json", run_data.get("metadata", {})))
        await self._execute_write(
            """
            INSERT INTO execution_runs (
                id, project_id, feature_id, provider, source_command, normalized_command, cwd,
                env_profile, recommendation_rule_id, risk_level, policy_verdict, requires_approval,
                approved_by, approved_at, status, exit_code, started_at, ended_at, retry_of_run_id,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(run_data.get("id") or ""),
                str(run_data.get("project_id") or ""),
                str(run_data.get("feature_id") or ""),
                str(run_data.get("provider") or "local"),
                str(run_data.get("source_command") or ""),
                str(run_data.get("normalized_command") or ""),
                str(run_data.get("cwd") or ""),
                str(run_data.get("env_profile") or "default"),
                str(run_data.get("recommendation_rule_id") or ""),
                str(run_data.get("risk_level") or "medium"),
                str(run_data.get("policy_verdict") or "allow"),
                _to_bool_int(run_data.get("requires_approval", False)),
                str(run_data.get("approved_by") or ""),
                str(run_data.get("approved_at") or ""),
                str(run_data.get("status") or "queued"),
                run_data.get("exit_code"),
                str(run_data.get("started_at") or ""),
                str(run_data.get("ended_at") or ""),
                str(run_data.get("retry_of_run_id") or ""),
                json.dumps(metadata),
                str(run_data.get("created_at") or now),
                str(run_data.get("updated_at") or now),
            ),
        )
        await self._commit_with_retry()
        created = await self.get_run(str(run_data.get("id") or ""))
        await publish_execution_run_snapshot(created)
        return created or {}

    async def update_run(self, run_id: str, updates: dict) -> dict | None:
        normalized = dict(updates or {})
        if not normalized:
            return await self.get_run(run_id)

        if "metadata" in normalized and "metadata_json" not in normalized:
            normalized["metadata_json"] = normalized.pop("metadata")

        if "metadata_json" in normalized:
            normalized["metadata_json"] = json.dumps(_parse_json_dict(normalized.get("metadata_json")))

        if "requires_approval" in normalized:
            normalized["requires_approval"] = _to_bool_int(normalized.get("requires_approval"))

        normalized.setdefault("updated_at", _now_iso())
        assignments = ", ".join(f"{column} = ?" for column in normalized.keys())
        params = [normalized[column] for column in normalized.keys()]
        params.append(run_id)
        await self._execute_write(
            f"UPDATE execution_runs SET {assignments} WHERE id = ?",
            tuple(params),
        )
        await self._commit_with_retry()
        updated = await self.get_run(run_id)
        await publish_execution_run_snapshot(updated)
        return updated

    async def get_run(self, run_id: str) -> dict | None:
        async with self.db.execute("SELECT * FROM execution_runs WHERE id = ?", (run_id,)) as cur:
            row = await cur.fetchone()
        return self._run_row_to_dict(row) if row else None

    async def list_runs(
        self,
        project_id: str,
        *,
        feature_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        params: list[object] = [project_id]
        where = "project_id = ?"
        if feature_id:
            where += " AND feature_id = ?"
            params.append(feature_id)
        params.extend([max(1, int(limit)), max(0, int(offset))])
        async with self.db.execute(
            f"""
            SELECT * FROM execution_runs
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        ) as cur:
            rows = await cur.fetchall()
        return [self._run_row_to_dict(row) for row in rows]

    async def append_run_events(self, run_id: str, events: list[dict]) -> list[dict]:
        if not events:
            return []
        lock = _RUN_EVENT_LOCKS.setdefault(run_id, asyncio.Lock())
        async with lock:
            async with self.db.execute(
                "SELECT COALESCE(MAX(sequence_no), 0) FROM execution_run_events WHERE run_id = ?",
                (run_id,),
            ) as cur:
                row = await cur.fetchone()
                sequence = int((row[0] if row else 0) or 0)

            inserted: list[dict] = []
            for event in events:
                sequence += 1
                occurred_at = str(event.get("occurred_at") or _now_iso())
                payload_json = _parse_json_dict(event.get("payload_json", event.get("payload", {})))
                await self._execute_write(
                    """
                    INSERT INTO execution_run_events (
                        run_id, sequence_no, stream, event_type, payload_text, payload_json, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        sequence,
                        str(event.get("stream") or "system"),
                        str(event.get("event_type") or "status"),
                        str(event.get("payload_text") or ""),
                        json.dumps(payload_json),
                        occurred_at,
                    ),
                )
                inserted.append(
                    {
                        "run_id": run_id,
                        "sequence_no": sequence,
                        "stream": str(event.get("stream") or "system"),
                        "event_type": str(event.get("event_type") or "status"),
                        "payload_text": str(event.get("payload_text") or ""),
                        "payload_json": payload_json,
                        "occurred_at": occurred_at,
                    }
                )
            await self._commit_with_retry()
            await publish_execution_run_events(run_id, inserted)
            return inserted

    async def list_events_after_sequence(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> list[dict]:
        async with self.db.execute(
            """
            SELECT * FROM execution_run_events
            WHERE run_id = ? AND sequence_no > ?
            ORDER BY sequence_no ASC
            LIMIT ?
            """,
            (run_id, max(0, int(after_sequence)), max(1, int(limit))),
        ) as cur:
            rows = await cur.fetchall()
        return [self._event_row_to_dict(row) for row in rows]

    async def create_approval(self, approval_data: dict) -> dict:
        now = _now_iso()
        await self._execute_write(
            """
            INSERT INTO execution_approvals (
                run_id, decision, reason, requested_at, resolved_at, requested_by, resolved_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(approval_data.get("run_id") or ""),
                str(approval_data.get("decision") or "pending"),
                str(approval_data.get("reason") or ""),
                str(approval_data.get("requested_at") or now),
                str(approval_data.get("resolved_at") or ""),
                str(approval_data.get("requested_by") or ""),
                str(approval_data.get("resolved_by") or ""),
            ),
        )
        await self._commit_with_retry()
        async with self.db.execute(
            "SELECT * FROM execution_approvals WHERE run_id = ? ORDER BY id DESC LIMIT 1",
            (str(approval_data.get("run_id") or ""),),
        ) as cur:
            row = await cur.fetchone()
        return self._approval_row_to_dict(row) if row else {}

    async def get_pending_approval(self, run_id: str) -> dict | None:
        async with self.db.execute(
            """
            SELECT * FROM execution_approvals
            WHERE run_id = ? AND decision = 'pending'
            ORDER BY id DESC
            LIMIT 1
            """,
            (run_id,),
        ) as cur:
            row = await cur.fetchone()
        return self._approval_row_to_dict(row) if row else None

    async def resolve_approval(
        self,
        run_id: str,
        *,
        decision: str,
        reason: str = "",
        resolved_by: str = "",
    ) -> dict | None:
        pending = await self.get_pending_approval(run_id)
        if not pending:
            return None

        now = _now_iso()
        await self._execute_write(
            """
            UPDATE execution_approvals
            SET decision = ?, reason = ?, resolved_at = ?, resolved_by = ?
            WHERE id = ?
            """,
            (
                decision,
                reason,
                now,
                resolved_by,
                int(pending.get("id") or 0),
            ),
        )
        await self._commit_with_retry()
        async with self.db.execute(
            "SELECT * FROM execution_approvals WHERE id = ? LIMIT 1",
            (int(pending.get("id") or 0),),
        ) as cur:
            row = await cur.fetchone()
        return self._approval_row_to_dict(row) if row else None

    def _run_row_to_dict(self, row: aiosqlite.Row) -> dict:
        data = dict(row)
        data["metadata_json"] = _parse_json_dict(data.get("metadata_json", {}))
        data["requires_approval"] = bool(int(data.get("requires_approval") or 0))
        return data

    def _event_row_to_dict(self, row: aiosqlite.Row) -> dict:
        data = dict(row)
        data["payload_json"] = _parse_json_dict(data.get("payload_json", {}))
        return data

    def _approval_row_to_dict(self, row: aiosqlite.Row) -> dict:
        return dict(row)
