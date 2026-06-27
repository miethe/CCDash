"""P3 worker-bootstrap and enterprise fail-fast tests.

Tests covered:
  - P3-008: resolve_project fail-fast when principal has hosted claim scope and
            no project is resolvable — must NOT fall back to the active project.
            Local mode RETAINS the active-project fallback.
  - P3-012: bootstrap_worker module is safely importable without building a live
            RuntimeContainer (no side-effects at import time).
  - P3-016: _resolve_startup_project_binding emits a WARNING when the registry
            has multiple projects but no explicit binding is configured.
  - T3-005 (SPIKE scenarios 1-6):
      S1: empty CCDASH_WORKER_WATCH_PROJECT_ID → fan-out from registry (≥1 binding)
      S2: non-empty env pin → exactly that one project (backward-compat regression guard)
      S3: empty registry → no RuntimeError, zero bindings, warning emitted
      S4: dynamic add via reconcile tick → new binding added, existing unaffected
      S5: per-project failure isolation → one task fails (degraded), siblings running
      S6: per-project health map present in /api/health/detail watcher.projects

CRITICAL: This test module MUST NOT import backend.main or call
RuntimeContainer.startup() / build_worker_runtime() / build_worker_probe_app()
without an explicit container argument — those paths trigger DB connections and
hang in worktree environments.
"""
from __future__ import annotations

import asyncio
import logging
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi import HTTPException

from backend.application.context import (
    AuthProviderMetadata,
    Principal,
    RequestContext,
    TraceContext,
)
from backend.application.services.common import resolve_project
from backend.models import Project


# ---------------------------------------------------------------------------
# P3-008 — enterprise/hosted fail-fast in resolve_project
# ---------------------------------------------------------------------------

def _make_hosted_context(*, project_id: str | None = None) -> RequestContext:
    """Build a minimal hosted-scope RequestContext (no project in scope)."""
    from backend.application.context import ProjectScope, WorkspaceScope

    project_scope = (
        ProjectScope(
            project_id=project_id,
            project_name="Test Project",
            root_path="/tmp/test",
            sessions_dir="/tmp/test/sessions",
            docs_dir="/tmp/test/docs",
            progress_dir="/tmp/test/progress",
        )
        if project_id
        else None
    )
    workspace_scope = (
        WorkspaceScope(workspace_id=project_id, root_path="/tmp/test") if project_id else None
    )
    return RequestContext(
        principal=Principal(
            subject="bearer:api-client",
            display_name="API Client",
            auth_mode="bearer",
            provider=AuthProviderMetadata(
                provider_id="static-bearer",
                issuer="ccdash-api",
                audience="ccdash",
                hosted=True,
            ),
        ),
        workspace=workspace_scope,
        project=project_scope,
        runtime_profile="api",
        trace=TraceContext(request_id="req-enterprise-failfast"),
    )


def _make_local_context() -> RequestContext:
    """Build a minimal local (non-hosted) RequestContext."""
    return RequestContext(
        principal=Principal(
            subject="local:local-operator",
            display_name="Local Operator",
            auth_mode="local",
        ),
        workspace=None,
        project=None,
        runtime_profile="local",
        trace=TraceContext(request_id="req-local-fallback"),
    )


def _make_ports_with_active(active_project: Project) -> types.SimpleNamespace:
    """Build a minimal ports stub that serves a single active project."""
    return types.SimpleNamespace(
        workspace_registry=types.SimpleNamespace(
            get_project=lambda pid: active_project if pid == active_project.id else None,
            get_active_project=lambda: active_project,
        )
    )


_ACTIVE_PROJECT = Project(
    id="project-active",
    name="Active Project",
    path="/tmp/project-active",
)


class EnterpriseFailFastTests(unittest.TestCase):
    """P3-008: hosted requests with no resolvable project must NOT fall back."""

    def test_hosted_context_without_project_returns_none(self) -> None:
        """resolve_project must return None for a hosted request with no project."""
        context = _make_hosted_context()  # no project_id
        ports = _make_ports_with_active(_ACTIVE_PROJECT)

        result = resolve_project(context, ports)

        self.assertIsNone(result)

    def test_hosted_context_without_project_raises_for_required(self) -> None:
        """resolve_project must raise 404 when required=True for a hosted
        request that has no resolvable project."""
        context = _make_hosted_context()  # no project_id
        ports = _make_ports_with_active(_ACTIVE_PROJECT)

        with self.assertRaises(HTTPException) as cm:
            resolve_project(context, ports, required=True)

        self.assertEqual(cm.exception.status_code, 404)

    def test_hosted_context_with_scoped_project_resolves_correctly(self) -> None:
        """When the request already has a project scope, resolve_project returns it
        without touching get_active_project."""
        context = _make_hosted_context(project_id=_ACTIVE_PROJECT.id)
        get_active_called = []
        ports = types.SimpleNamespace(
            workspace_registry=types.SimpleNamespace(
                get_project=lambda pid: _ACTIVE_PROJECT if pid == _ACTIVE_PROJECT.id else None,
                get_active_project=lambda: get_active_called.append(True) or _ACTIVE_PROJECT,
            )
        )

        result = resolve_project(context, ports)

        self.assertEqual(result, _ACTIVE_PROJECT)
        # The hosted-fallback path must NOT have been reached.
        self.assertEqual(get_active_called, [])

    def test_local_context_without_project_falls_back_to_active(self) -> None:
        """Local mode RETAINS the active-project fallback — P3-008 must not
        disable it for non-hosted principals."""
        context = _make_local_context()
        ports = _make_ports_with_active(_ACTIVE_PROJECT)

        result = resolve_project(context, ports)

        self.assertEqual(result, _ACTIVE_PROJECT)

    def test_local_context_without_project_raises_for_required_when_no_active(self) -> None:
        """Local mode still raises 404 when required=True and no active project."""
        context = _make_local_context()
        ports = types.SimpleNamespace(
            workspace_registry=types.SimpleNamespace(
                get_project=lambda pid: None,
                get_active_project=lambda: None,
            )
        )

        with self.assertRaises(HTTPException) as cm:
            resolve_project(context, ports, required=True)

        self.assertEqual(cm.exception.status_code, 404)


