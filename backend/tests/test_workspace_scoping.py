"""Reflection test: workspace_id scoping contract for repository public methods.

PURPOSE
-------
This test verifies that the key repository classes in CCDash that read from
workspace-partitioned tables enforce the ``workspace_id`` scoping contract.

Specifically, every public read/count/list method on the in-scope repository
classes MUST:
(a) accept a ``workspace_id`` keyword-only parameter (verified via
    ``inspect.signature``), AND
(b) reference ``workspace_id`` in its method source (verified via
    ``inspect.getsource``).

Write-path methods (upsert, delete, etc.) are excluded by name pattern.

EXEMPTION PROCESS
-----------------
If a public method on an in-scope class legitimately does NOT need
workspace_id (e.g., an infrastructure helper that delegates to another
scoped method, or a cross-workspace admin operation), add it to
``EXEMPT_METHODS`` with a descriptive justification:

    EXEMPT_METHODS = {
        "sessions.SqliteSessionRepository.get_by_id": "lookup by PK, no workspace filter needed for single-row access",
    }

OUT-OF-SCOPE DOMAINS
--------------------
The following domains are intentionally NOT checked by this test (they are
either workspace-agnostic by design or scheduled for a later phase):

- pricing.*         — global model_pricing catalog, workspace-agnostic
- runtime_state.*   — singleton infra state (alert_config, sync_state)
- test_*.*          — test domain repos, not yet workspace-partitioned
- worktree_contexts.*— separate concern, out of Phase 4 scope
- analytics.*       — metric aggregation repo, separate scoping concern
- intelligence.*    — session intelligence facts, separate scoping concern
- entity_graph.*    — graph linking repo, not partitioned in Phase 4
- links.*           — entity links, not partitioned in Phase 4

The test runs in < 1 second. No live database connection is required.
"""
from __future__ import annotations

import importlib
import inspect
import unittest
from typing import Any

# ---------------------------------------------------------------------------
# In-scope repository classes to check
# Format: (module_dotted_path, class_name)
# ---------------------------------------------------------------------------

IN_SCOPE_REPO_CLASSES: list[tuple[str, str]] = [
    # SQLite repos
    ("backend.db.repositories.sessions", "SqliteSessionRepository"),
    ("backend.db.repositories.tasks", "SqliteTaskRepository"),
    ("backend.db.repositories.features", "SqliteFeatureRepository"),
    ("backend.db.repositories.documents", "SqliteDocumentRepository"),
    # Postgres repos
    ("backend.db.repositories.postgres.sessions", "PostgresSessionRepository"),
    ("backend.db.repositories.postgres.tasks", "PostgresTaskRepository"),
    ("backend.db.repositories.postgres.features", "PostgresFeatureRepository"),
    ("backend.db.repositories.postgres.documents", "PostgresDocumentRepository"),
]

# ---------------------------------------------------------------------------
# Exemption registry
# Format: "module_short_name.ClassName.method_name": "justification"
# module_short_name is the last component of the dotted module path.
# ---------------------------------------------------------------------------

