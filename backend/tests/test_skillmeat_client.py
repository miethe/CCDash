import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from backend.services.integrations.skillmeat_client import SkillMeatClient, SkillMeatClientError


class SkillMeatClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_artifact_definitions_uses_v1_and_collection_scope(self) -> None:
        client = SkillMeatClient(base_url="http://skillmeat.local", timeout_seconds=2.0)

        with patch.object(
            SkillMeatClient,
            "_request_json",
            return_value={
                "items": [
                    {"type": "artifact", "name": "build-docs", "version": "2026.03.07", "url": "http://skillmeat.local/a/build-docs"},
                    {"id": "artifact:test-runner", "title": "Test Runner"},
                ],
                "page_info": {"has_next_page": False, "end_cursor": None},
            },
        ) as request_mock:
            items = await client.fetch_definitions(
                definition_type="artifact",
                project_id="sm-project",
                collection_id="default",
            )

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["external_id"], "artifact:build-docs")
        self.assertEqual(items[0]["display_name"], "build-docs")
        self.assertEqual(items[1]["external_id"], "artifact:test-runner")
        request_mock.assert_called_once()
        self.assertEqual(request_mock.call_args.args[0], "/api/v1/artifacts")
        self.assertEqual(
            request_mock.call_args.args[1],
            {"limit": 200, "collection": "default"},
        )

    async def test_context_modules_preserve_module_id_and_alias_ctx_name(self) -> None:
        client = SkillMeatClient(base_url="http://skillmeat.local", timeout_seconds=2.0)

        with patch.object(
            SkillMeatClient,
            "_request_json",
            return_value={
                "items": [{"id": "cm_123", "name": "Planning", "project_id": "/tmp/project"}],
                "next_cursor": None,
                "has_more": False,
            },
        ):
            items = await client.fetch_definitions(definition_type="context_module", project_id="/tmp/project")

        self.assertEqual(items[0]["external_id"], "cm_123")
        self.assertIn("ctx:planning", items[0]["resolution_metadata"]["aliases"])

    async def test_preview_context_pack_posts_project_scoped_request(self) -> None:
        client = SkillMeatClient(base_url="http://skillmeat.local", timeout_seconds=2.0)

        with patch.object(
            SkillMeatClient,
            "_request_json",
            return_value={"items": [], "budget_tokens": 4000, "total_estimated_tokens": 0, "total_items": 0},
        ) as request_mock:
            payload = await client.preview_context_pack(
                project_id="/tmp/project",
                module_id="cm_123",
                budget_tokens=4096,
            )

        self.assertEqual(payload["budget_tokens"], 4000)
        request_mock.assert_called_once_with(
            "/api/v1/context-packs/preview",
            {"project_id": "/tmp/project"},
            method="POST",
            body={"module_id": "cm_123", "budget_tokens": 4096, "filters": None},
        )

    async def test_request_json_sends_bearer_token_when_aaa_enabled(self) -> None:
        client = SkillMeatClient(
            base_url="http://skillmeat.local",
            timeout_seconds=2.0,
            aaa_enabled=True,
            api_key="secret-token",
        )
        captured_request = None

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"items":[],"page_info":{"has_next_page":false,"end_cursor":null}}'

        def fake_urlopen(req, timeout=0):
            nonlocal captured_request
            captured_request = req
            return _Response()

        with patch("backend.services.integrations.skillmeat_client.request.urlopen", side_effect=fake_urlopen):
            payload = client._request_json("/api/v1/artifacts", {"limit": 1})

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.headers.get("Authorization"), "Bearer secret-token")
        self.assertIsInstance(payload, dict)

    async def test_request_json_surfaces_error_envelope_detail(self) -> None:
        client = SkillMeatClient(base_url="http://skillmeat.local", timeout_seconds=2.0)
        http_error = HTTPError(
            url="http://skillmeat.local/api/v1/projects",
            code=401,
            msg="Unauthorized",
            hdrs=MagicMock(),
            fp=BytesIO(b'{"detail":"Bearer token required","status_code":401}'),
        )

        with patch("backend.services.integrations.skillmeat_client.request.urlopen", side_effect=http_error):
            with self.assertRaises(SkillMeatClientError) as ctx:
                client._request_json("/api/v1/projects", {"limit": 1})

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Bearer token required")

    async def test_create_context_module_posts_expected_payload(self) -> None:
        client = SkillMeatClient(base_url="http://skillmeat.local", timeout_seconds=2.0)

        with patch.object(
            SkillMeatClient,
            "_request_json",
            return_value={"id": "cm_1", "name": "Workflow memory"},
        ) as request_mock:
            payload = await client.create_context_module(
                project_id="sm-project",
                name="Workflow memory",
                description="Derived from CCDash sessions.",
            )

        self.assertEqual(payload["id"], "cm_1")
        request_mock.assert_called_once_with(
            "/api/v1/context-modules",
            None,
            method="POST",
            body={
                "project_id": "sm-project",
                "name": "Workflow memory",
                "description": "Derived from CCDash sessions.",
                "selectors": {},
                "priority": 5,
            },
        )

    async def test_add_context_module_memory_posts_expected_payload(self) -> None:
        client = SkillMeatClient(base_url="http://skillmeat.local", timeout_seconds=2.0)

        with patch.object(
            SkillMeatClient,
            "_request_json",
            return_value={"id": "mem_1"},
        ) as request_mock:
            payload = await client.add_context_module_memory(
                "cm_1",
                memory_type="learning",
                title="Successful pattern",
                content="Keep this pattern.",
                confidence=0.82,
                metadata={"sessionId": "session-1"},
            )

        self.assertEqual(payload["id"], "mem_1")
        request_mock.assert_called_once_with(
            "/api/v1/context-modules/cm_1/memories",
            None,
            method="POST",
            body={
                "type": "learning",
                "title": "Successful pattern",
                "content": "Keep this pattern.",
                "confidence": 0.82,
                "metadata": {"sessionId": "session-1"},
            },
        )


if __name__ == "__main__":
    unittest.main()