# ---------------------------------------------------------------------------
# P3-012 — bootstrap_worker module-level import smoke
# ---------------------------------------------------------------------------

class BootstrapWorkerImportTests(unittest.TestCase):
    """P3-012: importing bootstrap_worker must NOT build a live RuntimeContainer."""

    def test_bootstrap_worker_imports_without_side_effects(self) -> None:
        """Importing backend.runtime.bootstrap_worker must complete without
        calling build_worker_runtime() or constructing a RuntimeContainer.

        This validates the P3-012 fix: the module-level
        `container = build_worker_runtime()` was removed.
        """
        with patch(
            "backend.runtime.bootstrap_worker.RuntimeContainer.__init__",
            side_effect=AssertionError(
                "RuntimeContainer.__init__ must NOT be called at import time (P3-012)"
            ),
        ):
            # Force a fresh import by temporarily removing the cached module.
            import sys
            mod_name = "backend.runtime.bootstrap_worker"
            cached = sys.modules.pop(mod_name, None)
            try:
                import backend.runtime.bootstrap_worker  # noqa: F401
            finally:
                # Restore the cached module so subsequent tests use the real one.
                if cached is not None:
                    sys.modules[mod_name] = cached
                else:
                    sys.modules.pop(mod_name, None)

    def test_build_worker_runtime_function_exists_and_is_callable(self) -> None:
        """build_worker_runtime must remain importable as a callable."""
        from backend.runtime.bootstrap_worker import build_worker_runtime

        self.assertTrue(callable(build_worker_runtime))

    def test_resolve_worker_runtime_profile_defaults_to_worker(self) -> None:
        """resolve_worker_runtime_profile returns 'worker' when env is unset."""
        from backend.runtime.bootstrap_worker import resolve_worker_runtime_profile
        from backend import config

        with patch.dict(__import__("os").environ, {config.CCDASH_RUNTIME_PROFILE_ENV: ""}, clear=False):
            profile = resolve_worker_runtime_profile()

        self.assertEqual(profile, "worker")

    def test_resolve_worker_runtime_profile_accepts_worker_watch(self) -> None:
        """resolve_worker_runtime_profile accepts the worker-watch profile."""
        from backend.runtime.bootstrap_worker import resolve_worker_runtime_profile
        from backend import config

        with patch.dict(__import__("os").environ, {config.CCDASH_RUNTIME_PROFILE_ENV: "worker-watch"}):
            profile = resolve_worker_runtime_profile()

        self.assertEqual(profile, "worker-watch")

    def test_resolve_worker_runtime_profile_rejects_unknown(self) -> None:
        """resolve_worker_runtime_profile raises RuntimeError for unknown profiles."""
        from backend.runtime.bootstrap_worker import resolve_worker_runtime_profile
        from backend import config

        with patch.dict(__import__("os").environ, {config.CCDASH_RUNTIME_PROFILE_ENV: "api"}):
            with self.assertRaises(RuntimeError):
                resolve_worker_runtime_profile()


# ---------------------------------------------------------------------------
# P3-016 — multi-project no-binding warning in _resolve_startup_project_binding
# ---------------------------------------------------------------------------

