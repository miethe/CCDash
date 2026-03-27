"""Worker job wrapper for outbound telemetry exports."""
from __future__ import annotations

from dataclasses import dataclass

from backend.services.integrations import TelemetryExportCoordinator


@dataclass(slots=True)
class TelemetryExportRunResult:
    success: bool
    outcome: str
    batch_size: int = 0
    duration_ms: int = 0
    queue_depth: int = 0
    error: str | None = None
    retry_after_seconds: int | None = None
    last_push_timestamp: str | None = None


class TelemetryExporterJob:
    """Adapt the shared telemetry coordinator to the runtime job interface."""

    def __init__(self, coordinator: TelemetryExportCoordinator) -> None:
        self.coordinator = coordinator

    async def execute(self, *, trigger: str = "scheduled") -> TelemetryExportRunResult:
        outcome = await self.coordinator.execute(trigger=trigger, raise_on_busy=False)
        return TelemetryExportRunResult(
            success=outcome.success,
            outcome=outcome.outcome,
            batch_size=outcome.batch_size,
            duration_ms=outcome.duration_ms,
            error=outcome.error,
        )


__all__ = ["TelemetryExporterJob", "TelemetryExportRunResult"]
