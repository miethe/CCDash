"""Fixture suite for the 5th AAR-review flag ``new_skill_or_agent_need``
(``ccdash-automated-aar-review`` Phase 3, T3-001..T3-004).

Covers:
- T3-002: ``count_recent_flag_triggers`` -- pure-function aggregation over
  already-PERSISTED ``aar_reviews`` rows (dedup-by-document, lookback-window
  filtering, flag-id scoping).
- T3-002/T3-003: ``evaluate_new_skill_or_agent_need`` -- below / at / above
  threshold, each independently exercised WITH and WITHOUT a matching
  SkillMeat ranking (six-cell matrix, AC-P3.2).
- T3-001: ``evaluate_stack_ineffectiveness``'s new ``artifact_rankings``
  parameter only ever ADDS evidence to an already-triggered flag -- the
  trigger gate itself is unchanged.
- T3-004 (AC-P3.2): end-to-end wiring through ``AARReviewQueryService
  .get_review`` against a real in-memory ``aar_reviews`` table seeded
  directly (live persist-on-compute is intentionally deferred -- this suite
  seeds the table rather than relying on a prior ``get_review`` call to have
  written it).

HARD INVARIANT #1 (unchanged): zero LLM/model calls anywhere on this path --
every fixture below is a plain dict/dataclass; no model/agent client is
imported.

HARD INVARIANT #2 (CCDash emits only): every SkillMeat-ranking fixture in
this file is a plain in-memory read-only fake (``_Rankings.list_rankings``);
none of it writes/creates/dispatches anything, mirroring the read-only
contract of ``ArtifactIntelligenceQueryService.get_rankings``.

Run as named modules (full collection can hang):
    backend/.venv/bin/python -m pytest backend/tests/test_aar_review_fifth_flag.py -v
"""
from __future__ import annotations

import json
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.aar_review import (
    AARReviewQueryService,
    count_recent_flag_triggers,
    evaluate_new_skill_or_agent_need,
    evaluate_stack_ineffectiveness,
)
from backend.db.repositories.aar_reviews import SqliteAarReviewsRepository
from backend.db.sqlite_migrations import run_migrations

