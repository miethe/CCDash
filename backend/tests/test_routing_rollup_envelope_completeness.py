"""Envelope-completeness test (T6-003, R-P3 seam task) for the Proof -> Routing
Feedback Loop rollup's ENABLED response -- the structural counterpart to
T6-002's mapping-digest-parity seam task
(``test_routing_feedback_contract_parity.py``).

Where T6-002 defends the vendored mapping's byte-identity, this module
defends the **envelope's structural completeness** -- the actual join
contract the router's ``validateFeedbackJoin()`` depends on receiving. It
asserts every ENABLED response, on every transport (REST/MCP/CLI), carries
all 11 pinned envelope fields per key plus the three top-level coverage
counters -- PRD Sec.6.3's literal JSON example, cited verbatim below, never
re-derived or improvised (PRD Sec.11 AC-1):

  - Per-key (``keys[]`` entries): ``producer``, ``contract_id``,
    ``contract_version``, ``taxonomy_id``, ``taxonomy_version``,
    ``taxonomy_digest``, ``mapping_id``, ``mapping_version``,
    ``mapping_digest``, ``source_skill_name``, ``task_class``.
  - Top-level (once per response, never per key): ``mapped_count``,
    ``unclassified_count``, ``distinct_unmapped_skill_names``.

``producer``'s VALUE is additionally asserted equal to the frozen
``PRODUCER = "ccdash"`` constant exactly -- not merely asserted present, per
this task's explicit acceptance criterion.

This module extends ``test_routing_rollup_transports.py``'s (T5-004)
established three-transport plumbing -- ``_FakeMCP``/``_run_mcp_tool``/
``_normalize_mcp_envelope`` for MCP, ``TestClient`` + ``build_runtime_app``
for REST, ``CliRunner`` + ``cli_app`` for CLI -- but exercises the ENABLED
path with real, seeded ``routing_rollup`` rows rather than the disabled
short-circuit T5-004 already covers exclusively. All three transports read
through the identical shared coroutine
(``backend.routers._client_v1_routing_rollup._fetch_routing_rollup``), so
seeding once and fetching three times proves the real cross-transport
contract, not merely a DTO-shape identity assumed to propagate unverified
from one transport to the other two.

Project-resolution note
------------------------
No FastAPI dependency override is used here (unlike
``test_client_v1_routing_rollup.py``'s REST-only enabled test) -- MCP and CLI
have no DI-override mechanism to hook the same way REST does. The real
production workspace registry (``backend.project_manager.db_project_manager``)
is also unusable for test isolation: it is a **module-level singleton**
constructed once, at import time, against ``config.DB_PATH`` -- a constant
frozen when ``backend.config`` first loads, which a later
``patch.dict(os.environ, {"CCDASH_DB_PATH": ...})`` cannot retroactively
change (unlike ``backend/db/connection.py``'s ``get_connection()``, which
deliberately re-reads ``os.environ`` fresh on every call for exactly this
kind of test isolation -- see that module's own comment). Relying on it here
would silently resolve every transport against whatever DB path was live the
first time ANY test in this process touched project resolution, not this
module's own throwaway fixture DB.

Instead, this module builds one fresh, explicitly-seeded legacy
``ProjectManager`` (JSON-backed, never touches SQL) per test and patches
``backend.runtime_ports.db_project_manager`` -- the single shared fallback
``build_workspace_registry()``/``build_core_ports()`` resolve to in
production for ALL THREE transports (``backend/cli/runtime.py``,
``backend/mcp/bootstrap.py``, and ``backend/runtime/container.py`` all call
the identical ``backend.runtime_ports.build_core_ports``). Patching the name
inside ``runtime_ports``'s own module namespace -- not
``backend.project_manager.db_project_manager``, which importers already
copied into their own namespace at import time via ``from ... import
db_project_manager`` -- is what makes the patch visible to every one of the
three transports' calls into that shared function (``build_workspace_registry``
resolves the name ``db_project_manager`` fresh from its own module globals on
every call). The fresh manager registers and activates exactly one project
(``_PROJECT_ID``), matching the ``project_id`` every seeded ``routing_rollup``
row below carries, so REST (``AuthContext.synthesize_local(project_id=_PROJECT_ID)``),
MCP, and CLI (both ``project_id=None``, resolving via the active-project
fallback) all resolve to the identical project deterministically.

Run as a named module (full collection can hang -- see the PRD's repo-wide
pytest-collection caveat):
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_envelope_completeness.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest.mock import AsyncMock, patch

import aiosqlite
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from backend import config
from backend.adapters.auth.context import AuthContext
from backend.adapters.auth.dependency import get_auth_context
from backend.application.services.agent_queries.routing_feedback_contract import (
    CONTRACT_VERSION,
    MAPPING_VERSION,
    PRODUCER,
    TAXONOMY_VERSION,
)
from backend.application.services.agent_queries.routing_rollup import UNCLASSIFIED_TASK_CLASS
from backend.cli.main import app as cli_app
from backend.db.repositories.routing_rollup import ROUTING_ROLLUP_COLUMNS
from backend.db.sqlite_migrations import run_migrations
from backend.mcp import bootstrap as mcp_bootstrap
from backend.mcp.tools.routing import register_routing_tools
from backend.models import Project
from backend.project_manager import ProjectManager
from backend.runtime.bootstrap import build_runtime_app

_PROJECT_ID = "test-project-routing-rollup-envelope-completeness"

#: PRD Sec.6.3's literal per-key JSON example -- the 11 pinned join-envelope
#: fields, cited verbatim, never re-derived or improvised (AC-1).
PINNED_KEY_ENVELOPE_FIELDS: tuple[str, ...] = (
    "producer",
    "contract_id",
    "contract_version",
    "taxonomy_id",
    "taxonomy_version",
    "taxonomy_digest",
    "mapping_id",
    "mapping_version",
    "mapping_digest",
    "source_skill_name",
    "task_class",
)

#: PRD Sec.6.3's top-level envelope example -- the 3 FR-7 coverage counters,
#: carried once per response, never per key (AC-1).
TOP_LEVEL_COUNTER_FIELDS: tuple[str, ...] = (
    "mapped_count",
    "unclassified_count",
    "distinct_unmapped_skill_names",
)

#: DI-4e/D-b3 -- the two additive skill-dimension coverage counters. Kept
#: as a separate tuple from ``TOP_LEVEL_COUNTER_FIELDS`` (never merged into
#: it) since the two seed rows below use ``min_sample_size``-clearing
#: sample counts and asserting these alongside the FR-7 counters proves
#: the persisted-read path (``_client_v1_routing_rollup.py``) actually
#: reassembles them, not merely the live compute path.
SKILL_DIMENSION_COUNTER_FIELDS: tuple[str, ...] = (
    "skill_attributed_key_count",
    "skill_unattributed_key_count",
)


def _make_seed_row(**overrides: Any) -> dict[str, Any]:
    """A ``ROUTING_ROLLUP_COLUMNS``-shaped dict -- mirrors
    ``test_client_v1_routing_rollup.py``'s ``_make_row`` fixture exactly.
    """
    row: dict[str, Any] = {
        "project_id": _PROJECT_ID,
        "source_skill_name": "planning",
        "model": "claude-sonnet-5",
        "window_start": "2026-07-24T00:00:00+00:00",
        "window_end": "2026-07-31T00:00:00+00:00",
        "task_class": "orchestration",
        "provider": "anthropic",
        "sample_count": 12,
        "success_rate": None,
        "cost_index": 1.0,
        # DI-4e: this fixture was missing `cost_coverage_fraction` --
        # (v47's persisted column) which drifted out of sync with
        # ROUTING_ROLLUP_COLUMNS and failed this module's own
        # `assert set(row) == set(ROUTING_ROLLUP_COLUMNS)` shape check.
        # Fixed here as part of this task's fixture update (pre-existing
        # bug, not introduced by DI-4e's own changes).
        "cost_coverage_fraction": 1.0,
        "regression_rate": None,
        # DI-4c (v45): unambiguous-or-null tier + provenance + the
        # authoritative-fraction trust companion.
        "effort_tier": "high",
        "effort_tier_source": "codex_payload_effort",
        "authoritative_effort_fraction": 0.75,
        "confidence": 0.8,
        "eligible_for_adjustment": 1,
        "freshness_ts": "2026-07-31T00:00:00+00:00",
        "contract_version": CONTRACT_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "mapping_version": MAPPING_VERSION,
    }
    row.update(overrides)
    assert set(row) == set(ROUTING_ROLLUP_COLUMNS)
    return row


class _FakeMCP:
    """Minimal FastMCP stand-in -- verbatim clone of
    ``test_routing_rollup_transports.py``'s fixture; no live stdio transport
    is spun up for this unit-level parity check.
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
    MCP-side runtime container within the same event loop that created it --
    verbatim clone of ``test_routing_rollup_transports.py``'s helper.
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
    and CLI's flat JSON -- verbatim clone of
    ``test_routing_rollup_transports.py``'s helper.
    """
    data = dict(envelope["data"])
    data["generated_at"] = envelope["meta"].get("generated_at")
    return data


async def _bootstrap_schema(db_path: str) -> None:
    """Create every table (including ``routing_rollup``) against *db_path*
    directly, via a short-lived connection distinct from the process-wide
    singleton each transport's own bootstrap later opens. Closed before any
    transport touches the file, so there is no handle contention -- mirrors
    ``test_routing_rollup_sweep_job.py``'s ``run_migrations(self.db)`` call,
    just against a file path instead of ``:memory:`` so the schema is visible
    to the three independently-bootstrapped transport connections that read
    it afterward. (Project resolution itself never touches this file or any
    SQL table -- see module docstring's project-resolution note.)
    """
    db = await aiosqlite.connect(db_path)
    try:
        await run_migrations(db)
    finally:
        await db.close()


class TestRoutingRollupEnvelopeCompleteness(unittest.TestCase):
    """T6-003 / AC-1: every enabled response, on every transport, carries all
    11 pinned per-key fields plus the 3 top-level coverage counters.
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

        self._flag_patcher = patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True)
        self._flag_patcher.start()

        # Fresh, explicitly-seeded legacy ProjectManager -- see module
        # docstring's project-resolution note for why the real
        # db_project_manager singleton cannot be used for test isolation
        # here, and why patching backend.runtime_ports.db_project_manager
        # (rather than backend.project_manager.db_project_manager) is what
        # makes this visible to all three transports.
        self._projects_tmpdir = tempfile.TemporaryDirectory()
        manager = ProjectManager(Path(self._projects_tmpdir.name) / "projects.json")
        manager.add_project(
            Project(id=_PROJECT_ID, name="Routing Rollup Envelope Completeness", path=self._tmpdb.name)
        )
        manager.set_active_project(_PROJECT_ID)
        self._manager_patcher = patch("backend.runtime_ports.db_project_manager", manager)
        self._manager_patcher.start()

        asyncio.run(_bootstrap_schema(self._tmpdb.name))

        # Two seed rows -- one ordinary mapped key, one _unclassified key --
        # so the response exercises both FR-7 counter buckets, not just the
        # trivial single-row case.
        self._insert_seed_row(
            source_skill_name="planning",
            model="claude-sonnet-5",
            task_class="orchestration",
            provider="anthropic",
            sample_count=10,
        )
        self._insert_seed_row(
            source_skill_name="codex",
            model="gpt-5.6",
            task_class=UNCLASSIFIED_TASK_CLASS,
            provider="openai",
            sample_count=3,
            confidence=0.0,
            eligible_for_adjustment=0,
            freshness_ts="2026-07-31T01:00:00+00:00",
        )

    def tearDown(self) -> None:
        self._manager_patcher.stop()
        self._projects_tmpdir.cleanup()
        self._flag_patcher.stop()
        self._env_patcher.stop()
        try:
            os.unlink(self._tmpdb.name)
        except OSError:
            pass

    def _insert_seed_row(self, **overrides: Any) -> None:
        row = _make_seed_row(**overrides)
        columns_sql = ", ".join(ROUTING_ROLLUP_COLUMNS)
        placeholders_sql = ", ".join(["?"] * len(ROUTING_ROLLUP_COLUMNS))
        values = tuple(row[col] for col in ROUTING_ROLLUP_COLUMNS)

        conn = sqlite3.connect(self._tmpdb.name)
        try:
            conn.execute(
                f"INSERT INTO routing_rollup ({columns_sql}) VALUES ({placeholders_sql})",
                values,
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Transport fetch helpers -- REST/MCP/CLI, cloned from
    # test_routing_rollup_transports.py's own three legs, run against the
    # enabled path (no disabled-envelope short-circuit here: the flag is
    # patched True in setUp above).
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

    def _fetch_via_cli(self) -> dict[str, Any]:
        runner = CliRunner()
        result = runner.invoke(cli_app, ["routing", "rollup", "--json"])
        self.assertEqual(result.exit_code, 0, result.output)
        return json.loads(result.output)

    # ------------------------------------------------------------------
    # Envelope-completeness assertion helpers -- the load-bearing checks
    # this whole module exists to prove (AC-1).
    # ------------------------------------------------------------------

    def _assert_key_envelope_complete(self, key: dict[str, Any], *, transport: str) -> None:
        for field in PINNED_KEY_ENVELOPE_FIELDS:
            self.assertIn(
                field, key, f"{transport} key missing pinned envelope field {field!r}: {key}"
            )
        # Not merely present -- the producer's VALUE must equal the frozen
        # PRODUCER constant exactly, per T6-003's explicit acceptance
        # criterion ("not merely asserted present").
        self.assertEqual(
            key["producer"],
            PRODUCER,
            f"{transport} key's producer field must equal the frozen PRODUCER "
            f"constant ({PRODUCER!r}) exactly, got {key.get('producer')!r}",
        )

    def _assert_response_envelope_complete(self, data: dict[str, Any], *, transport: str) -> None:
        for field in TOP_LEVEL_COUNTER_FIELDS:
            self.assertIn(
                field, data, f"{transport} response missing top-level counter {field!r}: {data}"
            )
        for field in SKILL_DIMENSION_COUNTER_FIELDS:
            self.assertIn(
                field,
                data,
                f"{transport} response missing DI-4e skill-dimension counter {field!r}: {data}",
            )
        self.assertTrue(
            data.get("keys"),
            f"{transport} response has no keys -- seed-row fixture did not reach "
            f"this transport ({data})",
        )
        for key in data["keys"]:
            self._assert_key_envelope_complete(key, transport=transport)

    # ------------------------------------------------------------------
    # Parametrized three-transport assertion -- this task's primary
    # contribution to AC-1: proves the shape independently on REST, MCP, AND
    # CLI rather than asserting only one and assuming DTO-shape identity
    # guarantees the others.
    # ------------------------------------------------------------------

    def test_enabled_envelope_carries_all_pinned_fields_across_transports(self) -> None:
        rest_status, rest_body = self._fetch_via_rest()
        self.assertEqual(rest_status, 200, rest_body)

        mcp_envelope = _run_mcp_tool(project_id=None)
        mcp_data = _normalize_mcp_envelope(mcp_envelope)

        cli_data = self._fetch_via_cli()

        for transport, data in (
            ("REST", rest_body["data"]),
            ("MCP", mcp_data),
            ("CLI", cli_data),
        ):
            with self.subTest(transport=transport):
                self._assert_response_envelope_complete(data, transport=transport)

    # ------------------------------------------------------------------
    # DI-4e/D-b3: the skill-dimension counters reassembled from persisted
    # rows must reflect the SAME min_sample_size-clearing population the
    # compute-layer's own _skill_dimension_coverage uses -- proven with
    # concrete expected counts, not merely field presence.
    # ------------------------------------------------------------------

    def test_skill_dimension_counters_reflect_min_sample_size_population(self) -> None:
        # setUp seeds sample_count=10 (clears the default min_sample_size=5,
        # non-empty source_skill_name "planning" -> attributed) and
        # sample_count=3 (below threshold -> excluded from BOTH counters).
        rest_status, rest_body = self._fetch_via_rest()
        self.assertEqual(rest_status, 200, rest_body)

        mcp_data = _normalize_mcp_envelope(_run_mcp_tool(project_id=None))
        cli_data = self._fetch_via_cli()

        for transport, data in (
            ("REST", rest_body["data"]),
            ("MCP", mcp_data),
            ("CLI", cli_data),
        ):
            with self.subTest(transport=transport):
                self.assertEqual(data.get("skill_attributed_key_count"), 1, data)
                self.assertEqual(data.get("skill_unattributed_key_count"), 0, data)

    # ------------------------------------------------------------------
    # Load-bearing proof: a response with any one pinned field deliberately
    # stripped fails the build -- proves the assertion above catches a real
    # incomplete envelope, not just a well-formed one (T6-003's third
    # acceptance criterion).
    # ------------------------------------------------------------------

    def test_missing_any_single_pinned_field_fails_the_completeness_assertion(self) -> None:
        status, body = self._fetch_via_rest()
        self.assertEqual(status, 200, body)
        real_keys = body["data"]["keys"]
        self.assertTrue(real_keys, "fixture seeding failed -- no keys to strip a field from")
        real_key = real_keys[0]

        for missing_field in PINNED_KEY_ENVELOPE_FIELDS:
            stripped_key = dict(real_key)  # copy -- never mutate the real response
            del stripped_key[missing_field]
            with self.subTest(missing_field=missing_field):
                with self.assertRaises(
                    AssertionError,
                    msg=(
                        f"stripping {missing_field!r} did not fail the "
                        "envelope-completeness assertion -- it would be "
                        "vacuously true and could never catch a real "
                        "incomplete response, defeating this seam task's "
                        "purpose (AC-1)."
                    ),
                ):
                    self._assert_key_envelope_complete(stripped_key, transport="test-fixture")


if __name__ == "__main__":
    unittest.main()
