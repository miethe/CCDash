import types
import unittest
from pathlib import Path

import aiosqlite

from backend.db.factory import (
    get_agentic_intelligence_repository,
    get_document_repository,
    get_entity_link_repository,
    get_feature_repository,
    get_session_repository,
    get_session_usage_repository,
    get_sync_state_repository,
    get_task_repository,
)
from backend.db.sqlite_migrations import run_migrations
from backend.runtime_ports import build_core_ports
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.services.agent_queries import (
    FeatureForensicsQueryService,
    ProjectStatusQueryService,
    ReportingQueryService,
    WorkflowDiagnosticsQueryService,
)


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


class AgentQueryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)
        self.project = types.SimpleNamespace(id="project-1", name="Project 1")
        self.ports = build_core_ports(self.db, workspace_registry=_WorkspaceRegistry(self.project))
        self.context = _context()

        self.feature_repo = get_feature_repository(self.db)
        self.document_repo = get_document_repository(self.db)
        self.task_repo = get_task_repository(self.db)
        self.session_repo = get_session_repository(self.db)
        self.link_repo = get_entity_link_repository(self.db)
        self.sync_repo = get_sync_state_repository(self.db)
        self.usage_repo = get_session_usage_repository(self.db)
        self.intelligence_repo = get_agentic_intelligence_repository(self.db)

        await self._seed_feature_context()
        await self._seed_workflow_context()

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _seed_feature_context(self) -> None:
        await self.feature_repo.upsert(
            {
                "id": "feature-1",
                "name": "Feature One",
                "status": "in_progress",
                "createdAt": "2026-04-11T08:00:00+00:00",
                "updatedAt": "2026-04-11T10:00:00+00:00",
            },
            "project-1",
        )
        await self.document_repo.upsert(
            {
                "id": "doc-1",
                "title": "Implementation Plan",
                "filePath": "docs/project_plans/plan.md",
                "canonicalPath": "docs/project_plans/plan.md",
                "rootKind": "project_plans",
                "docType": "implementation_plan",
                "hasFrontmatter": True,
                "featureSlugCanonical": "feature-1",
                "updatedAt": "2026-04-11T09:20:00+00:00",
                "frontmatter": {"linkedFeatures": ["feature-1"]},
            },
            "project-1",
        )
        await self.task_repo.upsert(
            {
                "id": "task-1",
                "title": "Implement service",
                "status": "in_progress",
                "featureId": "feature-1",
                "updatedAt": "2026-04-11T09:25:00+00:00",
            },
            "project-1",
        )
        await self.session_repo.upsert(
            {
                "id": "session-1",
                "taskId": "feature-1",
                "status": "completed",
                "model": "gpt-5",
                "durationSeconds": 1800,
                "observedTokens": 500,
                "totalCost": 1.25,
                "startedAt": "2026-04-11T09:00:00+00:00",
                "endedAt": "2026-04-11T09:30:00+00:00",
                "createdAt": "2026-04-11T09:00:00+00:00",
                "updatedAt": "2026-04-11T09:30:00+00:00",
            },
            "project-1",
        )
        await self.session_repo.upsert_logs(
            "session-1",
            [
                {
                    "timestamp": "2026-04-11T09:00:00+00:00",
                    "speaker": "agent",
                    "type": "command",
                    "content": "/dev:execute-phase 1 docs/project_plans/plan.md",
                }
            ],
        )
        await self.link_repo.upsert(
            {
                "source_type": "feature",
                "source_id": "feature-1",
                "target_type": "session",
                "target_id": "session-1",
                "link_type": "related",
            }
        )
        await self.link_repo.upsert(
            {
                "source_type": "feature",
                "source_id": "feature-1",
                "target_type": "document",
                "target_id": "doc-1",
                "link_type": "related",
            }
        )
        await self.link_repo.upsert(
            {
                "source_type": "feature",
                "source_id": "feature-1",
                "target_type": "task",
                "target_id": "task-1",
                "link_type": "related",
            }
        )
        await self.sync_repo.upsert_sync_state(
            {
                "file_path": "docs/project_plans/plan.md",
                "file_hash": "abc",
                "file_mtime": "2026-04-11T09:20:00+00:00",
                "entity_type": "document",
                "project_id": "project-1",
                "last_synced": "2026-04-11T10:05:00+00:00",
                "parse_ms": 5,
            }
        )

    async def _seed_workflow_context(self) -> None:
        source = await self.intelligence_repo.upsert_definition_source(
            {
                "project_id": "project-1",
                "source_kind": "skillmeat",
                "enabled": True,
                "base_url": "http://skillmeat.local",
            }
        )
        await self.intelligence_repo.upsert_external_definition(
            {
                "project_id": "project-1",
                "source_id": source["id"],
                "definition_type": "workflow",
                "external_id": "phase-execution",
                "display_name": "Phase Execution",
                "resolution_metadata": {
                    "effectiveWorkflowId": "phase-execution",
                    "effectiveWorkflowName": "Phase Execution",
                    "aliases": ["/dev:execute-phase"],
                },
                "fetched_at": "2026-04-11T09:00:00+00:00",
            }
        )
        await self.intelligence_repo.upsert_stack_observation(
            {
                "project_id": "project-1",
                "session_id": "session-1",
                "feature_id": "feature-1",
                "workflow_ref": "phase-execution",
                "confidence": 0.95,
                "evidence": {"commands": ["/dev:execute-phase 1 docs/project_plans/plan.md"]},
                "updated_at": "2026-04-11T09:05:00+00:00",
            },
            components=[
                {
                    "project_id": "project-1",
                    "component_type": "workflow",
                    "component_key": "phase-execution",
                    "status": "resolved",
                    "confidence": 0.95,
                    "external_definition_type": "workflow",
                    "external_definition_external_id": "phase-execution",
                    "payload": {"workflowRef": "phase-execution"},
                }
            ],
        )
        await self.usage_repo.replace_session_usage(
            "project-1",
            "session-1",
            [
                {
                    "id": "evt-1",
                    "root_session_id": "session-1",
                    "linked_session_id": "",
                    "source_log_id": "log-1",
                    "captured_at": "2026-04-11T09:01:00+00:00",
                    "event_kind": "message",
                    "model": "gpt-5",
                    "tool_name": "",
                    "agent_name": "backend-architect",
                    "token_family": "model_input",
                    "delta_tokens": 500,
                    "cost_usd_model_io": 1.25,
                    "metadata_json": {},
                }
            ],
            [],
        )

    async def test_services_operate_against_real_sqlite_data(self) -> None:
        project_status = await ProjectStatusQueryService().get_status(self.context, self.ports)
        feature_forensics = await FeatureForensicsQueryService().get_forensics(self.context, self.ports, "feature-1")
        workflow_diagnostics = await WorkflowDiagnosticsQueryService().get_diagnostics(self.context, self.ports)
        reporting = await ReportingQueryService().generate_aar(self.context, self.ports, "feature-1")

        self.assertEqual(project_status.status, "ok")
        self.assertEqual(feature_forensics.status, "ok")
        self.assertIn(workflow_diagnostics.status, {"ok", "partial"})
        self.assertIn(reporting.status, {"ok", "partial"})

        self.assertEqual(
            type(project_status).model_validate(project_status.model_dump()).project_id,
            "project-1",
        )
        self.assertEqual(
            type(feature_forensics).model_validate(feature_forensics.model_dump()).feature_id,
            "feature-1",
        )
        self.assertEqual(
            type(workflow_diagnostics).model_validate(workflow_diagnostics.model_dump()).project_id,
            "project-1",
        )
        self.assertEqual(
            type(reporting).model_validate(reporting.model_dump()).feature_id,
            "feature-1",
        )
