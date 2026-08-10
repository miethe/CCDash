"""hosted-llm-anthropic-ica-lane-v1 -- ADR-018's structural import-graph guardrail.

ADR-018 (``docs/project_plans/adrs/adr-018-redaction-provenance-carried-by-type.md``,
"Architecture guardrail" section) requires an architecture-level test forbidding
``backend/adapters/llm/*`` provider modules from importing a raw transcript/session
reader directly. The ADR is explicit about *why* this cannot be left to
``enforce_egress_provenance`` (``backend/application/ports/llm.py``) alone: that
function polices the ``PromptProvenance`` carried by a :class:`PromptEnvelope` --
but it only ever runs once an envelope has actually been constructed and handed to
an adapter's ``complete()``. A provider module that imported a raw reader directly
(``SessionTranscriptService.list_session_logs``, ``parse_session_file``/
``scan_sessions``, or ``get_session_detail`` itself) and used its output without
ever building a ``PromptEnvelope`` would never touch ``enforce_egress_provenance``
at all -- there would be nothing to reject, because the sanctioned seam was never
called. The type-level provenance guarantee this feature is built on therefore
holds only by convention at exactly the boundary (adapter module import surface)
it is supposed to make structural. This test closes that hole.

Mirrors the AST-import-walk method already used in this codebase for structurally
identical concerns -- ``test_aar_review_no_llm_imports.py``,
``test_routing_rollup_no_llm_imports.py``, and (closest in shape: a boundary-limited
BFS proving a *forward* import walk from a small set of entry modules never reaches
a named set of banned targets) ``test_session_naming_read_path_no_model_client.py``.
This test is the mirror image of that last one: where the naming test walks
*read-path* entry points and bans them from reaching the *egress* backends/sweep
job, this test walks the *egress adapter* entry points and bans them from reaching
the *raw transcript readers* upstream of the envelope/factory boundary.

Forbidden targets (verified by reading the code, not guessed) -- the raw
transcript/session readers ADR-018's guardrail section names, plus the read-path
entry point the SPIKE and this task explicitly call out:

  * ``backend.parsers.sessions`` -- ``parse_session_file`` / ``scan_sessions``,
    the filesystem JSONL parser (ADR-018 names these two functions explicitly).
  * ``backend.application.services.sessions`` -- holds
    ``SessionTranscriptService.list_session_logs``, the DB-backed transcript
    reader (ADR-018 names this explicitly too).
  * ``backend.application.services.agent_queries.session_detail`` -- holds
    ``get_session_detail``, the transport-neutral full-session-detail read path
    that both derived-naming backends call *before* building a
    ``PromptEnvelope`` (see ``backend/services/session_naming_hosted_backend.py``
    and ``backend/services/session_naming_local_backend.py``, both of which
    import it directly -- correctly, since they are upstream of the envelope
    boundary, not inside ``backend/adapters/llm/``).

``backend.application.ports.llm`` -- the sanctioned seam (``PromptEnvelope``,
``envelope_from_redacted_transcript``, ``enforce_egress_provenance``) -- is
explicitly ALLOWED; every current adapter imports it and must keep doing so. It
is also this test's POSITIVE CONTROL target (see below).

Two-sided by construction, per this task's requirement and this repo's own
memory of exactly this failure class (a walk that silently visits nothing still
"passes" the negative assertion):

  1. Negative: no adapter module's boundary-limited forward walk reaches a
     banned raw-reader module.
  2. Positive control: the SAME walk, run from each adapter entry module, DOES
     reach ``backend.application.ports.llm`` -- proving the walk traverses real
     edges rather than short-circuiting into an empty/near-empty visited set
     (which would make finding #1 vacuous). Modeled directly on
     ``test_session_naming_read_path_no_model_client.py``'s
     ``test_session_detail_module_is_part_of_every_relevant_walk``.
  3. Reachability sanity: the union of every walk's visited set is non-empty
     and contains all three adapter entry modules themselves.

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_llm_adapters_no_raw_transcript_imports.py -v
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Every provider-adapter module under backend/adapters/llm/ -- the entire
# surface ADR-018's guardrail is scoped to. (backend/adapters/llm/__init__.py
# is intentionally NOT an entry here: it only re-exports gemini/ollama today
# and is not itself an egress adapter; walking each concrete adapter module
# directly is both necessary and sufficient to cover "no module under
# backend/adapters/llm/ ... reaches a raw transcript reader".)
_ADAPTER_ENTRY_MODULES = (
    "backend.adapters.llm.gemini",
    "backend.adapters.llm.ollama",
    "backend.adapters.llm.anthropic",
)

# The sanctioned seam -- every EGRESS adapter imports this, and it is the ONLY
# legitimate way transcript-derived content may reach an adapter (via a
# PromptEnvelope built by envelope_from_redacted_transcript upstream, in a
# caller OUTSIDE backend/adapters/llm/). Used below as the positive control.
_SANCTIONED_SEAM_MODULE = "backend.application.ports.llm"

# The raw transcript/session readers an adapter must never transitively
# reach. See the module docstring for why each one is here.
_BANNED_RAW_READER_MODULES = frozenset(
    {
        "backend.parsers.sessions",
        "backend.application.services.sessions",
        "backend.application.services.agent_queries.session_detail",
    }
)

# DI-composition-root modules the walk must not expand past, mirroring
# ``test_session_naming_read_path_no_model_client.py``'s
# ``_COMPOSITION_ROOT_BOUNDARIES``. Today's adapter modules do not reach any
# of these (their entire graph is adapter -> ports.llm -> redaction), but the
# boundary is kept here so a future adapter change that legitimately needs
# something from the composition root (e.g. a config helper) does not turn
# this test into a false positive via that module's own unrelated re-export
# fan-out -- the same reasoning the naming test documents at length.
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


def _walk_adapter_graph(entry_module: str) -> tuple[set[str], list[str]]:
    """Boundary-limited BFS of the backend-local import graph from *entry_module*.

    Returns ``(visited_modules, offending_findings)``. A module in
    ``_COMPOSITION_ROOT_BOUNDARIES`` is visited (recorded) but never expanded
    -- see the module docstring. Never raises -- unparseable source is
    skipped (recorded as a visited-but-unwalked leaf, not a finding).
    """
    visited: set[str] = set()
    offending: list[str] = []
    queue: list[str] = [entry_module]

    while queue:
        if len(visited) > _MAX_VISITED_MODULES:
            raise AssertionError(
                f"llm-adapter import walk exceeded {_MAX_VISITED_MODULES} visited "
                "modules -- likely a cycle-detection regression; investigate before "
                "trusting this test's coverage."
            )
        module_name = queue.pop()
        if module_name in visited:
            continue
        visited.add(module_name)

        if module_name in _BANNED_RAW_READER_MODULES:
            offending.append(f"adapter import walk reached banned module {module_name!r}")

        if module_name in _COMPOSITION_ROOT_BOUNDARIES:
            # Opaque boundary: the edge INTO it is real (already recorded via
            # `visited`), but its own re-export fan-out is not part of this
            # adapter's real dependency shape -- do not parse/enqueue its imports.
            continue

        path = _module_name_to_path(module_name)
        if path is None:
            continue

        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        for candidate in _iter_import_candidates(tree, module_name):
            if candidate in _BANNED_RAW_READER_MODULES:
                offending.append(f"{module_name} imports banned module {candidate!r}")
            if candidate.startswith("backend") and candidate not in visited:
                queue.append(candidate)

    return visited, offending


class LlmAdaptersNeverImportRawTranscriptReadersTests(unittest.TestCase):
    """ADR-018's structural enforcement: adapters never reach a raw reader."""

    def test_adapter_modules_never_reach_a_raw_transcript_reader(self) -> None:
        for entry_module in _ADAPTER_ENTRY_MODULES:
            with self.subTest(entry_module=entry_module):
                visited, offending = _walk_adapter_graph(entry_module)

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
                    "Found a banned raw-transcript-reader import in the "
                    f"{entry_module} dependency graph: {offending}",
                )

    def test_walk_reaches_the_sanctioned_seam_module(self) -> None:
        """Positive control -- the walk genuinely traverses real edges.

        Mirrors ``test_session_naming_read_path_no_model_client.py``'s
        ``test_session_detail_module_is_part_of_every_relevant_walk``: if the
        walk mechanism silently broke (e.g. a path-resolution regression made
        it visit zero modules past the entry point), the negative assertion
        above would pass for the wrong reason -- vacuously, not because the
        adapters are actually clean. Every current adapter imports
        ``backend.application.ports.llm`` directly, so a working walk MUST
        reach it from every entry module.
        """
        for entry_module in _ADAPTER_ENTRY_MODULES:
            with self.subTest(entry_module=entry_module):
                visited, _ = _walk_adapter_graph(entry_module)
                self.assertIn(_SANCTIONED_SEAM_MODULE, visited)

    def test_walk_visits_all_three_adapter_entry_modules(self) -> None:
        """Reachability sanity: the walk covers a non-empty, known-real graph.

        Guards against the entry-module list itself silently shrinking to
        nothing (e.g. a typo'd module name that never resolves to a file) --
        the union of every walk's visited set must be non-empty and must
        contain each of the three concrete adapter modules this guardrail is
        scoped to (gemini, ollama, anthropic).
        """
        visited_union: set[str] = set()
        for entry_module in _ADAPTER_ENTRY_MODULES:
            visited, _ = _walk_adapter_graph(entry_module)
            visited_union |= visited

        self.assertTrue(visited_union, "adapter import walk visited nothing at all")
        for entry_module in _ADAPTER_ENTRY_MODULES:
            self.assertIn(entry_module, visited_union)

    def test_banned_modules_resolve_to_real_files(self) -> None:
        """The banned-module set must name modules that actually exist.

        A stale/typo'd entry in ``_BANNED_RAW_READER_MODULES`` (e.g. after a
        rename) would never be reachable by construction, making the negative
        assertion above pass for the wrong reason. This pins each banned
        target to a real file on disk.
        """
        for module_name in _BANNED_RAW_READER_MODULES:
            with self.subTest(module_name=module_name):
                path = _module_name_to_path(module_name)
                self.assertIsNotNone(
                    path, f"{module_name}: does not resolve to any file on disk"
                )
                assert path is not None  # narrow for the type checker
                self.assertTrue(path.is_file(), f"{module_name}: resolved path is not a file")


if __name__ == "__main__":
    unittest.main()
