---
name: issue6-sync-all-projects
description: Fix for SkillMeat docs not detected — three defects: active-only sync, no worknotes scan root, write-back not suppressed for non-active projects
metadata:
  type: project
---

Issue 6: CCDash was not detecting completed SkillMeat planning docs (core-cache-boundary-refactor-v1 showing 'backlog' instead of 'completed').

Root causes and fixes landed 2026-06-03:

**PRIMARY (SYNC_ALL_PROJECTS)**: `RuntimeJobAdapter.start()` only synced/watched the active project. Fixed by iterating all registered projects when `CCDASH_SYNC_ALL_PROJECTS=True` (default True). Non-active syncs are serialised; the new block uses `_list_fn = getattr(workspace_registry, 'list_projects', None); callable(_list_fn)` guard to avoid breaking tests that use SimpleNamespace registries.

**WRITE-BACK SUPPRESSION (startup path)**: Non-active project syncs pass `allow_writeback=False` through the chain: `RuntimeJobAdapter.start()` → `sync.sync_project(allow_writeback=False)` → `_sync_features(allow_writeback=False)` → `scan_features(allow_writeback=False)` → `_reconcile_completion_equivalence(allow_writeback=False)`. The check is inserted BEFORE the `INFERRED_STATUS_WRITEBACK_ENABLED` config check so it takes priority.

**WRITE-BACK SUPPRESSION (watcher path — review fix 2026-06-03)**: The steady-state file-watcher path was leaking: `FileWatcher._watch_loop` called `sync_changed_files()` without `allow_writeback=False`, so changed .md files in non-active projects could still mutate source files. Fixed by threading `allow_writeback: bool = True` through: `sync_changed_files(allow_writeback)` → `_sync_features(allow_writeback)`, and `FileWatcher.start(allow_writeback)` → `_watch_loop(allow_writeback)` → stored as `self._allow_writeback`, and `FileWatcherRegistry.register(allow_writeback)` → `FileWatcher.start(allow_writeback)`. `RuntimeJobAdapter` passes `allow_writeback=False` for non-active projects in the watcher registration block.

**TERTIARY (WORKNOTES)**: `.claude/worknotes` added as a scan root to `_scan_auxiliary_docs` and watch root to `FileWatcher._resolve_watch_paths` + `FileWatcher.start` + `FileWatcherRegistry.register` (all accept new `worknotes_dir: Path | None` kwarg). Resolved via `_resolve_worknotes_dir()` helper in runtime.py.

**How to apply:** Operator must restart CCDash (or trigger `STARTUP_SYNC_ENABLED`) to backfill the existing DB for SkillMeat core-cache-boundary-refactor-v1 → completed.

**Why:** Active project at time of SkillMeat's completion was MeatyWiki, so SkillMeat was never synced after those docs were created.
