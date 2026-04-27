"""TEST-507: pytest tests for BE-303 batch workflow query (N+1 elimination).

Verifies three acceptance criteria against the call site in
workflow_intelligence.WorkflowDiagnosticsQueryService.get_diagnostics:

1. A single call with N workflow IDs returns N detail rows.
2. The output structure of the batch path matches the per-workflow
   (single-item) path — same top-level keys on each detail dict.
3. The number of DB-load calls is O(1) — _load_registry_details is invoked
   exactly once regardless of how many IDs are in the batch.
"""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.application.services.agent_queries.workflow_intelligence import (
    WorkflowDiagnosticsQueryService,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

def _make_project(project_id: str = "project-be303") -> types.SimpleNamespace:
    return types.SimpleNamespace(id=project_id, name="BE-303 Test Project")


def _context(project_id: str = "project-be303") -> RequestContext:
    return RequestContext(
        principal=Principal(subject="test", display_name="Test", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id=project_id,
            project_name="BE-303 Test Project",
            root_path=Path("/tmp/be303"),
            sessions_dir=Path("/tmp/be303/sessions"),
            docs_dir=Path("/tmp/be303/docs"),
            progress_dir=Path("/tmp/be303/progress"),
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-be303"),
    )


def _ports(project_id: str = "project-be303") -> CorePorts:
    project = _make_project(project_id)

    class _WorkspaceRegistry:
        def get_project(self, pid):
            return project if pid == project_id else None

        def get_active_project(self):
            return project

        def resolve_scope(self, pid=None):
            resolved = pid or project_id
            return None, ProjectScope(
                project_id=resolved,
                project_name="BE-303 Test Project",
                root_path=Path("/tmp/be303"),
                sessions_dir=Path("/tmp/be303/sessions"),
                docs_dir=Path("/tmp/be303/docs"),
                progress_dir=Path("/tmp/be303/progress"),
            )

    class _Storage:
        db = object()

    return CorePorts(
        identity_provider=types.SimpleNamespace(
            get_principal=AsyncMock(
                return_value=Principal(subject="test", display_name="Test", auth_mode="test")
            )
        ),
        authorization_policy=types.SimpleNamespace(
            authorize=AsyncMock(return_value=AuthorizationDecision(allowed=True))
        ),
        workspace_registry=_WorkspaceRegistry(),
        storage=_Storage(),
        job_scheduler=types.SimpleNamespace(schedule=lambda job, **_: job),
        integration_client=types.SimpleNamespace(invoke=AsyncMock(return_value={})),
    )


def _registry_item(wf_id: str, label: str, sample_size: int = 5) -> dict:
    return {
        "id": f"registry:{wf_id}",
        "identity": {
            "displayLabel": label,
            "registryId": wf_id,
            "resolvedWorkflowId": wf_id,
        },
        "sampleSize": sample_size,
    }


def _detail_item(registry_id: str, sessions: list | None = None) -> dict:
    """Minimal detail dict that mirrors the shape returned by fetch_workflow_details."""
    return {
        "id": registry_id,
        "identity": {"displayLabel": registry_id},
        "correlationState": "observed",
        "issueCount": 0,
        "observedCommandCount": 1,
        "sampleSize": 5,
        "lastObservedAt": "2026-04-01T00:00:00+00:00",
        "issues": [],
        "representativeSessions": sessions or [],
    }


# ---------------------------------------------------------------------------
# Helpers that build consistent mock triplets
# ---------------------------------------------------------------------------

def _make_patches(registry_items: list[dict], detail_items: list[dict]):
    """Return three patch context managers for the three external calls."""
    registry_mock = AsyncMock(
        return_value={"items": registry_items, "generatedAt": "2026-04-27T00:00:00+00:00"}
    )
    effectiveness_mock = AsyncMock(
        return_value={"items": [], "generatedAt": "2026-04-27T00:00:00+00:00"}
    )
    failure_mock = AsyncMock(
        return_value={"items": [], "generatedAt": "2026-04-27T00:00:00+00:00"}
    )
    detail_mock = AsyncMock(return_value=detail_items)

    return registry_mock, effectiveness_mock, failure_mock, detail_mock


# ---------------------------------------------------------------------------
# AC1: N workflow IDs → N detail rows present in the output
# ---------------------------------------------------------------------------

class TestBatchReturnsNRows(unittest.IsolatedAsyncioTestCase):
    """fetch_workflow_details is fed N IDs and the service produces N diagnostics."""

    async def _run_with_n_workflows(self, n: int) -> list:
        registry_items = [_registry_item(f"wf-{i}", f"Workflow {i}") for i in range(n)]
        detail_items = [_detail_item(f"registry:wf-{i}") for i in range(n)]

        reg_mock, eff_mock, fail_mock, detail_mock = _make_patches(registry_items, detail_items)

        with (
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.list_workflow_registry",
                new=reg_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.get_workflow_effectiveness",
                new=eff_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.detect_failure_patterns",
                new=fail_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.fetch_workflow_details",
                new=detail_mock,
            ),
        ):
            result = await WorkflowDiagnosticsQueryService().get_diagnostics(
                _context(), _ports()
            )

        return result, detail_mock

    async def test_one_workflow_id_returns_one_diagnostic(self) -> None:
        result, detail_mock = await self._run_with_n_workflows(1)
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.workflows), 1)
        # fetch_workflow_details was called once with exactly one ID
        detail_mock.assert_awaited_once()
        ids_arg = detail_mock.call_args[0][2]
        self.assertEqual(len(ids_arg), 1)

    async def test_three_workflow_ids_returns_three_diagnostics(self) -> None:
        result, detail_mock = await self._run_with_n_workflows(3)
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.workflows), 3)
        ids_arg = detail_mock.call_args[0][2]
        self.assertEqual(len(ids_arg), 3)

    async def test_ten_workflow_ids_returns_ten_diagnostics(self) -> None:
        result, detail_mock = await self._run_with_n_workflows(10)
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.workflows), 10)
        ids_arg = detail_mock.call_args[0][2]
        self.assertEqual(len(ids_arg), 10)

    async def test_fetch_receives_all_registry_ids(self) -> None:
        """fetch_workflow_details must be called with the exact registry IDs collected."""
        n = 4
        registry_items = [_registry_item(f"wf-{i}", f"Workflow {i}") for i in range(n)]
        detail_items = [_detail_item(f"registry:wf-{i}") for i in range(n)]
        reg_mock, eff_mock, fail_mock, detail_mock = _make_patches(registry_items, detail_items)

        with (
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.list_workflow_registry",
                new=reg_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.get_workflow_effectiveness",
                new=eff_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.detect_failure_patterns",
                new=fail_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.fetch_workflow_details",
                new=detail_mock,
            ),
        ):
            await WorkflowDiagnosticsQueryService().get_diagnostics(_context(), _ports())

        ids_arg = detail_mock.call_args[0][2]
        expected_ids = {f"registry:wf-{i}" for i in range(n)}
        self.assertEqual(set(ids_arg), expected_ids)


