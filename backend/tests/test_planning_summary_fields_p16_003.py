"""Backend coverage for SC-16.3 planning summary fields and document-driven
cache invalidation.

Complements ``test_planning_query_service.py`` with end-to-end DTO shape
assertions and integration-level invalidation coverage:

1. ``status_counts`` — verifies the ``PlanningStatusCounts`` bucket payload
   on the ``ProjectPlanningSummaryDTO`` response (P13-001).
2. Ctx / phase fields — verifies ``ctx_per_phase`` on the summary DTO and
   phase-level raw/effective status / planning_status on
   ``PhaseContextItem`` entries returned by ``get_feature_planning_context``
   (P13-001 / P13-002).
3. Token availability info — verifies ``token_telemetry`` is always present
   on the summary DTO with the ``unavailable`` source when no session
   aggregation is available (P13-001).
4. Active-first filtering — verifies the default ordering and terminal
   exclusion semantics of ``feature_summaries`` (P12-001).
5. Document-driven invalidation — inserting/updating rows in the
   ``documents`` table advances the fingerprint (documents table is part
   of ``_FINGERPRINT_TABLES`` in ``backend/application/services/agent_queries/cache.py``)
   and triggers a cache miss on subsequent planning summary calls
   (P12-003).
"""
from __future__ import annotations

import json
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.application.context import (
    Principal,
    ProjectScope,
    RequestContext,
    TraceContext,
)
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.cache import clear_cache
from backend.application.services.agent_queries.planning import PlanningQueryService
from backend.models import Feature, FeaturePhase, LinkedDocument


# ── Shared fixture helpers (mirror test_planning_query_service.py style) ─────


_PROJECT_ID = "project-p16-003"


def _phase(
    *,
    number: str = "1",
    status: str = "backlog",
    total: int = 2,
    completed: int = 0,
) -> FeaturePhase:
    return FeaturePhase(
        id=f"feat:phase-{number}",
        phase=number,
        title=f"Phase {number}",
        status=status,
        progress=0,
        totalTasks=total,
        completedTasks=completed,
        deferredTasks=0,
        tasks=[],
        phaseBatches=[],
    )


def _feature(
    *,
    fid: str,
    name: str,
    status: str = "backlog",
    phases: list | None = None,
    linked_docs: list | None = None,
) -> Feature:
    return Feature(
        id=fid,
        name=name,
        status=status,
        totalTasks=0,
        completedTasks=0,
        category="enhancement",
        tags=[],
        updatedAt="2026-04-14T10:00:00+00:00",
        linkedDocs=linked_docs or [],
        phases=phases or [],
        relatedFeatures=[],
    )


def _feature_row(feature: Feature) -> dict:
    return {
        "id": feature.id,
        "name": feature.name,
        "status": feature.status,
        "total_tasks": feature.totalTasks,
        "completed_tasks": feature.completedTasks,
        "deferred_tasks": feature.deferredTasks,
        "category": feature.category,
        "updated_at": feature.updatedAt,
        "data_json": json.dumps(
            {
                "id": feature.id,
                "name": feature.name,
                "status": feature.status,
                "phases": [p.model_dump() for p in feature.phases],
                "linkedDocs": [d.model_dump() for d in feature.linkedDocs],
                "linkedFeatures": [],
            }
        ),
    }


def _doc_row(
    *,
    did: str = "doc-1",
    title: str = "Doc",
    doc_type: str = "implementation_plan",
    file_path: str = "docs/plan.md",
    feature_slug: str = "feat-1",
    updated_at: str = "2026-04-14T10:00:00+00:00",
) -> dict:
    return {
        "id": did,
        "title": title,
        "doc_type": doc_type,
        "file_path": file_path,
        "feature_slug_canonical": feature_slug,
        "feature_slug_hint": feature_slug,
        "updated_at": updated_at,
        "status": "in-progress",
        "metadata_json": "{}",
        "frontmatter_json": "{}",
    }


class _IdentityProvider:
    async def get_principal(self, metadata, *, runtime_profile):
        return Principal(subject="test", display_name="Test", auth_mode="test")


class _AuthorizationPolicy:
    async def authorize(self, context, *, action, resource=None):
        return AuthorizationDecision(allowed=True)


