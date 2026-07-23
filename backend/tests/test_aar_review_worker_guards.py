"""Phase 6 (T6-003/T6-004/T6-006/T6-009/T6-010) guard + worker tests.

Covers:

- T6-009 (AC-P6.3, Guard 1): a synthetic self-referential session (provenance
  ``skill_name == "aar-review"``) fed into the triage input set is EXCLUDED
  UNCONDITIONALLY, independent of any other session data -- both at the pure
  guard-function level and end-to-end through ``AARReviewSweepJob.execute()``.
- T6-010 (AC-P6.3, Guard 2): simulated worker-restart idempotency -- a SECOND,
  entirely fresh ``AARReviewSweepJob`` instance (no shared in-process state
  with the first) reads the SAME persisted ``aar_reviews`` rows and must
  never re-persist an already-triaged ``(aar_document_id, session_id)`` pair.
- Pure guard-function unit coverage for both guards plus the incremental
  document-selection helper.
- The worker's default-off flag gating, coalescing guard, and cache-
  invalidation hook.

HARD INVARIANT: zero LLM/model calls anywhere on this path -- every fixture
below is a plain dict/AsyncMock; no model/agent client is imported.

Run as a named module (full collection can hang):
    backend/.venv/bin/python -m pytest backend/tests/test_aar_review_worker_guards.py -v
"""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend import config
from backend.adapters.jobs.aar_review_sweep_guards import (
    AAR_REVIEW_SELF_SKILL_NAME,
    AAR_REVIEW_SELF_WORKFLOW_ID_PREFIX,
    build_triaged_pair_ledger,
    filter_self_referential_session_ids,
    filter_untriaged_pairs,
    is_already_triaged,
    is_self_referential_session_row,
    select_incremental_documents,
)
from backend.adapters.jobs.aar_review_sweep_job import (
    AARReviewSweepJob,
    looks_like_aar_document,
    resolve_session_workspace_id,
)
from backend.application.context import Principal, ProjectScope
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.db.repositories.aar_reviews import SqliteAarReviewsRepository
from backend.db.repositories.base import DEFAULT_WORKSPACE_ID
from backend.db.sqlite_migrations import run_migrations
from backend.scripts.aar_reviews_backfill import looks_like_aar_document as _script_looks_like_aar_document


# ── 1. Guard 1 (T6-003): pure provenance self-exclusion ─────────────────────


