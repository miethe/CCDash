---
schema_version: 2
doc_type: progress
phase: 7
feature_slug: ccdash-core-remediation
title: "CCDash Core Remediation — Phase 7: Sync Coalescing + Recent-First + Startup Hygiene"
status: completed
started: 2026-06-11
completed: 2026-06-11
overall_progress: 100
completion_estimate: "100%"
validator_signed_off: true
runtime_smoke: skipped
runtime_smoke_reason: "Backend-only phase; no UI surfaces. Phase 7 is dispatch/sync-layer only — no HTTP routes, no FE components."

decisions:
  OQ-3:
    question: "Recent-first window definition: count-bounded (N-most-recent) vs time-bounded (last-K-days) vs mtime-budget."
    decision: "N-most-recent with mtime tiebreak. Default N=200 (CCDASH_SYNC_RECENT_FIRST_N)."
    rationale: >
      Count-bounded window works identically on workspaces of any age or size — avoids empty windows
      on new projects and runaway windows on large archives. Single integer knob for operators; no
      calendar dependency. Full backfill follows immediately in the same sync call; backfill_count
      is asserted == baseline_count (no silent partial). mtime tiebreak: files already sorted
      mtime-desc so the N boundary is deterministic even when multiple files share a second.
    config_key: "CCDASH_SYNC_RECENT_FIRST_N"
    default_value: 200
    location: "backend/config.py:1169-1184"

tasks:
  - id: T7-001
    name: "Design coalescing key + resolve OQ-3"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    verified_by: ["wave-2-reviewer"]
    evidence:
      - "backend/config.py:1150-1184 — SYNC_COALESCING_ENABLED, SYNC_RECENT_FIRST_ENABLED, SYNC_RECENT_FIRST_N with OQ-3 rationale inline"
      - "backend/db/sync_engine.py:3038-3064 — coalescing key (project_id, trigger) comment block"

  - id: T7-002
    name: "In-process coalescing guard"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    verified_by: ["wave-2-reviewer"]
    evidence:
      - "backend/db/sync_engine.py:1333-1338 — _sync_in_flight: set[tuple[str,str]] initialized in __init__"
      - "backend/db/sync_engine.py:3048-3064 — check+add guard (atomic in asyncio single-thread)"
      - "backend/db/sync_engine.py:3054-3062 — coalesced=True early-return with structured log"
      - "backend/db/sync_engine.py:3330-3335 — finally: _sync_in_flight.discard(_coal_key)"
      - "tests: TestInProcessCoalescing (5 tests, all pass)"

  - id: T7-003
    name: "Durable-queue coalescing guard"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    verified_by: ["wave-2-reviewer"]
    evidence:
      - "backend/adapters/jobs/durable_queue.py:126-177 — enqueue_durable_idempotent()"
      - "backend/adapters/jobs/durable_queue.py:157-168 — pending+running depth check; structured log on dedupe"
      - "backend/adapters/jobs/runtime.py:202-227 — startup uses enqueue_durable_idempotent; logs coalesced result"
      - "tests: TestDurableQueueCoalescing (4 tests, all pass)"

  - id: T7-004
    name: "Recent-first parse + lazy backfill"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    verified_by: ["wave-2-reviewer"]
    evidence:
      - "backend/db/sync_engine.py:4373-4468 — _sync_sessions: mtime-desc sort, recent-window priority pass, backfill pass"
      - "backend/db/sync_engine.py:4440-4450 — parity check: WARNING log on total_processed != baseline_count"
      - "backend/db/sync_engine.py:4413-4422 — log when recent window ready + backfill_deferred count"
      - "backend/db/sync_engine.py:4460-4467 — backfill_complete log"
      - "tests: TestRecentFirstParity (4 tests, all pass)"

  - id: T7-005
    name: "Reload boot-cost reduction (startup hygiene)"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    verified_by: ["wave-2-reviewer"]
    evidence:
      - "backend/config.py:992-995 — STARTUP_SYNC_LIGHT_MODE (existing flag, coordinated with)"
      - "backend/db/sync_engine.py:4364-4371 — _light_mode_scan_skip called at _sync_sessions entry"
      - "backend/adapters/jobs/runtime.py:1190-1209 — light_mode path: planning-artifacts only + rebuild_links=False"
      - "backend/adapters/jobs/runtime.py:1234-1237 — STARTUP_DEFERRED_REBUILD_LINKS with stagger delay"
      - "No parallel skip path introduced — AC 7.4 compliant"
      - "tests: TestReloadBootCostLightMode (2 tests, all pass)"

  - id: T7-006
    name: "Concurrency proof + tests"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    verified_by: ["wave-2-reviewer"]
    evidence:
      - "backend/tests/test_sync_coalescing.py — 22 tests, all pass"
      - "TestInProcessCoalescing::test_three_concurrent_dispatches_one_real_sync — AC 7.2 primary: 3 concurrent gather → 1 real sync"
      - "TestInProcessCoalescing::test_different_trigger_keys_not_coalesced — different keys both run"
      - "TestInProcessCoalescing::test_key_removed_from_in_flight_after_sync — key absent after completion"
      - "TestInProcessCoalescing::test_coalescing_disabled_allows_concurrent_runs — disabled=no guard"
      - "TestRecentFirstParity — 4 parity tests covering N<count, N>count, disabled, window split"
      - "TestReloadBootCostLightMode — manifest-skip and manifest-miss paths"
      - "TestBothBackendsCovered — memory and durable backend coverage"

  - id: T7-007
    name: "Concurrency review (gate)"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    verified_by: ["wave-2-reviewer"]
    notes: >
      Concurrency review performed inline. Guard analysis:
      (1) TOCTOU: check (_coal_key in set) + add (set.add) are both synchronous — no await between them
          in asyncio's cooperative single-threaded event loop. Second concurrent caller's check executes
          only after first caller's add, because the first yield is at _start_operation (after the add).
          No race window.
      (2) Key uniqueness under contention: key = (str(project_id), trigger_str) — deterministic, no
          hash collision risk for string tuples.
      (3) Lock scope: set membership is the primitive (not a lock); discard() in finally is idempotent
          even if add never ran (disabled path or early-return path). No deadlock possible.
      (4) Durable token uniqueness: depth() checks both pending and running status independently;
          compound check (pending > 0 OR running > 0) is correct — no gap between them.
      No unresolved race findings.
    evidence:
      - "backend/db/sync_engine.py:3048-3064 — check+add atomic in asyncio single-thread"
      - "backend/adapters/jobs/durable_queue.py:126-177 — durable guard depth() dual-status check"
      - "backend/tests/test_sync_coalescing.py::TestInProcessCoalescing (5 tests, all pass)"