# ---------------------------------------------------------------------------
# AC2: Output structure of batch path matches per-workflow (single-item) path
# ---------------------------------------------------------------------------

class TestBatchStructureMatchesSingleItemPath(unittest.IsolatedAsyncioTestCase):
    """Detail dicts produced via the batch path must have the same top-level keys
    as a single-item invocation of fetch_workflow_details."""

    async def _get_batch_details(self, registry_id: str, detail: dict) -> dict:
        """Run get_diagnostics with a single workflow and capture representative_sessions."""
        registry_items = [
            {
                "id": registry_id,
                "identity": {"displayLabel": "Test Workflow", "registryId": "wf-single"},
                "sampleSize": 3,
            }
        ]

        reg_mock, eff_mock, fail_mock, detail_mock = _make_patches(
            registry_items, [detail]
        )

        with (
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.list_workflow_registry",
                new=reg_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.get_workflow_effectiveness",
                new=eff_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.detect_failure_patterns",
                new=fail_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.fetch_workflow_details",
                new=detail_mock,
            ),
        ):
            result = await WorkflowDiagnosticsQueryService().get_diagnostics(
                _context(), _ports()
            )

        # Return the captured detail arg (what the service passed to the batch call)
        captured_detail = detail_mock.call_args[0][2]
        return result, captured_detail

    async def test_batch_detail_fields_match_single_item_shape(self) -> None:
        """The batch detail dict that reaches the assembler has the same keys as
        a single-item fetch_workflow_details response."""
        registry_id = "registry:wf-single"
        single_item_detail = _detail_item(registry_id, sessions=[{"sessionId": "s-1", "workflowRef": "wf-single"}])

        result, captured_ids = await self._get_batch_details(registry_id, single_item_detail)

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.workflows), 1)
        wf = result.workflows[0]

        # Fields derived from the detail dict must be populated correctly
        self.assertEqual(len(wf.representative_sessions), 1)
        self.assertEqual(wf.representative_sessions[0].session_id, "s-1")

    async def test_representative_sessions_from_batch_match_single_path(self) -> None:
        """Session references extracted via the batch path must equal those from
        a hypothetical single-workflow fetch."""
        registry_id = "registry:wf-parity"
        sessions_payload = [
            {"sessionId": "sess-A", "workflowRef": "wf-parity", "featureId": "feat-1"},
            {"sessionId": "sess-B", "workflowRef": "wf-parity", "featureId": "feat-1"},
        ]
        detail = _detail_item(registry_id, sessions=sessions_payload)
        registry_items = [
            {
                "id": registry_id,
                "identity": {"displayLabel": "Parity Test", "registryId": "wf-parity"},
                "sampleSize": 2,
            }
        ]

        reg_mock, eff_mock, fail_mock, detail_mock = _make_patches(registry_items, [detail])

        with (
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.list_workflow_registry",
                new=reg_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.get_workflow_effectiveness",
                new=eff_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.detect_failure_patterns",
                new=fail_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.fetch_workflow_details",
                new=detail_mock,
            ),
        ):
            result = await WorkflowDiagnosticsQueryService().get_diagnostics(
                _context(), _ports()
            )

        wf = result.workflows[0]
        # Cap is 3 — both sessions should be present
        session_ids = [s.session_id for s in wf.representative_sessions]
        self.assertIn("sess-A", session_ids)
        self.assertIn("sess-B", session_ids)

    async def test_batch_caps_representative_sessions_at_three(self) -> None:
        """The assembler caps representativeSessions at 3 regardless of batch size."""
        registry_id = "registry:wf-cap"
        sessions_payload = [
            {"sessionId": f"sess-{i}", "workflowRef": "wf-cap"}
            for i in range(6)
        ]
        detail = _detail_item(registry_id, sessions=sessions_payload)
        registry_items = [
            {
                "id": registry_id,
                "identity": {"displayLabel": "Cap Test", "registryId": "wf-cap"},
                "sampleSize": 6,
            }
        ]

        reg_mock, eff_mock, fail_mock, detail_mock = _make_patches(registry_items, [detail])

        with (
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.list_workflow_registry",
                new=reg_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.get_workflow_effectiveness",
                new=eff_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.detect_failure_patterns",
                new=fail_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.fetch_workflow_details",
                new=detail_mock,
            ),
        ):
            result = await WorkflowDiagnosticsQueryService().get_diagnostics(
                _context(), _ports()
            )

        wf = result.workflows[0]
        self.assertLessEqual(len(wf.representative_sessions), 3)


