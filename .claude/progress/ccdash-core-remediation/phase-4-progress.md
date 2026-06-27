---
schema_version: 2
doc_type: progress
phase: 4
phase_title: "Live Link Freshness"
feature_slug: ccdash-core-remediation
status: completed
created: 2026-06-11
updated: 2026-06-11
overall_progress: 100
completion_estimate: 2026-06-11
parallelization:
  strategy: sequential
  batch_1: [T4-001, T4-002, T4-003, T4-004, T4-005, T4-006, T4-007]
---

# Phase 4 Progress — Live Link Freshness

## Causal-Link Proof (T4-001)

**Dispatch seam: watcher event → sync_changed_files → link rebuild**

### Current (unfixed) hot path:
1. `FileWatcher._watch_loop` emits a change event (watchfiles)
2. → `sync_engine.sync_changed_files(project_id, classified, sessions_dir, docs_dir, progress_dir, ...)`
3. → For each JSONL change: `_sync_single_session(project_id, path)` — scoped to the single file, correct
4. → After all files processed: **directly calls `_rebuild_entity_links(project_id, docs_dir, progress_dir, operation_id)`** ← BUG: full global rebuild, bypasses the flag

### Global fingerprint scan location:
`_rebuild_entity_links(project_id, docs_dir, progress_dir)` — when `docs_dir` and `progress_dir` are provided,
it internally calls `_store_document_catalog_index()` (line ~5044) which walks **all `.md` files** via
`self._rglob(root, "*.md")`. This is the **global filesystem scan** that AC-T4-003 prohibits on the hot path.

### `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` flag (pre-fix):
- Gated in `_dispatch_link_rebuild` (called from `sync_project` / full sync only)
- `sync_changed_files` bypasses `_dispatch_link_rebuild` and calls `_rebuild_entity_links` directly
- Therefore the flag had **zero effect** on the watcher hot path before this fix

### Scoped path (`rebuild_links_for_entities`):
- Calls `link_repo.rebuild_for_entities(entity_type, ids)` — scoped delete for those entity IDs only
- Then calls `_rebuild_entity_links(project_id)` **without `docs_dir`/`progress_dir`** → no `_store_document_catalog_index` → no filesystem walk
- This is the "family-scoped" path

### Fix implemented (sync_engine.py):
In `sync_changed_files`, replaced the direct `_rebuild_entity_links(project_id, docs_dir, progress_dir)` call with:
1. When `INCREMENTAL_LINK_REBUILD_ENABLED=True` AND `should_rebuild_links` AND NOT `should_rebuild_for_version`:
   - Collect session IDs from changed JSONL files via `session_repo.list_by_source(sync_key)`
   - If IDs found: call `rebuild_links_for_entities(project_id, "session", ids, trigger=trigger)` → scoped
   - If no IDs (orphan/empty JSONL): NO-OP, log deferred count, no global fallback (AC-T4-002)
2. When flag=False OR version stale OR version-only trigger: use existing full path (unchanged)

## Task Table

tasks:
  - id: T4-001
    name: "Trace scoped-rebuild causal path"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    evidence: "Causal-link proof: dispatch seam is sync_changed_files line 4176 (pre-fix) calling _rebuild_entity_links directly. Global scan: _store_document_catalog_index at ~line 5034 walks docs_dir/*.md via _rglob. Flag had zero effect on watcher path. Scoped path: rebuild_links_for_entities calls _rebuild_entity_links WITHOUT docs_dir = no filesystem walk."
    acs:
      - AC-T4-001: DONE

  - id: T4-002
    name: "Family-scoped rebuild on watcher event"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    evidence: "sync_engine.py sync_changed_files: collects session IDs via session_repo.list_by_source, calls rebuild_links_for_entities with those IDs. No-op when IDs empty (per AC-T4-002 resilience). Verified by T4-005/T4-006 tests."
    acs:
      - AC-T4-002: DONE — verified by TestLinkFreshnessWithinOneCycle + TestDeferredRebuildForOrphanJsonl

  - id: T4-003
    name: "No global fingerprint scan on hot path"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    evidence: "sync_changed_files flag=True path routes to rebuild_links_for_entities which calls _rebuild_entity_links WITHOUT docs_dir/progress_dir → _store_document_catalog_index is a no-op. Test TestNoGlobalScanOnHotPath::test_global_rebuild_not_called_scoped_rebuild_called_once patches _rebuild_entity_links and asserts 0 direct calls."
    acs:
      - AC-T4-003: DONE — verified by TestNoGlobalScanOnHotPath

  - id: T4-004
    name: "Flip CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED default to True"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    evidence: "backend/config.py: _env_bool('CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED', True). .env.example updated. CLAUDE.md convention note updated. TestConfigDefaultTrue::test_default_is_true_when_env_unset passes."
    acs:
      - AC-T4-004: DONE — 3 config tests green

  - id: T4-005
    name: "Freshness integration test"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    evidence: "TestLinkFreshnessWithinOneCycle::test_new_jsonl_triggers_scoped_rebuild_within_one_cycle: writes JSONL, drives ONE deterministic watcher tick via sync_changed_files, asserts rebuild_links_for_entities called and links_created==2. Uses deterministic tick, no wall-clock sleep."
    acs:
      - AC-T4-005: DONE

  - id: T4-006
    name: "No-global-scan assertion test"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    evidence: "TestNoGlobalScanOnHotPath::test_global_rebuild_not_called_scoped_rebuild_called_once: patches _rebuild_entity_links (global) and rebuild_links_for_entities (scoped), fires sync_changed_files with INCREMENTAL=True, asserts global NOT called and scoped called once with correct args. TestConfigDefaultTrue::test_default_is_true_when_env_unset asserts default=True."
    acs:
      - AC-T4-006: DONE — 15/15 tests pass

  - id: T4-007
    name: "Update flag docs note"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    evidence: "CLAUDE.md line updated from 'default false' to 'default true' with description of proven family-scoped watcher path. .env.example comment updated. CHANGELOG deferred to Phase 12."
    acs:
      - AC-T4-007: DONE

