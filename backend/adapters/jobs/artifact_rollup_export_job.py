"""Worker job wrapper for SkillMeat artifact usage rollup exports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend import config
from backend.services.integrations.skillmeat_client import SkillMeatClient
from backend.services.integrations.telemetry_exporter import TelemetryExportCoordinator


@dataclass(slots=True)
class ArtifactRollupExportRunResult:
    success: bool
    outcome: str
    rollup_count: int = 0
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    error: str | None = None


class ArtifactRollupExportJob:
    """Adapt artifact rollup export to the runtime job interface."""

    def __init__(
        self,
        coordinator: TelemetryExportCoordinator,
        *,
        project: Any | None = None,
        period: str = "30d",
    ) -> None:
        self.coordinator = coordinator
        self.project = project
        self.period = period

    async def execute(self, *, trigger: str = "scheduled") -> ArtifactRollupExportRunResult:
        del trigger
        if not bool(getattr(config, "CCDASH_ARTIFACT_INTELLIGENCE_ENABLED", False)):
            return ArtifactRollupExportRunResult(success=True, outcome="disabled")
        project = self.project
        if project is None:
            return ArtifactRollupExportRunResult(success=True, outcome="no_project")
        skillmeat = getattr(project, "skillMeat", None)
        base_url = str(getattr(skillmeat, "baseUrl", "") or "").strip()
        if not base_url:
            return ArtifactRollupExportRunResult(success=True, outcome="not_configured")

        client = SkillMeatClient(
            base_url=base_url,
            timeout_seconds=float(getattr(skillmeat, "requestTimeoutSeconds", 5.0) or 5.0),
            aaa_enabled=bool(getattr(skillmeat, "aaaEnabled", False)),
            api_key=str(getattr(skillmeat, "apiKey", "") or ""),
        )
        outcome = await self.coordinator.export_artifact_usage_rollups(
            project_id=str(getattr(project, "id", "") or ""),
            period=self.period,
            skillmeat_client=client,
            skillmeat_project_id=str(getattr(skillmeat, "projectId", "") or "") or None,
            collection_id=str(getattr(skillmeat, "collectionId", "") or "") or None,
        )
        return ArtifactRollupExportRunResult(
            success=outcome.success,
            outcome=outcome.outcome,
            rollup_count=outcome.rollup_count,
            success_count=outcome.success_count,
            skipped_count=outcome.skipped_count,
            failed_count=outcome.failed_count,
            error=outcome.error,
        )


__all__ = ["ArtifactRollupExportJob", "ArtifactRollupExportRunResult"]
