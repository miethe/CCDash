import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.services.agent_queries.models import PlanningCommandCenterGitStateDTO
from backend.application.services.agent_queries.planning_command_center import PlanningCommandCenterQueryService
from backend.models import Project


class _FeaturesRepo:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    async def list_all(self, project_id: str) -> list[dict]:
        return list(self.rows)


class _DocumentsRepo:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    async def list_all(self, project_id: str) -> list[dict]:
        return list(self.rows)


class _WorktreeRepo:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    async def list(self, project_id: str, **kwargs) -> list[dict]:
        return list(self.rows)


class _WorkspaceRegistry:
    def __init__(self, project: Project) -> None:
        self.project = project

    def get_project(self, project_id: str) -> Project | None:
        return self.project if project_id == self.project.id else None

    def get_active_project(self) -> Project | None:
        return self.project

    def resolve_scope(self, project_id: str):
        return None, ProjectScope(
            project_id=project_id,
            project_name=self.project.name,
            root_path=Path(self.project.path),
            sessions_dir=Path(self.project.path) / "sessions",
            docs_dir=Path(self.project.path) / "docs",
            progress_dir=Path(self.project.path) / "progress",
        )


class _GitProbe:
    async def probe(self, worktree_path: str) -> PlanningCommandCenterGitStateDTO:
        return PlanningCommandCenterGitStateDTO(
            path_exists=bool(worktree_path),
            head="abc1234" if worktree_path else "",
            dirty_count=0 if worktree_path else None,
            probed_at="2026-05-28T00:00:00+00:00",
        )


def _request_context(project: Project) -> RequestContext:
    return RequestContext(
        principal=Principal(subject="tester", display_name="Tester", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project.id,
            project_name=project.name,
            root_path=Path(project.path),
            sessions_dir=Path(project.path) / "sessions",
            docs_dir=Path(project.path) / "docs",
            progress_dir=Path(project.path) / "progress",
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-1"),
    )


class PlanningCommandCenterQueryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_center_composes_feature_command_worktree_and_git_state(self) -> None:
        project = Project(id="proj-1", name="Project One", path="/tmp/project-one")
        plan_path = "docs/project_plans/implementation_plans/enhancements/feat-1.md"
        feature_row = {
            "id": "feat-1",
            "name": "Feature One",
            "status": "in-progress",
            "updated_at": "2026-05-28T00:00:00+00:00",
            "data_json": json.dumps(
                {
                    "id": "feat-1",
                    "name": "Feature One",
                    "status": "in-progress",
                    "summary": "A live planning feature",
                    "priority": "high",
                    "tags": ["tier-2"],
                    "prRefs": ["https://github.com/acme/repo/pull/7"],
                    "linkedDocs": [
                        {
                            "id": "plan:feat-1",
                            "title": "Feature One Plan",
                            "filePath": plan_path,
                            "docType": "implementation_plan",
                        }
                    ],
                    "phases": [
                        {
                            "id": "feat-1:phase-1",
                            "phase": "1",
                            "title": "Foundation",
                            "status": "done",
                            "progress": 100,
                            "totalTasks": 2,
                            "completedTasks": 2,
                            "tasks": [],
                        },
                        {
                            "id": "feat-1:phase-2",
                            "phase": "2",
                            "title": "UI",
                            "status": "backlog",
                            "progress": 0,
                            "totalTasks": 3,
                            "completedTasks": 0,
                            "tasks": [],
                        },
                    ],
                }
            ),
        }
        storage = SimpleNamespace(
            features=lambda: _FeaturesRepo([feature_row]),
            documents=lambda: _DocumentsRepo([]),
            worktree_contexts=lambda: _WorktreeRepo(
                [
                    {
                        "id": "wt-1",
                        "feature_id": "feat-1",
                        "branch": "codex/feat-1",
                        "worktree_path": "/tmp/project-one-worktree",
                        "status": "ready",
                        "phase_number": 2,
                        "batch_id": "batch_1",
                    }
                ]
            ),
        )
        ports = SimpleNamespace(storage=storage, workspace_registry=_WorkspaceRegistry(project))
        service = PlanningCommandCenterQueryService(git_probe=_GitProbe())

        page = await service.get_command_center(
            _request_context(project),
            ports,
            project_id_override="proj-1",
            q="Feature",
            page=1,
            page_size=10,
        )

        self.assertEqual(page.status, "ok")
        self.assertEqual(page.total, 1)
        item = page.items[0]
        self.assertEqual(item.feature.feature_id, "feat-1")
        self.assertEqual(item.command.rule_id, "PCC-CMD-007")
        self.assertEqual(item.command.phase, 2)
        self.assertEqual(item.command.command, f"/dev:execute-phase 2 {plan_path}")
        self.assertEqual(item.story_points.total, 5)
        self.assertEqual(item.story_points.remaining, 3)
        self.assertEqual(item.worktree.branch, "codex/feat-1")
        self.assertEqual(item.git_state.head, "abc1234")
        self.assertTrue(item.capabilities.open_pr)


if __name__ == "__main__":
    unittest.main()
