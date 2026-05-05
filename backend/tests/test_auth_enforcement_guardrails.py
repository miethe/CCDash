from __future__ import annotations

import ast
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROUTER_DIR = BACKEND_DIR / "routers"

SINGLETON_MIGRATED_ROUTERS = (
    "codebase.py",
    "session_mappings.py",
    "cache.py",
    "pricing.py",
)

PROTECTED_AUTH_ROUTERS = (
    *SINGLETON_MIGRATED_ROUTERS,
    "execution.py",
    "integrations.py",
    "live.py",
    "analytics.py",
    "api.py",
    "test_visualizer.py",
)

EXPECTED_PERMISSION_ACTIONS_BY_ROUTER: dict[str, set[str]] = {
    "codebase.py": {
        "codebase:activity_read",
        "codebase:file_read",
        "codebase:read_tree",
    },
    "session_mappings.py": {
        "session_mapping:diagnose",
        "session_mapping:read",
        "session_mapping:update",
    },
    "cache.py": {
        "cache.links:rebuild",
        "cache.operation:read",
        "cache.paths:sync",
        "cache.sync:trigger",
        "cache:read_status",
        "link_audit:run",
    },
    "pricing.py": {
        "admin.pricing:delete",
        "admin.pricing:read",
        "admin.pricing:reset",
        "admin.pricing:sync",
        "admin.pricing:update",
    },
    "execution.py": {
        "execution.launch:prepare",
        "execution.launch:start",
        "execution.run:approve",
        "execution.run:cancel",
        "execution.run:create",
        "execution.run:retry",
        "execution:read",
        "worktree_context:create",
        "worktree_context:update",
    },
    "integrations.py": {
        "integration.github.workspace:refresh",
        "integration.github:read_settings",
        "integration.github:update_settings",
        "integration.github:validate",
        "integration.github:write_probe",
        "integration.skillmeat.memory:generate",
        "integration.skillmeat.memory:publish",
        "integration.skillmeat.memory:review",
        "integration.skillmeat:backfill",
        "integration.skillmeat:sync",
        "integration:read",
    },
    "live.py": {
        "execution:read",
        "live.execution:subscribe",
        "live.feature:subscribe",
        "live.project:subscribe",
        "live.session:subscribe",
        "live:subscribe",
    },
    "analytics.py": {
        "analytics.alert:create",
        "analytics.alert:delete",
        "analytics.alert:update",
        "analytics.export:prometheus",
        "analytics.notification:read",
        "analytics:read",
    },
    "api.py": {
        "entity_link:create",
        "planning.writeback:sync",
    },
    "test_visualizer.py": {
        "test.mapping:backfill",
        "test.mapping:import",
        "test.metrics:read",
        "test.run:ingest",
        "test.sync:trigger",
        "test:read",
    },
}


def _router_source(filename: str) -> str:
    return (ROUTER_DIR / filename).read_text(encoding="utf-8")


def _router_tree(filename: str) -> ast.Module:
    return ast.parse(_router_source(filename), filename=str(ROUTER_DIR / filename))


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _call_sites_named(tree: ast.AST, name: str) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == name:
            lines.append(node.lineno)
        elif isinstance(node.func, ast.Attribute) and node.func.attr == name:
            lines.append(node.lineno)
    return lines


def _string_literals(tree: ast.AST) -> set[str]:
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _project_manager_import_violations(tree: ast.AST) -> list[int]:
    violations: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "backend.project_manager" or alias.name.startswith("backend.project_manager."):
                    violations.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "backend.project_manager":
                violations.append(node.lineno)
            elif node.module == "backend":
                if any(alias.name == "project_manager" for alias in node.names):
                    violations.append(node.lineno)
    return violations


def _direct_active_project_call_violations(tree: ast.AST) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get_active_project"
    ]


def _direct_authorization_policy_call_violations(tree: ast.AST) -> list[int]:
    violations: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "authorize":
            continue
        receiver = _dotted_name(node.func.value)
        if receiver == "authorization_policy" or receiver.endswith(".authorization_policy"):
            violations.append(node.lineno)
    return violations


class AuthEnforcementGuardrailTests(unittest.TestCase):
    def test_singleton_migrated_routers_do_not_use_project_manager_or_active_project(self) -> None:
        failures: list[str] = []
        for filename in SINGLETON_MIGRATED_ROUTERS:
            tree = _router_tree(filename)
            import_lines = _project_manager_import_violations(tree)
            active_project_lines = _direct_active_project_call_violations(tree)
            if import_lines:
                failures.append(f"{filename} imports backend.project_manager on lines {import_lines}")
            if active_project_lines:
                failures.append(f"{filename} calls get_active_project() on lines {active_project_lines}")

        self.assertEqual(
            failures,
            [],
            "Covered singleton-migrated routers must stay on request context/workspace registry seams.",
        )

    def test_protected_routers_use_http_authorization_helper_not_policy_directly(self) -> None:
        failures: list[str] = []
        for filename in PROTECTED_AUTH_ROUTERS:
            tree = _router_tree(filename)
            direct_policy_lines = _direct_authorization_policy_call_violations(tree)
            helper_lines = _call_sites_named(tree, "require_http_authorization")
            if direct_policy_lines:
                failures.append(f"{filename} calls authorization_policy.authorize() on lines {direct_policy_lines}")
            if not helper_lines:
                failures.append(f"{filename} does not call require_http_authorization()")

        self.assertEqual(
            failures,
            [],
            "Protected HTTP routers should go through request_scope.require_http_authorization().",
        )

    def test_protected_route_permission_vocabulary_remains_named_and_explicit(self) -> None:
        failures: list[str] = []
        for filename, expected_actions in EXPECTED_PERMISSION_ACTIONS_BY_ROUTER.items():
            tree = _router_tree(filename)
            present_actions = _string_literals(tree)
            missing = sorted(expected_actions - present_actions)
            if missing:
                failures.append(f"{filename} is missing permission action literals: {missing}")

        self.assertEqual(
            failures,
            [],
            "Covered protected route families must retain their curated named permission checks.",
        )


if __name__ == "__main__":
    unittest.main()
