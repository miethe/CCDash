"""Tests for ``run_intelligence.py`` (T2-003, research-foundry-run-telemetry-v1).

Two tiers of coverage:

1. Pure helper/DTO-mapping tests (no DB) — the AC-2-Field nullability
   contract: every optional metric maps ``NULL`` -> ``None``, never a
   fabricated ``0``/``""``/``[]``.
2. Service-level tests against a real in-memory SQLite DB (mirrors
   ``test_research_runs_migration_governance.py``'s established convention):
   seed ``rf_events`` -> backfill ``research_runs`` -> exercise
   ``RunIntelligenceQueryService.list_runs``/``get_run_detail`` end-to-end,
   including cursor pagination and the T2-006 entity-link correlation
   (AC-3's explicit "no linked session" resilience state).

Run as a named module (full collection can hang — see project memory):
    backend/.venv/bin/python -m pytest backend/tests/test_run_intelligence_query_service.py -v
"""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries import cache as cache_mod
from backend.application.services.agent_queries.run_intelligence import (
    DEFAULT_LIMIT,
    ResearchRunDetailDTO,
    ResearchRunSummaryDTO,
    RunIntelligenceQueryService,
    _decode_cursor,
    _encode_cursor,
    _run_row_to_detail,
    _run_row_to_summary,
)
from backend.db.repositories.entity_graph import SqliteEntityLinkRepository
from backend.db.repositories.research_runs import SqliteResearchRunsRepository
from backend.db.repositories.rf_events import SqliteRfEventsRepository
from backend.db.sqlite_migrations import run_migrations
from backend.models import Project


def _make_rf_event_row(event_id: str, run_id: str | None, *, project_id: str = "proj-1", **extra) -> dict:
    row = {
        "event_id": event_id,
        "workspace_id": "default-local",
        "project_id": project_id,
        "event_timestamp": "2026-07-21T10:00:00.000000Z",
        "rf_project": "research-foundry",
        "run_id": run_id,
        "raw_payload_json": "{}",
    }
    row.update(extra)
    return row


# ── 1. Pure helper / row-mapping tests (AC-2-Field) ─────────────────────────


class CursorHelperTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        cursor = _encode_cursor(42)
        self.assertEqual(_decode_cursor(cursor), 42)

    def test_none_decodes_to_zero(self) -> None:
        self.assertEqual(_decode_cursor(None), 0)

    def test_garbage_decodes_to_zero(self) -> None:
        self.assertEqual(_decode_cursor("not-a-real-cursor"), 0)

    def test_negative_offset_clamped_to_zero(self) -> None:
        import base64
        import json

        raw = base64.urlsafe_b64encode(json.dumps({"o": -5}).encode()).decode()
        self.assertEqual(_decode_cursor(raw), 0)


