"""PostgreSQL implementation of session intelligence fact storage."""
from __future__ import annotations

import json
from typing import Any

import asyncpg


class PostgresSessionIntelligenceRepository:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def replace_session_sentiment_facts(self, session_id: str, facts: list[dict[str, Any]]) -> None:
        await self.db.execute("DELETE FROM session_sentiment_facts WHERE session_id = $1", session_id)
        if not facts:
            return
        await self.db.executemany(
            """
            INSERT INTO session_sentiment_facts (
                session_id, feature_id, root_session_id, thread_session_id,
                source_message_id, source_log_id, message_index,
                sentiment_label, sentiment_score, confidence,
                heuristic_version, evidence_json
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb)
            """,
            [
                (
                    session_id,
                    str(fact.get("feature_id") or ""),
                    str(fact.get("root_session_id") or ""),
                    str(fact.get("thread_session_id") or ""),
                    str(fact.get("source_message_id") or ""),
                    str(fact.get("source_log_id") or ""),
                    int(fact.get("message_index", 0) or 0),
                    str(fact.get("sentiment_label") or "neutral"),
                    float(fact.get("sentiment_score", 0.0) or 0.0),
                    float(fact.get("confidence", 0.0) or 0.0),
                    str(fact.get("heuristic_version") or ""),
                    json.dumps(fact.get("evidence_json") or {}),
                )
                for fact in facts
            ],
        )

    async def list_session_sentiment_facts(self, session_id: str) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            """
            SELECT *
            FROM session_sentiment_facts
            WHERE session_id = $1
            ORDER BY message_index ASC, source_log_id ASC, id ASC
            """,
            session_id,
        )
        return [dict(row) for row in rows]

    async def replace_session_code_churn_facts(self, session_id: str, facts: list[dict[str, Any]]) -> None:
        await self.db.execute("DELETE FROM session_code_churn_facts WHERE session_id = $1", session_id)
        if not facts:
            return
        await self.db.executemany(
            """
            INSERT INTO session_code_churn_facts (
                session_id, feature_id, root_session_id, thread_session_id,
                file_path, first_source_log_id, last_source_log_id,
                first_message_index, last_message_index,
                touch_count, distinct_edit_turn_count, repeat_touch_count, rewrite_pass_count,
                additions_total, deletions_total, net_diff_total,
                churn_score, progress_score, low_progress_loop,
                confidence, heuristic_version, evidence_json
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22::jsonb)
            """,
            [
                (
                    session_id,
                    str(fact.get("feature_id") or ""),
                    str(fact.get("root_session_id") or ""),
                    str(fact.get("thread_session_id") or ""),
                    str(fact.get("file_path") or ""),
                    str(fact.get("first_source_log_id") or ""),
                    str(fact.get("last_source_log_id") or ""),
                    int(fact.get("first_message_index", 0) or 0),
                    int(fact.get("last_message_index", 0) or 0),
                    int(fact.get("touch_count", 0) or 0),
                    int(fact.get("distinct_edit_turn_count", 0) or 0),
                    int(fact.get("repeat_touch_count", 0) or 0),
                    int(fact.get("rewrite_pass_count", 0) or 0),
                    int(fact.get("additions_total", 0) or 0),
                    int(fact.get("deletions_total", 0) or 0),
                    int(fact.get("net_diff_total", 0) or 0),
                    float(fact.get("churn_score", 0.0) or 0.0),
                    float(fact.get("progress_score", 0.0) or 0.0),
                    bool(fact.get("low_progress_loop")),
                    float(fact.get("confidence", 0.0) or 0.0),
                    str(fact.get("heuristic_version") or ""),
                    json.dumps(fact.get("evidence_json") or {}),
                )
                for fact in facts
            ],
        )

    async def list_session_code_churn_facts(self, session_id: str) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            """
            SELECT *
            FROM session_code_churn_facts
            WHERE session_id = $1
            ORDER BY file_path ASC, id ASC
            """,
            session_id,
        )
        return [dict(row) for row in rows]

    async def replace_session_scope_drift_facts(self, session_id: str, facts: list[dict[str, Any]]) -> None:
        await self.db.execute("DELETE FROM session_scope_drift_facts WHERE session_id = $1", session_id)
        if not facts:
            return
        await self.db.executemany(
            """
            INSERT INTO session_scope_drift_facts (
                session_id, feature_id, root_session_id, thread_session_id,
                planned_path_count, actual_path_count, matched_path_count, out_of_scope_path_count,
                drift_ratio, adherence_score, confidence, heuristic_version, evidence_json
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb)
            """,
            [
                (
                    session_id,
                    str(fact.get("feature_id") or ""),
                    str(fact.get("root_session_id") or ""),
                    str(fact.get("thread_session_id") or ""),
                    int(fact.get("planned_path_count", 0) or 0),
                    int(fact.get("actual_path_count", 0) or 0),
                    int(fact.get("matched_path_count", 0) or 0),
                    int(fact.get("out_of_scope_path_count", 0) or 0),
                    float(fact.get("drift_ratio", 0.0) or 0.0),
                    float(fact.get("adherence_score", 0.0) or 0.0),
                    float(fact.get("confidence", 0.0) or 0.0),
                    str(fact.get("heuristic_version") or ""),
                    json.dumps(fact.get("evidence_json") or {}),
                )
                for fact in facts
            ],
        )

    async def list_session_scope_drift_facts(self, session_id: str) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            """
            SELECT *
            FROM session_scope_drift_facts
            WHERE session_id = $1
            ORDER BY feature_id ASC, id ASC
            """,
            session_id,
        )
        return [dict(row) for row in rows]

    async def list_backfill_sessions(
        self,
        project_id: str,
        *,
        after_started_at: str = "",
        after_session_id: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        rows = await self.db.fetch(
            """
            SELECT *
            FROM sessions
            WHERE project_id = $1
              AND (
                    $2 = ''
                    OR COALESCE(NULLIF(TRIM(started_at), ''), created_at, '') > $2
                    OR (
                        COALESCE(NULLIF(TRIM(started_at), ''), created_at, '') = $2
                        AND id > $3
                    )
                  )
            ORDER BY COALESCE(NULLIF(TRIM(started_at), ''), created_at, '') ASC, id ASC
            LIMIT $4
            """,
            project_id,
            after_started_at,
            after_session_id,
            max(1, int(limit)),
        )
        return [dict(row) for row in rows]

    async def load_backfill_checkpoint(
        self,
        project_id: str,
        *,
        checkpoint_key: str,
    ) -> dict[str, Any]:
        row = await self.db.fetchrow(
            """
            SELECT value
            FROM app_metadata
            WHERE entity_type = $1 AND entity_id = $2 AND key = $3
            LIMIT 1
            """,
            "project",
            project_id,
            checkpoint_key,
        )
        raw_value = row["value"] if row else ""
        if not isinstance(raw_value, str) or not raw_value.strip():
            return {}
        try:
            parsed = json.loads(raw_value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    async def save_backfill_checkpoint(
        self,
        project_id: str,
        checkpoint: dict[str, Any],
        *,
        checkpoint_key: str,
    ) -> None:
        payload = json.dumps(checkpoint or {})
        await self.db.execute(
            """
            INSERT INTO app_metadata (entity_type, entity_id, key, value, updated_at)
            VALUES ($1, $2, $3, $4, NOW()::text)
            ON CONFLICT(entity_type, entity_id, key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = EXCLUDED.updated_at
            """,
            "project",
            project_id,
            checkpoint_key,
            payload,
        )

    async def delete_backfill_checkpoint(
        self,
        project_id: str,
        *,
        checkpoint_key: str,
    ) -> None:
        await self.db.execute(
            """
            DELETE FROM app_metadata
            WHERE entity_type = $1 AND entity_id = $2 AND key = $3
            """,
            "project",
            project_id,
            checkpoint_key,
        )
