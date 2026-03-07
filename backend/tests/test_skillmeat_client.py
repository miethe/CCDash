import unittest
from unittest.mock import patch

from backend.services.integrations.skillmeat_client import SkillMeatClient


class SkillMeatClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_definitions_normalizes_payloads(self) -> None:
        client = SkillMeatClient(base_url="http://skillmeat.local", timeout_seconds=2.0)

        with patch.object(
            SkillMeatClient,
            "_request_json",
            return_value={
                "artifacts": [
                    {"type": "artifact", "name": "build-docs", "version": "2026.03.07", "url": "http://skillmeat.local/a/build-docs"},
                    {"id": "artifact:test-runner", "title": "Test Runner"},
                ]
            },
        ) as request_mock:
            items = await client.fetch_definitions(
                definition_type="artifact",
                project_id="sm-project",
                workspace_id="default",
            )

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["external_id"], "artifact:build-docs")
        self.assertEqual(items[0]["display_name"], "build-docs")
        self.assertEqual(items[1]["external_id"], "artifact:test-runner")
        request_mock.assert_called_once()
        self.assertEqual(request_mock.call_args.args[0], "/api/artifacts")
        self.assertEqual(
            request_mock.call_args.args[1],
            {"project_id": "sm-project", "workspace_id": "default"},
        )

    async def test_context_modules_prefix_ctx_when_missing(self) -> None:
        client = SkillMeatClient(base_url="http://skillmeat.local", timeout_seconds=2.0)

        with patch.object(
            SkillMeatClient,
            "_request_json",
            return_value={"contextModules": [{"name": "planning", "version": "1"}]},
        ):
            items = await client.fetch_definitions(definition_type="context_module")

        self.assertEqual(items[0]["external_id"], "ctx:planning")


if __name__ == "__main__":
    unittest.main()