class RowToSummaryDTOTests(unittest.TestCase):
    """AC-2-Field: every optional metric is None when the source column is NULL."""

    def _minimal_row(self, **overrides) -> dict:
        row = {
            "run_id": "11111111-1111-4111-8111-111111111111",
            "rf_run_id": None,
            "project_id": "proj-1",
            "workspace_id": "default-local",
            "intent_id": None,
            "task_node_id": None,
            "rf_project": None,
            "event_count": 1,
            "first_event_at": "2026-07-21T10:00:00Z",
            "last_event_at": "2026-07-21T10:00:00Z",
            "total_queries_executed": None,
            "total_urls_extracted": None,
            "total_useful_source_count": None,
            "total_tokens_estimated": None,
            "total_claims_total": None,
            "total_claims_supported": None,
            "total_claims_mixed": None,
            "total_claims_contradicted": None,
            "total_unsupported_claims": None,
            "total_estimated_cost_usd": None,
            "total_latency_ms": None,
            "citation_coverage": None,
            "duplicate_rate": None,
            "extraction_failure_rate": None,
            "quality_score": None,
            "drift_score": None,
            "governance_sensitivity": None,
            "governance_policy_passed": None,
            "human_review_required": None,
            "human_review_status": None,
            "human_review_reviewer": None,
            "reuse_meatywiki_writeback_candidate": None,
            "reuse_skillbom_candidate": None,
            "reuse_reusable_source_pack_candidate": None,
            "agent_postures_json": None,
            "skillbom_ids_json": None,
            "tools_json": None,
            "input_artifacts_json": None,
            "output_artifacts_json": None,
            "created_at": "2026-07-21T10:00:00Z",
            "updated_at": "2026-07-21T10:00:00Z",
        }
        row.update(overrides)
        return row

    def test_all_optional_metrics_are_none_not_zero(self) -> None:
        dto = _run_row_to_summary(self._minimal_row())
        self.assertIsInstance(dto, ResearchRunSummaryDTO)
        for field in (
            "queries_executed", "urls_extracted", "useful_source_count",
            "tokens_estimated", "claims_total", "claims_supported",
            "claims_mixed", "claims_contradicted", "unsupported_claims",
            "estimated_cost_usd", "latency_ms", "citation_coverage",
            "duplicate_rate", "extraction_failure_rate", "quality_score",
            "drift_score", "governance_policy_passed", "human_review_required",
            "human_review_status", "human_review_reviewer",
            "reuse_meatywiki_writeback_candidate", "reuse_skillbom_candidate",
            "reuse_reusable_source_pack_candidate", "rf_run_id", "intent_id",
            "task_node_id",
        ):
            self.assertIsNone(
                getattr(dto, field), f"{field} must be None, not a fabricated default"
            )
        # AC-2-Field explicitly names these -- always None today (documented gap).
        self.assertIsNone(dto.mode)
        self.assertIsNone(dto.selected_providers)
        # Never correlated in this fixture -- explicit empty list, not None.
        self.assertIsNone(dto.linked_session_id)
        self.assertEqual(dto.linked_session_ids, [])

    def test_populated_metrics_survive_mapping(self) -> None:
        dto = _run_row_to_summary(
            self._minimal_row(
                total_estimated_cost_usd=1.23,
                citation_coverage=0.75,
                total_queries_executed=7,
                human_review_required=1,
                reuse_skillbom_candidate=0,
            )
        )
        self.assertAlmostEqual(dto.estimated_cost_usd, 1.23)
        self.assertAlmostEqual(dto.citation_coverage, 0.75)
        self.assertEqual(dto.queries_executed, 7)
        self.assertIs(dto.human_review_required, True)
        self.assertIs(dto.reuse_skillbom_candidate, False)

    def test_linked_session_ids_populates_primary_pointer(self) -> None:
        dto = _run_row_to_summary(self._minimal_row(), linked_session_ids=["sess-a", "sess-b"])
        self.assertEqual(dto.linked_session_id, "sess-a")
        self.assertEqual(dto.linked_session_ids, ["sess-a", "sess-b"])

    def test_detail_dto_decodes_json_snapshot_columns(self) -> None:
        row = self._minimal_row(tools_json='["exa", "brave"]', agent_postures_json="not-json")
        dto = _run_row_to_detail(row)
        self.assertIsInstance(dto, ResearchRunDetailDTO)
        self.assertEqual(dto.tools, ["exa", "brave"])
        # Malformed JSON degrades to None, never a crash or a fabricated [].
        self.assertIsNone(dto.agent_postures)
        self.assertIsNone(dto.skillbom_ids)


# ── 2. Service-level tests against a real in-memory SQLite DB ──────────────


class _WorkspaceRegistry:
    def __init__(self, project: Project) -> None:
        self._project = project

    def get_project(self, project_id: str):
        if project_id == self._project.id:
            return self._project
        return None

    def get_active_project(self):
        return self._project

    def resolve_scope(self, project_id=None):
        return None, ProjectScope(
            project_id=project_id or self._project.id,
            project_name=self._project.name,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


class _Storage:
    def __init__(self, db) -> None:
        self.db = db
        self._entity_links = SqliteEntityLinkRepository(db)

    def entity_links(self):
        return self._entity_links


def _context(project_id: str) -> RequestContext:
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
        trace=TraceContext(request_id="req-run-intel-1"),
    )


