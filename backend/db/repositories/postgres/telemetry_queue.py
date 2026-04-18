"""PostgreSQL repository for outbound telemetry queue rows."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import asyncpg

from backend import config


logger = logging.getLogger("ccdash.telemetry.queue")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_payload(payload: dict[str, Any] | str) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _parse_payload(payload_json: Any) -> Any:
    if isinstance(payload_json, str) and payload_json.strip():
        try:
            return json.loads(payload_json)
        except Exception:
            return payload_json
    return payload_json


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class PostgresTelemetryQueueRepository:
    """Postgres-backed outbound telemetry queue storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def enqueue(
        self,
        session_id: str,
        project_slug: str,
        payload: dict[str, Any] | str,
        queue_id: str | None = None,
        event_type: str = "execution_outcome",
    ) -> dict[str, Any]:
        existing = await self._get_by_session_id(session_id)
        if existing is not None:
            return existing

        payload_json = _serialize_payload(payload)
        if not queue_id and isinstance(payload, dict):
            queue_id = str(payload.get("event_id") or "").strip() or None
        queue_id = queue_id or str(uuid4())
        now = _now_iso()

        pending_size = await self._count_pending()
        max_queue_size = max(1, int(config.TELEMETRY_EXPORTER_CONFIG.max_queue_size))
        if pending_size >= max_queue_size:
            logger.warning(
                "Dropping telemetry enqueue because pending queue is full",
                extra={
                    "session_id": session_id,
                    "pending_queue_size": pending_size,
                    "max_queue_size": max_queue_size,
                },
            )
            return {}

        await self.db.execute(
            """
            INSERT INTO outbound_telemetry_queue (
                id, session_id, project_slug, payload_json, event_type, status, created_at
            ) VALUES ($1, $2, $3, $4, $5, 'pending', $6)
            ON CONFLICT(session_id) DO NOTHING
            """,
            queue_id,
            session_id,
            project_slug,
            payload_json,
            event_type,
            now,
        )
        row = await self._get_by_session_id(session_id)
        return row or {}

    async def fetch_pending_batch(self, batch_size: int) -> list[dict[str, Any]]:
        size = max(1, int(batch_size))
        rows = await self.db.fetch(
            """
            SELECT *
            FROM outbound_telemetry_queue
            WHERE status IN ('pending', 'failed')
            ORDER BY CASE WHEN status = 'pending' THEN 0 ELSE 1 END, created_at ASC, id ASC
            LIMIT $1
            """,
            max(size * 10, 200),
        )
        eligible: list[dict[str, Any]] = []
        for row in rows:
            item = self._row_to_dict(row)
            if item.get("status") == "pending" or self._retry_due(item):
                eligible.append(item)
            if len(eligible) >= size:
                break
        return eligible

    async def mark_synced(self, queue_id: str) -> dict[str, Any] | None:
        await self.db.execute(
            """
            UPDATE outbound_telemetry_queue
            SET status = 'synced',
                last_attempt_at = $1,
                attempt_count = attempt_count + 1,
                last_error = NULL
            WHERE id = $2
            """,
            _now_iso(),
            queue_id,
        )
        return await self._get_by_id(queue_id)

    async def mark_failed(
        self,
        queue_id: str,
        error: str,
        attempt_count: int | None = None,
    ) -> dict[str, Any] | None:
        now = _now_iso()
        if attempt_count is None:
            await self.db.execute(
                """
                UPDATE outbound_telemetry_queue
                SET status = 'failed',
                    last_attempt_at = $1,
                    attempt_count = attempt_count + 1,
                    last_error = $2
                WHERE id = $3
                """,
                now,
                error,
                queue_id,
            )
        else:
            next_attempt = max(1, int(attempt_count))
            await self.db.execute(
                """
                UPDATE outbound_telemetry_queue
                SET status = 'failed',
                    last_attempt_at = $1,
                    attempt_count = CASE
                        WHEN $2 > attempt_count THEN $2
                        ELSE attempt_count + 1
                    END,
                    last_error = $3
                WHERE id = $4
                """,
                now,
                next_attempt,
                error,
                queue_id,
            )
        return await self._get_by_id(queue_id)

    async def mark_abandoned(
        self,
        queue_id: str,
        error: str,
        attempt_count: int | None = None,
    ) -> dict[str, Any] | None:
        now = _now_iso()
        if attempt_count is None:
            await self.db.execute(
                """
                UPDATE outbound_telemetry_queue
                SET status = 'abandoned',
                    last_attempt_at = $1,
                    attempt_count = attempt_count + 1,
                    last_error = $2
                WHERE id = $3
                """,
                now,
                error,
                queue_id,
            )
        else:
            next_attempt = max(1, int(attempt_count))
            await self.db.execute(
                """
                UPDATE outbound_telemetry_queue
                SET status = 'abandoned',
                    last_attempt_at = $1,
                    attempt_count = CASE
                        WHEN $2 > attempt_count THEN $2
                        ELSE attempt_count + 1
                    END,
                    last_error = $3
                WHERE id = $4
                """,
                now,
                next_attempt,
                error,
                queue_id,
            )
        return await self._get_by_id(queue_id)

    async def get_queue_stats(self) -> dict[str, Any]:
        rows = await self.db.fetch(
            """
            SELECT status, COUNT(*) AS count
            FROM outbound_telemetry_queue
            GROUP BY status
            """
        )
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        pending = counts.get("pending", 0)
        synced = counts.get("synced", 0)
        failed = counts.get("failed", 0)
        abandoned = counts.get("abandoned", 0)
        last_push_row = await self.db.fetchrow(
            """
            SELECT last_attempt_at
            FROM outbound_telemetry_queue
            WHERE status = 'synced' AND last_attempt_at IS NOT NULL
            ORDER BY last_attempt_at DESC
            LIMIT 1
            """
        )
        pushed_row = await self.db.fetchrow(
            """
            SELECT COUNT(*) AS count
            FROM outbound_telemetry_queue
            WHERE status = 'synced' AND last_attempt_at IS NOT NULL
              AND (last_attempt_at::timestamptz) >= ($1::timestamptz)
            """,
            (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        )
        error_row = await self.db.fetchrow(
            """
            SELECT status, last_error, COALESCE(last_attempt_at, created_at) AS error_at
            FROM outbound_telemetry_queue
            WHERE last_error IS NOT NULL AND BTRIM(last_error) <> ''
            ORDER BY COALESCE(last_attempt_at, created_at) DESC
            LIMIT 1
            """
        )
        return {
            "pending": pending,
            "synced": synced,
            "failed": failed,
            "abandoned": abandoned,
            "total": pending + synced + failed + abandoned,
            "last_push_timestamp": str(last_push_row["last_attempt_at"]) if last_push_row else "",
            "events_pushed_24h": int(pushed_row["count"]) if pushed_row else 0,
            "last_error_status": str(error_row["status"]) if error_row else "",
            "last_error": str(error_row["last_error"]) if error_row else "",
            "last_error_at": str(error_row["error_at"]) if error_row else "",
        }

    async def purge_old_synced(self, retention_days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, int(retention_days)))).isoformat()
        deleted_rows = await self.db.fetch(
            """
            DELETE FROM outbound_telemetry_queue
            WHERE status = 'synced' AND (created_at::timestamptz) < ($1::timestamptz)
            RETURNING id
            """,
            cutoff,
        )
        return len(deleted_rows)

    async def _get_by_id(self, queue_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchrow(
            "SELECT * FROM outbound_telemetry_queue WHERE id = $1 LIMIT 1",
            queue_id,
        )
        return self._row_to_dict(row) if row else None

    async def _get_by_session_id(self, session_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchrow(
            "SELECT * FROM outbound_telemetry_queue WHERE session_id = $1 LIMIT 1",
            session_id,
        )
        return self._row_to_dict(row) if row else None

    async def _count_pending(self) -> int:
        row = await self.db.fetchrow(
            "SELECT COUNT(*) AS count FROM outbound_telemetry_queue WHERE status = 'pending'"
        )
        return int(row["count"]) if row else 0

    def _row_to_dict(self, row: asyncpg.Record) -> dict[str, Any]:
        data = dict(row)
        data["payload_json"] = _parse_payload(data.get("payload_json"))
        return data

    def _retry_due(self, row: dict[str, Any]) -> bool:
        if str(row.get("status") or "") != "failed":
            return False
        attempt_count = max(1, int(row.get("attempt_count") or 1))
        delay_seconds = min(60 * (2 ** max(0, attempt_count - 1)), 14400)
        last_attempt = _parse_timestamp(row.get("last_attempt_at"))
        if last_attempt is None:
            return True
        return (datetime.now(timezone.utc) - last_attempt).total_seconds() >= delay_seconds
