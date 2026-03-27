import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import aiosqlite

from backend.adapters.jobs.telemetry_exporter import TelemetryExporterJob
from backend.config import TelemetryExporterConfig
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.repositories.telemetry_queue import SqliteTelemetryQueueRepository
from backend.db.sqlite_migrations import run_migrations
from backend.observability import otel as observability_module
from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import get_runtime_profile
from backend.services.integrations.sam_telemetry_client import SAMTelemetryClient
from backend.services.integrations import telemetry_exporter as telemetry_exporter_module
from backend.services.integrations.telemetry_exporter import TelemetryExportBusyError, TelemetryExportCoordinator
from backend.services.integrations.telemetry_settings_store import TelemetrySettingsStore


class _FakeClient:
    def __init__(self, *, success: bool, error: str | None = None):
        self.success = success
        self.error = error
        self.calls: list[list] = []

    async def push_batch(self, events):
        self.calls.append(events)
        return self.success, self.error


class _FakeCounter:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, str]]] = []

    def add(self, value, labels) -> None:  # noqa: ANN001
        self.calls.append((value, labels))


class _FakeHistogram:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, str]]] = []

    def record(self, value, labels) -> None:  # noqa: ANN001
        self.calls.append((value, labels))


class _FakePromCounter:
    def __init__(self) -> None:
        self.labels_calls: list[dict[str, str]] = []
        self.inc_calls: list[int] = []

    def labels(self, **labels):  # noqa: ANN003
        self.labels_calls.append(labels)
        return self

    def inc(self, value=1) -> None:
        self.inc_calls.append(value)


class _FakePromHistogram:
    def __init__(self) -> None:
        self.labels_calls: list[dict[str, str]] = []
        self.observe_calls: list[float] = []

    def labels(self, **labels):  # noqa: ANN003
        self.labels_calls.append(labels)
        return self

    def observe(self, value: float) -> None:
        self.observe_calls.append(value)


class _FakePromGauge:
    def __init__(self) -> None:
        self.labels_calls: list[dict[str, str]] = []
        self.set_calls: list[int] = []

    def labels(self, **labels):  # noqa: ANN003
        self.labels_calls.append(labels)
        return self

    def set(self, value: int) -> None:
        self.set_calls.append(value)


class TelemetryObservabilityHelperTests(unittest.TestCase):
    def test_helper_functions_update_metrics_state_and_prometheus(self) -> None:
        otel_counter = _FakeCounter()
        otel_hist = _FakeHistogram()
        otel_error_counter = _FakeCounter()
        prom_counter = _FakePromCounter()
        prom_hist = _FakePromHistogram()
        prom_error_counter = _FakePromCounter()
        prom_queue_gauge = _FakePromGauge()
        prom_disabled_gauge = _FakePromGauge()

        with (
            patch.object(observability_module, "_enabled", True),
            patch.object(observability_module, "_prom_enabled", True),
            patch.object(observability_module, "_telemetry_export_events_counter", otel_counter),
            patch.object(observability_module, "_telemetry_export_latency_hist", otel_hist),
            patch.object(observability_module, "_telemetry_export_errors_counter", otel_error_counter),
            patch.object(observability_module, "_prom_telemetry_export_events_counter", prom_counter),
            patch.object(observability_module, "_prom_telemetry_export_latency_hist", prom_hist),
            patch.object(observability_module, "_prom_telemetry_export_errors_counter", prom_error_counter),
            patch.object(observability_module, "_prom_telemetry_export_queue_depth_gauge", prom_queue_gauge),
            patch.object(observability_module, "_prom_telemetry_export_disabled_gauge", prom_disabled_gauge),
        ):
            observability_module.record_telemetry_export_event(
                project_id="project-1",
                status="success",
                count=2,
            )
            observability_module.record_telemetry_export_latency(
                project_id="project-1",
                duration_ms=12.5,
            )
            observability_module.record_telemetry_export_error(
                project_id="project-1",
                error_type="5xx",
            )
            observability_module.set_telemetry_export_queue_depth(
                project_id="project-1",
                status="pending",
                depth=4,
            )
            observability_module.set_telemetry_export_disabled(True)

        self.assertEqual(otel_counter.calls, [(2, {"status": "success", "project_id": "project-1"})])
        self.assertEqual(otel_hist.calls, [(12.5, {"project_id": "project-1"})])
        self.assertEqual(otel_error_counter.calls, [(1, {"error_type": "5xx", "project_id": "project-1"})])
        self.assertEqual(prom_counter.inc_calls, [2])
        self.assertEqual(prom_hist.observe_calls, [12.5])
        self.assertEqual(prom_error_counter.inc_calls, [1])
        self.assertEqual(prom_queue_gauge.set_calls, [4])
        self.assertEqual(prom_disabled_gauge.set_calls, [1])
        self.assertEqual(observability_module._telemetry_queue_depth_state[("project-1", "pending")], 4)
        self.assertEqual(observability_module._telemetry_export_disabled_state, 1)


class TelemetryExportCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.session_repo = SqliteSessionRepository(self.db)
        self.queue_repo = SqliteTelemetryQueueRepository(self.db)
        self.tempdir = tempfile.TemporaryDirectory()
        self.settings_store = TelemetrySettingsStore(Path(self.tempdir.name) / "integrations.json")
        self.settings_store.save(type("Req", (), {"enabled": True})())
        self.coordinator = TelemetryExportCoordinator(
            repository=self.queue_repo,
            settings_store=self.settings_store,
            runtime_config=TelemetryExporterConfig(
                enabled=True,
                sam_endpoint="https://sam.example/api/v1/analytics/execution-outcomes",
                sam_api_key="secret",
                timeout_seconds=30,
            ),
        )

    async def asyncTearDown(self) -> None:
        self.tempdir.cleanup()
        await self.db.close()

    async def _enqueue(self, session_id: str = "session-1") -> None:
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
        payload = {
            "event_id": str(uuid4()),
            "project_slug": "project-1",
            "session_id": str(uuid4()),
            "workflow_type": "feature-implementation",
            "model_family": "Sonnet",
            "token_input": 100,
            "token_output": 50,
            "cost_usd": 0.0,
            "tool_call_count": 1,
            "duration_seconds": 60,
            "message_count": 3,
            "outcome_status": "completed",
            "timestamp": "2026-03-12T12:01:00Z",
            "ccdash_version": "0.1.0",
        }
        await self.queue_repo.enqueue(session_id, "project-1", payload)

    async def test_execute_marks_rows_synced_on_success(self) -> None:
        await self._enqueue()
        fake_client = _FakeClient(success=True)
        self.coordinator._client = fake_client

        result = await self.coordinator.execute(trigger="manual", raise_on_busy=True)

        self.assertTrue(result.success)
        self.assertEqual(result.batch_size, 1)
        stats = await self.queue_repo.get_queue_stats()
        self.assertEqual(stats["synced"], 1)
        self.assertEqual(len(fake_client.calls), 1)

    async def test_execute_marks_rows_failed_for_retryable_errors(self) -> None:
        await self._enqueue()
        self.coordinator._client = _FakeClient(success=False, error="boom")

        result = await self.coordinator.execute(trigger="manual", raise_on_busy=True)

        self.assertFalse(result.success)
        self.assertEqual(result.error, "boom")
        stats = await self.queue_repo.get_queue_stats()
        self.assertEqual(stats["failed"], 1)

    async def test_execute_marks_rows_abandoned_for_client_errors(self) -> None:
        await self._enqueue()
        self.coordinator._client = _FakeClient(success=False, error="abandoned:bad request")

        result = await self.coordinator.execute(trigger="manual", raise_on_busy=True)

        self.assertFalse(result.success)
        self.assertEqual(result.outcome, "abandoned")
        stats = await self.queue_repo.get_queue_stats()
        self.assertEqual(stats["abandoned"], 1)

    async def test_execute_abandons_retryable_rows_after_tenth_attempt(self) -> None:
        await self._enqueue()
        row = await self.queue_repo._get_by_session_id("session-1")  # noqa: SLF001
        self.assertIsNotNone(row)
        await self.db.execute(
            """
            UPDATE outbound_telemetry_queue
            SET status = 'failed',
                attempt_count = 9,
                last_attempt_at = ?
            WHERE id = ?
            """,
            ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), row["id"]),
        )
        await self.db.commit()
        self.coordinator._client = _FakeClient(success=False, error="boom")

        result = await self.coordinator.execute(trigger="manual", raise_on_busy=True)

        self.assertFalse(result.success)
        self.assertEqual(result.outcome, "abandoned")
        refreshed = await self.queue_repo._get_by_id(row["id"])  # noqa: SLF001
        self.assertEqual(refreshed["status"], "abandoned")
        self.assertEqual(refreshed["attempt_count"], 10)

    async def test_execute_records_span_attributes_and_metrics_on_success(self) -> None:
        await self._enqueue()
        self.coordinator._client = _FakeClient(success=True)
        span = Mock()

        @contextmanager
        def _fake_span():
            yield span

        with (
            patch.object(telemetry_exporter_module.observability, "start_span", return_value=_fake_span()) as start_span,
            patch.object(telemetry_exporter_module.observability, "record_telemetry_export_event") as record_event,
            patch.object(telemetry_exporter_module.observability, "record_telemetry_export_latency") as record_latency,
            patch.object(telemetry_exporter_module.observability, "record_telemetry_export_error") as record_error,
            patch.object(telemetry_exporter_module.observability, "set_telemetry_export_queue_depth") as set_queue_depth,
            patch.object(telemetry_exporter_module.observability, "set_telemetry_export_disabled") as set_disabled,
        ):
            result = await self.coordinator.execute(trigger="manual", raise_on_busy=True)

        self.assertTrue(result.success)
        start_span.assert_called_once()
        self.assertEqual(start_span.call_args.args[0], "telemetry.export.batch")
        attrs = start_span.call_args.args[1]
        self.assertEqual(attrs["ccdash.telemetry.project_slug"], "project-1")
        self.assertEqual(attrs["ccdash.telemetry.sam_endpoint_host"], "sam.example")
        span.set_attribute.assert_called_once_with("ccdash.telemetry.outcome", "success")
        set_disabled.assert_called_once_with(False)
        record_event.assert_called_once_with(project_id="project-1", status="success", count=1)
        record_latency.assert_called_once()
        record_error.assert_not_called()
        self.assertEqual(set_queue_depth.call_count, 3)

    async def test_execute_marks_disabled_state_for_env_locked_config(self) -> None:
        disabled_coordinator = TelemetryExportCoordinator(
            repository=self.queue_repo,
            settings_store=self.settings_store,
            runtime_config=TelemetryExporterConfig(
                enabled=False,
                sam_endpoint="",
                sam_api_key="",
                timeout_seconds=30,
            ),
        )

        with patch.object(telemetry_exporter_module.observability, "set_telemetry_export_disabled") as set_disabled:
            result = await disabled_coordinator.execute(trigger="scheduled", raise_on_busy=False)

        self.assertFalse(result.success)
        self.assertEqual(result.outcome, "not_configured")
        set_disabled.assert_called_once_with(True)

    async def test_execute_raises_when_busy(self) -> None:
        await self.coordinator._lock.acquire()
        try:
            with self.assertRaises(TelemetryExportBusyError):
                await self.coordinator.execute(trigger="manual", raise_on_busy=True)
        finally:
            self.coordinator._lock.release()

    async def test_status_reports_env_and_settings_state(self) -> None:
        status = await self.coordinator.status()
        self.assertTrue(status.enabled)
        self.assertTrue(status.configured)
        self.assertEqual(status.samEndpointMasked, "sam.example")


