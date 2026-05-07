import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import aiosqlite

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.services.agent_queries import ArtifactIntelligenceQueryService, SnapshotDiagnosticsDTO
from backend.db.sqlite_migrations import run_migrations
from backend.runtime_ports import build_core_ports


class _WorkspaceRegistry:
    def __init__(self, project) -> None:
        self.project = project

    def get_project(self, project_id):
        if getattr(self.project, "id", "") == project_id:
            return self.project
        return None

    def get_active_project(self):
        return self.project

    def resolve_scope(self, project_id=None):
        resolved_id = project_id or self.project.id
        return None, ProjectScope(
            project_id=resolved_id,
            project_name=self.project.name,
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        )


def _context() -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id="project-1",
            project_name="Project 1",
            root_path=Path("/tmp/project"),
            sessions_dir=Path("/tmp/project/sessions"),
            docs_dir=Path("/tmp/project/docs"),
            progress_dir=Path("/tmp/project/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


class ArtifactIntelligenceQueryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.project = types.SimpleNamespace(id="project-1", name="Project 1")
        self.ports = build_core_ports(self.db, workspace_registry=_WorkspaceRegistry(self.project))
        self.context = _context()
        self.service = ArtifactIntelligenceQueryService()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def test_snapshot_diagnostics_returns_repository_values(self) -> None:
        await self.db.execute(
            """
            INSERT INTO artifact_snapshot_cache (
                project_id, collection_id, schema_version, generated_at,
                fetched_at, artifact_count, status, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "project-1",
                "collection-a",
                "skillmeat-artifact-snapshot-v1",
                "2026-05-07T09:55:00Z",
                "2026-05-07T10:00:00Z",
                3,
                "fetched",
                "{}",
            ),
        )
        await self.db.executemany(
            """
            INSERT INTO artifact_identity_map (
                project_id, ccdash_name, ccdash_type, match_tier, unresolved_reason
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("project-1", "frontend-design", "skill", "tier-1", ""),
                ("project-1", "planning", "skill", "tier-2", ""),
                ("project-1", "missing-skill", "skill", "unresolved", "not_in_snapshot"),
            ],
        )
        await self.db.commit()

        with patch(
            "backend.db.repositories.artifact_snapshot_repository._utc_now",
            return_value=datetime(2026, 5, 7, 10, 5, tzinfo=timezone.utc),
        ), patch(
            "backend.db.repositories.artifact_snapshot_repository.config.CCDASH_SNAPSHOT_FRESHNESS_MAX_AGE_SECONDS",
            600,
        ):
            result = await self.service.get_snapshot_diagnostics(self.context, self.ports)

        self.assertIsInstance(result, SnapshotDiagnosticsDTO)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.project_id, "project-1")
        self.assertEqual(result.snapshot_age_seconds, 300)
        self.assertEqual(result.artifact_count, 3)
        self.assertEqual(result.resolved_count, 2)
        self.assertEqual(result.unresolved_count, 1)
        self.assertFalse(result.is_stale)
        self.assertIn("project-1", result.source_refs)
