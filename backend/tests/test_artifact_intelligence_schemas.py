import copy
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models import (
    CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION,
    SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION,
    ArtifactOutcomePayload,
    ArtifactUsageRollup,
    SkillMeatArtifactSnapshot,
)


SNAPSHOT_SCHEMA_PATH = Path("docs/schemas/integrations/skillmeat-artifact-snapshot-v1.schema.json")
SNAPSHOT_SAMPLE_PATH = Path("docs/schemas/integrations/skillmeat-artifact-snapshot-v1.sample.json")
ROLLUP_SCHEMA_PATH = Path("docs/schemas/integrations/ccdash-artifact-usage-rollup-v1.schema.json")
ROLLUP_SAMPLE_PATH = Path("docs/schemas/integrations/ccdash-artifact-usage-rollup-v1.sample.json")

_NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
_START = datetime(2026, 4, 10, 0, 0, 0, tzinfo=timezone.utc)
_END = datetime(2026, 4, 17, 0, 0, 0, tzinfo=timezone.utc)


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def _validate_json_schema(schema_path: Path, payload: dict[str, object]) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = _load_json(schema_path)
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator_cls(schema, format_checker=jsonschema.FormatChecker()).validate(payload)


def _minimal_snapshot_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schemaVersion": SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION,
        "generatedAt": "2026-05-06T00:00:00Z",
        "projectId": "skillmeat-project-id",
        "artifacts": [
            {
                "definitionType": "skill",
                "externalId": "skill:frontend-design",
                "artifactUuid": "artifact-uuid",
                "displayName": "frontend-design",
                "versionId": "version-id",
                "contentHash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "defaultLoadMode": "always",
                "status": "active",
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


def test_snapshot_json_schema_validates_sample_payload() -> None:
    sample = _load_json(SNAPSHOT_SAMPLE_PATH)

    _validate_json_schema(SNAPSHOT_SCHEMA_PATH, sample)


def test_snapshot_pydantic_round_trips_sample_without_data_loss() -> None:
    sample = _load_json(SNAPSHOT_SAMPLE_PATH)

    snapshot = SkillMeatArtifactSnapshot.model_validate(sample)
    dumped = snapshot.snapshot_dict()

    assert dumped == sample
    assert SkillMeatArtifactSnapshot.model_validate(dumped).snapshot_dict() == dumped


def test_snapshot_optional_defaults_are_applied() -> None:
    snapshot = SkillMeatArtifactSnapshot.model_validate(_minimal_snapshot_payload())
    artifact = snapshot.artifacts[0]

    assert snapshot.collection_id is None
    assert snapshot.freshness.snapshot_source == "skillmeat"
    assert snapshot.freshness.source_generated_at == snapshot.generated_at
    assert snapshot.freshness.warnings == []
    assert artifact.collection_ids == []
    assert artifact.deployment_profile_ids == []
    assert artifact.workflow_refs == []
    assert artifact.tags == []


def test_snapshot_rejects_schema_version_mismatch() -> None:
    with pytest.raises(ValidationError):
        SkillMeatArtifactSnapshot.model_validate(
            _minimal_snapshot_payload(schemaVersion="skillmeat-artifact-snapshot-v2")
        )


@pytest.mark.parametrize(
    "mutation",
    [
        {"generatedAt": "2026-05-06T00:00:00"},
        {
            "artifacts": [
                {
                    "definitionType": "skill",
                    "externalId": "skill:frontend-design",
                    "artifactUuid": "artifact-uuid",
                    "displayName": "frontend-design",
                    "versionId": "version-id",
                    "defaultLoadMode": "always",
                    "status": "active",
                }
            ]
        },
        {
            "artifacts": [
                {
                    "definitionType": "skill",
                    "externalId": "skill:frontend-design",
                    "artifactUuid": "artifact-uuid",
                    "displayName": "frontend-design",
                    "versionId": "version-id",
                    "contentHash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "defaultLoadMode": "unsupported",
                    "status": "active",
                }
            ]
        },
    ],
)
def test_snapshot_rejects_invalid_payloads(mutation: dict[str, object]) -> None:
    payload = _minimal_snapshot_payload(**mutation)

    with pytest.raises(ValidationError):
        SkillMeatArtifactSnapshot.model_validate(payload)


def test_rollup_json_schema_validates_sample_and_minimal_payloads() -> None:
    _validate_json_schema(ROLLUP_SCHEMA_PATH, _load_json(ROLLUP_SAMPLE_PATH))
    _validate_json_schema(
        ROLLUP_SCHEMA_PATH,
        {"schemaVersion": CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION},
    )


def test_rollup_pydantic_round_trips_sample_without_data_loss() -> None:
    sample = _load_json(ROLLUP_SAMPLE_PATH)

    rollup = ArtifactUsageRollup.model_validate(sample)
    dumped = rollup.rollup_dict()

    assert dumped == sample
    assert ArtifactUsageRollup.model_validate(dumped).rollup_dict() == dumped


def test_rollup_optional_defaults_are_applied() -> None:
    rollup = ArtifactUsageRollup.model_validate(
        {"schemaVersion": CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION}
    )

    assert rollup.generated_at is None
    assert rollup.project_slug is None
    assert rollup.skillmeat_project_id is None
    assert rollup.artifact is None
    assert rollup.usage is None
    assert rollup.effectiveness is None
    assert rollup.recommendations == []
    assert rollup.rollup_dict() == {
        "schemaVersion": CCDASH_ARTIFACT_USAGE_ROLLUP_SCHEMA_VERSION,
        "recommendations": [],
    }


def test_rollup_rejects_schema_version_mismatch() -> None:
    with pytest.raises(ValidationError):
        ArtifactUsageRollup.model_validate({"schemaVersion": "ccdash-artifact-usage-rollup-v2"})


@pytest.mark.parametrize(
    "mutation",
    [
        {"generatedAt": "2026-05-06T00:05:00"},
        {"usage": {"exclusiveTokens": -1}},
        {"effectiveness": {"successScore": 1.01}},
        {"recommendations": [{"type": "unsupported_recommendation"}]},
    ],
)
def test_rollup_rejects_invalid_payloads(mutation: dict[str, object]) -> None:
    payload = copy.deepcopy(_load_json(ROLLUP_SAMPLE_PATH))
    payload.update(mutation)

    with pytest.raises(ValidationError):
        ArtifactUsageRollup.model_validate(payload)


def test_artifact_outcome_payload_behavior_remains_unchanged() -> None:
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
    assert event["period_end"] == "2026-04-17T00:00:00Z"
    assert event["timestamp"] == "2026-04-17T12:00:00Z"
