import pytest

from backend.models import ArtifactUsageRollup
from backend.services.telemetry_transformer import AnonymizationVerifier, PrivacyViolationError

PROHIBITED_FIELDS = [
    "raw_prompt",
    "prompt_text",
    "transcript_text",
    "message_content",
    "source_code",
    "code_snippet",
    "absolute_path",
    "file_path",
    "unhashed_username",
    "user_email",
    "api_key",
    "token",
    "secret",
]

PROHIBITED_FIELD_ALIASES = [
    "rawPrompt",
    "promptText",
    "transcriptText",
    "messageContent",
    "sourceCode",
    "codeSnippet",
    "absolutePath",
    "filePath",
    "unhashedUsername",
    "userEmail",
    "apiKey",
]


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
    PROHIBITED_FIELDS + PROHIBITED_FIELD_ALIASES,
)
def test_prohibited_mock_fields_raise_privacy_violation(field_name: str) -> None:
    payload = _clean_rollup().rollup_dict()
    payload[field_name] = "blocked"

    with pytest.raises(PrivacyViolationError):
        AnonymizationVerifier.verify_rollup_payload(payload)


@pytest.mark.parametrize(
    "field_path,value",
    [
        (("recommendations", 0, "nextAction"), "/Users/miethe/private/raw-session.jsonl"),
        (("recommendations", 0, "nextAction"), "C:\\Users\\miethe\\private\\raw-session.jsonl"),
        (("recommendations", 0, "nextAction"), "operator@example.com"),
        (("recommendations", 0, "nextAction"), "```python\ndef leak():\n    return secret\n```"),
    ],
)
def test_sensitive_values_in_allowed_fields_raise_privacy_violation(
    field_path: tuple[str, int, str],
    value: str,
) -> None:
    payload = _clean_rollup().rollup_dict()
    target = payload
    for segment in field_path[:-1]:
        target = target[segment]
    target[field_path[-1]] = value

    with pytest.raises(PrivacyViolationError):
        AnonymizationVerifier.verify_rollup_payload(payload)
