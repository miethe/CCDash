"""Disabled-state finalization, cross-transport reversibility, and top-level
version-field presence tests for the Proof -> Routing Feedback Loop rollup
(T6-006) -- PRD Sec.11's AC-4 (default-off disabled behavior), AC-7
(reversibility), and AC-8 (version-mismatch resilience).

This module deliberately does NOT re-derive ground already proven by earlier
tasks; it finalizes/re-confirms across the one dimension none of them
combined yet: REAL PERSISTED ROWS in the ``routing_rollup`` table, read
through ALL THREE transports (REST/MCP/CLI), while the
``CCDASH_ROUTING_FEEDBACK_ENABLED`` flag is flipped mid-test.

  - ``test_routing_rollup_transports.py`` (T5-004) proves the disabled
    envelope is byte-identical across transports, but with an EMPTY table --
    it never seeds a row, so it cannot prove the disabled short-circuit wins
    over a persisted row that is actually there.
  - ``test_routing_rollup_sweep_job.py`` (T4-001) proves flag-flip
    reversibility, but only at the WORKER/WRITE layer (``execute()``'s next
    tick performs zero writes) -- it never touches the READ transports.
  - ``test_routing_rollup_envelope_completeness.py`` (T6-003) proves the
    ENABLED envelope's per-key field completeness across transports, but
    never asserts the response-level ``contract_version``/
    ``taxonomy_version``/``mapping_version`` fields, and never touches the
    disabled shape at all.

This module closes those three gaps:

  1. **AC-4 finalization** (``TestDisabledShortCircuitsOverPersistedRows``,
     ``TestCapabilityAdvertisedIndependentOfEnabledFlag``): with real rows
     already sitting in ``routing_rollup`` (simulating residue from a prior
     enabled window), flipping the flag off must still short-circuit to the
     deterministic disabled envelope on every transport -- the persisted
     rows are never leaked, and REST is always a 200, never a 404.
     Capability advertisement (``"routing:feedback"`` in
     ``/api/v1/capabilities``) is independent of the flag's runtime value --
     a consumer sees the capability exists regardless of whether it happens
     to be enabled or disabled right now (AC-4's "predates this feature"
     vs. "supports it but finds it disabled" distinction).
  2. **AC-7 reversibility, read layer** (``TestReversibilityAcrossTransports``):
     one seeded fixture, flag ON -> flag OFF -> flag ON again, fetched via
     all three transports at each step. Disabling must produce the disabled
     envelope on the very next call (no partial state, no stale enabled rows
     served); re-enabling must immediately resume serving the SAME persisted
     rows with no backfill/migration step required of the read path.
  3. **AC-8 version-field presence** (``TestVersionFieldsPresentOnEveryResponse``):
     every response -- enabled AND disabled, on every transport -- carries
     the three top-level identity-version fields
     (``contract_version``/``taxonomy_version``/``mapping_version``) equal to
     the frozen ``routing_feedback_contract`` constants, never omitted or
     coerced.

Cache-collision note (process-restart modeling)
------------------------------------------------
``_fetch_routing_rollup`` is wrapped by ``@memoized_query(...)`` (TTL-bounded,
module-level, process-wide ``TTLCache``). AC-7's own propagation_contract
frames reversibility as "flipping the flag AND restarting the worker/API
process" -- a restart wipes that in-process cache entirely as a side effect
of starting a fresh process. This module models that restart faithfully by
calling ``cache.clear_cache()`` (the same test-suite-exposed reset helper
``test_agent_query_bypass_cache.py`` and a dozen other test files already
use) immediately after every flag flip, rather than relying on REST's
``bypass_cache`` query param alone -- MCP and CLI expose no such param, so
the only correct way to model "next call after a restart" for those two
transports is clearing the shared cache singleton, not passing a kwarg
neither transport's public surface accepts. ``setUp`` also clears the cache
proactively so no residue from an earlier test METHOD in this same process
(the repo-wide pytest-collection caveat means this file's classes all run
in one process even though cross-FILE runs are isolated) can leak into a
later assertion.

Run as a named module (full collection can hang -- see the PRD's repo-wide
pytest-collection caveat):
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_disabled_state.py -v
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
from backend.application.services.agent_queries import routing_feedback_contract
from backend.application.services.agent_queries.cache import clear_cache
from backend.cli.main import app as cli_app
from backend.db.repositories.routing_rollup import ROUTING_ROLLUP_COLUMNS
from backend.db.sqlite_migrations import run_migrations
from backend.mcp import bootstrap as mcp_bootstrap
from backend.mcp.tools.routing import register_routing_tools
from backend.models import Project
from backend.project_manager import ProjectManager
from backend.runtime.bootstrap import build_runtime_app

_PROJECT_ID = "test-project-routing-rollup-disabled-state"

#: The three top-level identity-version fields AC-8 pins on EVERY response,
#: enabled or disabled (PRD Sec.6.3's disabled-envelope example cites exactly
#: these three by name, distinct from the per-key envelope's 11 pinned
#: fields T6-003 already covers).
VERSION_FIELDS: tuple[str, ...] = ("contract_version", "taxonomy_version", "mapping_version")

#: Frozen expected values for the three version fields -- read from the same
#: ``routing_feedback_contract`` constants the production code assembles
#: every response from, never re-derived or hand-copied.
_EXPECTED_VERSIONS: dict[str, str] = {
    "contract_version": routing_feedback_contract.CONTRACT_VERSION,
    "taxonomy_version": routing_feedback_contract.TAXONOMY_VERSION,
    "mapping_version": routing_feedback_contract.MAPPING_VERSION,
}

#: The deterministic disabled envelope's expected field values -- verbatim
#: clone of ``test_routing_rollup_transports.py``'s ``_DISABLED_DTO_FIELDS``,
#: reproduced here (not imported) because this module intentionally does not
#: depend on that file's internals -- a future edit to one must not silently
#: change the other's fixture.
_DISABLED_DTO_FIELDS: dict[str, Any] = {
    "enabled": False,
    "generated_at": None,
    "mapped_count": 0,
    "unclassified_count": 0,
    "distinct_unmapped_skill_names": [],
    "keys": [],
}


# ---------------------------------------------------------------------------
# Shared transport-fetch scaffolding -- cloned from
# test_routing_rollup_envelope_completeness.py (T6-003), which itself cloned
# test_routing_rollup_transports.py's (T5-004) own helpers. Reproduced here
# rather than imported for the same file-independence reason as the disabled
# fixture above.
# ---------------------------------------------------------------------------


class _FakeMCP:
    """Minimal FastMCP stand-in -- no live stdio transport is spun up for
    this unit-level parity check."""

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self, *_args: Any, name: str | None = None, **_kwargs: Any):
        def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name or func.__name__] = func
            return func

        return _decorator


def _run_mcp_tool(**kwargs: Any) -> dict[str, Any]:
    """Register + invoke ``ccdash_routing_rollup`` directly, then close the
    MCP-side runtime container within the same event loop that created it."""
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
    and CLI's flat JSON."""
    data = dict(envelope["data"])
    data["generated_at"] = envelope["meta"].get("generated_at")
    return data