_NEW_SKILL_FLAG_IDS = frozenset({"generic_agent_vs_specialist", "missing_artifacts"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_row(
    *,
    doc_id: str,
    session_id: str,
    project_id: str = "project-1",
    flag_id: str = "missing_artifacts",
    triggered: bool = True,
    generated_at: str | None = None,
) -> dict:
    """Build one ``AAR_REVIEWS_COLUMNS``-shaped row directly (no ``AARReviewDTO`` needed).

    Mirrors exactly what ``build_aar_review_row`` would write for a document
    whose only notable flag is *flag_id* -- seeded directly per T3-004's
    explicit deferral of live persist-on-compute.
    """
    flags = [
        {"flag_id": "context_ballooning", "triggered": False, "severity": "low", "evidence_refs": [], "rationale": "n/a"},
        {"flag_id": flag_id, "triggered": triggered, "severity": "medium", "evidence_refs": ["evidence"], "rationale": "n/a"},
    ]
    return {
        "aar_document_id": doc_id,
        "session_id": session_id,
        "project_id": project_id,
        "aar_document_path": f"docs/{doc_id}.md",
        "correlation": json.dumps(
            {"strategy": "explicit_session_ref", "confidence": 1.0, "session_ids": [session_id], "feature_id": None}
        ),
        "flags": json.dumps(flags),
        "triage_verdict": "deep_review_recommended" if triggered else "surface_only",
        "triage_reasons": json.dumps([]),
        "evidence_refs": json.dumps([doc_id, session_id]),
        "generated_at": generated_at or _now_iso(),
        "provenance_skill_name": None,
        "provenance_workflow_id": None,
    }


# ── T3-002: count_recent_flag_triggers (pure function) ──────────────────────


class CountRecentFlagTriggersTests(unittest.TestCase):
    def test_dedupes_by_document_not_by_fanned_out_row(self) -> None:
        lookback_start = datetime.now(timezone.utc) - timedelta(days=30)
        rows = [
            _seed_row(doc_id="doc-1", session_id="s-1"),
            _seed_row(doc_id="doc-1", session_id="s-2"),  # same doc, fanned out per session
        ]
        count, doc_ids = count_recent_flag_triggers(rows, _NEW_SKILL_FLAG_IDS, lookback_start=lookback_start)
        self.assertEqual(count, 1)
        self.assertEqual(doc_ids, ["doc-1"])

    def test_counts_multiple_distinct_documents(self) -> None:
        lookback_start = datetime.now(timezone.utc) - timedelta(days=30)
        rows = [_seed_row(doc_id=f"doc-{i}", session_id=f"s-{i}") for i in range(4)]
        count, doc_ids = count_recent_flag_triggers(rows, _NEW_SKILL_FLAG_IDS, lookback_start=lookback_start)
        self.assertEqual(count, 4)
        self.assertEqual(doc_ids, ["doc-0", "doc-1", "doc-2", "doc-3"])

    def test_excludes_rows_outside_the_lookback_window(self) -> None:
        lookback_start = datetime.now(timezone.utc) - timedelta(days=7)
        stale = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        rows = [_seed_row(doc_id="doc-old", session_id="s-1", generated_at=stale)]
        count, doc_ids = count_recent_flag_triggers(rows, _NEW_SKILL_FLAG_IDS, lookback_start=lookback_start)
        self.assertEqual(count, 0)
        self.assertEqual(doc_ids, [])

    def test_ignores_rows_where_the_flag_did_not_trigger(self) -> None:
        lookback_start = datetime.now(timezone.utc) - timedelta(days=30)
        rows = [_seed_row(doc_id="doc-1", session_id="s-1", triggered=False)]
        count, _doc_ids = count_recent_flag_triggers(rows, _NEW_SKILL_FLAG_IDS, lookback_start=lookback_start)
        self.assertEqual(count, 0)

    def test_only_the_two_scoped_flag_ids_count_toward_the_aggregate(self) -> None:
        lookback_start = datetime.now(timezone.utc) - timedelta(days=30)
        rows = [_seed_row(doc_id="doc-1", session_id="s-1", flag_id="context_ballooning", triggered=True)]
        count, _doc_ids = count_recent_flag_triggers(rows, _NEW_SKILL_FLAG_IDS, lookback_start=lookback_start)
        self.assertEqual(count, 0)

    def test_unparsable_generated_at_is_skipped_not_an_error(self) -> None:
        lookback_start = datetime.now(timezone.utc) - timedelta(days=30)
        rows = [_seed_row(doc_id="doc-1", session_id="s-1", generated_at="not-a-date")]
        count, _doc_ids = count_recent_flag_triggers(rows, _NEW_SKILL_FLAG_IDS, lookback_start=lookback_start)
        self.assertEqual(count, 0)

    def test_non_dict_row_is_skipped_not_an_error(self) -> None:
        lookback_start = datetime.now(timezone.utc) - timedelta(days=30)
        count, _doc_ids = count_recent_flag_triggers(["not-a-dict"], _NEW_SKILL_FLAG_IDS, lookback_start=lookback_start)  # type: ignore[list-item]
        self.assertEqual(count, 0)


# ── T3-002/T3-003: evaluate_new_skill_or_agent_need matrix ──────────────────


class EvaluateNewSkillOrAgentNeedTests(unittest.TestCase):
    """Below / at / above threshold, each WITH and WITHOUT a matching SkillMeat ranking."""

    # -- below threshold --

    def test_below_threshold_without_ranking_does_not_trigger(self) -> None:
        flag = evaluate_new_skill_or_agent_need(2, 3, lookback_days=30)
        self.assertEqual(flag.flag_id, "new_skill_or_agent_need")
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.severity, "low")
        self.assertEqual(flag.evidence_refs, [])
        self.assertIn("below threshold", flag.rationale)

    def test_below_threshold_with_matching_ranking_still_does_not_trigger(self) -> None:
        rankings = {"backend-typescript-architect": {"cost_usd": 1.0, "period": "30d"}}
        flag = evaluate_new_skill_or_agent_need(
            2, 3, lookback_days=30,
            implicated_specialists=["backend-typescript-architect"], artifact_rankings=rankings,
        )
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.evidence_refs, [], "ranking evidence must never appear on a non-triggered flag")

    # -- at threshold --

    def test_at_threshold_without_ranking_triggers_with_count_evidence_only(self) -> None:
        flag = evaluate_new_skill_or_agent_need(3, 3, lookback_days=30)
        self.assertTrue(flag.triggered)
        self.assertEqual(flag.severity, "medium")
        self.assertEqual(len(flag.evidence_refs), 1)
        self.assertIn("3 generic-agent/missing-artifact trigger", flag.evidence_refs[0])

    def test_at_threshold_with_matching_ranking_adds_descriptive_evidence(self) -> None:
        rankings = {"ui-engineer-enhanced": {"cost_usd": 4.2, "efficiency_score": 0.8, "period": "30d"}}
        flag = evaluate_new_skill_or_agent_need(
            3, 3, lookback_days=30,
            implicated_specialists=["ui-engineer-enhanced"], artifact_rankings=rankings,
        )
        self.assertTrue(flag.triggered)
        self.assertEqual(len(flag.evidence_refs), 2)
        self.assertIn("consider a specialist for domain 'ui-engineer-enhanced'", flag.evidence_refs[1])
        self.assertIn("cost_usd=4.2", flag.evidence_refs[1])
        self.assertIn("efficiency_score=0.8", flag.evidence_refs[1])

    # -- above threshold --

    def test_above_threshold_without_ranking_triggers(self) -> None:
        flag = evaluate_new_skill_or_agent_need(7, 3, lookback_days=30)
        self.assertTrue(flag.triggered)
        self.assertEqual(len(flag.evidence_refs), 1)
        self.assertIn("7 generic-agent/missing-artifact trigger", flag.evidence_refs[0])

    def test_above_threshold_with_matching_ranking_adds_descriptive_evidence(self) -> None:
        rankings = {"backend-typescript-architect": {"cost_usd": 9.9, "period": "30d"}}
        flag = evaluate_new_skill_or_agent_need(
            7, 3, lookback_days=30,
            implicated_specialists=["backend-typescript-architect"], artifact_rankings=rankings,
        )
        self.assertTrue(flag.triggered)
        self.assertEqual(len(flag.evidence_refs), 2)
        self.assertIn("consider a specialist for domain 'backend-typescript-architect'", flag.evidence_refs[1])
        self.assertIn("cost_usd=9.9", flag.evidence_refs[1])

    def test_above_threshold_with_ranking_for_an_unimplicated_specialist_adds_no_evidence(self) -> None:
        rankings = {"ui-engineer-enhanced": {"cost_usd": 4.2}}
        flag = evaluate_new_skill_or_agent_need(
            7, 3, lookback_days=30,
            implicated_specialists=["backend-typescript-architect"], artifact_rankings=rankings,
        )
        self.assertTrue(flag.triggered)
        self.assertEqual(len(flag.evidence_refs), 1, "no ranking evidence when the implicated specialist has no ranking row")

    def test_ranking_presence_never_changes_triggered_severity_or_flag_id(self) -> None:
        no_ranking = evaluate_new_skill_or_agent_need(5, 3, lookback_days=30)
        with_ranking = evaluate_new_skill_or_agent_need(
            5, 3, lookback_days=30,
            implicated_specialists=["backend-typescript-architect"],
            artifact_rankings={"backend-typescript-architect": {"cost_usd": 1.0}},
        )
        self.assertEqual(no_ranking.triggered, with_ranking.triggered)
        self.assertEqual(no_ranking.severity, with_ranking.severity)
        self.assertEqual(no_ranking.flag_id, with_ranking.flag_id)


