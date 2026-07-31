"""Static import-graph audit for the routing-rollup module (T3-005 / AOS
Constraint 4).

Clones ``backend/tests/test_aar_review_no_llm_imports.py``'s AST-walk BFS
pattern verbatim (same ``_BANNED_IMPORT_PATTERNS`` / ``_BANNED_SYMBOL_PATTERNS``
lists, same ``_module_name_to_path`` / ``_iter_import_candidates`` /
``_walk_dependency_graph`` structure) -- deliberately NOT re-derived or
tightened here; divergence between the two guard files is itself a
maintenance risk (phase-3 risk-mitigation table).

Automates this feature's own Hard Invariant (AOS Constraint 4):
``routing_rollup.py`` and every module it (transitively, statically) imports
under ``backend/`` must never import a model/LLM client library
(``anthropic``, ``openai``, ``litellm``, ``langchain``,
``google.generativeai`` / ``genai``), and must never reference a Task/Agent-
dispatch helper symbol. Every computation in ``routing_rollup.py`` is pure
SQL aggregation plus threshold/arithmetic -- this test makes that invariant
CI-enforceable rather than relying on manual reviewer grep.

Method: parse (via ``ast``, no execution) the source of
``routing_rollup.py``, follow every statically-declared ``import`` /
``from ... import`` statement whose resolved module lives under
``backend/`` on disk, and repeat over the whole transitive closure (cycle-
safe via a visited set). For each visited module's raw source we:

  1. Check every statically-resolved import name against a banned-import
     name list.
  2. Regex-scan the raw source for banned Task/Agent-dispatch helper symbol
     names.

Non-``backend`` (third-party/stdlib) imports are checked by name only --
this test deliberately does not walk into installed package source; a
third-party import matching the banned-name list still fails the test even
though its source is never opened.

Phase 6 (T6-001) EXTENDS this file with a second, independent BFS entry
point covering Phase 4's ``backend/adapters/jobs/routing_rollup_sweep_job.py``
sweep-job module (``_P6_ENTRY_MODULES`` below) -- mirroring the AAR
precedent's own ``_P6_ENTRY_MODULES`` extension pattern (a second
entry-point tuple + ``subTest`` loop, added to the same
``NoLLMOrAgentDispatchImportGraphTests`` class below -- additive, never a
rewrite of the walk machinery). ``routing_rollup_sweep_job.py``'s own
"zero re-derivation" invariant (see that module's docstring) is what this
second entry point makes CI-enforceable: it never computes a task_class,
provider, or D5 metric value itself, and (per this test) never imports an
LLM client or references an agent-dispatch symbol anywhere in its own
transitive closure -- including its several call-time-deferred imports
inside ``_execute_inner`` (import-cycle avoidance, per that module's own
docstring), which ``ast.walk`` still visits because it traverses the whole
module tree, not just top-level statements.

Run as a named module (full collection can hang -- see
``docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md`` and
the repo-wide pytest-collection caveat):
    backend/.venv/bin/python -m pytest backend/tests/test_routing_rollup_no_llm_imports.py -v
"""
import ast
import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENTRY_MODULE = "backend.application.services.agent_queries.routing_rollup"

# Phase 6 (T6-001): the background-worker sweep job is ALSO an entry point
# into this dependency graph -- until now it was only verified by inspection
# (the module's own extensive docstring), not by this automated walk. Walked
# independently (its own BFS from its own entry point) so a banned
# import/symbol anywhere in its transitive closure is caught, even where
# that closure does not overlap with routing_rollup.py's own. Kept as a
# tuple (rather than a bare string) to mirror
# ``test_aar_review_no_llm_imports.py``'s own ``_P6_ENTRY_MODULES`` shape
# byte-for-byte, even though this feature has only one Phase-6 entry point
# today (vs. AAR review's two) -- a future second worker/writeback module
# extends this tuple, not the walk machinery.
_P6_ENTRY_MODULES = (
    "backend.adapters.jobs.routing_rollup_sweep_job",
)

# Module-name prefixes that indicate a model/LLM client dependency. Matched
# against the fully-qualified import name (e.g. "openai.types" matches the
# "openai" pattern below). Byte-identical to the AAR precedent's list --
# keep in sync unless a new banned SDK is discovered.
_BANNED_IMPORT_PATTERNS = [
    re.compile(r"^anthropic(\.|$)"),
    re.compile(r"^openai(\.|$)"),
    re.compile(r"^litellm(\.|$)"),
    re.compile(r"^langchain(\.|$)"),
    re.compile(r"^google\.generativeai(\.|$)"),
    re.compile(r"^genai(\.|$)"),
]

# Symbol-name patterns that indicate a Task/Agent-dispatch helper. Scanned
# against raw module source (not just imports) so a locally-defined dispatch
# helper is caught too, not only an imported one. Byte-identical to the AAR
# precedent's list.
_BANNED_SYMBOL_PATTERNS = [
    re.compile(r"\bspawn_agent\b"),
    re.compile(r"\bdispatch_agent\b"),
    re.compile(r"\binvoke_agent\b"),
    re.compile(r"\brun_subagent\b"),
    re.compile(r"\bTaskDispatch\b"),
    re.compile(r"\bAgentDispatch\b"),
    re.compile(r"\bsubagent_task_tool\b"),
]

# Hard cap on the number of modules the BFS will visit -- a generous bound
# for this dependency graph (a few hundred backend modules at most); if this
# is ever hit it indicates the walk escaped its intended scope (e.g. cycle
# detection regressed), not that the codebase legitimately needs more.
_MAX_VISITED_MODULES = 2000


