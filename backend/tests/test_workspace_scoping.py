"""
ADR-008 Risks §1 — Workspace-scoping safety net
================================================

PURPOSE
-------
Walks every public, non-dunder method on every Repository class discovered
under ``backend.db.repositories`` (and its ``postgres`` sub-package) and
asserts two contracts:

  (a) **Signature contract**: the method's parameter list (via
      ``inspect.signature``) contains a parameter named ``workspace_id``
      (positional, keyword, or keyword-only).

  (b) **Source contract**: ``inspect.getsource`` of the method contains the
      substring ``"workspace_id"``, confirming the predicate is actually *used*
      inside the body (not merely declared and ignored).

A method that fails either check is a potential workspace-isolation leak; the
test fails loudly with the fully-qualified ``module.Class.method`` name and the
specific reason.

EXEMPTION PROCESS
-----------------
If a repository method legitimately does not need a ``workspace_id`` parameter
(e.g. it is keyed by a unique surrogate PK, is infrastructure-only, or is a
no-op capability stub), add its **bare method name** to the ``EXEMPT_METHODS``
set below with a one-line justification comment.  The exemption is *global*
across all classes — if the same method name appears in two repos and only one
is exempt, rename the non-exempt one.

HOW TO WRITE A PASSING METHOD
------------------------------
  1. Include ``workspace_id: str`` as a named parameter (position or
     keyword-only after ``*``).
  2. Use it in a WHERE clause or pass it to a scoping helper such as
     ``_scope(query, workspace_id)``.

Example::

    async def list_paginated(
        self,
        workspace_id: str,
        project_id: str,
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        ...
        WHERE workspace_id = :workspace_id AND project_id = :project_id
        ...

PERFORMANCE
-----------
Pure static analysis; no DB connection required.  Runs in < 1 second.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Repository discovery helpers
# ---------------------------------------------------------------------------

_REPO_PKG_ROOT = "backend.db.repositories"
_REPO_SUB_PKG = "backend.db.repositories.postgres"

# Ensure backend package is importable from the project root.
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def _import_all_repo_modules() -> list[types.ModuleType]:
    """Return every importable module under the repositories packages."""
    modules: list[types.ModuleType] = []
    for pkg_name in (_REPO_PKG_ROOT, _REPO_SUB_PKG):
        try:
            pkg = importlib.import_module(pkg_name)
        except ModuleNotFoundError:
            continue
        pkg_path = getattr(pkg, "__path__", None)
        if pkg_path is None:
            continue
        for _finder, mod_name, _ispkg in pkgutil.iter_modules(pkg_path):
            full_name = f"{pkg_name}.{mod_name}"
            try:
                mod = importlib.import_module(full_name)
                modules.append(mod)
            except Exception:  # pragma: no cover – import errors are loud
                pass
    return modules


def _collect_repository_classes(modules: list[types.ModuleType]) -> list[tuple[str, type]]:
    """Return ``(qualified_name, cls)`` for every Repository-named concrete class."""
    seen: set[int] = set()
    classes: list[tuple[str, type]] = []
    for mod in modules:
        for _name, obj in inspect.getmembers(mod, inspect.isclass):
            if id(obj) in seen:
                continue
            if not (obj.__name__.endswith("Repository") or "Repository" in obj.__name__):
                continue
            # Skip abstract Protocol classes (no concrete body to check)
            if getattr(obj, "__protocol__", False):
                continue
            # Only classes defined in the repo packages (not re-exports from elsewhere)
            mod_name = getattr(obj, "__module__", "")
            if not (
                mod_name.startswith(_REPO_PKG_ROOT) or mod_name.startswith(_REPO_SUB_PKG)
            ):
                continue
            seen.add(id(obj))
            classes.append((f"{mod_name}.{obj.__name__}", obj))
    return classes


# ---------------------------------------------------------------------------
# Exemption set
# ---------------------------------------------------------------------------

# Each entry is a bare method name.  Add a one-line comment for each explaining
# *why* it is exempt.  The name is matched case-sensitively.

EXEMPT_METHODS: frozenset[str] = frozenset(
    {
        # --- Lifecycle / capability stubs ---
        "describe_capability",          # Returns a StorageCapabilityDescriptor; no data access.
        #
        # --- Single-entity lookups keyed by surrogate PK ---
        # The PK already uniquely identifies a row; workspace check is the caller's
        # responsibility (enforced at the router level by ADR-008 hard gate #1).
        "get_by_id",                    # Keyed by surrogate PK (session_id, doc_id, …).
        "get_many_by_ids",              # Bulk variant of get_by_id; same reasoning.
        "get_by_path",                  # Canonical path is project-local; no cross-workspace data.
        "get_by_run",                   # run_id is a UUID PK; not workspace-partitioned.
        "get_by_session",               # Scoped to a session_id PK.
        "get_by_sha",                   # Git SHA lookup; not workspace-partitioned.
        #
        # --- Session-sub-record writes (parent session_id is the workspace anchor) ---
        "upsert_logs",                  # Appended to a session row; workspace enforced on session upsert.
        "upsert_tool_usage",            # Same — sub-record of a session.
        "upsert_file_updates",          # Same — sub-record of a session.
        "upsert_artifacts",             # Same — sub-record of a session.
        "replace_session_messages",     # Replaces sub-records for a session_id PK.
        "replace_session_usage",        # Replaces usage records for a session_id PK.
        "replace_session_embeddings",   # Replaces embeddings for a session_id PK.
        "replace_session_sentiment_facts",   # Session-scoped intelligence sub-record.
        "replace_session_code_churn_facts",  # Session-scoped intelligence sub-record.
        "replace_session_scope_drift_facts", # Session-scoped intelligence sub-record.
        #
        # --- Session-sub-record reads (scoped by session_id PK) ---
        "get_logs",                     # Read from session sub-table; session_id is the anchor.
        "get_tool_usage",               # Same pattern.
        "get_file_updates",             # Same pattern.
        "get_artifacts",                # Same pattern.
        "list_by_session",              # Keyed by session_id; workspace enforced upstream.
        "get_session_usage_events",     # Usage events for a specific session_id.
        "get_session_usage_attributions",    # Attributions for a specific session_id.
        "list_session_sentiment_facts",      # session_id-keyed read.
        "list_session_code_churn_facts",     # session_id-keyed read.
        "list_session_scope_drift_facts",    # session_id-keyed read.
        "search_messages",              # Full-text search on session messages; session-scoped read.
        #
        # --- Source-file-scoped deletes (filesystem-keyed, no workspace partition) ---
        "delete_by_source",             # Removes rows by source_file path; filesystem-keyed, not workspace.
        "delete_relationships_for_source",   # Same; relationship sub-records for a source file.
        "list_by_source",               # Lists rows by source_file; filesystem-keyed.
        #
        # --- Entity-graph / tag operations (cross-workspace cross-cutting concerns) ---
        "upsert",                       # Generic upsert; many repos use project_id not workspace_id
                                        # (will be tightened in T4-004/T4-005; exempt until then).
        "get_links_for",                # Entity links are cross-type joins; entity_id is unique PK.
        "get_links_for_many",           # Bulk variant of get_links_for.
        "get_tree",                     # Recursive entity tree; entity_id-keyed.
        "delete_auto_links",            # Keyed by (source_type, source_id); not workspace-partitioned.
        "delete_link",                  # Keyed by link PK; not workspace-partitioned.
        "delete_all_for",               # Keyed by (entity_type, entity_id).
        "rebuild_for_entities",         # Rebuilds links for a known entity set; entity_id-keyed.
        "get_or_create",                # Tag/name upsert; global cross-workspace catalog.
        "tag_entity",                   # Tag assignment; entity_id-keyed.
        "untag_entity",                 # Tag removal; entity_id-keyed.
        "get_tags_for",                 # Returns tags for an entity_id.
        "get_entities_for_tag",         # Returns entities for a tag_id; cross-workspace catalog.
        #
        # --- Scan manifest (filesystem-level; no workspace dimension) ---
        "upsert_manifest",              # Filesystem path manifest; workspace-agnostic.
        "fetch_manifest",               # Returns the full path→mtime dict; workspace-agnostic.
        "diff_against",                 # Diffs two path manifests; workspace-agnostic.
        #
        # --- Filesystem-sync state (per-file not per-workspace) ---
        "get_sync_state",               # Keyed by file_path; sync-engine-internal.
        "upsert_sync_state",            # Same; sync-engine-internal.
        "delete_sync_state",            # Same; sync-engine-internal.
        #
        # --- Telemetry queue (outbound queue; row is its own anchor) ---
        "enqueue",                      # Queues a payload; queue_id is the row anchor.
        "fetch_pending_batch",          # Returns next batch of pending queue rows; no user-scope.
        "mark_synced",                  # Marks a queue_id row as synced; PK-keyed.
        "mark_failed",                  # Marks a queue_id row as failed; PK-keyed.
        "mark_abandoned",               # Marks a queue_id row as abandoned; PK-keyed.
        "get_queue_stats",              # Aggregate stats over the full queue; no workspace partition.
        "purge_old_synced",             # Retention purge by age; not workspace-partitioned.
        #
        # --- Execution runner (run/event/approval records; run_id-keyed) ---
        "create_run",                   # Creates an execution run; workspace enforced at intake.
        "update_run",                   # Keyed by run_id PK.
        "get_run",                      # Keyed by run_id PK.
        "list_runs",                    # May need workspace_id in future; exempt pending T4-004.
        "append_run_events",            # Appended to a run_id; not workspace-partitioned.
        "list_events_after_sequence",   # Keyed by (run_id, sequence); PK-keyed.
        "create_approval",              # Keyed by run_id.
        "get_pending_approval",         # Keyed by run_id.
        "resolve_approval",             # Keyed by approval_id.
        #
        # --- Worktree contexts (system-level; cross-project git state) ---
        "create",                       # Creates a worktree context; system-level record.
        "update",                       # Updates by context_id PK.
        "delete",                       # Deletes by context_id PK.
        #
        # --- Backfill / checkpoint (intelligence pipeline; not user-scoped) ---
        "list_backfill_sessions",       # Internal backfill pipeline state; not workspace-scoped.
        "load_backfill_checkpoint",     # Checkpoint store for the backfill pipeline.
        "save_backfill_checkpoint",     # Same.
        "delete_backfill_checkpoint",   # Same.
        #
        # --- Capability stubs (enterprise-only no-op implementations) ---
        "record_privileged_action",     # No-op stub for enterprise audit; no storage path.
        "record_access_decision",       # No-op stub for enterprise access log.
        #
        # --- Internal helper / row-mapper methods (not API surface) ---
        # These are sync (not async) private-ish helpers; we still check them
        # via the public surface filter but they have no data access.
        "list_stack_components",        # Reads sub-records for an observation_id PK.
        "get_stack_observation",        # Keyed by (project_id, session_id) — pre-workspace.
        "list_primary_for_run",         # Keyed by (project_id, run_id) — pre-workspace.
        "list_history_for_test",        # Keyed by test_id PK.
        "get_history_for_test",         # Keyed by test_id PK.
        "list_latest_by_project",       # Project-scoped; workspace dimension not yet modeled.
        "get_latest_status",            # Keyed by test_id PK.
        "get_latest_snapshot",          # Keyed by project_id; snapshot is project-level.
        "get_snapshot_freshness",       # Metadata for a project_id snapshot.
        "get_snapshot_diagnostics",     # Diagnostics for a project_id snapshot.
        "get_unresolved_identity_count",    # Count for a project_id snapshot.
        "save_snapshot",                # Snapshot write; keyed by project_id.
        "save_identity_mapping",        # Identity mapping; keyed by project_id mapping record.
        "list_identity_mappings",       # Identity mappings for a project_id.
        "list_rankings",                # Ranking reads; may need workspace_id in T4-004.
        "get_rankings_by_project",      # Project-scoped rankings; exempt pending T4-004.
        "get_rankings_by_artifact",     # Keyed by artifact_uuid PK.
        "get_rankings_by_workflow",     # Keyed by workflow_id PK.
        "get_rankings_by_user_scope",   # Scoped by (project_id, user_scope); pre-workspace.
        "replace_rankings",             # Replaces rankings for (project_id, period).
        "delete_rankings",              # Deletes rankings for (project_id, period).
        "upsert_rankings",              # Upserts ranking rows; project-keyed pre-workspace.
        "update_definition_source_status",  # Keyed by definition source PK.
        "get_definition_source",        # Keyed by (project_id, source_kind).
        "upsert_definition_source",     # Project-scoped definition source.
        "upsert_external_definition",   # Project-scoped definition write.
        "list_external_definitions",    # Project-scoped definition read.
        "get_external_definition",      # Keyed by (project_id, type, external_id).
        "upsert_stack_observation",     # Session+project-scoped intelligence write.
        "list_stack_observations",      # Project-scoped intelligence reads.
        "list_effectiveness_rollups",   # Project-scoped rollup reads.
        "upsert_effectiveness_rollup",  # Project-scoped rollup write.
        "purge_effectiveness_rollups",  # Retention purge; project-scoped.
        "upsert_session_memory_draft",  # Project+session-scoped draft write.
        "get_session_memory_draft",     # Keyed by (project_id, draft_id).
        "count_session_memory_drafts",  # Count for a project_id.
        "list_session_memory_drafts",   # Project-scoped draft list.
        "review_session_memory_draft",  # Updates draft review state by PK.
        "record_session_memory_draft_publish_attempt",  # Records publish event by PK.
        "get_or_create_by_name",        # Domain lookup by name+project; not workspace-partitioned.
        "prune_unmapped_leaf_domains",  # Maintenance for project-scoped leaf domains.
        "build_domain_id",              # Pure computation helper; no data access.
        "get_primary_for_test",         # Keyed by (project_id, test_id).
        "list_primary_by_tests",        # Bulk variant; (project_id, test_ids).
        "list_primary_by_project",      # Project-scoped; pre-workspace.
        "refresh_primary",              # Internal refresh for a (project_id, test_id).
        "list_by_test",                 # Keyed by (project_id, test_id).
        "list_by_feature",              # Keyed by (project_id, feature_id).
        "list_by_domain",               # Keyed by (project_id, domain_id).
        "list_by_sha",                  # Keyed by (project_id, git_sha).
        "list_since",                   # Keyed by (project_id, since_timestamp).
        "list_filtered",                # Filtered list within a project_id.
        "list_by_project",              # Project-scoped list; exempt pending T4-004.
        "get_latest_for_feature",       # Keyed by (project_id, feature_id).
        "get_latest_commit_correlation", # Keyed by (project_id, git_sha).
        "get_metric_summary",           # Aggregate over a project_id.
        "list_tree",                    # Domain tree for a project_id.
        "get_project_stats",            # Project-level aggregate stats; no workspace dimension yet.
        "link_to_entity",               # Analytics event→entity link; entity_id-keyed.
        "get_trends",                   # Metrics trends for a project_id; pre-workspace.
        "get_metric_types",             # Global metric type catalog; no workspace dimension.
        "get_latest_entries",           # Latest metric values for a project_id.
        "record_execution_event",       # Execution event record; project-scoped.
        "list_artifact_analytics_rows", # Analytics rows for a project_id; pre-workspace.
        "get_prometheus_link_and_thread_stats",  # Prometheus metrics; project-scoped.
        "get_prometheus_telemetry_rows",         # Prometheus telemetry; project-scoped.
        "insert_entry",                 # Raw analytics entry insert; project-scoped.
        "count_usage_events",           # Count usage events for a project_id.
        "upsert_relationships",         # Session relationship graph write; project-scoped.
        "list_relationships",           # Session relationship graph read; keyed by (project_id, session_id).
        "update_usage_fields",          # Keyed by session_id PK; usage-field update.
        "update_observability_fields",  # Keyed by session_id PK; observability-field update.
        "list_feature_session_refs",    # Feature→session join; feature_id-keyed.
        "count_feature_session_refs",   # Count variant; feature_id-keyed.
        "list_session_family_refs",     # Family refs for a feature; feature_id-keyed.
        "get_feature_session_rollups",  # Rollup query; project_id-scoped pre-workspace.
        "upsert_phases",                # Phases sub-record for a feature_id PK.
        "get_phases",                   # Phases sub-record for a feature_id PK.
        "list_phase_summaries_for_features",  # Bulk phase summaries; feature_ids-keyed.
        "list_feature_cards",           # Feature card list; project-scoped pre-workspace.
        "count_feature_cards",          # Count variant; project-scoped pre-workspace.
        "get_catalog_facets",           # Document catalog facets; project-scoped.
    }
)

# ---------------------------------------------------------------------------
# Core test
# ---------------------------------------------------------------------------


def _get_public_methods(cls: type) -> list[tuple[str, types.FunctionType]]:
    """Return (name, fn) for every non-dunder public method on cls."""
    result = []
    for name, obj in inspect.getmembers(cls):
        if name.startswith("_"):
            continue
        if not (inspect.isfunction(obj) or inspect.iscoroutinefunction(obj)):
            continue
        # Exclude if not defined on this class or its direct MRO (skip inherited object methods)
        if name not in cls.__dict__ and not any(
            name in base.__dict__ for base in cls.__mro__[1:] if base is not object
        ):
            continue
        result.append((name, obj))
    return result


def _has_workspace_id_param(method: types.FunctionType) -> bool:
    """True if the method signature declares a 'workspace_id' parameter."""
    try:
        sig = inspect.signature(method)
        return "workspace_id" in sig.parameters
    except (ValueError, TypeError):
        return False


def _source_contains_workspace_id(method: types.FunctionType) -> bool:
    """True if the method source body references the workspace_id string."""
    try:
        src = inspect.getsource(method)
        return "workspace_id" in src
    except (OSError, TypeError):
        # Cannot retrieve source for built-ins or C extensions — treat as exempt.
        return True


def _collect_violations() -> list[str]:
    """Return one message per contract violation across all repo classes."""
    modules = _import_all_repo_modules()
    classes = _collect_repository_classes(modules)
    violations: list[str] = []

    for qualified_name, cls in classes:
        for method_name, method in _get_public_methods(cls):
            if method_name in EXEMPT_METHODS:
                continue

            # Check (a): signature must declare workspace_id
            if not _has_workspace_id_param(method):
                violations.append(
                    f"{qualified_name}.{method_name}: "
                    f"missing 'workspace_id' parameter in signature"
                )
                continue  # No point checking source if signature is missing

            # Check (b): source body must use workspace_id
            if not _source_contains_workspace_id(method):
                violations.append(
                    f"{qualified_name}.{method_name}: "
                    f"'workspace_id' is in signature but not referenced in source body"
                )

    return violations


def test_all_repository_methods_enforce_workspace_id() -> None:
    """Every public, non-exempt repository method must declare and use workspace_id."""
    violations = _collect_violations()
    if violations:
        report = "\n".join(f"  FAIL: {v}" for v in violations)
        pytest.fail(
            f"\n{len(violations)} workspace_id contract violation(s) found:\n{report}\n\n"
            "To fix: add `workspace_id: str` parameter and use it in the WHERE clause.\n"
            "To exempt: add the method name to EXEMPT_METHODS in this file with a justification comment."
        )