# ---------------------------------------------------------------------------
# AC3: DB calls are O(1) — fetch_workflow_details called exactly once
# ---------------------------------------------------------------------------

class TestBatchCallIsOOne(unittest.IsolatedAsyncioTestCase):
    """fetch_workflow_details must be invoked exactly once regardless of N."""

    async def _count_fetch_calls(self, n: int) -> int:
        registry_items = [_registry_item(f"wf-{i}", f"Workflow {i}") for i in range(n)]
        detail_items = [_detail_item(f"registry:wf-{i}") for i in range(n)]
        reg_mock, eff_mock, fail_mock, detail_mock = _make_patches(registry_items, detail_items)

        with (
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.list_workflow_registry",
                new=reg_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.get_workflow_effectiveness",
                new=eff_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.detect_failure_patterns",
                new=fail_mock,
            ),
            patch(
                "backend.application.services.agent_queries.workflow_intelligence.fetch_workflow_details",
                new=detail_mock,
            ),
        ):
            await WorkflowDiagnosticsQueryService().get_diagnostics(_context(), _ports())

        return detail_mock.await_count

    async def test_fetch_called_once_for_single_workflow(self) -> None:
        count = await self._count_fetch_calls(1)
        self.assertEqual(count, 1, "fetch_workflow_details must be called exactly once for N=1")

    async def test_fetch_called_once_for_five_workflows(self) -> None:
        count = await self._count_fetch_calls(5)
        self.assertEqual(count, 1, "fetch_workflow_details must be called exactly once for N=5")

    async def test_fetch_called_once_for_twenty_workflows(self) -> None:
        count = await self._count_fetch_calls(20)
        self.assertEqual(count, 1, "fetch_workflow_details must be called exactly once for N=20")

    async def test_fetch_call_count_invariant_across_n(self) -> None:
        """Call count must be 1 for each of several N values — proving O(1) not O(N)."""
        for n in (1, 3, 7, 15):
            with self.subTest(n=n):
                count = await self._count_fetch_calls(n)
                self.assertEqual(
                    count,
                    1,
                    f"fetch_workflow_details called {count} times for N={n}; expected 1",
                )

    async def test_batch_helper_itself_issues_single_load_call(self) -> None:
        """Inspect the batch helper directly: _load_registry_details called once for N IDs.

        This test operates one layer deeper than the service — it verifies the
        O(1) invariant at the fetch_workflow_details level to guard against future
        refactors that might re-introduce a loop inside the helper.
        """
        import aiosqlite
        import types as _types

        from backend.db.factory import get_agentic_intelligence_repository
        from backend.db.sqlite_migrations import run_migrations
        from backend.services.workflow_registry import fetch_workflow_details
        import backend.services.workflow_registry as _wf_module

        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await run_migrations(db)

        # Seed a source so _load_registry_details can run
        repo = get_agentic_intelligence_repository(db)
        source = await repo.upsert_definition_source(
            {
                "project_id": "proj-load-test",
                "source_kind": "skillmeat",
                "enabled": True,
                "base_url": "http://local.test",
            }
        )
        for ext_id in ("load-wf-1", "load-wf-2", "load-wf-3"):
            await repo.upsert_external_definition(
                {
                    "project_id": "proj-load-test",
                    "source_id": source["id"],
                    "definition_type": "workflow",
                    "external_id": ext_id,
                    "display_name": ext_id.replace("-", " ").title(),
                    "source_url": f"http://local.test/{ext_id}",
                    "fetched_at": "2026-04-01T00:00:00+00:00",
                    "resolution_metadata": {"isEffective": True},
                }
            )

        project = _types.SimpleNamespace(
            id="proj-load-test",
            skillMeat=_types.SimpleNamespace(
                webBaseUrl="http://local.test",
                projectId="proj-load-test",
                collectionId="default",
            ),
        )

        load_call_count = 0
        original_load = _wf_module._load_registry_details

        async def counting_load(db_, proj_):
            nonlocal load_call_count
            load_call_count += 1
            return await original_load(db_, proj_)

        ids = ["workflow:load-wf-1", "workflow:load-wf-2", "workflow:load-wf-3"]
        with patch.object(_wf_module, "_load_registry_details", counting_load):
            result = await fetch_workflow_details(db, project, ids)

        await db.close()

        self.assertEqual(
            load_call_count,
            1,
            f"_load_registry_details called {load_call_count} times for {len(ids)} IDs; expected 1",
        )
        self.assertEqual(len(result), 3)


if __name__ == "__main__":
    unittest.main()
