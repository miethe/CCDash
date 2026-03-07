import unittest

import aiosqlite

from backend.db.factory import get_agentic_intelligence_repository, get_session_repository
from backend.db.sqlite_migrations import run_migrations


class IntelligenceRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.repo = get_agentic_intelligence_repository(self.db)
        self.session_repo = get_session_repository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_definition_source_and_cache_round_trip(self) -> None:
        source = await self.repo.upsert_definition_source(
            {
                "project_id": "project-1",
                "source_kind": "skillmeat",
                "enabled": True,
                "base_url": "http://skillmeat.local",
                "project_mapping": {"projectId": "sm-project", "workspaceId": "default"},
            }
        )
        definition = await self.repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "artifact",
                "external_id": "artifact:build-docs",
                "display_name": "build-docs",
                "version": "v1",
                "raw_snapshot": {"id": "artifact:build-docs"},
                "resolution_metadata": {"normalizedFrom": ["id"]},
                "fetched_at": "2026-03-07T00:00:00+00:00",
            }
        )

        cached = await self.repo.get_external_definition("project-1", "artifact", "artifact:build-docs")

        self.assertTrue(source["enabled"])
        self.assertEqual(definition["display_name"], "build-docs")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["raw_snapshot_json"]["id"], "artifact:build-docs")

    async def test_stack_observation_replaces_components(self) -> None:
        await self.session_repo.upsert(
            {
                "id": "session-1",
                "status": "completed",
                "model": "gpt-5",
                "createdAt": "2026-03-07T00:00:00+00:00",
                "updatedAt": "2026-03-07T00:00:00+00:00",
            },
            "project-1",
        )
        observation = await self.repo.upsert_stack_observation(
            {
                "project_id": "project-1",
                "session_id": "session-1",
                "feature_id": "feature-1",
                "workflow_ref": "phase-execution",
                "confidence": 0.8,
                "evidence": {"commands": ["/dev:execute-phase 1"]},
            },
            components=[
                {
                    "project_id": "project-1",
                    "component_type": "command",
                    "component_key": "/dev:execute-phase 1",
                    "status": "explicit",
                    "confidence": 0.75,
                    "payload": {"command": "/dev:execute-phase 1"},
                }
            ],
        )
        updated = await self.repo.upsert_stack_observation(
            {
                "project_id": "project-1",
                "session_id": "session-1",
                "feature_id": "feature-1",
                "workflow_ref": "phase-execution",
                "confidence": 0.9,
                "evidence": {"commands": ["/dev:execute-phase 2"]},
            },
            components=[
                {
                    "project_id": "project-1",
                    "component_type": "workflow",
                    "component_key": "phase-execution",
                    "status": "inferred",
                    "confidence": 0.7,
                    "payload": {"workflowRef": "phase-execution"},
                }
            ],
        )

        self.assertEqual(observation["session_id"], "session-1")
        self.assertEqual(len(updated["components"]), 1)
        self.assertEqual(updated["components"][0]["component_type"], "workflow")

    async def test_effectiveness_rollup_round_trip(self) -> None:
        stored = await self.repo.upsert_effectiveness_rollup(
            {
                "project_id": "project-1",
                "scope_type": "workflow",
                "scope_id": "phase-execution",
                "period": "all",
                "metrics": {
                    "scopeLabel": "phase-execution",
                    "sampleSize": 2,
                    "successScore": 0.75,
                    "efficiencyScore": 0.61,
                    "qualityScore": 0.8,
                    "riskScore": 0.22,
                    "generatedAt": "2026-03-07T00:00:00+00:00",
                },
                "evidence_summary": {
                    "featureIds": ["feature-1"],
                    "representativeSessionIds": ["session-1"],
                },
            }
        )

        rows = await self.repo.list_effectiveness_rollups(
            "project-1",
            scope_type="workflow",
            period="all",
        )

        self.assertEqual(stored["scope_id"], "phase-execution")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["metrics_json"]["sampleSize"], 2)
        self.assertEqual(rows[0]["evidence_summary_json"]["featureIds"], ["feature-1"])


if __name__ == "__main__":
    unittest.main()