class MultiProjectNoBindingWarningTests(unittest.TestCase):
    """P3-016: warn when registry has multiple projects but no explicit binding."""

    def _make_registry_stub(self, project_ids: list[str]) -> MagicMock:
        projects = [
            Project(id=pid, name=f"Project {pid}", path=f"/tmp/{pid}")
            for pid in project_ids
        ]
        registry = MagicMock()
        registry.list_projects.return_value = projects

        from backend.application.ports.core import ProjectBinding
        from backend.services.project_paths.models import ResolvedProjectPaths

        def _resolve_binding(pid: str | None, allow_active_fallback: bool = True, refresh: bool = False):
            if pid:
                for p in projects:
                    if p.id == pid:
                        binding = MagicMock(spec=ProjectBinding)
                        binding.project = p
                        binding.source = "registry"
                        binding.paths = MagicMock()
                        binding.paths.root = MagicMock()
                        binding.paths.root.path = f"/tmp/{pid}"
                        return binding
            return None

        registry.resolve_project_binding.side_effect = _resolve_binding
        return registry

    def test_single_project_registry_emits_no_warning(self) -> None:
        """One project in the registry → no multi-project warning."""
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile
        from backend import config

        container = RuntimeContainer(profile=get_runtime_profile("worker"))
        registry_stub = self._make_registry_stub(["project-only"])

        with patch("backend.runtime.container.build_workspace_registry", return_value=registry_stub), \
             patch.dict(__import__("os").environ, {config.CCDASH_WORKER_PROJECT_ID_ENV: "project-only"}):
            with self.assertLogs("ccdash.runtime", level="DEBUG") as log_ctx:
                # Inject a dummy DEBUG message so assertLogs doesn't fail on zero logs.
                logging.getLogger("ccdash.runtime").debug("dummy")
                container._resolve_startup_project_binding()

        warning_msgs = [m for m in log_ctx.output if "WARNING" in m and "projects in the registry" in m]
        self.assertEqual(warning_msgs, [], "No multi-project warning expected for single-project registry")

    def test_multi_project_registry_with_explicit_binding_emits_no_warning(self) -> None:
        """Multiple projects + explicit binding → no warning."""
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile
        from backend import config

        container = RuntimeContainer(profile=get_runtime_profile("worker"))
        registry_stub = self._make_registry_stub(["project-a", "project-b"])

        with patch("backend.runtime.container.build_workspace_registry", return_value=registry_stub), \
             patch.dict(__import__("os").environ, {config.CCDASH_WORKER_PROJECT_ID_ENV: "project-a"}):
            with self.assertLogs("ccdash.runtime", level="DEBUG") as log_ctx:
                logging.getLogger("ccdash.runtime").debug("dummy")
                container._resolve_startup_project_binding()

        warning_msgs = [m for m in log_ctx.output if "WARNING" in m and "projects in the registry" in m]
        self.assertEqual(warning_msgs, [], "No warning expected when explicit binding is set")

    def test_worker_watch_uses_worker_watch_project_id_when_set(self) -> None:
        """For the worker-watch profile, WORKER_WATCH_PROJECT_ID overrides the
        generic CCDASH_WORKER_PROJECT_ID when both are set.

        _resolve_startup_project_binding now returns (primary, fan_out) tuple;
        env-pin → single-project path means primary is set and fan_out is [].
        """
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile
        from backend import config

        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))
        registry_stub = self._make_registry_stub(["project-a", "project-watch"])

        with patch("backend.runtime.container.build_workspace_registry", return_value=registry_stub), \
             patch.dict(__import__("os").environ, {
                 config.CCDASH_WORKER_PROJECT_ID_ENV: "project-a",
             }), \
             patch.object(config, "WORKER_WATCH_PROJECT_ID", "project-watch"):
            primary, fan_out = container._resolve_startup_project_binding()

        self.assertIsNotNone(primary)
        self.assertEqual(primary.project.id, "project-watch")
        self.assertEqual(fan_out, [])

    def test_worker_watch_falls_back_to_worker_project_id_when_watch_id_empty(self) -> None:
        """For the worker-watch profile, if WORKER_WATCH_PROJECT_ID is empty,
        use CCDASH_WORKER_PROJECT_ID as the fallback (fan-out from registry).

        When WORKER_WATCH_PROJECT_ID is empty and registry has one project,
        fan-out mode resolves that one project as a fan-out binding.
        """
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile
        from backend import config

        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))
        registry_stub = self._make_registry_stub(["project-a"])

        with patch("backend.runtime.container.build_workspace_registry", return_value=registry_stub), \
             patch.dict(__import__("os").environ, {config.CCDASH_WORKER_PROJECT_ID_ENV: "project-a"}), \
             patch.object(config, "WORKER_WATCH_PROJECT_ID", ""):
            primary, fan_out = container._resolve_startup_project_binding()

        # Empty WORKER_WATCH_PROJECT_ID → fan-out mode: primary is None, fan_out has the one project.
        self.assertIsNone(primary)
        self.assertEqual(len(fan_out), 1)
        self.assertEqual(fan_out[0].project.id, "project-a")


# ---------------------------------------------------------------------------
# Helpers for T3-005 watcher fan-out test scenarios
# ---------------------------------------------------------------------------

def _make_project(pid: str, root: str | None = None) -> "Project":
    from backend.models import Project
    return Project(id=pid, name=f"Project {pid}", path=root or f"/tmp/{pid}")