EXEMPT_METHODS: dict[str, str] = {
    # ── Sessions: write paths and detail sub-tables ──────────────────────────
    # Detail sub-tables (session_logs, session_tool_usage, session_file_updates,
    # session_artifacts, session_relationships) are JOIN'd to sessions on
    # session_id and are already tenant-scoped transitively through the sessions
    # table.  write-path methods always receive workspace_id as a positional arg.
    "sessions.SqliteSessionRepository.upsert": "write path, workspace_id passed as parameter to INSERT",
    "sessions.SqliteSessionRepository.upsert_logs": "write path for session_logs detail table",
    "sessions.SqliteSessionRepository.upsert_tool_usage": "write path for session_tool_usage detail table",
    "sessions.SqliteSessionRepository.upsert_file_updates": "write path for session_file_updates detail table",
    "sessions.SqliteSessionRepository.upsert_artifacts": "write path for session_artifacts detail table",
    "sessions.SqliteSessionRepository.upsert_relationships": "write path for session_relationships detail table",
    "sessions.SqliteSessionRepository.delete_by_source": "write path (delete), no workspace filter needed",
    "sessions.SqliteSessionRepository.delete_relationships_for_source": "write path (delete), no workspace filter needed",
    "sessions.SqliteSessionRepository.update_usage_fields": "write path (update by PK), no workspace filter needed",
    "sessions.SqliteSessionRepository.update_observability_fields": "write path (update by PK), no workspace filter needed",
    "sessions.SqliteSessionRepository.get_logs": "detail sub-table keyed by session_id; cross-workspace access is already blocked by get_by_id workspace check upstream",
    "sessions.SqliteSessionRepository.get_tool_usage": "detail sub-table keyed by session_id; cross-workspace access already blocked upstream",
    "sessions.SqliteSessionRepository.get_file_updates": "detail sub-table keyed by session_id; cross-workspace access already blocked upstream",
    "sessions.SqliteSessionRepository.get_artifacts": "detail sub-table keyed by session_id; cross-workspace access already blocked upstream",
    "sessions.SqliteSessionRepository.list_relationships": "detail sub-table keyed by project + session; cross-workspace access already blocked upstream",

    # ── Tasks: write paths / non-workspace-partitioned detail reads ──────────
    "tasks.SqliteTaskRepository.upsert": "write path, workspace_id passed as parameter to INSERT",
    "tasks.SqliteTaskRepository.delete_by_source": "write path (delete), no workspace filter needed",

    # ── Features: write paths / phase sub-table operations ───────────────────
    "features.SqliteFeatureRepository.upsert": "write path, workspace_id passed as parameter to INSERT",
    "features.SqliteFeatureRepository.delete": "write path (delete), no workspace filter needed",
    "features.SqliteFeatureRepository.upsert_phases": "write path for feature_phases detail table",
    "features.SqliteFeatureRepository.get_phases": "detail sub-table keyed by feature_id; cross-workspace access already blocked upstream by get_by_id",
    "features.SqliteFeatureRepository.list_all": "cross-project workspace-scoped list, see WORKSPACE-AUDIT-EXEMPT comment",

    # ── Documents: write paths ───────────────────────────────────────────────
    "documents.SqliteDocumentRepository.upsert": "write path, workspace_id passed as parameter to INSERT",
    "documents.SqliteDocumentRepository.delete_by_source": "write path (delete), no workspace filter needed",
    "documents.SqliteDocumentRepository.upsert_refs": "write path for document_refs detail table",
    "documents.SqliteDocumentRepository.list_all": "delegates to list_paginated which enforces workspace_id",

    # ── Postgres Sessions ────────────────────────────────────────────────────
    "sessions.PostgresSessionRepository.upsert": "write path",
    "sessions.PostgresSessionRepository.upsert_logs": "write path",
    "sessions.PostgresSessionRepository.upsert_tool_usage": "write path",
    "sessions.PostgresSessionRepository.upsert_file_updates": "write path",
    "sessions.PostgresSessionRepository.upsert_artifacts": "write path",
    "sessions.PostgresSessionRepository.upsert_relationships": "write path",
    "sessions.PostgresSessionRepository.delete_by_source": "write path",
    "sessions.PostgresSessionRepository.delete_relationships_for_source": "write path",
    "sessions.PostgresSessionRepository.update_usage_fields": "write path (update by PK)",
    "sessions.PostgresSessionRepository.update_observability_fields": "write path (update by PK)",
    "sessions.PostgresSessionRepository.get_logs": "detail sub-table keyed by session_id; cross-workspace access already blocked by get_by_id upstream",
    "sessions.PostgresSessionRepository.get_tool_usage": "detail sub-table keyed by session_id; cross-workspace access already blocked upstream",
    "sessions.PostgresSessionRepository.get_file_updates": "detail sub-table keyed by session_id; cross-workspace access already blocked upstream",
    "sessions.PostgresSessionRepository.get_artifacts": "detail sub-table keyed by session_id; cross-workspace access already blocked upstream",
    "sessions.PostgresSessionRepository.list_relationships": "detail sub-table by project + session; cross-workspace access already blocked upstream",

    # ── Postgres Tasks ───────────────────────────────────────────────────────
    "tasks.PostgresTaskRepository.upsert": "write path",
    "tasks.PostgresTaskRepository.delete_by_source": "write path",

    # ── Postgres Features ────────────────────────────────────────────────────
    "features.PostgresFeatureRepository.upsert": "write path",
    "features.PostgresFeatureRepository.delete": "write path",
    "features.PostgresFeatureRepository.upsert_phases": "write path for feature_phases",
    "features.PostgresFeatureRepository.get_phases": "detail sub-table keyed by feature_id; cross-workspace access already blocked by get_by_id upstream",
    "features.PostgresFeatureRepository.list_all": "cross-project workspace-scoped list, see WORKSPACE-AUDIT-EXEMPT comment",

    # ── Postgres Documents ───────────────────────────────────────────────────
    "documents.PostgresDocumentRepository.upsert": "write path",
    "documents.PostgresDocumentRepository.delete_by_source": "write path",
    "documents.PostgresDocumentRepository.upsert_refs": "write path for document_refs",
    "documents.PostgresDocumentRepository.list_all": "delegates to list_paginated which enforces workspace_id",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _module_short(dotted: str) -> str:
    return dotted.rsplit(".", 1)[-1]


def _is_exempt(module_short: str, class_name: str, method_name: str) -> bool:
    key = f"{module_short}.{class_name}.{method_name}"
    return key in EXEMPT_METHODS


def _accepts_workspace_id(method: Any) -> bool:
    try:
        sig = inspect.signature(method)
    except (ValueError, TypeError):
        return False
    return "workspace_id" in sig.parameters


def _source_has_workspace_predicate(method: Any) -> bool:
    """Return True if the method source references workspace_id."""
    try:
        src = inspect.getsource(method)
    except (OSError, TypeError):
        return True  # Cannot introspect; trust the signature check
    return "workspace_id" in src


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

class TestWorkspaceScopingContract(unittest.TestCase):
    """All non-exempt public methods on in-scope repository classes must enforce
    workspace_id scoping."""

    def test_all_scoped_methods_enforce_workspace_id(self) -> None:
        """Walk every public non-exempt method on in-scope repository classes and
        assert that each method:
        (a) accepts a ``workspace_id`` parameter in its signature, AND
        (b) references ``workspace_id`` in its method source.

        Failures are aggregated so all violations are visible in one run.
        """
        failures: list[str] = []

        for dotted_module, class_name in IN_SCOPE_REPO_CLASSES:
            short = _module_short(dotted_module)
            try:
                module = importlib.import_module(dotted_module)
                cls = getattr(module, class_name)
            except (ImportError, AttributeError) as exc:
                failures.append(f"IMPORT ERROR: {dotted_module}.{class_name} — {exc}")
                continue

            for method_name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue  # private/dunder always exempt
                if _is_exempt(short, class_name, method_name):
                    continue

                # (a) Must accept workspace_id
                if not _accepts_workspace_id(method):
                    failures.append(
                        f"MISSING PARAM: {short}.{class_name}.{method_name}() "
                        f"— workspace_id not in signature. "
                        f"Add to EXEMPT_METHODS with justification or fix the method."
                    )
                    continue  # skip source check if param is absent

                # (b) Source must reference workspace_id
                if not _source_has_workspace_predicate(method):
                    failures.append(
                        f"MISSING PREDICATE: {short}.{class_name}.{method_name}() "
                        f"— workspace_id not referenced in method source. "
                        f"Ensure WHERE workspace_id = ? is present or a helper enforces it."
                    )

        if failures:
            msg = (
                f"\n{len(failures)} workspace scoping violation(s) detected.\n"
                "To exempt a method, add an entry to EXEMPT_METHODS in this file\n"
                "with a justification string explaining why it is exempt.\n\n"
            )
            msg += "\n".join(f"  - {f}" for f in sorted(failures))
            self.fail(msg)


if __name__ == "__main__":
    unittest.main()
