import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import aiosqlite
from aiohttp import web

from backend.config import TelemetryExporterConfig
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.repositories.telemetry_queue import SqliteTelemetryQueueRepository
from backend.db.sqlite_migrations import run_migrations
from backend.db.sync_engine import SyncEngine
from backend.models import ExecutionOutcomePayload
from backend.services.integrations.sam_telemetry_client import SAMTelemetryClient
from backend.services.integrations.telemetry_exporter import (
    TelemetryExportBusyError,
    TelemetryExportCoordinator,
)
from backend.services.integrations.telemetry_settings_store import TelemetrySettingsStore
from backend.adapters.jobs.telemetry_exporter import TelemetryExporterJob


class _StubClient:
    def __init__(self, result: tuple[bool, str | None], *, gate: asyncio.Event | None = None) -> None:
        self.result = result
        self.gate = gate
        self.calls = 0

    async def push_batch(self, events):  # noqa: ANN001
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        return self.result


class _AiohttpServer:
    def __init__(self, handler):
        self.app = web.Application()
        self.app.router.add_post("/api/v1/analytics/execution-outcomes", handler)
        self.runner = web.AppRunner(self.app)
        self.site = None
        self.base_url = ""

    async def start(self) -> str:
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        sockets = getattr(self.site, "_server", None).sockets
        port = sockets[0].getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        return self.base_url

    async def stop(self) -> None:
        await self.runner.cleanup()


class SAMTelemetryClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        server = getattr(self, "_server", None)
        if server is not None:
            await server.stop()

    def _event(self) -> ExecutionOutcomePayload:
        return ExecutionOutcomePayload(
            event_id=uuid4(),
            project_slug="project-1",
            session_id=uuid4(),
            workflow_type="feature",
            model_family="Sonnet",
            token_input=10,
            token_output=5,
            cost_usd=0.01,
            tool_call_count=1,
            duration_seconds=30,
            message_count=2,
            outcome_status="completed",
            timestamp=datetime.now(timezone.utc),
            ccdash_version="0.1.0",
        )

    async def test_push_batch_returns_success_on_202(self) -> None:
        async def handler(request):
            payload = await request.json()
            self.assertEqual(payload["schema_version"], "1")
            return web.json_response({"accepted": True}, status=202)

        self._server = _AiohttpServer(handler)
        base_url = await self._server.start()
        client = SAMTelemetryClient(
            endpoint_url=f"{base_url}/api/v1/analytics/execution-outcomes",
            api_key="secret",
            allow_insecure=True,
        )

        success, error = await client.push_batch([self._event()])
        self.assertTrue(success)
        self.assertIsNone(error)

    async def test_push_batch_returns_rate_limited_on_429(self) -> None:
        async def handler(_request):
            return web.Response(text="slow down", status=429)

        self._server = _AiohttpServer(handler)
        base_url = await self._server.start()
        client = SAMTelemetryClient(
            endpoint_url=f"{base_url}/api/v1/analytics/execution-outcomes",
            api_key="secret",
            allow_insecure=True,
        )

        success, error = await client.push_batch([self._event()])
        self.assertFalse(success)
        self.assertEqual(error, "rate_limited")

    async def test_push_batch_returns_abandoned_marker_on_400(self) -> None:
        async def handler(_request):
            return web.Response(text="bad payload", status=400)

        self._server = _AiohttpServer(handler)
        base_url = await self._server.start()
        client = SAMTelemetryClient(
            endpoint_url=f"{base_url}/api/v1/analytics/execution-outcomes",
            api_key="secret",
            allow_insecure=True,
        )

        success, error = await client.push_batch([self._event()])
        self.assertFalse(success)
        self.assertEqual(error, "abandoned:bad payload")

    async def test_push_batch_returns_retry_message_on_503(self) -> None:
        async def handler(_request):
            return web.Response(text="upstream unavailable", status=503)

        self._server = _AiohttpServer(handler)
        base_url = await self._server.start()
        client = SAMTelemetryClient(
            endpoint_url=f"{base_url}/api/v1/analytics/execution-outcomes",
            api_key="secret",
            allow_insecure=True,
        )

        success, error = await client.push_batch([self._event()])
        self.assertFalse(success)
        self.assertEqual(error, "upstream unavailable")

    def test_constructor_rejects_insecure_http_when_not_allowed(self) -> None:
        with self.assertRaises(ValueError):
            SAMTelemetryClient(
                endpoint_url="http://127.0.0.1:8080/api/v1/analytics/execution-outcomes",
                api_key="secret",
                allow_insecure=False,
            )


class TelemetryExportCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.settings_store = TelemetrySettingsStore(Path(self._tmp.name) / "integrations.json")
        self.settings_store.save(type("Req", (), {"enabled": True})())
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.session_repo = SqliteSessionRepository(self.db)
        self.repo = SqliteTelemetryQueueRepository(self.db)
        self.runtime_config = TelemetryExporterConfig(
            enabled=True,
            sam_endpoint="https://sam.example.com/api/v1/analytics/execution-outcomes",
            sam_api_key="secret",
            batch_size=10,
            timeout_seconds=30,
            interval_seconds=60,
            max_queue_size=1000,
            queue_retention_days=30,
            allow_insecure=False,
            ccdash_version="0.1.0",
        )
        self.coordinator = TelemetryExportCoordinator(
            repository=self.repo,
            settings_store=self.settings_store,
            runtime_config=self.runtime_config,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self._tmp.cleanup()

    async def _insert_queue_event(self, session_id: str = "session-1") -> dict:
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
        payload = ExecutionOutcomePayload(
            event_id=uuid4(),
            project_slug="project-1",
            session_id=uuid4(),
            workflow_type="feature",
            model_family="Sonnet",
            token_input=10,
            token_output=5,
            cost_usd=0.01,
            tool_call_count=1,
            duration_seconds=30,
            message_count=2,
            outcome_status="completed",
            timestamp=datetime.now(timezone.utc),
            ccdash_version="0.1.0",
        )
        return await self.repo.enqueue(session_id, "project-1", payload.event_dict(), queue_id=str(payload.event_id))

    async def test_execute_marks_rows_synced_on_success(self) -> None:
        item = await self._insert_queue_event()
        self.coordinator._client = _StubClient((True, None))

        outcome = await self.coordinator.execute(trigger="manual", raise_on_busy=True)

        self.assertTrue(outcome.success)
        self.assertEqual(outcome.outcome, "success")
        synced = await self.repo._get_by_id(item["id"])  # noqa: SLF001
        self.assertEqual(synced["status"], "synced")

    async def test_execute_marks_rows_failed_and_backoff_excludes_immediate_retry(self) -> None:
        item = await self._insert_queue_event()
        self.coordinator._client = _StubClient((False, "rate_limited"))

        outcome = await self.coordinator.execute(trigger="scheduled", raise_on_busy=False)

        self.assertFalse(outcome.success)
        self.assertEqual(outcome.outcome, "retry")
        failed = await self.repo._get_by_id(item["id"])  # noqa: SLF001
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["last_error"], "rate_limited")
        self.assertEqual(await self.repo.fetch_pending_batch(1), [])

    async def test_execute_marks_rows_abandoned_on_client_signal(self) -> None:
        item = await self._insert_queue_event()
        self.coordinator._client = _StubClient((False, "abandoned:bad payload"))

        outcome = await self.coordinator.execute(trigger="scheduled", raise_on_busy=False)

        self.assertFalse(outcome.success)
        self.assertEqual(outcome.outcome, "abandoned")
        abandoned = await self.repo._get_by_id(item["id"])  # noqa: SLF001
        self.assertEqual(abandoned["status"], "abandoned")
        self.assertEqual(abandoned["last_error"], "bad payload")

    async def test_execute_abandons_retryable_rows_after_max_attempts(self) -> None:
        item = await self._insert_queue_event()
        await self.db.execute(
            """
            UPDATE outbound_telemetry_queue
            SET status = 'failed',
                attempt_count = 9,
                last_attempt_at = ?
            WHERE id = ?
            """,
            ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), item["id"]),
        )
        await self.db.commit()
        self.coordinator._client = _StubClient((False, "rate_limited"))

        outcome = await self.coordinator.execute(trigger="scheduled", raise_on_busy=False)

        self.assertFalse(outcome.success)
        self.assertEqual(outcome.outcome, "abandoned")
        abandoned = await self.repo._get_by_id(item["id"])  # noqa: SLF001
        self.assertEqual(abandoned["status"], "abandoned")
        self.assertEqual(abandoned["attempt_count"], 10)

    async def test_execute_raises_busy_error_when_requested(self) -> None:
        await self._insert_queue_event()
        gate = asyncio.Event()
        self.coordinator._client = _StubClient((True, None), gate=gate)

        first = asyncio.create_task(self.coordinator.execute(trigger="manual", raise_on_busy=False))
        await asyncio.sleep(0)

        with self.assertRaises(TelemetryExportBusyError):
            await self.coordinator.execute(trigger="manual", raise_on_busy=True)

        gate.set()
        await first


class TelemetryExporterJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_job_delegates_to_coordinator_with_scheduled_trigger(self) -> None:
        class _Coordinator:
            def __init__(self) -> None:
                self.calls = []

            async def execute(self, *, trigger: str, raise_on_busy: bool):
                self.calls.append((trigger, raise_on_busy))
                return type("Outcome", (), {"success": True, "outcome": "success", "batch_size": 1, "duration_ms": 3, "error": None})()

        coordinator = _Coordinator()
        job = TelemetryExporterJob(coordinator)

        outcome = await job.execute()

        self.assertTrue(outcome.success)
        self.assertEqual(coordinator.calls, [("scheduled", False)])


class SyncEngineTelemetryExportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.engine = SyncEngine(self.db)
        self.session_repo = SqliteSessionRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_maybe_enqueue_telemetry_export_skips_active_session_without_end_time(self) -> None:
        await self.engine._maybe_enqueue_telemetry_export(  # noqa: SLF001
            "project-1",
            {
                "id": str(uuid4()),
                "status": "active",
                "model": "claude-sonnet-4-5-20260101",
            },
        )

        self.assertEqual(await self.engine.telemetry_queue_repo.fetch_pending_batch(10), [])

    async def test_maybe_enqueue_telemetry_export_enqueues_finalized_session(self) -> None:
        session_id = str(uuid4())
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

        await self.engine._maybe_enqueue_telemetry_export(  # noqa: SLF001
            "project-1",
            {
                "id": session_id,
                "status": "completed",
                "model": "claude-sonnet-4-5-20260101",
                "tokensIn": 100,
                "tokensOut": 50,
                "displayCostUsd": 0.0,
                "durationSeconds": 60,
                "logs": [{"id": "1"}],
                "toolsUsed": [],
                "endedAt": "2026-03-12T12:01:00Z",
            },
        )

        batch = await self.engine.telemetry_queue_repo.fetch_pending_batch(10)
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]["session_id"], session_id)


if __name__ == "__main__":
    unittest.main()
