from datetime import datetime, timedelta, timezone

from backend.services.artifact_recommendation_service import ArtifactRecommendationService


NOW = datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc)


def _row(artifact_id: str, **overrides) -> dict:
    row = {
        "project_id": "project-1",
        "collection_id": "collection-a",
        "user_scope": "all",
        "artifact_type": "skill",
        "artifact_id": artifact_id,
        "artifact_uuid": artifact_id,
        "version_id": "v1",
        "workflow_id": "",
        "period": "30d",
        "exclusive_tokens": 5000,
        "supporting_tokens": 0,
        "cost_usd": 0.2,
        "session_count": 6,
        "workflow_count": 2,
        "confidence": 0.85,
        "success_score": 0.8,
        "efficiency_score": 0.8,
        "quality_score": 0.8,
        "risk_score": 0.2,
        "context_pressure": 0.3,
        "sample_size": 6,
        "identity_confidence": 1.0,
        "snapshot_fetched_at": NOW.isoformat().replace("+00:00", "Z"),
        "evidence": {
            "projectSessionCount": 10,
            "snapshot": {"defaultLoadMode": "on_demand", "status": "active"},
        },
    }
    row.update(overrides)
    return row


def _types(rows: list[dict], **kwargs) -> set[str]:
    recommendations = ArtifactRecommendationService(min_sample_size=3).generate_recommendations(
        rows,
        now=NOW,
        **kwargs,
    )
    return {rec.recommendation_type for rec in recommendations}


def test_calibration_high_usage_artifact_is_optimization_target() -> None:
    rows = [_row("expensive", session_count=8, sample_size=8, efficiency_score=0.25, cost_usd=2.0)]

    assert _types(rows) == {"optimization_target"}


def test_calibration_zero_usage_always_loaded_artifact_is_disable_candidate() -> None:
    rows = [
        _row(
            "unused",
            session_count=0,
            sample_size=0,
            confidence=None,
            evidence={"projectSessionCount": 10, "snapshot": {"defaultLoadMode": "always", "status": "active"}},
        )
    ]

    assert _types(rows) == {"disable_candidate"}


def test_calibration_narrow_workflow_high_pressure_artifact_loads_on_demand() -> None:
    rows = [
        _row(
            "narrow",
            workflow_count=1,
            context_pressure=0.85,
            evidence={"projectSessionCount": 10, "snapshot": {"defaultLoadMode": "always", "status": "active"}},
        )
    ]

    assert _types(rows) == {"load_on_demand"}


def test_calibration_version_regression_detects_newer_underperforming_version() -> None:
    rows = [
        _row("versioned", artifact_uuid="uuid-versioned", version_id="v1", success_score=0.92),
        _row("versioned", artifact_uuid="uuid-versioned", version_id="v2", success_score=0.65),
    ]

    assert _types(rows) == {"version_regression"}


def test_calibration_cold_start_suppresses_actions_except_insufficient_data() -> None:
    rows = [
        _row(
            "cold",
            session_count=1,
            sample_size=1,
            confidence=None,
            efficiency_score=0.1,
            cost_usd=4.0,
            evidence={"projectSessionCount": 1, "snapshot": {"defaultLoadMode": "always", "status": "active"}},
        )
    ]

    assert _types(rows) == {"insufficient_data"}


def test_calibration_stale_snapshot_suppresses_destructive_types() -> None:
    stale = (NOW - timedelta(days=10)).isoformat().replace("+00:00", "Z")
    rows = [
        _row(
            "unused",
            session_count=0,
            sample_size=0,
            confidence=None,
            snapshot_fetched_at=stale,
            evidence={"projectSessionCount": 10, "snapshot": {"defaultLoadMode": "always", "status": "active"}},
        )
    ]

    assert _types(rows) == {"insufficient_data"}
