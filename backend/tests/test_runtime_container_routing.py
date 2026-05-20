"""Tests for RuntimeContainer per-request multi-project binding (ADR-010).

Coverage:
- resolve_binding(project_id) returns a binding for a known project.
- Repeated calls hit the LRU cache (no re-construction from workspace registry).
- LRU eviction at maxsize removes the oldest entry.
- evict_binding removes a cached entry.
- api profile boots without an eager project binding (project_binding is None).
- worker profile retains eager binding at startup.
- Two projects served in one container instance (ADR-010 §Smoke gate).
"""
from __future__ import annotations

import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from backend.application.ports.core import ProjectBinding
from backend.runtime.container import RuntimeContainer
from backend.runtime.profiles import get_runtime_profile


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


def _make_project(project_id: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        id=project_id,
        name=f"Project {project_id}",
    )


def _make_binding(project_id: str) -> ProjectBinding:
    """Construct a minimal ProjectBinding for test use."""
    project = _make_project(project_id)
    paths = MagicMock()
    paths.root = types.SimpleNamespace(path=Path(f"/tmp/{project_id}"))
    return ProjectBinding(
        project=project,
        paths=paths,
        source="explicit",
        requested_project_id=project_id,
    )


def _make_container_with_mock_registry(
    profile_name: str = "api",
    projects: list[str] | None = None,
) -> tuple[RuntimeContainer, MagicMock]:
    """Return a container with a mock workspace registry that knows ``projects``."""
    profile = get_runtime_profile(profile_name)
    container = RuntimeContainer(profile=profile)

    projects = projects or ["proj-a", "proj-b"]
    mock_registry = MagicMock()

    def resolve_project_binding(project_id, *, allow_active_fallback=True, refresh=False):
        if project_id in projects:
            return _make_binding(project_id)
        return None

    mock_registry.resolve_project_binding.side_effect = resolve_project_binding

    mock_ports = MagicMock()
    mock_ports.workspace_registry = mock_registry
    container.ports = mock_ports

    return container, mock_registry


# --------------------------------------------------------------------------- #
# resolve_binding tests                                                         #
# --------------------------------------------------------------------------- #


class TestResolveBinding(unittest.TestCase):

    def test_returns_binding_for_known_project(self) -> None:
        container, _ = _make_container_with_mock_registry(projects=["proj-a"])
        binding = container.resolve_binding("proj-a")
        self.assertIsNotNone(binding)
        self.assertEqual(binding.project.id, "proj-a")

    def test_unknown_project_raises_404(self) -> None:
        from fastapi import HTTPException

        container, _ = _make_container_with_mock_registry(projects=["proj-a"])
        with self.assertRaises(HTTPException) as cm:
            container.resolve_binding("proj-unknown")
        self.assertEqual(cm.exception.status_code, 404)

    def test_repeated_calls_hit_cache_not_registry(self) -> None:
        """Second call for the same project_id should not call the registry again."""
        container, mock_registry = _make_container_with_mock_registry(projects=["proj-a"])

        binding1 = container.resolve_binding("proj-a")
        binding2 = container.resolve_binding("proj-a")

        self.assertEqual(binding1, binding2)
        # Registry should have been called exactly once (first call only).
        self.assertEqual(mock_registry.resolve_project_binding.call_count, 1)

    def test_two_projects_returned_independently(self) -> None:
        """Two different project_ids should each resolve to their own binding."""
        container, _ = _make_container_with_mock_registry(projects=["proj-a", "proj-b"])

        binding_a = container.resolve_binding("proj-a")
        binding_b = container.resolve_binding("proj-b")

        self.assertEqual(binding_a.project.id, "proj-a")
        self.assertEqual(binding_b.project.id, "proj-b")
        self.assertIsNot(binding_a, binding_b)

    def test_raises_if_ports_not_initialized(self) -> None:
        """resolve_binding should fail fast if called before startup."""
        container = RuntimeContainer(profile=get_runtime_profile("api"))
        # ports is None (pre-startup)
        with self.assertRaises(RuntimeError):
            container.resolve_binding("any-project")


# --------------------------------------------------------------------------- #
# LRU eviction tests                                                            #
# --------------------------------------------------------------------------- #