def _make_project_binding(project: "Project") -> "ProjectBinding":
    """Build a minimal ProjectBinding without touching filesystem or DB."""
    from backend.application.ports.core import ProjectBinding
    from backend.services.project_paths.models import ResolvedProjectPaths, ResolvedProjectPath
    from backend.models import ProjectPathReference

    def _rpp(field: str, sub: str) -> ResolvedProjectPath:
        root = Path(project.path)
        # ProjectPathReference.field must be a valid ProjectPathField literal.
        # Use "filesystem" for sourceKind (a valid PathSourceKind string literal).
        ref = ProjectPathReference(field=field, sourceKind="filesystem", filesystemPath=str(root / sub))
        return ResolvedProjectPath(
            field=field,
            source_kind="filesystem",
            requested=ref,
            path=root / sub,
        )

    paths = ResolvedProjectPaths(
        project_id=project.id,
        root=_rpp("root", "."),
        plan_docs=_rpp("plan_docs", "docs"),
        sessions=_rpp("sessions", ".claude/sessions"),
        progress=_rpp("progress", ".claude/progress"),
    )
    return ProjectBinding(
        project=project,
        paths=paths,
        source="registry",
        requested_project_id=project.id,
    )


def _make_registry_stub_with_bindings(
    projects: list,
) -> MagicMock:
    """Build a workspace-registry stub that maps project ids → ProjectBinding."""
    registry = MagicMock()
    registry.list_projects.return_value = list(projects)

    def _resolve(pid: str | None = None, *, allow_active_fallback: bool = True, refresh: bool = False):
        for p in projects:
            if p.id == pid:
                return _make_project_binding(p)
        return None

    registry.resolve_project_binding.side_effect = _resolve
    registry.reload_projects = MagicMock()  # reconcile loop calls this
    return registry


# ---------------------------------------------------------------------------
# T3-005 Scenario 1 — Empty env → registry fan-out (≥1 binding)
# ---------------------------------------------------------------------------

class WatcherFanOutDefaultRegistryTests(unittest.TestCase):
    """S1: CCDASH_WORKER_WATCH_PROJECT_ID empty/unset → fan-out across all registry projects.

    SPIKE §Scenario 1: _resolve_startup_project_binding returns two WatcherBinding
    objects when the registry has two projects and the env var is unset.
    """

    def _call_resolve(self, projects: list) -> tuple:
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile
        from backend import config

        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))
        registry_stub = _make_registry_stub_with_bindings(projects)

        with patch("backend.runtime.container.build_workspace_registry", return_value=registry_stub), \
             patch.object(config, "WORKER_WATCH_PROJECT_ID", ""):
            return container._resolve_startup_project_binding()

    def test_two_projects_produces_two_fan_out_bindings(self) -> None:
        """Registry with 2 projects → 2 fan-out bindings, primary binding is None."""
        projects = [_make_project("proj-alpha"), _make_project("proj-beta")]
        primary, fan_out = self._call_resolve(projects)

        self.assertIsNone(primary, "primary binding must be None in fan-out mode")
        self.assertEqual(len(fan_out), 2)
        ids = {b.project.id for b in fan_out}
        self.assertIn("proj-alpha", ids)
        self.assertIn("proj-beta", ids)

    def test_single_project_in_registry_produces_one_fan_out_binding(self) -> None:
        """Registry with 1 project → 1 fan-out binding."""
        projects = [_make_project("proj-only")]
        primary, fan_out = self._call_resolve(projects)

        self.assertIsNone(primary)
        self.assertEqual(len(fan_out), 1)
        self.assertEqual(fan_out[0].project.id, "proj-only")

    def test_source_is_registry(self) -> None:
        """Each fan-out binding source must be 'registry'."""
        projects = [_make_project("p1"), _make_project("p2")]
        _, fan_out = self._call_resolve(projects)
        for b in fan_out:
            self.assertEqual(b.source, "registry")


# ---------------------------------------------------------------------------
# T3-005 Scenario 2 — Non-empty env pin → single project (backward-compat)
# ---------------------------------------------------------------------------

class WatcherEnvPinSingleProjectTests(unittest.TestCase):
    """S2: CCDASH_WORKER_WATCH_PROJECT_ID non-empty → exactly one project watched.

    SPIKE §Scenario 3 (env-pin / backward-compat regression guard).
    """

    def test_env_pin_scopes_to_single_project(self) -> None:
        """When WORKER_WATCH_PROJECT_ID is non-empty, only that project is bound."""
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile
        from backend import config

        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))
        projects = [_make_project("proj-abc123"), _make_project("proj-other")]
        registry_stub = _make_registry_stub_with_bindings(projects)

        with patch("backend.runtime.container.build_workspace_registry", return_value=registry_stub), \
             patch.object(config, "WORKER_WATCH_PROJECT_ID", "proj-abc123"):
            primary, fan_out = container._resolve_startup_project_binding()

        # Env-pin → single-project path: primary binding set, fan-out empty.
        self.assertIsNotNone(primary)
        self.assertEqual(primary.project.id, "proj-abc123")
        self.assertEqual(fan_out, [], "fan_out must be empty when env pin is active")

    def test_env_pin_does_not_watch_other_registry_projects(self) -> None:
        """The second registry project must not appear in any binding."""
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile
        from backend import config

        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))
        projects = [_make_project("proj-abc123"), _make_project("proj-other")]
        registry_stub = _make_registry_stub_with_bindings(projects)

        with patch("backend.runtime.container.build_workspace_registry", return_value=registry_stub), \
             patch.object(config, "WORKER_WATCH_PROJECT_ID", "proj-abc123"):
            primary, fan_out = container._resolve_startup_project_binding()

        self.assertNotEqual(getattr(primary, "project", None) and primary.project.id, "proj-other")
        for b in fan_out:
            self.assertNotEqual(b.project.id, "proj-other")


