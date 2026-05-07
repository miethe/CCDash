"""Advisory artifact optimization recommendations from ranking evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend import config
from backend.models import ArtifactRecommendation, ArtifactRecommendationType


DEFAULT_STALENESS_THRESHOLDS_SECONDS: dict[str, int] = {
    "disable_candidate": config.CCDASH_SNAPSHOT_FRESHNESS_DISABLE_CANDIDATE_SECONDS,
    "workflow_specific_swap": config.CCDASH_SNAPSHOT_FRESHNESS_WORKFLOW_SPECIFIC_SWAP_SECONDS,
    "load_on_demand": config.CCDASH_SNAPSHOT_FRESHNESS_LOAD_ON_DEMAND_SECONDS,
    "version_regression": config.CCDASH_SNAPSHOT_FRESHNESS_VERSION_REGRESSION_SECONDS,
    "optimization_target": config.CCDASH_SNAPSHOT_FRESHNESS_OPTIMIZATION_TARGET_SECONDS,
    "identity_reconciliation": config.CCDASH_SNAPSHOT_FRESHNESS_IDENTITY_RECONCILIATION_SECONDS,
    "insufficient_data": config.CCDASH_SNAPSHOT_FRESHNESS_INSUFFICIENT_DATA_SECONDS,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _parse_dt(value: Any) -> datetime | None:
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


def _clip_confidence(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _snapshot_is_stale(row: dict[str, Any], *, now: datetime, max_age_seconds: int) -> bool:
    fetched_at = _parse_dt(row.get("snapshot_fetched_at") or row.get("snapshotFetchedAt"))
    if fetched_at is None:
        return True
    return (now - fetched_at).total_seconds() > max_age_seconds


def _snapshot_fetched_at(row: dict[str, Any]) -> Any:
    return row.get("snapshot_fetched_at") or row.get("snapshotFetchedAt")


def _artifact_key(row: dict[str, Any]) -> str:
    return str(row.get("artifact_uuid") or row.get("artifactUuid") or row.get("artifact_id") or row.get("artifactId") or "")


def _recommendation(
    row: dict[str, Any],
    rec_type: ArtifactRecommendationType,
    *,
    confidence: float | None,
    rationale_code: str,
    next_action: str,
    evidence: dict[str, Any],
    affected_artifact_ids: list[str] | None = None,
    scope: str | None = None,
) -> ArtifactRecommendation:
    return ArtifactRecommendation(
        recommendation_type=rec_type,
        confidence=confidence,
        rationale_code=rationale_code,
        next_action=next_action,
        evidence=evidence,
        affected_artifact_ids=affected_artifact_ids or [_artifact_key(row)],
        scope=scope or str(row.get("workflow_id") or row.get("workflowId") or row.get("collection_id") or row.get("collectionId") or "project"),
        project_id=str(row.get("project_id") or row.get("projectId") or ""),
        collection_id=str(row.get("collection_id") or row.get("collectionId") or "") or None,
        user_scope=str(row.get("user_scope") or row.get("userScope") or "") or None,
        workflow_id=str(row.get("workflow_id") or row.get("workflowId") or "") or None,
        period=str(row.get("period") or ""),
    )


class ArtifactRecommendationService:
    """Classify ranking rows into advisory-only recommendations."""

    def __init__(
        self,
        *,
        min_sample_size: int | None = None,
        min_confidence: float | None = None,
        staleness_thresholds_seconds: dict[str, int] | None = None,
    ) -> None:
        self.min_sample_size = min_sample_size or config.CCDASH_RANKING_MIN_SAMPLE_SIZE
        self.min_confidence = min_confidence if min_confidence is not None else config.CCDASH_RECOMMENDATION_MIN_CONFIDENCE
        self.staleness_thresholds_seconds = {
            **DEFAULT_STALENESS_THRESHOLDS_SECONDS,
            **(staleness_thresholds_seconds or {}),
        }

    def generate_recommendations(
        self,
        rows: list[dict[str, Any]],
        *,
        recommendation_type: str | None = None,
        min_confidence: float | None = None,
        now: datetime | None = None,
    ) -> list[ArtifactRecommendation]:
        threshold = self.min_confidence if min_confidence is None else min_confidence
        current_time = now or datetime.now(timezone.utc)
        recommendations: list[ArtifactRecommendation] = []
        aggregate_rows = [row for row in rows if not self._is_workflow_row(row)]
        workflow_rows = [row for row in rows if self._is_workflow_row(row)]
        target_rows = aggregate_rows or rows
        for row in target_rows:
            recommendations.extend(self._row_recommendations(row, rows, threshold=threshold, now=current_time))
        for row in workflow_rows:
            recommendations.extend(self._workflow_row_recommendations(row, rows, threshold=threshold, now=current_time))

        if recommendation_type:
            recommendations = [rec for rec in recommendations if rec.recommendation_type == recommendation_type]
        return recommendations

    def _is_workflow_row(self, row: dict[str, Any]) -> bool:
        return bool(str(row.get("workflow_id") or row.get("workflowId") or ""))

    def _row_recommendations(
        self,
        row: dict[str, Any],
        all_rows: list[dict[str, Any]],
        *,
        threshold: float,
        now: datetime,
    ) -> list[ArtifactRecommendation]:
        evidence = _safe_mapping(row.get("evidence") or row.get("evidence_json"))
        sample_size = _safe_int(row.get("sample_size") or row.get("sampleSize"))
        project_session_count = _safe_int(evidence.get("projectSessionCount"), sample_size)
        confidence = row.get("confidence")
        confidence_value = None if confidence is None else _safe_float(confidence)
        session_count = _safe_int(row.get("session_count") or row.get("sessionCount"))
        exclusive_tokens = _safe_int(row.get("exclusive_tokens") or row.get("exclusiveTokens"))
        cost_usd = _safe_float(row.get("cost_usd") or row.get("costUsd"))
        workflow_count = _safe_int(row.get("workflow_count") or row.get("workflowCount"))
        context_pressure = _safe_float(row.get("context_pressure") or row.get("contextPressure"))
        efficiency_score = row.get("efficiency_score") if "efficiency_score" in row else row.get("efficiencyScore")
        risk_score = row.get("risk_score") if "risk_score" in row else row.get("riskScore")
        success_score = row.get("success_score") if "success_score" in row else row.get("successScore")
        snapshot = dict(evidence.get("snapshot") or {})
        load_mode = str(snapshot.get("defaultLoadMode") or snapshot.get("default_load_mode") or "").strip()
        status = str(snapshot.get("status") or "").strip()

        recommendations: list[ArtifactRecommendation] = []

        if project_session_count < self.min_sample_size:
            return [
                _recommendation(
                    row,
                    "insufficient_data",
                    confidence=None,
                    rationale_code="sample_below_threshold",
                    next_action="Collect more attributed sessions before acting on this artifact.",
                    evidence={"sampleSize": sample_size, "minSampleSize": self.min_sample_size},
                )
            ]

        if (
            sample_size == 0
            and load_mode == "always"
            and status != "disabled"
        ):
            if self._type_is_stale(row, "disable_candidate", now):
                self._append_stale_snapshot_recommendation(recommendations, row, suppressed_type="disable_candidate")
                return recommendations
            recommendations.append(
                _recommendation(
                    row,
                    "disable_candidate",
                    confidence=0.65,
                    rationale_code="always_loaded_zero_usage",
                    next_action="Consider disabling or unbundling this artifact after human review.",
                    evidence={
                        "sessionCount": session_count,
                        "projectSessionCount": project_session_count,
                        "loadMode": load_mode,
                        "status": status,
                    },
                )
            )
            return recommendations

        if sample_size < self.min_sample_size:
            return [
                _recommendation(
                    row,
                    "insufficient_data",
                    confidence=confidence_value,
                    rationale_code="artifact_sample_below_threshold",
                    next_action="Collect more attributed sessions for this artifact before acting on it.",
                    evidence={
                        "sampleSize": sample_size,
                        "projectSessionCount": project_session_count,
                        "minSampleSize": self.min_sample_size,
                    },
                )
            ]

        if confidence_value is None or confidence_value < threshold:
            return [
                _recommendation(
                    row,
                    "insufficient_data",
                    confidence=confidence_value,
                    rationale_code="confidence_below_threshold",
                    next_action="Improve attribution confidence before making optimization decisions.",
                    evidence={"confidence": confidence_value, "minConfidence": threshold},
                )
            ]

        identity_confidence = row.get("identity_confidence") if "identity_confidence" in row else row.get("identityConfidence")
        if identity_confidence is None and session_count > 0:
            recommendations.append(
                _recommendation(
                    row,
                    "identity_reconciliation",
                    confidence=_clip_confidence(confidence_value),
                    rationale_code="unresolved_identity_with_usage",
                    next_action="Review the SkillMeat identity mapping for this observed artifact.",
                    evidence={"sessionCount": session_count, "artifactId": row.get("artifact_id") or row.get("artifactId")},
                )
            )

        if load_mode == "always" and status != "disabled" and session_count == 0:
            if self._type_is_stale(row, "disable_candidate", now):
                self._append_stale_snapshot_recommendation(recommendations, row, suppressed_type="disable_candidate")
            else:
                recommendations.append(
                    _recommendation(
                        row,
                        "disable_candidate",
                        confidence=_clip_confidence(confidence_value),
                        rationale_code="always_loaded_zero_usage",
                        next_action="Consider disabling or unbundling this artifact after human review.",
                        evidence={"sessionCount": session_count, "loadMode": load_mode, "status": status},
                    )
                )

        if session_count >= self.min_sample_size and workflow_count <= 1 and context_pressure >= 0.75 and load_mode in {"always", "workflow_scoped"}:
            if self._type_is_stale(row, "load_on_demand", now):
                self._append_stale_snapshot_recommendation(recommendations, row, suppressed_type="load_on_demand")
            else:
                recommendations.append(
                    _recommendation(
                        row,
                        "load_on_demand",
                        confidence=_clip_confidence(confidence_value * 0.9),
                        rationale_code="narrow_workflow_high_context_pressure",
                        next_action="Consider loading this artifact only for the workflow where it is observed.",
                        evidence={"workflowCount": workflow_count, "contextPressure": context_pressure, "loadMode": load_mode},
                    )
                )

        if session_count >= self.min_sample_size * 2 and (
            (efficiency_score is not None and _safe_float(efficiency_score) < 0.55)
            or cost_usd >= 1.0
            or (risk_score is not None and _safe_float(risk_score) >= 0.55)
        ):
            if self._type_is_stale(row, "optimization_target", now):
                self._append_stale_snapshot_recommendation(recommendations, row, suppressed_type="optimization_target")
            else:
                recommendations.append(
                    _recommendation(
                        row,
                        "optimization_target",
                        confidence=_clip_confidence(confidence_value),
                        rationale_code="high_utilization_poor_efficiency_or_risk",
                        next_action="Prioritize this artifact for an optimization pass.",
                        evidence={
                            "sessionCount": session_count,
                            "exclusiveTokens": exclusive_tokens,
                            "costUsd": cost_usd,
                            "efficiencyScore": efficiency_score,
                            "riskScore": risk_score,
                        },
                    )
                )

        recommendations.extend(self._version_regression_recommendations(row, all_rows, confidence_value, success_score, now))
        return recommendations

    def _workflow_row_recommendations(
        self,
        row: dict[str, Any],
        all_rows: list[dict[str, Any]],
        *,
        threshold: float,
        now: datetime,
    ) -> list[ArtifactRecommendation]:
        sample_size = _safe_int(row.get("sample_size") or row.get("sampleSize"))
        confidence = row.get("confidence")
        confidence_value = None if confidence is None else _safe_float(confidence)
        if sample_size < self.min_sample_size or confidence_value is None or confidence_value < threshold:
            return []
        if self._type_is_stale(row, "workflow_specific_swap", now):
            recommendations: list[ArtifactRecommendation] = []
            self._append_stale_snapshot_recommendation(recommendations, row, suppressed_type="workflow_specific_swap")
            return recommendations
        return self._workflow_swap_recommendations(row, all_rows, confidence_value)

    def _workflow_swap_recommendations(
        self,
        row: dict[str, Any],
        all_rows: list[dict[str, Any]],
        confidence_value: float,
    ) -> list[ArtifactRecommendation]:
        workflow_id = str(row.get("workflow_id") or row.get("workflowId") or "")
        if not workflow_id:
            return []
        current_success = row.get("success_score") if "success_score" in row else row.get("successScore")
        current_efficiency = row.get("efficiency_score") if "efficiency_score" in row else row.get("efficiencyScore")
        current_success_f = _safe_float(current_success, -1.0)
        current_efficiency_f = _safe_float(current_efficiency, -1.0)
        if current_success_f < 0 or _safe_int(row.get("sample_size") or row.get("sampleSize")) < self.min_sample_size:
            return []
        for candidate in all_rows:
            if candidate is row or str(candidate.get("workflow_id") or candidate.get("workflowId") or "") != workflow_id:
                continue
            if _safe_int(candidate.get("sample_size") or candidate.get("sampleSize")) < self.min_sample_size:
                continue
            alt_success = _safe_float(candidate.get("success_score") if "success_score" in candidate else candidate.get("successScore"), -1.0)
            alt_efficiency = _safe_float(candidate.get("efficiency_score") if "efficiency_score" in candidate else candidate.get("efficiencyScore"), -1.0)
            if alt_success - current_success_f >= 0.15 or alt_efficiency - current_efficiency_f >= 0.2:
                return [
                    _recommendation(
                        row,
                        "workflow_specific_swap",
                        confidence=_clip_confidence(confidence_value * 0.85),
                        rationale_code="workflow_alternative_outperforms",
                        next_action="Review whether this workflow should prefer the better-performing artifact.",
                        evidence={
                            "workflowId": workflow_id,
                            "currentArtifact": _artifact_key(row),
                            "alternativeArtifact": _artifact_key(candidate),
                            "currentSuccessScore": current_success_f,
                            "alternativeSuccessScore": alt_success,
                            "currentEfficiencyScore": current_efficiency_f,
                            "alternativeEfficiencyScore": alt_efficiency,
                        },
                        affected_artifact_ids=[_artifact_key(row), _artifact_key(candidate)],
                        scope=workflow_id,
                    )
                ]
        return []

    def _version_regression_recommendations(
        self,
        row: dict[str, Any],
        all_rows: list[dict[str, Any]],
        confidence_value: float,
        success_score: Any,
        now: datetime,
    ) -> list[ArtifactRecommendation]:
        artifact_uuid = str(row.get("artifact_uuid") or row.get("artifactUuid") or "")
        version_id = str(row.get("version_id") or row.get("versionId") or "")
        if not artifact_uuid or not version_id:
            return []
        current_success = _safe_float(success_score, -1.0)
        if current_success < 0 or _safe_int(row.get("sample_size") or row.get("sampleSize")) < self.min_sample_size:
            return []
        if self._type_is_stale(row, "version_regression", now):
            recommendations: list[ArtifactRecommendation] = []
            self._append_stale_snapshot_recommendation(recommendations, row, suppressed_type="version_regression")
            return recommendations
        prior_rows = [
            candidate
            for candidate in all_rows
            if str(candidate.get("artifact_uuid") or candidate.get("artifactUuid") or "") == artifact_uuid
            and str(candidate.get("version_id") or candidate.get("versionId") or "") != version_id
            and not str(candidate.get("workflow_id") or candidate.get("workflowId") or "")
            and _safe_int(candidate.get("sample_size") or candidate.get("sampleSize")) >= self.min_sample_size
        ]
        for prior in prior_rows:
            prior_success = _safe_float(prior.get("success_score") if "success_score" in prior else prior.get("successScore"), -1.0)
            if prior_success - current_success >= 0.15 and str(prior.get("version_id") or prior.get("versionId") or "") < version_id:
                return [
                    _recommendation(
                        row,
                        "version_regression",
                        confidence=_clip_confidence(confidence_value),
                        rationale_code="newer_version_underperforms_prior",
                        next_action="Compare this version against the prior version before broader rollout.",
                        evidence={
                            "artifactUuid": artifact_uuid,
                            "currentVersionId": version_id,
                            "priorVersionId": prior.get("version_id") or prior.get("versionId"),
                            "currentSuccessScore": current_success,
                            "priorSuccessScore": prior_success,
                        },
                    )
                ]
        return []

    def _type_is_stale(self, row: dict[str, Any], rec_type: str, now: datetime) -> bool:
        max_age_seconds = self.staleness_thresholds_seconds.get(rec_type)
        if max_age_seconds is None:
            return False
        return _snapshot_is_stale(row, now=now, max_age_seconds=max_age_seconds)

    def _append_stale_snapshot_recommendation(
        self,
        recommendations: list[ArtifactRecommendation],
        row: dict[str, Any],
        *,
        suppressed_type: str,
    ) -> None:
        if any(rec.recommendation_type == "insufficient_data" and rec.rationale_code == "stale_snapshot" for rec in recommendations):
            return
        recommendations.append(
            _recommendation(
                row,
                "insufficient_data",
                confidence=None,
                rationale_code="stale_snapshot",
                next_action="Refresh the SkillMeat artifact snapshot before acting on state-changing recommendations.",
                evidence={"snapshotFetchedAt": _snapshot_fetched_at(row), "suppressedType": suppressed_type},
            )
        )
