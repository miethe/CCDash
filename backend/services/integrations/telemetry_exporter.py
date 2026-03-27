"""Shared telemetry export coordination for routes and scheduled jobs."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from backend import config
from backend.db.repositories.base import TelemetryQueueRepository
from backend.models import (
    ExecutionOutcomePayload,
    PushNowResponse,
    TelemetryExportSettings,
    TelemetryExportStatusResponse,
    TelemetryQueueStatsResponse,
)
from backend.observability import otel as observability
from backend.services.integrations.sam_telemetry_client import SAMTelemetryClient
from backend.services.integrations.telemetry_settings_store import TelemetrySettingsStore

logger = logging.getLogger("ccdash.telemetry.exporter")
MAX_EXPORT_RETRY_ATTEMPTS = 10


class TelemetryExportBusyError(RuntimeError):
    """Raised when an export run is already in progress."""


@dataclass(slots=True)
class TelemetryExportOutcome:
    success: bool
    outcome: str
    batch_size: int
    duration_ms: int
    error: str | None = None
    run_id: str = field(default_factory=lambda: str(uuid4()))

    def to_push_now_response(self) -> PushNowResponse:
        return PushNowResponse(
            success=self.success,
            batchSize=self.batch_size,
            durationMs=self.duration_ms,
            error=self.error or "",
        )


class TelemetryExportCoordinator:
    def __init__(
        self,
        *,
        repository: TelemetryQueueRepository,
        settings_store: TelemetrySettingsStore,
        runtime_config: config.TelemetryExporterConfig,
    ) -> None:
        self.repository = repository
        self.settings_store = settings_store
        self.runtime_config = runtime_config
        self._lock = asyncio.Lock()
        self._client: SAMTelemetryClient | None = None

    def settings(self) -> TelemetryExportSettings:
        return self.settings_store.load()

    async def status(self) -> TelemetryExportStatusResponse:
        settings = self.settings()
        stats = await self.repository.get_queue_stats()
        error_severity = ""
        if stats.get("last_error_status") == "abandoned":
            error_severity = "error"
        elif stats.get("last_error"):
            error_severity = "warning"

        return TelemetryExportStatusResponse(
            enabled=self._effective_enabled(settings),
            configured=bool(self.runtime_config.configured),
            samEndpointMasked=self._mask_endpoint(self.runtime_config.sam_endpoint),
            queueStats=TelemetryQueueStatsResponse(
                pending=int(stats.get("pending", 0)),
                synced=int(stats.get("synced", 0)),
                failed=int(stats.get("failed", 0)),
                abandoned=int(stats.get("abandoned", 0)),
                total=int(stats.get("total", 0)),
            ),
            lastPushTimestamp=str(stats.get("last_push_timestamp") or ""),
            eventsPushed24h=int(stats.get("events_pushed_24h", 0)),
            lastError=str(stats.get("last_error") or ""),
            errorSeverity=error_severity,
            envLocked=not bool(self.runtime_config.enabled),
            persistedEnabled=bool(settings.enabled),
        )

    async def execute(
        self,
        *,
        trigger: str,
        raise_on_busy: bool,
    ) -> TelemetryExportOutcome:
        if self._lock.locked():
            if raise_on_busy:
                raise TelemetryExportBusyError("Telemetry export is already in progress")
            return TelemetryExportOutcome(success=False, outcome="busy", batch_size=0, duration_ms=0, error="busy")

        async with self._lock:
            return await self._run_locked(trigger=trigger)

    async def _run_locked(self, *, trigger: str) -> TelemetryExportOutcome:
        started = time.monotonic()
        settings = self.settings()
        if not self.runtime_config.configured:
            return TelemetryExportOutcome(
                success=False,
                outcome="not_configured",
                batch_size=0,
                duration_ms=0,
                error="Telemetry exporter is not configured",
            )
        if not self.runtime_config.enabled:
            return TelemetryExportOutcome(
                success=False,
                outcome="env_locked",
                batch_size=0,
                duration_ms=0,
                error="Telemetry exporter is disabled by environment configuration",
            )
        if not settings.enabled:
            return TelemetryExportOutcome(
                success=False,
                outcome="disabled",
                batch_size=0,
                duration_ms=0,
                error="Telemetry exporter is disabled in settings",
            )

        batch = await self.repository.fetch_pending_batch(self.runtime_config.batch_size)
        if not batch:
            duration_ms = int((time.monotonic() - started) * 1000)
            return TelemetryExportOutcome(success=True, outcome="idle", batch_size=0, duration_ms=duration_ms)

        run_id = str(uuid4())
        attributes = {
            "ccdash.telemetry.trigger": trigger,
            "ccdash.telemetry.run_id": run_id,
            "ccdash.telemetry.batch_size": len(batch),
        }
        with observability.start_span("telemetry.export.batch", attributes):
            outcome = await self._push_batch(batch, trigger=trigger, run_id=run_id, started=started)
        return outcome

    async def _push_batch(
        self,
        batch: list[dict[str, Any]],
        *,
        trigger: str,
        run_id: str,
        started: float,
    ) -> TelemetryExportOutcome:
        events = [
            ExecutionOutcomePayload.model_validate(row.get("payload_json") or {})
            for row in batch
        ]
        queue_ids = [str(row.get("id") or "") for row in batch if str(row.get("id") or "").strip()]
        client = self._client or self._build_client()
        self._client = client
        success, error = await client.push_batch(events)

        synced = 0
        failed = 0
        abandoned = 0
        outcome_name = "success"
        error_message = error or None

        if success:
            for queue_id in queue_ids:
                await self.repository.mark_synced(queue_id)
                synced += 1
        elif error and error.startswith("abandoned:"):
            outcome_name = "abandoned"
            message = error.split(":", 1)[-1].strip() or "abandoned"
            for queue_id in queue_ids:
                await self.repository.mark_abandoned(queue_id, message)
                abandoned += 1
            error_message = message
        else:
            outcome_name = "retry"
            retry_message = "rate_limited" if error == "rate_limited" else (error or "retry_later")
            for row in batch:
                queue_id = str(row.get("id") or "").strip()
                if not queue_id:
                    continue
                next_attempt = int(row.get("attempt_count") or 0) + 1
                if next_attempt >= MAX_EXPORT_RETRY_ATTEMPTS:
                    await self.repository.mark_abandoned(queue_id, retry_message, attempt_count=next_attempt)
                    abandoned += 1
                    outcome_name = "abandoned" if failed == 0 else outcome_name
                    continue
                await self.repository.mark_failed(queue_id, retry_message, attempt_count=next_attempt)
                failed += 1
            error_message = retry_message

        duration_ms = int((time.monotonic() - started) * 1000)
        stats = await self.repository.get_queue_stats()
        logger.info(
            "Telemetry export run complete",
            extra={
                "run_id": run_id,
                "trigger": trigger,
                "batch_size": len(queue_ids),
                "duration_ms": duration_ms,
                "outcome": outcome_name,
                "queue_depth": int(stats.get("pending", 0)),
                "synced": synced,
                "failed": failed,
                "abandoned": abandoned,
            },
        )
        return TelemetryExportOutcome(
            success=success,
            outcome=outcome_name,
            batch_size=len(queue_ids),
            duration_ms=duration_ms,
            error=error_message,
            run_id=run_id,
        )

    def _build_client(self) -> SAMTelemetryClient:
        return SAMTelemetryClient.from_config(self.runtime_config)

    def _effective_enabled(self, settings: TelemetryExportSettings) -> bool:
        return bool(self.runtime_config.enabled and self.runtime_config.configured and settings.enabled)

    def _mask_endpoint(self, endpoint: str) -> str:
        parsed = urlparse(str(endpoint or "").strip())
        if not parsed.hostname:
            return ""
        if parsed.port:
            return f"{parsed.hostname}:{parsed.port}"
        return parsed.hostname
