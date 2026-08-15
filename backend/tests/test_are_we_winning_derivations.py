"""Tests for the are-we-winning dashboard M2-part-B derivations.

Covers the milestone's explicit AC (see the M2-part-B task description):

  1. Terminal-status boundary — completed -> in_progress counts as reopened;
     in_progress -> blocked does not; a node never completed is never even
     examined.
  2. Derivation scope — the reopened-derivation candidate set is exactly the
     ever-completed node-id set, never the whole tree (instrumented via the
     fake HTTP getter's recorded call node ids).
  3. Self-caught unknown bucket — no discriminator present buckets to
     unknown; a 100% undiscriminated population yields all-unknown counts,
     never a percentage over a reduced denominator.
  4. Closed vocabulary — an unrecognized/absent proxy value maps to unknown,
     never raises, never invents a fourth bucket; a *recognized* value (when
     a map is explicitly injected) proves the bucketing machinery itself
     works, not just "always unknown".
  5. Zero render-path egress still holds for the new part-B surfaces
     (get_summary with derived data present, get_reopened_drill_through,
     get_self_caught_drill_through) — an outbound HTTP client patched to
     raise on any call.
  6. Absent-until-derived — reopened/self_caught_ratio stay None until the
     corresponding derivation's ingest_cursors watermark shows a completed
     pass; once it has, they populate for real (even if the derived tables
     are empty).
  7. Drill-through parity for both new surfaces.
  8. New memoized methods return pydantic DTOs directly (the already-fixed
     PostgresCacheBackend.aset _json_safe path — deliberate about the return
     type per the plan's named Postgres cache-write hazard).
  9. The derivation services themselves: persistence, fail-soft, idempotency,
     and cursor-watermark semantics, exercised end-to-end with a fake HTTP
     getter (mirrors test_intenttree_events_ingest.py's harness).

Run as a named module (full collection can hang in this repo):
    python3 -m pytest backend/tests/test_are_we_winning_derivations.py -v
"""
from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import aiosqlite
import httpx

from backend import config
from backend.application.context import (
    Principal,
    ProjectScope,
    RequestContext,
    TraceContext,
)
from backend.application.ports import CorePorts
from backend.application.services.agent_queries.are_we_winning import (
    AreWeWinningQueryService,
    compute_self_caught_ratio,
)
from backend.application.services.agent_queries.cache import clear_cache
from backend.application.services.ingest.intenttree_reopened_derivation import (
    ACTIVE_DESTINATION_STATUSES,
    SOURCE_ID as REOPENED_SOURCE_ID,
    TERMINAL_STATUSES,
    IntentTreeReopenedDerivationService,
)
from backend.application.services.ingest.intenttree_self_caught_derivation import (
    OTHER_CAUGHT_BUCKET,
    SELF_CAUGHT_BUCKET,
    SOURCE_ID as SELF_CAUGHT_SOURCE_ID,
    UNKNOWN_BUCKET,
    IntentTreeSelfCaughtDerivationService,
    decide_self_caught_bucket,
)
from backend.db.repositories.ingest_cursors import SqliteIngestCursorRepository
from backend.db.repositories.intent_tree_derivations import (
    SqliteIntentTreeReopenedEventsRepository,
    SqliteIntentTreeSelfCaughtBucketsRepository,
)
from backend.db.repositories.intent_tree_events import SqliteIntentTreeEventsRepository
from backend.db.sqlite_migrations import run_migrations
from backend.models import (
    AreWeWinningDrillThroughPageDTO,
    AreWeWinningSelfCaughtDrillThroughPageDTO,
    AreWeWinningSummaryDTO,
)
from backend.runtime_ports import build_core_ports


# ── Shared fixture helpers (mirrors test_are_we_winning_rollups.py) ─────────


def _context(project_id: str = "project-1") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Project 1",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


class _WorkspaceRegistry:
    def __init__(self, projects: list[Any]) -> None:
        self._projects = projects
        self._active = projects[0] if projects else None

    def list_projects(self) -> list[Any]:
        return list(self._projects)

    def get_project(self, project_id: str) -> Any | None:
        return next((p for p in self._projects if p.id == project_id), None)

    def get_active_project(self) -> Any | None:
        return self._active

    def resolve_scope(self, project_id: str | None = None) -> tuple[Any, Any]:
        _ = project_id
        return None, None


def _make_project(project_id: str) -> Any:
    import types

    return types.SimpleNamespace(id=project_id, name=project_id)


class _RaisingIntegrationClient:
    """Stand-in "outbound HTTP client" that raises on any call (zero render-path egress)."""

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "are_we_winning render path must never make an external call — "
            f"invoke() was called with args={args!r} kwargs={kwargs!r}"
        )


def _make_ports(db: Any, projects: list[Any] | None = None) -> CorePorts:
    real_ports = build_core_ports(
        db,
        workspace_registry=_WorkspaceRegistry(projects or [_make_project("project-1")]),
    )
    return CorePorts(
        identity_provider=real_ports.identity_provider,
        authorization_policy=real_ports.authorization_policy,
        workspace_registry=real_ports.workspace_registry,
        storage=real_ports.storage,
        job_scheduler=real_ports.job_scheduler,
        integration_client=_RaisingIntegrationClient(),
    )