class Guard1PureFunctionTests(unittest.TestCase):
    def test_excludes_session_with_self_skill_name(self) -> None:
        row = {"skill_name": "aar-review", "workflow_id": ""}
        self.assertTrue(is_self_referential_session_row(row))

    def test_excludes_session_with_self_skill_name_case_insensitive(self) -> None:
        row = {"skill_name": "AAR-Review", "workflow_id": ""}
        self.assertTrue(is_self_referential_session_row(row))

    def test_excludes_session_with_reserved_workflow_id_prefix(self) -> None:
        row = {"skill_name": "", "workflow_id": "aar-review-sweep-2026-07-22"}
        self.assertTrue(is_self_referential_session_row(row))

    def test_allows_ordinary_session(self) -> None:
        row = {"skill_name": "dev-execution", "workflow_id": "execute-plan-1"}
        self.assertFalse(is_self_referential_session_row(row))

    def test_allows_session_with_no_provenance_columns(self) -> None:
        self.assertFalse(is_self_referential_session_row({}))

    def test_exclusion_is_unconditional_regardless_of_other_fields(self) -> None:
        """Independent of session 'content' -- only the two provenance columns matter."""
        row = {
            "skill_name": "aar-review",
            "workflow_id": "",
            # Arbitrary other session fields that might otherwise look benign --
            # must never override the provenance-column verdict.
            "subagent_type": "backend-typescript-architect",
            "agents_used_json": '["general-purpose"]',
            "context_utilization_pct": 10.0,
            "id": "session-benign-looking",
        }
        self.assertTrue(is_self_referential_session_row(row))

    def test_filter_partitions_allowed_and_excluded(self) -> None:
        rows = {
            "s-self": {"skill_name": "aar-review"},
            "s-normal": {"skill_name": "dev-execution"},
            "s-prefixed": {"workflow_id": "aar-review-abc"},
        }
        allowed, excluded = filter_self_referential_session_ids(
            ["s-self", "s-normal", "s-prefixed"], rows,
        )
        self.assertEqual(allowed, ["s-normal"])
        self.assertEqual(sorted(excluded), ["s-prefixed", "s-self"])

    def test_filter_treats_missing_row_as_excluded_fail_closed(self) -> None:
        """Karen P6 hardening: a session_id whose provenance row is absent/unfetchable
        must be EXCLUDED, not allowed -- Guard 1 fails CLOSED on undeterminable
        provenance, since it is a self-recursion guard (better to under-triage
        than to risk feeding an aar-review-originated session back into triage)."""
        allowed, excluded = filter_self_referential_session_ids(["s-unknown"], {})
        self.assertEqual(allowed, [])
        self.assertEqual(excluded, ["s-unknown"])

    def test_filter_still_allows_a_session_with_determinable_ordinary_provenance(self) -> None:
        """Fail-closed only bites on UNDETERMINABLE provenance -- a session whose
        row IS resolvable and is NOT aar-review-originated stays allowed."""
        rows = {"s-normal": {"skill_name": "dev-execution", "workflow_id": "execute-plan-1"}}
        allowed, excluded = filter_self_referential_session_ids(["s-normal"], rows)
        self.assertEqual(allowed, ["s-normal"])
        self.assertEqual(excluded, [])

    def test_filter_partitions_mixed_missing_self_ref_and_normal_rows(self) -> None:
        """End-to-end partition sanity check spanning all three provenance states."""
        rows = {
            "s-normal": {"skill_name": "dev-execution"},
            "s-self-ref": {"skill_name": "aar-review"},
            # "s-missing" intentionally has no entry at all.
        }
        allowed, excluded = filter_self_referential_session_ids(
            ["s-normal", "s-self-ref", "s-missing"], rows,
        )
        self.assertEqual(allowed, ["s-normal"])
        self.assertEqual(sorted(excluded), ["s-missing", "s-self-ref"])

    def test_reserved_markers_match_module_constants(self) -> None:
        self.assertEqual(AAR_REVIEW_SELF_SKILL_NAME, "aar-review")
        self.assertEqual(AAR_REVIEW_SELF_WORKFLOW_ID_PREFIX, "aar-review-")


# ── 2. Guard 2 (T6-004): pure idempotent dedup ledger ───────────────────────


class Guard2PureFunctionTests(unittest.TestCase):
    def test_ledger_built_from_persisted_rows(self) -> None:
        rows = [
            {"aar_document_id": "doc-1", "session_id": "s-1"},
            {"aar_document_id": "doc-1", "session_id": "s-2"},
            {"aar_document_id": "doc-2", "session_id": "s-1"},
        ]
        ledger = build_triaged_pair_ledger(rows)
        self.assertEqual(ledger, {("doc-1", "s-1"), ("doc-1", "s-2"), ("doc-2", "s-1")})

    def test_ledger_skips_rows_missing_either_key(self) -> None:
        rows = [{"aar_document_id": "doc-1", "session_id": ""}, {"aar_document_id": "", "session_id": "s-1"}]
        self.assertEqual(build_triaged_pair_ledger(rows), set())

    def test_is_already_triaged(self) -> None:
        ledger = {("doc-1", "s-1")}
        self.assertTrue(is_already_triaged(ledger, "doc-1", "s-1"))
        self.assertFalse(is_already_triaged(ledger, "doc-1", "s-2"))

    def test_filter_untriaged_pairs_partitions_new_vs_already_triaged(self) -> None:
        ledger = {("doc-1", "s-1")}
        candidates = [("doc-1", "s-1"), ("doc-1", "s-2"), ("doc-2", "s-1")]
        new_pairs, already_triaged = filter_untriaged_pairs(candidates, ledger)
        self.assertEqual(sorted(new_pairs), [("doc-1", "s-2"), ("doc-2", "s-1")])
        self.assertEqual(already_triaged, [("doc-1", "s-1")])

    def test_filter_untriaged_pairs_is_deterministic_across_repeated_calls(self) -> None:
        """Idempotency contract: same ledger + same candidates -> same partition, always."""
        ledger = {("doc-1", "s-1")}
        candidates = [("doc-1", "s-1"), ("doc-1", "s-2")]
        first = filter_untriaged_pairs(candidates, ledger)
        second = filter_untriaged_pairs(candidates, ledger)
        self.assertEqual(first, second)