class _WorkspaceRegistry:
    def __init__(self, project):
        self._project = project

    def get_project(self, project_id):
        if self._project and getattr(self._project, "id", "") == project_id:
            return self._project
        return None

    def get_active_project(self):
        return self._project

    def resolve_scope(self, project_id=None):
        if self._project is None:
            return None, None
        resolved_id = project_id or self._project.id
        return None, ProjectScope(
            project_id=resolved_id,
            project_name=self._project.name,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


class _Storage:
    def __init__(self, *, features_repo, docs_repo, db=None):
        self.db = db or object()
        self._features_repo = features_repo
        self._docs_repo = docs_repo

    def features(self):
        return self._features_repo

    def documents(self):
        return self._docs_repo

    def sessions(self):
        return types.SimpleNamespace(list_paginated=AsyncMock(return_value=[]))

    def sync_state(self):
        return types.SimpleNamespace(list_all=AsyncMock(return_value=[]))

    def entity_links(self):
        return types.SimpleNamespace(get_links_for=AsyncMock(return_value=[]))


def _context(project_id: str = _PROJECT_ID) -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="Project P16-003",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-p16-003"),
    )


def _ports(*, features_repo, docs_repo, db=None, project=None) -> CorePorts:
    resolved_project = project or types.SimpleNamespace(
        id=_PROJECT_ID, name="Project P16-003"
    )
    return CorePorts(
        identity_provider=_IdentityProvider(),
        authorization_policy=_AuthorizationPolicy(),
        workspace_registry=_WorkspaceRegistry(resolved_project),
        storage=_Storage(features_repo=features_repo, docs_repo=docs_repo, db=db),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


# ── Tests: summary DTO field shape ──────────────────────────────────────────


class PlanningSummaryStatusCountsShapeTests(unittest.IsolatedAsyncioTestCase):
    """SC-16.3 — ``status_counts`` on the summary DTO has all eight buckets."""

    def setUp(self) -> None:
        clear_cache()

    async def test_status_counts_field_populated_with_all_buckets(self) -> None:
        # Features with status=done/deferred must have a terminal phase so the
        # planning projection leaves their effective_status terminal (otherwise
        # the reversal heuristic rewrites them to ``backlog`` and they land in
        # the ``shaping`` bucket instead of ``completed`` / ``deferred``).
        features = [
            _feature(fid="feat-active", name="Active", status="in-progress"),
            _feature(fid="feat-review", name="Review", status="review"),
            _feature(fid="feat-planned", name="Planned", status="planned"),
            _feature(fid="feat-draft", name="Draft", status="draft"),
            _feature(
                fid="feat-done",
                name="Done",
                status="done",
                phases=[_phase(number="1", status="done", total=1, completed=1)],
            ),
            _feature(
                fid="feat-deferred",
                name="Deferred",
                status="deferred",
                phases=[_phase(number="1", status="deferred", total=1, completed=0)],
            ),
            _feature(fid="feat-backlog", name="Backlog", status="backlog"),
        ]
        rows = [_feature_row(f) for f in features]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports, include_terminal=True, limit=100
        )

        counts = result.status_counts
        self.assertIsNotNone(counts, "status_counts must be populated on summary DTO")
        # All eight bucket fields must be present on the pydantic model.
        for field_name in (
            "shaping",
            "planned",
            "active",
            "blocked",
            "review",
            "completed",
            "deferred",
            "stale_or_mismatched",
        ):
            self.assertTrue(
                hasattr(counts, field_name),
                f"status_counts must expose bucket '{field_name}' (P13-001)",
            )
            self.assertIsInstance(getattr(counts, field_name), int)

        # Sum across buckets must equal total_feature_count (mutually exclusive).
        total = (
            counts.shaping
            + counts.planned
            + counts.active
            + counts.blocked
            + counts.review
            + counts.completed
            + counts.deferred
            + counts.stale_or_mismatched
        )
        self.assertEqual(total, result.total_feature_count)

        # Specific buckets that must land given the input statuses.
        self.assertGreaterEqual(counts.active, 1)
        self.assertGreaterEqual(counts.review, 1)
        self.assertGreaterEqual(counts.planned, 2)  # planned + draft
        self.assertGreaterEqual(counts.completed, 1)
        self.assertGreaterEqual(counts.deferred, 1)

    async def test_status_counts_present_even_when_project_empty(self) -> None:
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        self.assertIsNotNone(result.status_counts)
        self.assertEqual(result.status_counts.active, 0)
        self.assertEqual(result.status_counts.blocked, 0)