async def _insert_event(
    repo: SqliteIntentTreeEventsRepository,
    *,
    event_id: str,
    event_type: str,
    occurred_at: str,
    node_id: str,
) -> None:
    await repo.insert_if_not_exists(
        {
            "id": event_id,
            "workspace_id": "ws-test",
            "tree_id": "tree-test",
            "node_id": node_id,
            "event_type": event_type,
            "actor_type": "system",
            "actor_id": None,
            "occurred_at": occurred_at,
            "payload_json": None,
        }
    )


class _AsyncSqliteHarness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        clear_cache()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.events_repo = SqliteIntentTreeEventsRepository(self.db)
        self.reopened_repo = SqliteIntentTreeReopenedEventsRepository(self.db)
        self.buckets_repo = SqliteIntentTreeSelfCaughtBucketsRepository(self.db)
        self.cursor_repo = SqliteIngestCursorRepository(self.db)
        self.ports = _make_ports(self.db)
        self.service = AreWeWinningQueryService()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        clear_cache()

    def _reopened_service(self, http_get, **kwargs) -> IntentTreeReopenedDerivationService:
        return IntentTreeReopenedDerivationService(
            self.db,
            self.reopened_repo,
            self.cursor_repo,
            api_url="http://intenttree.example.invalid",
            api_token="test-token",
            workspace_id="ws-test",
            http_get=http_get,
            **kwargs,
        )

    def _self_caught_service(self, http_get, **kwargs) -> IntentTreeSelfCaughtDerivationService:
        return IntentTreeSelfCaughtDerivationService(
            self.db,
            self.buckets_repo,
            self.cursor_repo,
            api_url="http://intenttree.example.invalid",
            api_token="test-token",
            workspace_id="ws-test",
            http_get=http_get,
            **kwargs,
        )