def _make_seed_row(**overrides: Any) -> dict[str, Any]:
    """A ``ROUTING_ROLLUP_COLUMNS``-shaped dict -- mirrors
    ``test_routing_rollup_envelope_completeness.py``'s ``_make_seed_row``
    exactly."""
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
        "regression_rate": None,
        "confidence": 0.8,
        "eligible_for_adjustment": 1,
        "freshness_ts": "2026-07-31T00:00:00+00:00",
        "contract_version": routing_feedback_contract.CONTRACT_VERSION,
        "taxonomy_version": routing_feedback_contract.TAXONOMY_VERSION,
        "mapping_version": routing_feedback_contract.MAPPING_VERSION,
    }
    row.update(overrides)
    assert set(row) == set(ROUTING_ROLLUP_COLUMNS)
    return row


async def _bootstrap_schema(db_path: str) -> None:
    """Create every table (including ``routing_rollup``) against *db_path*
    via a short-lived connection distinct from the process-wide singleton
    each transport's own bootstrap later opens."""
    db = await aiosqlite.connect(db_path)
    try:
        await run_migrations(db)
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Base fixture: fresh tmp DB, a single active project resolvable by all
# three transports, and (by default) TWO persisted routing_rollup rows --
# an ordinary mapped key plus an _unclassified key, so "persisted rows
# exist" is a real, non-trivial multi-key fixture rather than a single-row
# toy case.
# ---------------------------------------------------------------------------


