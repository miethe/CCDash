"""automatic-session-naming (M3 / T3-005) — read-path model-client import audit.

Mirrors ``test_aar_review_no_llm_imports.py``'s static-import-graph-walk
method, INVERTED for this feature's shape: AAR review bans model-client
imports from its *entire* dependency graph (it never calls a model at all).
Derived session naming legitimately DOES call a model -- but only from the
worker-side sweep job (T3-001/T3-002/T3-003), never from a request-serving
read/render path. So this test walks the READ-PATH entry points (the routers
and MCP tools that serve session detail/list/search, plus the shared
application-layer services they call into) and asserts their transitive
``backend``-local import graph never reaches either naming-backend module
(``session_naming_local_backend`` / ``session_naming_hosted_backend`` -- the
modules that actually hold the ``httpx`` calls to Ollama/Gemini) or the sweep
job module itself (``session_naming_sweep_job``).

Why the walk stops at the DI-composition-root boundary
--------------------------------------------------------
Unlike ``aar_review.py`` (an isolated module with no legitimate reason to
import anything job-scheduling-related), this feature's naming-backend
modules live under ``backend/services/`` and its sweep job lives inside the
SAME shared ``backend.adapters.jobs`` package as every other worker job
(``AARReviewSweepJob``, ``TelemetryExporterJob``, etc.), all re-exported from
one ``__init__.py``. Virtually every request handler in this codebase
eventually imports *something* from that composition-root layer
(``backend.runtime.container`` / ``backend.runtime_ports`` /
``backend.adapters.jobs``) for unrelated reasons (e.g. type hints, a
DI helper, ``InProcessJobScheduler`` for a completely different job) --
Python then loads that package's *entire* ``__init__.py`` body, which
transitively "imports" every sibling job class as a side effect of package
mechanics, not because the read path calls any of them. A naive full-depth
BFS would therefore flag every read-path entry point as "reaching" the
sweep job purely from this fan-out, which is a false positive: importing a
module only loads its class/function *definitions* into memory, it does not
invoke ``derive_name`` or make a network call.

So the walk treats the recognized composition-root modules
(``_COMPOSITION_ROOT_BOUNDARIES``) as an OPAQUE BOUNDARY: it is visited (the
edge into it is real and recorded) but never expanded further -- which is
exactly the worker-only registration surface these same modules constitute
(see ``test_naming_job_is_worker_registered_only`` below, and
``test_session_naming_sweep_job.py``'s ``WorkerOnlyRegistrationTests`` /
``test_session_naming_sweep_guards.py``'s
``SessionNamingSweepTaskStarterTests`` for the profile-gate behaviour on the
other side of that boundary). This keeps the assertion meaningful: a DIRECT
import of a naming-backend module or the sweep job module -- ``from
backend.services.session_naming_local_backend import ...``, wherever it is
spelled inside the walked non-boundary graph -- by any router/service on the
actual request-handling path still fails this test.

Note this walk deliberately does NOT also raw-source-regex-scan every
visited module (unlike the AAR test's banned-symbol scan): these banned
names legitimately appear in comments/docstrings of ubiquitous
infrastructure modules every part of the app transitively imports (e.g.
``backend/config.py``'s own flag documentation), which would make a text
scan there a universal false positive, not a signal. The raw-source regex
scan is instead applied narrowly and directly, in
``test_naming_job_is_worker_registered_only`` below, against the small,
known worker-registration file set only -- as a POSITIVE control proving the
reference genuinely exists there by the expected name.

This is a STRUCTURAL assertion (parsed via ``ast``, nothing executed, no
network) so a future refactor that pulls a naming-backend import onto the
read path fails this test even if no test ever actually exercises the
resulting code path.

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_session_naming_read_path_no_model_client.py -v
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Every module a session-detail/list/search *request* can reach. Chosen to
# cover both the versioned client API surface and the MCP tool surface,
# mirroring the multi-entry-point shape of the AAR test's ``_P6_ENTRY_MODULES``.
_READ_PATH_ENTRY_MODULES = (
    "backend.routers._client_v1_sessions",
    "backend.routers.client_v1",
    "backend.routers.analytics",
    "backend.mcp.tools.sessions",
    "backend.application.services.agent_queries.session_detail",
    "backend.application.services.session_intelligence",
)

# The naming-job's own worker-only registration surface -- expected to
# directly reference the sweep job/naming-backend modules. NOT walked as a
# read-path entry point; instead used as a positive control by
# ``test_naming_job_is_worker_registered_only`` (proving the reference
# genuinely exists on the worker side, not merely absent from the read path
# because the check itself is broken).
_WORKER_REGISTRATION_MODULES = (
    "backend.runtime.container",
    "backend.adapters.jobs.runtime",
    "backend.adapters.jobs.__init__",
)

# DI-composition-root modules the read-path walk must not expand PAST -- see
# the module docstring's "Why the walk stops..." section. These modules are
# still visited (the edge into them is real) but their own import statements
# are never parsed/enqueued, so the shared-package re-export fan-out below
# this boundary never contaminates the read-path result.
_COMPOSITION_ROOT_BOUNDARIES = frozenset(
    {
        "backend.runtime.container",
        "backend.runtime.dependencies",
        "backend.runtime.bootstrap",
        "backend.runtime.bootstrap_worker",
        "backend.runtime_ports",
        "backend.adapters.jobs",
        "backend.mcp.bootstrap",
        "backend.cli.offline",
        "backend.cli.runtime",
        "backend.worker",
    }
)

# The modules a read-path request must never transitively reach (within the
# boundary-limited walk).
_BANNED_READ_PATH_MODULES = frozenset(
    {
        "backend.services.session_naming_local_backend",
        "backend.services.session_naming_hosted_backend",
        "backend.adapters.jobs.session_naming_sweep_job",
    }
)

# Symbol-name patterns that indicate a direct reference to the naming
# backends or the sweep job -- scanned against raw module source (not just
# statically-resolved imports), mirroring
# ``test_aar_review_no_llm_imports.py``'s ``_BANNED_SYMBOL_PATTERNS`` scan.
_BANNED_SYMBOL_PATTERNS = [
    re.compile(r"\bSessionNamingSweepJob\b"),
    re.compile(r"\bLocalOllamaNamingBackend\b"),
    re.compile(r"\bHostedGeminiNamingBackend\b"),
    re.compile(r"\bresolve_naming_backend\b"),
    re.compile(r"\bderive_name_fail_open\b"),
    re.compile(r"\bsession_naming_local_backend\b"),
    re.compile(r"\bsession_naming_hosted_backend\b"),
    re.compile(r"\bsession_naming_sweep_job\b"),
]

_MAX_VISITED_MODULES = 2000


def _module_name_to_path(module_name: str) -> Path | None:
    """Resolve a dotted ``backend.*`` module name to its source file, if any."""
    if not module_name.startswith("backend"):
        return None
    rel = module_name.replace(".", "/")
    module_file = _REPO_ROOT / f"{rel}.py"
    if module_file.is_file():
        return module_file
    package_init = _REPO_ROOT / rel / "__init__.py"
    if package_init.is_file():
        return package_init
    return None


def _iter_import_candidates(tree: ast.Module, current_module: str) -> list[str]:
    """Return every dotted-name candidate a statement in *tree* could refer to."""
    candidates: list[str] = []
    current_parts = current_module.split(".")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                candidates.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                trim = node.level
                base_parts = current_parts[:-trim] if trim <= len(current_parts) else []
                base = ".".join(base_parts)
                if node.module:
                    base = f"{base}.{node.module}" if base else node.module
            else:
                base = node.module or ""
            if base:
                candidates.append(base)
            for alias in node.names:
                candidates.append(f"{base}.{alias.name}" if base else alias.name)
    return candidates


def _walk_read_path_graph(entry_module: str) -> tuple[set[str], list[str]]:
    """Boundary-limited BFS of the backend-local import graph from *entry_module*.

    Returns ``(visited_modules, offending_findings)``. A module in
    ``_COMPOSITION_ROOT_BOUNDARIES`` is visited (recorded) but never
    expanded -- see the module docstring. Never raises -- unparseable source
    is skipped (recorded as a visited-but-unwalked leaf, not a finding).
    """
    visited: set[str] = set()
    offending: list[str] = []
    queue: list[str] = [entry_module]

    while queue:
        if len(visited) > _MAX_VISITED_MODULES:
            raise AssertionError(
                f"session-naming read-path walk exceeded {_MAX_VISITED_MODULES} "
                "visited modules -- likely a cycle-detection regression; investigate "
                "before trusting this test's coverage."
            )
        module_name = queue.pop()
        if module_name in visited:
            continue
        visited.add(module_name)

        if module_name in _BANNED_READ_PATH_MODULES:
            offending.append(f"read-path walk reached banned module {module_name!r}")

        if module_name in _COMPOSITION_ROOT_BOUNDARIES:
            # Opaque boundary: the edge INTO it is real (already recorded
            # above via `visited`), but its own re-export fan-out is not
            # part of the read path -- do not parse/enqueue its imports.
            continue

        path = _module_name_to_path(module_name)
        if path is None:
            continue

        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue

        # Deliberately NOT a raw-source regex scan here (unlike the AAR
        # test's banned-symbol scan): these banned names legitimately appear
        # in comments/docstrings of ubiquitous infrastructure modules (e.g.
        # ``backend/config.py``'s own flag documentation), which every
        # module in the app transitively imports -- a text scan there would
        # be a universal false positive, not a signal. The AST-based import
        # check below is precise (it only fires on an actual import
        # statement naming the banned module), which is what this walk
        # relies on; the raw-source regex scan is instead applied narrowly
        # and directly in ``test_naming_job_is_worker_registered_only``
        # against the small, known worker-registration file set only.
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        for candidate in _iter_import_candidates(tree, module_name):
            if candidate in _BANNED_READ_PATH_MODULES:
                offending.append(f"{module_name} imports banned module {candidate!r}")
            if candidate.startswith("backend") and candidate not in visited:
                queue.append(candidate)

    return visited, offending


class ReadPathNeverImportsANamingBackendOrTheSweepJobTests(unittest.TestCase):
    """T3-005 -- the positive, inverted structural assertion."""

    def test_read_path_entry_modules_never_reach_a_naming_backend_or_the_sweep_job(
        self,
    ) -> None:
        for entry_module in _READ_PATH_ENTRY_MODULES:
            with self.subTest(entry_module=entry_module):
                visited, offending = _walk_read_path_graph(entry_module)

                # Sanity: the walk must actually traverse a real graph, not
                # just the entry module itself -- otherwise this test would
                # trivially "pass" while covering nothing.
                self.assertIn(entry_module, visited)
                self.assertGreater(
                    len(visited),
                    1,
                    f"{entry_module}: walk visited only the entry module -- covers nothing",
                )

                self.assertEqual(
                    offending,
                    [],
                    "Found a banned naming-backend/sweep-job import or symbol reference in "
                    f"the {entry_module} read-path dependency graph: {offending}",
                )

    def test_session_detail_module_is_part_of_every_relevant_walk(self) -> None:
        """Sanity check that the walk actually reaches the shared redaction
        door (``session_detail.get_session_detail``) from the client-facing
        entry points -- otherwise a walk that silently short-circuited
        before reaching it would still "pass" the module-absence assertion
        above for the wrong reason.
        """
        for entry_module in (
            "backend.routers._client_v1_sessions",
            "backend.routers.client_v1",
            "backend.mcp.tools.sessions",
        ):
            with self.subTest(entry_module=entry_module):
                visited, _ = _walk_read_path_graph(entry_module)
                self.assertIn(
                    "backend.application.services.agent_queries.session_detail",
                    visited,
                )

    def test_naming_job_is_worker_registered_only(self) -> None:
        """The counterpart half of this task's AC: the sweep job/naming
        backends are referenced ONLY from the worker-side composition-root
        modules, never from the read path.

        Two-sided proof:

          1. POSITIVE control -- the sweep job / naming-backend resolver are
             genuinely referenced (by name, in raw source) from the known
             worker-registration modules. This guards against the whole
             check above being vacuously true because nothing anywhere
             references these symbols by the expected names any more (a
             silent rename would otherwise make every other assertion in
             this file pass for the wrong reason).
          2. The boundary-limited read-path walk (proven above) never
             reaches these same modules/symbols -- i.e. the only path to
             them runs through the composition-root boundary, which this
             test's docstring establishes as the worker-only registration
             surface (profile-gated to ``worker``/``worker-watch``, see
             ``test_session_naming_sweep_guards.py``).
        """
        expected_sources = {
            "backend.runtime.container": _REPO_ROOT / "backend/runtime/container.py",
            "backend.adapters.jobs.runtime": _REPO_ROOT / "backend/adapters/jobs/runtime.py",
            "backend.adapters.jobs.__init__": _REPO_ROOT / "backend/adapters/jobs/__init__.py",
        }
        for module_name, source_path in expected_sources.items():
            self.assertTrue(source_path.is_file(), f"{module_name}: expected file missing")
            source = source_path.read_text(encoding="utf-8")
            matched = any(pattern.search(source) for pattern in _BANNED_SYMBOL_PATTERNS)
            self.assertTrue(
                matched,
                f"{module_name}: expected a direct reference to the sweep job / naming "
                "backend resolver on the worker-registration surface, found none -- either "
                "the registration wiring moved (update this test) or a rename broke this "
                "positive control silently.",
            )

        for read_entry_module in _READ_PATH_ENTRY_MODULES:
            visited, offending = _walk_read_path_graph(read_entry_module)
            self.assertEqual(offending, [])
            self.assertFalse(
                _BANNED_READ_PATH_MODULES & visited,
                f"{read_entry_module}: read path must never reach a naming-backend or "
                "sweep-job module",
            )


if __name__ == "__main__":
    unittest.main()
