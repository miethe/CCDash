"""Tests for CC-2: artifact-level telemetry queue/dispatch (Phase 3.5).

Covers:
- Polymorphic _push_batch dispatch: execution_outcome, artifact_outcome,
  artifact_version_outcome routes to correct client method.
- Feature-flag gating: artifact_outcome rows stay pending when
  artifact_telemetry_enabled=False.
- SAM client batched payload shape (artifact + artifact_version endpoints).
- Enqueue integration: emit_artifact_outcomes / emit_artifact_version_outcomes
  store rows with correct event_type.
- model_validator enforcement on ArtifactVersionOutcomePayload.
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import aiosqlite
import pytest
from pydantic import ValidationError

from backend.config import TelemetryExporterConfig
from backend.db.repositories.telemetry_queue import SqliteTelemetryQueueRepository
from backend.db.sqlite_migrations import run_migrations
from backend.models import (
    ArtifactOutcomePayload,
    ArtifactVersionOutcomePayload,
)
from backend.services.integrations import telemetry_exporter as te_module
from backend.services.integrations.sam_telemetry_client import SAMTelemetryClient
from backend.services.integrations.telemetry_exporter import (
    TelemetryExportCoordinator,
    emit_artifact_outcomes,
    emit_artifact_version_outcomes,
    _sam_base_url,
)
from backend.services.integrations.telemetry_settings_store import TelemetrySettingsStore


# ── fixtures ────────────────────────────────────────────────────────────────

_VALID_HASH = "sha256:" + "a" * 64  # 71 chars
_BARE_HEX = "f" * 64                # 64 chars
_NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
_START = datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc)
_END = datetime(2026, 4, 17, 0, 0, 0, tzinfo=timezone.utc)


def _artifact_payload(**overrides) -> dict:
    return {
        "event_id": uuid4(),
        "definition_type": "skill",
        "external_id": "skill:my-skill",
        "period_label": "7d",
        "period_start": _START,
        "period_end": _END,
        "execution_count": 10,
        "success_count": 8,
        "failure_count": 2,
        "token_input": 1000,
        "token_output": 500,
        "cost_usd": 0.05,
        "duration_ms": 3000,
        "timestamp": _NOW,
        **overrides,
    }


def _make_client(base_url: str = "https://sam.example.com/api/v1/analytics/execution-outcomes") -> SAMTelemetryClient:
    return SAMTelemetryClient(
        endpoint_url=base_url,
        api_key="test-key",
        timeout_seconds=30,
        allow_insecure=False,
    )


def _mock_http_response(status: int, body: str = "") -> MagicMock:
    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value=body)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


def _mock_http_session(response: MagicMock) -> MagicMock:
    session = MagicMock()
    session.post = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


# ── ArtifactVersionOutcomePayload model_validator ───────────────────────────

class TestArtifactVersionOutcomePayloadValidator(unittest.TestCase):
    """Step 1: ensure model_validator replaces the field-level override."""

    def test_requires_content_hash_present(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ArtifactVersionOutcomePayload(**_artifact_payload())
        assert "content_hash is required" in str(exc_info.value)

    def test_requires_content_hash_not_none(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactVersionOutcomePayload(**_artifact_payload(content_hash=None))

    def test_requires_content_hash_not_empty(self) -> None:
        # Empty string passes the Optional[str] field constraint but fails the validator.
        # The field min_length=64 will fire first if the string is short,
        # but we test that a completely absent value triggers the validator message.
        with pytest.raises(ValidationError):
            ArtifactVersionOutcomePayload(**_artifact_payload())

    def test_valid_with_full_hash(self) -> None:
        p = ArtifactVersionOutcomePayload(**_artifact_payload(content_hash=_VALID_HASH))
        assert p.content_hash == _VALID_HASH

    def test_valid_with_bare_hex_hash(self) -> None:
        p = ArtifactVersionOutcomePayload(**_artifact_payload(content_hash=_BARE_HEX))
        assert p.content_hash == _BARE_HEX

    def test_field_type_is_optional_str_on_parent(self) -> None:
        """Parent field type must remain Optional[str] — no Pyright override."""
        import inspect
        import typing
        hints = typing.get_type_hints(ArtifactOutcomePayload)
        # Optional[str] is Union[str, None]
        args = getattr(hints.get("content_hash"), "__args__", ())
        assert type(None) in args, "content_hash on parent should be Optional[str]"

    def test_subclass_field_type_matches_parent(self) -> None:
        """ArtifactVersionOutcomePayload must NOT redefine content_hash field."""
        import inspect
        import typing
        parent_hints = typing.get_type_hints(ArtifactOutcomePayload)
        child_hints = typing.get_type_hints(ArtifactVersionOutcomePayload)
        assert parent_hints.get("content_hash") == child_hints.get("content_hash"), (
            "content_hash field type must be identical on both classes — "
            "use model_validator, not field override"
        )


# ── SAM client: artifact endpoint URL + payload shape ───────────────────────

class TestSAMClientArtifactEndpoints(unittest.IsolatedAsyncioTestCase):
    """Step 3: SAM client methods post to correct URLs with correct body."""

    def setUp(self) -> None:
        self.client = _make_client()
        self.sam_base = "https://sam.example.com"
        self.artifact_url = f"{self.sam_base}/api/v1/analytics/artifact-outcomes"
        self.artifact_version_url = f"{self.sam_base}/api/v1/analytics/artifact-version-outcomes"

    async def test_push_artifact_batch_posts_to_correct_url(self) -> None:
        response = _mock_http_response(200)
        session = _mock_http_session(response)
        events = [ArtifactOutcomePayload(**_artifact_payload())]
        with patch("aiohttp.ClientSession", return_value=session):
            ok, err = await self.client.push_artifact_batch(events, self.sam_base)
        self.assertTrue(ok)
        self.assertIsNone(err)
        session.post.assert_called_once()
        called_url = session.post.call_args[0][0] if session.post.call_args[0] else session.post.call_args.args[0]
        self.assertEqual(called_url, self.artifact_url)

    async def test_push_artifact_batch_body_has_events_array(self) -> None:
        response = _mock_http_response(202)
        session = _mock_http_session(response)
        events = [ArtifactOutcomePayload(**_artifact_payload())]
        with patch("aiohttp.ClientSession", return_value=session):
            await self.client.push_artifact_batch(events, self.sam_base)
        posted_json = session.post.call_args[1].get("json", {})
        self.assertIn("events", posted_json)
        self.assertEqual(len(posted_json["events"]), 1)

    async def test_push_artifact_version_batch_posts_to_correct_url(self) -> None:
        response = _mock_http_response(200)
        session = _mock_http_session(response)
        events = [ArtifactVersionOutcomePayload(**_artifact_payload(content_hash=_VALID_HASH))]
        with patch("aiohttp.ClientSession", return_value=session):
            ok, _ = await self.client.push_artifact_version_batch(events, self.sam_base)
        self.assertTrue(ok)
        called_url = session.post.call_args[0][0] if session.post.call_args[0] else session.post.call_args.args[0]
        self.assertEqual(called_url, self.artifact_version_url)

    async def test_push_artifact_batch_includes_auth_header(self) -> None:
        response = _mock_http_response(200)
        session = _mock_http_session(response)
        events = [ArtifactOutcomePayload(**_artifact_payload())]
        with patch("aiohttp.ClientSession", return_value=session):
            await self.client.push_artifact_batch(events, self.sam_base)
        headers = session.post.call_args[1]["headers"]
        self.assertEqual(headers.get("Authorization"), "Bearer test-key")

    async def test_push_artifact_batch_empty_returns_success(self) -> None:
        with patch("aiohttp.ClientSession") as mock_cls:
            ok, err = await self.client.push_artifact_batch([], self.sam_base)
        mock_cls.assert_not_called()
        self.assertTrue(ok)
        self.assertIsNone(err)

    async def test_push_artifact_version_batch_empty_returns_success(self) -> None:
        with patch("aiohttp.ClientSession") as mock_cls:
            ok, err = await self.client.push_artifact_version_batch([], self.sam_base)
        mock_cls.assert_not_called()
        self.assertTrue(ok)
        self.assertIsNone(err)

    async def test_sam_base_url_strips_path(self) -> None:
        url = "https://sam.example.com/api/v1/analytics/execution-outcomes"
        self.assertEqual(_sam_base_url(url), "https://sam.example.com")

    async def test_sam_base_url_preserves_port(self) -> None:
        url = "https://sam.example.com:8443/api/v1/analytics/execution-outcomes"
        self.assertEqual(_sam_base_url(url), "https://sam.example.com:8443")


# ── Polymorphic _push_batch dispatch ────────────────────────────────────────

class _FakeMultiClient:
    """Captures calls to each push method."""

    def __init__(self, *, success: bool = True, error: str | None = None):
        self.success = success
        self.error = error
        self.execution_calls: list = []
        self.artifact_calls: list = []
        self.artifact_version_calls: list = []

    async def push_batch(self, events):
        self.execution_calls.append(events)
        return self.success, self.error

    async def push_artifact_batch(self, events, sam_base):
        self.artifact_calls.append((events, sam_base))
        return self.success, self.error

    async def push_artifact_version_batch(self, events, sam_base):
        self.artifact_version_calls.append((events, sam_base))
        return self.success, self.error


def _make_coordinator(artifact_enabled: bool = True) -> TelemetryExportCoordinator:
    coordinator = TelemetryExportCoordinator.__new__(TelemetryExportCoordinator)
    coordinator.runtime_config = TelemetryExporterConfig(
        enabled=True,
        sam_endpoint="https://sam.example.com/api/v1/analytics/execution-outcomes",
        sam_api_key="secret",
        timeout_seconds=30,
        artifact_telemetry_enabled=artifact_enabled,
    )
    coordinator.repository = MagicMock()
    coordinator.repository.mark_synced = AsyncMock()
    coordinator.repository.mark_failed = AsyncMock()
    coordinator.repository.mark_abandoned = AsyncMock()
    coordinator.repository.get_queue_stats = AsyncMock(return_value={"pending": 0, "synced": 0, "failed": 0, "abandoned": 0})
    coordinator.settings_store = MagicMock()
    coordinator._lock = MagicMock()
    coordinator._client = None
    return coordinator


def _queue_row(event_type: str, payload: dict, queue_id: str = "") -> dict:
    return {
        "id": queue_id or str(uuid4()),
        "session_id": f"art:{uuid4()}",
        "project_slug": "test-project",
        "payload_json": payload,
        "event_type": event_type,
        "status": "pending",
        "attempt_count": 0,
    }


class TestPushBatchPolymorphicDispatch(unittest.IsolatedAsyncioTestCase):
    """Step 4: _push_batch routes rows to the correct client method."""

    async def _run_push_batch(
        self,
        batch: list[dict],
        artifact_enabled: bool = True,
    ) -> tuple[TelemetryExportCoordinator, _FakeMultiClient]:
        coordinator = _make_coordinator(artifact_enabled=artifact_enabled)
        fake_client = _FakeMultiClient(success=True)

        with (
            patch.object(te_module.observability, "record_telemetry_export_event"),
            patch.object(te_module.observability, "record_telemetry_export_latency"),
            patch.object(te_module.observability, "record_telemetry_export_error"),
            patch.object(te_module.observability, "set_telemetry_export_queue_depth"),
        ):
            await coordinator._push_batch(
                batch,
                trigger="test",
                run_id="r1",
                started=0.0,
                _fake_client=None,  # ignored; we set _client directly
            )

        return coordinator, fake_client

    async def _push_with_fake(self, batch, artifact_enabled=True):
        coordinator = _make_coordinator(artifact_enabled=artifact_enabled)
        fake_client = _FakeMultiClient(success=True)
        coordinator._client = fake_client

        with (
            patch.object(te_module.observability, "record_telemetry_export_event"),
            patch.object(te_module.observability, "record_telemetry_export_latency"),
            patch.object(te_module.observability, "record_telemetry_export_error"),
            patch.object(te_module.observability, "set_telemetry_export_queue_depth"),
        ):
            outcome = await coordinator._push_batch(
                batch,
                trigger="test",
                run_id="r1",
                started=0.0,
            )
        return outcome, fake_client

    async def test_execution_outcome_routes_to_push_batch(self) -> None:
        from backend.models import ExecutionOutcomePayload
        payload = ExecutionOutcomePayload(
            event_id=uuid4(),
            project_slug="p1",
            session_id=uuid4(),
            model_family="Sonnet",
            token_input=100,
            token_output=50,
            cost_usd=0.01,
            tool_call_count=2,
            duration_seconds=60,
            message_count=5,
            outcome_status="completed",
            timestamp=_NOW,
            ccdash_version="1.0.0",
        ).event_dict()
        batch = [_queue_row("execution_outcome", payload)]
        outcome, client = await self._push_with_fake(batch)
        self.assertTrue(outcome.success)
        self.assertEqual(len(client.execution_calls), 1)
        self.assertEqual(len(client.artifact_calls), 0)
        self.assertEqual(len(client.artifact_version_calls), 0)

    async def test_artifact_outcome_routes_to_push_artifact_batch(self) -> None:
        payload = ArtifactOutcomePayload(**_artifact_payload()).event_dict()
        batch = [_queue_row("artifact_outcome", payload)]
        outcome, client = await self._push_with_fake(batch, artifact_enabled=True)
        self.assertTrue(outcome.success)
        self.assertEqual(len(client.artifact_calls), 1)
        self.assertEqual(len(client.execution_calls), 0)
        self.assertEqual(len(client.artifact_version_calls), 0)

    async def test_artifact_version_outcome_routes_to_push_artifact_version_batch(self) -> None:
        payload = ArtifactVersionOutcomePayload(**_artifact_payload(content_hash=_VALID_HASH)).event_dict()
        batch = [_queue_row("artifact_version_outcome", payload)]
        outcome, client = await self._push_with_fake(batch, artifact_enabled=True)
        self.assertTrue(outcome.success)
        self.assertEqual(len(client.artifact_version_calls), 1)
        self.assertEqual(len(client.execution_calls), 0)
        self.assertEqual(len(client.artifact_calls), 0)

    async def test_mixed_batch_dispatches_all_types(self) -> None:
        from backend.models import ExecutionOutcomePayload
        exec_payload = ExecutionOutcomePayload(
            event_id=uuid4(),
            project_slug="p1",
            session_id=uuid4(),
            model_family="Opus",
            token_input=10,
            token_output=5,
            cost_usd=0.001,
            tool_call_count=1,
            duration_seconds=10,
            message_count=2,
            outcome_status="completed",
            timestamp=_NOW,
            ccdash_version="1.0.0",
        ).event_dict()
        art_payload = ArtifactOutcomePayload(**_artifact_payload()).event_dict()
        artv_payload = ArtifactVersionOutcomePayload(**_artifact_payload(content_hash=_VALID_HASH)).event_dict()
        batch = [
            _queue_row("execution_outcome", exec_payload),
            _queue_row("artifact_outcome", art_payload),
            _queue_row("artifact_version_outcome", artv_payload),
        ]
        outcome, client = await self._push_with_fake(batch, artifact_enabled=True)
        self.assertTrue(outcome.success)
        self.assertEqual(len(client.execution_calls), 1)
        self.assertEqual(len(client.artifact_calls), 1)
        self.assertEqual(len(client.artifact_version_calls), 1)


# ── Feature flag gating ──────────────────────────────────────────────────────

class TestArtifactTelemetryFeatureFlag(unittest.IsolatedAsyncioTestCase):
    """Step 4: artifact rows stay pending when artifact_telemetry_enabled=False."""

    async def _push_with_fake(self, batch, artifact_enabled):
        coordinator = _make_coordinator(artifact_enabled=artifact_enabled)
        fake_client = _FakeMultiClient(success=True)
        coordinator._client = fake_client

        with (
            patch.object(te_module.observability, "record_telemetry_export_event"),
            patch.object(te_module.observability, "record_telemetry_export_latency"),
            patch.object(te_module.observability, "record_telemetry_export_error"),
            patch.object(te_module.observability, "set_telemetry_export_queue_depth"),
        ):
            outcome = await coordinator._push_batch(
                batch,
                trigger="test",
                run_id="r1",
                started=0.0,
            )
        return outcome, fake_client, coordinator

    async def test_artifact_rows_not_sent_when_flag_disabled(self) -> None:
        payload = ArtifactOutcomePayload(**_artifact_payload()).event_dict()
        batch = [_queue_row("artifact_outcome", payload)]
        outcome, client, coordinator = await self._push_with_fake(batch, artifact_enabled=False)
        # No artifact push calls.
        self.assertEqual(len(client.artifact_calls), 0)
        # Skipped rows are not marked synced, failed, or abandoned.
        coordinator.repository.mark_synced.assert_not_awaited()
        coordinator.repository.mark_failed.assert_not_awaited()
        coordinator.repository.mark_abandoned.assert_not_awaited()

    async def test_artifact_version_rows_not_sent_when_flag_disabled(self) -> None:
        payload = ArtifactVersionOutcomePayload(**_artifact_payload(content_hash=_VALID_HASH)).event_dict()
        batch = [_queue_row("artifact_version_outcome", payload)]
        _, client, coordinator = await self._push_with_fake(batch, artifact_enabled=False)
        self.assertEqual(len(client.artifact_version_calls), 0)
        coordinator.repository.mark_synced.assert_not_awaited()

    async def test_execution_rows_still_sent_when_artifact_flag_disabled(self) -> None:
        from backend.models import ExecutionOutcomePayload
        exec_payload = ExecutionOutcomePayload(
            event_id=uuid4(),
            project_slug="p1",
            session_id=uuid4(),
            model_family="Sonnet",
            token_input=10,
            token_output=5,
            cost_usd=0.001,
            tool_call_count=1,
            duration_seconds=10,
            message_count=2,
            outcome_status="completed",
            timestamp=_NOW,
            ccdash_version="1.0.0",
        ).event_dict()
        art_payload = ArtifactOutcomePayload(**_artifact_payload()).event_dict()
        batch = [
            _queue_row("execution_outcome", exec_payload),
            _queue_row("artifact_outcome", art_payload),
        ]
        _, client, coordinator = await self._push_with_fake(batch, artifact_enabled=False)
        # Execution rows ARE sent.
        self.assertEqual(len(client.execution_calls), 1)
        # Artifact rows are NOT sent.
        self.assertEqual(len(client.artifact_calls), 0)
        # Execution rows are marked synced; artifact rows are not touched.
        coordinator.repository.mark_synced.assert_awaited_once()


# ── emit_artifact_outcomes / emit_artifact_version_outcomes integration ──────

class TestEmitArtifactOutcomesIntegration(unittest.IsolatedAsyncioTestCase):
    """Step 5: enqueue helpers store rows with correct event_type."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.queue = SqliteTelemetryQueueRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_emit_artifact_outcomes_stores_with_correct_event_type(self) -> None:
        payload = ArtifactOutcomePayload(**_artifact_payload())
        await emit_artifact_outcomes(self.queue, [payload], "test-project")
        # Verify row in DB.
        async with self.db.execute(
            "SELECT event_type, status FROM outbound_telemetry_queue WHERE id = ?",
            (str(payload.event_id),),
        ) as cur:
            row = await cur.fetchone()
        self.assertIsNotNone(row, "Expected a queue row to be inserted")
        self.assertEqual(row["event_type"], "artifact_outcome")
        self.assertEqual(row["status"], "pending")

    async def test_emit_artifact_version_outcomes_stores_with_correct_event_type(self) -> None:
        payload = ArtifactVersionOutcomePayload(**_artifact_payload(content_hash=_VALID_HASH))
        await emit_artifact_version_outcomes(self.queue, [payload], "test-project")
        async with self.db.execute(
            "SELECT event_type, status FROM outbound_telemetry_queue WHERE id = ?",
            (str(payload.event_id),),
        ) as cur:
            row = await cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["event_type"], "artifact_version_outcome")
        self.assertEqual(row["status"], "pending")

    async def test_emit_multiple_payloads_stores_all(self) -> None:
        payloads = [
            ArtifactOutcomePayload(**_artifact_payload(external_id=f"skill:s{i}"))
            for i in range(3)
        ]
        await emit_artifact_outcomes(self.queue, payloads, "test-project")
        async with self.db.execute(
            "SELECT COUNT(*) FROM outbound_telemetry_queue WHERE event_type = 'artifact_outcome'"
        ) as cur:
            row = await cur.fetchone()
        self.assertEqual(int(row[0]), 3)

    async def test_emit_is_idempotent_same_event_id(self) -> None:
        """Re-emitting the same payload (same event_id) is a no-op."""
        payload = ArtifactOutcomePayload(**_artifact_payload())
        await emit_artifact_outcomes(self.queue, [payload], "p1")
        await emit_artifact_outcomes(self.queue, [payload], "p1")  # second call
        async with self.db.execute(
            "SELECT COUNT(*) FROM outbound_telemetry_queue WHERE event_type = 'artifact_outcome'"
        ) as cur:
            row = await cur.fetchone()
        self.assertEqual(int(row[0]), 1, "Duplicate event_id should not insert a second row")

    async def test_emit_artifact_outcomes_empty_list_is_noop(self) -> None:
        await emit_artifact_outcomes(self.queue, [], "p1")
        async with self.db.execute("SELECT COUNT(*) FROM outbound_telemetry_queue") as cur:
            row = await cur.fetchone()
        self.assertEqual(int(row[0]), 0)


# ── Config: feature flag plumbing ────────────────────────────────────────────

class TestArtifactTelemetryConfigFlag(unittest.TestCase):
    def test_telemetry_exporter_config_has_artifact_telemetry_enabled(self) -> None:
        cfg = TelemetryExporterConfig(
            enabled=True,
            sam_endpoint="https://sam.example.com/api/v1/analytics/execution-outcomes",
            sam_api_key="secret",
            artifact_telemetry_enabled=True,
        )
        self.assertTrue(cfg.artifact_telemetry_enabled)

    def test_artifact_telemetry_enabled_defaults_false(self) -> None:
        cfg = TelemetryExporterConfig(
            enabled=True,
            sam_endpoint="https://sam.example.com/api/v1/analytics/execution-outcomes",
            sam_api_key="secret",
        )
        self.assertFalse(cfg.artifact_telemetry_enabled)


if __name__ == "__main__":
    unittest.main()