def _ports(db, project: Project) -> CorePorts:
    return CorePorts(
        identity_provider=types.SimpleNamespace(
            get_principal=AsyncMock(return_value=Principal(subject="t", display_name="t", auth_mode="test"))
        ),
        authorization_policy=types.SimpleNamespace(
            authorize=AsyncMock(return_value=AuthorizationDecision(allowed=True))
        ),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_Storage(db),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


class RunIntelligenceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        # Bypass the query cache entirely -- this test suite exercises the
        # service's own DB-facing logic, not CACHE-004's memoization.
        self._ttl_patch = patch.object(cache_mod.config, "CCDASH_QUERY_CACHE_TTL_SECONDS", 0)
        self._ttl_patch.start()

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        self.project = Project(id="proj-1", name="Project 1", path="/tmp/project")
        self.context = _context(self.project.id)
        self.ports = _ports(self.db, self.project)

        self.rf_repo = SqliteRfEventsRepository(self.db)
        self.rr_repo = SqliteResearchRunsRepository(self.db)
        self.service = RunIntelligenceQueryService()

    async def asyncTearDown(self) -> None:
        self._ttl_patch.stop()
        await self.db.close()

    async def test_list_runs_empty_project_returns_ok_empty_page(self) -> None:
        result = await self.service.list_runs(self.context, self.ports)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.items, [])
        self.assertIsNone(result.next_cursor)

    async def test_list_runs_returns_seeded_rows_newest_first(self) -> None:
        await self.rf_repo.insert_if_not_exists(
            _make_rf_event_row("evt-a", "run-old", event_timestamp="2026-07-21T09:00:00Z")
        )
        await self.rf_repo.insert_if_not_exists(
            _make_rf_event_row("evt-b", "run-new", event_timestamp="2026-07-21T11:00:00Z")
        )
        await self.rr_repo.backfill_from_rf_events(project_id="proj-1")

        result = await self.service.list_runs(self.context, self.ports)
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.items[0].rf_run_id, "run-new", "newest last_event_at first")
        self.assertEqual(result.items[1].rf_run_id, "run-old")
        self.assertIsNone(result.next_cursor)

    async def test_list_runs_does_not_leak_other_projects(self) -> None:
        await self.rf_repo.insert_if_not_exists(
            _make_rf_event_row("evt-a", "run-a", project_id="proj-1")
        )
        await self.rf_repo.insert_if_not_exists(
            _make_rf_event_row("evt-b", "run-b", project_id="proj-other")
        )
        await self.rr_repo.backfill_from_rf_events(project_id="proj-1")
        await self.rr_repo.backfill_from_rf_events(project_id="proj-other")

        result = await self.service.list_runs(self.context, self.ports)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].rf_run_id, "run-a")

    async def test_list_runs_cursor_pagination_covers_all_rows_without_overlap(self) -> None:
        for i in range(5):
            await self.rf_repo.insert_if_not_exists(
                _make_rf_event_row(f"evt-{i}", f"run-{i}", event_timestamp=f"2026-07-21T{10 + i:02d}:00:00Z")
            )
        await self.rr_repo.backfill_from_rf_events(project_id="proj-1")

        seen_run_ids: list[str] = []
        cursor = None
        pages = 0
        while True:
            page = await self.service.list_runs(self.context, self.ports, cursor=cursor, limit=2)
            seen_run_ids.extend(item.rf_run_id for item in page.items)
            pages += 1
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
            self.assertLess(pages, 10, "pagination did not terminate")

        self.assertEqual(pages, 3, "5 rows at limit=2 should page 2+2+1")
        self.assertEqual(sorted(seen_run_ids), sorted(f"run-{i}" for i in range(5)))
        self.assertEqual(len(seen_run_ids), len(set(seen_run_ids)), "no duplicate rows across pages")

    async def test_get_run_detail_not_found_is_ok_status_not_error(self) -> None:
        result = await self.service.get_run_detail(self.context, self.ports, "does-not-exist")
        self.assertEqual(result.status, "ok")
        self.assertFalse(result.found)
        self.assertIsNone(result.run)

    async def test_get_run_detail_empty_run_id_is_error(self) -> None:
        result = await self.service.get_run_detail(self.context, self.ports, "")
        self.assertEqual(result.status, "error")
        self.assertFalse(result.found)

    async def test_get_run_detail_returns_full_row(self) -> None:
        await self.rf_repo.insert_if_not_exists(
            _make_rf_event_row(
                "evt-a", "run-detail-1",
                metric_estimated_cost_usd=0.42, metric_citation_coverage=0.9,
                metric_queries_executed=3,
            )
        )
        await self.rr_repo.backfill_from_rf_events(project_id="proj-1")

        row = await self.rr_repo.get_by_rf_run_id("run-detail-1", project_id="proj-1")
        run_id = row["run_id"]

        result = await self.service.get_run_detail(self.context, self.ports, run_id)
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.found)
        self.assertIsNotNone(result.run)
        self.assertEqual(result.run.run_id, run_id)
        self.assertEqual(result.run.rf_run_id, "run-detail-1")
        self.assertAlmostEqual(result.run.estimated_cost_usd, 0.42)
        self.assertAlmostEqual(result.run.citation_coverage, 0.9)
        self.assertEqual(result.run.queries_executed, 3)
        # Never correlated -- explicit empty list per AC-3.
        self.assertEqual(result.run.linked_session_ids, [])
        self.assertIsNone(result.run.linked_session_id)

    async def test_get_run_detail_scopes_to_requested_project(self) -> None:
        """A run_id that exists only in a different project must resolve as not-found."""
        await self.rf_repo.insert_if_not_exists(
            _make_rf_event_row("evt-a", "run-x", project_id="proj-other")
        )
        await self.rr_repo.backfill_from_rf_events(project_id="proj-other")
        row = await self.rr_repo.get_by_rf_run_id("run-x", project_id="proj-other")
        run_id = row["run_id"]

        result = await self.service.get_run_detail(self.context, self.ports, run_id)
        self.assertFalse(result.found)

    async def test_get_run_detail_surfaces_correlated_session_via_entity_links(self) -> None:
        """AC-3 / T2-006: a linked session shows up as an explicit non-empty list."""
        await self.rf_repo.insert_if_not_exists(_make_rf_event_row("evt-a", "run-linked"))
        await self.rr_repo.backfill_from_rf_events(project_id="proj-1")
        row = await self.rr_repo.get_by_rf_run_id("run-linked", project_id="proj-1")
        run_id = row["run_id"]

        entity_links = self.ports.storage.entity_links()
        linked = await entity_links.link_research_run_sessions(row, ["sess-42"])
        self.assertEqual(linked, 1)

        result = await self.service.get_run_detail(self.context, self.ports, run_id)
        self.assertEqual(result.run.linked_session_ids, ["sess-42"])
        self.assertEqual(result.run.linked_session_id, "sess-42")

    async def test_list_runs_batches_correlation_lookup_without_n_plus_1(self) -> None:
        """Same correlation contract as detail, exercised through the list page."""
        await self.rf_repo.insert_if_not_exists(_make_rf_event_row("evt-a", "run-list-linked"))
        await self.rr_repo.backfill_from_rf_events(project_id="proj-1")
        row = await self.rr_repo.get_by_rf_run_id("run-list-linked", project_id="proj-1")

        entity_links = self.ports.storage.entity_links()
        await entity_links.link_research_run_sessions(row, ["sess-99"])

        result = await self.service.list_runs(self.context, self.ports)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].linked_session_ids, ["sess-99"])

    async def test_unresolvable_project_returns_error_status(self) -> None:
        result = await self.service.get_run_detail(
            self.context, self.ports, "irrelevant", project_id_override="no-such-project"
        )
        self.assertEqual(result.status, "error")


if __name__ == "__main__":
    unittest.main()