class PlanningSummaryCtxPerPhaseShapeTests(unittest.IsolatedAsyncioTestCase):
    """SC-16.3 — ``ctx_per_phase`` populated on summary DTO (P13-001)."""

    def setUp(self) -> None:
        clear_cache()

    async def test_ctx_per_phase_reports_backend_source_when_phases_present(self) -> None:
        feat = _feature(
            fid="feat-ctx",
            name="Ctx Feature",
            status="in-progress",
            phases=[
                _phase(number="1", status="in-progress"),
                _phase(number="2", status="backlog"),
            ],
        )
        rows = [_feature_row(feat)]
        doc_rows = [
            _doc_row(
                did="ctx-doc-1",
                title="Context Note",
                doc_type="context",
                file_path="docs/context/feat-ctx.md",
                feature_slug="feat-ctx",
            ),
        ]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=doc_rows),
            list_paginated=AsyncMock(return_value=doc_rows),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports, include_terminal=True, limit=100
        )

        ratio = result.ctx_per_phase
        self.assertIsNotNone(ratio)
        self.assertEqual(ratio.source, "backend")
        self.assertEqual(ratio.phase_count, 2)
        self.assertGreaterEqual(ratio.context_count, 1)
        self.assertIsNotNone(ratio.ratio)

    async def test_ctx_per_phase_unavailable_when_no_phases(self) -> None:
        feat = _feature(fid="feat-nophase", name="NoPhase", status="in-progress")
        rows = [_feature_row(feat)]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        self.assertIsNotNone(result.ctx_per_phase)
        self.assertEqual(result.ctx_per_phase.source, "unavailable")
        self.assertIsNone(result.ctx_per_phase.ratio)
        self.assertEqual(result.ctx_per_phase.phase_count, 0)


class PlanningSummaryTokenTelemetryShapeTests(unittest.IsolatedAsyncioTestCase):
    """SC-16.3 — ``token_telemetry`` surfaced on summary DTO (P13-001)."""

    def setUp(self) -> None:
        clear_cache()

    async def test_token_telemetry_present_with_unavailable_source_when_no_data(
        self,
    ) -> None:
        feat = _feature(fid="feat-tok", name="Token Feature", status="in-progress")
        rows = [_feature_row(feat)]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        telemetry = result.token_telemetry
        self.assertIsNotNone(telemetry, "token_telemetry must appear on summary DTO")
        self.assertEqual(telemetry.source, "unavailable")
        self.assertIsNone(telemetry.total_tokens)
        self.assertEqual(telemetry.by_model_family, [])


class PlanningSummaryActiveFirstOrderingTests(unittest.IsolatedAsyncioTestCase):
    """SC-16.3 — default ``active_first=True`` ordering (P12-001)."""

    def setUp(self) -> None:
        clear_cache()

    async def test_active_first_default_sorts_active_before_planned(self) -> None:
        # Intentionally insert in non-priority order to catch stable-sort regressions.
        features = [
            _feature(fid="feat-draft", name="Draft", status="draft"),
            _feature(fid="feat-active", name="Active", status="in-progress"),
            _feature(fid="feat-review", name="Review", status="review"),
            _feature(fid="feat-planned", name="Planned", status="planned"),
        ]
        rows = [_feature_row(f) for f in features]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )

        ordered_ids = [item.feature_id for item in result.feature_summaries]
        # Active must come before planned; draft is terminal-filtered by default? No,
        # draft is rank 4 (non-terminal). Terminal filter excludes done/deferred only.
        self.assertEqual(ordered_ids[0], "feat-active")
        # Review (rank 3) must come after active (rank 0) but before draft (rank 4).
        self.assertLess(ordered_ids.index("feat-active"), ordered_ids.index("feat-review"))
        self.assertLess(ordered_ids.index("feat-review"), ordered_ids.index("feat-draft"))

    async def test_terminal_excluded_by_default(self) -> None:
        # Terminal phases keep the projected effective_status terminal so the
        # default ``include_terminal=False`` filter can exclude them.
        features = [
            _feature(fid="feat-active", name="Active", status="in-progress"),
            _feature(
                fid="feat-done",
                name="Done",
                status="done",
                phases=[_phase(number="1", status="done", total=1, completed=1)],
            ),
            _feature(
                fid="feat-deferred",
                name="Deferred",
                status="deferred",
                phases=[_phase(number="1", status="deferred", total=1, completed=0)],
            ),
        ]
        rows = [_feature_row(f) for f in features]
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=rows),
            get_by_id=AsyncMock(return_value=None),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        result = await PlanningQueryService().get_project_planning_summary(
            _context(), ports
        )
        ids = {item.feature_id for item in result.feature_summaries}
        self.assertIn("feat-active", ids)
        self.assertNotIn("feat-done", ids)
        self.assertNotIn("feat-deferred", ids)


