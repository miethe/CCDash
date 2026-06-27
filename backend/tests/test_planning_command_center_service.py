import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.services.agent_queries.models import PlanningCommandCenterGitStateDTO
from backend.application.services.agent_queries.planning_command_center import (
    PlanningCommandCenterQueryService,
    _NullGitProbe,
    _TERMINAL_STATUSES,
    _pcc_params,
)
from backend.models import Project


class _FeaturesRepo:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.list_all_call_count = 0
        self.get_by_id_call_count = 0

    async def list_all(self, project_id: str) -> list[dict]:
        self.list_all_call_count += 1
        return list(self.rows)

    async def get_by_id(self, feature_id: str) -> dict | None:
        self.get_by_id_call_count += 1
        for row in self.rows:
            if row.get("id") == feature_id:
                return row
        return None


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


def _make_feature_row(feature_id: str = "feat-1") -> dict:
    return {
        "id": feature_id,
        "name": f"Feature {feature_id}",
        "status": "in-progress",
        "updated_at": "2026-05-28T00:00:00+00:00",
        "data_json": json.dumps(
            {
                "id": feature_id,
                "name": f"Feature {feature_id}",
                "status": "in-progress",
                "summary": "Test feature",
                "priority": "medium",
                "tags": [],
                "phases": [
                    {
                        "id": f"{feature_id}:phase-1",
                        "phase": "1",
                        "title": "Phase 1",
                        "status": "active",
                        "progress": 0,
                        "totalTasks": 1,
                        "completedTasks": 0,
                        "tasks": [],
                    }
                ],
            }
        ),
    }


def _make_storage(feature_row: dict) -> SimpleNamespace:
    return SimpleNamespace(
        features=lambda: _FeaturesRepo([feature_row]),
        documents=lambda: _DocumentsRepo([]),
        worktree_contexts=lambda: _WorktreeRepo([]),
    )


class P2009MemoizationTests(unittest.TestCase):
    """P2-009: get_command_center is decorated with @memoized_query."""

    def test_get_command_center_has_memoized_query_wrapper(self) -> None:
        # The decorator wraps the original function and sets __wrapped__.
        method = PlanningCommandCenterQueryService.get_command_center
        self.assertTrue(
            hasattr(method, "__wrapped__"),
            "get_command_center must be wrapped by @memoized_query (missing __wrapped__)",
        )

    def test_pcc_params_extractor_returns_project_id_key(self) -> None:
        # _pcc_params must return "project_id" so the decorator pops it into
        # the cache-key scope slot (not double-hashed into the param dict).
        project = Project(id="proj-1", name="P1", path="/tmp/p1")
        ctx = _request_context(project)
        ports = object()
        svc = PlanningCommandCenterQueryService()
        params = _pcc_params(svc, ctx, ports, project_id_override="proj-1", q="search", page=2, page_size=25)
        self.assertIn("project_id", params, "_pcc_params must include 'project_id' for scope-slot derivation")
        self.assertEqual(params["project_id"], "proj-1")
        self.assertEqual(params["q"], "search")
        self.assertEqual(params["page"], 2)
        self.assertEqual(params["page_size"], 25)


class P2011SingleFeatureFastPathTests(unittest.IsolatedAsyncioTestCase):
    """P2-011: get_command_center_item uses get_by_id, not a 500-item scan."""

    async def test_get_command_center_item_uses_get_by_id(self) -> None:
        project = Project(id="proj-1", name="Project One", path="/tmp/project-one")
        feature_row = _make_feature_row("feat-1")
        features_repo = _FeaturesRepo([feature_row])
        storage = SimpleNamespace(
            features=lambda: features_repo,
            documents=lambda: _DocumentsRepo([]),
            worktree_contexts=lambda: _WorktreeRepo([]),
        )
        ports = SimpleNamespace(storage=storage, workspace_registry=_WorkspaceRegistry(project))
        service = PlanningCommandCenterQueryService()

        item = await service.get_command_center_item(
            _request_context(project),
            ports,
            feature_id="feat-1",
            project_id_override="proj-1",
        )

        self.assertIsNotNone(item, "Expected a non-None item for an existing feature")
        self.assertEqual(item.feature.feature_id, "feat-1")
        # get_by_id must have been called exactly once (not a list_all scan).
        self.assertEqual(features_repo.get_by_id_call_count, 1, "get_by_id must be called exactly once")
        # list_all must NOT have been called for features (no 500-item scan).
        self.assertEqual(
            features_repo.list_all_call_count,
            0,
            "list_all must NOT be called on the features repo for get_command_center_item",
        )

    async def test_get_command_center_item_returns_none_for_missing_feature(self) -> None:
        project = Project(id="proj-1", name="Project One", path="/tmp/project-one")
        features_repo = _FeaturesRepo([])
        storage = SimpleNamespace(
            features=lambda: features_repo,
            documents=lambda: _DocumentsRepo([]),
            worktree_contexts=lambda: _WorktreeRepo([]),
        )
        ports = SimpleNamespace(storage=storage, workspace_registry=_WorkspaceRegistry(project))
        service = PlanningCommandCenterQueryService()

        item = await service.get_command_center_item(
            _request_context(project),
            ports,
            feature_id="nonexistent-feature",
            project_id_override="proj-1",
        )
        self.assertIsNone(item)


