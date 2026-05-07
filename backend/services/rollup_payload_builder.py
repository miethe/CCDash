"""Build export-safe artifact usage rollups from persisted ranking rows."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from backend import config
from backend.db.factory import get_artifact_ranking_repository
from backend.models import (
    CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION,
    ArtifactEffectivenessStats,
    ArtifactRecommendation,
    ArtifactRecommendationEmbed,
    ArtifactUsageRollup,
    ArtifactUsageRollupArtifactRef,
    ArtifactUsageStats,
)
from backend.services.artifact_recommendation_service import ArtifactRecommendationService


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _score(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return round(max(0.0, min(1.0, _safe_float(value))), 4)


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _evidence(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("evidence")
    return value if isinstance(value, dict) else {}


def _snapshot(row: dict[str, Any]) -> dict[str, Any]:
    snapshot = _evidence(row).get("snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _content_hash(row: dict[str, Any]) -> str | None:
    snapshot = _snapshot(row)
    value = snapshot.get("contentHash") or snapshot.get("content_hash")
    return str(value).strip() or None


def _artifact_key(row: dict[str, Any]) -> str:
    return (
        str(row.get("artifact_uuid") or "").strip()
        or str(row.get("artifact_id") or "").strip()
        or str(row.get("artifactId") or "").strip()
    )


def _recommendation_key(recommendation: ArtifactRecommendation) -> tuple[str, str, str]:
    return (
        recommendation.recommendation_type,
        recommendation.rationale_code,
        recommendation.scope,
    )


class RollupPayloadBuilder:
    """Transform artifact ranking rows into schema v1 rollup payloads."""

    def __init__(
        self,
        *,
        recommendation_service: ArtifactRecommendationService | None = None,
    ) -> None:
        self.recommendation_service = recommendation_service or ArtifactRecommendationService()

    async def build_rollups(
        self,
        db: Any,
        *,
        project_id: str,
        period: str,
        skillmeat_project_id: str | None = None,
        collection_id: str | None = None,
        generated_at: datetime | None = None,
        hosted: bool | None = None,
    ) -> list[ArtifactUsageRollup]:
        ranking_repo = get_artifact_ranking_repository(db)
        rows = await self._load_rows(
            ranking_repo,
            project_id=project_id,
            period=period,
            collection_id=collection_id,
        )
        if not rows:
            return []

        generated = (generated_at or _utc_now()).astimezone(timezone.utc)
        recommendations = self.recommendation_service.generate_recommendations(rows, now=generated)
        recommendations_by_artifact = self._recommendations_by_artifact(recommendations)

        grouped: dict[tuple[str, str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            effective_collection = str(row.get("collection_id") or collection_id or "").strip()
            normalized_user_scope = self._user_scope(row.get("user_scope"), hosted=hosted)
            key = (
                str(row.get("project_id") or project_id),
                effective_collection,
                normalized_user_scope or "",
                _artifact_key(row),
                str(row.get("version_id") or ""),
                str(row.get("period") or period),
            )
            grouped[key].append({**row, "collection_id": effective_collection, "user_scope": normalized_user_scope})

        rollups = [
            self._rollup_from_group(
                rows=group_rows,
                project_id=project_id,
                skillmeat_project_id=skillmeat_project_id,
                generated_at=generated,
                recommendations_by_artifact=recommendations_by_artifact,
            )
            for group_rows in grouped.values()
        ]
        rollups.sort(
            key=lambda item: (
                item.collection_id or "",
                item.artifact.artifact_uuid if item.artifact else "",
                item.artifact.external_id if item.artifact else "",
                item.period or "",
            )
        )
        return rollups

    async def _load_rows(
        self,
        ranking_repo: Any,
        *,
        project_id: str,
        period: str,
        collection_id: str | None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            payload = await ranking_repo.list_rankings(
                project_id=project_id,
                period=period,
                collection_id=collection_id,
                limit=500,
                cursor=cursor,
            )
            batch = payload.get("rows", []) if isinstance(payload, dict) else []
            rows.extend([row for row in batch if isinstance(row, dict)])
            cursor = str(payload.get("next_cursor") or "") if isinstance(payload, dict) else ""
            if not cursor:
                break
        return rows

    def _user_scope(self, raw_scope: Any, *, hosted: bool | None) -> str | None:
        mode = str(getattr(config, "CCDASH_LOCAL_USER_ROLLUP_SCOPE_MODE", "pseudonym") or "pseudonym").lower()
        current_hosted = bool(hosted) if hosted is not None else config.STORAGE_PROFILE.profile == "enterprise"
        scope = str(raw_scope or "").strip()
        if current_hosted:
            return scope if scope and scope != "all" else None
        if mode == "omit":
            return None
        if scope and scope != "all":
            return scope
        return str(getattr(config, "CCDASH_LOCAL_USER_SCOPE_PSEUDONYM", "local-user") or "local-user")

    def _recommendations_by_artifact(
        self,
        recommendations: list[ArtifactRecommendation],
    ) -> dict[str, list[ArtifactRecommendation]]:
        mapped: dict[str, list[ArtifactRecommendation]] = defaultdict(list)
        seen: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
        for recommendation in recommendations:
            key = _recommendation_key(recommendation)
            for artifact_id in recommendation.affected_artifact_ids:
                token = str(artifact_id or "").strip()
                if not token or key in seen[token]:
                    continue
                mapped[token].append(recommendation)
                seen[token].add(key)
        return mapped

    def _rollup_from_group(
        self,
        *,
        rows: list[dict[str, Any]],
        project_id: str,
        skillmeat_project_id: str | None,
        generated_at: datetime,
        recommendations_by_artifact: dict[str, list[ArtifactRecommendation]],
    ) -> ArtifactUsageRollup:
        metric_rows = [row for row in rows if not str(row.get("workflow_id") or "").strip()] or rows
        base = metric_rows[0]
        artifact_keys = {
            str(base.get("artifact_uuid") or "").strip(),
            str(base.get("artifact_id") or "").strip(),
        }
        recommendations = []
        for key in artifact_keys:
            recommendations.extend(recommendations_by_artifact.get(key, []))

        return ArtifactUsageRollup(
            schema_version=CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION,
            generated_at=generated_at,
            project_slug=project_id,
            skillmeat_project_id=skillmeat_project_id or project_id,
            collection_id=str(base.get("collection_id") or "") or None,
            user_scope=str(base.get("user_scope") or "") or None,
            period=str(base.get("period") or "") or None,
            artifact=ArtifactUsageRollupArtifactRef(
                definition_type=str(base.get("artifact_type") or "") or None,
                external_id=str(base.get("artifact_id") or "") or None,
                artifact_uuid=str(base.get("artifact_uuid") or "") or None,
                version_id=str(base.get("version_id") or "") or None,
                content_hash=_content_hash(base),
            ),
            usage=self._usage(metric_rows),
            effectiveness=self._effectiveness(metric_rows),
            recommendations=self._embed_recommendations(recommendations),
        )

    def _usage(self, rows: list[dict[str, Any]]) -> ArtifactUsageStats:
        exclusive_tokens = sum(_safe_int(row.get("exclusive_tokens")) for row in rows)
        supporting_tokens = sum(_safe_int(row.get("supporting_tokens")) for row in rows)
        session_count = sum(_safe_int(row.get("session_count")) for row in rows)
        success_scores = [_safe_float(row.get("success_score"), -1.0) for row in rows if row.get("success_score") is not None]
        success_count = round(session_count * max(success_scores)) if success_scores else None
        failure_count = max(0, session_count - success_count) if success_count is not None else None
        return ArtifactUsageStats(
            exclusive_tokens=exclusive_tokens,
            supporting_tokens=supporting_tokens,
            attributed_tokens=exclusive_tokens + supporting_tokens,
            cost_usd=round(sum(_safe_float(row.get("cost_usd")) for row in rows), 6),
            session_count=session_count,
            workflow_count=max((_safe_int(row.get("workflow_count")) for row in rows), default=0),
            execution_count=session_count,
            success_count=success_count,
            failure_count=failure_count,
            last_observed_at=self._latest_observed_at(rows),
            average_confidence=self._weighted_score(rows, "avg_confidence"),
            context_pressure=self._weighted_score(rows, "context_pressure"),
        )

    def _effectiveness(self, rows: list[dict[str, Any]]) -> ArtifactEffectivenessStats:
        return ArtifactEffectivenessStats(
            success_score=self._weighted_score(rows, "success_score"),
            efficiency_score=self._weighted_score(rows, "efficiency_score"),
            quality_score=self._weighted_score(rows, "quality_score"),
            risk_score=self._weighted_score(rows, "risk_score"),
            confidence=self._weighted_score(rows, "confidence"),
            sample_size=sum(_safe_int(row.get("sample_size")) for row in rows),
        )

    def _weighted_score(self, rows: list[dict[str, Any]], field: str) -> float | None:
        total = 0.0
        weight_total = 0
        for row in rows:
            value = _score(row.get(field))
            if value is None:
                continue
            weight = max(1, _safe_int(row.get("sample_size") or row.get("session_count"), 1))
            total += value * weight
            weight_total += weight
        if weight_total <= 0:
            return None
        return round(total / weight_total, 4)

    def _latest_observed_at(self, rows: list[dict[str, Any]]) -> datetime | None:
        values = [_timestamp(row.get("last_observed_at")) for row in rows]
        present = [value for value in values if value is not None]
        return max(present) if present else None

    def _embed_recommendations(
        self,
        recommendations: list[ArtifactRecommendation],
    ) -> list[ArtifactRecommendationEmbed]:
        embedded: list[ArtifactRecommendationEmbed] = []
        seen: set[tuple[str, str, str]] = set()
        for recommendation in recommendations:
            key = _recommendation_key(recommendation)
            if key in seen:
                continue
            seen.add(key)
            embedded.append(
                ArtifactRecommendationEmbed(
                    recommendation_type=recommendation.recommendation_type,
                    confidence=recommendation.confidence,
                    rationale_code=recommendation.rationale_code,
                    next_action=recommendation.next_action,
                    evidence=self._evidence_strings(recommendation.evidence),
                    affected_artifact_ids=recommendation.affected_artifact_ids,
                    scope=recommendation.scope,
                )
            )
        return embedded

    def _evidence_strings(self, evidence: dict[str, Any]) -> list[str]:
        safe: list[str] = []
        for key, value in sorted(evidence.items()):
            if isinstance(value, (str, int, float, bool)) and len(safe) < 6:
                safe.append(f"{key}={value}")
            elif isinstance(value, list) and len(safe) < 6:
                safe.append(f"{key}.count={len(value)}")
            elif isinstance(value, dict) and len(safe) < 6:
                safe.append(f"{key}.keys={','.join(sorted(str(item) for item in value.keys())[:6])}")
        return safe
