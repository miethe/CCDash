"""Persistence-foundation tests for ``aar_reviews`` (T1-005/T1-006/T1-007/T1-008).

``aar_reviews`` (``ccdash-automated-aar-review-v1`` Phase 1, v42) is the
rollup table persisting one row per ``(aar_document_id, session_id)`` pairing
computed by the existing, already-shipped deterministic triage service
(``backend/application/services/agent_queries/aar_review.py`` ::
``AARReviewQueryService``). This module is the Phase 1 exit-gate coverage for:

1. Dual-DDL column parity (ADR-007 / ``migration_governance.py``) --
   ``aar_reviews`` must be registered in both backend migration-table getters
   and carry a structurally identical column set (after canonical type
   normalization) across SQLite and Postgres, with ZERO
   ``COLUMN_PARITY_DRIFT_ALLOWLIST`` entries (parity-clean by construction,
   mirroring ``research_runs``'s precedent exactly).
2. ADR-007 direct-count assertion: every intended write actually lands a row,
   and upsert-by-``(aar_document_id, session_id)`` never duplicates.
3. T1-008: the one-time backfill hook is idempotent (re-run is a no-op on row
   count) and reuses ``aar_review.py``'s correlate/compute_verdict logic
   verbatim -- this module never reimplements it.

HARD INVARIANT: zero LLM/model calls anywhere on this path -- every fixture
below is a plain dict/dataclass; no model/agent client is imported.

Run as a named module (full collection can hang):
    backend/.venv/bin/python -m pytest backend/tests/test_aar_reviews_repo.py -v
"""
from __future__ import annotations

import json
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import aiosqlite

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.models import AARReviewCorrelation, AARReviewDTO, AARReviewFlag
from backend.db.migration_governance import (
    COLUMN_PARITY_DRIFT_ALLOWLIST,
    column_parity_diff,
    get_column_parity_diff_all,
    get_enterprise_only_postgres_tables,
    get_postgres_migration_tables,
    get_sqlite_migration_tables,
)
from backend.db.repositories.aar_reviews import (
    AAR_REVIEWS_COLUMNS,
    SqliteAarReviewsRepository,
    build_aar_review_row,
    build_aar_review_rows,
)
from backend.db.sqlite_migrations import run_migrations
from backend.scripts.aar_reviews_backfill import backfill_aar_reviews_for_project, looks_like_aar_document


# ── 1. Migration governance: registration + column parity ──────────────────


class AarReviewsMigrationGovernanceTests(unittest.TestCase):
    """aar_reviews registration + static DDL column-parity assertions (T1-005/T1-007)."""

    def test_aar_reviews_registered_in_sqlite_migration_tables(self) -> None:
        self.assertIn("aar_reviews", get_sqlite_migration_tables())

    def test_aar_reviews_registered_in_postgres_migration_tables(self) -> None:
        self.assertIn("aar_reviews", get_postgres_migration_tables())

    def test_aar_reviews_is_not_enterprise_only(self) -> None:
        """aar_reviews is a shared table -- it must exist in SQLite too, never enterprise-only."""
        self.assertNotIn("aar_reviews", get_enterprise_only_postgres_tables())

    def test_aar_reviews_column_parity_diff_is_empty(self) -> None:
        """aar_reviews is parity-clean by construction -- zero structural drift."""
        diff = column_parity_diff("aar_reviews")
        self.assertEqual(
            diff, {}, msg=f"aar_reviews must be column-parity-clean across backends; found drift: {diff}",
        )

    def test_aar_reviews_included_in_global_parity_sweep(self) -> None:
        merged_diff = get_column_parity_diff_all()
        self.assertNotIn(
            "aar_reviews", merged_diff,
            msg=f"aar_reviews introduced drift in the global parity sweep: {merged_diff.get('aar_reviews')}",
        )

    def test_aar_reviews_has_zero_allowlist_entries(self) -> None:
        """aar_reviews must NOT appear in COLUMN_PARITY_DRIFT_ALLOWLIST at all.

        Mirrors the rf_events/research_runs precedent: because aar_reviews is
        parity-clean by construction, allowlisting any (aar_reviews, column)
        pair would silently mask a real future regression.
        """
        entries = {pair for pair in COLUMN_PARITY_DRIFT_ALLOWLIST if pair[0] == "aar_reviews"}
        self.assertEqual(
            entries, set(),
            msg=f"aar_reviews must have zero COLUMN_PARITY_DRIFT_ALLOWLIST entries; found: {sorted(entries)}",
        )

    def test_aar_reviews_column_set_matches_repository_contract(self) -> None:
        """Every column the repository writes (AAR_REVIEWS_COLUMNS) must exist in both DDLs."""
        from backend.db import postgres_migrations, sqlite_migrations
        from backend.db.migration_governance import _backend_table_blocks, _parse_table_columns

        sqlite_cols = set(_parse_table_columns(_backend_table_blocks(sqlite_migrations)["aar_reviews"]))
        pg_cols = set(_parse_table_columns(_backend_table_blocks(postgres_migrations)["aar_reviews"]))

        for col in AAR_REVIEWS_COLUMNS:
            self.assertIn(col, sqlite_cols, msg=f"AAR_REVIEWS_COLUMNS entry '{col}' missing from SQLite DDL")
            self.assertIn(col, pg_cols, msg=f"AAR_REVIEWS_COLUMNS entry '{col}' missing from Postgres DDL")