# ── 3. select_incremental_documents — pure watermark scoping ────────────────


class SelectIncrementalDocumentsTests(unittest.TestCase):
    def test_empty_watermark_selects_every_row(self) -> None:
        rows = [{"updated_at": "2026-01-01"}, {"updated_at": "2026-07-01"}]
        self.assertEqual(select_incremental_documents(rows, ""), rows)

    def test_only_rows_newer_than_watermark_are_selected(self) -> None:
        rows = [
            {"id": "old", "updated_at": "2026-01-01T00:00:00Z"},
            {"id": "new", "updated_at": "2026-07-01T00:00:00Z"},
        ]
        selected = select_incremental_documents(rows, "2026-06-01T00:00:00Z")
        self.assertEqual([r["id"] for r in selected], ["new"])

    def test_falls_back_to_created_at_when_updated_at_absent(self) -> None:
        rows = [{"id": "x", "created_at": "2026-07-01T00:00:00Z"}]
        selected = select_incremental_documents(rows, "2026-06-01T00:00:00Z")
        self.assertEqual([r["id"] for r in selected], ["x"])


# ── 4. looks_like_aar_document duplication parity ───────────────────────────


class LooksLikeAarDocumentParityTests(unittest.TestCase):
    """The worker module duplicates (rather than imports) the backfill script's
    heuristic -- assert the two stay byte-for-byte identical in behavior."""

    def test_parity_with_backfill_script_across_fixtures(self) -> None:
        fixtures = [
            {"file_stem": "planning-command-center-v1-aar-2026-05-29"},
            {"file_stem": "aar"},
            {"canonical_path": "docs/project_plans/reports/foo-aar-2026-01-01.md"},
            {"file_stem": "implementation-plan"},
            {},
        ]
        for doc_row in fixtures:
            self.assertEqual(
                looks_like_aar_document(doc_row),
                _script_looks_like_aar_document(doc_row),
                msg=f"parity mismatch for {doc_row}",
            )


# ── 4b. resolve_session_workspace_id (multi-project workspace-routing fix) ──


class ResolveSessionWorkspaceIdTests(unittest.TestCase):
    """Guard 1's session fetch must never use a bare string literal -- it must
    call this named, per-project resolution function instead."""

    def test_falls_back_to_shared_constant_when_project_is_none(self) -> None:
        self.assertEqual(resolve_session_workspace_id(None), DEFAULT_WORKSPACE_ID)

    def test_falls_back_to_shared_constant_when_project_has_no_workspace_id(self) -> None:
        project = types.SimpleNamespace(id="project-1")
        self.assertEqual(resolve_session_workspace_id(project), DEFAULT_WORKSPACE_ID)

    def test_falls_back_to_shared_constant_when_workspace_id_is_blank(self) -> None:
        project = types.SimpleNamespace(id="project-1", workspace_id="   ")
        self.assertEqual(resolve_session_workspace_id(project), DEFAULT_WORKSPACE_ID)

    def test_prefers_a_materialized_per_project_workspace_id(self) -> None:
        project = types.SimpleNamespace(id="project-1", workspace_id="workspace-xyz")
        self.assertEqual(resolve_session_workspace_id(project), "workspace-xyz")


# ── 5. AARReviewSweepJob integration fixtures ───────────────────────────────


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        _ = metadata, runtime_profile
        return Principal(subject="aar-review-sweep", display_name="AAR Review Sweep", auth_mode="test")


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


