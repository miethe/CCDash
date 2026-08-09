"""Tests for backend/application/services/agent_queries/intent_node_cost.py.

Covers the itt-node-session-cost-join AC1 acceptance criteria:
  * declare_intent_node_sessions records an idempotent binding.
  * get_intent_node_cost rolls up tokens_in/tokens_out/total_cost across the
    EXACT declared session set by default (attributionScope="declared").
  * expand_family=True widens the rollup to every session sharing a declared
    session's workflow_id within the project (attributionScope="family"),
    while a session with a different workflow_id is correctly excluded.
  * An unknown/unlinked node yields the explicit zero-workload response
    (sessionCount=0, sessions=[]), never an error.

Run as a named module:
    backend/.venv/bin/python -m pytest backend/tests/test_intent_node_cost_service.py -v
"""
from __future__ import annotations

import unittest
from typing import Any

import aiosqlite

from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.application.services.agent_queries.intent_node_cost import (
    ATTRIBUTION_SCOPE_DECLARED,
    ATTRIBUTION_SCOPE_FAMILY,
    declare_intent_node_sessions,
    get_intent_node_cost,
)
from backend.db.repositories.sessions import SqliteSessionRepository
from backend.db.sqlite_migrations import run_migrations

PROJECT_ID = "proj-alpha"
OTHER_PROJECT_ID = "proj-beta"
NODE_ID = "itt-node-cost-001"


