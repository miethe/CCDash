import pytest

from backend.models import ArtifactUsageRollup
from backend.services.telemetry_transformer import AnonymizationVerifier, PrivacyViolationError


def _clean_rollup() -> ArtifactUsageRollup:
    return ArtifactUsageRollup.model_validate(
        {
            "schemaVersion": "ccdash-artifact-usage-rollup-v1",
            "projectSlug": "project-1",
            "skillmeatProjectId": "sm-project",
            "collectionId": "default",
            "userScope": "local-user",
            "period": "30d",
            "artifact": {
                "definitionType": "skill",
                "externalId": "skill:frontend-design",
                "artifactUuid": "uuid-1",
            },
            "usage": {"exclusiveTokens": 10, "supportingTokens": 5, "sessionCount": 1},
            "effectiveness": {"successScore": 1.0, "sampleSize": 1},
            "recommendations": [
                {
                    "type": "optimization_target",
                    "rationaleCode": "high_usage",
                    "nextAction": "Review optimization target.",
                    "evidence": ["sampleSize=1"],
                    "affectedArtifactIds": ["uuid-1"],
                    "scope": "project",
                }
            ],
        }
    )


def test_clean_rollup_passes_allowlist_verification() -> None:
    assert AnonymizationVerifier.verify_rollup_payload(_clean_rollup()) is True


@pytest.mark.parametrize(
    "field_name",
    ["rawPrompt", "transcriptText", "code", "absolutePath", "unhashedUsername"],
)
def test_prohibited_mock_fields_raise_privacy_violation(field_name: str) -> None:
    payload = _clean_rollup().rollup_dict()
    payload[field_name] = "blocked"

    with pytest.raises(PrivacyViolationError):
        AnonymizationVerifier.verify_rollup_payload(payload)


def test_absolute_paths_in_allowed_fields_raise_privacy_violation() -> None:
    payload = _clean_rollup().rollup_dict()
    payload["recommendations"][0]["nextAction"] = "/Users/miethe/private/raw-session.jsonl"

    with pytest.raises(PrivacyViolationError):
        AnonymizationVerifier.verify_rollup_payload(payload)
