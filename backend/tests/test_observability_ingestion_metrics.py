import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.db.sqlite_migrations import run_migrations
from backend.db.sync_engine import SyncEngine
from backend.observability import otel


class _FakeCounter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, dict[str, str]]] = []

    def add(self, value: int, labels: dict[str, str]) -> None:
        self.calls.append((value, labels))


class _FakeHistogram:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, str]]] = []

    def record(self, value: float, labels: dict[str, str]) -> None:
        self.calls.append((value, labels))


class _FakePromCounter:
    def __init__(self) -> None:
        self.labels_calls: list[dict[str, str]] = []
        self.inc_calls: list[int] = []

    def labels(self, **labels: str) -> "_FakePromCounter":
        self.labels_calls.append(labels)
        return self

    def inc(self, value: int = 1) -> None:
        self.inc_calls.append(value)


class _FakePromHistogram:
    def __init__(self) -> None:
        self.labels_calls: list[dict[str, str]] = []
        self.observe_calls: list[float] = []

    def labels(self, **labels: str) -> "_FakePromHistogram":
        self.labels_calls.append(labels)
        return self

    def observe(self, value: float) -> None:
        self.observe_calls.append(value)


class _ParsedSession:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def model_dump(self) -> dict:
        return dict(self._payload)


class IngestionObservabilityTests(unittest.TestCase):
    def test_record_ingestion_defaults_source_for_existing_callers(self) -> None:
        otel_counter = _FakeCounter()
        otel_hist = _FakeHistogram()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", False),
            patch.object(otel, "_ingestion_counter", otel_counter),
            patch.object(otel, "_ingestion_latency_hist", otel_hist),
        ):
            otel.record_ingestion("document", "success", 12.5, project_id="project-1")

        expected_labels = {
            "entity": "document",
            "result": "success",
            "project_id": "project-1",
            "source": "unknown",
        }
        self.assertEqual(otel_counter.calls, [(1, expected_labels)])
        self.assertEqual(otel_hist.calls, [(12.5, expected_labels)])

    def test_record_ingestion_emits_source_label_for_otel_and_prometheus(self) -> None:
        otel_counter = _FakeCounter()
        otel_hist = _FakeHistogram()
        prom_counter = _FakePromCounter()
        prom_hist = _FakePromHistogram()

        with (
            patch.object(otel, "_enabled", True),
            patch.object(otel, "_prom_enabled", True),
            patch.object(otel, "_ingestion_counter", otel_counter),
            patch.object(otel, "_ingestion_latency_hist", otel_hist),
            patch.object(otel, "_prom_ingestion_counter", prom_counter),
            patch.object(otel, "_prom_ingestion_latency_hist", prom_hist),
        ):
            otel.record_ingestion("session", "success", -3.0, project_id="project-1", source="jsonl")

        expected_otel_labels = {
            "entity": "session",
            "result": "success",
            "project_id": "project-1",
            "source": "jsonl",
        }
        expected_prom_labels = {
            "project": "project-1",
            "entity": "session",
            "result": "success",
            "source": "jsonl",
        }
        self.assertEqual(otel_counter.calls, [(1, expected_otel_labels)])
        self.assertEqual(otel_hist.calls, [(0.0, expected_otel_labels)])
        self.assertEqual(prom_counter.labels_calls, [expected_prom_labels])
        self.assertEqual(prom_counter.inc_calls, [1])
        self.assertEqual(prom_hist.labels_calls, [expected_prom_labels])
        self.assertEqual(prom_hist.observe_calls, [0.0])


class JsonlSessionSyncIngestionMetricTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.engine = SyncEngine(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_sync_single_session_records_jsonl_source_dimension(self) -> None:
        session_payload = {
            "id": "S-JSONL-1",
            "status": "completed",
            "startedAt": "2026-05-05T12:00:00Z",
            "endedAt": "2026-05-05T12:01:00Z",
            "logs": [],
            "toolsUsed": [],
            "updatedFiles": [],
            "linkedArtifacts": [],
        }
        ingest_service = SimpleNamespace(persist_envelope=AsyncMock(return_value=None))
        self.engine._get_session_ingest_service = lambda: ingest_service  # type: ignore[method-assign]

        with tempfile.TemporaryDirectory() as tmp_dir:
            session_path = Path(tmp_dir) / "session.jsonl"
            session_path.write_text("{}\n", encoding="utf-8")
            with (
                patch("backend.db.sync_engine.parse_session_file", return_value=_ParsedSession(session_payload)),
                patch("backend.db.sync_engine.observability.record_ingestion") as record_ingestion,
            ):
                synced = await self.engine._sync_single_session("project-1", session_path, force=True)

        self.assertTrue(synced)
        record_ingestion.assert_called_once()
        self.assertEqual(record_ingestion.call_args.args[:2], ("session", "success"))
        self.assertEqual(record_ingestion.call_args.kwargs["project_id"], "project-1")
        self.assertEqual(record_ingestion.call_args.kwargs["source"], "jsonl")


if __name__ == "__main__":
    unittest.main()
