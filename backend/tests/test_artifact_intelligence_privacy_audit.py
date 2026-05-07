from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from backend.models import ArtifactUsageRollup
from backend.services.integrations.skillmeat_client import SkillMeatClient, SkillMeatClientError
from backend.services.integrations.telemetry_exporter import TelemetryExportCoordinator
from backend.services.rollup_payload_builder import RollupPayloadBuilder


PROHIBITED_FIELDS = {
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
}

RECOMMENDATION_KEYS = {
    "type",
    "confidence",
    "rationaleCode",
    "nextAction",
    "evidence",
    "affectedArtifactIds",
    "scope",
}


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
                "versionId": "v1",
                "contentHash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            },
            "usage": {
                "exclusiveTokens": 10,
                "supportingTokens": 5,
                "attributedTokens": 15,
                "sessionCount": 1,
                "workflowCount": 1,
            },
            "effectiveness": {"successScore": 1.0, "sampleSize": 1},
            "recommendations": [
                {
                    "type": "optimization_target",
                    "confidence": 0.8,
                    "rationaleCode": "high_usage",
                    "nextAction": "Prioritize this artifact for an optimization pass.",
                    "evidence": ["sampleSize=1", "exclusiveTokens=10"],
                    "affectedArtifactIds": ["uuid-1"],
                    "scope": "project",
                }
            ],
        }
    )


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_walk_keys(item))
    return keys


class _Builder:
    async def build_rollups(self, *_args: Any, **_kwargs: Any) -> list[ArtifactUsageRollup]:
        return [_clean_rollup()]


class _Client:
    async def post_artifact_usage_rollup(self, rollup: ArtifactUsageRollup) -> dict[str, bool]:
        assert rollup.user_scope == "local-user"
        return {"accepted": True}


def test_artifact_usage_rollup_payload_shape_excludes_prohibited_fields() -> None:
    payload = _clean_rollup().rollup_dict()

    assert _walk_keys(payload).isdisjoint(PROHIBITED_FIELDS)
    assert payload["recommendations"]
    assert set(payload["recommendations"][0]) == RECOMMENDATION_KEYS


def test_local_user_scope_uses_pseudonym_or_omits_in_local_mode() -> None:
    builder = RollupPayloadBuilder()

    with patch("backend.services.rollup_payload_builder.config.CCDASH_LOCAL_USER_ROLLUP_SCOPE_MODE", "pseudonym"):
        with patch("backend.services.rollup_payload_builder.config.CCDASH_LOCAL_USER_SCOPE_PSEUDONYM", "local-audit-user"):
            assert builder._user_scope("all", hosted=False) == "local-audit-user"

    with patch("backend.services.rollup_payload_builder.config.CCDASH_LOCAL_USER_ROLLUP_SCOPE_MODE", "omit"):
        assert builder._user_scope("all", hosted=False) is None

    assert builder._user_scope("all", hosted=True) is None
    assert builder._user_scope("principal:abc123", hosted=True) == "principal:abc123"


def test_snapshot_fetch_logs_omit_auth_headers_and_tokens(caplog: pytest.LogCaptureFixture) -> None:
    client = SkillMeatClient(
        base_url="http://skillmeat.local",
        timeout_seconds=2.0,
        aaa_enabled=True,
        api_key="sk-secret-audit-token",
    )

    with (
        patch(
            "backend.services.integrations.skillmeat_client.agentic_intelligence_flags.artifact_intelligence_enabled",
            return_value=True,
        ),
        patch.object(
            SkillMeatClient,
            "_request_json",
            side_effect=SkillMeatClientError("missing", status_code=404, detail="Project not found"),
        ) as request_mock,
        caplog.at_level("INFO", logger="ccdash.skillmeat_client"),
    ):
        snapshot = asyncio.run(client.fetch_project_artifact_snapshot("sm-project", "default"))

    assert snapshot is None
    request_mock.assert_called_once_with(
        "/api/v1/projects/sm-project/artifact-snapshot",
        {"collection_id": "default"},
    )
    log_text = caplog.text
    assert "sk-secret-audit-token" not in log_text
    assert "Authorization" not in log_text
    assert "Bearer" not in log_text


def test_rollup_export_logs_omit_payloads_and_credentials(caplog: pytest.LogCaptureFixture) -> None:
    coordinator = TelemetryExportCoordinator(
        repository=SimpleNamespace(),
        settings_store=SimpleNamespace(),
        runtime_config=SimpleNamespace(),
        db=SimpleNamespace(),
        rollup_payload_builder=_Builder(),
    )

    with (
        patch("backend.services.integrations.telemetry_exporter.config.CCDASH_ARTIFACT_INTELLIGENCE_ENABLED", True),
        caplog.at_level("INFO", logger="ccdash.telemetry.exporter"),
    ):
        outcome = asyncio.run(
            coordinator.export_artifact_usage_rollups(
                project_id="project-1",
                period="30d",
                skillmeat_client=_Client(),
                skillmeat_project_id="sm-project",
                collection_id="default",
            )
        )

    assert outcome.success is True
    assert outcome.success_count == 1
    assert "Artifact usage rollup export complete" in caplog.text
    assert "skill:frontend-design" not in caplog.text
    assert "sha256:" not in caplog.text
    for field_name in PROHIBITED_FIELDS:
        assert field_name not in caplog.text
    for record in caplog.records:
        assert "payload" not in record.__dict__
        assert "rollup" not in record.__dict__
        assert "api_key" not in record.__dict__