class _MultiWorkspaceRegistry:
    """Multi-project variant of ``_WorkspaceRegistry`` -- backs
    ``ports.workspace_registry.list_projects()`` with a real, non-empty list
    so ``AARReviewSweepJob._resolve_projects_to_sweep`` fans out across all of
    them (task: sweep multiple registered projects in one tick)."""

    def __init__(self, projects: list[Any]):
        self._by_id = {str(getattr(p, "id", "") or ""): p for p in projects}

    def list_projects(self) -> list[Any]:
        return list(self._by_id.values())

    def get_project(self, project_id):
        return self._by_id.get(project_id)

    def get_active_project(self):
        return next(iter(self._by_id.values()), None)

    def resolve_scope(self, project_id=None):
        project = self._by_id.get(project_id) if project_id else self.get_active_project()
        if project is None:
            return None, None
        return None, ProjectScope(
            project_id=project.id,
            project_name=project.name,
            root_path=Path(f"/tmp/{project.id}"),
            sessions_dir=Path(f"/tmp/{project.id}/sessions"),
            docs_dir=Path(f"/tmp/{project.id}/docs"),
            progress_dir=Path(f"/tmp/{project.id}/progress"),
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


def _aar_doc_row(doc_id: str = "aar-doc-1", project_id: str = "project-1", updated_at: str = "2026-07-22T00:00:00Z") -> dict:
    return {
        "id": doc_id,
        "project_id": project_id,
        "file_stem": "planning-command-center-v1-aar-2026-05-29",
        "canonical_path": f"docs/project_plans/reports/{doc_id}.md",
        "file_path": f"docs/project_plans/reports/{doc_id}.md",
        "frontmatter_json": "{}",
        "updated_at": updated_at,
    }


def _session_row(session_id: str = "session-1", *, skill_name: str = "", workflow_id: str = "") -> dict:
    return {
        "id": session_id,
        "skill_name": skill_name,
        "workflow_id": workflow_id,
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


def _build_ports(
    db,
    *,
    doc_rows: list[dict],
    links_by_doc: dict[str, list[dict]],
    session_rows_by_id: dict[str, dict],
    project_workspace_id: str | None = None,
) -> CorePorts:
    project = types.SimpleNamespace(id="project-1", name="Project 1")
    if project_workspace_id is not None:
        project.workspace_id = project_workspace_id

    async def _get_by_id(document_id, **_kw):
        for row in doc_rows:
            if row["id"] == document_id:
                return row
        return None

    async def _get_links_for(entity_type, entity_id, link_type=None, **_kw):
        _ = entity_type, link_type
        return links_by_doc.get(entity_id, [])

    async def _sessions_get_by_id(session_id, _project_id=None, **_kw):
        return session_rows_by_id.get(session_id)

    documents_repo = types.SimpleNamespace(
        list_all=AsyncMock(return_value=doc_rows),
        get_by_id=AsyncMock(side_effect=_get_by_id),
    )
    sessions_repo = types.SimpleNamespace(
        get_by_id=AsyncMock(side_effect=_sessions_get_by_id),
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


def _build_multi_project_ports(
    db,
    *,
    projects: list[Any],
    doc_rows_by_project: dict[str, list[dict]],
    links_by_doc: dict[str, list[dict]],
    session_rows_by_id: dict[str, dict],
) -> CorePorts:
    """Multi-project counterpart of ``_build_ports`` -- backs
    ``workspace_registry.list_projects()`` with every project passed in, and
    scopes ``documents_repo.list_all(project_id)`` to just that project's
    rows (mirroring the real repository's project_id-filtered query)."""
    all_doc_rows = [row for rows in doc_rows_by_project.values() for row in rows]

    async def _get_by_id(document_id, **_kw):
        for row in all_doc_rows:
            if row["id"] == document_id:
                return row
        return None

    async def _list_all(project_id=None, **_kw):
        if project_id is None:
            return list(all_doc_rows)
        return list(doc_rows_by_project.get(project_id, []))

    async def _get_links_for(entity_type, entity_id, link_type=None, **_kw):
        _ = entity_type, link_type
        return links_by_doc.get(entity_id, [])

    async def _sessions_get_by_id(session_id, _project_id=None, **_kw):
        return session_rows_by_id.get(session_id)

    documents_repo = types.SimpleNamespace(
        list_all=AsyncMock(side_effect=_list_all),
        get_by_id=AsyncMock(side_effect=_get_by_id),
    )
    sessions_repo = types.SimpleNamespace(
        get_by_id=AsyncMock(side_effect=_sessions_get_by_id),
        get_file_updates=AsyncMock(return_value=[]),
    )
    links_repo = types.SimpleNamespace(get_links_for=AsyncMock(side_effect=_get_links_for))

    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_MultiWorkspaceRegistry(projects),
        storage=_Storage(documents_repo=documents_repo, sessions_repo=sessions_repo, links_repo=links_repo, db=db),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


class AARReviewSweepJobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self._flag_patch = patch.object(config, "CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED", True)
        self._flag_patch.start()

    async def asyncTearDown(self) -> None:
        self._flag_patch.stop()
        await self.db.close()

    async def _count(self) -> int:
        cursor = await self.db.execute("SELECT COUNT(*) FROM aar_reviews")
        (count,) = await cursor.fetchone()
        return int(count)

    async def test_disabled_by_default_flag_is_a_no_op(self) -> None:
        self._flag_patch.stop()
        with patch.object(config, "CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED", False):
            aar_doc = _aar_doc_row()
            ports = _build_ports(
                self.db,
                doc_rows=[aar_doc],
                links_by_doc={aar_doc["id"]: [_direct_session_link(aar_doc["id"], "session-1")]},
                session_rows_by_id={"session-1": _session_row("session-1")},
            )
            job = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())
            result = await job.execute()
        self._flag_patch = patch.object(config, "CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED", True)
        self._flag_patch.start()

        self.assertEqual(result.outcome, "disabled")
        self.assertEqual(await self._count(), 0)

    async def test_no_project_bound_is_a_no_op(self) -> None:
        aar_doc = _aar_doc_row()
        ports = _build_ports(self.db, doc_rows=[aar_doc], links_by_doc={}, session_rows_by_id={})
        job = AARReviewSweepJob(ports=ports, project=None)
        result = await job.execute()
        self.assertEqual(result.outcome, "no_project")

    async def test_end_to_end_writes_one_pair_for_one_normal_session(self) -> None:
        aar_doc = _aar_doc_row()
        ports = _build_ports(
            self.db,
            doc_rows=[aar_doc],
            links_by_doc={aar_doc["id"]: [_direct_session_link(aar_doc["id"], "session-1")]},
            session_rows_by_id={"session-1": _session_row("session-1")},
        )
        job = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())

        result = await job.execute()

        self.assertEqual(result.outcome, "success")
        self.assertEqual(result.pairs_written, 1)
        self.assertEqual(result.sessions_excluded_self_referential, 0)
        self.assertEqual(await self._count(), 1)
        stored = await SqliteAarReviewsRepository(self.db).get_one(aar_doc["id"], "session-1")
        self.assertIsNotNone(stored)

    async def test_guard1_excludes_self_referential_session_end_to_end(self) -> None:
        """T6-009: an aar-review-originated session is EXCLUDED unconditionally.

        The document correlates to two sessions -- one ordinary, one whose
        provenance skill_name marks it as aar-review-originated. Only the
        ordinary session's pairing must be persisted.
        """
        aar_doc = _aar_doc_row()
        links = [
            _direct_session_link(aar_doc["id"], "session-normal"),
            _direct_session_link(aar_doc["id"], "session-self-ref"),
        ]
        ports = _build_ports(
            self.db,
            doc_rows=[aar_doc],
            links_by_doc={aar_doc["id"]: links},
            session_rows_by_id={
                "session-normal": _session_row("session-normal"),
                "session-self-ref": _session_row("session-self-ref", skill_name="aar-review"),
            },
        )
        job = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())

        result = await job.execute()

        self.assertEqual(result.sessions_excluded_self_referential, 1)
        self.assertEqual(result.pairs_written, 1)
        self.assertEqual(await self._count(), 1)
        stored_normal = await SqliteAarReviewsRepository(self.db).get_one(aar_doc["id"], "session-normal")
        stored_self_ref = await SqliteAarReviewsRepository(self.db).get_one(aar_doc["id"], "session-self-ref")
        self.assertIsNotNone(stored_normal, "the ordinary session's pairing must be persisted")
        self.assertIsNone(stored_self_ref, "the self-referential session's pairing must NEVER be persisted")

    async def test_guard1_excludes_via_reserved_workflow_id_prefix_end_to_end(self) -> None:
        aar_doc = _aar_doc_row()
        links = [_direct_session_link(aar_doc["id"], "session-swept")]
        ports = _build_ports(
            self.db,
            doc_rows=[aar_doc],
            links_by_doc={aar_doc["id"]: links},
            session_rows_by_id={
                "session-swept": _session_row("session-swept", workflow_id="aar-review-sweep-run-9"),
            },
        )
        job = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())

        result = await job.execute()

        self.assertEqual(result.sessions_excluded_self_referential, 1)
        self.assertEqual(result.pairs_written, 0)
        self.assertEqual(await self._count(), 0)

    async def test_guard1_fails_closed_end_to_end_when_session_row_is_unfetchable(self) -> None:
        """Karen P6 hardening, end-to-end: a session whose provenance row cannot
        be fetched (get_by_id returns None) must be EXCLUDED, never persisted --
        fail-closed, not fail-open."""
        aar_doc = _aar_doc_row()
        links = [_direct_session_link(aar_doc["id"], "session-unfetchable")]
        ports = _build_ports(
            self.db,
            doc_rows=[aar_doc],
            links_by_doc={aar_doc["id"]: links},
            # Deliberately no entry for "session-unfetchable" -> get_by_id
            # resolves to None, simulating a broken/failed provenance lookup.
            session_rows_by_id={},
        )
        job = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())

        result = await job.execute()

        self.assertEqual(result.sessions_excluded_self_referential, 1)
        self.assertEqual(result.pairs_written, 0)
        self.assertEqual(await self._count(), 0, "an undeterminable-provenance session must never be persisted")

    async def test_guard2_worker_restart_idempotency(self) -> None:
        """T6-010: a second, entirely fresh job instance must not re-triage an
        already-persisted (aar_document_id, session_id) pair -- simulating a
        worker restart between two sweep ticks against the SAME database.
        """
        aar_doc = _aar_doc_row()
        ports = _build_ports(
            self.db,
            doc_rows=[aar_doc],
            links_by_doc={aar_doc["id"]: [_direct_session_link(aar_doc["id"], "session-1")]},
            session_rows_by_id={"session-1": _session_row("session-1")},
        )

        # First "process" run.
        job_before_restart = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())
        first_result = await job_before_restart.execute()
        self.assertEqual(first_result.pairs_written, 1)
        self.assertEqual(await self._count(), 1)

        # Simulate a worker restart: a BRAND NEW job instance, sharing nothing
        # in-process with job_before_restart (no shared _in_flight set, no
        # shared _watermarks dict) -- only the persisted DB state carries over.
        job_after_restart = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())
        second_result = await job_after_restart.execute()

        self.assertEqual(second_result.pairs_written, 0, "the pair was already triaged before the restart")
        self.assertEqual(second_result.pairs_already_triaged, 1)
        self.assertEqual(await self._count(), 1, "row count must stay stable across the restart boundary")

    async def test_guard2_still_persists_new_pairs_after_restart(self) -> None:
        """A restart must not block genuinely NEW pairs discovered on the next tick."""
        aar_doc = _aar_doc_row(doc_id="aar-doc-1")
        second_doc = _aar_doc_row(doc_id="aar-doc-2")
        ports = _build_ports(
            self.db,
            doc_rows=[aar_doc, second_doc],
            links_by_doc={
                aar_doc["id"]: [_direct_session_link(aar_doc["id"], "session-1")],
                second_doc["id"]: [_direct_session_link(second_doc["id"], "session-2")],
            },
            session_rows_by_id={
                "session-1": _session_row("session-1"),
                "session-2": _session_row("session-2"),
            },
        )

        job_before_restart = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())
        # First tick only "sees" the first document (simulates it landing
        # before the second was ever written/synced).
        ports.storage.documents().list_all = AsyncMock(return_value=[aar_doc])
        first_result = await job_before_restart.execute()
        self.assertEqual(first_result.pairs_written, 1)

        # Restart: fresh job instance; now BOTH documents are visible.
        ports.storage.documents().list_all = AsyncMock(return_value=[aar_doc, second_doc])
        job_after_restart = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())
        second_result = await job_after_restart.execute()

        self.assertEqual(second_result.pairs_written, 1, "the genuinely new second-document pairing must be persisted")
        self.assertEqual(second_result.pairs_already_triaged, 1, "the first document's pairing must be recognized as already-triaged")
        self.assertEqual(await self._count(), 2)

    async def test_coalescing_guard_returns_coalesced_for_in_flight_key(self) -> None:
        aar_doc = _aar_doc_row()
        ports = _build_ports(
            self.db,
            doc_rows=[aar_doc],
            links_by_doc={aar_doc["id"]: [_direct_session_link(aar_doc["id"], "session-1")]},
            session_rows_by_id={"session-1": _session_row("session-1")},
        )
        job = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())
        job._in_flight.add(("project-1", "scheduled"))

        result = await job.execute(trigger="scheduled")

        self.assertEqual(result.outcome, "coalesced")
        self.assertEqual(await self._count(), 0, "a coalesced dispatch must never write")

    async def test_cache_invalidation_hook_fires_only_on_write(self) -> None:
        aar_doc = _aar_doc_row()
        ports = _build_ports(
            self.db,
            doc_rows=[aar_doc],
            links_by_doc={aar_doc["id"]: [_direct_session_link(aar_doc["id"], "session-1")]},
            session_rows_by_id={"session-1": _session_row("session-1")},
        )
        job = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())

        # aclear_project_cache is imported lazily (call-time, not module-scope)
        # inside AARReviewSweepJob._execute_inner to avoid a runtime_ports
        # import cycle -- patch it at its defining module so the local
        # `from backend.application.services.agent_queries import
        # aclear_project_cache` picks up the patched symbol.
        with patch(
            "backend.application.services.agent_queries.aclear_project_cache", new=AsyncMock(),
        ) as mock_clear:
            result = await job.execute()
            self.assertEqual(result.pairs_written, 1)
            mock_clear.assert_awaited_once_with("project-1")

        # Second run against the same DB: nothing new to write -> cache
        # invalidation must NOT fire again.
        job_second = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())
        with patch(
            "backend.application.services.agent_queries.aclear_project_cache", new=AsyncMock(),
        ) as mock_clear_second:
            second_result = await job_second.execute()
            self.assertEqual(second_result.pairs_written, 0)
            mock_clear_second.assert_not_awaited()

    async def test_guard1_fetch_uses_the_resolved_per_project_workspace_id(self) -> None:
        """The Guard 1 fetch must thread the resolved per-project workspace_id
        through -- never the old bare ``"default-local"`` literal -- so a
        project with a materialized ``workspace_id`` is honored end-to-end."""
        aar_doc = _aar_doc_row()
        ports = _build_ports(
            self.db,
            doc_rows=[aar_doc],
            links_by_doc={aar_doc["id"]: [_direct_session_link(aar_doc["id"], "session-1")]},
            session_rows_by_id={"session-1": _session_row("session-1")},
            project_workspace_id="workspace-xyz",
        )
        job = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())

        result = await job.execute()

        self.assertEqual(result.pairs_written, 1)
        sessions_repo = ports.storage.sessions()
        # AARReviewQueryService.get_review() itself also calls sessions().get_by_id
        # (its own, out-of-scope, still-hardcoded "default-local" lookup that
        # PRODUCES the session_ids Guard 1 filters) plus session_detail's
        # enrichment lookup -- Guard 1's OWN fetch is always the LAST call in
        # AARReviewSweepJob._execute_inner's per-session loop, after
        # get_review() has already returned.
        self.assertGreaterEqual(sessions_repo.get_by_id.await_count, 1)
        last_call = sessions_repo.get_by_id.await_args_list[-1]
        self.assertEqual(last_call.kwargs.get("workspace_id"), "workspace-xyz")

    async def test_guard1_fetch_falls_back_to_shared_constant_without_a_materialized_workspace(self) -> None:
        aar_doc = _aar_doc_row()
        ports = _build_ports(
            self.db,
            doc_rows=[aar_doc],
            links_by_doc={aar_doc["id"]: [_direct_session_link(aar_doc["id"], "session-1")]},
            session_rows_by_id={"session-1": _session_row("session-1")},
        )
        job = AARReviewSweepJob(ports=ports, project=ports.workspace_registry.get_active_project())

        result = await job.execute()

        self.assertEqual(result.pairs_written, 1)
        sessions_repo = ports.storage.sessions()
        self.assertGreaterEqual(sessions_repo.get_by_id.await_count, 1)
        last_call = sessions_repo.get_by_id.await_args_list[-1]
        self.assertEqual(last_call.kwargs.get("workspace_id"), DEFAULT_WORKSPACE_ID)


