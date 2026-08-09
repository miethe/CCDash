"""HTTP-level contract tests for the itt-node-session-cost-join feature.

AC2 is literally "session_logs rows are reachable by an external script
without direct postgres access" — a claim about HTTP.  The unit/service
tests in ``test_entity_graph_intent_node_links.py``,
``test_intent_node_cost_service.py``, and ``test_session_tool_calls_endpoint.py``
all call the handler *functions* directly and therefore cannot catch a
mis-registered route, a mis-declared query param, an auth/workspace
dependency regression, or a JSON field-name drift in ``ClientV1Envelope``
serialisation.  This file closes that gap by driving the real FastAPI app
through ``fastapi.testclient.TestClient`` — the same harness used by
``test_client_v1_contract.py`` and ``test_external_api_contract.py`` (see
those files for the base pattern; this file reuses ``_standard_patches``
from the latter rather than inventing a new harness).

Covers, over real HTTP against a seeded throw-away SQLite app:
  1. GET /sessions/{id}/tool-calls -> 200 envelope with exact camelCase
     {items, cursor, limit, nextCursor} keys.
  2. Same endpoint: missing project_id -> 400; unknown session -> 404.
  3. POST /intent-nodes/{id}/sessions -> declare a binding, then
     GET /intent-nodes/{id}/cost -> concrete token/cost totals matching the
     seeded sessions, attributionScope == "declared" (AC1 end-to-end proof:
     node id in, token totals out, one round trip, no manual correlation).
  4. Same GET with expand_family=true -> attributionScope == "family" and a
     wider session set (the workflow_id sibling is pulled in).
  5. GET /capabilities advertises both "intent-nodes:cost" and
     "sessions:tool-calls".
  6. Reviewer-confirmed cross-project leak regression: an explicit but empty
     ``?project_id=`` on the cost endpoint (distinct from an omitted one,
     which FastAPI's own required-Query validation already rejects as 422)
     must be rejected as 400 -- including when combined with
     ``expand_family=true``, which is the exact PoC shape that previously
     folded a foreign project's session into the rollup. A dedicated
     cross-project fixture (SESS_FOREIGN, same workflow_id as SESS_A but a
     different project, with deliberately oversized token counts) proves
     the foreign session is excluded both by the 400 guard AND by
     ``list_by_workflow_ids``'s own project_id scoping when a *correct*
     project_id is supplied.

Run as a named module:
    backend/.venv/bin/python -m pytest backend/tests/test_intent_node_cost_http_contract.py -v
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

import aiosqlite
from fastapi.testclient import TestClient

from backend.db.repositories.sessions import SqliteSessionRepository
from backend.runtime.bootstrap import build_runtime_app
from backend.tests.test_external_api_contract import _standard_patches

PROJECT_ID = "proj-itt-http-contract"
NODE_ID = "itt-node-http-contract-001"
SESS_A = "sess-http-contract-a"  # declared binding; workflow "wf-http-A"
SESS_B = "sess-http-contract-b"  # workflow sibling of A (same workflow_id), NOT declared
SESS_C = "sess-http-contract-c"  # unrelated workflow "wf-http-B", must never be pulled in

# Cross-project leak PoC fixture (reviewer-confirmed defect): a session that
# shares SESS_A's workflow_id but belongs to a DIFFERENT project. Deliberately
# oversized token counts so any leak is unmistakable in the assertions below.
PROJECT_ID_FOREIGN = "proj-itt-http-contract-foreign"
SESS_FOREIGN = "sess-http-contract-foreign"  # same workflow "wf-http-A" as SESS_A, foreign project
NODE_ID_LEAK = "itt-node-http-contract-leak-poc"


def _session(session_id: str, **overrides) -> dict:
    base: dict = {
        "id": session_id,
        "status": "completed",
        "tokensIn": 0,
        "tokensOut": 0,
        "totalCost": 0.0,
        "startedAt": "2026-08-01T00:00:00Z",
        "endedAt": "2026-08-01T00:01:00Z",
    }
    base.update(overrides)
    return base


async def _seed_fixture(db_path: str) -> None:
    """Seed sessions + session_logs directly against the app's own DB file.

    Runs AFTER the app's lifespan startup has already applied migrations
    against *db_path* (see ``setUpClass`` below), so the schema already
    exists — this only opens an independent connection to write fixture
    rows. Per ADR-007, an independent sqlite connection MUST issue
    ``PRAGMA busy_timeout``.
    """
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA busy_timeout = 30000")
    try:
        repo = SqliteSessionRepository(db)
        await repo.upsert(
            _session(SESS_A, workflowId="wf-http-A", tokensIn=100, tokensOut=50, totalCost=1.5),
            PROJECT_ID,
        )
        await repo.upsert(
            _session(SESS_B, workflowId="wf-http-A", tokensIn=200, tokensOut=100, totalCost=2.5),
            PROJECT_ID,
        )
        await repo.upsert(
            _session(SESS_C, workflowId="wf-http-B", tokensIn=10, tokensOut=5, totalCost=0.1),
            PROJECT_ID,
        )
        # Cross-project leak PoC fixture: same workflow_id as SESS_A, but a
        # DIFFERENT project. Must NEVER be folded into a PROJECT_ID rollup,
        # even with expand_family=true.
        await repo.upsert(
            _session(
                SESS_FOREIGN,
                workflowId="wf-http-A",
                tokensIn=9_999,
                tokensOut=9_998,
                totalCost=99.99,
            ),
            PROJECT_ID_FOREIGN,
        )
        await repo.upsert_logs(
            SESS_A,
            [
                {
                    "id": "log-1",
                    "timestamp": "2026-08-01T00:00:01Z",
                    "speaker": "user",
                    "type": "message",
                    "content": "please read the config",
                    "toolCall": None,
                },
                {
                    "id": "log-2",
                    "timestamp": "2026-08-01T00:00:02Z",
                    "speaker": "assistant",
                    "type": "message",
                    "content": "",
                    "toolCall": {
                        "id": "tc-1",
                        "name": "Read",
                        "args": "config.yaml",
                        "output": "key: value",
                        "status": "success",
                        "isError": False,
                    },
                },
            ],
            PROJECT_ID,
        )
        await db.commit()
    finally:
        await db.close()


class TestIntentNodeCostHttpContract(unittest.TestCase):
    """Drive the real app over HTTP for the itt-node-session-cost-join feature."""

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

        # Seed fixture rows directly into the now-migrated db file, via an
        # independent connection (see _seed_fixture's docstring).
        asyncio.run(_seed_fixture(cls._tmpdb.name))

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
    # 5. Capability discovery
    # ------------------------------------------------------------------

    def test_capabilities_includes_intent_nodes_cost(self) -> None:
        data = self.client.get("/api/v1/capabilities").json()["data"]
        self.assertIn("intent-nodes:cost", data["capabilities"])

    def test_capabilities_includes_sessions_tool_calls(self) -> None:
        data = self.client.get("/api/v1/capabilities").json()["data"]
        self.assertIn("sessions:tool-calls", data["capabilities"])

    # ------------------------------------------------------------------
    # 1 + 2. Tool-calls endpoint over real HTTP
    # ------------------------------------------------------------------

    def test_tool_calls_missing_project_id_returns_400(self) -> None:
        resp = self.client.get(f"/api/v1/sessions/{SESS_A}/tool-calls")
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_tool_calls_unknown_session_returns_404(self) -> None:
        resp = self.client.get(
            f"/api/v1/sessions/does-not-exist-http-contract/tool-calls?project_id={PROJECT_ID}"
        )
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_tool_calls_200_has_exact_envelope_keys(self) -> None:
        """Pinned over HTTP: the {items, cursor, limit, nextCursor} envelope,
        wrapped inside {status, data, meta} — the exact shape an external
        script receives, not just what the handler function returns in
        Python."""
        resp = self.client.get(
            f"/api/v1/sessions/{SESS_A}/tool-calls?project_id={PROJECT_ID}"
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        for f in ("status", "data", "meta"):
            self.assertIn(f, body, f"envelope missing: {f}")
        data = body["data"]
        for f in ("items", "cursor", "limit", "nextCursor"):
            self.assertIn(f, data, f"tool-calls page missing field: {f}")
        # Only the tool-call-bearing log entry survives the filter.
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["toolCall"]["name"], "Read")

    def test_tool_calls_tool_filter_over_http(self) -> None:
        resp = self.client.get(
            f"/api/v1/sessions/{SESS_A}/tool-calls?project_id={PROJECT_ID}&tool=Read"
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        items = resp.json()["data"]["items"]
        self.assertEqual(len(items), 1)

        resp_miss = self.client.get(
            f"/api/v1/sessions/{SESS_A}/tool-calls?project_id={PROJECT_ID}&tool=Write"
        )
        self.assertEqual(resp_miss.json()["data"]["items"], [])

    # ------------------------------------------------------------------
    # 3. AC1 end-to-end: declare a binding, then read the cost rollup
    # ------------------------------------------------------------------

    def test_declare_bindings_returns_200_with_linked_ids(self) -> None:
        resp = self.client.post(
            f"/api/v1/intent-nodes/{NODE_ID}/sessions",
            json={"project_id": PROJECT_ID, "session_ids": [SESS_A]},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        self.assertEqual(data["nodeId"], NODE_ID)
        self.assertEqual(data["linkedSessionIds"], [SESS_A])
        self.assertEqual(data["linkedCount"], 1)

    def test_cost_declared_scope_matches_seeded_totals_exactly(self) -> None:
        """AC1 end-to-end: node id in -> token totals out, one round trip,
        no manual correlation. Numbers must match the exact seeded fixture
        (tokensIn=100, tokensOut=50, totalCost=1.5 for SESS_A alone)."""
        post_resp = self.client.post(
            f"/api/v1/intent-nodes/{NODE_ID}/sessions",
            json={"project_id": PROJECT_ID, "session_ids": [SESS_A]},
        )
        self.assertEqual(post_resp.status_code, 200, post_resp.text)

        cost_resp = self.client.get(
            f"/api/v1/intent-nodes/{NODE_ID}/cost?project_id={PROJECT_ID}"
        )
        self.assertEqual(cost_resp.status_code, 200, cost_resp.text)
        data = cost_resp.json()["data"]

        self.assertEqual(data["nodeId"], NODE_ID)
        self.assertEqual(data["attributionScope"], "declared")
        self.assertEqual(len(data["sessions"]), 1)
        self.assertEqual(data["sessions"][0]["sessionId"], SESS_A)
        self.assertTrue(data["sessions"][0]["declared"])

        totals = data["totals"]
        self.assertEqual(totals["sessionCount"], 1)
        self.assertEqual(totals["tokensIn"], 100)
        self.assertEqual(totals["tokensOut"], 50)
        self.assertAlmostEqual(totals["totalCost"], 1.5)

    # ------------------------------------------------------------------
    # 4. expand_family widens the rollup and relabels the scope
    # ------------------------------------------------------------------

    def test_cost_family_scope_widens_to_workflow_sibling_over_http(self) -> None:
        self.client.post(
            f"/api/v1/intent-nodes/{NODE_ID}/sessions",
            json={"project_id": PROJECT_ID, "session_ids": [SESS_A]},
        )

        cost_resp = self.client.get(
            f"/api/v1/intent-nodes/{NODE_ID}/cost"
            f"?project_id={PROJECT_ID}&expand_family=true"
        )
        self.assertEqual(cost_resp.status_code, 200, cost_resp.text)
        data = cost_resp.json()["data"]

        self.assertEqual(data["attributionScope"], "family")
        session_ids = {s["sessionId"] for s in data["sessions"]}
        # SESS_B shares SESS_A's workflow_id ("wf-http-A") -> pulled in.
        # SESS_C belongs to an unrelated workflow ("wf-http-B") -> excluded.
        self.assertEqual(session_ids, {SESS_A, SESS_B})

        totals = data["totals"]
        self.assertEqual(totals["sessionCount"], 2)
        self.assertEqual(totals["tokensIn"], 300)  # 100 + 200
        self.assertEqual(totals["tokensOut"], 150)  # 50 + 100
        self.assertAlmostEqual(totals["totalCost"], 4.0)  # 1.5 + 2.5

    # ------------------------------------------------------------------
    # Reviewer-confirmed defect: empty (present-but-falsy) project_id must
    # be rejected — omitted project_id (422, FastAPI's own required-param
    # validation) is a DIFFERENT case from an explicit "?project_id=" empty
    # string (400, this handler's own guard). Mirrors
    # test_tool_calls_missing_project_id_returns_400's sibling contract.
    # ------------------------------------------------------------------

    def test_cost_omitted_project_id_returns_422(self) -> None:
        resp = self.client.get(f"/api/v1/intent-nodes/{NODE_ID}/cost")
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_cost_empty_project_id_returns_400(self) -> None:
        resp = self.client.get(f"/api/v1/intent-nodes/{NODE_ID}/cost?project_id=")
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_cost_empty_project_id_with_expand_family_still_returns_400(self) -> None:
        """The exact reviewer PoC shape: an empty project_id combined with
        expand_family=true must be rejected before any session lookup runs,
        not silently degrade to an unscoped (cross-project) read."""
        resp = self.client.get(
            f"/api/v1/intent-nodes/{NODE_ID}/cost?project_id=&expand_family=true"
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_declare_empty_project_id_in_body_is_rejected(self) -> None:
        """An empty project_id in the POST body must not write a link row.

        Rejected as HTTP 422 by IntentNodeSessionBindingRequest's
        Field(..., min_length=1) — pydantic validation runs before the
        handler (and its own defense-in-depth ValueError guard) ever sees
        the request, so this is 422 rather than the GET endpoint's 400. See
        test_intent_node_cost_service.py's
        test_declare_intent_node_sessions_rejects_empty_project_id for the
        service-layer guard this pydantic constraint backs up.
        """
        resp = self.client.post(
            "/api/v1/intent-nodes/itt-node-http-contract-empty-pid/sessions",
            json={"project_id": "", "session_ids": [SESS_A]},
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    # ------------------------------------------------------------------
    # The leak-pinning tests: two sessions in two DIFFERENT projects share a
    # workflow_id; declaring only the same-project one and requesting
    # expand_family=true must NEVER fold the foreign-project session in —
    # neither via the empty-project_id bypass (blocked at 400 above the
    # session lookup) nor via a correctly-scoped request (blocked by
    # list_by_workflow_ids's own project_id filter).
    # ------------------------------------------------------------------

    def test_cross_project_leak_empty_project_id_is_blocked_before_any_lookup(self) -> None:
        declare_resp = self.client.post(
            f"/api/v1/intent-nodes/{NODE_ID_LEAK}/sessions",
            json={"project_id": PROJECT_ID, "session_ids": [SESS_A]},
        )
        self.assertEqual(declare_resp.status_code, 200, declare_resp.text)

        # This is the exact reviewer PoC request shape. Before the fix, this
        # returned HTTP 200 with SESS_FOREIGN's 9,999 tokens folded into the
        # rollup (tokensIn 100 -> 10099). It must now be rejected outright.
        leak_resp = self.client.get(
            f"/api/v1/intent-nodes/{NODE_ID_LEAK}/cost?project_id=&expand_family=true"
        )
        self.assertEqual(leak_resp.status_code, 400, leak_resp.text)

    def test_cross_project_leak_correct_project_id_excludes_foreign_session(self) -> None:
        declare_resp = self.client.post(
            f"/api/v1/intent-nodes/{NODE_ID_LEAK}/sessions",
            json={"project_id": PROJECT_ID, "session_ids": [SESS_A]},
        )
        self.assertEqual(declare_resp.status_code, 200, declare_resp.text)

        cost_resp = self.client.get(
            f"/api/v1/intent-nodes/{NODE_ID_LEAK}/cost"
            f"?project_id={PROJECT_ID}&expand_family=true"
        )
        self.assertEqual(cost_resp.status_code, 200, cost_resp.text)
        data = cost_resp.json()["data"]

        session_ids = {s["sessionId"] for s in data["sessions"]}
        # SESS_B shares SESS_A's workflow_id AND SESS_A's project -> pulled in.
        # SESS_FOREIGN shares SESS_A's workflow_id but belongs to a DIFFERENT
        # project -> must be excluded even under expand_family=true.
        self.assertNotIn(SESS_FOREIGN, session_ids)
        self.assertEqual(session_ids, {SESS_A, SESS_B})

        # Totals must equal project PROJECT_ID's own sessions only —
        # SESS_FOREIGN's oversized 9,999/9,998/99.99 must not appear at all.
        totals = data["totals"]
        self.assertEqual(totals["sessionCount"], 2)
        self.assertEqual(totals["tokensIn"], 300)  # SESS_A(100) + SESS_B(200), never +9999
        self.assertEqual(totals["tokensOut"], 150)  # SESS_A(50) + SESS_B(100), never +9998
        self.assertAlmostEqual(totals["totalCost"], 4.0)  # SESS_A(1.5) + SESS_B(2.5), never +99.99

    # ------------------------------------------------------------------
    # Router registration sanity check
    # ------------------------------------------------------------------

    def test_new_routes_are_registered_in_openapi_schema(self) -> None:
        paths = self._app.openapi()["paths"]
        for expected in (
            "/api/v1/sessions/{session_id}/tool-calls",
            "/api/v1/intent-nodes/{node_id}/sessions",
            "/api/v1/intent-nodes/{node_id}/cost",
        ):
            self.assertIn(expected, paths, f"Expected path not in OpenAPI schema: {expected}")


if __name__ == "__main__":
    unittest.main()
