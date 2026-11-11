"""Worker probes must not queue behind long-lived filesystem watchers."""
from __future__ import annotations

import asyncio
import types
import unittest

import anyio
import httpx

from backend.runtime.bootstrap_worker import build_worker_probe_app


class WorkerProbeResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    def _container(self, ready: bool):
        return types.SimpleNamespace(
            profile=types.SimpleNamespace(name="worker-watch"),
            runtime_status=lambda: {
                "probeContract": {
                    "schemaVersion": "1",
                    "runtimeProfile": "worker-watch",
                    "live": {"live": True},
                    "ready": {"ready": ready, "status": "pass" if ready else "fail"},
                    "detail": {},
                },
            },
        )

    async def _request_with_thread_pool_occupied(self, path: str, *, ready: bool):
        limiter = anyio.to_thread.current_default_thread_limiter()
        original_limit = limiter.total_tokens
        borrower = object()
        limiter.total_tokens = 1
        await limiter.acquire_on_behalf_of(borrower)
        try:
            app = build_worker_probe_app(self._container(ready))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://worker"
            ) as client:
                return await asyncio.wait_for(client.get(path), timeout=1)
        finally:
            limiter.release_on_behalf_of(borrower)
            limiter.total_tokens = original_limit

    async def test_all_probe_routes_respond_when_watchers_occupy_thread_pool(self) -> None:
        for path in ("/livez", "/readyz", "/detailz"):
            with self.subTest(path=path):
                response = await self._request_with_thread_pool_occupied(path, ready=True)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["runtimeProfile"], "worker-watch")
                if path != "/livez":
                    self.assertIs(response.json()["ready"]["ready"], True)

    async def test_unready_runtime_still_returns_503_with_thread_pool_occupied(self) -> None:
        response = await self._request_with_thread_pool_occupied("/readyz", ready=False)
        self.assertEqual(response.status_code, 503)
        self.assertIs(response.json()["ready"]["ready"], False)