def _history_http_get(history_by_node: dict[str, list[dict]], fail_for: set[str] | None = None):
    """Fake HTTP GET for ``GET .../nodes/{node_id}/history``.

    Returns ``(http_get, calls)`` -- ``calls`` records every node_id
    requested, in call order (used to assert the exact candidate set the
    derivation examined).
    """
    calls: list[str] = []
    fail_for = fail_for or set()

    async def _http_get(url: str, params: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        node_id = url.rsplit("/nodes/", 1)[1].split("/history")[0]
        calls.append(node_id)
        if node_id in fail_for:
            raise httpx.ConnectError("simulated unreachable", request=None)
        items = history_by_node.get(node_id, [])
        return {"items": items, "next_cursor": None, "total": len(items)}

    return _http_get, calls


def _node_read_http_get(nodes_by_id: dict[str, dict], fail_for: set[str] | None = None):
    """Fake HTTP GET for ``GET .../nodes/{node_id}``."""
    calls: list[str] = []
    fail_for = fail_for or set()

    async def _http_get(url: str, params: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        node_id = url.rsplit("/nodes/", 1)[1]
        calls.append(node_id)
        if node_id in fail_for:
            raise httpx.ConnectError("simulated unreachable", request=None)
        return nodes_by_id.get(node_id, {"tags": [], "meta": {}})

    return _http_get, calls


def _history_item(
    *, item_id: str, old_status: str | None, new_status: str | None, changed_at: str
) -> dict[str, Any]:
    return {
        "id": item_id,
        "node_id": "unused-field-not-read",  # the service uses the URL's node_id, not this
        "field": "status",
        "old_value": ({"value": old_status} if old_status is not None else None),
        "new_value": ({"value": new_status} if new_status is not None else None),
        "changed_at": changed_at,
    }


# ── AC1: terminal-status boundary ───────────────────────────────────────────


class TerminalStatusBoundaryTests(_AsyncSqliteHarness):
    async def test_completed_to_in_progress_counts_as_reopened(self) -> None:
        await _insert_event(
            self.events_repo,
            event_id="evt-completed-1",
            event_type="node.completed",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        history_by_node = {
            "node-1": [
                _history_item(
                    item_id="hist-1",
                    old_status="completed",
                    new_status="in_progress",
                    changed_at="2026-08-10T00:00:00.000000Z",
                )
            ]
        }
        http_get, _calls = _history_http_get(history_by_node)
        result = await self._reopened_service(http_get).derive_all()

        self.assertTrue(result.ok)
        self.assertEqual(result.reopens_written, 1)
        rows = await self.reopened_repo.list_all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["node_id"], "node-1")
        self.assertEqual(rows[0]["from_status"], "completed")
        self.assertEqual(rows[0]["to_status"], "in_progress")

    async def test_in_progress_to_blocked_does_not_count(self) -> None:
        await _insert_event(
            self.events_repo,
            event_id="evt-completed-1",
            event_type="node.completed",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        history_by_node = {
            "node-1": [
                _history_item(
                    item_id="hist-1",
                    old_status="in_progress",
                    new_status="blocked",
                    changed_at="2026-08-10T00:00:00.000000Z",
                )
            ]
        }
        http_get, _calls = _history_http_get(history_by_node)
        result = await self._reopened_service(http_get).derive_all()

        self.assertTrue(result.ok)
        self.assertEqual(result.reopens_written, 0)
        rows = await self.reopened_repo.list_all()
        self.assertEqual(rows, [])

    async def test_node_never_completed_is_never_examined(self) -> None:
        # node-2 only ever emitted node.created -- it must never be fetched.
        await _insert_event(
            self.events_repo,
            event_id="evt-created-2",
            event_type="node.created",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-2",
        )
        http_get, calls = _history_http_get({})
        result = await self._reopened_service(http_get).derive_all()

        self.assertTrue(result.ok)
        self.assertEqual(result.candidate_node_ids, [])
        self.assertEqual(calls, [])

    async def test_terminal_statuses_constant_is_completed_only(self) -> None:
        # Pin the exact terminal-status set this derivation uses -- the
        # single highest-risk "silently plausible wrong" boundary named in
        # the task. See intenttree_reopened_derivation.py's module docstring
        # for the full rationale (archived/deferred deliberately excluded).
        self.assertEqual(TERMINAL_STATUSES, frozenset({"completed"}))

    async def test_completed_to_archived_is_disposal_not_a_reopen(self) -> None:
        # Gate fix: constraining only the source status (a node must have
        # been completed) silently counted completed -> archived as a
        # reopen. Archiving a finished node is disposal, not "completed
        # work regressed" -- it must not be persisted as a reopen row.
        await _insert_event(
            self.events_repo,
            event_id="evt-completed-1",
            event_type="node.completed",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        history_by_node = {
            "node-1": [
                _history_item(
                    item_id="hist-1",
                    old_status="completed",
                    new_status="archived",
                    changed_at="2026-08-10T00:00:00.000000Z",
                )
            ]
        }
        http_get, _calls = _history_http_get(history_by_node)
        result = await self._reopened_service(http_get).derive_all()

        self.assertTrue(result.ok)
        self.assertEqual(result.reopens_written, 0)
        rows = await self.reopened_repo.list_all()
        self.assertEqual(rows, [], "completed -> archived must not be persisted as a reopen")

    async def test_completed_to_deferred_is_disposal_not_a_reopen(self) -> None:
        await _insert_event(
            self.events_repo,
            event_id="evt-completed-1",
            event_type="node.completed",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        history_by_node = {
            "node-1": [
                _history_item(
                    item_id="hist-1",
                    old_status="completed",
                    new_status="deferred",
                    changed_at="2026-08-10T00:00:00.000000Z",
                )
            ]
        }
        http_get, _calls = _history_http_get(history_by_node)
        result = await self._reopened_service(http_get).derive_all()

        self.assertTrue(result.ok)
        self.assertEqual(result.reopens_written, 0)
        rows = await self.reopened_repo.list_all()
        self.assertEqual(rows, [], "completed -> deferred must not be persisted as a reopen")

    async def test_active_destination_statuses_excludes_disposal_values(self) -> None:
        # Pin the exact allow-list this derivation uses for the destination
        # side of the transition -- an allow-list, not a deny-list, so a
        # future upstream status defaults to "not a reopen".
        self.assertNotIn("archived", ACTIVE_DESTINATION_STATUSES)
        self.assertNotIn("deferred", ACTIVE_DESTINATION_STATUSES)
        self.assertNotIn("completed", ACTIVE_DESTINATION_STATUSES)
        self.assertIn("in_progress", ACTIVE_DESTINATION_STATUSES)


# ── AC2: derivation scope (ever-completed set only) ─────────────────────────


class DerivationScopeTests(_AsyncSqliteHarness):
    async def test_candidate_set_is_exactly_the_ever_completed_set(self) -> None:
        # 3 completed nodes (candidates), 2 created-only nodes (never examined).
        for i in range(3):
            await _insert_event(
                self.events_repo,
                event_id=f"evt-completed-{i}",
                event_type="node.completed",
                occurred_at="2026-08-01T00:00:00.000000Z",
                node_id=f"completed-node-{i}",
            )
        for i in range(2):
            await _insert_event(
                self.events_repo,
                event_id=f"evt-created-only-{i}",
                event_type="node.created",
                occurred_at="2026-08-01T00:00:00.000000Z",
                node_id=f"created-only-node-{i}",
            )

        http_get, calls = _history_http_get({})
        result = await self._reopened_service(http_get).derive_all()

        expected = {"completed-node-0", "completed-node-1", "completed-node-2"}
        self.assertEqual(set(result.candidate_node_ids), expected)
        self.assertEqual(set(calls), expected, "must fetch history for exactly the ever-completed set")
        self.assertEqual(len(calls), 3, "must not fetch any candidate more than once per pass")


# ── AC3: self-caught unknown bucket ─────────────────────────────────────────


class SelfCaughtUnknownBucketTests(_AsyncSqliteHarness):
    async def test_node_with_no_discriminator_buckets_to_unknown(self) -> None:
        verdict = decide_self_caught_bucket(tags=[], meta={})
        self.assertEqual(verdict.bucket, UNKNOWN_BUCKET)
        self.assertIn("no finding tag", verdict.reason)
        self.assertIn("meta.origin absent", verdict.reason)

    async def test_finding_tag_alone_does_not_discriminate(self) -> None:
        # The worknote is explicit: the finding tag marks THAT something is a
        # finding, not WHO caught it -- it must never, on its own, resolve to
        # self_caught or other_caught.
        verdict = decide_self_caught_bucket(tags=["finding"], meta={})
        self.assertEqual(verdict.bucket, UNKNOWN_BUCKET)
        self.assertIn("finding tag present", verdict.reason)

    async def test_100_percent_undiscriminated_population_yields_all_unknown_no_reduced_denominator(
        self,
    ) -> None:
        for i in range(5):
            await _insert_event(
                self.events_repo,
                event_id=f"evt-created-{i}",
                event_type="node.created",
                occurred_at="2026-08-01T00:00:00.000000Z",
                node_id=f"node-{i}",
            )
        # Every node has no tags/meta -- the measured-reality shape.
        http_get, _calls = _node_read_http_get({})
        result = await self._self_caught_service(http_get).derive_all()

        self.assertTrue(result.ok)
        self.assertEqual(result.buckets_written[UNKNOWN_BUCKET], 5)
        self.assertEqual(result.buckets_written[SELF_CAUGHT_BUCKET], 0)
        self.assertEqual(result.buckets_written[OTHER_CAUGHT_BUCKET], 0)

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            summary = await self.service.get_summary(_context(), self.ports)
        assert summary.self_caught_ratio is not None
        # total is the SUM of all three buckets (including unknown) -- never
        # a denominator with unknown subtracted out.
        self.assertEqual(summary.self_caught_ratio.total, 5)
        counts = {b.bucket: b.count for b in summary.self_caught_ratio.buckets}
        self.assertEqual(counts, {SELF_CAUGHT_BUCKET: 0, OTHER_CAUGHT_BUCKET: 0, UNKNOWN_BUCKET: 5})
        # All three buckets are always present in the response, even at 0 --
        # never silently dropped.
        self.assertEqual(
            {b.bucket for b in summary.self_caught_ratio.buckets},
            {SELF_CAUGHT_BUCKET, OTHER_CAUGHT_BUCKET, UNKNOWN_BUCKET},
        )


# ── AC4: closed vocabulary ───────────────────────────────────────────────────


class ClosedVocabularyTests(unittest.TestCase):
    def test_unrecognized_origin_value_maps_to_unknown_never_raises(self) -> None:
        verdict = decide_self_caught_bucket(
            tags=[],
            meta={"origin": "decision"},
            origin_bucket_map={"bug": SELF_CAUGHT_BUCKET},
        )
        self.assertEqual(verdict.bucket, UNKNOWN_BUCKET)

    def test_a_map_entry_that_is_not_a_counted_token_never_invents_a_fourth_bucket(self) -> None:
        # Defensive: even if a future map entry is malformed/typo'd, the
        # candidate must be one of exactly the two counted tokens or the
        # result falls back to unknown -- never a raise, never a new bucket.
        verdict = decide_self_caught_bucket(
            tags=[],
            meta={"origin": "bug"},
            origin_bucket_map={"bug": "something_else_entirely"},
        )
        self.assertEqual(verdict.bucket, UNKNOWN_BUCKET)

    def test_recognized_origin_value_resolves_correctly_when_a_map_is_injected(self) -> None:
        # Proves the closed-vocabulary machinery genuinely branches, not just
        # "always returns unknown" -- with an explicitly injected map (the
        # shipped default is empty; see the module docstring for why).
        self_caught_verdict = decide_self_caught_bucket(
            tags=[],
            meta={"origin": "bug"},
            origin_bucket_map={"bug": SELF_CAUGHT_BUCKET, "imported_plan": OTHER_CAUGHT_BUCKET},
        )
        self.assertEqual(self_caught_verdict.bucket, SELF_CAUGHT_BUCKET)

        other_caught_verdict = decide_self_caught_bucket(
            tags=[],
            meta={"origin": "imported_plan"},
            origin_bucket_map={"bug": SELF_CAUGHT_BUCKET, "imported_plan": OTHER_CAUGHT_BUCKET},
        )
        self.assertEqual(other_caught_verdict.bucket, OTHER_CAUGHT_BUCKET)

    def test_default_origin_bucket_map_is_empty_so_every_node_is_unknown_today(self) -> None:
        # The shipped conservative default: no confirmed origin-value
        # vocabulary exists that discriminates self vs. other-caught (see
        # the module docstring's ground-truth citation), so every node
        # buckets to unknown until that changes.
        verdict = decide_self_caught_bucket(tags=[], meta={"origin": "bug"})
        self.assertEqual(verdict.bucket, UNKNOWN_BUCKET)


# ── AC5: zero render-path egress, extended to the part-B surfaces ──────────


class ZeroRenderPathEgressTests(_AsyncSqliteHarness):
    async def _seed_derived_data(self) -> None:
        await _insert_event(
            self.events_repo,
            event_id="evt-completed-1",
            event_type="node.completed",
            occurred_at="2026-08-10T00:00:00.000000Z",
            node_id="node-1",
        )
        await self.reopened_repo.insert_if_not_exists(
            {
                "id": "hist-1",
                "node_id": "node-1",
                "from_status": "completed",
                "to_status": "in_progress",
                "occurred_at": "2026-08-10T00:00:00.000000Z",
            }
        )
        await self.buckets_repo.insert_if_not_exists(
            {"node_id": "node-1", "bucket": UNKNOWN_BUCKET, "reason": "no discriminator present"}
        )
        await self.cursor_repo.get_or_create(
            source_id=REOPENED_SOURCE_ID, project_id="global", workspace_id="ws-test"
        )
        await self.cursor_repo.advance(
            source_id=REOPENED_SOURCE_ID,
            project_id="global",
            workspace_id="ws-test",
            cursor_value="c1",
            occurred_at="2026-08-10T00:00:00.000000Z",
        )
        await self.cursor_repo.get_or_create(
            source_id=SELF_CAUGHT_SOURCE_ID, project_id="global", workspace_id="ws-test"
        )
        await self.cursor_repo.advance(
            source_id=SELF_CAUGHT_SOURCE_ID,
            project_id="global",
            workspace_id="ws-test",
            cursor_value="c1",
            occurred_at="2026-08-10T00:00:00.000000Z",
        )

    async def test_get_summary_with_derived_data_never_touches_the_raising_client(self) -> None:
        await self._seed_derived_data()
        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            result = await self.service.get_summary(_context(), self.ports)
        self.assertIsInstance(result, AreWeWinningSummaryDTO)
        self.assertIsNotNone(result.reopened)
        self.assertIsNotNone(result.self_caught_ratio)

    async def test_get_reopened_drill_through_never_touches_the_raising_client(self) -> None:
        await self._seed_derived_data()
        iso_year, iso_week, _ = date(2026, 8, 10).isocalendar()
        result = await self.service.get_reopened_drill_through(
            _context(), self.ports, iso_year=iso_year, iso_week=iso_week
        )
        self.assertIsInstance(result, AreWeWinningDrillThroughPageDTO)

    async def test_get_self_caught_drill_through_never_touches_the_raising_client(self) -> None:
        await self._seed_derived_data()
        result = await self.service.get_self_caught_drill_through(
            _context(), self.ports, bucket=UNKNOWN_BUCKET
        )
        self.assertIsInstance(result, AreWeWinningSelfCaughtDrillThroughPageDTO)


# ── AC6: absent-until-derived ────────────────────────────────────────────────


class AbsentUntilDerivedTests(_AsyncSqliteHarness):
    async def test_reopened_and_self_caught_ratio_stay_none_with_no_derivation_watermark(self) -> None:
        # Raw events exist, but neither derivation has ever run (no
        # ingest_cursors row for either source_id) -- both fields must stay
        # None, mirroring the pre-existing part-A AC4 test exactly.
        await _insert_event(
            self.events_repo,
            event_id="evt-1",
            event_type="node.created",
            occurred_at="2026-08-10T00:00:00.000000Z",
            node_id="node-1",
        )
        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            summary = await self.service.get_summary(_context(), self.ports)
        self.assertIsNone(summary.reopened)
        self.assertIsNone(summary.self_caught_ratio)

    async def test_reopened_and_self_caught_ratio_populate_once_watermark_set_even_if_empty(
        self,
    ) -> None:
        # Both derivations "ran" (cursor watermark advanced) but found
        # nothing to write -- the fields must populate for real (empty
        # trendline / all-zero-bucket ratio), never stay None.
        await self.cursor_repo.get_or_create(
            source_id=REOPENED_SOURCE_ID, project_id="global", workspace_id="ws-test"
        )
        await self.cursor_repo.advance(
            source_id=REOPENED_SOURCE_ID,
            project_id="global",
            workspace_id="ws-test",
            cursor_value="c1",
            occurred_at="2026-08-10T00:00:00.000000Z",
        )
        await self.cursor_repo.get_or_create(
            source_id=SELF_CAUGHT_SOURCE_ID, project_id="global", workspace_id="ws-test"
        )
        await self.cursor_repo.advance(
            source_id=SELF_CAUGHT_SOURCE_ID,
            project_id="global",
            workspace_id="ws-test",
            cursor_value="c1",
            occurred_at="2026-08-10T00:00:00.000000Z",
        )

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            summary = await self.service.get_summary(_context(), self.ports)

        self.assertIsNotNone(summary.reopened)
        self.assertEqual(summary.reopened.points, [])
        self.assertIsNotNone(summary.self_caught_ratio)
        self.assertEqual(summary.self_caught_ratio.total, 0)
        self.assertEqual(len(summary.self_caught_ratio.buckets), 3)


# ── AC7: drill-through parity ────────────────────────────────────────────────


class DrillThroughParityTests(_AsyncSqliteHarness):
    async def test_reopened_drill_through_returns_the_real_node_row(self) -> None:
        await _insert_event(
            self.events_repo,
            event_id="evt-completed-1",
            event_type="node.completed",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        await _insert_event(
            self.events_repo,
            event_id="evt-created-1",
            event_type="node.created",
            occurred_at="2026-07-01T00:00:00.000000Z",
            node_id="node-1",
        )
        history_by_node = {
            "node-1": [
                _history_item(
                    item_id="hist-1",
                    old_status="completed",
                    new_status="in_progress",
                    changed_at="2026-08-10T09:00:00.000000Z",
                )
            ]
        }
        http_get, _calls = _history_http_get(history_by_node)
        result = await self._reopened_service(http_get).derive_all()
        self.assertTrue(result.ok)

        iso_year, iso_week, _ = date(2026, 8, 10).isocalendar()
        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            summary = await self.service.get_summary(_context(), self.ports)
            page = await self.service.get_reopened_drill_through(
                _context(), self.ports, iso_year=iso_year, iso_week=iso_week
            )

        reopened_point = next(
            p for p in summary.reopened.points if (p.iso_year, p.iso_week) == (iso_year, iso_week)
        )
        self.assertEqual(reopened_point.count, 1)
        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0].node_id, "node-1")
        self.assertEqual(page.items[0].event_type, "node.reopened")

    async def test_generic_get_drill_through_also_serves_node_reopened(self) -> None:
        # The already-shipped M3 frontend's "Nodes Reopened" click handler
        # round-trips `trendline.event_type` ("node.reopened") into the
        # GENERIC /drill-through endpoint (get_drill_through), not the
        # dedicated get_reopened_drill_through one -- see
        # components/Analytics/AreWeWinningTab.tsx's openTrendPointDrillThrough
        # + lib/areWeWinning.ts's trendlineToChartPoints. If this path did not
        # also serve node.reopened, that click would silently return an empty
        # page the moment `reopened` stops being None -- a decorative click
        # target, which the plan's rubric names as an AC failure.
        await _insert_event(
            self.events_repo,
            event_id="evt-completed-1",
            event_type="node.completed",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        history_by_node = {
            "node-1": [
                _history_item(
                    item_id="hist-1",
                    old_status="completed",
                    new_status="in_progress",
                    changed_at="2026-08-10T09:00:00.000000Z",
                )
            ]
        }
        http_get, _calls = _history_http_get(history_by_node)
        result = await self._reopened_service(http_get).derive_all()
        self.assertTrue(result.ok)

        iso_year, iso_week, _ = date(2026, 8, 10).isocalendar()
        page = await self.service.get_drill_through(
            _context(),
            self.ports,
            event_type="node.reopened",
            iso_year=iso_year,
            iso_week=iso_week,
        )
        self.assertEqual(page.total, 1, "the generic drill-through endpoint must not decorate-empty node.reopened")
        self.assertEqual(page.items[0].node_id, "node-1")
        self.assertEqual(page.items[0].event_type, "node.reopened")

    async def test_self_caught_drill_through_returns_the_real_node_row(self) -> None:
        await _insert_event(
            self.events_repo,
            event_id="evt-created-1",
            event_type="node.created",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        http_get, _calls = _node_read_http_get({"node-1": {"tags": [], "meta": {}}})
        result = await self._self_caught_service(http_get).derive_all()
        self.assertTrue(result.ok)

        page = await self.service.get_self_caught_drill_through(
            _context(), self.ports, bucket=UNKNOWN_BUCKET
        )
        self.assertEqual(page.total, 1)
        self.assertEqual(page.items[0].node_id, "node-1")
        self.assertEqual(page.items[0].bucket, UNKNOWN_BUCKET)

    async def test_self_caught_drill_through_unrecognized_bucket_returns_empty_not_raise(self) -> None:
        page = await self.service.get_self_caught_drill_through(
            _context(), self.ports, bucket="not_a_real_bucket"
        )
        self.assertEqual(page.total, 0)
        self.assertEqual(page.items, [])


# ── AC8: new memoized methods return pydantic DTOs directly ────────────────


class MemoizedReturnTypeTests(_AsyncSqliteHarness):
    async def test_new_memoized_methods_return_pydantic_dtos_directly(self) -> None:
        # Mirrors the established, already-Postgres-safe pattern (see
        # are_we_winning.py's module docstring on PostgresCacheBackend.aset /
        # _json_safe): the memoized methods must return the pydantic response
        # DTO itself, never a pre-serialized dict/str -- that guard is what
        # makes returning the model directly safe on the Postgres cache
        # backend. This test cannot exercise Postgres directly in this
        # environment (see the implementation notes' deviation entry).
        from pydantic import BaseModel

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            reopened_page = await self.service.get_reopened_drill_through(
                _context(), self.ports, iso_year=2026, iso_week=1
            )
            self_caught_page = await self.service.get_self_caught_drill_through(
                _context(), self.ports, bucket=UNKNOWN_BUCKET
            )
        self.assertIsInstance(reopened_page, BaseModel)
        self.assertIsInstance(self_caught_page, BaseModel)


# ── AC9: derivation-service integration (persistence, fail-soft, idempotency) ─


class ReopenedDerivationServiceIntegrationTests(_AsyncSqliteHarness):
    async def test_persists_rows_and_advances_cursor_on_full_success(self) -> None:
        await _insert_event(
            self.events_repo,
            event_id="evt-completed-1",
            event_type="node.completed",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        history_by_node = {
            "node-1": [
                _history_item(
                    item_id="hist-1",
                    old_status="completed",
                    new_status="blocked",
                    changed_at="2026-08-10T00:00:00.000000Z",
                )
            ]
        }
        http_get, _calls = _history_http_get(history_by_node)
        result = await self._reopened_service(http_get).derive_all()
        self.assertTrue(result.ok)

        cursor = await self.cursor_repo.get_or_create(
            source_id=REOPENED_SOURCE_ID, project_id="global", workspace_id="ws-test"
        )
        self.assertIsNotNone(cursor.last_ingest_at)

    async def test_fail_soft_leaves_previously_derived_rows_uncrashed_and_does_not_advance_cursor(
        self,
    ) -> None:
        for i in range(2):
            await _insert_event(
                self.events_repo,
                event_id=f"evt-completed-{i}",
                event_type="node.completed",
                occurred_at="2026-08-01T00:00:00.000000Z",
                node_id=f"node-{i}",
            )
        history_by_node = {
            "node-0": [
                _history_item(
                    item_id="hist-0",
                    old_status="completed",
                    new_status="in_progress",
                    changed_at="2026-08-10T00:00:00.000000Z",
                )
            ],
        }
        # node-1's history fetch fails -- candidates are processed in sorted
        # order, so node-0 (already-written) precedes node-1 (fails).
        http_get, calls = _history_http_get(history_by_node, fail_for={"node-1"})
        result = await self._reopened_service(http_get).derive_all()

        self.assertFalse(result.ok)
        self.assertEqual(result.reopens_written, 1, "node-0's reopen must not be rolled back")
        rows = await self.reopened_repo.list_all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["node_id"], "node-0")

        cursor = await self.cursor_repo.get_or_create(
            source_id=REOPENED_SOURCE_ID, project_id="global", workspace_id="ws-test"
        )
        self.assertIsNone(cursor.last_ingest_at, "watermark must not advance on a partial-failure pass")

    async def test_idempotent_rerun_does_not_duplicate_rows(self) -> None:
        await _insert_event(
            self.events_repo,
            event_id="evt-completed-1",
            event_type="node.completed",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        history_by_node = {
            "node-1": [
                _history_item(
                    item_id="hist-1",
                    old_status="completed",
                    new_status="in_progress",
                    changed_at="2026-08-10T00:00:00.000000Z",
                )
            ]
        }
        http_get, _calls = _history_http_get(history_by_node)
        await self._reopened_service(http_get).derive_all()
        second_result = await self._reopened_service(http_get).derive_all()

        self.assertTrue(second_result.ok)
        self.assertEqual(second_result.reopens_written, 0, "re-deriving the same history is a no-op")
        rows = await self.reopened_repo.list_all()
        self.assertEqual(len(rows), 1)


class SelfCaughtDerivationServiceIntegrationTests(_AsyncSqliteHarness):
    async def test_persists_buckets_and_is_incremental_on_rerun(self) -> None:
        await _insert_event(
            self.events_repo,
            event_id="evt-created-1",
            event_type="node.created",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        http_get, calls = _node_read_http_get({"node-1": {"tags": [], "meta": {}}})
        first = await self._self_caught_service(http_get).derive_all()
        self.assertTrue(first.ok)
        self.assertEqual(len(calls), 1)

        # A newly-created second node arrives; the first must NOT be re-fetched.
        await _insert_event(
            self.events_repo,
            event_id="evt-created-2",
            event_type="node.created",
            occurred_at="2026-08-02T00:00:00.000000Z",
            node_id="node-2",
        )
        second = await self._self_caught_service(http_get).derive_all()
        self.assertTrue(second.ok)
        self.assertEqual(second.candidate_node_ids, ["node-2"], "already-bucketed node-1 must be skipped")
        self.assertEqual(calls, ["node-1", "node-2"])

    async def test_fail_soft_does_not_crash_and_does_not_advance_cursor(self) -> None:
        await _insert_event(
            self.events_repo,
            event_id="evt-created-1",
            event_type="node.created",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        http_get, _calls = _node_read_http_get({}, fail_for={"node-1"})
        result = await self._self_caught_service(http_get).derive_all()

        self.assertFalse(result.ok)
        rows = await self.buckets_repo.list_all()
        self.assertEqual(rows, [])
        cursor = await self.cursor_repo.get_or_create(
            source_id=SELF_CAUGHT_SOURCE_ID, project_id="global", workspace_id="ws-test"
        )
        self.assertIsNone(cursor.last_ingest_at)


class SelfCaughtClosedVocabularyNarrowingTests(_AsyncSqliteHarness):
    """M2 scheduler wiring task item 2: the closed vocabulary must be closed
    at the boundary where a stored bucket value leaves the database, not
    merely documented. A row with a bucket token outside the known 3-value
    set (which should never happen -- the derivation service only ever
    writes the closed vocabulary -- but a stored value is never trustworthy
    by construction) must surface as ``unknown``, never raise, and never
    become a 4th bucket in the returned DTO.
    """

    async def test_unexpected_stored_bucket_value_surfaces_as_unknown(self) -> None:
        await self.buckets_repo.insert_if_not_exists(
            {"node_id": "node-1", "bucket": "self_caught", "reason": "test fixture"}
        )
        await self.buckets_repo.insert_if_not_exists(
            {"node_id": "node-2", "bucket": "some_future_bucket_token", "reason": "test fixture"}
        )

        result = await compute_self_caught_ratio(self.db)

        self.assertEqual(result.total, 2)
        by_bucket = {row.bucket: row.count for row in result.buckets}
        self.assertEqual(
            set(by_bucket.keys()),
            {"self_caught", "other_caught", "unknown"},
            "an unrecognized token must never introduce a 4th bucket",
        )
        self.assertEqual(by_bucket["self_caught"], 1)
        self.assertEqual(by_bucket["other_caught"], 0)
        self.assertEqual(
            by_bucket["unknown"],
            1,
            "the unrecognized 'some_future_bucket_token' row must be narrowed to unknown",
        )

    async def test_drill_through_unknown_total_matches_summary_unknown_count(self) -> None:
        # Gate fix: compute_self_caught_ratio narrows stored bucket values
        # through _narrow_self_caught_bucket, but the drill-through path
        # previously compared/emitted the raw stored token -- so an
        # unrecognized token was counted as "unknown" in the summary while
        # being absent from the "unknown" drill-through page. Both surfaces
        # must agree about the same population.
        await self.buckets_repo.insert_if_not_exists(
            {"node_id": "node-1", "bucket": "self_caught", "reason": "test fixture"}
        )
        await self.buckets_repo.insert_if_not_exists(
            {"node_id": "node-2", "bucket": "some_future_bucket_token", "reason": "test fixture"}
        )
        await self.buckets_repo.insert_if_not_exists(
            {"node_id": "node-3", "bucket": "unknown", "reason": "test fixture"}
        )

        with patch.object(config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0):
            summary_ratio = await compute_self_caught_ratio(self.db)
            unknown_page = await self.service.get_self_caught_drill_through(
                _context(), self.ports, bucket=UNKNOWN_BUCKET
            )

        summary_unknown_count = next(
            b.count for b in summary_ratio.buckets if b.bucket == "unknown"
        )
        self.assertEqual(summary_unknown_count, 2)
        self.assertEqual(
            unknown_page.total,
            summary_unknown_count,
            "the unknown drill-through total must match the summary's unknown count",
        )
        drilled_node_ids = {item.node_id for item in unknown_page.items}
        self.assertEqual(drilled_node_ids, {"node-2", "node-3"})


class ReopenedCursorAdvanceFailureTests(_AsyncSqliteHarness):
    """Gate fix: cursor creation/advance previously caught every Exception,
    after which derive_all() still reported ok=True -- a programming or
    storage-contract error while recording the success watermark was
    swallowed while the watermark itself was never written. Mirrors the
    M1 ingestion service's principle: fail-soft must mean "the remote is
    unavailable", never "our code is wrong".
    """

    async def test_unexpected_exception_during_cursor_advance_does_not_produce_ok_true(
        self,
    ) -> None:
        await _insert_event(
            self.events_repo,
            event_id="evt-completed-1",
            event_type="node.completed",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        http_get, _calls = _history_http_get({"node-1": []})
        service = self._reopened_service(http_get)

        async def _broken_advance(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("simulated programming/storage-contract error")

        with patch.object(self.cursor_repo, "advance", _broken_advance):
            result = await service.derive_all()

        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)


class SelfCaughtCursorAdvanceFailureTests(_AsyncSqliteHarness):
    async def test_unexpected_exception_during_cursor_advance_does_not_produce_ok_true(
        self,
    ) -> None:
        await _insert_event(
            self.events_repo,
            event_id="evt-created-1",
            event_type="node.created",
            occurred_at="2026-08-01T00:00:00.000000Z",
            node_id="node-1",
        )
        http_get, _calls = _node_read_http_get({"node-1": {"tags": [], "meta": {}}})
        service = self._self_caught_service(http_get)

        async def _broken_advance(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("simulated programming/storage-contract error")

        with patch.object(self.cursor_repo, "advance", _broken_advance):
            result = await service.derive_all()

        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)


if __name__ == "__main__":
    unittest.main()
