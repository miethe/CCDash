import asyncio
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import aiosqlite

from backend.db.sqlite_migrations import run_migrations
from backend.models import (
    ExecutionApprovalRequest,
    ExecutionCancelRequest,
    ExecutionPolicyCheckRequest,
    ExecutionRunCreateRequest,
)
from backend.routers import execution as execution_router
from backend.services.execution_runtime import get_execution_runtime


class ExecutionRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.workspace = Path(self._tmp.name).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        self.project = types.SimpleNamespace(
            id="project-1",
            path=str(self.workspace),
        )
        self.project_patch = patch.object(
            execution_router.project_manager,
            "get_active_project",
            return_value=self.project,
        )
        self.conn_patch = patch.object(
            execution_router.connection,
            "get_connection",
            new=AsyncMock(return_value=self.db),
        )
        self.project_patch.start()
        self.conn_patch.start()
        await get_execution_runtime().reset_for_tests()

    async def asyncTearDown(self) -> None:
        await get_execution_runtime().reset_for_tests()
        self.project_patch.stop()
        self.conn_patch.stop()
        await self.db.close()
        self._tmp.cleanup()

    async def _wait_for_terminal_status(self, run_id: str, timeout_seconds: float = 6.0) -> str:
        loop = 0
        attempts = max(1, int(timeout_seconds / 0.05))
        while loop < attempts:
            loop += 1
            run = await execution_router.get_execution_run(run_id)
            if run.status in {"succeeded", "failed", "canceled", "blocked"}:
                return run.status
            await asyncio.sleep(0.05)
        return (await execution_router.get_execution_run(run_id)).status

    async def test_policy_check_endpoint(self) -> None:
        result = await execution_router.check_execution_policy(
            ExecutionPolicyCheckRequest(command="git status", cwd=".", envProfile="default")
        )
        self.assertEqual(result.verdict, "allow")
        self.assertEqual(result.riskLevel, "low")

    async def test_create_run_allow_and_stream_output(self) -> None:
        run = await execution_router.create_execution_run(
            ExecutionRunCreateRequest(
                command="echo execution-ok",
                cwd=".",
                featureId="feat-1",
                recommendationRuleId="R2_START_PHASE_1",
            )
        )
        terminal_status = await self._wait_for_terminal_status(run.id)
        self.assertEqual(terminal_status, "succeeded")

        events = await execution_router.list_execution_run_events(run.id)
        payloads = [event.payloadText for event in events.items]
        self.assertTrue(any("execution-ok" in text for text in payloads))

    async def test_requires_approval_then_approve(self) -> None:
        run = await execution_router.create_execution_run(
            ExecutionRunCreateRequest(
                command="rm -rf build",
                cwd=".",
                featureId="feat-1",
            )
        )
        self.assertEqual(run.policyVerdict, "requires_approval")
        self.assertTrue(run.requiresApproval)
        self.assertEqual(run.status, "blocked")

        approved = await execution_router.approve_execution_run(
            run.id,
            ExecutionApprovalRequest(decision="approved", reason="approved in test", actor="tester"),
        )
        self.assertIn(approved.status, {"queued", "running", "succeeded", "failed", "canceled"})
        terminal_status = await self._wait_for_terminal_status(run.id)
        self.assertIn(terminal_status, {"succeeded", "failed", "canceled"})

    async def test_deny_blocked_pattern(self) -> None:
        run = await execution_router.create_execution_run(
            ExecutionRunCreateRequest(command="rm -rf /", cwd=".")
        )
        self.assertEqual(run.policyVerdict, "deny")
        self.assertEqual(run.status, "blocked")

    async def test_cancel_running_run(self) -> None:
        run = await execution_router.create_execution_run(
            ExecutionRunCreateRequest(
                command='python -u -c "import time; print(\'begin\'); time.sleep(3); print(\'done\')"',
                cwd=".",
                featureId="feat-1",
            )
        )
        self.assertIn(run.status, {"queued", "running"})

        canceled = await execution_router.cancel_execution_run(
            run.id,
            ExecutionCancelRequest(reason="test cancel", actor="tester"),
        )
        self.assertEqual(canceled.status, "canceled")
        terminal_status = await self._wait_for_terminal_status(run.id)
        self.assertEqual(terminal_status, "canceled")


if __name__ == "__main__":
    unittest.main()
