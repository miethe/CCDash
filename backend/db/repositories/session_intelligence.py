"""SQLite implementation of session intelligence fact storage."""
from __future__ import annotations

import json
from typing import Any

import aiosqlite


def _dumps(value: object) -> str:
    return json.dumps(value or {})


def _loads_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class SqliteSessionIntelligenceRepository:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def replace_session_sentiment_facts(self, session_id: str, facts: list[dict[str, Any]]) -> None:
        await self.db.execute("DELETE FROM session_sentiment_facts WHERE session_id = ?", (session_id,))
        for fact in facts:
            await self.db.execute(
                """
                INSERT INTO session_sentiment_facts (
                    session_id, feature_id, root_session_id, thread_session_id,
                    source_message_id, source_log_id, message_index,
                    sentiment_label, sentiment_score, confidence,
                    heuristic_version, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
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
                    _dumps(fact.get("evidence_json")),
                ),
            )
        await self.db.commit()

    async def list_session_sentiment_facts(self, session_id: str) -> list[dict[str, Any]]:
        async with self.db.execute(
            """
            SELECT *
            FROM session_sentiment_facts
            WHERE session_id = ?
            ORDER BY message_index ASC, source_log_id ASC, id ASC
            """,
            (session_id,),
        ) as cur:
            rows = [dict(row) for row in await cur.fetchall()]
        for row in rows:
            row["evidence_json"] = _loads_dict(row.get("evidence_json"))
        return rows

    async def replace_session_code_churn_facts(self, session_id: str, facts: list[dict[str, Any]]) -> None:
        await self.db.execute("DELETE FROM session_code_churn_facts WHERE session_id = ?", (session_id,))
        for fact in facts:
            await self.db.execute(
                """
                INSERT INTO session_code_churn_facts (
                    session_id, feature_id, root_session_id, thread_session_id,
                    file_path, first_source_log_id, last_source_log_id,
                    first_message_index, last_message_index,
                    touch_count, distinct_edit_turn_count, repeat_touch_count, rewrite_pass_count,
                    additions_total, deletions_total, net_diff_total,
                    churn_score, progress_score, low_progress_loop,
                    confidence, heuristic_version, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
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
                    1 if fact.get("low_progress_loop") else 0,
                    float(fact.get("confidence", 0.0) or 0.0),
                    str(fact.get("heuristic_version") or ""),
                    _dumps(fact.get("evidence_json")),
                ),
            )
        await self.db.commit()

    async def list_session_code_churn_facts(self, session_id: str) -> list[dict[str, Any]]:
        async with self.db.execute(
            """
            SELECT *
            FROM session_code_churn_facts
            WHERE session_id = ?
            ORDER BY file_path ASC, id ASC
            """,
            (session_id,),
        ) as cur:
            rows = [dict(row) for row in await cur.fetchall()]
        for row in rows:
            row["low_progress_loop"] = bool(row.get("low_progress_loop"))
            row["evidence_json"] = _loads_dict(row.get("evidence_json"))
        return rows

    async def replace_session_scope_drift_facts(self, session_id: str, facts: list[dict[str, Any]]) -> None:
        await self.db.execute("DELETE FROM session_scope_drift_facts WHERE session_id = ?", (session_id,))
        for fact in facts:
            await self.db.execute(
                """
                INSERT INTO session_scope_drift_facts (
                    session_id, feature_id, root_session_id, thread_session_id,
                    planned_path_count, actual_path_count, matched_path_count, out_of_scope_path_count,
                    drift_ratio, adherence_score, confidence, heuristic_version, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
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
                    _dumps(fact.get("evidence_json")),
                ),
            )
        await self.db.commit()

    async def list_session_scope_drift_facts(self, session_id: str) -> list[dict[str, Any]]:
        async with self.db.execute(
            """
            SELECT *
            FROM session_scope_drift_facts
            WHERE session_id = ?
            ORDER BY feature_id ASC, id ASC
            """,
            (session_id,),
        ) as cur:
            rows = [dict(row) for row in await cur.fetchall()]
        for row in rows:
            row["evidence_json"] = _loads_dict(row.get("evidence_json"))
        return rows
