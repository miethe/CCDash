"""TTL-expiry integration test for backend.application.services.agent_queries.cache.

CACHE-010: Verifies that after the TTL window elapses the decorator re-fetches
(cache miss) rather than serving a stale entry.

Strategy
--------
- Monkeypatch the module-level ``_query_cache`` singleton with a fresh
  ``TTLCache(maxsize=512, ttl=2)`` so the test does not depend on the
  environment's ``CCDASH_QUERY_CACHE_TTL_SECONDS`` setting.
- Monkeypatch ``get_data_version_fingerprint`` to return a fixed string so the
  decorator always has a valid fingerprint and proceeds to read/write the cache
  (the decorator bypasses cache when the fingerprint is ``None``).
- Use a test-local dummy async function wrapped by ``@memoized_query``; avoids
  standing up any real service or DB.
- ``time.sleep(2.5)`` is intentionally used (not asyncio.sleep) because
  ``TTLCache`` expiry is wall-clock based and independent of the event loop.

DO NOT call ``_set_ttl_for_testing`` — that helper does not exist; the pure
monkeypatch approach is preferred (see CACHE-010 spec).
"""
from __future__ import annotations

import time
import unittest
from unittest.mock import AsyncMock, patch

from cachetools import TTLCache

import backend.application.services.agent_queries.cache as cache_mod
from backend.application.services.agent_queries.cache import memoized_query


# ── Dummy probe function ────────────────────────────────────────────────────
#
# A plain async function (no self) decorated with memoized_query.
# param_extractor returns {} so the cache key is stable across calls.
# Each real invocation increments a counter so we can count live calls.

_call_counter: dict[str, int] = {"n": 0}


@memoized_query("ttl_test", param_extractor=lambda context, ports, **_: {})
async def _probe(context, ports):  # noqa: ANN001
    """Minimal async probe; increments a counter on each live (non-cached) call."""
    _call_counter["n"] += 1
    return _call_counter["n"]


# ── Test ────────────────────────────────────────────────────────────────────

class TTLExpiryIntegrationTest(unittest.IsolatedAsyncioTestCase):
    """After the TTL window elapses, the decorator must treat the entry as expired."""

    async def asyncSetUp(self) -> None:  # noqa: N802
        # Reset the call counter before each test run.
        _call_counter["n"] = 0

    async def test_cache_refetches_after_ttl_expiry(self) -> None:
        """Sequence: miss → hit → (sleep past TTL) → miss."""

        short_ttl_cache: TTLCache = TTLCache(maxsize=512, ttl=2)

        with (
            patch.object(cache_mod, "_query_cache", short_ttl_cache),
            patch(
                "backend.application.services.agent_queries.cache.get_data_version_fingerprint",
                new=AsyncMock(return_value="stable-fp"),
            ),
        ):
            # Dummy context/ports — only need to be truthy so the decorator
            # proceeds to fingerprinting rather than bypassing cache.
            ctx = object()
            ports = object()

            # ── First call: cache miss (counter goes to 1) ──────────────────
            result_1 = await _probe(ctx, ports)
            self.assertEqual(result_1, 1, "first call must be a cache miss → counter=1")
            self.assertEqual(_call_counter["n"], 1)

            # ── Second call (immediate): cache hit (counter stays at 1) ─────
            result_2 = await _probe(ctx, ports)
            self.assertEqual(result_2, 1, "immediate second call must be a cache hit → same value")
            self.assertEqual(_call_counter["n"], 1, "underlying function must NOT have been called again")

            # ── Wait for TTL to expire ──────────────────────────────────────
            # TTLCache expires entries based on wall-clock time.  2.5 s > 2 s TTL.
            time.sleep(2.5)

            # ── Third call: TTL expired → cache miss (counter goes to 2) ───
            result_3 = await _probe(ctx, ports)
            self.assertEqual(result_3, 2, "call after TTL expiry must be a cache miss → counter=2")
            self.assertEqual(_call_counter["n"], 2, "underlying function must have been called exactly once more")


if __name__ == "__main__":
    unittest.main()