class _RoutingRollupDisabledStateFixture(unittest.TestCase):
    def setUp(self) -> None:
        # Model a fresh process's cache state, independent of whatever any
        # earlier test METHOD in this same file/process may have left behind
        # (see module docstring's cache-collision note).
        clear_cache()

        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmpdb.close()

        self._env_patcher = patch.dict(
            os.environ,
            {"CCDASH_DB_PATH": self._tmpdb.name, "CCDASH_DB_BACKEND": "sqlite"},
        )
        self._env_patcher.start()

        asyncio.run(_bootstrap_schema(self._tmpdb.name))

        self._projects_tmpdir = tempfile.TemporaryDirectory()
        manager = ProjectManager(Path(self._projects_tmpdir.name) / "projects.json")
        manager.add_project(
            Project(id=_PROJECT_ID, name="Routing Rollup Disabled State", path=self._tmpdb.name)
        )
        manager.set_active_project(_PROJECT_ID)
        self._manager_patcher = patch("backend.runtime_ports.db_project_manager", manager)
        self._manager_patcher.start()

        # Two persisted rows -- an ordinary mapped key plus an _unclassified
        # key -- representing residue from a PRIOR enabled sweep window.
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
            task_class="_unclassified",
            provider="openai",
            sample_count=3,
            confidence=0.0,
            eligible_for_adjustment=0,
            freshness_ts="2026-07-31T01:00:00+00:00",
        )

    def tearDown(self) -> None:
        self._manager_patcher.stop()
        self._projects_tmpdir.cleanup()
        self._env_patcher.stop()
        try:
            os.unlink(self._tmpdb.name)
        except OSError:
            pass
        clear_cache()

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

    def _persisted_row_count(self) -> int:
        conn = sqlite3.connect(self._tmpdb.name)
        try:
            cur = conn.execute("SELECT COUNT(*) FROM routing_rollup")
            return int(cur.fetchone()[0])
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Transport fetch helpers -- byte-for-byte the same three legs as
    # test_routing_rollup_transports.py / test_routing_rollup_envelope_completeness.py.
    # ------------------------------------------------------------------

    def _fetch_via_rest(self, *, bypass_cache: bool = True) -> tuple[int, dict[str, Any]]:
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
                    "/api/v1/routing/rollup",
                    params={"bypass_cache": "true"} if bypass_cache else {},
                )
                return resp.status_code, resp.json()
        finally:
            app.dependency_overrides.clear()
            for p in reversed(patches):
                p.stop()

    def _fetch_via_mcp(self) -> dict[str, Any]:
        envelope = _run_mcp_tool(project_id=None)
        return _normalize_mcp_envelope(envelope)

    def _fetch_via_cli(self) -> dict[str, Any]:
        runner = CliRunner()
        result = runner.invoke(cli_app, ["routing", "rollup", "--json"])
        self.assertEqual(result.exit_code, 0, result.output)
        return json.loads(result.output)

    def _fetch_all_transports(self) -> dict[str, dict[str, Any]]:
        """Fetch via all three transports and return a label -> data map.
        Always REST-bypasses the cache (the one transport with a public
        bypass knob); MCP/CLI rely on whatever ``clear_cache()`` calls the
        caller already issued (see module docstring's cache-collision note)."""
        rest_status, rest_body = self._fetch_via_rest(bypass_cache=True)
        self.assertEqual(rest_status, 200, rest_body)
        return {
            "REST": rest_body["data"],
            "MCP": self._fetch_via_mcp(),
            "CLI": self._fetch_via_cli(),
        }


# ---------------------------------------------------------------------------
# AC-4 (finalization): the disabled short-circuit wins over ANY persisted
# rows sitting in the table, on every transport -- never a partial leak of
# stale enabled data, never a 404.
# ---------------------------------------------------------------------------


class TestDisabledShortCircuitsOverPersistedRows(_RoutingRollupDisabledStateFixture):
    def setUp(self) -> None:
        super().setUp()
        self._flag_patcher = patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", False)
        self._flag_patcher.start()

    def tearDown(self) -> None:
        self._flag_patcher.stop()
        super().tearDown()

    def test_persisted_rows_exist_but_every_transport_still_returns_the_disabled_envelope(self) -> None:
        # Sanity: the fixture really did persist rows -- a trivially-empty
        # table would make this test vacuous (it would "prove" the
        # short-circuit wins over nothing).
        self.assertEqual(self._persisted_row_count(), 2, "fixture seeding failed")

        results = self._fetch_all_transports()

        for transport, data in results.items():
            with self.subTest(transport=transport):
                for field, expected in _DISABLED_DTO_FIELDS.items():
                    self.assertEqual(
                        data[field],
                        expected,
                        f"{transport} data.{field} leaked stale/partial state "
                        f"despite CCDASH_ROUTING_FEEDBACK_ENABLED=False",
                    )

    def test_rest_disabled_response_is_a_200_never_a_404(self) -> None:
        status, body = self._fetch_via_rest(bypass_cache=True)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["data"]["enabled"], False)