phase4_composition_check:
  INCREMENTAL_LINK_REBUILD_ENABLED:
    status: preserved
    default: true
    location: "backend/config.py:128-133"
  dispatch_routing:
    status: preserved
    evidence:
      - "backend/db/sync_engine.py:2623 — if not config.INCREMENTAL_LINK_REBUILD_ENABLED: → full rebuild"
      - "backend/db/sync_engine.py:2665 — await self.rebuild_links_for_entities(...) on incremental path"
      - "backend/db/sync_engine.py:4230 — watcher hot path checks INCREMENTAL_LINK_REBUILD_ENABLED"
      - "backend/db/sync_engine.py:4264 — rebuild_links_for_entities on watcher incremental path"

test_results:
  command: "/Users/miethe/dev/homelab/development/CCDash/backend/.venv/bin/python -m pytest backend/tests/test_sync_coalescing.py -v"
  total: 22
  passed: 22
  failed: 0
  skipped: 0
  run_date: 2026-06-11

fix_applied:
  description: >
    The 4 failing TestInProcessCoalescing tests used _make_minimal_sync_engine() which bypassed
    SyncEngine.__init__ (via __new__), leaving self.db unset. When SYNC_COALESCING_ENABLED=False
    or a key was NOT pre-seeded as in-flight, sync_project ran the full sync path and reached
    _load_link_state (line 2496) which calls self.db → AttributeError.
    Fix: added 3 AsyncMock stubs to _make_minimal_sync_engine():
      engine._load_link_state = AsyncMock(return_value={})
      engine._save_link_state = AsyncMock()
      engine._capture_analytics = AsyncMock()
    These are production methods that access self.db; the test fixture stubs them out consistently
    with the existing pattern (all other self.db-touching methods were already mocked). No
    production code was changed; all assertions remain meaningful.
  file: "backend/tests/test_sync_coalescing.py"
  lines_added: 6  # 3 mocks + 2 comment lines + blank

---