class HideDoneFilterTests(unittest.IsolatedAsyncioTestCase):
    """Part-A: hide_done excludes all members of _TERMINAL_STATUSES."""

    def _make_terminal_row(self, feature_id: str, status: str) -> dict:
        return {
            "id": feature_id,
            "name": f"Feature {feature_id}",
            "status": status,
            "updated_at": "2026-05-28T00:00:00+00:00",
            "data_json": json.dumps({
                "id": feature_id,
                "name": f"Feature {feature_id}",
                "status": status,
                "summary": "Terminal feature",
                "priority": "low",
                "tags": [],
                "phases": [],
            }),
        }

    async def test_hide_done_excludes_full_terminal_set(self) -> None:
        project = Project(id="proj-1", name="P1", path="/tmp/p1")
        rows = [self._make_terminal_row(s, s) for s in _TERMINAL_STATUSES]
        # Also add one active feature that must NOT be excluded.
        rows.append(_make_feature_row("active-feat"))
        storage = SimpleNamespace(
            features=lambda: _FeaturesRepo(rows),
            documents=lambda: _DocumentsRepo([]),
            worktree_contexts=lambda: _WorktreeRepo([]),
        )
        ports = SimpleNamespace(storage=storage, workspace_registry=_WorkspaceRegistry(project))
        service = PlanningCommandCenterQueryService()

        page = await service.get_command_center(
            _request_context(project),
            ports,
            project_id_override="proj-1",
            hide_done=True,
            page=1,
            page_size=50,
        )

        returned_ids = {item.feature.feature_id for item in page.items}
        for terminal_status in _TERMINAL_STATUSES:
            self.assertNotIn(terminal_status, returned_ids,
                             f"hide_done=True must exclude feature with status '{terminal_status}'")
        self.assertIn("active-feat", returned_ids,
                      "hide_done=True must keep the active feature")

    async def test_hide_done_false_retains_terminal_items(self) -> None:
        project = Project(id="proj-1", name="P1", path="/tmp/p1")
        rows = [self._make_terminal_row("done-feat", "done")]
        storage = SimpleNamespace(
            features=lambda: _FeaturesRepo(rows),
            documents=lambda: _DocumentsRepo([]),
            worktree_contexts=lambda: _WorktreeRepo([]),
        )
        ports = SimpleNamespace(storage=storage, workspace_registry=_WorkspaceRegistry(project))
        service = PlanningCommandCenterQueryService()

        page = await service.get_command_center(
            _request_context(project),
            ports,
            project_id_override="proj-1",
            hide_done=False,
            page=1,
            page_size=50,
        )

        returned_ids = {item.feature.feature_id for item in page.items}
        self.assertIn("done-feat", returned_ids, "hide_done=False must retain terminal items")