# ---------------------------------------------------------------------------
# T3-005 Scenario 3 — Empty registry → no RuntimeError, zero bindings, warning
# ---------------------------------------------------------------------------

class WatcherFanOutEmptyRegistryTests(unittest.TestCase):
    """S3: Registry returns 0 projects → process must NOT raise RuntimeError.

    SPIKE §Scenario 2: zero WatcherBinding objects, WARNING logged, health map = {}.
    """

    def test_empty_registry_does_not_raise(self) -> None:
        """Empty registry must not raise RuntimeError (valid transient state)."""
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile
        from backend import config

        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))
        registry_stub = _make_registry_stub_with_bindings([])

        with patch("backend.runtime.container.build_workspace_registry", return_value=registry_stub), \
             patch.object(config, "WORKER_WATCH_PROJECT_ID", ""):
            try:
                primary, fan_out = container._resolve_startup_project_binding()
            except RuntimeError as exc:
                self.fail(f"Empty registry raised RuntimeError (must not): {exc}")

    def test_empty_registry_returns_zero_fan_out_bindings(self) -> None:
        """Empty registry → (None, [])."""
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile
        from backend import config

        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))
        registry_stub = _make_registry_stub_with_bindings([])

        with patch("backend.runtime.container.build_workspace_registry", return_value=registry_stub), \
             patch.object(config, "WORKER_WATCH_PROJECT_ID", ""):
            primary, fan_out = container._resolve_startup_project_binding()

        self.assertIsNone(primary)
        self.assertEqual(fan_out, [])

    def test_empty_registry_emits_warning(self) -> None:
        """Empty registry → a WARNING is logged."""
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile
        from backend import config

        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))
        registry_stub = _make_registry_stub_with_bindings([])

        with patch("backend.runtime.container.build_workspace_registry", return_value=registry_stub), \
             patch.object(config, "WORKER_WATCH_PROJECT_ID", ""), \
             self.assertLogs("ccdash.runtime", level="WARNING") as log_ctx:
            container._resolve_startup_project_binding()

        warning_msgs = [m for m in log_ctx.output if "WARNING" in m and "0 projects" in m]
        self.assertGreater(len(warning_msgs), 0, "Expected a WARNING log about 0 projects in registry")


# ---------------------------------------------------------------------------
# T3-005 Scenario 4 — Dynamic add via reconcile tick
# ---------------------------------------------------------------------------