# ---------------------------------------------------------------------------
# AC-4 (supplement): capability advertisement is independent of the flag's
# CURRENT runtime value -- a consumer sees "routing:feedback" exists whether
# the feature happens to be on or off right now. Only an OLDER server that
# predates the feature entirely omits the string.
# ---------------------------------------------------------------------------


class TestCapabilityAdvertisedIndependentOfEnabledFlag(unittest.TestCase):
    def _capabilities(self) -> list[str]:
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
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/v1/capabilities")
                self.assertEqual(resp.status_code, 200, resp.text)
                return resp.json()["data"]["capabilities"]
        finally:
            for p in reversed(patches):
                p.stop()

    def test_capability_present_when_flag_enabled(self) -> None:
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True):
            self.assertIn(routing_feedback_contract.CAPABILITY_STRING, self._capabilities())

    def test_capability_present_when_flag_disabled(self) -> None:
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", False):
            self.assertIn(routing_feedback_contract.CAPABILITY_STRING, self._capabilities())

    def test_capability_string_is_the_frozen_constant(self) -> None:
        self.assertEqual(routing_feedback_contract.CAPABILITY_STRING, "routing:feedback")


# ---------------------------------------------------------------------------
# AC-7: reversibility, read layer. ON -> OFF -> ON again, fetched via all
# three transports at every step. See module docstring's cache-collision
# note for why clear_cache() (not REST-only bypass_cache) is the correct way
# to model "the very next call after a restart" for MCP/CLI too.
# ---------------------------------------------------------------------------


class TestReversibilityAcrossTransports(_RoutingRollupDisabledStateFixture):
    def test_flag_flip_off_then_on_round_trips_cleanly_across_all_transports(self) -> None:
        # ── Step 1: flag ON -- every transport must serve the real,
        # already-persisted rows. ──────────────────────────────────────────
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True):
            clear_cache()
            enabled_results = self._fetch_all_transports()

        for transport, data in enabled_results.items():
            with self.subTest(step="enabled", transport=transport):
                self.assertTrue(data["enabled"])
                self.assertEqual(len(data["keys"]), 2, f"{transport} did not serve the persisted rows")

        enabled_key_sets = {
            transport: {(k["source_skill_name"], k["model"]) for k in data["keys"]}
            for transport, data in enabled_results.items()
        }
        self.assertEqual(
            enabled_key_sets["REST"], {("planning", "claude-sonnet-5"), ("codex", "gpt-5.6")}
        )
        # All three transports agree on which keys are being served.
        self.assertEqual(enabled_key_sets["REST"], enabled_key_sets["MCP"])
        self.assertEqual(enabled_key_sets["MCP"], enabled_key_sets["CLI"])

        # ── Step 2: flip OFF (+ restart-equivalent cache clear) -- the VERY
        # NEXT call on every transport must return the disabled envelope,
        # despite the rows still physically sitting in the table (proven by
        # _persisted_row_count() below) -- no partial state, no stale
        # enabled rows served. ──────────────────────────────────────────────
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", False):
            clear_cache()
            disabled_results = self._fetch_all_transports()

        self.assertEqual(
            self._persisted_row_count(), 2, "disabling must never delete/mutate persisted rows"
        )
        for transport, data in disabled_results.items():
            with self.subTest(step="disabled", transport=transport):
                for field, expected in _DISABLED_DTO_FIELDS.items():
                    self.assertEqual(data[field], expected, f"{transport} data.{field}")

        # ── Step 3: flip back ON (+ restart-equivalent cache clear) --
        # re-enabling must immediately resume serving the SAME persisted
        # rows already in the table -- no backfill/migration required of
        # the read path. ─────────────────────────────────────────────────
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True):
            clear_cache()
            re_enabled_results = self._fetch_all_transports()

        for transport, data in re_enabled_results.items():
            with self.subTest(step="re-enabled", transport=transport):
                self.assertTrue(data["enabled"])
                re_enabled_keys = {(k["source_skill_name"], k["model"]) for k in data["keys"]}
                self.assertEqual(
                    re_enabled_keys,
                    enabled_key_sets[transport],
                    f"{transport} did not resume serving the exact same persisted rows "
                    "after re-enabling -- reversibility must never require a backfill/migration",
                )

    def test_repeated_disable_re_enable_cycles_never_lose_or_duplicate_persisted_rows(self) -> None:
        """A second flip cycle, independent of the first test's assertions,
        proves the round trip is not a one-shot fluke -- the persisted row
        count must stay exactly 2 through every phase."""
        baseline_count = self._persisted_row_count()
        self.assertEqual(baseline_count, 2)

        for _ in range(2):
            with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", False):
                clear_cache()
                self._fetch_all_transports()
            self.assertEqual(self._persisted_row_count(), baseline_count)

            with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True):
                clear_cache()
                results = self._fetch_all_transports()
            self.assertEqual(self._persisted_row_count(), baseline_count)
            for transport, data in results.items():
                with self.subTest(transport=transport):
                    self.assertEqual(len(data["keys"]), baseline_count)


