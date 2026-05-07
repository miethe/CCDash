from datetime import datetime, timedelta, timezone

from backend.models import ArtifactRecommendation
from backend.services.artifact_recommendation_service import ArtifactRecommendationService


NOW = datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc)


def _row(
    artifact_id: str,
    *,
    artifact_uuid: str | None = None,
    version_id: str = "v1",
    workflow_id: str = "",
    sample_size: int = 6,
    session_count: int = 6,
    workflow_count: int = 2,
    confidence: float | None = 0.8,
    success_score: float | None = 0.8,
    efficiency_score: float | None = 0.8,
    risk_score: float | None = 0.1,
    context_pressure: float | None = 0.2,
    cost_usd: float = 0.1,
    identity_confidence: float | None = 1.0,
    default_load_mode: str = "on_demand",
    status: str = "active",
    snapshot_fetched_at: datetime = NOW,
    project_session_count: int = 12,
) -> dict:
    return {
        "project_id": "project-1",
        "collection_id": "collection-a",
        "user_scope": "user-a",
        "artifact_type": "skill",
        "artifact_id": artifact_id,
        "artifact_uuid": artifact_uuid or artifact_id,
        "version_id": version_id,
        "workflow_id": workflow_id,
        "period": "30d",
        "exclusive_tokens": 2000,
        "supporting_tokens": 100,
        "cost_usd": cost_usd,
        "session_count": session_count,
        "workflow_count": workflow_count,
        "avg_confidence": confidence,
        "confidence": confidence,
        "success_score": success_score,
        "efficiency_score": efficiency_score,
        "quality_score": success_score,
        "risk_score": risk_score,
        "context_pressure": context_pressure,
        "sample_size": sample_size,
        "identity_confidence": identity_confidence,
        "snapshot_fetched_at": snapshot_fetched_at.isoformat().replace("+00:00", "Z"),
        "evidence": {
            "projectSessionCount": project_session_count,
            "snapshot": {
                "defaultLoadMode": default_load_mode,
                "status": status,
            },
        },
        "computed_at": NOW.isoformat().replace("+00:00", "Z"),
    }


def test_generates_all_advisory_recommendation_types() -> None:
    rows = [
        _row("unused", sample_size=0, session_count=0, confidence=None, default_load_mode="always"),
        _row("narrow", workflow_count=1, context_pressure=0.82, default_load_mode="always"),
        _row("expensive", sample_size=8, session_count=8, efficiency_score=0.3, cost_usd=2.5),
        _row("unresolved", identity_confidence=None),
        _row("cold", sample_size=1, session_count=1, confidence=None, project_session_count=1),
        _row("versioned", artifact_uuid="artifact-versioned", version_id="v1", success_score=0.92),
        _row("versioned", artifact_uuid="artifact-versioned", version_id="v2", success_score=0.65),
        _row("swap-current", workflow_id="workflow-a", success_score=0.55, efficiency_score=0.45),
        _row("swap-alt", workflow_id="workflow-a", success_score=0.86, efficiency_score=0.8),
    ]

    recommendations = ArtifactRecommendationService(min_sample_size=3).generate_recommendations(rows, now=NOW)
    types = {rec.recommendation_type for rec in recommendations}

    assert types == {
        "disable_candidate",
        "load_on_demand",
        "workflow_specific_swap",
        "optimization_target",
        "version_regression",
        "identity_reconciliation",
        "insufficient_data",
    }
    assert all(isinstance(rec, ArtifactRecommendation) for rec in recommendations)
    assert "auto_apply" not in ArtifactRecommendation.model_fields
    assert "patch_payload" not in ArtifactRecommendation.model_fields


def test_low_confidence_suppresses_actionable_recommendations() -> None:
    rows = [
        _row(
            "expensive",
            sample_size=8,
            session_count=8,
            confidence=0.4,
            efficiency_score=0.2,
            cost_usd=3.0,
        )
    ]

    recommendations = ArtifactRecommendationService(min_sample_size=3).generate_recommendations(rows, now=NOW)

    assert [rec.recommendation_type for rec in recommendations] == ["insufficient_data"]
    assert recommendations[0].rationale_code == "confidence_below_threshold"


def test_stale_snapshot_suppresses_destructive_recommendation_type() -> None:
    stale = NOW - timedelta(days=8)
    rows = [
        _row(
            "unused",
            sample_size=0,
            session_count=0,
            confidence=None,
            default_load_mode="always",
            snapshot_fetched_at=stale,
        )
    ]

    recommendations = ArtifactRecommendationService(min_sample_size=3).generate_recommendations(rows, now=NOW)

    assert [rec.recommendation_type for rec in recommendations] == ["insufficient_data"]
    assert recommendations[0].rationale_code == "stale_snapshot"
    assert recommendations[0].evidence["suppressedType"] == "disable_candidate"