# ── 6. Multi-project sweep (fan-out correctness) ────────────────────────────


class MultiProjectAARReviewSweepTests(unittest.IsolatedAsyncioTestCase):
    """T?-0xx: AARReviewSweepJob constructed with ``project=None`` must
    enumerate and sweep EVERY registered project via
    ``ports.workspace_registry.list_projects()`` in a single tick -- not just
    whichever single project the worker's sync engine happens to be bound
    to."""

    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self._flag_patch = patch.object(config, "CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED", True)
        self._flag_patch.start()

    async def asyncTearDown(self) -> None:
        self._flag_patch.stop()
        await self.db.close()

    async def _count(self) -> int:
        cursor = await self.db.execute("SELECT COUNT(*) FROM aar_reviews")
        (count,) = await cursor.fetchone()
        return int(count)

    async def test_sweeps_multiple_registered_projects_in_one_tick(self) -> None:
        project_a = types.SimpleNamespace(id="project-a", name="Project A")
        project_b = types.SimpleNamespace(id="project-b", name="Project B")
        doc_a = _aar_doc_row(doc_id="aar-doc-a", project_id="project-a")
        doc_b = _aar_doc_row(doc_id="aar-doc-b", project_id="project-b")
        ports = _build_multi_project_ports(
            self.db,
            projects=[project_a, project_b],
            doc_rows_by_project={"project-a": [doc_a], "project-b": [doc_b]},
            links_by_doc={
                doc_a["id"]: [_direct_session_link(doc_a["id"], "session-a")],
                doc_b["id"]: [_direct_session_link(doc_b["id"], "session-b")],
            },
            session_rows_by_id={
                "session-a": _session_row("session-a"),
                "session-b": _session_row("session-b"),
            },
        )
        # project=None -> the job must enumerate ALL registered projects via
        # the registry rather than being scoped to a single bound project.
        job = AARReviewSweepJob(ports=ports, project=None)

        with patch(
            "backend.application.services.agent_queries.aclear_project_cache", new=AsyncMock(),
        ) as mock_clear:
            result = await job.execute()

        self.assertEqual(result.outcome, "success")
        self.assertTrue(result.success)
        self.assertEqual(result.pairs_written, 2)
        self.assertEqual(result.documents_scanned, 2)
        self.assertEqual(sorted(result.details.get("projectIds", [])), ["project-a", "project-b"])
        self.assertEqual(result.details.get("projectCount"), 2)
        self.assertEqual(await self._count(), 2)

        stored_a = await SqliteAarReviewsRepository(self.db).get_one(doc_a["id"], "session-a")
        stored_b = await SqliteAarReviewsRepository(self.db).get_one(doc_b["id"], "session-b")
        self.assertIsNotNone(stored_a)
        self.assertIsNotNone(stored_b)

        # Cache invalidation fires once per project that actually wrote a row.
        self.assertEqual(mock_clear.await_count, 2)
        mock_clear.assert_any_await("project-a")
        mock_clear.assert_any_await("project-b")

        # Watermarks are tracked independently, per project.
        self.assertIn("project-a", job._watermarks)
        self.assertIn("project-b", job._watermarks)

    async def test_guard2_dedup_ledger_is_scoped_independently_per_project(self) -> None:
        """A pair already triaged in project A must never suppress a
        DIFFERENT pair in project B on the same tick (or vice versa)."""
        project_a = types.SimpleNamespace(id="project-a", name="Project A")
        project_b = types.SimpleNamespace(id="project-b", name="Project B")
        doc_a = _aar_doc_row(doc_id="aar-doc-a", project_id="project-a")
        doc_b = _aar_doc_row(doc_id="aar-doc-b", project_id="project-b")
        ports = _build_multi_project_ports(
            self.db,
            projects=[project_a, project_b],
            doc_rows_by_project={"project-a": [doc_a], "project-b": [doc_b]},
            links_by_doc={
                doc_a["id"]: [_direct_session_link(doc_a["id"], "session-a")],
                doc_b["id"]: [_direct_session_link(doc_b["id"], "session-b")],
            },
            session_rows_by_id={
                "session-a": _session_row("session-a"),
                "session-b": _session_row("session-b"),
            },
        )

        job_before_restart = AARReviewSweepJob(ports=ports, project=None)
        first_result = await job_before_restart.execute()
        self.assertEqual(first_result.pairs_written, 2)

        # Simulate a worker restart: a brand-new job instance sharing no
        # in-process state, reading the SAME persisted ledger.
        job_after_restart = AARReviewSweepJob(ports=ports, project=None)
        second_result = await job_after_restart.execute()

        self.assertEqual(second_result.pairs_written, 0, "both pairs were already triaged before the restart")
        self.assertEqual(second_result.pairs_already_triaged, 2)
        self.assertEqual(await self._count(), 2, "row count must stay stable across the restart boundary")


if __name__ == "__main__":
    unittest.main()
