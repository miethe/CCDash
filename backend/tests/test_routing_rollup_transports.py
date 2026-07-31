"""Cross-transport parity for the routing-feedback rollup (T5-004).

Confirms REST (``GET /api/v1/routing/rollup``), MCP (``ccdash_routing_rollup``),
and CLI (``ccdash routing rollup``) all serialize the exact same
``RoutingRollupResponseDTO`` (Phase 3's frozen contract, ``backend/
application/services/agent_queries/models.py``) with zero per-transport
reshaping, and that all three return a **byte-identical disabled envelope**
when ``CCDASH_ROUTING_FEEDBACK_ENABLED=false`` -- ``enabled: false``, an
empty ``keys[]``, zero counts across every count field, and (critically for
REST, per AC-4) an HTTP 200 response, never a 404. A disabled feature is a
normal contract state, not a missing-route error.

Envelope-shape note
--------------------
The three transports intentionally wrap the shared DTO in different outer
envelopes (REST: ``{status, data, meta}`` via ``ClientV1Envelope``; MCP:
``{status, data, meta}`` via ``build_envelope`` -- which moves
``generated_at`` out of ``data`` and into ``meta`` per its documented
``META_FIELDS`` set; CLI ``--json``: the flat DTO with no wrapper at all).
This is expected, already-shipped behavior for every other three-transport
trio in this repo (see ``aar_reviews``) -- not a defect. This test therefore
normalizes each transport's response back down to the DTO level (re-merging
MCP's ``meta.generated_at`` into its ``data`` dict) before asserting
byte-identical equality, per the phase plan's own guidance: "the shape is
Phase 3's contract, this task only proves transport parity against it."

MCP's top-level envelope ``status`` field is a KNOWN, already-documented
drift (T5-002 Finding) -- ``RoutingRollupResponseDTO`` defines no ``status``
field, so ``build_envelope`` always reports ``"error"`` for this DTO, even on
a perfectly healthy disabled response. This test does not assert on that
field for exactly that reason; it asserts on ``data.enabled``/``data.keys``/
the count fields instead, per the phase plan's Findings section.

Event-loop isolation note
--------------------------
``aiosqlite.Connection`` is bound to the event loop that created it.
``backend.db.connection.get_connection()`` is a **process-wide singleton**,
and each transport's bootstrap path (FastAPI lifespan for REST,
``backend.mcp.bootstrap.bootstrap_mcp`` for MCP, ``backend.cli.runtime.
bootstrap_cli`` for CLI) creates its own runtime container against whatever
connection the singleton currently holds. All three bootstraps already
close and clear that singleton on their own teardown path (``RuntimeContainer
.shutdown``, ``shutdown_mcp``, ``shutdown_cli`` -- the latter two run inside
``execute_query``'s own ``finally``), so running the three legs strictly in
sequence -- each one fully entering *and exiting* before the next begins --
guarantees every leg gets a fresh connection bound to its own event loop,
with zero manual singleton surgery required in this test.

Run as a named module:
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_transports.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from typing import Any, Callable
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from backend import config
from backend.adapters.auth.context import AuthContext
from backend.adapters.auth.dependency import get_auth_context
from backend.cli.main import app as cli_app
from backend.mcp import bootstrap as mcp_bootstrap
from backend.mcp.tools.routing import register_routing_tools
from backend.runtime.bootstrap import build_runtime_app

_PROJECT_ID = "test-project-routing-rollup-transports"

# The five AC-4 fields every disabled envelope must agree on, verbatim, per
# Phase 3's ``_disabled_envelope()`` construction (cited, not re-derived --
# see this file's module docstring).
_DISABLED_DTO_FIELDS: dict[str, Any] = {
    "enabled": False,
    "generated_at": None,
    "mapped_count": 0,
    "unclassified_count": 0,
    "distinct_unmapped_skill_names": [],
    "keys": [],
}


class _FakeMCP:
    """Minimal FastMCP stand-in that only captures the registered tool
    callable -- no live stdio transport, per T5-004's explicit guidance
    ("do not spin up a live stdio MCP transport for a unit-level parity
    check").
    """

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self, *_args: Any, name: str | None = None, **_kwargs: Any):
        def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name or func.__name__] = func
            return func

        return _decorator


def _run_mcp_tool(**kwargs: Any) -> dict[str, Any]:
    """Register + invoke ``ccdash_routing_rollup`` directly, then close the
    MCP-side runtime container within the same event loop that created it
    (mirrors what a real stdio-server lifecycle would eventually do, just
    synchronously and immediately instead of at process shutdown).
    """
    fake_mcp = _FakeMCP()
    register_routing_tools(fake_mcp)
    tool_fn = fake_mcp.tools["ccdash_routing_rollup"]

    async def _invoke() -> dict[str, Any]:
        try:
            return await tool_fn(**kwargs)
        finally:
            await mcp_bootstrap.shutdown_mcp()

    return asyncio.run(_invoke())


def _normalize_mcp_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Re-merge ``build_envelope``'s ``meta.generated_at`` back into the data
    dict so MCP's DTO-level payload is directly comparable to REST's ``data``
    and CLI's flat JSON (see module docstring's "Envelope-shape note").
    """
    data = dict(envelope["data"])
    data["generated_at"] = envelope["meta"].get("generated_at")
    return data


class TestRoutingRollupTransportParity(unittest.TestCase):
    """AC-4 (partial, finalized in Phase 6): REST/MCP/CLI byte-identical
    disabled envelopes when ``CCDASH_ROUTING_FEEDBACK_ENABLED=false``.
    """

    def setUp(self) -> None:
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmpdb.close()

        self._env_patcher = patch.dict(
            os.environ,
            {
                "CCDASH_DB_PATH": self._tmpdb.name,
                "CCDASH_DB_BACKEND": "sqlite",
            },
        )
        self._env_patcher.start()

        self._flag_patcher = patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", False)
        self._flag_patcher.start()

    def tearDown(self) -> None:
        self._flag_patcher.stop()
        self._env_patcher.stop()
        try:
            os.unlink(self._tmpdb.name)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # REST leg
    # ------------------------------------------------------------------

    def _fetch_via_rest(self) -> tuple[int, dict[str, Any]]:
        app = build_runtime_app("test")
        patches = [
            patch("backend.runtime.container.initialize_observability"),
            patch("backend.runtime.container.shutdown_observability"),
            patch(
                "backend.adapters.jobs.runtime.file_watcher.start",
                new_callable=lambda: lambda: AsyncMock(),
            ),
            patch(
                "backend.adapters.jobs.runtime.file_watcher.stop",
                new_callable=lambda: lambda: AsyncMock(),
            ),
        ]
        for p in patches:
            p.start()
        app.dependency_overrides[get_auth_context] = lambda: AuthContext.synthesize_local(
            project_id=_PROJECT_ID
        )
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/api/v1/routing/rollup", params={"bypass_cache": "true"}
                )
                return resp.status_code, resp.json()
        finally:
            app.dependency_overrides.clear()
            for p in reversed(patches):
                p.stop()

    def test_rest_returns_200_disabled_envelope(self) -> None:
        status_code, body = self._fetch_via_rest()

        self.assertEqual(status_code, 200, body)
        for field, expected in _DISABLED_DTO_FIELDS.items():
            self.assertEqual(body["data"][field], expected, f"REST data.{field}")

    # ------------------------------------------------------------------
    # MCP leg
    # ------------------------------------------------------------------

    def test_mcp_returns_disabled_envelope(self) -> None:
        envelope = _run_mcp_tool(project_id=None)
        data = _normalize_mcp_envelope(envelope)

        for field, expected in _DISABLED_DTO_FIELDS.items():
            self.assertEqual(data[field], expected, f"MCP data.{field}")

    # ------------------------------------------------------------------
    # CLI leg
    # ------------------------------------------------------------------

    def _fetch_via_cli(self) -> dict[str, Any]:
        runner = CliRunner()
        result = runner.invoke(cli_app, ["routing", "rollup", "--json"])
        self.assertEqual(result.exit_code, 0, result.output)
        return json.loads(result.output)

    def test_cli_returns_disabled_envelope(self) -> None:
        data = self._fetch_via_cli()

        for field, expected in _DISABLED_DTO_FIELDS.items():
            self.assertEqual(data[field], expected, f"CLI {field}")

    # ------------------------------------------------------------------
    # Cross-transport byte-identical assertion -- this task's primary
    # contribution to AC-4 (partial; finalized in Phase 6).
    # ------------------------------------------------------------------

    def test_all_three_transports_are_byte_identical_when_disabled(self) -> None:
        rest_status, rest_body = self._fetch_via_rest()
        rest_data = rest_body["data"]

        mcp_envelope = _run_mcp_tool(project_id=None)
        mcp_data = _normalize_mcp_envelope(mcp_envelope)

        cli_data = self._fetch_via_cli()

        # AC-4: REST is a normal 200, never a 404, for the disabled state.
        self.assertEqual(rest_status, 200, rest_body)

        for label, data in (("REST", rest_data), ("MCP", mcp_data), ("CLI", cli_data)):
            for field, expected in _DISABLED_DTO_FIELDS.items():
                self.assertEqual(data[field], expected, f"{label} data.{field}")

        # Byte-identical: normalize to the same key order and diff as strings
        # so any future per-transport field drift fails loudly and precisely.
        rest_json = json.dumps(rest_data, sort_keys=True)
        mcp_json = json.dumps(mcp_data, sort_keys=True)
        cli_json = json.dumps(cli_data, sort_keys=True)

        self.assertEqual(rest_json, mcp_json, "REST and MCP disabled envelopes diverged")
        self.assertEqual(mcp_json, cli_json, "MCP and CLI disabled envelopes diverged")
        self.assertEqual(rest_json, cli_json, "REST and CLI disabled envelopes diverged")


if __name__ == "__main__":
    unittest.main()
