import types
import unittest

import aiosqlite

from backend.db.factory import get_agentic_intelligence_repository, get_session_repository
from backend.db.sqlite_migrations import run_migrations
from backend.services.stack_observations import backfill_session_stack_observations


class StackObservationBackfillTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.session_repo = get_session_repository(self.db)
        self.intelligence_repo = get_agentic_intelligence_repository(self.db)
        self.project = types.SimpleNamespace(id="project-1")

        source = await self.intelligence_repo.upsert_definition_source(
            {
                "project_id": "project-1",
                "source_kind": "skillmeat",
                "enabled": True,
                "base_url": "http://skillmeat.local",
                "project_mapping": {"projectId": "sm-project"},
            }
        )
        await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "artifact",
                "external_id": "artifact:build-docs",
                "display_name": "artifact:build-docs",
                "raw_snapshot": {"id": "artifact:build-docs"},
                "fetched_at": "2026-03-07T00:00:00+00:00",
            }
        )
        await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "context_module",
                "external_id": "ctx:planning",
                "display_name": "planning",
                "raw_snapshot": {"name": "planning"},
                "fetched_at": "2026-03-07T00:00:00+00:00",
            }
        )

        await self.session_repo.upsert(
            {
                "id": "session-1",
                "status": "completed",
                "model": "gpt-5",
                "taskId": "feature-1",
                "startedAt": "2026-03-07T00:00:00+00:00",
                "endedAt": "2026-03-07T00:05:00+00:00",
                "createdAt": "2026-03-07T00:00:00+00:00",
                "updatedAt": "2026-03-07T00:05:00+00:00",
                "thinkingLevel": "high",
                "sessionForensics": {
                    "thinking": {"level": "high"},
                    "queuePressure": {"queueOperationCount": 2},
                    "subagentTopology": {"subagentStartCount": 1},
                    "testExecution": {"runCount": 1},
                },
            },
            "project-1",
        )
        await self.session_repo.upsert_logs(
            "session-1",
            [
                {
                    "timestamp": "2026-03-07T00:01:00+00:00",
                    "speaker": "agent",
                    "type": "command",
                    "content": "/dev:execute-phase 1 docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v1.md",
                    "metadata": {
                        "args": "1 docs/project_plans/implementation_plans/enhancements/agentic-sdlc-intelligence-foundation-v1.md",
                        "parsedCommand": {"phases": ["1"], "phaseToken": "1"},
                    },
                },
                {
                    "timestamp": "2026-03-07T00:02:00+00:00",
                    "speaker": "agent",
                    "type": "tool",
                    "content": "",
                    "toolCall": {
                        "name": "Skill",
                        "args": "{\"skill\":\"artifact:build-docs\"}",
                        "status": "success",
                    },
                },
            ],
        )
        await self.session_repo.upsert_artifacts(
            "session-1",
            [
                {
                    "id": "ctx:planning",
                    "title": "Planning Context",
                    "type": "document",
                    "source": "SkillMeat",
                    "url": "http://skillmeat.local/context/planning",
                }
            ],
        )
        await self.session_repo.upsert_file_updates(
            "session-1",
            [{"filePath": "docs/plan.md", "additions": 10, "deletions": 0}],
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_backfill_extracts_and_resolves_components(self) -> None:
        payload = await backfill_session_stack_observations(
            self.db,
            self.project,
            limit=50,
            force_recompute=True,
        )

        observation = await self.intelligence_repo.get_stack_observation("project-1", "session-1")

        self.assertEqual(payload["sessionsProcessed"], 1)
        self.assertIsNotNone(observation)
        components = observation["components"]
        resolved_keys = {component["component_key"] for component in components if component["status"] == "resolved"}
        self.assertIn("artifact:build-docs", resolved_keys)
        self.assertIn("ctx:planning", resolved_keys)


if __name__ == "__main__":
    unittest.main()
