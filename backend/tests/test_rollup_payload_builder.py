import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import aiosqlite

from backend.db.repositories.artifact_ranking_repository import SqliteArtifactRankingRepository
from backend.db.sqlite_migrations import run_migrations
from backend.models import ArtifactRecommendation
from backend.services.rollup_payload_builder import RollupPayloadBuilder


def _ranking_row(artifact_id: str, **overrides):
    row = {
        "project_id": "project-1",
        "collection_id": "collection-a",
        "user_scope": "all",
        "artifact_type": "skill",
        "artifact_id": artifact_id,
        "artifact_uuid": f"uuid-{artifact_id}",
        "version_id": "v1",
        "workflow_id": "",
        "period": "30d",
        "exclusive_tokens": 100,
        "supporting_tokens": 40,
        "cost_usd": 0.25,
        "session_count": 4,
        "workflow_count": 2,
        "last_observed_at": "2026-05-07T10:00:00Z",
        "avg_confidence": 0.8,
        "confidence": 0.8,
        "success_score": 0.75,
        "efficiency_score": 0.7,
        "quality_score": 0.8,
        "risk_score": 0.2,
        "context_pressure": 0.4,
        "sample_size": 4,
        "identity_confidence": 0.9,
        "snapshot_fetched_at": "2026-05-07T09:00:00Z",
        "recommendation_types": ["optimization_target"],
        "evidence": {
            "projectSessionCount": 8,
            "snapshot": {
                "contentHash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            },
        },
        "computed_at": "2026-05-07T10:05:00Z",
    }
    row.update(overrides)
    return row


class RollupPayloadBuilderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteArtifactRankingRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_builds_schema_v1_rollups_from_ranking_rows_with_recommendations(self) -> None:
        await self.repo.upsert_rankings(
            [
                _ranking_row("frontend-design", session_count=4),
                _ranking_row(
                    "frontend-design",
                    workflow_id="workflow-a",
                    exclusive_tokens=20,
                    session_count=2,
                ),
            ]
        )

        class _RecommendationService:
            def generate_recommendations(self, rows, *, now=None, **_kwargs):  # noqa: ANN001
                return [
                    ArtifactRecommendation(
                        type="optimization_target",
                        confidence=0.8,
                        rationaleCode="high_usage_low_efficiency",
                        nextAction="Review artifact optimization.",
                        affectedArtifactIds=["uuid-frontend-design"],
                        scope="project",
                        projectId="project-1",
                        period="30d",
                    )
                ]

        rollups = await RollupPayloadBuilder(recommendation_service=_RecommendationService()).build_rollups(
            self.db,
            project_id="project-1",
            skillmeat_project_id="sm-project",
            period="30d",
            generated_at=datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            hosted=False,
        )

        self.assertEqual(len(rollups), 1)
        payload = rollups[0].rollup_dict()
        self.assertEqual(payload["schemaVersion"], "ccdash-artifact-usage-rollup-v1")
        self.assertEqual(payload["projectSlug"], "project-1")
        self.assertEqual(payload["skillmeatProjectId"], "sm-project")
        self.assertEqual(payload["userScope"], "local-user")
        self.assertEqual(payload["usage"]["exclusiveTokens"], 100)
        self.assertEqual(payload["usage"]["attributedTokens"], 140)
        self.assertEqual(payload["artifact"]["contentHash"], "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.assertTrue(payload["recommendations"])

    async def test_local_user_scope_can_be_omitted_by_config(self) -> None:
        await self.repo.upsert_rankings([_ranking_row("artifact-a")])

        with patch("backend.services.rollup_payload_builder.config.CCDASH_LOCAL_USER_ROLLUP_SCOPE_MODE", "omit"):
            rollups = await RollupPayloadBuilder().build_rollups(
                self.db,
                project_id="project-1",
                period="30d",
                hosted=False,
            )

        self.assertIsNone(rollups[0].user_scope)

    async def test_hosted_scope_preserves_persisted_principal_scope(self) -> None:
        await self.repo.upsert_rankings([_ranking_row("artifact-a", user_scope="principal:abc123")])

        rollups = await RollupPayloadBuilder().build_rollups(
            self.db,
            project_id="project-1",
            period="30d",
            hosted=True,
        )

        self.assertEqual(rollups[0].user_scope, "principal:abc123")


if __name__ == "__main__":
    unittest.main()