class SAMTelemetryClientTests(unittest.TestCase):
    def test_rejects_insecure_http_by_default(self) -> None:
        with self.assertRaises(ValueError):
            SAMTelemetryClient(
                endpoint_url="http://sam.example/api",
                api_key="secret",
            )

    def test_accepts_https_endpoint(self) -> None:
        client = SAMTelemetryClient(
            endpoint_url="https://sam.example/api",
            api_key="secret",
        )
        self.assertEqual(client.endpoint_url, "https://sam.example/api")


class TelemetryExporterJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_delegates_to_coordinator_with_non_blocking_busy_handling(self) -> None:
        coordinator = SimpleNamespace(
            execute=unittest.mock.AsyncMock(
                return_value=SimpleNamespace(
                    success=True,
                    outcome="success",
                    batch_size=3,
                    duration_ms=45,
                    error=None,
                )
            )
        )
        job = TelemetryExporterJob(coordinator)

        result = await job.execute()

        coordinator.execute.assert_awaited_once_with(trigger="scheduled", raise_on_busy=False)
        self.assertTrue(result.success)
        self.assertEqual(result.batch_size, 3)


class RuntimeContainerTelemetryObservabilityTests(unittest.TestCase):
    def test_worker_container_records_disabled_state_from_runtime_and_settings(self) -> None:
        container = RuntimeContainer(profile=get_runtime_profile("worker"))
        container.telemetry_settings_store = SimpleNamespace(load=lambda: SimpleNamespace(enabled=False))

        with (
            patch.object(
                telemetry_exporter_module.config,
                "TELEMETRY_EXPORTER_CONFIG",
                TelemetryExporterConfig(
                    enabled=True,
                    sam_endpoint="https://sam.example/api/v1/analytics/execution-outcomes",
                    sam_api_key="secret",
                    timeout_seconds=30,
                ),
            ),
            patch("backend.runtime.container.observability.set_telemetry_export_disabled") as set_disabled,
        ):
            container._record_telemetry_export_disabled_state()  # noqa: SLF001

        set_disabled.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