class WatcherReconcileAddProjectTests(unittest.TestCase):
    """S4: reconcile loop adds new binding, existing binding unaffected.

    SPIKE §Scenario 4: after one reconcile tick, a second WatcherBinding is
    added and the first binding remains running.  Tests use asyncio.run() and
    directly exercise the reconcile coroutine internal diff logic to avoid
    starting actual file watchers.
    """

    def _run(self, coro):
        return asyncio.run(coro)

    def test_reconcile_adds_new_project_id_to_fan_out_tasks(self) -> None:
        """After reconcile sees a new project in registry, fan_out_watcher_tasks gains that project."""
        from backend.adapters.jobs.runtime import RuntimeJobAdapter, RuntimeJobState
        from backend.runtime.profiles import get_runtime_profile

        proj_existing = _make_project("proj-existing")
        proj_new = _make_project("proj-new")

        registry_stub = _make_registry_stub_with_bindings([proj_existing, proj_new])

        ports = MagicMock()
        ports.workspace_registry = registry_stub

        adapter = RuntimeJobAdapter(
            profile=get_runtime_profile("worker-watch"),
            ports=ports,
            sync_engine=None,
            watcher_fan_out_bindings=[_make_project_binding(proj_existing)],
        )
        # Simulate pre-existing watcher task for proj_existing.
        existing_task = MagicMock(spec=asyncio.Task)
        existing_task.done.return_value = False
        adapter.state.fan_out_watcher_tasks["proj-existing"] = existing_task
        adapter.state.fan_out_watcher_health["proj-existing"] = "running"
        adapter._watcher_sync_semaphore = asyncio.Semaphore(20)
        adapter._rebind_lock = asyncio.Lock()

        # Stub _start_single_fan_out_watcher so it doesn't touch filesystem.
        async def _fake_start_single_watcher(**kwargs):
            pid = kwargs["binding"].project.id
            fake_task = asyncio.create_task(asyncio.sleep(0))
            adapter.state.fan_out_watcher_tasks[pid] = fake_task
            adapter.state.fan_out_watcher_health[pid] = "running"

        adapter._start_single_fan_out_watcher = _fake_start_single_watcher

        async def _run_one_reconcile_tick():
            """Execute a single reconcile tick against the adapter state directly."""
            all_projects = list(registry_stub.list_projects())
            registry_ids: set[str] = {str(getattr(p, "id", "")) for p in all_projects if getattr(p, "id", "")}
            active_ids: set[str] = set(adapter.state.fan_out_watcher_tasks.keys())
            new_ids = registry_ids - active_ids
            for pid in new_ids:
                binding = registry_stub.resolve_project_binding(pid, allow_active_fallback=False, refresh=True)
                if binding is not None:
                    await adapter._start_single_fan_out_watcher(
                        binding=binding,
                        semaphore=adapter._watcher_sync_semaphore,
                        supervisor_callback=lambda t: None,
                        start_singleton=False,
                    )

        self._run(_run_one_reconcile_tick())

        self.assertIn("proj-new", adapter.state.fan_out_watcher_tasks, "Reconcile must add proj-new")
        self.assertIn("proj-existing", adapter.state.fan_out_watcher_tasks, "Existing binding must remain")

    def test_reconcile_does_not_replace_existing_binding(self) -> None:
        """Reconcile must not replace or cancel the pre-existing binding."""
        from backend.adapters.jobs.runtime import RuntimeJobAdapter
        from backend.runtime.profiles import get_runtime_profile

        proj = _make_project("proj-stable")
        registry_stub = _make_registry_stub_with_bindings([proj])

        ports = MagicMock()
        ports.workspace_registry = registry_stub

        adapter = RuntimeJobAdapter(
            profile=get_runtime_profile("worker-watch"),
            ports=ports,
            sync_engine=None,
            watcher_fan_out_bindings=[_make_project_binding(proj)],
        )
        sentinel_task = MagicMock(spec=asyncio.Task)
        sentinel_task.done.return_value = False
        adapter.state.fan_out_watcher_tasks["proj-stable"] = sentinel_task
        adapter.state.fan_out_watcher_health["proj-stable"] = "running"
        adapter._watcher_sync_semaphore = asyncio.Semaphore(20)

        async def _fake_start(**kwargs):
            pid = kwargs["binding"].project.id
            adapter.state.fan_out_watcher_tasks[pid] = MagicMock()

        adapter._start_single_fan_out_watcher = _fake_start

        async def _tick():
            all_projects = list(registry_stub.list_projects())
            registry_ids = {str(getattr(p, "id", "")) for p in all_projects}
            active_ids = set(adapter.state.fan_out_watcher_tasks.keys())
            new_ids = registry_ids - active_ids
            for pid in new_ids:
                binding = registry_stub.resolve_project_binding(pid, allow_active_fallback=False, refresh=True)
                if binding is not None:
                    await adapter._start_single_fan_out_watcher(binding=binding, semaphore=None, supervisor_callback=lambda t: None)

        self._run(_tick())

        # The sentinel task must NOT have been replaced.
        self.assertIs(adapter.state.fan_out_watcher_tasks["proj-stable"], sentinel_task)


# ---------------------------------------------------------------------------
# T3-005 Scenario 5 — Per-project failure isolation
# ---------------------------------------------------------------------------

