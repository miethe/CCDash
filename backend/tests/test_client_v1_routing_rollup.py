"""Enabled+seeded-rows reassembly coverage for ``_client_v1_routing_rollup.py``.

Closes a review gap on Phase 5 (Transport Surfaces): T5-001's acceptance
criteria claimed the enabled/seeded-rows path was "verified via manual
pytest-harness round trip", but no such round trip was ever committed as an
automated test -- ``test_routing_rollup_transports.py`` (T5-004) only covers
the ``CCDASH_ROUTING_FEEDBACK_ENABLED=false`` disabled-envelope path across
transports. This module is the durable regression protection for the
**enabled** path's FR-7 counter-resummation logic
(``_build_response_from_rows``/``_row_to_key_dto``), which the
``routing_rollup`` table does not persist itself (see both functions'
docstrings in ``backend/routers/_client_v1_routing_rollup.py``).

Two layers of coverage:

1. **Pure-function unit tests** (no DB, no app) directly against
   ``_row_to_key_dto`` and ``_build_response_from_rows`` -- the exact two
   functions named in the review finding. Fast and precisely targeted at the
   reassembly arithmetic: mapped/unclassified counter partitioning,
   ``distinct_unmapped_skill_names`` dedup+sort, ``generated_at`` = max
   ``freshness_ts``, per-row version-field verbatim-vs-fallback behavior, and
   the nullable-metric-passthrough vs metric-default coercions.
2. **End-to-end REST round trip** with real persisted rows seeded into a
   throwaway SQLite file and ``CCDASH_ROUTING_FEEDBACK_ENABLED=true`` --
   proves the full request path (repository read -> reassembly -> envelope)
   the disabled-only transports test never exercised. Setup mirrors
   ``test_client_v1_aar_review.py`` (stub ``WorkspaceRegistry`` override +
   raw-``sqlite3`` row seeding against the same file the async app reads).

Run as a named module:
    backend/.venv/bin/python -m pytest backend/tests/test_client_v1_routing_rollup.py -v
"""
from __future__ import annotations

import dataclasses
import os
import sqlite3
import tempfile
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend import config
from backend.adapters.auth.context import AuthContext
from backend.adapters.auth.dependency import get_auth_context
from backend.application.context import (
    Principal,
    ProjectScope,
    RequestContext,
    TraceContext,
    WorkspaceScope,
)
from backend.application.services.agent_queries.routing_feedback_contract import (
    CONTRACT_ID,
    CONTRACT_VERSION,
    MAPPING_DIGEST,
    MAPPING_ID,
    MAPPING_VERSION,
    PRODUCER,
    TAXONOMY_DIGEST,
    TAXONOMY_ID,
    TAXONOMY_VERSION,
)
from backend.application.services.agent_queries.routing_rollup import UNCLASSIFIED_TASK_CLASS
from backend.db.repositories.routing_rollup import ROUTING_ROLLUP_COLUMNS
from backend.models import Project
from backend.request_scope import get_core_ports, get_request_context
from backend.routers._client_v1_routing_rollup import (
    _build_response_from_rows,
    _row_to_key_dto,
)
from backend.runtime.bootstrap import build_runtime_app

_PROJECT_ID = "test-project-routing-rollup-reassembly"


