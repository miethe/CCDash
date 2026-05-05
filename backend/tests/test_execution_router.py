import asyncio
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import aiosqlite
from fastapi import HTTPException

from backend.adapters.auth.local import LocalIdentityProvider
from backend.adapters.integrations.local import NoopIntegrationClient
from backend.adapters.jobs.local import InProcessJobScheduler
from backend.adapters.storage.local import LocalStorageUnitOfWork
from backend.adapters.workspaces.local import ProjectManagerWorkspaceRegistry
from backend.application.context import Principal, ProjectScope, RequestContext, TraceContext
from backend.application.ports import AuthorizationDecision, CorePorts
from backend.db.sqlite_migrations import run_migrations
from backend.models import (
    ExecutionApprovalRequest,
    ExecutionCancelRequest,
    ExecutionPolicyCheckRequest,
    ExecutionRunCreateRequest,
    Project,
)
from backend.project_manager import ProjectManager
from backend.routers import execution as execution_router
from backend.services.execution_runtime import get_execution_runtime


class _AllowAuthorizationPolicy:
    def __init__(self) -> None:
        self.calls: list[dict[str, str | None]] = []

    async def authorize(self, context, *, action, resource=None):
        _ = context
        self.calls.append({"action": action, "resource": resource})
        return AuthorizationDecision(allowed=True, code="permission_allowed")


class _DenyAuthorizationPolicy:
    def __init__(self) -> None:
        self.calls: list[dict[str, str | None]] = []

    async def authorize(self, context, *, action, resource=None):
        _ = context
        self.calls.append({"action": action, "resource": resource})
        return AuthorizationDecision(
            allowed=False,
            code="permission_not_granted",
            reason=f"{action} denied in test",
        )


def _request_context(root_path: Path | None = None) -> RequestContext:
    root = root_path or Path("/tmp/project-1")
    return RequestContext(
        principal=Principal(subject="test:operator", display_name="Operator", auth_mode="test"),
        workspace=None,
        project=ProjectScope(
            project_id="project-1",
            project_name="Project 1",
            root_path=root,
            sessions_dir=root / ".claude" / "sessions",
            docs_dir=root / "docs",
            progress_dir=root / ".claude" / "progress",
        ),
        runtime_profile="test",
        trace=TraceContext(request_id="req-execution-deny"),
    )


class ExecutionRouterAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_run_denies_without_execution_create_permission(self) -> None:
        policy = _DenyAuthorizationPolicy()
        with self.assertRaises(HTTPException) as ctx:
            await execution_router.create_execution_run(
                ExecutionRunCreateRequest(command="echo no", cwd="."),
                request_context=_request_context(),
                core_ports=types.SimpleNamespace(authorization_policy=policy),
            )

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail["action"], "execution.run:create")
        self.assertEqual(ctx.exception.detail["resource"], "project:project-1")
        self.assertEqual(policy.calls, [{"action": "execution.run:create", "resource": "project:project-1"}])


class ExecutionRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.workspace = Path(self._tmp.name).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await run_migrations(self.db)

        self.project_manager = ProjectManager(self.workspace / "projects.json")
        self.project = Project(
            id="project-1",
            name="Project 1",
            path=str(self.workspace),
        )
        self.project_manager.add_project(self.project)
        self.project_manager.set_active_project(self.project.id)
        self.authorization_policy = _AllowAuthorizationPolicy()
        self.core_ports = CorePorts(
            identity_provider=LocalIdentityProvider(),
            authorization_policy=self.authorization_policy,
            workspace_registry=ProjectManagerWorkspaceRegistry(self.project_manager),
            storage=LocalStorageUnitOfWork(self.db),
            job_scheduler=InProcessJobScheduler(),
            integration_client=NoopIntegrationClient(),
        )
        self.request_context = _request_context(self.workspace)
        await get_execution_runtime().reset_for_tests()

    async def asyncTearDown(self) -> None:
        await get_execution_runtime().reset_for_tests()
        await self.db.close()
        self._tmp.cleanup()

    async def _wait_for_terminal_status(self, run_id: str, timeout_seconds: float = 6.0) -> str:
        loop = 0
        attempts = max(1, int(timeout_seconds / 0.05))
        while loop < attempts:
            loop += 1
            run = await execution_router.get_execution_run(
                run_id,
                request_context=self.request_context,
                core_ports=self.core_ports,
            )
            if run.status in {"succeeded", "failed", "canceled", "blocked"}:
                return run.status
            await asyncio.sleep(0.05)
        return (
            await execution_router.get_execution_run(
                run_id,
                request_context=self.request_context,
                core_ports=self.core_ports,
            )
        ).status

    async def test_policy_check_endpoint(self) -> None:
        result = await execution_router.check_execution_policy(
            ExecutionPolicyCheckRequest(command="git status", cwd=".", envProfile="default"),
            request_context=self.request_context,
            core_ports=self.core_ports,
        )
        self.assertEqual(result.verdict, "allow")
        self.assertEqual(result.riskLevel, "low")
        self.assertEqual(
            self.authorization_policy.calls,
            [{"action": "execution.run:create", "resource": "project:project-1"}],
        )

    async def test_create_run_allow_and_stream_output(self) -> None:
        run = await execution_router.create_execution_run(
            ExecutionRunCreateRequest(
                command="echo execution-ok",
                cwd=".",
                featureId="feat-1",
                recommendationRuleId="R2_START_PHASE_1",
            ),
            request_context=self.request_context,
            core_ports=self.core_ports,
        )
        terminal_status = await self._wait_for_terminal_status(run.id)
        self.assertEqual(terminal_status, "succeeded")

        events = await execution_router.list_execution_run_events(
            run.id,
            request_context=self.request_context,
            core_ports=self.core_ports,
        )
        payloads = [event.payloadText for event in events.items]
        self.assertTrue(any("execution-ok" in text for text in payloads))

    async def test_requires_approval_then_approve(self) -> None:
        run = await execution_router.create_execution_run(
            ExecutionRunCreateRequest(
                command="rm -rf build",
                cwd=".",
                featureId="feat-1",
            ),
            request_context=self.request_context,
            core_ports=self.core_ports,
        )
        self.assertEqual(run.policyVerdict, "requires_approval")
        self.assertTrue(run.requiresApproval)
        self.assertEqual(run.status, "blocked")

        approved = await execution_router.approve_execution_run(
            run.id,
            ExecutionApprovalRequest(decision="approved", reason="approved in test", actor="tester"),
            request_context=self.request_context,
            core_ports=self.core_ports,
        )
        self.assertIn(approved.status, {"queued", "running", "succeeded", "failed", "canceled"})
        terminal_status = await self._wait_for_terminal_status(run.id)
        self.assertIn(terminal_status, {"succeeded", "failed", "canceled"})

    async def test_deny_blocked_pattern(self) -> None:
        run = await execution_router.create_execution_run(
            ExecutionRunCreateRequest(command="rm -rf /", cwd="."),
            request_context=self.request_context,
            core_ports=self.core_ports,
        )
        self.assertEqual(run.policyVerdict, "deny")
        self.assertEqual(run.status, "blocked")

    async def test_cancel_running_run(self) -> None:
        run = await execution_router.create_execution_run(
            ExecutionRunCreateRequest(
                command='python -u -c "import time; print(\'begin\'); time.sleep(3); print(\'done\')"',
                cwd=".",
                featureId="feat-1",
            ),
            request_context=self.request_context,
            core_ports=self.core_ports,
        )
        self.assertIn(run.status, {"queued", "running"})

        canceled = await execution_router.cancel_execution_run(
            run.id,
            ExecutionCancelRequest(reason="test cancel", actor="tester"),
            request_context=self.request_context,
            core_ports=self.core_ports,
        )
        self.assertEqual(canceled.status, "canceled")
        terminal_status = await self._wait_for_terminal_status(run.id)
        self.assertEqual(terminal_status, "canceled")


if __name__ == "__main__":
    unittest.main()
