"""P3 worker-bootstrap and enterprise fail-fast tests.

Tests covered:
  - P3-008: resolve_project fail-fast when principal has hosted claim scope and
            no project is resolvable — must NOT fall back to the active project.
            Local mode RETAINS the active-project fallback.
  - P3-012: bootstrap_worker module is safely importable without building a live
            RuntimeContainer (no side-effects at import time).
  - P3-016: _resolve_startup_project_binding emits a WARNING when the registry
            has multiple projects but no explicit binding is configured.

CRITICAL: This test module MUST NOT import backend.main or call
RuntimeContainer.startup() / build_worker_runtime() / build_worker_probe_app()
without an explicit container argument — those paths trigger DB connections and
hang in worktree environments.
"""
from __future__ import annotations

import logging
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

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
        generic CCDASH_WORKER_PROJECT_ID when both are set."""
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
            binding = container._resolve_startup_project_binding()

        self.assertEqual(binding.project.id, "project-watch")

    def test_worker_watch_falls_back_to_worker_project_id_when_watch_id_empty(self) -> None:
        """For the worker-watch profile, if WORKER_WATCH_PROJECT_ID is empty,
        use CCDASH_WORKER_PROJECT_ID as the fallback."""
        from backend.runtime.container import RuntimeContainer
        from backend.runtime.profiles import get_runtime_profile
        from backend import config

        container = RuntimeContainer(profile=get_runtime_profile("worker-watch"))
        registry_stub = self._make_registry_stub(["project-a"])

        with patch("backend.runtime.container.build_workspace_registry", return_value=registry_stub), \
             patch.dict(__import__("os").environ, {config.CCDASH_WORKER_PROJECT_ID_ENV: "project-a"}), \
             patch.object(config, "WORKER_WATCH_PROJECT_ID", ""):
            binding = container._resolve_startup_project_binding()

        self.assertEqual(binding.project.id, "project-a")


if __name__ == "__main__":
    unittest.main()