# ── Tests: feature context phase fields (ctx/phase fields per P13-002) ──────


class FeaturePlanningContextPhaseFieldsTests(unittest.IsolatedAsyncioTestCase):
    """SC-16.3 — PhaseContextItem exposes raw/effective status + planning_status."""

    def setUp(self) -> None:
        clear_cache()

    async def test_phase_entries_include_ctx_phase_fields(self) -> None:
        feat = _feature(
            fid="feat-phases",
            name="Phase Fields Feature",
            status="in-progress",
            phases=[
                _phase(number="1", status="in-progress", total=3, completed=1),
                _phase(number="2", status="backlog", total=2, completed=0),
            ],
        )
        row = _feature_row(feat)
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with patch(
            "backend.application.services.agent_queries.planning.load_execution_documents",
            new=AsyncMock(return_value=[]),
        ):
            result = await PlanningQueryService().get_feature_planning_context(
                _context(), ports, feature_id="feat-phases"
            )

        self.assertEqual(len(result.phases), 2)
        for phase_item in result.phases:
            # Each phase entry must expose the P13-002 ctx fields.
            self.assertTrue(phase_item.phase_token)
            self.assertTrue(phase_item.phase_title)
            self.assertIsInstance(phase_item.raw_status, str)
            self.assertIsInstance(phase_item.effective_status, str)
            self.assertIsInstance(phase_item.mismatch_state, str)
            # planning_status must be a dict (possibly empty) — never None.
            self.assertIsInstance(phase_item.planning_status, dict)
            # Task counters surfaced at the phase level.
            self.assertIsInstance(phase_item.total_tasks, int)
            self.assertIsInstance(phase_item.completed_tasks, int)

    async def test_feature_context_exposes_token_metadata_fields(self) -> None:
        """Feature context DTO surfaces token_usage_by_model + total_tokens (P13-001 token availability)."""
        feat = _feature(
            fid="feat-tok-ctx",
            name="Token Context",
            status="in-progress",
            phases=[_phase(number="1", status="in-progress")],
        )
        row = _feature_row(feat)
        features_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[row]),
            get_by_id=AsyncMock(return_value=row),
        )
        docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(return_value=[]),
            list_paginated=AsyncMock(return_value=[]),
        )
        ports = _ports(features_repo=features_repo, docs_repo=docs_repo)

        with patch(
            "backend.application.services.agent_queries.planning.load_execution_documents",
            new=AsyncMock(return_value=[]),
        ):
            result = await PlanningQueryService().get_feature_planning_context(
                _context(), ports, feature_id="feat-tok-ctx"
            )

        # Token metadata fields must be present on the DTO regardless of value.
        self.assertTrue(hasattr(result, "total_tokens"))
        self.assertTrue(hasattr(result, "token_usage_by_model"))
        self.assertIsNotNone(result.token_usage_by_model)


# ── Tests: document-driven cache invalidation (P12-003) ─────────────────────


