"""Shared telemetry export coordination for routes and scheduled jobs."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from backend import config
from backend.db.repositories.base import TelemetryQueueRepository
from backend.models import (
    ArtifactOutcomePayload,
    ArtifactVersionOutcomePayload,
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
        observability.set_telemetry_export_disabled(not self._effective_enabled(settings))
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
            await self._record_queue_depth_metrics(project_slug="all-projects")
            return TelemetryExportOutcome(success=True, outcome="idle", batch_size=0, duration_ms=duration_ms)

        run_id = str(uuid4())
        project_slug = self._project_slug_for_batch(batch)
        attributes = {
            "ccdash.telemetry.trigger": trigger,
            "ccdash.telemetry.run_id": run_id,
            "ccdash.telemetry.batch_size": len(batch),
            "ccdash.telemetry.project_slug": project_slug,
            "ccdash.telemetry.sam_endpoint_host": self._mask_endpoint(self.runtime_config.sam_endpoint),
        }
        span_context = observability.start_span("telemetry.export.batch", attributes)
        with span_context if span_context is not None else nullcontext(None) as span:
            outcome = await self._push_batch(batch, trigger=trigger, run_id=run_id, started=started)
            if span is not None:
                span.set_attribute("ccdash.telemetry.outcome", self._span_outcome(outcome.outcome))
        await self._purge_old_synced_rows()
        return outcome

    async def _push_batch(
        self,
        batch: list[dict[str, Any]],
        *,
        trigger: str,
        run_id: str,
        started: float,
    ) -> TelemetryExportOutcome:
        # Separate rows by event_type for polymorphic dispatch.
        execution_rows: list[dict[str, Any]] = []
        artifact_rows: list[dict[str, Any]] = []
        artifact_version_rows: list[dict[str, Any]] = []
        skipped_artifact_ids: list[str] = []

        artifact_telemetry_enabled = self.runtime_config.artifact_telemetry_enabled
        for row in batch:
            et = str(row.get("event_type") or "execution_outcome")
            if et == "artifact_outcome":
                if artifact_telemetry_enabled:
                    artifact_rows.append(row)
                else:
                    # Feature-flagged off: leave pending (do not fail or abandon).
                    qid = str(row.get("id") or "").strip()
                    if qid:
                        skipped_artifact_ids.append(qid)
            elif et == "artifact_version_outcome":
                if artifact_telemetry_enabled:
                    artifact_version_rows.append(row)
                else:
                    qid = str(row.get("id") or "").strip()
                    if qid:
                        skipped_artifact_ids.append(qid)
            else:
                execution_rows.append(row)

        if skipped_artifact_ids:
            logger.debug(
                "Artifact telemetry disabled; skipping %d artifact rows in this batch",
                len(skipped_artifact_ids),
            )

        # Build a synthetic batch composed only of rows we will actually push.
        active_batch = execution_rows + artifact_rows + artifact_version_rows

        # Parse each sub-batch into typed models.
        execution_events = [
            ExecutionOutcomePayload.model_validate(row.get("payload_json") or {})
            for row in execution_rows
        ]
        artifact_events = [
            ArtifactOutcomePayload.model_validate(row.get("payload_json") or {})
            for row in artifact_rows
        ]
        artifact_version_events = [
            ArtifactVersionOutcomePayload.model_validate(row.get("payload_json") or {})
            for row in artifact_version_rows
        ]

        queue_ids = [str(row.get("id") or "") for row in active_batch if str(row.get("id") or "").strip()]
        client = self._client or self._build_client()
        self._client = client

        # Derive SAM base URL from the configured endpoint (strip path to API root).
        sam_base = _sam_base_url(self.runtime_config.sam_endpoint)

        # Execute all pushes; collect results.
        results: list[tuple[bool, str | None]] = []
        if execution_events:
            results.append(await client.push_batch(execution_events))
        if artifact_events:
            results.append(await client.push_artifact_batch(artifact_events, sam_base))
        if artifact_version_events:
            results.append(await client.push_artifact_version_batch(artifact_version_events, sam_base))

        # Merge results: success only if all sub-batches succeeded.
        if not results:
            # Nothing to push (all were skipped by feature flag).
            success, error = True, None
        elif all(ok for ok, _ in results):
            success, error = True, None
        else:
            # Return the first non-success error.
            for ok, err in results:
                if not ok:
                    success, error = False, err
                    break
            else:
                success, error = False, "unknown"

        synced = 0
        failed = 0
        abandoned = 0
        outcome_name = "success"
        error_message = error or None
        project_slug = self._project_slug_for_batch(batch)
        skipped_id_set = set(skipped_artifact_ids)

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
            for row in active_batch:
                queue_id = str(row.get("id") or "").strip()
                if not queue_id or queue_id in skipped_id_set:
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
        observability.record_telemetry_export_event(
            project_id=project_slug,
            status=self._span_outcome(outcome_name),
            count=len(queue_ids),
        )
        observability.record_telemetry_export_latency(project_id=project_slug, duration_ms=duration_ms)
        await self._record_queue_depth_metrics(project_slug=project_slug, stats=stats)
        if error_message:
            observability.record_telemetry_export_error(
                project_id=project_slug,
                error_type=self._classify_error_type(error_message, outcome=outcome_name),
            )
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

    async def _purge_old_synced_rows(self) -> None:
        purged = await self.repository.purge_old_synced(self.runtime_config.queue_retention_days)
        if purged <= 0:
            return
        logger.info(
            "Telemetry export purge complete",
            extra={
                "retention_days": self.runtime_config.queue_retention_days,
                "purged_rows": purged,
            },
        )

    async def _record_queue_depth_metrics(
        self,
        *,
        project_slug: str,
        stats: dict[str, Any] | None = None,
    ) -> None:
        summary = stats or await self.repository.get_queue_stats()
        for status in ("pending", "failed", "abandoned"):
            observability.set_telemetry_export_queue_depth(
                project_id=project_slug,
                status=status,
                depth=int(summary.get(status, 0)),
            )

    def _project_slug_for_batch(self, batch: list[dict[str, Any]]) -> str:
        slugs = {
            str(row.get("project_slug") or "").strip()
            for row in batch
            if str(row.get("project_slug") or "").strip()
        }
        if len(slugs) == 1:
            return slugs.pop()
        return "all-projects"

    def _classify_error_type(self, error: str, *, outcome: str) -> str:
        message = (error or "").strip().lower()
        if "timeout" in message:
            return "timeout"
        if any(token in message for token in ("connection", "connect", "refused", "unreachable", "dns", "network")):
            return "network"
        if outcome == "abandoned" or message == "rate_limited":
            return "4xx"
        return "5xx"

    def _span_outcome(self, outcome: str) -> str:
        return "abandon" if outcome == "abandoned" else outcome


def _sam_base_url(endpoint_url: str) -> str:
    """Derive the SAM base URL (scheme + host + port) from a configured endpoint URL.

    The execution-outcomes endpoint URL already contains a path
    (e.g. ``https://sam.example.com/api/v1/analytics/execution-outcomes``).
    Strip the path so callers can construct other SAM endpoint paths.
    """
    parsed = urlparse(str(endpoint_url or "").strip())
    if not parsed.hostname:
        return str(endpoint_url or "").strip()
    port_part = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port_part}"


async def emit_artifact_outcomes(
    queue: TelemetryQueueRepository,
    payloads: list[ArtifactOutcomePayload],
    project_slug: str,
) -> None:
    """Enqueue artifact-outcome payloads for later export to SAM.

    Each payload is enqueued independently.  Deduplication key is the
    payload's ``event_id`` (a UUID), so re-enqueuing the same event is a
    no-op.  Silently swallows enqueue errors (same pattern as sync_engine).
    """
    for payload in payloads:
        dedup_key = f"art:{payload.event_id}"
        try:
            await queue.enqueue(
                session_id=dedup_key,
                project_slug=project_slug,
                payload=payload.event_dict(),
                queue_id=str(payload.event_id),
                event_type="artifact_outcome",
            )
        except Exception:
            logger.exception(
                "Failed to enqueue artifact_outcome event",
                extra={"event_id": str(payload.event_id), "external_id": payload.external_id},
            )


async def emit_artifact_version_outcomes(
    queue: TelemetryQueueRepository,
    payloads: list[ArtifactVersionOutcomePayload],
    project_slug: str,
) -> None:
    """Enqueue artifact-version-outcome payloads for later export to SAM.

    Requires ``content_hash`` to be set (enforced by model validation).
    Deduplication key is the payload's ``event_id``.
    """
    for payload in payloads:
        dedup_key = f"artv:{payload.event_id}"
        try:
            await queue.enqueue(
                session_id=dedup_key,
                project_slug=project_slug,
                payload=payload.event_dict(),
                queue_id=str(payload.event_id),
                event_type="artifact_version_outcome",
            )
        except Exception:
            logger.exception(
                "Failed to enqueue artifact_version_outcome event",
                extra={"event_id": str(payload.event_id), "external_id": payload.external_id},
            )
