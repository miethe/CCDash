import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.models import (
    SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION,
    SkillMeatArtifactSnapshot,
)


SCHEMA_PATH = Path("docs/schemas/integrations/skillmeat-artifact-snapshot-v1.schema.json")
SAMPLE_PATH = Path("docs/schemas/integrations/skillmeat-artifact-snapshot-v1.sample.json")


def _sample_payload(**overrides):
    payload = {
        "schemaVersion": SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION,
        "generatedAt": "2026-05-06T00:00:00Z",
        "projectId": "skillmeat-project-id",
        "collectionId": "collection-id",
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


def test_schema_and_sample_files_parse_and_match_version() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    sample = json.loads(SAMPLE_PATH.read_text())

    assert schema["properties"]["schemaVersion"]["const"] == SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION
    assert sample["schemaVersion"] == SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION
    assert SkillMeatArtifactSnapshot.model_validate(sample).schema_version == SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION


def test_snapshot_round_trips_by_wire_aliases_without_data_loss() -> None:
    payload = _sample_payload()

    snapshot = SkillMeatArtifactSnapshot.model_validate(payload)
    dumped = snapshot.snapshot_dict()

    assert dumped["schemaVersion"] == payload["schemaVersion"]
    assert dumped["generatedAt"] == payload["generatedAt"]
    assert dumped["projectId"] == payload["projectId"]
    assert dumped["collectionId"] == payload["collectionId"]
    assert dumped["artifacts"][0]["externalId"] == payload["artifacts"][0]["externalId"]
    assert dumped["artifacts"][0]["defaultLoadMode"] == payload["artifacts"][0]["defaultLoadMode"]
    assert dumped["freshness"]["snapshotSource"] == "skillmeat"
    assert dumped["freshness"]["sourceGeneratedAt"] == payload["generatedAt"]


def test_snapshot_accepts_snake_case_internal_keys_and_dumps_external_aliases() -> None:
    snapshot = SkillMeatArtifactSnapshot.model_validate(
        {
            "schema_version": SKILLMEAT_ARTIFACT_SNAPSHOT_SCHEMA_VERSION,
            "generated_at": "2026-05-06T00:00:00Z",
            "project_id": "skillmeat-project-id",
            "artifacts": [
                {
                    "definition_type": "skill",
                    "external_id": "skill:frontend-design",
                    "artifact_uuid": "artifact-uuid",
                    "display_name": "frontend-design",
                    "version_id": "version-id",
                    "content_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "default_load_mode": "workflow_scoped",
                    "status": "active",
                }
            ],
        }
    )

    dumped = snapshot.snapshot_dict()

    assert "schemaVersion" in dumped
    assert "generatedAt" in dumped
    assert dumped["artifacts"][0]["definitionType"] == "skill"
    assert dumped["artifacts"][0]["defaultLoadMode"] == "workflow_scoped"


def test_snapshot_rejects_wrong_schema_version() -> None:
    with pytest.raises(ValidationError):
        SkillMeatArtifactSnapshot.model_validate(_sample_payload(schemaVersion="wrong-version"))


def test_snapshot_enforces_required_artifact_fields() -> None:
    payload = _sample_payload(
        artifacts=[
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
    )

    with pytest.raises(ValidationError):
        SkillMeatArtifactSnapshot.model_validate(payload)


def test_snapshot_optional_artifact_lists_default_to_empty() -> None:
    artifact = SkillMeatArtifactSnapshot.model_validate(_sample_payload()).artifacts[0]

    assert artifact.collection_ids == []
    assert artifact.deployment_profile_ids == []
    assert artifact.workflow_refs == []
    assert artifact.tags == []