def _module_name_to_path(module_name: str) -> Path | None:
    """Resolve a dotted ``backend.*`` module name to its source file, if any.

    Returns ``None`` for anything outside the ``backend`` package (external
    library or stdlib) or for a dotted name that does not resolve to an
    actual file (e.g. a dotted name where the final component is a symbol,
    not a submodule) -- callers must not treat ``None`` as an error.
    """
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
    """Return every dotted-name candidate a statement in *tree* could refer to.

    For ``from X import Y`` this yields both ``X`` (the common case -- ``Y``
    is a symbol defined in module ``X``) and ``X.Y`` (the case where ``Y`` is
    itself a submodule, e.g. ``from backend import config``). Unresolvable
    candidates are filtered out later by ``_module_name_to_path`` returning
    ``None`` for them -- harmless, since a symbol name will never coincide
    with a real ``backend`` module path in practice.
    """
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


def _walk_dependency_graph(entry_module: str) -> tuple[set[str], list[str]]:
    """BFS the backend-local import graph from *entry_module*.

    Returns ``(visited_modules, offending_findings)``. Never raises --
    unparseable source is skipped (recorded as a visited-but-unwalked leaf,
    not a finding).
    """
    visited: set[str] = set()
    offending: list[str] = []
    queue: list[str] = [entry_module]

    while queue:
        if len(visited) > _MAX_VISITED_MODULES:
            raise AssertionError(
                f"routing_rollup dependency-graph walk exceeded {_MAX_VISITED_MODULES} "
                "visited modules -- likely a cycle-detection regression; investigate "
                "before trusting this test's coverage."
            )
        module_name = queue.pop()
        if module_name in visited:
            continue
        visited.add(module_name)

        for pattern in _BANNED_IMPORT_PATTERNS:
            if pattern.match(module_name):
                offending.append(f"banned import resolved while walking to {module_name!r}")

        path = _module_name_to_path(module_name)
        if path is None:
            # External/unresolved -- nothing further to walk into.
            continue

        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue

        for pattern in _BANNED_SYMBOL_PATTERNS:
            if pattern.search(source):
                offending.append(f"{module_name}: source matches banned symbol pattern {pattern.pattern!r}")

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        for candidate in _iter_import_candidates(tree, module_name):
            for pattern in _BANNED_IMPORT_PATTERNS:
                if pattern.match(candidate):
                    offending.append(f"{module_name} imports {candidate!r}")
            if candidate.startswith("backend") and candidate not in visited:
                queue.append(candidate)

    return visited, offending


class NoLLMOrAgentDispatchImportGraphTests(unittest.TestCase):
    """T3-005 / AOS Constraint 4 -- automated, CI-enforceable no-LLM guard
    for the routing-rollup compute module, extended by T6-001 to also cover
    the Phase 4 worker sweep job -- mirroring
    ``test_aar_review_no_llm_imports.py``'s own two-test-method shape.
    """

    def test_no_llm_client_import_or_agent_dispatch_symbol_in_dependency_graph(self) -> None:
        visited, offending = _walk_dependency_graph(_ENTRY_MODULE)

        # Sanity: the walk must actually traverse a real graph, not just the
        # entry module -- otherwise this test would trivially "pass" while
        # covering nothing (phase-3 AC: "the walk visiting more than 5
        # modules").
        self.assertIn(_ENTRY_MODULE, visited)
        self.assertIn(
            "backend.application.services.agent_queries.routing_feedback_contract",
            visited,
            "the Phase 1 pinned-contract module must be part of the walked graph",
        )
        self.assertIn(
            "backend.model_identity",
            visited,
            "model_identity.py must be part of the walked graph (T3-003's sole provider source)",
        )
        self.assertIn(
            "backend.application.services.agent_queries._filters",
            visited,
            "_filters.py must be part of the walked graph (T3-001's window-resolution helper)",
        )
        self.assertGreater(len(visited), 5)

        self.assertEqual(
            offending,
            [],
            "Found a banned LLM-client import or agent-dispatch symbol in the "
            f"routing_rollup dependency graph: {offending}",
        )

    def test_p6_entry_modules_have_no_llm_client_import_or_agent_dispatch_symbol(self) -> None:
        """T6-001: extend the automated walk to the Phase 4 background-worker
        sweep job (``RoutingRollupSweepJob``) -- previously only verified by
        manual inspection (that module's own extensive docstring), not by
        this CI-enforceable check. Mirrors
        ``test_aar_review_no_llm_imports.py``'s own P6 subTest method
        byte-for-byte.
        """
        for entry_module in _P6_ENTRY_MODULES:
            with self.subTest(entry_module=entry_module):
                visited, offending = _walk_dependency_graph(entry_module)

                # Sanity: the walk must actually traverse a real graph, not
                # just the entry module itself -- otherwise this test would
                # trivially "pass" while covering nothing.
                self.assertIn(entry_module, visited)
                self.assertGreater(
                    len(visited), 1,
                    f"{entry_module}: walk visited only the entry module -- covers nothing",
                )
                self.assertIn(
                    "backend.db.repositories.routing_rollup",
                    visited,
                    f"{entry_module}: the routing_rollup repository module "
                    "(this job's persistence dependency) must be part of the "
                    "walked graph",
                )

                self.assertEqual(
                    offending,
                    [],
                    f"Found a banned LLM-client import or agent-dispatch symbol in the "
                    f"{entry_module} dependency graph: {offending}",
                )


if __name__ == "__main__":
    unittest.main()