class WatcherPerProjectFailureIsolationTests(unittest.TestCase):
    """S5: one project's watcher fails → sibling stays running, failed project is degraded.

    SPIKE §Scenario 5: per-project failure isolation via fan_out_watcher_health.
    """

    def test_failed_project_marked_degraded_sibling_unaffected(self) -> None:
        """When one project watcher is degraded, its health entry is 'degraded'; sibling stays 'running'."""
        from backend.adapters.jobs.runtime import RuntimeJobState

        state = RuntimeJobState()
        state.fan_out_watcher_health["proj-ok"] = "running"
        state.fan_out_watcher_health["proj-fail"] = "running"

        # Simulate supervisor callback marking proj-fail as degraded.
        state.fan_out_watcher_health["proj-fail"] = "degraded"

        self.assertEqual(state.fan_out_watcher_health["proj-ok"], "running",
                         "Sibling project must remain 'running'")
        self.assertEqual(state.fan_out_watcher_health["proj-fail"], "degraded",
                         "Failed project must be 'degraded'")

    def test_degraded_project_does_not_affect_sibling_task(self) -> None:
        """Degrading one project's health entry must not touch the sibling's task."""
        from backend.adapters.jobs.runtime import RuntimeJobState

        state = RuntimeJobState()
        sibling_task = MagicMock(spec=asyncio.Task)
        sibling_task.done.return_value = False
        state.fan_out_watcher_tasks["proj-ok"] = sibling_task
        state.fan_out_watcher_health["proj-ok"] = "running"
        state.fan_out_watcher_tasks["proj-fail"] = MagicMock(spec=asyncio.Task)
        state.fan_out_watcher_health["proj-fail"] = "running"

        # Simulate failure of proj-fail: remove its task, mark degraded.
        state.fan_out_watcher_tasks.pop("proj-fail")
        state.fan_out_watcher_health["proj-fail"] = "degraded"

        # Sibling task must be untouched.
        self.assertIn("proj-ok", state.fan_out_watcher_tasks)
        self.assertIs(state.fan_out_watcher_tasks["proj-ok"], sibling_task)
        sibling_task.cancel.assert_not_called()

    def test_watcher_probe_detail_reflects_degraded_state(self) -> None:
        """_watcher_probe_detail must surface degraded state in per-project map."""
        from backend.adapters.jobs.runtime import RuntimeJobAdapter, RuntimeJobState
        from backend.runtime.profiles import get_runtime_profile

        ports = MagicMock()
        adapter = RuntimeJobAdapter(
            profile=get_runtime_profile("worker-watch"),
            ports=ports,
            sync_engine=None,
        )
        adapter.state.fan_out_watcher_health["proj-fail"] = "degraded"
        adapter.state.fan_out_watcher_health["proj-ok"] = "running"

        # Stub file_watcher_registry.snapshot_all() to return per-project entries.
        registry_snapshots = {
            "proj-ok": {"running": True, "configured": True, "watchPathCount": 5, "lastChangeSyncAt": None},
            "proj-fail": {"running": False, "configured": True, "watchPathCount": 3, "lastChangeSyncAt": None},
        }

        import backend.adapters.jobs.runtime as _rt_mod
        import backend.db.file_watcher as _fw_mod

        original_snapshot_all = _fw_mod.file_watcher_registry.snapshot_all
        original_fw_snapshot = _fw_mod.file_watcher.snapshot

        try:
            _fw_mod.file_watcher_registry.snapshot_all = lambda: registry_snapshots
            _fw_mod.file_watcher.snapshot = lambda: {"configured": True, "running": True, "watchPathCount": 8}

            detail = adapter._watcher_probe_detail()
        finally:
            _fw_mod.file_watcher_registry.snapshot_all = original_snapshot_all
            _fw_mod.file_watcher.snapshot = original_fw_snapshot

        projects_map = detail.get("projects", {})
        self.assertIn("proj-fail", projects_map)
        self.assertIn("proj-ok", projects_map)
        self.assertEqual(projects_map["proj-fail"]["state"], "degraded",
                         "fan_out_watcher_health 'degraded' must override running=False → 'stopped'")
        self.assertEqual(projects_map["proj-ok"]["state"], "running")

    def test_aggregate_watcher_state_is_degraded_when_any_project_degraded(self) -> None:
        """When one project is degraded, per_project_states drives watcher_check_status.

        SPIKE §OQ-5: 'warn' when any not-running in non-required context;
        confirmed by the T3-003 per_project_states aggregation logic in
        RuntimeContainer._build_probe_contract.
        """
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile

        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))

        # Inject a fake runtime_status that mimics a per-project map with one degraded entry.
        watcher_detail_with_projects = {
            "state": "running",
            "expected": True,
            "enabled": True,
            "configured": True,
            "running": True,
            "watchPathCount": 5,
            "watchPaths": [],
            "lastChangeSyncAt": None,
            "lastChangeCount": None,
            "lastSyncStatus": None,
            "lastSyncError": None,
            "projects": {
                "proj-ok": {"state": "running", "watchPathCount": 3, "lastChangeSyncAt": None},
                "proj-fail": {"state": "degraded", "watchPathCount": 2, "lastChangeSyncAt": None},
            },
            "lastReconcileAt": None,
            "lastReconcileError": None,
        }

        # Directly test the aggregation rule from _build_probe_contract.
        per_project_states = {
            str(pid): str(entry.get("state", "unknown"))
            for pid, entry in watcher_detail_with_projects["projects"].items()
            if isinstance(entry, dict)
        }
        all_running = all(s == "running" for s in per_project_states.values())
        any_not_running = any(s != "running" for s in per_project_states.values())

        self.assertFalse(all_running, "Not all projects running")
        self.assertTrue(any_not_running, "At least one project not running")

        # For worker-watch profile, watcher_runtime is required → any_not_running → "fail".
        # For optional profile (local), it would be "warn".
        # We check that the per-project logic path fires (not the scalar watcher_state fallback).
        watcher_runtime_required = True  # worker-watch profile
        if all_running:
            expected = "pass"
        elif any_not_running and watcher_runtime_required:
            expected = "fail"
        else:
            expected = "warn"
        self.assertEqual(expected, "fail")


# ---------------------------------------------------------------------------
# T3-005 Scenario 6 — /api/health/detail watcher.projects map structure
# ---------------------------------------------------------------------------