# ── 2. build_aar_review_row(s) — pure mapping, no DB ────────────────────────


def _make_dto(
    *,
    document_id: str = "doc-1",
    session_ids: list[str] | None = None,
    confidence: float | None = 1.0,
    strategy: str | None = "explicit_session_ref",
    triage_verdict: str | None = "surface_only",
) -> AARReviewDTO:
    session_ids = session_ids if session_ids is not None else ["session-1"]
    return AARReviewDTO(
        status="ok",
        document_id=document_id,
        correlation=AARReviewCorrelation(
            strategy=strategy, confidence=confidence, session_ids=session_ids, feature_id=None,
        ),
        flags=[
            AARReviewFlag(flag_id="context_ballooning", triggered=False, severity="low", rationale="n/a"),
            AARReviewFlag(
                flag_id="missing_artifacts", triggered=True, severity="medium",
                evidence_refs=["docs/foo.md"], rationale="claimed file not found",
            ),
        ],
        triage_verdict=triage_verdict,
        reasons=["1 flag(s) triggered: missing_artifacts"],
        generated_at="2026-07-22T00:00:00+00:00",
        source_refs=[document_id, *session_ids],
    )


class BuildAarReviewRowTests(unittest.TestCase):
    def test_build_row_maps_dto_fields_verbatim(self) -> None:
        dto = _make_dto()
        row = build_aar_review_row(dto, "session-1", project_id="project-1", aar_document_path="docs/aar.md")

        self.assertEqual(row["aar_document_id"], "doc-1")
        self.assertEqual(row["session_id"], "session-1")
        self.assertEqual(row["project_id"], "project-1")
        self.assertEqual(row["aar_document_path"], "docs/aar.md")
        self.assertEqual(json.loads(row["correlation"]), dto.correlation.model_dump())
        self.assertEqual(json.loads(row["flags"]), [flag.model_dump() for flag in dto.flags])
        self.assertEqual(row["triage_verdict"], "surface_only")
        # triage_reasons <- DTO.reasons (deliberate name mapping; not DTO.triage_verdict again)
        self.assertEqual(json.loads(row["triage_reasons"]), dto.reasons)
        # evidence_refs <- DTO.source_refs (deliberate name mapping)
        self.assertEqual(json.loads(row["evidence_refs"]), dto.source_refs)
        self.assertEqual(row["generated_at"], dto.generated_at)
        self.assertIsNone(row["provenance_skill_name"])
        self.assertIsNone(row["provenance_workflow_id"])

    def test_build_row_accepts_guard_input_provenance(self) -> None:
        dto = _make_dto()
        row = build_aar_review_row(
            dto, "session-1", project_id="project-1",
            provenance_skill_name="op-story", provenance_workflow_id="wf-123",
        )
        self.assertEqual(row["provenance_skill_name"], "op-story")
        self.assertEqual(row["provenance_workflow_id"], "wf-123")

    def test_build_rows_fans_out_one_row_per_session_id(self) -> None:
        dto = _make_dto(session_ids=["session-1", "session-2", "session-3"])
        rows = build_aar_review_rows(dto, project_id="project-1")
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            sorted(row["session_id"] for row in rows), ["session-1", "session-2", "session-3"],
        )
        for row in rows:
            self.assertEqual(row["aar_document_id"], "doc-1")

    def test_build_rows_returns_empty_list_when_no_sessions_resolved(self) -> None:
        """No discoverable session pairing => zero rows, never a placeholder row."""
        dto = _make_dto(session_ids=[], confidence=None, strategy=None, triage_verdict="human_triage_required")
        rows = build_aar_review_rows(dto, project_id="project-1")
        self.assertEqual(rows, [])