class SortMissingTimestampTests(unittest.IsolatedAsyncioTestCase):
    """Part-B: items with no last_activity timestamp sort LAST under desc."""

    def _make_row_with_ts(self, feature_id: str, ts: str | None) -> dict:
        base = _make_feature_row(feature_id)
        data = json.loads(base["data_json"])
        data["updatedAt"] = ts
        base["updated_at"] = ts or ""
        base["data_json"] = json.dumps(data)
        return base

    async def test_missing_timestamp_sorts_last_desc(self) -> None:
        project = Project(id="proj-1", name="P1", path="/tmp/p1")
        rows = [
            self._make_row_with_ts("feat-ts", "2026-05-28T10:00:00+00:00"),
            self._make_row_with_ts("feat-no-ts", None),
        ]
        storage = SimpleNamespace(
            features=lambda: _FeaturesRepo(rows),
            documents=lambda: _DocumentsRepo([]),
            worktree_contexts=lambda: _WorktreeRepo([]),
        )
        ports = SimpleNamespace(storage=storage, workspace_registry=_WorkspaceRegistry(project))
        service = PlanningCommandCenterQueryService()

        page = await service.get_command_center(
            _request_context(project),
            ports,
            project_id_override="proj-1",
            sort_by="last_activity",
            sort_direction="desc",
            page=1,
            page_size=50,
        )

        ids = [item.feature.feature_id for item in page.items]
        self.assertEqual(len(ids), 2)
        # timestamped item must be first under desc
        self.assertEqual(ids[0], "feat-ts",
                         "Under desc sort, item WITH timestamp must precede item WITHOUT")
        self.assertEqual(ids[-1], "feat-no-ts",
                         "Under desc sort, item WITHOUT timestamp must be last")

    async def test_missing_timestamp_sorts_last_asc(self) -> None:
        project = Project(id="proj-1", name="P1", path="/tmp/p1")
        rows = [
            self._make_row_with_ts("feat-ts", "2026-05-28T10:00:00+00:00"),
            self._make_row_with_ts("feat-no-ts", None),
        ]
        storage = SimpleNamespace(
            features=lambda: _FeaturesRepo(rows),
            documents=lambda: _DocumentsRepo([]),
            worktree_contexts=lambda: _WorktreeRepo([]),
        )
        ports = SimpleNamespace(storage=storage, workspace_registry=_WorkspaceRegistry(project))
        service = PlanningCommandCenterQueryService()

        page = await service.get_command_center(
            _request_context(project),
            ports,
            project_id_override="proj-1",
            sort_by="last_activity",
            sort_direction="asc",
            page=1,
            page_size=50,
        )

        ids = [item.feature.feature_id for item in page.items]
        # Under asc sort, missing timestamps must still be last.
        self.assertEqual(ids[-1], "feat-no-ts",
                         "Under asc sort, item WITHOUT timestamp must still be last")


class P2013NullGitProbeTests(unittest.IsolatedAsyncioTestCase):
    """P2-013: V1 build defaults to _NullGitProbe; no git subprocess per item."""

    def test_default_git_probe_is_null_probe(self) -> None:
        svc = PlanningCommandCenterQueryService()
        self.assertIsInstance(
            svc.git_probe,
            _NullGitProbe,
            "PlanningCommandCenterQueryService must default to _NullGitProbe (parity with MPCC-206)",
        )

    def test_explicit_git_probe_overrides_null_probe(self) -> None:
        probe = _GitProbe()
        svc = PlanningCommandCenterQueryService(git_probe=probe)
        self.assertIs(svc.git_probe, probe)

    async def test_null_probe_returns_sparse_git_state(self) -> None:
        probe = _NullGitProbe()
        state = await probe.probe("/some/path")
        # path_exists=None is the sentinel that signals "not yet probed".
        self.assertIsNone(state.path_exists)
        self.assertGreater(len(state.warnings), 0, "NullGitProbe should include a deferral warning")

    async def test_command_center_with_null_probe_builds_items_without_git_io(self) -> None:
        """End-to-end: get_command_center with default (NullGitProbe) returns items."""
        project = Project(id="proj-1", name="Project One", path="/tmp/project-one")
        feature_row = _make_feature_row("feat-1")
        storage = _make_storage(feature_row)
        ports = SimpleNamespace(storage=storage, workspace_registry=_WorkspaceRegistry(project))

        # Service with default _NullGitProbe (no real git I/O).
        service = PlanningCommandCenterQueryService()

        page = await service.get_command_center(
            _request_context(project),
            ports,
            project_id_override="proj-1",
            page=1,
            page_size=10,
        )

        self.assertIn(page.status, {"ok", "partial"})
        self.assertEqual(page.total, 1)
        item = page.items[0]
        self.assertEqual(item.feature.feature_id, "feat-1")
        # git_state must be present but sparse (path_exists=None from NullGitProbe).
        self.assertIsNotNone(item.git_state)
        self.assertIsNone(item.git_state.path_exists)


if __name__ == "__main__":
    unittest.main()
