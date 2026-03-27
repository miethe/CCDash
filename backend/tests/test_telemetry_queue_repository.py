import unittest
from unittest.mock import patch

import aiosqlite

from backend import config
from backend.db.repositories.base import TelemetryQueueRepository
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.repositories.telemetry_queue import SqliteTelemetryQueueRepository
from backend.db.sqlite_migrations import run_migrations


class TelemetryQueueRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.session_repo = SqliteSessionRepository(self.db)
        self.repo = SqliteTelemetryQueueRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _insert_session(self, session_id: str) -> None:
        await self.session_repo.upsert(
            {
                "id": session_id,
                "taskId": "",
                "status": "completed",
                "model": "claude-sonnet-4-5-20260101",
                "platformType": "Claude Code",
                "platformVersion": "2.1.52",
                "platformVersions": ["2.1.52"],
                "platformVersionTransitions": [],
                "durationSeconds": 60,
                "tokensIn": 100,
                "tokensOut": 50,
                "totalCost": 0.0,
                "startedAt": "2026-03-12T12:00:00Z",
                "endedAt": "2026-03-12T12:01:00Z",
                "sourceFile": f"/tmp/{session_id}.jsonl",
            },
            "project-1",
        )

    async def test_protocol_runtime_check(self) -> None:
        self.assertIsInstance(self.repo, TelemetryQueueRepository)

    async def test_enqueue_is_idempotent_by_session_id(self) -> None:
        await self._insert_session("session-1")
        first = await self.repo.enqueue("session-1", "project-1", {"event_id": "event-1", "value": 1})
        second = await self.repo.enqueue("session-1", "project-1", {"event_id": "event-2", "value": 2})

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["session_id"], "session-1")
        async with self.db.execute("SELECT COUNT(*) FROM outbound_telemetry_queue WHERE session_id = ?", ("session-1",)) as cur:
            row = await cur.fetchone()
        self.assertEqual(int(row[0]), 1)

    async def test_enqueue_drops_new_rows_when_pending_queue_hits_cap(self) -> None:
        await self._insert_session("session-cap-1")
        await self._insert_session("session-cap-2")
        with patch.object(config.TELEMETRY_EXPORTER_CONFIG, "max_queue_size", 1):
            first = await self.repo.enqueue("session-cap-1", "project-1", {"event_id": "event-cap-1"})
            dropped = await self.repo.enqueue("session-cap-2", "project-1", {"event_id": "event-cap-2"})

        self.assertEqual(first["session_id"], "session-cap-1")
        self.assertEqual(dropped, {})
        async with self.db.execute("SELECT COUNT(*) FROM outbound_telemetry_queue") as cur:
            row = await cur.fetchone()
        self.assertEqual(int(row[0]), 1)

    async def test_enqueue_existing_session_still_returns_existing_row_when_cap_reached(self) -> None:
        await self._insert_session("session-existing")
        with patch.object(config.TELEMETRY_EXPORTER_CONFIG, "max_queue_size", 1):
            first = await self.repo.enqueue("session-existing", "project-1", {"event_id": "event-existing-1"})
            second = await self.repo.enqueue("session-existing", "project-1", {"event_id": "event-existing-2"})

        self.assertEqual(first["id"], second["id"])
        async with self.db.execute("SELECT COUNT(*) FROM outbound_telemetry_queue") as cur:
            row = await cur.fetchone()
        self.assertEqual(int(row[0]), 1)

    async def test_fetch_pending_batch_orders_by_created_at(self) -> None:
        for idx in range(1, 4):
            await self._insert_session(f"session-{idx}")
            await self.repo.enqueue(f"session-{idx}", "project-1", {"event_id": f"event-{idx}"})

        await self.db.execute(
            "UPDATE outbound_telemetry_queue SET created_at = ? WHERE session_id = ?",
            ("2026-01-01T00:00:03+00:00", "session-1"),
        )
        await self.db.execute(
            "UPDATE outbound_telemetry_queue SET created_at = ? WHERE session_id = ?",
            ("2026-01-01T00:00:01+00:00", "session-2"),
        )
        await self.db.execute(
            "UPDATE outbound_telemetry_queue SET created_at = ? WHERE session_id = ?",
            ("2026-01-01T00:00:02+00:00", "session-3"),
        )
        await self.db.commit()

        batch = await self.repo.fetch_pending_batch(3)
        self.assertEqual([row["session_id"] for row in batch], ["session-2", "session-3", "session-1"])

    async def test_mark_failed_increments_attempt_count_and_sets_last_attempt(self) -> None:
        await self._insert_session("session-failed")
        item = await self.repo.enqueue("session-failed", "project-1", {"event_id": "event-failed"})
        failed_once = await self.repo.mark_failed(item["id"], "first failure")
        failed_twice = await self.repo.mark_failed(item["id"], "second failure")

        self.assertIsNotNone(failed_once)
        self.assertIsNotNone(failed_twice)
        self.assertEqual(failed_twice["status"], "failed")
        self.assertEqual(failed_twice["attempt_count"], 2)
        self.assertEqual(failed_twice["last_error"], "second failure")
        self.assertTrue(str(failed_twice["last_attempt_at"]).strip())

    async def test_mark_failed_honors_explicit_attempt_count_floor(self) -> None:
        await self._insert_session("session-explicit-failed")
        item = await self.repo.enqueue("session-explicit-failed", "project-1", {"event_id": "event-explicit-failed"})
        failed = await self.repo.mark_failed(item["id"], "explicit", attempt_count=4)
        failed_next = await self.repo.mark_failed(item["id"], "explicit-next", attempt_count=2)

        self.assertIsNotNone(failed)
        self.assertIsNotNone(failed_next)
        self.assertEqual(failed["attempt_count"], 4)
        self.assertEqual(failed_next["attempt_count"], 5)

    async def test_mark_abandoned_sets_status_and_error(self) -> None:
        await self._insert_session("session-abandoned")
        item = await self.repo.enqueue("session-abandoned", "project-1", {"event_id": "event-abandoned"})
        abandoned = await self.repo.mark_abandoned(item["id"], "bad request")

        self.assertIsNotNone(abandoned)
        self.assertEqual(abandoned["status"], "abandoned")
        self.assertEqual(abandoned["attempt_count"], 1)
        self.assertEqual(abandoned["last_error"], "bad request")

    async def test_mark_synced_sets_status_and_clears_last_error(self) -> None:
        await self._insert_session("session-synced")
        item = await self.repo.enqueue("session-synced", "project-1", {"event_id": "event-synced"})
        await self.repo.mark_failed(item["id"], "transient")
        synced = await self.repo.mark_synced(item["id"])

        self.assertIsNotNone(synced)
        self.assertEqual(synced["status"], "synced")
        self.assertEqual(synced["attempt_count"], 2)
        self.assertIsNone(synced["last_error"])

    async def test_get_queue_stats_counts_status_buckets(self) -> None:
        await self._insert_session("session-pending")
        await self._insert_session("session-synced")
        await self._insert_session("session-failed")
        await self._insert_session("session-abandoned")

        pending = await self.repo.enqueue("session-pending", "project-1", {"event_id": "event-pending"})
        synced = await self.repo.enqueue("session-synced", "project-1", {"event_id": "event-synced"})
        failed = await self.repo.enqueue("session-failed", "project-1", {"event_id": "event-failed"})
        abandoned = await self.repo.enqueue("session-abandoned", "project-1", {"event_id": "event-abandoned"})

        await self.repo.mark_synced(synced["id"])
        await self.repo.mark_failed(failed["id"], "retry later")
        await self.repo.mark_abandoned(abandoned["id"], "bad payload")

        stats = await self.repo.get_queue_stats()
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(stats["synced"], 1)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["abandoned"], 1)
        self.assertEqual(stats["total"], 4)
        self.assertEqual(pending["status"], "pending")

    async def test_purge_old_synced_removes_only_old_synced_rows(self) -> None:
        await self._insert_session("session-old-synced")
        await self._insert_session("session-new-synced")
        await self._insert_session("session-old-failed")

        old_synced = await self.repo.enqueue("session-old-synced", "project-1", {"event_id": "event-old-synced"})
        new_synced = await self.repo.enqueue("session-new-synced", "project-1", {"event_id": "event-new-synced"})
        old_failed = await self.repo.enqueue("session-old-failed", "project-1", {"event_id": "event-old-failed"})

        await self.repo.mark_synced(old_synced["id"])
        await self.repo.mark_synced(new_synced["id"])
        await self.repo.mark_failed(old_failed["id"], "still failing")

        await self.db.execute(
            "UPDATE outbound_telemetry_queue SET created_at = ? WHERE id = ?",
            ("2025-01-01T00:00:00+00:00", old_synced["id"]),
        )
        await self.db.execute(
            "UPDATE outbound_telemetry_queue SET created_at = ? WHERE id = ?",
            ("2026-03-20T00:00:00+00:00", new_synced["id"]),
        )
        await self.db.execute(
            "UPDATE outbound_telemetry_queue SET created_at = ? WHERE id = ?",
            ("2025-01-01T00:00:00+00:00", old_failed["id"]),
        )
        await self.db.commit()

        deleted = await self.repo.purge_old_synced(30)
        self.assertEqual(deleted, 1)

        async with self.db.execute(
            "SELECT status, COUNT(*) FROM outbound_telemetry_queue GROUP BY status ORDER BY status"
        ) as cur:
            rows = await cur.fetchall()
        summary = {str(row[0]): int(row[1]) for row in rows}
        self.assertEqual(summary.get("synced", 0), 1)
        self.assertEqual(summary.get("failed", 0), 1)


if __name__ == "__main__":
    unittest.main()
