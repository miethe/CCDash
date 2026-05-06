from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.db.sqlite_migrations import run_migrations
from backend.db.sync_engine import SyncEngine


class _ParsedSession:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self) -> dict[str, Any]:
        return dict(self._payload)


def _session_payload(logs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "S-jsonl-regression",
        "status": "completed",
        "model": "claude-sonnet-4-5",
        "startedAt": "2026-04-02T10:00:00Z",
        "endedAt": "2026-04-02T10:05:00Z",
        "updatedAt": "2026-04-02T10:05:00Z",
        "rootSessionId": "S-jsonl-regression",
        "conversationFamilyId": "S-jsonl-regression",
        "featureId": "jsonl-sync-regression",
        "logs": logs,
        "toolsUsed": [],
        "updatedFiles": [],
        "linkedArtifacts": [],
    }


def _message_log(
    log_id: str,
    timestamp: str,
    content: str,
    *,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, Any]:
    return {
        "id": log_id,
        "timestamp": timestamp,
        "speaker": "assistant",
        "type": "message",
        "content": content,
        "agentName": "executor",
        "metadata": {
            "model": "claude-sonnet-4-5",
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "cache_creation_input_tokens": 1,
            "cache_read_input_tokens": 2,
        },
    }


class SyncEngineJsonlPersistenceRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.engine = SyncEngine(self.db)

        self.engine._replace_session_telemetry_events = AsyncMock(return_value=0)  # type: ignore[attr-defined]
        self.engine._replace_session_commit_correlations = AsyncMock(return_value=0)  # type: ignore[attr-defined]
        self.engine._replace_session_intelligence_facts = AsyncMock(return_value=0)  # type: ignore[attr-defined]
        self.engine._maybe_enqueue_telemetry_export = AsyncMock(return_value=None)  # type: ignore[attr-defined]
        self.engine._derive_session_observability_fields = AsyncMock(return_value={})  # type: ignore[attr-defined]

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _count_rows(self, table_name: str, session_id: str = "S-jsonl-regression") -> int:
        async with self.db.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE session_id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0])

    async def test_sync_single_session_persists_usage_events_and_attributions(self) -> None:
        logs = [
            _message_log(
                "log-1",
                "2026-04-02T10:00:01Z",
                "first persisted message",
                input_tokens=11,
                output_tokens=17,
            )
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            session_path = Path(tmp_dir) / "session.jsonl"
            session_path.write_text('{"type":"message"}\n', encoding="utf-8")

            with (
                patch("backend.db.sync_engine.parse_session_file", return_value=_ParsedSession(_session_payload(logs))),
                patch("backend.db.sync_engine.publish_session_transcript_append", new_callable=AsyncMock),
                patch("backend.db.sync_engine.publish_session_snapshot", new_callable=AsyncMock),
            ):
                synced = await self.engine._sync_single_session("project-1", session_path, force=True)

        self.assertTrue(synced)
        self.assertEqual(await self._count_rows("session_messages"), 1)
        self.assertGreaterEqual(await self._count_rows("session_usage_events"), 4)
        async with self.db.execute(
            """
            SELECT COUNT(*)
            FROM session_usage_attributions sua
            JOIN session_usage_events sue ON sue.id = sua.event_id
            WHERE sue.session_id = ?
            """,
            ("S-jsonl-regression",),
        ) as cur:
            attribution_count = int((await cur.fetchone())[0])
        self.assertGreaterEqual(attribution_count, 4)

        async with self.db.execute(
            """
            SELECT token_family, delta_tokens
            FROM session_usage_events
            WHERE session_id = ?
            ORDER BY token_family
            """,
            ("S-jsonl-regression",),
        ) as cur:
            usage_rows = {str(row["token_family"]): int(row["delta_tokens"]) for row in await cur.fetchall()}
        self.assertEqual(usage_rows["model_input"], 11)
        self.assertEqual(usage_rows["model_output"], 17)

        async with self.db.execute(
            """
            SELECT DISTINCT entity_type, entity_id, attribution_role
            FROM session_usage_attributions sua
            JOIN session_usage_events sue ON sue.id = sua.event_id
            WHERE sue.session_id = ?
            """,
            ("S-jsonl-regression",),
        ) as cur:
            attribution_rows = {
                (str(row["entity_type"]), str(row["entity_id"]), str(row["attribution_role"]))
                for row in await cur.fetchall()
            }
        self.assertIn(("agent", "executor", "primary"), attribution_rows)
        self.assertIn(("feature", "jsonl-sync-regression", "supporting"), attribution_rows)


if __name__ == "__main__":
    unittest.main()
