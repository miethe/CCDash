"""HTTP-level contract tests for the M3-002 provider-credential rollup surface.

``test_provider_credential_rollup.py`` proves the service's correctness core
(the attribution choke points, rotation-lineage grouping) by calling
``ProviderCredentialRollupService.get_rollup`` directly. That is not the same
claim as "an external script can read this over HTTP" — it cannot catch a
mis-registered route, a mis-wired query param, an auth/workspace dependency
regression, or a JSON field-name drift in ``ClientV1Envelope`` serialisation.
This file closes that gap by driving the real FastAPI app through
``fastapi.testclient.TestClient``, reusing ``_standard_patches`` from
``test_external_api_contract.py`` — the same harness
``test_intent_node_cost_http_contract.py`` uses for its own REST surface.

Covers:
  1. GET /api/v1/provider-credentials/rollup -> 200 envelope; attributed-only
     spend total plus the EXACT excluded count for a series that has both an
     attributed and a non-attributed session.
  2. ?include_unattributed=true -> the excluded row is returned, with its raw
     (always-null-per-v51) spend_delta_raw and its attribution token intact.
  3. Default response (flag omitted) omits excluded_sessions entirely, but
     still reports spend_excluded_count -- the core invariant: a partial
     answer can never read as a complete one, whether or not the caller
     opted into the debug rows.
  4. GET /api/v1/capabilities advertises "provider-credentials:rollup".
  5. A consumer that never reads /capabilities still gets a working
     rollup response -- the endpoint's contract does not require reading
     the capability list first (capabilities are advertisement, not a gate).

Run as a named module:
    backend/.venv/bin/python -m pytest backend/tests/test_provider_credential_rollup_http.py -v
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
import tempfile
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import aiosqlite
from fastapi.testclient import TestClient

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.runtime.bootstrap import build_runtime_app
from backend.tests.test_external_api_contract import _standard_patches

PROJECT_A = "proj-rollup-http-a"
PROJECT_B = "proj-rollup-http-b"


class _AugmentedWorkspaceRegistry:
    """Wraps the app's real (DB-authoritative, ADR-006) workspace registry,
    adding two synthetic in-memory projects to ``list_projects()`` only.

    The real ``DbProjectManager`` is a process-wide singleton created at
    ``backend.project_manager`` import time, bound to whatever
    ``CCDASH_DB_PATH`` was current at THAT moment -- which predates this
    test's own tmp-db env patch and is a known, pre-existing cross-test
    isolation hazard (unrelated to the endpoint under test here; see
    ``ccdash-test-ordering-db-path-flake`` in the project's own memory
    notes). Directly inserting rows into a "projects" table the running
    process's registry singleton never actually reads is therefore not a
    reliable way to make ``ProviderCredentialRollupService.get_rollup``'s
    ``ports.workspace_registry.list_projects()`` call see this test's
    fixture projects.

    Wrapping the registry sidesteps that hazard without touching
    ``project_manager.py`` (out of scope for this task): every other
    method (auth/scope resolution during request-context building, etc.)
    delegates straight through to the real registry via ``__getattr__``;
    only ``list_projects()`` is widened, and only for this test's own app
    instance.
    """

    def __init__(self, inner, extra_projects: list) -> None:
        self._inner = inner
        self._extra_projects = extra_projects

    def list_projects(self):
        return list(self._inner.list_projects()) + list(self._extra_projects)

    def __getattr__(self, name):
        return getattr(self._inner, name)


async def _insert_credential(
    db: aiosqlite.Connection,
    *,
    cred_id: int,
    channel: str,
    credential_name: str,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    await db.execute(
        """
        INSERT INTO provider_credentials (
            id, channel, credential_name, provider_id, rotated_from_id,
            first_seen_at, last_seen_at, created_at, updated_at
        ) VALUES (?, ?, ?, '', NULL, ?, ?, ?, ?)
        """,
        (cred_id, channel, credential_name, now, now, now, now),
    )


async def _seed_fixture(db_path: str) -> None:
    """Seed credentials + sessions directly against the app's own DB file,
    after the app's own lifespan startup has already applied migrations
    (see setUpClass). Per ADR-007, an independent sqlite connection MUST
    issue PRAGMA busy_timeout.
    """
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA busy_timeout = 30000")
    try:
        await _insert_credential(db, cred_id=101, channel="ica", credential_name="HTTP-CC1")
        await db.commit()

        repo = SqliteSessionRepository(db)
        # Attributed session -- counts toward spend_usd.
        await repo.upsert(
            {
                "id": "sess-rollup-http-attributed",
                "status": "completed",
                "model": "claude-sonnet-5",
                "platformType": "Claude Code",
                "launcher": "ica-claude.sh",
                "tokensIn": 100,
                "tokensOut": 40,
                "icaKey": "HTTP-CC1",
                "icaSpendDelta": "7.25",
                "icaSpendAttribution": "attributed",
                "startedAt": "2026-08-01T00:00:00Z",
                "endedAt": "2026-08-01T00:01:00Z",
            },
            PROJECT_A,
        )
        # Non-attributed session, same credential -- excluded from spend_usd
        # but still counted toward tokens/session_count.
        await repo.upsert(
            {
                "id": "sess-rollup-http-excluded",
                "status": "completed",
                "model": "claude-sonnet-5",
                "platformType": "Claude Code",
                "launcher": "ica-claude.sh",
                "tokensIn": 9,
                "tokensOut": 3,
                "icaKey": "HTTP-CC1",
                "icaSpendDelta": None,
                "icaSpendAttribution": "concurrent_shared_key",
                "startedAt": "2026-08-01T00:02:00Z",
                "endedAt": "2026-08-01T00:03:00Z",
            },
            PROJECT_A,
        )
        # A second project's session under the same credential -- proves the
        # rollup spans multiple projects.
        await repo.upsert(
            {
                "id": "sess-rollup-http-b",
                "status": "completed",
                "model": "claude-sonnet-5",
                "platformType": "Claude Code",
                "launcher": "ica-claude.sh",
                "tokensIn": 5,
                "tokensOut": 2,
                "icaKey": "HTTP-CC1",
                "icaSpendDelta": "1.0",
                "icaSpendAttribution": "attributed",
                "startedAt": "2026-08-01T00:04:00Z",
                "endedAt": "2026-08-01T00:05:00Z",
            },
            PROJECT_B,
        )
        await db.commit()
    finally:
        await db.close()


def _find_series(data: dict, credential_name: str) -> dict:
    # ProviderCredentialRollupResponse / CredentialSeriesRollup use the same
    # ccdash_contracts camelCase alias_generator config as every other DTO
    # wrapped in ClientV1Envelope on this router, so the wire shape is
    # camelCase -- assert against camelCase keys throughout this file.
    for series in data["series"]:
        if credential_name in series["credentialNames"]:
            return series
    raise AssertionError(f"no series found containing credential {credential_name!r}")


class TestProviderCredentialRollupHttpContract(unittest.TestCase):
    """Drive the real app over HTTP for the provider-credential rollup surface."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()
        cls._env_patcher = patch.dict(
            os.environ,
            {"CCDASH_DB_PATH": cls._tmpdb.name, "CCDASH_DB_BACKEND": "sqlite"},
        )
        cls._env_patcher.start()
        cls._app = build_runtime_app("test")
        cls._patches = _standard_patches()
        for p in cls._patches:
            p.start()

        # Enter the TestClient context once; this triggers the app lifespan
        # (migrations run against cls._tmpdb.name here).
        cls._tc = TestClient(cls._app, raise_server_exceptions=False)
        cls._tc.__enter__()
        cls.client = cls._tc

        # Seed fixture rows directly into the now-migrated db file.
        asyncio.run(_seed_fixture(cls._tmpdb.name))

        # Widen the registered-project set for this app instance only (see
        # _AugmentedWorkspaceRegistry's docstring) so
        # ProviderCredentialRollupService.get_rollup's cross-project
        # ports.workspace_registry.list_projects() call sees PROJECT_A/B --
        # the DB-authoritative "projects" table is not reliably reachable
        # from a fresh tmp db by the process-wide registry singleton.
        core_ports = cls._app.state.core_ports
        cls._app.state.core_ports = dataclasses.replace(
            core_ports,
            workspace_registry=_AugmentedWorkspaceRegistry(
                core_ports.workspace_registry,
                [
                    types.SimpleNamespace(id=PROJECT_A, name=PROJECT_A),
                    types.SimpleNamespace(id=PROJECT_B, name=PROJECT_B),
                ],
            ),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tc.__exit__(None, None, None)
        for p in reversed(cls._patches):
            p.stop()
        cls._env_patcher.stop()
        try:
            os.unlink(cls._tmpdb.name)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # 4. Capability discovery
    # ------------------------------------------------------------------

    def test_capabilities_includes_provider_credentials_rollup(self) -> None:
        data = self.client.get("/api/v1/capabilities").json()["data"]
        self.assertIn("provider-credentials:rollup", data["capabilities"])

    # ------------------------------------------------------------------
    # 5. Endpoint works for a consumer that never read /capabilities --
    # the capability string is advertisement, not a gate on the route.
    # ------------------------------------------------------------------

    def test_rollup_endpoint_works_without_reading_capabilities_first(self) -> None:
        resp = self.client.get("/api/v1/provider-credentials/rollup")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        for f in ("status", "data", "meta"):
            self.assertIn(f, body, f"envelope missing: {f}")

    # ------------------------------------------------------------------
    # 1. Attributed-only spend total + exact excluded count, over HTTP.
    # ------------------------------------------------------------------

    def test_default_response_spend_is_attributed_only_with_exact_excluded_count(self) -> None:
        resp = self.client.get("/api/v1/provider-credentials/rollup")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]

        series = _find_series(data, "HTTP-CC1")
        # 7.25 (attributed, proj-a) + 1.0 (attributed, proj-b); the
        # concurrent_shared_key session contributes nothing.
        self.assertAlmostEqual(series["spendUsd"], 8.25, places=6)
        self.assertEqual(series["spendExcludedCount"], 1)
        self.assertEqual(
            series["spendExcludedByAttribution"], {"concurrent_shared_key": 1}
        )

        # Token/session counts include the excluded session too.
        self.assertEqual(series["sessionCount"], 3)
        self.assertEqual(series["tokensIn"], 114)  # 100 + 9 + 5
        self.assertEqual(series["tokensOut"], 45)  # 40 + 3 + 2

        # Spans both projects.
        self.assertEqual(set(series["projectIds"]), {PROJECT_A, PROJECT_B})

    def test_default_response_omits_excluded_sessions_field(self) -> None:
        resp = self.client.get("/api/v1/provider-credentials/rollup")
        data = resp.json()["data"]
        self.assertFalse(data["includeUnattributed"])
        series = _find_series(data, "HTTP-CC1")
        self.assertIsNone(series["excludedSessions"])
        # The invariant holds on the default response too: spendExcludedCount
        # is present alongside spendUsd, unconditionally on include_unattributed
        # -- a partial answer can never read as complete.
        self.assertEqual(series["spendExcludedCount"], 1)

    # ------------------------------------------------------------------
    # 2. include_unattributed=true returns the excluded rows.
    # ------------------------------------------------------------------

    def test_include_unattributed_true_returns_excluded_rows(self) -> None:
        resp = self.client.get(
            "/api/v1/provider-credentials/rollup?include_unattributed=true"
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        self.assertTrue(data["includeUnattributed"])

        series = _find_series(data, "HTTP-CC1")
        self.assertIsNotNone(series["excludedSessions"])
        self.assertEqual(len(series["excludedSessions"]), 1)
        excluded = series["excludedSessions"][0]
        self.assertEqual(excluded["sessionId"], "sess-rollup-http-excluded")
        self.assertEqual(excluded["attribution"], "concurrent_shared_key")
        # Per the v51 contract, non-attributed deltas are stored NULL.
        self.assertIsNone(excluded["spendDeltaRaw"])

        # The invariant holds regardless of the flag: spendExcludedCount
        # is present either way, so a partial answer never reads complete.
        self.assertEqual(series["spendExcludedCount"], 1)

    def test_include_unattributed_defaults_to_false_when_omitted(self) -> None:
        resp = self.client.get("/api/v1/provider-credentials/rollup")
        data = resp.json()["data"]
        self.assertFalse(data["includeUnattributed"])

    # ------------------------------------------------------------------
    # Router registration sanity check
    # ------------------------------------------------------------------

    def test_route_is_registered_in_openapi_schema(self) -> None:
        paths = self._app.openapi()["paths"]
        self.assertIn("/api/v1/provider-credentials/rollup", paths)

    # ------------------------------------------------------------------
    # Periodic windowing (since/until) — AC3 "cumulative AND periodic"
    # ------------------------------------------------------------------

    def test_window_narrows_to_matching_project_a_sessions_only(self) -> None:
        # sess-rollup-http-attributed@00:00 + sess-rollup-http-excluded@00:02
        # fall inside this window; sess-rollup-http-b@00:04 (project B) does
        # not.
        resp = self.client.get(
            "/api/v1/provider-credentials/rollup"
            "?since=2026-08-01T00:00:00Z&until=2026-08-01T00:02:30Z"
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        series = _find_series(data, "HTTP-CC1")
        self.assertAlmostEqual(series["spendUsd"], 7.25, places=6)
        self.assertEqual(series["spendExcludedCount"], 1)
        self.assertEqual(series["sessionCount"], 2)
        self.assertEqual(set(series["projectIds"]), {PROJECT_A})

    def test_window_echoes_effective_since_until_on_response(self) -> None:
        resp = self.client.get(
            "/api/v1/provider-credentials/rollup"
            "?since=2026-08-01T00:00:00Z&until=2026-08-01T00:02:30Z"
        )
        data = resp.json()["data"]
        self.assertIsNotNone(data["since"])
        self.assertIsNotNone(data["until"])
        self.assertTrue(data["since"].startswith("2026-08-01T00:00:00"))

    def test_omitting_window_leaves_since_until_null(self) -> None:
        resp = self.client.get("/api/v1/provider-credentials/rollup")
        data = resp.json()["data"]
        self.assertIsNone(data["since"])
        self.assertIsNone(data["until"])

    def test_invalid_since_returns_clean_400_not_500(self) -> None:
        resp = self.client.get(
            "/api/v1/provider-credentials/rollup?since=not-a-timestamp"
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("since", resp.json().get("detail", ""))

    def test_invalid_until_returns_clean_400_not_500(self) -> None:
        resp = self.client.get(
            "/api/v1/provider-credentials/rollup?until=also-not-a-timestamp"
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("until", resp.json().get("detail", ""))


if __name__ == "__main__":
    unittest.main()
