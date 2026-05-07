import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from backend.models import ArtifactOutcomePayload, ArtifactUsageRollup
from backend.services.integrations.skillmeat_client import SkillMeatClient


def _rollup() -> ArtifactUsageRollup:
    return ArtifactUsageRollup.model_validate(
        {
            "schemaVersion": "ccdash-artifact-usage-rollup-v1",
            "generatedAt": "2026-05-07T12:00:00Z",
            "projectSlug": "project-1",
            "skillmeatProjectId": "sm-project",
            "collectionId": "default",
            "period": "30d",
            "artifact": {"definitionType": "skill", "externalId": "skill:frontend-design"},
            "usage": {"exclusiveTokens": 10, "supportingTokens": 5, "sessionCount": 1},
        }
    )


def _artifact_outcome() -> ArtifactOutcomePayload:
    return ArtifactOutcomePayload(
        event_id="5b56afba-9ccb-4d2b-b334-f921d4460209",
        definition_type="skill",
        external_id="skill:frontend-design",
        period_label="30d",
        period_start=datetime(2026, 4, 7, tzinfo=timezone.utc),
        period_end=datetime(2026, 5, 7, tzinfo=timezone.utc),
        execution_count=1,
        success_count=1,
        failure_count=0,
        token_input=10,
        token_output=5,
        cost_usd=0.01,
        duration_ms=1000,
        timestamp=datetime(2026, 5, 7, tzinfo=timezone.utc),
    )


class SkillMeatRollupIngestionContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_client_posts_rollup_to_additive_analytics_endpoint(self) -> None:
        client = SkillMeatClient(base_url="http://skillmeat.local", timeout_seconds=2.0)
        rollup = _rollup()

        with patch.object(SkillMeatClient, "_request_json", return_value={"accepted": True}) as request_mock:
            response = await client.post_artifact_usage_rollup(rollup)

        self.assertEqual(response, {"accepted": True})
        request_mock.assert_called_once_with(
            "/api/v1/analytics/artifact-usage-rollups",
            None,
            method="POST",
            body=rollup.rollup_dict(),
        )

    async def test_rollup_contract_does_not_overlap_existing_artifact_outcome_shape(self) -> None:
        rollup_payload = _rollup().rollup_dict()
        outcome_payload = _artifact_outcome().event_dict()

        self.assertEqual(rollup_payload["schemaVersion"], "ccdash-artifact-usage-rollup-v1")
        self.assertIn("usage", rollup_payload)
        self.assertNotIn("schemaVersion", outcome_payload)
        self.assertIn("definition_type", outcome_payload)
        self.assertIn("external_id", outcome_payload)


if __name__ == "__main__":
    unittest.main()