class FakeCorePortsFactory:
    """Minimal CorePorts-compatible object backed by an in-memory SQLite DB."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._storage = LocalStorageUnitOfWork(db)

    @property
    def storage(self) -> LocalStorageUnitOfWork:
        return self._storage


def _session(session_id: str, **overrides: Any) -> dict:
    base = {
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


class TestIntentNodeCostService(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.ports = FakeCorePortsFactory(self.db)
        self.session_repo = SqliteSessionRepository(self.db)

        # sess-1 and sess-2 share workflow "wf-A" (an orchestrator + its
        # subagent, e.g.); sess-3 belongs to an unrelated workflow "wf-B".
        await self.session_repo.upsert(
            _session("sess-1", workflowId="wf-A", tokensIn=100, tokensOut=50, totalCost=1.5),
            PROJECT_ID,
        )
        await self.session_repo.upsert(
            _session("sess-2", workflowId="wf-A", tokensIn=200, tokensOut=100, totalCost=2.5),
            PROJECT_ID,
        )
        await self.session_repo.upsert(
            _session("sess-3", workflowId="wf-B", tokensIn=10, tokensOut=5, totalCost=0.1),
            PROJECT_ID,
        )
        await self.db.commit()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    # ── declare_intent_node_sessions ─────────────────────────────────────────

    async def test_declare_returns_deduped_session_ids(self) -> None:
        declared = await declare_intent_node_sessions(
            NODE_ID, ["sess-1", "sess-1", "sess-2"], PROJECT_ID, self.ports
        )
        self.assertEqual(declared, ["sess-1", "sess-2"])

    # ── declared scope (default) ─────────────────────────────────────────────

    async def test_declared_scope_rolls_up_exactly_the_bound_session(self) -> None:
        await declare_intent_node_sessions(NODE_ID, ["sess-1"], PROJECT_ID, self.ports)

        result = await get_intent_node_cost(NODE_ID, PROJECT_ID, self.ports)

        self.assertEqual(result.attribution_scope, ATTRIBUTION_SCOPE_DECLARED)
        self.assertEqual(result.totals.session_count, 1)
        self.assertEqual(result.totals.tokens_in, 100)
        self.assertEqual(result.totals.tokens_out, 50)
        self.assertAlmostEqual(result.totals.total_cost, 1.5)
        self.assertEqual(len(result.sessions), 1)
        self.assertEqual(result.sessions[0].session_id, "sess-1")
        self.assertTrue(result.sessions[0].declared)

    async def test_declared_scope_never_pulls_in_workflow_siblings(self) -> None:
        """Without expand_family, sess-2 (same workflow as sess-1) must NOT appear."""
        await declare_intent_node_sessions(NODE_ID, ["sess-1"], PROJECT_ID, self.ports)

        result = await get_intent_node_cost(NODE_ID, PROJECT_ID, self.ports, expand_family=False)

        session_ids = {s.session_id for s in result.sessions}
        self.assertEqual(session_ids, {"sess-1"})

    # ── family scope (expand_family=True) ────────────────────────────────────

    async def test_expand_family_widens_to_workflow_siblings_and_relabels_scope(self) -> None:
        await declare_intent_node_sessions(NODE_ID, ["sess-1"], PROJECT_ID, self.ports)

        result = await get_intent_node_cost(NODE_ID, PROJECT_ID, self.ports, expand_family=True)

        self.assertEqual(result.attribution_scope, ATTRIBUTION_SCOPE_FAMILY)
        session_ids = {s.session_id for s in result.sessions}
        # sess-2 shares workflow "wf-A" with declared sess-1 -> pulled in.
        # sess-3 belongs to "wf-B" -> excluded.
        self.assertEqual(session_ids, {"sess-1", "sess-2"})
        self.assertEqual(result.totals.session_count, 2)
        self.assertEqual(result.totals.tokens_in, 300)
        self.assertEqual(result.totals.tokens_out, 150)
        self.assertAlmostEqual(result.totals.total_cost, 4.0)

    async def test_expand_family_marks_declared_flag_correctly(self) -> None:
        await declare_intent_node_sessions(NODE_ID, ["sess-1"], PROJECT_ID, self.ports)

        result = await get_intent_node_cost(NODE_ID, PROJECT_ID, self.ports, expand_family=True)

        by_id = {s.session_id: s for s in result.sessions}
        self.assertTrue(by_id["sess-1"].declared)
        self.assertFalse(by_id["sess-2"].declared)

    async def test_family_member_declared_via_second_node_is_counted_once(self) -> None:
        """A session that is BOTH declared AND a family member must count once, not twice."""
        await declare_intent_node_sessions(NODE_ID, ["sess-1", "sess-2"], PROJECT_ID, self.ports)

        result = await get_intent_node_cost(NODE_ID, PROJECT_ID, self.ports, expand_family=True)

        self.assertEqual(result.totals.session_count, 2)
        self.assertEqual(result.totals.tokens_in, 300)

    # ── resilience: unknown / unlinked node ──────────────────────────────────

    async def test_unlinked_node_yields_explicit_zero_workload(self) -> None:
        result = await get_intent_node_cost("does-not-exist", PROJECT_ID, self.ports)

        self.assertEqual(result.totals.session_count, 0)
        self.assertEqual(result.sessions, [])
        self.assertEqual(result.totals.tokens_in, 0)
        self.assertEqual(result.totals.total_cost, 0.0)

    async def test_declared_session_scoped_to_different_project_is_excluded(self) -> None:
        """A declared session id is resolved with a project_id filter -- cross-project
        leakage must never happen even if the binding itself carries no project scope."""
        await declare_intent_node_sessions(NODE_ID, ["sess-1"], PROJECT_ID, self.ports)

        result = await get_intent_node_cost(NODE_ID, OTHER_PROJECT_ID, self.ports)

        self.assertEqual(result.totals.session_count, 0)
        self.assertEqual(result.sessions, [])

    # ── security: falsy project_id must never degrade to an unscoped read ────
    #
    # Defense-in-depth for the reviewer-confirmed cross-project leak: the
    # router-level guard is the primary defense (see
    # test_intent_node_cost_http_contract.py), but this service function
    # MUST also refuse a falsy project_id on its own -- any other transport
    # (CLI, MCP, a future caller) that skips the router entirely must not be
    # able to trigger the same unscoped-read-via-expand_family leak.

    async def test_get_intent_node_cost_rejects_empty_project_id(self) -> None:
        await declare_intent_node_sessions(NODE_ID, ["sess-1"], PROJECT_ID, self.ports)

        with self.assertRaises(ValueError):
            await get_intent_node_cost(NODE_ID, "", self.ports, expand_family=True)

    async def test_get_intent_node_cost_rejects_none_project_id(self) -> None:
        with self.assertRaises(ValueError):
            await get_intent_node_cost(NODE_ID, None, self.ports)  # type: ignore[arg-type]

    async def test_declare_intent_node_sessions_rejects_empty_project_id(self) -> None:
        with self.assertRaises(ValueError):
            await declare_intent_node_sessions(NODE_ID, ["sess-1"], "", self.ports)

        # No link row must have been written.
        result = await get_intent_node_cost(NODE_ID, PROJECT_ID, self.ports)
        self.assertEqual(result.totals.session_count, 0)


if __name__ == "__main__":
    unittest.main()