def _make_row(**overrides: Any) -> dict[str, Any]:
    """Return a ``ROUTING_ROLLUP_COLUMNS``-shaped dict -- the exact row shape
    ``_row_to_key_dto``/``_build_response_from_rows`` consume, mirroring
    ``test_routing_rollup_repo.py``'s ``_make_row`` fixture.
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
        "cost_index": 0.42,
        "cost_coverage_fraction": 0.94,
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


# ── Part 1: pure-function unit tests -- no DB, no app ──────────────────────


class RowToKeyDtoTests(unittest.TestCase):
    """``_row_to_key_dto``: per-row deserialisation into ``RoutingRollupKeyDTO``."""

    def test_contract_identity_fields_always_from_frozen_constants(self) -> None:
        dto = _row_to_key_dto(_make_row())
        self.assertEqual(dto.producer, PRODUCER)
        self.assertEqual(dto.contract_id, CONTRACT_ID)
        self.assertEqual(dto.taxonomy_id, TAXONOMY_ID)
        self.assertEqual(dto.taxonomy_digest, TAXONOMY_DIGEST)
        self.assertEqual(dto.mapping_id, MAPPING_ID)
        self.assertEqual(dto.mapping_digest, MAPPING_DIGEST)

    def test_per_row_version_fields_read_verbatim_when_present(self) -> None:
        dto = _row_to_key_dto(
            _make_row(contract_version="9.9.9", taxonomy_version="8.8.8", mapping_version="7.7.7")
        )
        self.assertEqual(dto.contract_version, "9.9.9")
        self.assertEqual(dto.taxonomy_version, "8.8.8")
        self.assertEqual(dto.mapping_version, "7.7.7")

    def test_empty_version_fields_fall_back_to_current_constants(self) -> None:
        dto = _row_to_key_dto(
            _make_row(contract_version="", taxonomy_version="", mapping_version="")
        )
        self.assertEqual(dto.contract_version, CONTRACT_VERSION)
        self.assertEqual(dto.taxonomy_version, TAXONOMY_VERSION)
        self.assertEqual(dto.mapping_version, MAPPING_VERSION)

    def test_identity_fields_mapped_verbatim(self) -> None:
        dto = _row_to_key_dto(
            _make_row(
                source_skill_name="release",
                task_class="mode_d",
                model="claude-opus-5",
                provider="anthropic",
                sample_count=7,
            )
        )
        self.assertEqual(dto.source_skill_name, "release")
        self.assertEqual(dto.task_class, "mode_d")
        self.assertEqual(dto.model, "claude-opus-5")
        self.assertEqual(dto.provider, "anthropic")
        self.assertEqual(dto.sample_count, 7)

    def test_nullable_metrics_pass_through_none_unchanged(self) -> None:
        dto = _row_to_key_dto(_make_row(success_rate=None, regression_rate=None))
        self.assertIsNone(dto.success_rate)
        self.assertIsNone(dto.regression_rate)

    def test_nullable_metrics_preserve_real_values(self) -> None:
        dto = _row_to_key_dto(_make_row(success_rate=0.91, regression_rate=0.03))
        self.assertEqual(dto.success_rate, 0.91)
        self.assertEqual(dto.regression_rate, 0.03)

    def test_success_rate_withheld_for_stale_provider_even_with_a_persisted_value(self) -> None:
        """The D-b4 gate must apply on this READ path too -- a persisted row
        carrying a real success_rate for a provider named in
        CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS must still be
        served as None. This is the backstop that makes "not served through
        REST/MCP/CLI" true regardless of what already landed in the column.

        Driven through `config` because the default is now EMPTY (the backfill
        landed and D-b4 re-verified clean at 89.3% informative, 2026-08-10).
        The mechanism is what matters here, not which provider happens to be
        listed today."""
        with patch.object(
            config, "CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS", ("openai",)
        ):
            dto = _row_to_key_dto(_make_row(provider="OpenAI", success_rate=0.99))
        self.assertIsNone(dto.success_rate)

    def test_success_rate_gate_normalizes_the_row_side_casing(self) -> None:
        """The persisted `provider` is whatever `derive_model_identity()` wrote
        ("OpenAI"), while configured entries are lowercase -- so the read path
        must lowercase the ROW side or a mixed-case provider escapes the gate.

        Asymmetric on purpose: the gate lowercases the row and trusts the
        config side to already be lowercase, which
        `test_env_csv_lower_normalizes_configured_entries` below pins. Note the
        sharp edge that follows from `_env_csv_lower`'s documented "falls back
        to *default* verbatim": a mixed-case tuple hardcoded as the DEFAULT in
        config.py would not be normalized and would silently not match. Keep
        any future default lowercase."""
        with patch.object(
            config, "CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS", ("openai",)
        ):
            dto = _row_to_key_dto(_make_row(provider="OpenAI", success_rate=0.99))
        self.assertIsNone(dto.success_rate)

    def test_env_csv_lower_normalizes_configured_entries(self) -> None:
        """The invariant the gate's one-sided comparison rests on: entries
        supplied through the environment are lowercased at load time, so the
        read path only has to normalize the row side."""
        with patch.dict(
            os.environ,
            {"CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS": "OpenAI, ANTHROPIC "},
        ):
            parsed = config._env_csv_lower(
                "CCDASH_ROUTING_FEEDBACK_SUCCESS_RATE_STALE_PROVIDERS", ()
            )
        self.assertEqual(parsed, ("openai", "anthropic"))

    def test_persisted_success_rate_is_served_for_that_provider_by_default(self) -> None:
        """The other side: with the default empty, the row the HALT gate used
        to withhold is now served with its real persisted value. Two-sided
        with the test above so a gate stuck permanently ON fails one of them."""
        dto = _row_to_key_dto(_make_row(provider="OpenAI", success_rate=0.99))
        self.assertEqual(dto.success_rate, 0.99)

    def test_success_rate_preserved_for_non_gated_provider(self) -> None:
        """Confirms the gate is provider-scoped, not a blanket suppression."""
        dto = _row_to_key_dto(_make_row(provider="anthropic", success_rate=0.91))
        self.assertEqual(dto.success_rate, 0.91)

    def test_cost_index_null_passes_through_unchanged(self) -> None:
        """DI-4a: a persisted NULL cost_index (a zero-coverage key,
        D-a2) must never be fabricated into a baseline -- the same
        null-over-fabrication principle already honored for
        success_rate/regression_rate below."""
        self.assertIsNone(_row_to_key_dto(_make_row(cost_index=None)).cost_index)

    def test_cost_index_preserves_real_value(self) -> None:
        self.assertEqual(_row_to_key_dto(_make_row(cost_index=0.13)).cost_index, 0.13)

    def test_cost_coverage_fraction_null_passes_through_unchanged(self) -> None:
        """v47: a persisted NULL cost_coverage_fraction (a row written before
        this column existed, or never re-swept since) must never be coerced
        into a fabricated 0.0 -- the same null-over-fabrication principle
        already honored for cost_index above."""
        self.assertIsNone(_row_to_key_dto(_make_row(cost_coverage_fraction=None)).cost_coverage_fraction)

    def test_cost_coverage_fraction_preserves_real_partial_value(self) -> None:
        """v47: a persisted PARTIAL-coverage key (2 of 50 sessions carried
        cost attribution) must round-trip through the client_v1 read path
        with its real fraction, not a fabricated/rounded value."""
        dto = _row_to_key_dto(_make_row(cost_coverage_fraction=2 / 50))
        self.assertAlmostEqual(dto.cost_coverage_fraction, 2 / 50)

    def test_cost_coverage_fraction_preserves_genuine_zero(self) -> None:
        """A genuinely computed zero-coverage key (0.0, not NULL) must still
        read back as a real 0.0, distinguishable from the None case above."""
        dto = _row_to_key_dto(_make_row(cost_coverage_fraction=0.0))
        self.assertEqual(dto.cost_coverage_fraction, 0.0)

    def test_confidence_defaults_to_zero_when_none(self) -> None:
        self.assertEqual(_row_to_key_dto(_make_row(confidence=None)).confidence, 0.0)

    def test_eligible_for_adjustment_bool_coercion(self) -> None:
        self.assertTrue(_row_to_key_dto(_make_row(eligible_for_adjustment=1)).eligible_for_adjustment)
        self.assertFalse(_row_to_key_dto(_make_row(eligible_for_adjustment=0)).eligible_for_adjustment)

    def test_sample_count_falsy_defaults_to_zero(self) -> None:
        self.assertEqual(_row_to_key_dto(_make_row(sample_count=None)).sample_count, 0)


class BuildResponseFromRowsTests(unittest.TestCase):
    """``_build_response_from_rows``: FR-7 counter re-summation over already-
    persisted rows -- the response-level counters ``routing_rollup`` does not
    persist itself (they are project-wide totals, not per-key)."""

    def test_empty_rows_returns_empty_enabled_response(self) -> None:
        response = _build_response_from_rows([])
        self.assertTrue(response.enabled)
        self.assertIsNone(response.generated_at)
        self.assertEqual(response.mapped_count, 0)
        self.assertEqual(response.unclassified_count, 0)
        self.assertEqual(response.distinct_unmapped_skill_names, [])
        self.assertEqual(response.keys, [])

    def test_all_mapped_rows_sum_into_mapped_count_only(self) -> None:
        rows = [
            _make_row(source_skill_name="planning", task_class="orchestration", sample_count=10),
            _make_row(source_skill_name="dev-execution", model="claude-opus-5", task_class="implementation", sample_count=5),
        ]
        response = _build_response_from_rows(rows)
        self.assertEqual(response.mapped_count, 15)
        self.assertEqual(response.unclassified_count, 0)
        self.assertEqual(response.distinct_unmapped_skill_names, [])
        self.assertEqual(len(response.keys), 2)

    def test_unclassified_rows_sum_into_unclassified_count_and_skill_names(self) -> None:
        rows = [
            _make_row(source_skill_name="codex", model="gpt-5.6", task_class=UNCLASSIFIED_TASK_CLASS, sample_count=3),
            _make_row(source_skill_name="claude-api", model="claude-opus-5", task_class=UNCLASSIFIED_TASK_CLASS, sample_count=4),
        ]
        response = _build_response_from_rows(rows)
        self.assertEqual(response.mapped_count, 0)
        self.assertEqual(response.unclassified_count, 7)
        self.assertEqual(response.distinct_unmapped_skill_names, ["claude-api", "codex"])

    def test_mixed_mapped_and_unclassified_rows_partition_correctly(self) -> None:
        rows = [
            _make_row(source_skill_name="planning", task_class="orchestration", sample_count=10),
            _make_row(source_skill_name="codex", model="gpt-5.6", task_class=UNCLASSIFIED_TASK_CLASS, sample_count=3),
        ]
        response = _build_response_from_rows(rows)
        self.assertEqual(response.mapped_count, 10)
        self.assertEqual(response.unclassified_count, 3)
        self.assertEqual(response.distinct_unmapped_skill_names, ["codex"])
        self.assertEqual(
            response.mapped_count + response.unclassified_count,
            sum(int(r["sample_count"]) for r in rows),
        )

    def test_distinct_unmapped_skill_names_deduplicated_and_sorted(self) -> None:
        rows = [
            _make_row(source_skill_name="codex", model="gpt-5.6", task_class=UNCLASSIFIED_TASK_CLASS, sample_count=1),
            _make_row(source_skill_name="codex", model="claude-opus-5", task_class=UNCLASSIFIED_TASK_CLASS, sample_count=2),
            _make_row(source_skill_name="ica-delegate", model="claude-opus-5", task_class=UNCLASSIFIED_TASK_CLASS, sample_count=2),
        ]
        response = _build_response_from_rows(rows)
        # Two rows share "codex" as source_skill_name -- the set must dedup,
        # not just concatenate, and the result must be sorted.
        self.assertEqual(response.distinct_unmapped_skill_names, ["codex", "ica-delegate"])
        self.assertEqual(response.unclassified_count, 5)

    def test_generated_at_is_max_freshness_ts_across_rows(self) -> None:
        rows = [
            _make_row(freshness_ts="2026-07-20T00:00:00+00:00"),
            _make_row(source_skill_name="dev-execution", freshness_ts="2026-07-31T00:00:00+00:00"),
            _make_row(source_skill_name="release", freshness_ts="2026-07-25T00:00:00+00:00"),
        ]
        response = _build_response_from_rows(rows)
        self.assertEqual(response.generated_at, "2026-07-31T00:00:00+00:00")

    def test_keys_equal_direct_row_to_key_dto_calls(self) -> None:
        """Reassembly must not reshape/rename anything ``_row_to_key_dto`` itself
        wouldn't produce -- ``keys[]`` is exactly ``[_row_to_key_dto(r) for r in rows]``.
        """
        rows = [
            _make_row(source_skill_name="planning"),
            _make_row(source_skill_name="release", task_class="mode_d"),
        ]
        response = _build_response_from_rows(rows)
        self.assertEqual(response.keys, [_row_to_key_dto(row) for row in rows])

    def test_response_enabled_true_and_identity_fields_from_constants(self) -> None:
        response = _build_response_from_rows([_make_row()])
        self.assertTrue(response.enabled)
        self.assertEqual(response.contract_id, CONTRACT_ID)
        self.assertEqual(response.taxonomy_id, TAXONOMY_ID)
        self.assertEqual(response.mapping_id, MAPPING_ID)


# ── Part 2: end-to-end REST round trip with real seeded rows ───────────────


class _StubWorkspaceRegistry:
    """Minimal ``WorkspaceRegistry`` stub -- mirrors
    ``test_client_v1_aar_review.py``'s fixture exactly. Only ``get_project``
    is exercised by ``resolve_project`` when an explicit ``project_id`` query
    param is supplied.
    """

    def __init__(self, project: Project) -> None:
        self._project = project

    def get_project(self, project_id: str) -> Project | None:
        return self._project if project_id == self._project.id else None

    def get_active_project(self) -> Project | None:
        return self._project

    def list_projects(self) -> list[Project]:
        return [self._project]


class TestClientV1RoutingRollupEnabledSeeded(unittest.TestCase):
    """AC (T5-001): the route returns the full envelope with real rollup data
    when ``CCDASH_ROUTING_FEEDBACK_ENABLED=true`` and persisted rows exist --
    previously verified only via an uncommitted manual harness round trip.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpdb.close()

        cls._env_patcher = patch.dict(
            os.environ,
            {
                "CCDASH_DB_PATH": cls._tmpdb.name,
                "CCDASH_DB_BACKEND": "sqlite",
            },
        )
        cls._env_patcher.start()

        cls._flag_patcher = patch.object(config, "CCDASH_ROUTING_FEEDBACK_ENABLED", True)
        cls._flag_patcher.start()

        cls._app = build_runtime_app("test")

        cls._patches = [
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
        for p in cls._patches:
            p.start()

        cls._app.dependency_overrides[get_auth_context] = lambda: AuthContext.synthesize_local(
            project_id=_PROJECT_ID
        )

        cls._tc = TestClient(cls._app, raise_server_exceptions=False)
        cls._tc.__enter__()
        cls.client = cls._tc

        # Migrations have now run (app startup). Wire a stub WorkspaceRegistry
        # so resolve_project_scope can resolve _PROJECT_ID against the real
        # container's storage -- mirrors test_client_v1_aar_review.py.
        real_ports = cls._app.state.core_ports
        stub_project = Project(id=_PROJECT_ID, name="Test Routing Rollup Project", path=cls._tmpdb.name)
        fake_ports = dataclasses.replace(
            real_ports, workspace_registry=_StubWorkspaceRegistry(stub_project)
        )
        fake_context = cls._build_fake_context(stub_project)
        cls._app.dependency_overrides[get_core_ports] = lambda: fake_ports
        cls._app.dependency_overrides[get_request_context] = lambda: fake_context

    @classmethod
    def _build_fake_context(cls, project: Project) -> RequestContext:
        principal = Principal(subject="test-local", display_name="Test Local", auth_mode="local")
        project_scope = ProjectScope(
            project_id=project.id,
            project_name=project.name,
            root_path=None,
            sessions_dir=None,
            docs_dir=None,
            progress_dir=None,
        )
        return RequestContext(
            principal=principal,
            workspace=WorkspaceScope(workspace_id=project.id, root_path=None),
            project=project_scope,
            runtime_profile="test",
            trace=TraceContext(
                request_id="test-routing-rollup", path="/api/v1/routing/rollup", method="GET"
            ),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._app.dependency_overrides.clear()
        cls._tc.__exit__(None, None, None)
        for p in reversed(cls._patches):
            p.stop()
        cls._flag_patcher.stop()
        cls._env_patcher.stop()
        try:
            os.unlink(cls._tmpdb.name)
        except OSError:
            pass

    def setUp(self) -> None:
        # Every persisted row belongs to _PROJECT_ID and this table is not
        # otherwise touched by app startup -- clear between tests so each
        # test's seeded rows are the only rows present.
        conn = sqlite3.connect(str(self._tmpdb.name))
        try:
            conn.execute("DELETE FROM routing_rollup")
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Helper: seed a routing_rollup row directly (raw sqlite3) -- mirrors
    # test_client_v1_aar_review.py's _insert_aar_review_row.
    # ------------------------------------------------------------------

    def _insert_routing_rollup_row(self, **overrides: Any) -> None:
        row = _make_row(**overrides)
        columns_sql = ", ".join(ROUTING_ROLLUP_COLUMNS)
        placeholders_sql = ", ".join(["?"] * len(ROUTING_ROLLUP_COLUMNS))
        values = tuple(row[col] for col in ROUTING_ROLLUP_COLUMNS)

        conn = sqlite3.connect(str(self._tmpdb.name))
        try:
            conn.execute(
                f"INSERT INTO routing_rollup ({columns_sql}) VALUES ({placeholders_sql})",
                values,
            )
            conn.commit()
        finally:
            conn.close()

    def _fetch(self) -> dict[str, Any]:
        resp = self.client.get("/api/v1/routing/rollup", params={"bypass_cache": "true"})
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def test_enabled_no_rows_returns_empty_but_enabled_envelope(self) -> None:
        body = self._fetch()
        data = body["data"]
        self.assertTrue(data["enabled"])
        self.assertIsNone(data["generated_at"])
        self.assertEqual(data["mapped_count"], 0)
        self.assertEqual(data["unclassified_count"], 0)
        self.assertEqual(data["distinct_unmapped_skill_names"], [])
        self.assertEqual(data["keys"], [])

    def test_enabled_seeded_rows_reassembled_into_full_envelope(self) -> None:
        self._insert_routing_rollup_row(
            source_skill_name="planning",
            model="claude-sonnet-5",
            task_class="orchestration",
            provider="anthropic",
            sample_count=10,
            success_rate=None,
            cost_index=0.5,
            cost_coverage_fraction=2 / 50,
            regression_rate=None,
            confidence=0.7,
            eligible_for_adjustment=1,
            freshness_ts="2026-07-30T00:00:00+00:00",
        )
        self._insert_routing_rollup_row(
            source_skill_name="codex",
            model="gpt-5.6",
            task_class=UNCLASSIFIED_TASK_CLASS,
            provider="openai",
            sample_count=4,
            success_rate=None,
            cost_index=0.1,
            cost_coverage_fraction=None,
            regression_rate=None,
            confidence=0.0,
            eligible_for_adjustment=0,
            freshness_ts="2026-07-31T00:00:00+00:00",
        )

        body = self._fetch()
        data = body["data"]

        self.assertTrue(data["enabled"])
        self.assertEqual(data["generated_at"], "2026-07-31T00:00:00+00:00")
        self.assertEqual(data["mapped_count"], 10)
        self.assertEqual(data["unclassified_count"], 4)
        self.assertEqual(data["distinct_unmapped_skill_names"], ["codex"])
        self.assertEqual(len(data["keys"]), 2)

        by_skill = {key["source_skill_name"]: key for key in data["keys"]}
        self.assertEqual(by_skill["planning"]["task_class"], "orchestration")
        self.assertEqual(by_skill["planning"]["sample_count"], 10)
        self.assertEqual(by_skill["planning"]["eligible_for_adjustment"], True)
        # v47 end-to-end round trip: a persisted PARTIAL-coverage key reads
        # back with its real fraction through the full client_v1 path
        # (repository read -> reassembly -> envelope), and a persisted NULL
        # (never re-swept / pre-v47 row) reads back as null, not 0.0.
        self.assertAlmostEqual(by_skill["planning"]["cost_coverage_fraction"], 2 / 50)
        self.assertIsNone(by_skill["codex"]["cost_coverage_fraction"])
        self.assertEqual(by_skill["codex"]["task_class"], UNCLASSIFIED_TASK_CLASS)
        self.assertEqual(by_skill["codex"]["eligible_for_adjustment"], False)
        # Contract identity fields are populated on every key row, even
        # though the table never persists them per-row.
        self.assertEqual(by_skill["planning"]["contract_id"], CONTRACT_ID)
        self.assertEqual(by_skill["planning"]["mapping_digest"], MAPPING_DIGEST)


if __name__ == "__main__":
    unittest.main()
