"""Artifact intelligence agent query service."""
from __future__ import annotations

from backend.application.context import RequestContext
from backend.application.ports import CorePorts

from ._filters import collect_source_refs, resolve_project_scope
from backend.services.artifact_recommendation_service import ArtifactRecommendationService

from .models import ArtifactRankingsDTO, ArtifactRecommendationsDTO, SnapshotDiagnosticsDTO


class ArtifactIntelligenceQueryService:
    """Expose SkillMeat artifact intelligence diagnostics for agent transports."""

    def __init__(self) -> None:
        self.recommendation_service = ArtifactRecommendationService()

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

    async def get_rankings(
        self,
        context: RequestContext,
        ports: CorePorts,
        project_id_override: str | None = None,
        *,
        period: str = "30d",
        collection_id: str | None = None,
        user_scope: str | None = None,
        artifact_uuid: str | None = None,
        artifact_id: str | None = None,
        version_id: str | None = None,
        workflow_id: str | None = None,
        artifact_type: str | None = None,
        recommendation_type: str | None = None,
        limit: int = 25,
        bypass_cache: bool = False,  # noqa: ARG002 - reserved for transport parity
    ) -> ArtifactRankingsDTO:
        scope = resolve_project_scope(context, ports, project_id_override)
        project_id = project_id_override or getattr(getattr(context, "project", None), "project_id", "") or ""
        if scope is None:
            return ArtifactRankingsDTO(
                status="error",
                project_id=project_id,
                period=period,
                source_refs=collect_source_refs(project_id),
            )

        payload = await ports.storage.integration_snapshots().artifact_rankings().list_rankings(
            project_id=scope.project.id,
            period=period,
            collection_id=collection_id,
            user_scope=user_scope,
            artifact_uuid=artifact_uuid,
            artifact_id=artifact_id,
            version_id=version_id,
            workflow_id=workflow_id,
            artifact_type=artifact_type,
            recommendation_type=recommendation_type,
            limit=limit,
        )
        return ArtifactRankingsDTO(
            project_id=scope.project.id,
            period=period,
            total=int(payload.get("total") or 0),
            rows=payload.get("rows") or [],
            source_refs=collect_source_refs(scope.project.id),
        )

    async def get_recommendations(
        self,
        context: RequestContext,
        ports: CorePorts,
        project_id_override: str | None = None,
        *,
        period: str = "30d",
        collection_id: str | None = None,
        user_scope: str | None = None,
        workflow_id: str | None = None,
        recommendation_type: str | None = None,
        min_confidence: float | None = None,
        limit: int = 100,
        bypass_cache: bool = False,  # noqa: ARG002 - reserved for transport parity
    ) -> ArtifactRecommendationsDTO:
        scope = resolve_project_scope(context, ports, project_id_override)
        project_id = project_id_override or getattr(getattr(context, "project", None), "project_id", "") or ""
        if scope is None:
            return ArtifactRecommendationsDTO(
                status="error",
                project_id=project_id,
                period=period,
                source_refs=collect_source_refs(project_id),
            )

        payload = await ports.storage.integration_snapshots().artifact_rankings().list_rankings(
            project_id=scope.project.id,
            period=period,
            collection_id=collection_id,
            user_scope=user_scope,
            workflow_id=workflow_id,
            limit=limit,
        )
        recommendations = self.recommendation_service.generate_recommendations(
            payload.get("rows") or [],
            recommendation_type=recommendation_type,
            min_confidence=min_confidence,
        )
        return ArtifactRecommendationsDTO(
            project_id=scope.project.id,
            period=period,
            total=len(recommendations),
            recommendations=[rec.model_dump(mode="json", by_alias=True) for rec in recommendations],
            source_refs=collect_source_refs(scope.project.id),
        )