# ---------------------------------------------------------------------------
# AC-8: every response -- enabled AND disabled, on every transport -- carries
# the three top-level identity-version fields, equal to the frozen contract
# constants.
# ---------------------------------------------------------------------------


class TestVersionFieldsPresentOnEveryResponse(_RoutingRollupDisabledStateFixture):
    def _assert_version_fields(self, data: dict[str, Any], *, transport: str, state: str) -> None:
        for field in VERSION_FIELDS:
            self.assertIn(
                field, data, f"{transport} ({state}) response missing top-level {field!r}: {data}"
            )
            self.assertEqual(
                data[field],
                _EXPECTED_VERSIONS[field],
                f"{transport} ({state}) {field} does not equal the frozen contract constant "
                f"({_EXPECTED_VERSIONS[field]!r}), got {data[field]!r} -- CCDash must never "
                "silently upgrade/downgrade its emitted version fields",
            )

    def test_disabled_envelope_carries_version_fields_across_transports(self) -> None:
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", False):
            clear_cache()
            results = self._fetch_all_transports()

        for transport, data in results.items():
            with self.subTest(transport=transport):
                self.assertFalse(data["enabled"])
                self._assert_version_fields(data, transport=transport, state="disabled")

    def test_enabled_envelope_carries_version_fields_across_transports(self) -> None:
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True):
            clear_cache()
            results = self._fetch_all_transports()

        for transport, data in results.items():
            with self.subTest(transport=transport):
                self.assertTrue(data["enabled"])
                self._assert_version_fields(data, transport=transport, state="enabled")

    def test_version_fields_present_regardless_of_whether_response_has_any_keys(self) -> None:
        """Response-level version fields are NOT a byproduct of having at
        least one key -- assert them on the disabled shape (zero keys) AND
        confirm they are the exact same values as the enabled shape (which
        does have keys), proving they are response-level constants, never
        derived from (and therefore never absent without) the keys array."""
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", False):
            clear_cache()
            disabled_data = self._fetch_via_rest(bypass_cache=True)[1]["data"]
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True):
            clear_cache()
            enabled_data = self._fetch_via_rest(bypass_cache=True)[1]["data"]

        self.assertEqual(disabled_data["keys"], [])
        self.assertGreater(len(enabled_data["keys"]), 0)
        for field in VERSION_FIELDS:
            self.assertEqual(disabled_data[field], enabled_data[field])

    def test_missing_any_single_version_field_fails_the_presence_assertion(self) -> None:
        """Load-bearing proof: a response with any one version field
        deliberately stripped fails the build -- proves the assertion above
        catches a real incomplete envelope, not just a well-formed one
        (mirrors test_routing_rollup_envelope_completeness.py's own
        stripped-field proof pattern for AC-1)."""
        with patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True):
            clear_cache()
            status, body = self._fetch_via_rest(bypass_cache=True)
        self.assertEqual(status, 200, body)
        real_data = body["data"]

        for missing_field in VERSION_FIELDS:
            stripped = dict(real_data)  # copy -- never mutate the real response
            del stripped[missing_field]
            with self.subTest(missing_field=missing_field):
                with self.assertRaises(
                    AssertionError,
                    msg=(
                        f"stripping {missing_field!r} did not fail the version-field "
                        "presence assertion -- it would be vacuously true and could "
                        "never catch a real AC-8 violation."
                    ),
                ):
                    self._assert_version_fields(stripped, transport="test-fixture", state="stripped")


if __name__ == "__main__":
    unittest.main()