class TestBindingLRUEviction(unittest.TestCase):

    def test_lru_eviction_at_maxsize(self) -> None:
        """Adding more than maxsize entries should evict the oldest (LRU) entry."""
        container, mock_registry = _make_container_with_mock_registry(
            projects=[f"proj-{i}" for i in range(70)]
        )
        # Set a small LRU size for test speed.
        container._binding_lru_maxsize = 5

        for i in range(5):
            container.resolve_binding(f"proj-{i}")

        # LRU has 5 entries; proj-0 is the oldest.
        self.assertIn("proj-0", container._binding_lru)

        # Adding proj-5 should evict proj-0.
        container.resolve_binding("proj-5")
        self.assertNotIn("proj-0", container._binding_lru)
        self.assertIn("proj-5", container._binding_lru)

    def test_lru_most_recently_used_not_evicted(self) -> None:
        """Accessing a cached entry before overflow keeps it from being evicted."""
        container, _ = _make_container_with_mock_registry(
            projects=[f"proj-{i}" for i in range(10)]
        )
        container._binding_lru_maxsize = 3

        container.resolve_binding("proj-0")
        container.resolve_binding("proj-1")
        container.resolve_binding("proj-2")

        # Access proj-0 to make it MRU.
        container.resolve_binding("proj-0")

        # Add proj-3 — should evict proj-1 (the LRU), not proj-0.
        container.resolve_binding("proj-3")
        self.assertIn("proj-0", container._binding_lru)
        self.assertNotIn("proj-1", container._binding_lru)

    def test_default_maxsize_is_64(self) -> None:
        container = RuntimeContainer(profile=get_runtime_profile("api"))
        self.assertEqual(container._binding_lru_maxsize, 64)


# --------------------------------------------------------------------------- #
# evict_binding tests                                                            #
# --------------------------------------------------------------------------- #


class TestEvictBinding(unittest.TestCase):

    def test_evict_removes_cached_entry(self) -> None:
        container, mock_registry = _make_container_with_mock_registry(projects=["proj-a"])
        container.resolve_binding("proj-a")
        self.assertIn("proj-a", container._binding_lru)

        container.evict_binding("proj-a")
        self.assertNotIn("proj-a", container._binding_lru)

    def test_evict_noop_on_uncached_project(self) -> None:
        """evict_binding should not raise if the project_id is not cached."""
        container = RuntimeContainer(profile=get_runtime_profile("api"))
        # No error expected.
        container.evict_binding("not-in-cache")

    def test_after_eviction_next_call_re_resolves(self) -> None:
        """After eviction, the next resolve_binding call should hit the registry again."""
        container, mock_registry = _make_container_with_mock_registry(projects=["proj-a"])
        container.resolve_binding("proj-a")
        container.evict_binding("proj-a")

        container.resolve_binding("proj-a")
        # Registry should have been called twice (initial + post-eviction).
        self.assertEqual(mock_registry.resolve_project_binding.call_count, 2)


# --------------------------------------------------------------------------- #
# Profile-specific binding behavior                                             #
# --------------------------------------------------------------------------- #


class TestProfileBindingBehavior(unittest.TestCase):

    def test_api_profile_has_no_startup_binding(self) -> None:
        """api profile: project_binding is None at construction time (no eager bind)."""
        container = RuntimeContainer(profile=get_runtime_profile("api"))
        self.assertIsNone(container.project_binding)

    def test_api_profile_lru_is_empty_at_startup(self) -> None:
        """api profile: _binding_lru starts empty; no pre-population at construction."""
        container = RuntimeContainer(profile=get_runtime_profile("api"))
        self.assertEqual(len(container._binding_lru), 0)

    def test_local_profile_has_no_startup_binding(self) -> None:
        """local profile: project_binding is also None at construction (set during startup
        via _resolve_startup_project_binding which returns None for non-worker profiles)."""
        container = RuntimeContainer(profile=get_runtime_profile("local"))
        self.assertIsNone(container.project_binding)

    def test_worker_profile_resolve_startup_binding_requires_env_var(self) -> None:
        """worker profile: _resolve_startup_project_binding raises without env var."""
        container = RuntimeContainer(profile=get_runtime_profile("worker"))
        # Without CCDASH_WORKER_PROJECT_ID set, should raise RuntimeError.
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("CCDASH_WORKER_PROJECT_ID", None)
            with self.assertRaises(RuntimeError):
                container._resolve_startup_project_binding()


# --------------------------------------------------------------------------- #
# Two-project smoke test (ADR-010 §Smoke)                                       #
# --------------------------------------------------------------------------- #


class TestTwoProjectMultiProjectSmoke(unittest.TestCase):
    """Confirm a single RuntimeContainer instance can serve two projects."""

    def test_two_projects_in_one_process(self) -> None:
        """Resolve bindings for two distinct projects from one container.

        This is the ADR-010 §Smoke gate:  a single api process serves multiple
        projects, with each request routing to its own binding.
        """
        container, mock_registry = _make_container_with_mock_registry(
            projects=["alpha-project", "beta-project"]
        )

        binding_alpha = container.resolve_binding("alpha-project")
        binding_beta = container.resolve_binding("beta-project")

        # Each binding refers to its own project.
        self.assertEqual(binding_alpha.project.id, "alpha-project")
        self.assertEqual(binding_beta.project.id, "beta-project")

        # Both are cached.
        self.assertIn("alpha-project", container._binding_lru)
        self.assertIn("beta-project", container._binding_lru)

        # Cache hits — no additional registry calls.
        container.resolve_binding("alpha-project")
        container.resolve_binding("beta-project")
        self.assertEqual(mock_registry.resolve_project_binding.call_count, 2)
