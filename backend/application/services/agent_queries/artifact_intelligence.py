"""Artifact intelligence agent query service."""
from __future__ import annotations

from backend.application.context import RequestContext
from backend.application.ports import CorePorts

from ._filters import collect_source_refs, resolve_project_scope
from .models import SnapshotDiagnosticsDTO


class ArtifactIntelligenceQueryService:
    """Expose SkillMeat artifact intelligence diagnostics for agent transports."""

    async def get_snapshot_diagnostics(
        self,
        context: RequestContext,
        ports: CorePorts,
        project_id_override: str | None = None,
        *,
        bypass_cache: bool = False,  # noqa: ARG002 - kept for REST parity with cached query services
    ) -> SnapshotDiagnosticsDTO:
        scope = resolve_project_scope(context, ports, project_id_override)
        project_id = project_id_override or getattr(getattr(context, "project", None), "project_id", "") or ""
        if scope is None:
            return SnapshotDiagnosticsDTO(
                status="error",
                project_id=project_id,
                source_refs=collect_source_refs(project_id),
            )

        diagnostics = await ports.storage.integration_snapshots().artifact_snapshots().get_snapshot_diagnostics(
            scope.project.id
        )
        return SnapshotDiagnosticsDTO(
            project_id=diagnostics.project_id,
            snapshot_age_seconds=diagnostics.snapshot_age_seconds,
            artifact_count=diagnostics.artifact_count,
            resolved_count=diagnostics.resolved_count,
            unresolved_count=diagnostics.unresolved_count,
            is_stale=diagnostics.is_stale,
            source_refs=collect_source_refs(scope.project.id),
        )
