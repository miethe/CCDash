import types
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.models import IngestRunResponse
from backend.routers import test_visualizer as router


class TestVisualizerRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._prev_enabled = router.config.CCDASH_TEST_VISUALIZER_ENABLED
        self._prev_integrity = router.config.CCDASH_INTEGRITY_SIGNALS_ENABLED

    async def asyncTearDown(self) -> None:
        router.config.CCDASH_TEST_VISUALIZER_ENABLED = self._prev_enabled
        router.config.CCDASH_INTEGRITY_SIGNALS_ENABLED = self._prev_integrity

    def _json_request(self, payload: dict) -> types.SimpleNamespace:
        async def _json() -> dict:
            return payload

        async def _form() -> dict:
            return {}

        return types.SimpleNamespace(
            headers={"content-type": "application/json"},
            json=_json,
            form=_form,
        )

    async def test_ingest_returns_503_when_feature_flag_disabled(self) -> None:
        router.config.CCDASH_TEST_VISUALIZER_ENABLED = False
        request = self._json_request({})

        with self.assertRaises(HTTPException) as ctx:
            await router.ingest_test_run(request)

        self.assertEqual(ctx.exception.status_code, 503)

    async def test_ingest_returns_400_for_invalid_json_payload(self) -> None:
        router.config.CCDASH_TEST_VISUALIZER_ENABLED = True
        request = self._json_request({"project_id": "project-1"})  # missing run_id + timestamp

        with self.assertRaises(HTTPException) as ctx:
            await router.ingest_test_run(request)

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_ingest_json_calls_service_and_sets_mapping_queue_flag(self) -> None:
        router.config.CCDASH_TEST_VISUALIZER_ENABLED = True
        router.config.CCDASH_INTEGRITY_SIGNALS_ENABLED = False
        request = self._json_request(
            {
                "run_id": "run-1",
                "project_id": "project-1",
                "timestamp": "2026-02-28T13:00:00Z",
                "test_results": [],
            }
        )
        fake_response = IngestRunResponse(
            run_id="run-1",
            status="created",
            test_definitions_upserted=0,
            test_results_inserted=0,
            test_results_skipped=0,
            mapping_trigger_queued=False,
            integrity_check_queued=False,
            errors=[],
        )
        created_coroutines = []

        def _fake_create_task(coro):
            created_coroutines.append(coro)
            coro.close()
            return object()

        with patch.object(router.connection, "get_connection", new=AsyncMock(return_value=object())), patch.object(router, "ingest_run", new=AsyncMock(return_value=fake_response)), patch.object(router.asyncio, "create_task", side_effect=_fake_create_task) as create_task:
            payload = await router.ingest_test_run(request)

        self.assertEqual(payload.run_id, "run-1")
        self.assertTrue(payload.mapping_trigger_queued)
        self.assertFalse(payload.integrity_check_queued)
        self.assertEqual(create_task.call_count, 1)
        self.assertEqual(len(created_coroutines), 1)


if __name__ == "__main__":
    unittest.main()