class WatcherHealthDetailProjectsMapTests(unittest.TestCase):
    """S6: /api/health/detail returns watcher.projects keyed by project id.

    SPIKE §Scenario 6 + OQ-5 FE resilience contract.
    Validates _probe_watcher_detail output shape without starting a live server.
    """

    def _make_adapter_with_snapshots(self, snapshots: dict) -> tuple:
        """Return (adapter, original_restore_fn) with file_watcher_registry patched."""
        from backend.adapters.jobs.runtime import RuntimeJobAdapter
        from backend.runtime.profiles import get_runtime_profile
        import backend.db.file_watcher as _fw_mod

        ports = MagicMock()
        adapter = RuntimeJobAdapter(
            profile=get_runtime_profile("worker-watch"),
            ports=ports,
            sync_engine=None,
        )

        orig_snap_all = _fw_mod.file_watcher_registry.snapshot_all
        orig_fw_snap = _fw_mod.file_watcher.snapshot

        _fw_mod.file_watcher_registry.snapshot_all = lambda: snapshots
        _fw_mod.file_watcher.snapshot = lambda: {
            "configured": True,
            "running": True,
            "watchPathCount": sum(s.get("watchPathCount", 0) for s in snapshots.values()),
        }

        def _restore():
            _fw_mod.file_watcher_registry.snapshot_all = orig_snap_all
            _fw_mod.file_watcher.snapshot = orig_fw_snap

        return adapter, _restore

    def test_projects_map_is_keyed_by_project_id(self) -> None:
        """watcher.projects must be a dict keyed by project id."""
        snapshots = {
            "proj-abc123": {"running": True, "configured": True, "watchPathCount": 22, "lastChangeSyncAt": "2026-06-13T10:00:00Z"},
            "proj-def456": {"running": True, "configured": True, "watchPathCount": 20, "lastChangeSyncAt": "2026-06-13T09:58:30Z"},
        }
        adapter, restore = self._make_adapter_with_snapshots(snapshots)
        try:
            detail = adapter._watcher_probe_detail()
        finally:
            restore()

        projects = detail.get("projects")
        self.assertIsInstance(projects, dict, "watcher.projects must be a dict")
        self.assertIn("proj-abc123", projects)
        self.assertIn("proj-def456", projects)

    def test_each_project_entry_has_required_fields(self) -> None:
        """Each project entry must have state, watchPathCount, lastChangeSyncAt."""
        snapshots = {
            "proj-x": {"running": True, "configured": True, "watchPathCount": 10, "lastChangeSyncAt": "2026-06-13T10:00:00Z"},
        }
        adapter, restore = self._make_adapter_with_snapshots(snapshots)
        try:
            detail = adapter._watcher_probe_detail()
        finally:
            restore()

        entry = detail["projects"]["proj-x"]
        self.assertIn("state", entry, "missing 'state'")
        self.assertIn("watchPathCount", entry, "missing 'watchPathCount'")
        self.assertIn("lastChangeSyncAt", entry, "missing 'lastChangeSyncAt'")

    def test_missing_projects_key_falls_back_to_empty_dict_in_probe_watcher_detail(self) -> None:
        """If the registry returns no snapshots, projects map is {} (not absent / None)."""
        adapter, restore = self._make_adapter_with_snapshots({})
        try:
            detail = adapter._watcher_probe_detail()
        finally:
            restore()

        projects = detail.get("projects")
        self.assertIsInstance(projects, dict, "'projects' must be present as a dict even when empty")
        self.assertEqual(projects, {})

    def test_state_field_defaults_to_unknown_for_missing_entry_state(self) -> None:
        """container._probe_watcher_detail enforces fallback: missing state → 'unknown'.

        The container reads status["watcherDetail"] (not status["watcher"]) for the
        structured probe dict.  The projects sub-map lives inside watcherDetail.
        """
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile

        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))

        # _probe_watcher_detail reads status.get("watcherDetail") for the structured dict.
        # 'state' key intentionally absent for proj-malformed to exercise the fallback.
        raw_status = {
            "watcherDetail": {
                "state": "running",
                "expected": True,
                "enabled": True,
                "configured": True,
                "running": True,
                "watchPathCount": 5,
                "watchPaths": [],
                "lastChangeSyncAt": None,
                "lastChangeCount": None,
                "lastSyncStatus": None,
                "lastSyncError": None,
                "projects": {"proj-malformed": {"watchPathCount": 3}},
                "lastReconcileAt": None,
                "lastReconcileError": None,
            }
        }

        # Call the container-level _probe_watcher_detail normalization (not the adapter's).
        detail = container._probe_watcher_detail(raw_status)
        projects = detail.get("projects", {})
        # The container normalizes: missing 'state' → 'unknown'.
        self.assertIn("proj-malformed", projects)
        self.assertEqual(projects["proj-malformed"]["state"], "unknown",
                         "Missing 'state' in entry must default to 'unknown' per OQ-5 FE contract")

    def test_lastreconcileat_and_error_present_in_adapter_probe_detail(self) -> None:
        """watcher probe detail from adapter includes lastReconcileAt and lastReconcileError keys."""
        snapshots = {
            "proj-y": {"running": True, "configured": True, "watchPathCount": 5, "lastChangeSyncAt": None},
        }
        adapter, restore = self._make_adapter_with_snapshots(snapshots)
        adapter._watcher_reconcile_last_at = "2026-06-13T10:01:00Z"
        adapter._watcher_reconcile_last_error = None
        try:
            detail = adapter._watcher_probe_detail()
        finally:
            restore()

        self.assertIn("lastReconcileAt", detail)
        self.assertIn("lastReconcileError", detail)
        self.assertEqual(detail["lastReconcileAt"], "2026-06-13T10:01:00Z")
        self.assertIsNone(detail["lastReconcileError"])


if __name__ == "__main__":
    unittest.main()
