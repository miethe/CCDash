"""Regression tests: /api/health/detail ``ingest_sources`` must not be a
structural constant ``[]`` on PostgreSQL deployments.

Prior bug: ``_build_ingest_sources_detail()`` returned ``[]`` unconditionally
whenever ``config.DB_BACKEND != "sqlite"``, even when ``ingest_cursors`` had
rows — because it opened its own synchronous SQLite connection and had no PG
path at all. The fix adds ``_build_ingest_sources_detail_async()``, which
reuses the shared async DB connection (``connection._connection``, the same
object ``_readyz_check_db()`` probes) and delegates to the transport-neutral
``get_ingest_sources_health()`` — already backend-agnostic (aiosqlite vs
asyncpg) and validated live on the asyncpg pool in the api container.

Covers:
  a) Fake asyncpg-like pool with rows + DB_BACKEND=postgres → ONE row back,
     not ``[]`` (the actual regression guard).
  b) ``connection._connection`` is ``None`` → ``[]``, never raises.
  c) Fake pool whose ``.fetch()`` raises → ``[]``, never raises.
  d) ``_build_detail_probe_payload(rs, ingest_sources=[...])`` uses the
     passed-through list; omitting the kwarg falls back to the sync builder
     (backward compatibility with existing sync call sites).

Structure mirrors ``backend/tests/test_ingest_sources_health.py``.

NOTE: Run ONLY this named file — the test suite hangs on unscoped runs:
  backend/.venv/bin/python -m pytest backend/tests/test_health_detail_ingest_sources_pg.py -v
"""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

import backend.runtime.bootstrap as bs
from backend.db import connection


# ---------------------------------------------------------------------------
# Shared runtime_status builder (mirrors test_health_detail_fields.py)
# ---------------------------------------------------------------------------

def _minimal_runtime_status() -> dict[str, Any]:
    """Return the minimum runtime_status dict accepted by both payload builders."""
    section: dict[str, Any] = {
        "state": "ready",
        "status": "ok",
        "summary": "ok",
        "ready": True,
        "degraded": False,
        "reasons": [],
        "checks": [],
        "activities": [],
        "recommendedCadence": {},
        "requiredReadinessChecks": [],
        "runtime": {},
        "storage": {},
        "database": {},
        "binding": {},
        "auth": {"guardrail": {"warnings": [], "warningCodes": []}},
        "warnings": [],
        "warningCodes": [],
    }
    return {
        "probeContract": {
            "schemaVersion": "v2",
            "runtimeProfile": "local",
            "live": section,
            "ready": section,
            "detail": section,
        },
    }


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeAsyncpgPool:
    """Minimal stand-in for an asyncpg ``Pool`` — only ``.fetch()`` is used
    by ``get_ingest_sources_health()``'s PG branch."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def fetch(self, _query: str) -> list[dict[str, Any]]:
        return self._rows


class _FakeRaisingAsyncpgPool:
    """Fake asyncpg pool whose ``.fetch()`` raises — proves the async builder
    swallows the error and returns ``[]`` rather than propagating."""

    async def fetch(self, _query: str) -> list[dict[str, Any]]:
        raise RuntimeError("simulated asyncpg connection failure")


# ---------------------------------------------------------------------------
# (a) Fake asyncpg pool with rows + postgres backend -> ONE row, not []
# ---------------------------------------------------------------------------

class TestBuildIngestSourcesDetailAsyncPostgres(unittest.IsolatedAsyncioTestCase):
    async def test_returns_row_from_asyncpg_pool(self) -> None:
        fake_row = {
            "source_id": "daemon-a",
            "project_id": "proj-1",
            "workspace_id": "default-local",
            "last_cursor": "cursor-123",
            "last_ingest_at": None,
        }
        fake_pool = _FakeAsyncpgPool([fake_row])

        with patch.object(connection, "_connection", fake_pool), patch.object(
            bs.config, "DB_BACKEND", "postgres"
        ):
            results = await bs._build_ingest_sources_detail_async()

        self.assertEqual(len(results), 1)
        self.assertNotEqual(results, [])
        row = results[0]
        expected_keys = {
            "source_id",
            "project_id",
            "workspace_id",
            "last_cursor",
            "last_ingest_at",
            "lag_seconds",
            "state",
        }
        self.assertEqual(set(row.keys()), expected_keys)
        self.assertEqual(row["source_id"], "daemon-a")
        self.assertEqual(row["project_id"], "proj-1")
        self.assertEqual(row["state"], "idle")  # last_ingest_at is None


# ---------------------------------------------------------------------------
# (b) connection._connection is None -> [], never raises
# ---------------------------------------------------------------------------

class TestBuildIngestSourcesDetailAsyncNoConnection(unittest.IsolatedAsyncioTestCase):
    async def test_returns_empty_list_when_connection_absent(self) -> None:
        with patch.object(connection, "_connection", None):
            results = await bs._build_ingest_sources_detail_async()
        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# (c) Fake pool whose .fetch() raises -> [], never raises
# ---------------------------------------------------------------------------

class TestBuildIngestSourcesDetailAsyncRaises(unittest.IsolatedAsyncioTestCase):
    async def test_returns_empty_list_on_query_failure(self) -> None:
        fake_pool = _FakeRaisingAsyncpgPool()
        with patch.object(connection, "_connection", fake_pool):
            # Must not raise.
            results = await bs._build_ingest_sources_detail_async()
        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# (d) _build_detail_probe_payload: passthrough vs sync-builder fallback
# ---------------------------------------------------------------------------

class TestBuildDetailProbePayloadIngestSourcesKwarg(unittest.TestCase):
    def test_explicit_ingest_sources_kwarg_is_used_verbatim(self) -> None:
        rs = _minimal_runtime_status()
        supplied = [
            {
                "source_id": "daemon-b",
                "project_id": "proj-2",
                "workspace_id": "default-local",
                "last_cursor": None,
                "last_ingest_at": None,
                "lag_seconds": None,
                "state": "idle",
            }
        ]
        payload = bs._build_detail_probe_payload(rs, ingest_sources=supplied)
        self.assertEqual(payload["ingest_sources"], supplied)

    def test_omitted_kwarg_falls_back_to_sync_builder(self) -> None:
        rs = _minimal_runtime_status()
        with patch.object(
            bs, "_build_ingest_sources_detail", return_value=[{"source_id": "sync-fallback"}]
        ) as mock_sync_builder:
            payload = bs._build_detail_probe_payload(rs)

        mock_sync_builder.assert_called_once()
        self.assertEqual(payload["ingest_sources"], [{"source_id": "sync-fallback"}])

    def test_single_positional_arg_call_site_still_works(self) -> None:
        """Existing sync test call sites pass a single positional arg — must
        keep working unchanged (backward compatibility, not made async)."""
        rs = _minimal_runtime_status()
        payload = bs._build_detail_probe_payload(rs)
        self.assertIn("ingest_sources", payload)
        self.assertIsInstance(payload["ingest_sources"], list)


if __name__ == "__main__":
    unittest.main()