# ── 3. ADR-007 direct-count assertion + upsert idempotency (SQLite) ────────


class SqliteAarReviewsDirectCountTests(unittest.IsolatedAsyncioTestCase):
    """ADR-007 §4: write N rows, assert direct COUNT(*) == N; upsert stays idempotent."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        # Independent SQLite connection MUST issue PRAGMA busy_timeout = 30000.
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self.repo = SqliteAarReviewsRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _direct_count(self) -> int:
        cursor = await self.db.execute("SELECT COUNT(*) FROM aar_reviews")
        (count,) = await cursor.fetchone()
        return int(count)

    async def test_direct_count_matches_writes(self) -> None:
        """Write N distinct (aar_document_id, session_id) rows; assert COUNT(*) == N."""
        n = 5
        for i in range(n):
            dto = _make_dto(document_id=f"doc-{i}", session_ids=[f"session-{i}"])
            for row in build_aar_review_rows(dto, project_id="project-1"):
                await self.repo.upsert(row)

        self.assertEqual(await self._direct_count(), n)
        self.assertEqual(await self.repo.count_by_project("project-1"), n)

    async def test_direct_count_matches_writes_for_fanned_out_rows(self) -> None:
        """A single document correlating to 3 sessions must land exactly 3 rows."""
        dto = _make_dto(document_id="doc-fanout", session_ids=["s-1", "s-2", "s-3"])
        for row in build_aar_review_rows(dto, project_id="project-1"):
            await self.repo.upsert(row)

        self.assertEqual(await self._direct_count(), 3)
        rows = await self.repo.get_by_document("doc-fanout")
        self.assertEqual(sorted(r["session_id"] for r in rows), ["s-1", "s-2", "s-3"])

    async def test_upsert_idempotency_keeps_count_stable_and_updates_row(self) -> None:
        """Re-upserting the same (aar_document_id, session_id) key twice must not duplicate."""
        dto_first = _make_dto(document_id="doc-x", session_ids=["session-x"], triage_verdict="surface_only")
        row_first = build_aar_review_rows(dto_first, project_id="project-1")[0]
        await self.repo.upsert(row_first)
        self.assertEqual(await self._direct_count(), 1)

        dto_second = _make_dto(
            document_id="doc-x", session_ids=["session-x"], triage_verdict="deep_review_recommended",
        )
        row_second = build_aar_review_rows(dto_second, project_id="project-1")[0]
        await self.repo.upsert(row_second)

        self.assertEqual(await self._direct_count(), 1, "upsert of the same dedup key must not duplicate")
        stored = await self.repo.get_one("doc-x", "session-x")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["triage_verdict"], "deep_review_recommended", "the row must reflect the latest write")

    async def test_upsert_many_writes_every_row(self) -> None:
        dto = _make_dto(document_id="doc-many", session_ids=["a", "b", "c", "d"])
        rows = build_aar_review_rows(dto, project_id="project-1")
        written = await self.repo.upsert_many(rows)
        self.assertEqual(written, 4)
        self.assertEqual(await self._direct_count(), 4)

    async def test_get_by_project_scopes_correctly(self) -> None:
        dto_a = _make_dto(document_id="doc-a", session_ids=["session-a"])
        dto_b = _make_dto(document_id="doc-b", session_ids=["session-b"])
        for row in build_aar_review_rows(dto_a, project_id="project-a"):
            await self.repo.upsert(row)
        for row in build_aar_review_rows(dto_b, project_id="project-b"):
            await self.repo.upsert(row)

        rows_a = await self.repo.get_by_project("project-a")
        self.assertEqual(len(rows_a), 1)
        self.assertEqual(rows_a[0]["aar_document_id"], "doc-a")
        self.assertEqual(await self.repo.count_by_project("project-b"), 1)


# ── 4. looks_like_aar_document — deterministic filename heuristic ──────────


class LooksLikeAarDocumentTests(unittest.TestCase):
    def test_matches_slug_aar_date_convention(self) -> None:
        self.assertTrue(
            looks_like_aar_document({"file_stem": "planning-command-center-v1-aar-2026-05-29"})
        )

    def test_matches_plain_aar_stem(self) -> None:
        self.assertTrue(looks_like_aar_document({"file_stem": "aar"}))

    def test_derives_stem_from_canonical_path_when_file_stem_missing(self) -> None:
        self.assertTrue(
            looks_like_aar_document({"canonical_path": "docs/project_plans/reports/foo-aar-2026-01-01.md"})
        )

    def test_rejects_unrelated_document(self) -> None:
        self.assertFalse(looks_like_aar_document({"file_stem": "implementation-plan"}))

    def test_rejects_empty_document(self) -> None:
        self.assertFalse(looks_like_aar_document({}))


# ── 5. T1-008: backfill idempotency (reuses aar_review.py's correlate/verdict) ──


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="migration", display_name="Migration", auth_mode="test")


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


class _Storage:
    def __init__(self, *, documents_repo, sessions_repo, links_repo, db):
        self.db = db
        self._documents_repo = documents_repo
        self._sessions_repo = sessions_repo
        self._links_repo = links_repo

    def documents(self):
        return self._documents_repo

    def sessions(self):
        return self._sessions_repo

    def entity_links(self):
        return self._links_repo


def _aar_doc_row(doc_id: str = "aar-doc-1", project_id: str = "project-1") -> dict:
    return {
        "id": doc_id,
        "project_id": project_id,
        "file_stem": "planning-command-center-v1-aar-2026-05-29",
        "canonical_path": "docs/project_plans/reports/planning-command-center-v1-aar-2026-05-29.md",
        "file_path": "docs/project_plans/reports/planning-command-center-v1-aar-2026-05-29.md",
        "frontmatter_json": "{}",
    }


def _other_doc_row(doc_id: str = "other-doc-1", project_id: str = "project-1") -> dict:
    return {
        "id": doc_id,
        "project_id": project_id,
        "file_stem": "implementation-plan",
        "canonical_path": "docs/project_plans/implementation_plans/implementation-plan.md",
        "file_path": "docs/project_plans/implementation_plans/implementation-plan.md",
        "frontmatter_json": "{}",
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


def _direct_session_link(doc_id: str, session_id: str) -> dict:
    return {
        "source_type": "document",
        "source_id": doc_id,
        "target_type": "session",
        "target_id": session_id,
        "confidence": 1.0,
        "metadata_json": {"linkStrategy": "task_session_ref"},
    }


def _build_ports(db, *, doc_rows: list[dict], links_by_doc: dict[str, list[dict]]) -> CorePorts:
    project = types.SimpleNamespace(id="project-1", name="Project 1")

    async def _get_by_id(document_id, **_kw):
        for row in doc_rows:
            if row["id"] == document_id:
                return row
        return None

    async def _get_links_for(entity_type, entity_id, link_type=None, **_kw):
        _ = entity_type, link_type
        return links_by_doc.get(entity_id, [])

    documents_repo = types.SimpleNamespace(
        list_all=AsyncMock(return_value=doc_rows),
        get_by_id=AsyncMock(side_effect=_get_by_id),
    )
    sessions_repo = types.SimpleNamespace(
        get_by_id=AsyncMock(return_value=_session_row()),
        get_file_updates=AsyncMock(return_value=[]),
    )
    links_repo = types.SimpleNamespace(get_links_for=AsyncMock(side_effect=_get_links_for))

    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(project),
        storage=_Storage(documents_repo=documents_repo, sessions_repo=sessions_repo, links_repo=links_repo, db=db),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


class AarReviewsBackfillIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    """T1-008: backfill runs idempotently; row count matches the discoverable pair count."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _count(self) -> int:
        cursor = await self.db.execute("SELECT COUNT(*) FROM aar_reviews")
        (count,) = await cursor.fetchone()
        return int(count)

    async def test_backfill_writes_exactly_the_discoverable_pair_count(self) -> None:
        """One AAR doc with one direct session link => exactly one discoverable pair."""
        aar_doc = _aar_doc_row()
        other_doc = _other_doc_row()
        ports = _build_ports(
            self.db,
            doc_rows=[aar_doc, other_doc],
            links_by_doc={aar_doc["id"]: [_direct_session_link(aar_doc["id"], "session-1")]},
        )

        written = await backfill_aar_reviews_for_project(self.db, "project-1", ports=ports)

        self.assertEqual(written, 1, "exactly one discoverable AAR<->session pair")
        self.assertEqual(await self._count(), 1)
        stored = await SqliteAarReviewsRepository(self.db).get_one(aar_doc["id"], "session-1")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["project_id"], "project-1")

    async def test_backfill_skips_non_aar_documents(self) -> None:
        """A document that does not match the AAR naming convention is never processed."""
        other_doc = _other_doc_row()
        ports = _build_ports(self.db, doc_rows=[other_doc], links_by_doc={})

        written = await backfill_aar_reviews_for_project(self.db, "project-1", ports=ports)

        self.assertEqual(written, 0)
        self.assertEqual(await self._count(), 0)

    async def test_backfill_writes_zero_rows_when_correlation_resolves_no_sessions(self) -> None:
        """An AAR doc with no discoverable session link contributes zero rows, not a placeholder."""
        aar_doc = _aar_doc_row()
        ports = _build_ports(self.db, doc_rows=[aar_doc], links_by_doc={})

        written = await backfill_aar_reviews_for_project(self.db, "project-1", ports=ports)

        self.assertEqual(written, 0)
        self.assertEqual(await self._count(), 0)

    async def test_backfill_is_idempotent_across_repeated_calls(self) -> None:
        """Re-running the backfill against the same fixtures must not duplicate rows."""
        aar_doc = _aar_doc_row()
        other_doc = _other_doc_row()
        ports = _build_ports(
            self.db,
            doc_rows=[aar_doc, other_doc],
            links_by_doc={aar_doc["id"]: [_direct_session_link(aar_doc["id"], "session-1")]},
        )

        written_first = await backfill_aar_reviews_for_project(self.db, "project-1", ports=ports)
        count_first = await self._count()

        written_second = await backfill_aar_reviews_for_project(self.db, "project-1", ports=ports)
        count_second = await self._count()

        self.assertEqual(written_first, written_second)
        self.assertEqual(count_first, count_second)
        self.assertEqual(count_second, 1, "re-running must not duplicate the discoverable pair")

    async def test_backfill_handles_multiple_correlated_sessions(self) -> None:
        """A document correlating to multiple sessions fans out into multiple rows, stably."""
        aar_doc = _aar_doc_row()
        links = [
            _direct_session_link(aar_doc["id"], "session-1"),
            _direct_session_link(aar_doc["id"], "session-2"),
        ]
        ports = _build_ports(self.db, doc_rows=[aar_doc], links_by_doc={aar_doc["id"]: links})

        written_first = await backfill_aar_reviews_for_project(self.db, "project-1", ports=ports)
        self.assertEqual(written_first, 2)
        self.assertEqual(await self._count(), 2)

        written_second = await backfill_aar_reviews_for_project(self.db, "project-1", ports=ports)
        self.assertEqual(written_second, 2)
        self.assertEqual(await self._count(), 2, "re-running must not duplicate either pairing")


if __name__ == "__main__":
    unittest.main()
