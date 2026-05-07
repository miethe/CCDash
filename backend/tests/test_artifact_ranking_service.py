import json
import unittest
from datetime import datetime, timedelta, timezone

import aiosqlite

from backend.db.sqlite_migrations import run_migrations
from backend.models import SkillMeatArtifactSnapshot
from backend.services.artifact_ranking_service import ArtifactRankingService


NOW = datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc)


def _snapshot_payload() -> dict:
    return {
        "schemaVersion": "skillmeat-artifact-snapshot-v1",
        "generatedAt": "2026-05-07T11:50:00Z",
        "projectId": "project-1",
        "collectionId": "collection-a",
        "freshness": {
            "snapshotSource": "skillmeat",
            "sourceGeneratedAt": "2026-05-07T11:50:00Z",
            "fetchedAt": "2026-05-07T11:55:00Z",
        },
        "artifacts": [
            {
                "definitionType": "skill",
                "externalId": "skill:hot-skill",
                "artifactUuid": "uuid-hot",
                "displayName": "Hot Skill",
                "versionId": "v2",
                "contentHash": "hash-hot",
                "collectionIds": ["collection-a"],
                "deploymentProfileIds": ["default"],
                "defaultLoadMode": "always",
                "workflowRefs": ["workflow-a"],
                "tags": [],
                "status": "active",
            },
            {
                "definitionType": "skill",
                "externalId": "skill:unused-skill",
                "artifactUuid": "uuid-unused",
                "displayName": "Unused Skill",
                "versionId": "v1",
                "contentHash": "hash-unused",
                "collectionIds": ["collection-a"],
                "deploymentProfileIds": ["default"],
                "defaultLoadMode": "always",
                "workflowRefs": [],
                "tags": [],
                "status": "active",
            },
        ],
    }


class ArtifactRankingServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _insert_usage(self, artifact_id: str, index: int, *, workflow: str = "workflow-a") -> None:
        session_id = f"S-{index}"
        captured_at = (NOW - timedelta(minutes=index)).isoformat().replace("+00:00", "Z")
        await self.db.execute(
            """
            INSERT INTO sessions (
                id, project_id, status, current_context_tokens, context_window_size,
                created_at, updated_at, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                "project-1",
                "completed",
                160000,
                200000,
                captured_at,
                captured_at,
                f"{session_id}.jsonl",
            ),
        )
        await self.db.execute(
            """
            INSERT INTO session_stack_observations (project_id, session_id, workflow_ref, confidence)
            VALUES (?, ?, ?, ?)
            """,
            ("project-1", session_id, workflow, 0.9),
        )
        event_id = f"E-{index}"
        await self.db.execute(
            """
            INSERT INTO session_usage_events (
                id, project_id, session_id, root_session_id, captured_at, event_kind,
                token_family, delta_tokens, cost_usd_model_io
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                "project-1",
                session_id,
                session_id,
                captured_at,
                "model_io",
                "input",
                40000,
                0.45,
            ),
        )
        await self.db.execute(
            """
            INSERT INTO session_usage_attributions (
                event_id, entity_type, entity_id, attribution_role, method, confidence
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, "skill", artifact_id, "primary", "test", 0.85),
        )

    async def test_compute_rankings_persists_snapshot_covered_rows_and_recommendation_types(self) -> None:
        from backend.db.factory import get_artifact_ranking_repository, get_artifact_snapshot_repository

        snapshot_repo = get_artifact_snapshot_repository(self.db)
        await snapshot_repo.save_snapshot(SkillMeatArtifactSnapshot.model_validate(_snapshot_payload()))
        for index in range(1, 7):
            await self._insert_usage("hot-skill", index)
        await self.db.execute(
            """
            INSERT INTO effectiveness_rollups (project_id, scope_type, scope_id, period, metrics_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "project-1",
                "artifact",
                "hot-skill",
                "30d",
                json.dumps({"successScore": 0.75, "efficiencyScore": 0.25, "qualityScore": 0.7, "riskScore": 0.7}),
            ),
        )
        await self.db.commit()

        rows = await ArtifactRankingService(min_sample_size=3).compute_rankings(
            self.db,
            project_id="project-1",
            period="30d",
            computed_at=NOW,
        )

        by_artifact = {row["artifact_id"]: row for row in rows if not row["workflow_id"]}
        self.assertIn("hot-skill", by_artifact)
        self.assertIn("unused-skill", by_artifact)
        self.assertEqual(by_artifact["hot-skill"]["artifact_uuid"], "uuid-hot")
        self.assertEqual(by_artifact["hot-skill"]["sample_size"], 6)
        self.assertEqual(by_artifact["hot-skill"]["context_pressure"], 0.8)
        self.assertIn("optimization_target", by_artifact["hot-skill"]["recommendation_types_json"])
        self.assertIn("load_on_demand", by_artifact["hot-skill"]["recommendation_types_json"])
        self.assertEqual(by_artifact["unused-skill"]["sample_size"], 0)
        self.assertIn("disable_candidate", by_artifact["unused-skill"]["recommendation_types_json"])

        stored = await get_artifact_ranking_repository(self.db).list_rankings(
            project_id="project-1",
            period="30d",
            recommendation_type="disable_candidate",
        )
        self.assertEqual(stored["total"], 1)
        self.assertEqual(stored["rows"][0]["artifact_id"], "unused-skill")
