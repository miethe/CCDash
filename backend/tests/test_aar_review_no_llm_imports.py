"""Static import-graph audit for the AAR review module (T2-008 / AC-P2.1).

Automates the "Hard Invariant #1" this PRD relies on: ``aar_review.py`` and
every module it (transitively, statically) imports under the ``backend``
package must never import a model/LLM client library, and must never
reference a Task/Agent-dispatch helper symbol.  This was previously verified
by manual reviewer grep only (see the docstrings of ``aar_review.py`` and
``test_agent_queries_aar_review.py``); this test makes that check
reproducible and CI-enforceable.

Method: parse (via ``ast``, no execution) the source of
``aar_review.py``, follow every statically-declared ``import`` /
``from ... import`` statement whose resolved module lives under
``backend/`` on disk, and repeat over the whole transitive closure (cycle-
safe via a visited set).  For each visited module's raw source we:

  1. Check every statically-resolved import name against a banned-import
     name list (``anthropic``, ``openai``, ``litellm``, ``langchain``,
     ``google.generativeai`` / ``genai``).
  2. Regex-scan the raw source for banned Task/Agent-dispatch helper symbol
     names.

Non-``backend`` (third-party/stdlib) imports are checked by name only --
this test deliberately does not walk into installed package source (that is
a different, much larger, and non-deterministic-across-environments
surface); a third-party import matching the banned-name list still fails
the test even though its source is never opened.
"""
import ast
import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENTRY_MODULE = "backend.application.services.agent_queries.aar_review"

# Phase 6 (ccdash-automated-aar-review-v1, karen P6 milestone review):
# the autonomous sweep worker and the gated writeback seam are ALSO entry
# points into this dependency graph -- until now they were only verified by
# inspection, not by this automated walk. Each is walked independently (its
# own BFS from its own entry point) so a banned import/symbol anywhere in
# EITHER module's own transitive closure is caught, even if that closure
# does not happen to overlap with aar_review.py's.
_P6_ENTRY_MODULES = (
    "backend.adapters.jobs.aar_review_sweep_job",
    "backend.application.services.agent_queries.aar_review_writeback",
)

# Module-name prefixes that indicate a model/LLM client dependency. Matched
# against the fully-qualified import name (e.g. "openai.types" matches the
# "openai" pattern below).
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
# helper is caught too, not only an imported one.
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
    actual file (e.g. ``backend.application.ports.CorePorts`` where
    ``CorePorts`` is a symbol, not a submodule) -- callers must not treat
    ``None`` as an error.
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
                f"aar_review dependency-graph walk exceeded {_MAX_VISITED_MODULES} "
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
    """T2-008 / AC-P2.1 -- Hard Invariant #1, automated."""

    def test_no_llm_client_import_or_agent_dispatch_symbol_in_dependency_graph(self) -> None:
        visited, offending = _walk_dependency_graph(_ENTRY_MODULE)

        # Sanity: the walk must actually traverse a real graph, not just the
        # entry module -- otherwise this test would trivially "pass" while
        # covering nothing.
        self.assertIn(_ENTRY_MODULE, visited)
        self.assertIn(
            "backend.application.services.agent_queries.aar_review_enrichment",
            visited,
            "the Phase 2 enrichment module must be part of the walked graph",
        )
        self.assertIn(
            "backend.application.services.agent_queries.session_detail",
            visited,
            "session_detail.py must be part of the walked graph (enrichment reuses it exclusively)",
        )
        self.assertGreater(len(visited), 5)

        self.assertEqual(
            offending,
            [],
            "Found a banned LLM-client import or agent-dispatch symbol in the "
            f"aar_review dependency graph: {offending}",
        )

    def test_p6_entry_modules_have_no_llm_client_import_or_agent_dispatch_symbol(self) -> None:
        """Karen P6 milestone review: expand the automated walk to the Phase 6
        autonomous sweep worker and the gated writeback seam -- previously
        only verified by manual inspection, not by this CI-enforceable check.
        """
        for entry_module in _P6_ENTRY_MODULES:
            with self.subTest(entry_module=entry_module):
                visited, offending = _walk_dependency_graph(entry_module)

                # Sanity: the walk must actually traverse a real graph, not
                # just the entry module itself.
                self.assertIn(entry_module, visited)
                self.assertGreater(
                    len(visited), 1,
                    f"{entry_module}: walk visited only the entry module -- covers nothing",
                )

                self.assertEqual(
                    offending,
                    [],
                    f"Found a banned LLM-client import or agent-dispatch symbol in the "
                    f"{entry_module} dependency graph: {offending}",
                )


if __name__ == "__main__":
    unittest.main()
