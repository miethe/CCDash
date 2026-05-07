import unittest

import aiosqlite

from backend.db.repositories.artifact_ranking_repository import SqliteArtifactRankingRepository
from backend.db.sqlite_migrations import run_migrations


def _ranking_row(artifact_id: str, **overrides):
    row = {
        "project_id": "project-1",
        "collection_id": "collection-a",
        "user_scope": "user-a",
        "artifact_type": "skill",
        "artifact_id": artifact_id,
        "artifact_uuid": f"uuid-{artifact_id}",
        "version_id": "v1",
        "workflow_id": "workflow-a",
        "period": "30d",
        "exclusive_tokens": 100,
        "supporting_tokens": 10,
        "cost_usd": 0.25,
        "session_count": 4,
        "workflow_count": 1,
        "last_observed_at": "2026-05-07T10:00:00Z",
        "avg_confidence": 0.8,
        "confidence": 0.8,
        "success_score": 0.8,
        "efficiency_score": 0.7,
        "quality_score": 0.8,
        "risk_score": 0.2,
        "context_pressure": 0.4,
        "sample_size": 4,
        "identity_confidence": 0.9,
        "snapshot_fetched_at": "2026-05-07T09:00:00Z",
        "recommendation_types": ["optimization_target"],
        "evidence": {"projectSessionCount": 8},
        "computed_at": "2026-05-07T10:05:00Z",
    }
    row.update(overrides)
    return row


class ArtifactRankingRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = SqliteArtifactRankingRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_upsert_and_filter_rankings_by_all_phase_dimensions(self) -> None:
        await self.repo.upsert_rankings(
            [
                _ranking_row("artifact-a"),
                _ranking_row(
                    "artifact-b",
                    collection_id="collection-b",
                    user_scope="user-b",
                    artifact_type="agent",
                    artifact_uuid="uuid-b",
                    version_id="v2",
                    workflow_id="workflow-b",
                    recommendation_types=["load_on_demand"],
                ),
            ]
        )

        payload = await self.repo.list_rankings(
            project_id="project-1",
            period="30d",
            collection_id="collection-b",
            user_scope="user-b",
            artifact_uuid="uuid-b",
            version_id="v2",
            workflow_id="workflow-b",
            artifact_type="agent",
            recommendation_type="load_on_demand",
        )

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["rows"][0]["artifact_id"], "artifact-b")
        self.assertEqual(payload["rows"][0]["recommendation_types"], ["load_on_demand"])
        self.assertEqual(payload["rows"][0]["evidence"], {"projectSessionCount": 8})

    async def test_cursor_pagination_returns_next_cursor(self) -> None:
        await self.repo.upsert_rankings(
            [
                _ranking_row("artifact-a", exclusive_tokens=300),
                _ranking_row("artifact-b", exclusive_tokens=200),
                _ranking_row("artifact-c", exclusive_tokens=100),
            ]
        )

        first = await self.repo.list_rankings(project_id="project-1", period="30d", limit=2)
        second = await self.repo.list_rankings(
            project_id="project-1",
            period="30d",
            limit=2,
            cursor=first["next_cursor"],
        )

        self.assertEqual([row["artifact_id"] for row in first["rows"]], ["artifact-a", "artifact-b"])
        self.assertEqual([row["artifact_id"] for row in second["rows"]], ["artifact-c"])
        self.assertIsNone(second["next_cursor"])