_CREATE_SESSIONS = """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        status TEXT,
        updated_at TEXT
    )
"""
_CREATE_FEATURES = """
    CREATE TABLE IF NOT EXISTS features (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        name TEXT,
        feature_slug TEXT,
        status TEXT,
        updated_at TEXT
    )
"""
_CREATE_FEATURE_PHASES = """
    CREATE TABLE IF NOT EXISTS feature_phases (
        id TEXT PRIMARY KEY,
        feature_id TEXT NOT NULL,
        phase TEXT NOT NULL,
        title TEXT DEFAULT '',
        status TEXT DEFAULT 'backlog',
        progress INTEGER DEFAULT 0,
        total_tasks INTEGER DEFAULT 0,
        completed_tasks INTEGER DEFAULT 0
    )
"""
_CREATE_DOCUMENTS = """
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        title TEXT NOT NULL,
        file_path TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        doc_type TEXT DEFAULT '',
        updated_at TEXT DEFAULT '',
        last_modified TEXT DEFAULT ''
    )
"""
_CREATE_ENTITY_LINKS = """
    CREATE TABLE IF NOT EXISTS entity_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        link_type TEXT DEFAULT 'related',
        created_at TEXT NOT NULL
    )
"""
_CREATE_PLANNING_WORKTREE_CONTEXTS = """
    CREATE TABLE IF NOT EXISTS planning_worktree_contexts (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        feature_id TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'draft',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""


async def _setup_schema(db: aiosqlite.Connection) -> None:
    for stmt in (
        _CREATE_SESSIONS,
        _CREATE_FEATURES,
        _CREATE_FEATURE_PHASES,
        _CREATE_DOCUMENTS,
        _CREATE_ENTITY_LINKS,
        _CREATE_PLANNING_WORKTREE_CONTEXTS,
    ):
        await db.execute(stmt)
    await db.commit()


async def _insert_feature_db(
    db: aiosqlite.Connection, feature_id: str, updated_at: str
) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO features (id, project_id, name, feature_slug, status, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (feature_id, _PROJECT_ID, feature_id, feature_id, "in-progress", updated_at),
    )
    await db.commit()


async def _insert_document_db(
    db: aiosqlite.Connection,
    *,
    doc_id: str,
    title: str,
    file_path: str,
    updated_at: str,
) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO documents "
        "(id, project_id, title, file_path, status, doc_type, updated_at, last_modified) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (doc_id, _PROJECT_ID, title, file_path, "active", "implementation_plan", updated_at, updated_at),
    )
    await db.commit()


async def _bump_document_updated_at(
    db: aiosqlite.Connection, doc_id: str, updated_at: str
) -> None:
    await db.execute(
        "UPDATE documents SET updated_at = ? WHERE id = ?",
        (updated_at, doc_id),
    )
    await db.commit()


class PlanningSummaryDocumentDrivenInvalidationTests(unittest.IsolatedAsyncioTestCase):
    """SC-16.3 — touching the documents table invalidates planning summary cache (P12-003).

    The fingerprint in ``backend/application/services/agent_queries/cache.py``
    includes ``MAX(documents.updated_at)`` scoped by project_id (see
    ``_FINGERPRINT_TABLES``).  When a planning doc is added or updated on
    disk → DB, the next planning summary call must recompute.
    """

    async def asyncSetUp(self) -> None:
        clear_cache()
        self._db = await aiosqlite.connect(":memory:")
        self._db.row_factory = aiosqlite.Row
        await _setup_schema(self._db)

        self._feature_id = "feat-doc-inv"
        await _insert_feature_db(
            self._db, self._feature_id, "2026-04-14T08:00:00+00:00"
        )

        feat = _feature(
            fid=self._feature_id,
            name="Doc-Invalidation Feature",
            status="in-progress",
            phases=[_phase(number="1", status="in-progress")],
        )
        self._feature_rows = [_feature_row(feat)]
        self._doc_rows: list[dict] = []

        self._features_repo = types.SimpleNamespace(
            list_all=AsyncMock(side_effect=lambda _pid: list(self._feature_rows)),
            get_by_id=AsyncMock(return_value=self._feature_rows[0]),
        )
        # The docs repo returns the current snapshot of self._doc_rows so we
        # can mutate it alongside DB inserts to keep both in lockstep.
        self._docs_repo = types.SimpleNamespace(
            list_all=AsyncMock(side_effect=lambda _pid: list(self._doc_rows)),
            list_paginated=AsyncMock(
                side_effect=lambda _pid, _off, _lim, _opts: list(self._doc_rows)
            ),
        )

        self._ports = _ports(
            features_repo=self._features_repo,
            docs_repo=self._docs_repo,
            db=self._db,
        )
        self._service = PlanningQueryService()

    async def asyncTearDown(self) -> None:
        await self._db.close()
        clear_cache()

    async def test_first_call_is_miss_second_is_hit(self) -> None:
        """Baseline: unchanged data → second call is served from cache."""
        # First call populates the cache (miss).
        await self._service.get_project_planning_summary(_context(), self._ports)
        miss_call_count = self._features_repo.list_all.await_count

        # Second call with identical inputs should be a hit — list_all not re-invoked.
        await self._service.get_project_planning_summary(_context(), self._ports)
        hit_call_count = self._features_repo.list_all.await_count

        self.assertEqual(
            hit_call_count,
            miss_call_count,
            "Cache hit must not re-invoke features.list_all",
        )

    async def test_new_document_row_invalidates_cache(self) -> None:
        """Inserting a new document row advances MAX(documents.updated_at) →
        next planning summary call is a cache miss (P12-003)."""
        # Prime the cache.
        await self._service.get_project_planning_summary(_context(), self._ports)
        await self._service.get_project_planning_summary(_context(), self._ports)
        baseline_call_count = self._features_repo.list_all.await_count

        # Insert a new planning doc — both in DB (for fingerprint) and in the
        # docs repo snapshot (for the service's doc row consumption).
        new_doc_id = "doc-new"
        new_updated_at = "2026-04-14T12:00:00+00:00"
        await _insert_document_db(
            self._db,
            doc_id=new_doc_id,
            title="New Plan",
            file_path="docs/plan-new.md",
            updated_at=new_updated_at,
        )
        self._doc_rows.append(
            _doc_row(
                did=new_doc_id,
                title="New Plan",
                doc_type="implementation_plan",
                file_path="docs/plan-new.md",
                feature_slug=self._feature_id,
                updated_at=new_updated_at,
            )
        )

        # Next call must be a cache miss — fingerprint changed → features.list_all re-invoked.
        await self._service.get_project_planning_summary(_context(), self._ports)
        post_insert_call_count = self._features_repo.list_all.await_count

        self.assertGreater(
            post_insert_call_count,
            baseline_call_count,
            "Inserting a new document must advance MAX(documents.updated_at) and "
            "invalidate the planning summary cache entry (P12-003).",
        )

    async def test_document_updated_at_bump_invalidates_cache(self) -> None:
        """Updating an existing document's updated_at must also invalidate the cache."""
        # Seed one document in both DB + repo snapshot.
        initial_updated_at = "2026-04-14T08:30:00+00:00"
        await _insert_document_db(
            self._db,
            doc_id="doc-existing",
            title="Existing Plan",
            file_path="docs/plan-existing.md",
            updated_at=initial_updated_at,
        )
        self._doc_rows.append(
            _doc_row(
                did="doc-existing",
                title="Existing Plan",
                doc_type="implementation_plan",
                file_path="docs/plan-existing.md",
                feature_slug=self._feature_id,
                updated_at=initial_updated_at,
            )
        )

        # Prime cache.
        await self._service.get_project_planning_summary(_context(), self._ports)
        await self._service.get_project_planning_summary(_context(), self._ports)
        baseline_call_count = self._features_repo.list_all.await_count

        # Bump the document's updated_at timestamp.
        later = "2026-04-14T13:00:00+00:00"
        await _bump_document_updated_at(self._db, "doc-existing", later)
        self._doc_rows[-1]["updated_at"] = later

        await self._service.get_project_planning_summary(_context(), self._ports)
        post_bump_call_count = self._features_repo.list_all.await_count

        self.assertGreater(
            post_bump_call_count,
            baseline_call_count,
            "Bumping documents.updated_at must advance the fingerprint and "
            "invalidate the planning summary cache entry (P12-003).",
        )


if __name__ == "__main__":
    unittest.main()