# ── T3-001: evaluate_stack_ineffectiveness's artifact_rankings addition ─────


class StackIneffectivenessArtifactRankingWiringTests(unittest.TestCase):
    """``artifact_rankings`` only ADDS evidence to an already-triggered flag."""

    _failure_items = [{"title": "Debug loop", "severity": "high", "sessionIds": ["s1"]}]

    def test_trigger_gate_is_byte_identical_with_or_without_rankings(self) -> None:
        without = evaluate_stack_ineffectiveness(
            ["s1"], {"s1": ["backend/foo.py"]}, self._failure_items, feature_scope_available=True,
        )
        with_rankings = evaluate_stack_ineffectiveness(
            ["s1"], {"s1": ["backend/foo.py"]}, self._failure_items, feature_scope_available=True,
            artifact_rankings={"backend-typescript-architect": {"cost_usd": 3.5, "period": "30d"}},
        )
        self.assertEqual(without.triggered, with_rankings.triggered)
        self.assertEqual(without.severity, with_rankings.severity)
        self.assertEqual(without.rationale, with_rankings.rationale)

    def test_adds_ranking_evidence_line_for_the_matched_specialist(self) -> None:
        flag = evaluate_stack_ineffectiveness(
            ["s1"], {"s1": ["backend/foo.py"]}, self._failure_items, feature_scope_available=True,
            artifact_rankings={
                "backend-typescript-architect": {"cost_usd": 3.5, "efficiency_score": 0.7, "period": "30d"},
            },
        )
        self.assertTrue(flag.triggered)
        self.assertTrue(
            any("SkillMeat ranking for specialist 'backend-typescript-architect'" in e for e in flag.evidence_refs)
        )
        self.assertTrue(any("cost_usd=3.5" in e for e in flag.evidence_refs))

    def test_no_evidence_added_when_specialist_has_no_known_ranking(self) -> None:
        flag = evaluate_stack_ineffectiveness(
            ["s1"], {"s1": ["backend/foo.py"]}, self._failure_items, feature_scope_available=True,
            artifact_rankings={"ui-engineer-enhanced": {"cost_usd": 3.5}},
        )
        self.assertTrue(flag.triggered)
        self.assertFalse(any("SkillMeat ranking" in e for e in flag.evidence_refs))

    def test_no_evidence_added_when_the_flag_does_not_trigger(self) -> None:
        flag = evaluate_stack_ineffectiveness(
            ["s1"], {"s1": ["backend/foo.py"]}, [], feature_scope_available=True,
            artifact_rankings={"backend-typescript-architect": {"cost_usd": 3.5}},
        )
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.evidence_refs, [])


