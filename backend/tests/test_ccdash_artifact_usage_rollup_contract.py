import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models import (
    CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION,
    ArtifactOutcomePayload,
    ArtifactUsageRollup,
)


SCHEMA_PATH = Path("docs/schemas/integrations/ccdash-artifact-usage-rollup-v1.schema.json")
SAMPLE_PATH = Path("docs/schemas/integrations/ccdash-artifact-usage-rollup-v1.sample.json")

_NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
_START = datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc)
_END = datetime(2026, 4, 17, 0, 0, 0, tzinfo=timezone.utc)


def _sample_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schemaVersion": CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION,
        "generatedAt": "2026-05-06T00:05:00Z",
        "projectSlug": "ccdash-project-id",
        "skillmeatProjectId": "skillmeat-project-id",
        "collectionId": "collection-id",
        "userScope": "hosted-principal-or-pseudonymous-local-scope",
        "period": "7d",
        "artifact": {
            "definitionType": "skill",
            "externalId": "skill:frontend-design",
            "artifactUuid": "artifact-uuid",
            "versionId": "version-id",
            "contentHash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        },
        "usage": {
            "exclusiveTokens": 12000,
            "supportingTokens": 24000,
            "attributedTokens": 36000,
            "tokenInput": 30000,
            "tokenOutput": 6000,
            "costUsd": 0.55,
            "costUsdModelIO": 0.42,
            "sessionCount": 8,
            "workflowCount": 3,
            "executionCount": 10,
            "successCount": 8,
            "failureCount": 2,
            "durationMs": 480000,
            "lastObservedAt": "2026-05-06T00:00:00Z",
            "averageConfidence": 0.83,
            "contextPressure": 0.31,
        },
        "effectiveness": {
            "successScore": 0.78,
            "efficiencyScore": 0.64,
            "qualityScore": 0.72,
            "riskScore": 0.22,
            "confidence": 0.8,
            "sampleSize": 8,
        },
        "recommendations": [
            {
                "type": "load_on_demand",
                "confidence": 0.81,
                "rationaleCode": "low_recency_high_context_pressure",
                "nextAction": "Review before changing deployment profile defaults.",
                "evidence": ["narrow workflow usage", "high context pressure"],
                "affectedArtifactIds": ["artifact-uuid"],
                "scope": "project",
            }
        ],
    }
    payload.update(overrides)
    return payload


def _artifact_outcome_payload() -> dict[str, object]:
    return {
        "event_id": uuid.uuid4(),
        "definition_type": "skill",
        "external_id": "skill:my-skill",
        "period_label": "7d",
        "period_start": _START,
        "period_end": _END,
        "execution_count": 10,
        "success_count": 8,
        "failure_count": 2,
        "token_input": 1000,
        "token_output": 500,
        "cost_usd": 0.05,
        "duration_ms": 3000,
        "timestamp": _NOW,
    }


def test_schema_and_sample_files_parse_and_match_version() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    sample = json.loads(SAMPLE_PATH.read_text())

    assert schema["properties"]["schemaVersion"]["const"] == CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION
    assert schema["required"] == ["schemaVersion"]
    assert sample["schemaVersion"] == CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION
    assert ArtifactUsageRollup.model_validate(sample).schema_version == CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION


def test_rollup_round_trips_by_wire_aliases_without_data_loss() -> None:
    payload = _sample_payload()

    rollup = ArtifactUsageRollup.model_validate(payload)
    dumped = rollup.rollup_dict()

    assert dumped == payload


def test_rollup_accepts_snake_case_internal_keys_and_dumps_external_aliases() -> None:
    rollup = ArtifactUsageRollup.model_validate(
        {
            "schema_version": CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION,
            "generated_at": "2026-05-06T00:05:00Z",
            "project_slug": "ccdash-project-id",
            "skillmeat_project_id": "skillmeat-project-id",
            "artifact": {
                "definition_type": "skill",
                "external_id": "skill:frontend-design",
                "artifact_uuid": "artifact-uuid",
                "version_id": "version-id",
            },
            "usage": {
                "exclusive_tokens": 12000,
                "cost_usd_model_io": 0.42,
                "last_observed_at": "2026-05-06T00:00:00Z",
            },
            "effectiveness": {
                "success_score": 0.78,
                "sample_size": 8,
            },
            "recommendations": [
                {
                    "recommendation_type": "optimization_target",
                    "rationale_code": "high_usage_low_efficiency",
                    "next_action": "Review optimization target before scheduling changes.",
                }
            ],
        }
    )

    dumped = rollup.rollup_dict()

    assert "schemaVersion" in dumped
    assert "generatedAt" in dumped
    assert dumped["artifact"]["definitionType"] == "skill"
    assert dumped["usage"]["costUsdModelIO"] == 0.42
    assert dumped["effectiveness"]["sampleSize"] == 8
    assert dumped["recommendations"][0]["type"] == "optimization_target"


def test_rollup_rejects_wrong_schema_version() -> None:
    with pytest.raises(ValidationError):
        ArtifactUsageRollup.model_validate(_sample_payload(schemaVersion="wrong-version"))


def test_rollup_dimensions_and_metrics_are_optional() -> None:
    rollup = ArtifactUsageRollup.model_validate({"schemaVersion": CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION})

    assert rollup.project_slug is None
    assert rollup.artifact is None
    assert rollup.usage is None
    assert rollup.effectiveness is None
    assert rollup.recommendations == []


def test_rollup_rejects_negative_metrics() -> None:
    with pytest.raises(ValidationError):
        ArtifactUsageRollup.model_validate(_sample_payload(usage={"exclusiveTokens": -1}))


def test_rollup_rejects_out_of_range_effectiveness_score() -> None:
    with pytest.raises(ValidationError):
        ArtifactUsageRollup.model_validate(_sample_payload(effectiveness={"successScore": 1.01}))


def test_existing_artifact_outcome_event_dict_and_schema_remain_snake_case() -> None:
    expected_fields = {
        "event_id",
        "definition_type",
        "external_id",
        "content_hash",
        "period_label",
        "period_start",
        "period_end",
        "execution_count",
        "success_count",
        "failure_count",
        "token_input",
        "token_output",
        "cost_usd",
        "duration_ms",
        "attributed_tokens",
        "ccdash_client_version",
        "extra_metrics",
        "timestamp",
    }

    assert set(ArtifactOutcomePayload.model_fields) == expected_fields
    assert set(ArtifactOutcomePayload.model_json_schema()["properties"]) == expected_fields

    event = ArtifactOutcomePayload(**_artifact_outcome_payload()).event_dict()

    assert "schemaVersion" not in event
    assert "definitionType" not in event
    assert "definition_type" in event
    assert "external_id" in event
    assert event["period_start"] == "2026-04-10T00:00:00Z"
