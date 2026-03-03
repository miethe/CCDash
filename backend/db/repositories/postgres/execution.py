"""PostgreSQL implementation of ExecutionRepository."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import asyncpg


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


class PostgresExecutionRepository:
    """Postgres-backed execution run/event/approval storage."""

    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def create_run(self, run_data: dict) -> dict:
        now = _now_iso()
        metadata = _parse_json_dict(run_data.get("metadata_json", run_data.get("metadata", {})))
        await self.db.execute(
            """
            INSERT INTO execution_runs (
                id, project_id, feature_id, provider, source_command, normalized_command, cwd,
                env_profile, recommendation_rule_id, risk_level, policy_verdict, requires_approval,
                approved_by, approved_at, status, exit_code, started_at, ended_at, retry_of_run_id,
                metadata_json, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7,
                $8, $9, $10, $11, $12,
                $13, $14, $15, $16, $17, $18, $19,
                $20::jsonb, $21, $22
            )
            """,
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
        )
        created = await self.get_run(str(run_data.get("id") or ""))
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
        columns = list(normalized.keys())
        assignments = ", ".join(f"{column} = ${idx}" for idx, column in enumerate(columns, start=1))
        params: list[object] = [normalized[column] for column in columns]
        params.append(run_id)
        await self.db.execute(
            f"UPDATE execution_runs SET {assignments} WHERE id = ${len(params)}",
            *params,
        )
        return await self.get_run(run_id)

    async def get_run(self, run_id: str) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM execution_runs WHERE id = $1", run_id)
        if not row:
            return None
        data = dict(row)
        data["metadata_json"] = _parse_json_dict(data.get("metadata_json", {}))
        data["requires_approval"] = bool(int(data.get("requires_approval") or 0))
        return data

    async def list_runs(
        self,
        project_id: str,
        *,
        feature_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        if feature_id:
            rows = await self.db.fetch(
                """
                SELECT * FROM execution_runs
                WHERE project_id = $1 AND feature_id = $2
                ORDER BY created_at DESC
                LIMIT $3 OFFSET $4
                """,
                project_id,
                feature_id,
                max(1, int(limit)),
                max(0, int(offset)),
            )
        else:
            rows = await self.db.fetch(
                """
                SELECT * FROM execution_runs
                WHERE project_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                project_id,
                max(1, int(limit)),
                max(0, int(offset)),
            )
        output: list[dict] = []
        for row in rows:
            data = dict(row)
            data["metadata_json"] = _parse_json_dict(data.get("metadata_json", {}))
            data["requires_approval"] = bool(int(data.get("requires_approval") or 0))
            output.append(data)
        return output

    async def append_run_events(self, run_id: str, events: list[dict]) -> list[dict]:
        if not events:
            return []
        lock = _RUN_EVENT_LOCKS.setdefault(run_id, asyncio.Lock())
        async with lock:
            row = await self.db.fetchrow(
                "SELECT COALESCE(MAX(sequence_no), 0) AS max_sequence FROM execution_run_events WHERE run_id = $1",
                run_id,
            )
            sequence = int((dict(row).get("max_sequence") if row else 0) or 0)

            inserted: list[dict] = []
            for event in events:
                sequence += 1
                occurred_at = str(event.get("occurred_at") or _now_iso())
                payload_json = _parse_json_dict(event.get("payload_json", event.get("payload", {})))
                await self.db.execute(
                    """
                    INSERT INTO execution_run_events (
                        run_id, sequence_no, stream, event_type, payload_text, payload_json, occurred_at
                    ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                    """,
                    run_id,
                    sequence,
                    str(event.get("stream") or "system"),
                    str(event.get("event_type") or "status"),
                    str(event.get("payload_text") or ""),
                    json.dumps(payload_json),
                    occurred_at,
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
            return inserted

    async def list_events_after_sequence(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT * FROM execution_run_events
            WHERE run_id = $1 AND sequence_no > $2
            ORDER BY sequence_no ASC
            LIMIT $3
            """,
            run_id,
            max(0, int(after_sequence)),
            max(1, int(limit)),
        )
        output: list[dict] = []
        for row in rows:
            data = dict(row)
            data["payload_json"] = _parse_json_dict(data.get("payload_json", {}))
            output.append(data)
        return output

    async def create_approval(self, approval_data: dict) -> dict:
        now = _now_iso()
        row = await self.db.fetchrow(
            """
            INSERT INTO execution_approvals (
                run_id, decision, reason, requested_at, resolved_at, requested_by, resolved_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            str(approval_data.get("run_id") or ""),
            str(approval_data.get("decision") or "pending"),
            str(approval_data.get("reason") or ""),
            str(approval_data.get("requested_at") or now),
            str(approval_data.get("resolved_at") or ""),
            str(approval_data.get("requested_by") or ""),
            str(approval_data.get("resolved_by") or ""),
        )
        return dict(row) if row else {}

    async def get_pending_approval(self, run_id: str) -> dict | None:
        row = await self.db.fetchrow(
            """
            SELECT * FROM execution_approvals
            WHERE run_id = $1 AND decision = 'pending'
            ORDER BY id DESC
            LIMIT 1
            """,
            run_id,
        )
        return dict(row) if row else None

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
        row = await self.db.fetchrow(
            """
            UPDATE execution_approvals
            SET decision = $1, reason = $2, resolved_at = $3, resolved_by = $4
            WHERE id = $5
            RETURNING *
            """,
            decision,
            reason,
            _now_iso(),
            resolved_by,
            int(pending.get("id") or 0),
        )
        return dict(row) if row else None