## Test Results

```
backend/tests/test_link_freshness.py::TestConfigDefaultTrue::test_default_is_true_when_env_unset PASSED
backend/tests/test_link_freshness.py::TestConfigDefaultTrue::test_env_override_false_disables_flag PASSED
backend/tests/test_link_freshness.py::TestConfigDefaultTrue::test_env_override_zero_disables_flag PASSED
backend/tests/test_link_freshness.py::TestSessionFamilyScopeKey::test_project_id_appears_first PASSED
backend/tests/test_link_freshness.py::TestSessionFamilyScopeKey::test_returns_empty_for_blank_path PASSED
backend/tests/test_link_freshness.py::TestSessionFamilyScopeKey::test_returns_empty_for_hidden_file PASSED
backend/tests/test_link_freshness.py::TestSessionFamilyScopeKey::test_returns_project_slash_stem PASSED
backend/tests/test_link_freshness.py::TestSessionFamilyScopeKey::test_stem_without_extension PASSED
backend/tests/test_link_freshness.py::TestNoGlobalScanOnHotPath::test_global_rebuild_called_when_flag_disabled PASSED
backend/tests/test_link_freshness.py::TestNoGlobalScanOnHotPath::test_global_rebuild_not_called_scoped_rebuild_called_once PASSED
backend/tests/test_link_freshness.py::TestNoGlobalScanOnHotPath::test_no_global_scan_when_version_stale_but_flag_on PASSED
backend/tests/test_link_freshness.py::TestLinkFreshnessWithinOneCycle::test_empty_jsonl_defers_but_does_not_raise PASSED
backend/tests/test_link_freshness.py::TestLinkFreshnessWithinOneCycle::test_new_jsonl_triggers_scoped_rebuild_within_one_cycle PASSED
backend/tests/test_link_freshness.py::TestDeferredRebuildForOrphanJsonl::test_deferred_does_not_call_global_or_scoped_rebuild PASSED
backend/tests/test_link_freshness.py::TestNoGlobalScanForDocChanges::test_doc_change_with_flag_on_does_not_invoke_global_rebuild PASSED
15/15 passed
```

## Regression Suite (pre-existing failure noted)

```
test_sync_engine_linking.py          14/14 passed
test_entity_links_rebuild_for_entities.py  6/6 passed
test_document_linking.py             14/14 passed
test_file_watcher.py                 5/6 passed (1 pre-existing failure unrelated to Phase 4)
test_sync_engine_session_ingest_boundaries.py  2/2 passed
test_p3_watcher_registry.py          57/57 passed (1 skipped)
test_sync_engine_session_ingest_repository_wiring.py  2/2 passed
test_sync_cache_invalidation_p2_002.py  6/6 passed
test_link_audit.py                   2/2 passed
test_sync_all_projects.py            13/13 passed
```

Pre-existing failure: test_file_watcher.py::RuntimeWatcherContractTests::test_job_adapter_does_not_resolve_binding_or_start_watcher_for_api_profile
— AttributeError on job_scheduler attribute in SimpleNamespace stub, unrelated to Phase 4 changes (confirmed by stash-check on clean branch).
