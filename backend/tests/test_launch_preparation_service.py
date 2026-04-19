"""Tests for LaunchPreparationApplicationService (PCP-503)."""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite

from backend.application.services.agent_queries.models import (
    PhaseOperationsDTO,
    PhaseTaskItem,
)
from backend.application.services.launch_preparation import LaunchPreparationApplicationService
from backend.db.sqlite_migrations import run_migrations
from backend.models import (
    LaunchPreparationRequest,
    LaunchStartRequest,
    LaunchWorktreeSelectionDTO,
)


def _make_phase_ops(
    *,
    feature_id: str = "FEAT-1",
    phase_number: int = 1,
    batch_id: str = "batch-a",
    is_ready: bool = True,
    blocked: bool = False,
) -> PhaseOperationsDTO:
    """Build a minimal PhaseOperationsDTO for testing."""
    readiness_state = "ready" if is_ready else ("blocked" if blocked else "unknown")
    return PhaseOperationsDTO(
        status="ok",
        feature_id=feature_id,
        phase_number=phase_number,
        phase_token="ph-1",
        phase_title="Phase One",
        phase_batches=[
            {
                "id": batch_id,
                "batch_id": batch_id,
                "task_ids": ["T-1"],
                "is_ready": is_ready,
                "readiness_state": readiness_state,
                "blocked_reason": "upstream blocked" if blocked else "",
                "dependencies": [],
            }
        ],
        blocked_batch_ids=[batch_id] if blocked else [],
        tasks=[
            PhaseTaskItem(
                task_id="T-1",
                title="Do the thing",
                status="pending",
                assignees=["alice"],
                blockers=[],
                batch_id=batch_id,
            )
        ],
    )


class _FakePlanningService:
    """Minimal stub replacing PlanningQueryService.get_phase_operations."""

    def __init__(self, phase_ops: PhaseOperationsDTO) -> None:
        self._phase_ops = phase_ops

    async def get_phase_operations(self, context, ports, *, feature_id, phase_number, project_id_override=None):
        return self._phase_ops


def _make_execution_service_stub(run_id: str = "run-001") -> MagicMock:
    svc = MagicMock()
    svc.create_run = AsyncMock(
        return_value={
            "id": run_id,
            "status": "queued",
            "requires_approval": False,
        }
    )
    return svc


class LaunchPreparationServiceTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.workspace = Path(self._tmp.name).resolve()
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        # Build a minimal LocalStorageUnitOfWork so worktree_contexts() is available.
        from backend.adapters.storage.local import LocalStorageUnitOfWork
        self.storage = LocalStorageUnitOfWork(self.db)

        # Build ports / context shims.
        self.project = types.SimpleNamespace(id="proj-1", path=str(self.workspace))
        self.ports = types.SimpleNamespace(storage=self.storage)
        self.context = types.SimpleNamespace(project=self.project)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self._tmp.cleanup()

    def _make_service(
        self,
        phase_ops: PhaseOperationsDTO,
        run_id: str = "run-001",
    ) -> LaunchPreparationApplicationService:
        from backend.application.services.execution import ExecutionApplicationService

        svc = LaunchPreparationApplicationService(
            planning_service=_FakePlanningService(phase_ops),
            execution_service=_make_execution_service_stub(run_id),
        )
        return svc

    def _patch_require_project(self):
        return patch(
            "backend.application.services.launch_preparation.require_project",
            return_value=self.project,
        )

    # ── Test 1: prepare with ready batch ──────────────────────────────────────

    async def test_prepare_with_ready_batch(self) -> None:
        phase_ops = _make_phase_ops(is_ready=True)
        svc = self._make_service(phase_ops)

        req = LaunchPreparationRequest(
            projectId="proj-1",
            featureId="FEAT-1",
            phaseNumber=1,
            batchId="batch-a",
        )
        with self._patch_require_project():
            result = await svc.prepare(self.context, self.ports, req)

        self.assertTrue(result.batch.isReady)
        self.assertTrue(any(p.provider == "local" for p in result.providers))
        self.assertEqual(result.selectedProvider, "local")
        self.assertEqual(result.approval.requirement, "none")
        # No candidates in DB, so createIfMissing should be True
        self.assertTrue(result.worktreeSelection.createIfMissing)

    # ── Test 2: prepare returns existing worktree candidate ───────────────────

    async def test_prepare_returns_existing_worktree_candidate(self) -> None:
        repo = self.storage.worktree_contexts()
        row = await repo.create(
            {
                "project_id": "proj-1",
                "feature_id": "FEAT-1",
                "phase_number": 1,
                "batch_id": "batch-a",
                "branch": "feat/test-branch",
                "worktree_path": "/tmp/worktrees/feat",
                "base_branch": "main",
                "status": "ready",
                "provider": "local",
            }
        )
        ctx_id = row["id"]

        phase_ops = _make_phase_ops(is_ready=True)
        svc = self._make_service(phase_ops)

        req = LaunchPreparationRequest(
            projectId="proj-1",
            featureId="FEAT-1",
            phaseNumber=1,
            batchId="batch-a",
        )
        with self._patch_require_project():
            result = await svc.prepare(self.context, self.ports, req)

        self.assertEqual(len(result.worktreeCandidates), 1)
        self.assertEqual(result.worktreeCandidates[0].id, ctx_id)
        self.assertEqual(result.worktreeSelection.worktreeContextId, ctx_id)
        self.assertFalse(result.worktreeSelection.createIfMissing)

    # ── Test 3: prepare blocked batch emits warning ───────────────────────────

    async def test_prepare_blocked_batch_emits_warning(self) -> None:
        phase_ops = _make_phase_ops(is_ready=False, blocked=True)
        svc = self._make_service(phase_ops)

        req = LaunchPreparationRequest(
            projectId="proj-1",
            featureId="FEAT-1",
            phaseNumber=1,
            batchId="batch-a",
        )
        with self._patch_require_project():
            result = await svc.prepare(self.context, self.ports, req)

        self.assertEqual(result.approval.requirement, "required")
        self.assertIn("batch_not_ready", result.approval.reasonCodes)
        self.assertTrue(len(result.warnings) > 0)

    # ── Test 4: start creates worktree context when requested ─────────────────

    async def test_start_creates_worktree_context_when_requested(self) -> None:
        phase_ops = _make_phase_ops(is_ready=True)
        svc = self._make_service(phase_ops, run_id="run-new")

        req = LaunchStartRequest(
            projectId="proj-1",
            featureId="FEAT-1",
            phaseNumber=1,
            batchId="batch-a",
            provider="local",
            worktree=LaunchWorktreeSelectionDTO(
                createIfMissing=True,
                branch="feat/new",
                worktreePath="/tmp/wt",
                baseBranch="main",
            ),
        )
        with self._patch_require_project():
            result = await svc.start(self.context, self.ports, req)

        self.assertNotEqual(result.worktreeContextId, "")
        self.assertEqual(result.runId, "run-new")

        # Verify the row was created and last_run_id set
        repo = self.storage.worktree_contexts()
        row = await repo.get_by_id(result.worktreeContextId)
        self.assertIsNotNone(row)
        self.assertEqual(row["last_run_id"], "run-new")

    # ── Test 5: start rejects unready batch without approval override ─────────

    async def test_start_rejects_unready_batch_without_approval_override(self) -> None:
        from fastapi import HTTPException

        phase_ops = _make_phase_ops(is_ready=False, blocked=True)
        svc = self._make_service(phase_ops)

        req = LaunchStartRequest(
            projectId="proj-1",
            featureId="FEAT-1",
            phaseNumber=1,
            batchId="batch-a",
            provider="local",
        )
        with self._patch_require_project():
            with self.assertRaises(HTTPException) as ctx:
                await svc.start(self.context, self.ports, req)

        self.assertEqual(ctx.exception.status_code, 409)

    # ── Test 6: start accepts unready batch with approval override ────────────

    async def test_start_accepts_unready_batch_with_approval_override(self) -> None:
        phase_ops = _make_phase_ops(is_ready=False, blocked=True)
        svc = self._make_service(phase_ops, run_id="run-override")

        req = LaunchStartRequest(
            projectId="proj-1",
            featureId="FEAT-1",
            phaseNumber=1,
            batchId="batch-a",
            provider="local",
            approvalDecision="approved",
            worktree=LaunchWorktreeSelectionDTO(createIfMissing=True),
        )
        with self._patch_require_project():
            result = await svc.start(self.context, self.ports, req)

        self.assertEqual(result.runId, "run-override")
        self.assertTrue(len(result.warnings) > 0)
        self.assertIn("non-ready batch", result.warnings[0])

    # ── Test 7: start rejects unknown worktree context ────────────────────────

    async def test_start_rejects_unknown_worktree_context(self) -> None:
        from fastapi import HTTPException

        phase_ops = _make_phase_ops(is_ready=True)
        svc = self._make_service(phase_ops)

        req = LaunchStartRequest(
            projectId="proj-1",
            featureId="FEAT-1",
            phaseNumber=1,
            batchId="batch-a",
            provider="local",
            worktree=LaunchWorktreeSelectionDTO(worktreeContextId="no-such-id"),
        )
        with self._patch_require_project():
            with self.assertRaises(HTTPException) as ctx:
                await svc.start(self.context, self.ports, req)

        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