# ── T3-004 (AC-P3.2): end-to-end wiring through get_review ──────────────────


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        _ = context, action, resource
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def __init__(self, project):
        self.project = project

    def get_project(self, project_id):
        if self.project and getattr(self.project, "id", "") == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project

    def resolve_scope(self, project_id=None):
        if self.project is None:
            return None, None
        resolved_id = project_id or self.project.id
        return None, ProjectScope(
            project_id=resolved_id,
            project_name=self.project.name,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


class _Rankings:
    """Read-only fake mirroring ``artifact_ranking``'s ``list_rankings`` shape."""

    def __init__(self, rows_by_project: dict[str, list[dict]]) -> None:
        self._rows_by_project = rows_by_project

    async def list_rankings(self, *, project_id: str, **_kwargs) -> dict:
        rows = self._rows_by_project.get(project_id, [])
        return {"rows": rows, "total": len(rows)}


class _IntegrationSnapshots:
    def __init__(self, rankings: _Rankings) -> None:
        self._rankings = rankings

    def artifact_rankings(self):
        return self._rankings

    def artifact_snapshots(self):
        return types.SimpleNamespace()


class _Storage:
    def __init__(self, *, documents_repo, sessions_repo, links_repo, db, ranking_rows_by_project=None):
        self.db = db
        self._documents_repo = documents_repo
        self._sessions_repo = sessions_repo
        self._links_repo = links_repo
        self._integration_snapshots = _IntegrationSnapshots(_Rankings(ranking_rows_by_project or {}))

    def documents(self):
        return self._documents_repo

    def sessions(self):
        return self._sessions_repo

    def entity_links(self):
        return self._links_repo

    def integration_snapshots(self):
        return self._integration_snapshots


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


def _doc_row(doc_id: str = "doc-1", project_id: str = "project-1") -> dict:
    return {"id": doc_id, "project_id": project_id, "frontmatter_json": "{}"}


def _direct_session_link(doc_id: str, session_id: str) -> dict:
    return {
        "source_type": "document",
        "source_id": doc_id,
        "target_type": "session",
        "target_id": session_id,
        "confidence": 1.0,
        "metadata_json": json.dumps({"linkStrategy": "explicit_session_ref"}),
    }


def _session_row(session_id: str = "session-1") -> dict:
    return {
        "id": session_id,
        "subagent_type": "",
        "agents_used_json": "[]",
        "context_window_size": 0,
        "context_utilization_pct": 0,
        "current_context_tokens": 0,
    }


class FifthFlagEndToEndTests(unittest.IsolatedAsyncioTestCase):
    """T3-004: below / at / above threshold x with / without a SkillMeat ranking, via ``get_review``."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        # Independent SQLite connection MUST issue PRAGMA busy_timeout = 30000.
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self.reviews_repo = SqliteAarReviewsRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _seed_history(self, count: int) -> None:
        """Seed *count* distinct historical AAR documents, each triggering ``missing_artifacts``."""
        for i in range(count):
            await self.reviews_repo.upsert(_seed_row(doc_id=f"hist-doc-{i}", session_id=f"hist-session-{i}"))

    def _build_ports(self, *, ranking_rows: list[dict] | None = None) -> CorePorts:
        project = types.SimpleNamespace(id="project-1", name="Project 1")
        documents_repo = types.SimpleNamespace(get_by_id=AsyncMock(return_value=_doc_row()))
        sessions_repo = types.SimpleNamespace(
            get_by_id=AsyncMock(return_value=_session_row()),
            # dominant extension .py -> specialist "backend-typescript-architect"
            get_file_updates=AsyncMock(return_value=[{"file_path": "backend/foo.py"}]),
        )
        links_repo = types.SimpleNamespace(
            get_links_for=AsyncMock(return_value=[_direct_session_link("doc-1", "session-1")])
        )
        return CorePorts(
            identity_provider=_IdentityProvider(),
            authorization_policy=_AuthorizationPolicy(),
            workspace_registry=_WorkspaceRegistry(project),
            storage=_Storage(
                documents_repo=documents_repo,
                sessions_repo=sessions_repo,
                links_repo=links_repo,
                db=self.db,
                ranking_rows_by_project={"project-1": ranking_rows or []},
            ),
            job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
            integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
        )

    async def _get_fifth_flag(self, *, ranking_rows: list[dict] | None = None):
        # bypass_cache=True: successive tests in this class re-use the same
        # document_id ("doc-1") against differently-seeded `aar_reviews`
        # history/rankings, and the query cache's data-version fingerprint
        # does not track that table -- without this, a later test could
        # observe an earlier test's stale cached DTO.
        result = await AARReviewQueryService().get_review(
            _context(), self._build_ports(ranking_rows=ranking_rows), "doc-1", bypass_cache=True,
        )
        flag = next(f for f in result.flags if f.flag_id == "new_skill_or_agent_need")
        return result, flag

    # -- below threshold --

    async def test_below_threshold_without_ranking_does_not_trigger(self) -> None:
        await self._seed_history(2)
        with patch("backend.config.CCDASH_AAR_NEW_SKILL_THRESHOLD", 3), \
             patch("backend.config.CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS", 30):
            _result, flag = await self._get_fifth_flag()
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.evidence_refs, [])

    async def test_below_threshold_with_matching_ranking_still_does_not_trigger(self) -> None:
        await self._seed_history(2)
        ranking_rows = [{"artifact_id": "backend-typescript-architect", "cost_usd": 1.0, "period": "30d"}]
        with patch("backend.config.CCDASH_AAR_NEW_SKILL_THRESHOLD", 3), \
             patch("backend.config.CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS", 30):
            _result, flag = await self._get_fifth_flag(ranking_rows=ranking_rows)
        self.assertFalse(flag.triggered)
        self.assertEqual(flag.evidence_refs, [])

    # -- at threshold --

    async def test_at_threshold_without_ranking_triggers(self) -> None:
        await self._seed_history(3)
        with patch("backend.config.CCDASH_AAR_NEW_SKILL_THRESHOLD", 3), \
             patch("backend.config.CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS", 30):
            result, flag = await self._get_fifth_flag()
        self.assertTrue(flag.triggered)
        self.assertEqual(flag.severity, "medium")
        self.assertEqual(len(flag.evidence_refs), 1)
        self.assertEqual(result.triage_verdict, "deep_review_recommended")

    async def test_at_threshold_with_matching_ranking_triggers_with_extra_evidence(self) -> None:
        await self._seed_history(3)
        ranking_rows = [
            {"artifact_id": "backend-typescript-architect", "cost_usd": 2.5, "efficiency_score": 0.6, "period": "30d"},
        ]
        with patch("backend.config.CCDASH_AAR_NEW_SKILL_THRESHOLD", 3), \
             patch("backend.config.CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS", 30):
            result, flag = await self._get_fifth_flag(ranking_rows=ranking_rows)
        self.assertTrue(flag.triggered)
        self.assertEqual(len(flag.evidence_refs), 2)
        self.assertTrue(
            any("consider a specialist for domain 'backend-typescript-architect'" in e for e in flag.evidence_refs)
        )
        self.assertEqual(result.triage_verdict, "deep_review_recommended")

    # -- above threshold --

    async def test_above_threshold_without_ranking_triggers(self) -> None:
        await self._seed_history(6)
        with patch("backend.config.CCDASH_AAR_NEW_SKILL_THRESHOLD", 3), \
             patch("backend.config.CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS", 30):
            _result, flag = await self._get_fifth_flag()
        self.assertTrue(flag.triggered)
        self.assertEqual(len(flag.evidence_refs), 1)
        self.assertIn("6 generic-agent/missing-artifact trigger", flag.evidence_refs[0])

    async def test_above_threshold_with_matching_ranking_triggers_with_extra_evidence(self) -> None:
        await self._seed_history(6)
        ranking_rows = [{"artifact_id": "backend-typescript-architect", "cost_usd": 9.9, "period": "30d"}]
        with patch("backend.config.CCDASH_AAR_NEW_SKILL_THRESHOLD", 3), \
             patch("backend.config.CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS", 30):
            _result, flag = await self._get_fifth_flag(ranking_rows=ranking_rows)
        self.assertTrue(flag.triggered)
        self.assertEqual(len(flag.evidence_refs), 2)
        self.assertTrue(any("cost_usd=9.9" in e for e in flag.evidence_refs))

    # -- verdict combinator is not special-cased for the 5th flag --

    async def test_fifth_flag_participates_in_the_generic_verdict_mapping_unchanged(self) -> None:
        await self._seed_history(6)
        with patch("backend.config.CCDASH_AAR_NEW_SKILL_THRESHOLD", 3), \
             patch("backend.config.CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS", 30):
            result, _flag = await self._get_fifth_flag()
        self.assertEqual(result.triage_verdict, "deep_review_recommended")
        self.assertTrue(any("new_skill_or_agent_need" in reason for reason in result.reasons))

    async def test_rows_from_a_different_project_are_excluded_from_the_aggregate(self) -> None:
        await self.reviews_repo.upsert(_seed_row(doc_id="other-proj-doc", session_id="s-1", project_id="project-2"))
        with patch("backend.config.CCDASH_AAR_NEW_SKILL_THRESHOLD", 1), \
             patch("backend.config.CCDASH_AAR_NEW_SKILL_LOOKBACK_DAYS", 30):
            _result, flag = await self._get_fifth_flag()
        self.assertFalse(flag.triggered, "a different project's persisted rows must not feed this project's aggregate")


if __name__ == "__main__":
    unittest.main()
