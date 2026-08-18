---
it_schema: 1
feature_slug: ccdash-relay-loop-resilience
title: "CCDash relay loop resilience — implementation plan"
doc_type: implementation_plan
status: completed
tier: 2
priority: P1
points: 11
risk_level: medium
context_class: C2
created: 2026-08-18
related_documents:
  - .claude/hooks context: backend/db/file_watcher.py backend/adapters/jobs/runtime.py
acceptance_criteria:
  - "AC1: sync_changed_files dispatch is wrapped in a configurable bounded timeout; a hung dispatch records a failed tick and the loop continues."
  - "AC2: FileWatcherSnapshot gains tick-level progress fields written on every tick, independent of whether classification was non-empty."
  - "AC3: the classified-changes log line renders raw/classified counts in the formatted message text, not only via logger extra=."
  - "AC4: dead_project_ids treats activity-without-progress as unhealthy and routes into the existing in-process backoff restart path; legitimately idle watchers are not flagged."
  - "AC5: per-watcher progress/staleness state is exposed via the worker/watcher probe detail reachable at /api/health/detail."
open_questions:
  - "Whether mechanism A (classify always empty) or B (hung dispatch) actually occurred cannot be determined post-hoc — AC1+AC2 cover both without needing to disambiguate."
decisions:
  - decision: "Bound the dispatch with asyncio.wait_for rather than a separate watchdog task."
    rationale: "Keeps the fix inside the existing per-tick try/except structure; no new task lifecycle to supervise."
    status: accepted
  - decision: "Self-heal restarts in-process only (existing backoff/re-registration path); never process-exit."
    rationale: "A self-exiting worker under launchd KeepAlive can crash-loop; the brief is explicit about this constraint."
    status: accepted
routing_constraints:
  - "Watcher supervisory/backoff-path correctness (M2) MUST stay claude-primary — no offload; this is the exact class of bug that caused the 44h incident."
  - "Mechanical test-writing for AC1-AC3 regression cases is offload-eligible."
required_artifacts: []
wave_plan:
  waves: [["M1"], ["M2"]]
  phases:
    - id: M1
      title: "Per-tick progress truth in the watch loop"
      depends_on: []
      exit_criteria:
        - "A stub sync_changed_files that never returns does not prevent subsequent ticks from being observed (AC1)."
        - "A tick with empty classification still advances tick-level fields while last_change_sync_at does not (AC2)."
        - "The rendered log line for 'File watcher classified changes' contains the raw and classified counts as text (AC3)."
      gate_lens: [validator]
    - id: M2
      title: "Progress-aware liveness, self-heal, and external visibility"
      depends_on: ["M1"]
      exit_criteria:
        - "inert-but-alive (ticking, zero successful dispatch, past threshold) is flagged by dead_project_ids and restarted through the existing backoff path (AC4a)."
        - "legitimately idle-and-quiet (no ticks, no pending work) is NOT flagged (AC4b)."
        - "/api/health/detail's watcher probe surfaces the new per-watcher progress/staleness fields, with an explicit fallback when absent (AC5)."
      gate_lens: [validator]
---

# Implementation Plan — CCDash relay loop resilience

```json autopilot-graph
{
  "tier": 2,
  "effort_points": 11,
  "wave_count": 2,
  "phase_count": 2,
  "file_count": 7,
  "mode_d": false,
  "mode_d_reasons": [],
  "needs_spike": false,
  "spike_reasons": [],
  "single_pass_feasible": true,
  "plan_artifact_path": "docs/project_plans/implementation_plans/harden-polish/ccdash-relay-loop-resilience-v1.md",
  "execution_target": "execute-plan",
  "slug": "ccdash-relay-loop-resilience",
  "category": "harden-polish",
  "review_intensity": "standard",
  "files_affected": [
    "backend/db/file_watcher.py",
    "backend/adapters/jobs/runtime.py",
    "backend/config.py",
    "backend/tests/test_file_watcher.py",
    "backend/tests/test_p3_watcher_registry.py",
    "backend/tests/test_reconcile_freshness.py",
    "backend/tests/test_health_detail_fields.py"
  ],
  "execution_graph": {
    "waves": [
      {
        "id": "wave-1",
        "phases": [
          {
            "id": "phase-1",
            "title": "Per-tick progress truth in the watch loop",
            "mode": "C",
            "review_intensity": "tier3",
            "tasks": [
              {
                "id": "TASK-1.1",
                "prompt": "Mode C: Autonomous implementation.\n\nRepo-relative files to change: backend/db/file_watcher.py, backend/config.py.\n\nContext: the Mac local watcher went loop-dead for ~44h after the node Postgres restarted on 2026-08-13, and nothing detected it because the watch loop never exited. Two candidate mechanisms remain unresolved and this task closes both without needing to disambiguate them.\n\nImplement, in backend/db/file_watcher.py:\n1. AC1 (bounded dispatch, covers a hung sync_changed_files on a dead pool): wrap the `await sync_engine.sync_changed_files(...)` call inside `FileWatcher._watch_loop` (around lines 227-267) in `asyncio.wait_for(..., timeout=<config flag>)`. On `asyncio.TimeoutError`, record the tick as a FAILURE (update the snapshot fields exactly as the existing `except Exception` branch does — last_change_sync_at, last_change_count, last_sync_status='failed', last_sync_error, plus a log line) and continue the loop to the next `awatch` iteration — a hung dispatch must never prevent subsequent ticks from being observed. Add a new config flag `CCDASH_WATCHER_DISPATCH_TIMEOUT_SECONDS` in backend/config.py following the existing `CCDASH_WATCHER_SYNC_CONCURRENCY` pattern (lines ~1475-1484): env-int parsed, clamped to a sane range, documented default (suggest 120s), exposed as `WATCHER_DISPATCH_TIMEOUT_SECONDS`.\n2. AC2 (per-tick progress state, covers classify-always-empty): add new fields to `FileWatcherSnapshot` (lines 41-67) written on EVERY tick regardless of whether `classified` is truthy — at minimum: a last-tick timestamp, the raw change count, the classified count, and a consecutive-ticks-without-dispatch counter that increments when classified is empty or the tick timed out, and resets to 0 on a successful dispatch. Today all four existing fields (last_change_sync_at / last_change_count / last_sync_status / last_sync_error) are written ONLY inside `if classified:` — that is precisely why an inert watcher looks identical to a healthy idle one. Add the new fields to `as_dict()` too (camelCase keys, following the existing convention).\n3. AC3 (diagnosable from its own log): change the 'File watcher classified changes' log call so the raw and classified counts appear in the RENDERED message string itself (e.g. an f-string or %-format in the message argument), not only via `extra=`. Keep the existing `extra=` dict for structured consumers.\n\nRegression tests are a separate task (TASK-1.2) — do not write them here, but make sure your field/flag names are stable so that task can target them.\n\nFILE PLACEMENT — mandatory, and not a style preference:\n  - Every path you read or write is REPO-RELATIVE (docs/project_plans/..., src/...). Never an\n    absolute path, never a leading '/Users/...' or '~/...', never a '../' that escapes the repo.\n  - You may be running inside a git worktree whose root is NOT the main checkout. cwd is already\n    the correct repo root; a relative path is therefore always right and an absolute one may\n    silently write to a DIFFERENT checkout of this same repo.\n  - If you genuinely need the root, derive it at runtime: `git rev-parse --show-toplevel`. Do not\n    hardcode it, and do not reconstruct it from a path you saw in a brief or in your own context.\n  - Report the path you wrote in repo-relative form — the downstream placement guards compare\n    against relative paths and cannot reason about an absolute one.\n\nDo NOT git add/commit/push/stash.",
                "assigned_to": "python-backend-engineer",
                "effort": 5,
                "files_affected": ["backend/db/file_watcher.py", "backend/config.py"]
              },
              {
                "id": "TASK-1.2",
                "prompt": "Mode C: Autonomous implementation (tests).\n\nRepo-relative file to change: backend/tests/test_file_watcher.py.\n\nContext: TASK-1.1 (same wave/phase) adds bounded-dispatch timeout handling, per-tick progress snapshot fields, and a rendered classified-changes log line to backend/db/file_watcher.py plus a new backend/config.py flag. Read that file's current state before writing tests — do not assume field/flag names, read them from the actual diff.\n\nWrite three regression tests in backend/tests/test_file_watcher.py:\n1. AC1: a `sync_changed_files` stub that never returns (e.g. `await asyncio.sleep(999)` or an unresolved Future) does not prevent subsequent ticks from being observed — assert the watcher's snapshot/tick counters advance past the hung tick once the configured timeout elapses (use a short timeout override for the test, not the production default).\n2. AC2: on a tick where `_classify_changes` returns an empty list, assert the new tick-level fields (last-tick timestamp, raw count, classified count, consecutive-ticks-without-dispatch counter) advance while `last_change_sync_at` does NOT change.\n3. AC3: assert the formatted log message text (via `record.getMessage()` on a captured `LogRecord`, not `record.__dict__`) contains both the raw and classified counts — a caplog fixture asserting on `caplog.records[i].getMessage()` is the correct pattern; asserting only on `record.raw_change_count` would be testing the extra= dict, not the fix.\n\nRun ONLY this named test file (per repo convention: a bare pytest sweep of backend/tests hangs during collection): `backend/.venv/bin/python -m pytest backend/tests/test_file_watcher.py -v`.\n\nDo NOT git add/commit/push/stash.",
                "assigned_to": "python-backend-engineer",
                "effort": 3,
                "files_affected": ["backend/tests/test_file_watcher.py"]
              }
            ]
          }
        ]
      },
      {
        "id": "wave-2",
        "phases": [
          {
            "id": "phase-2",
            "title": "Progress-aware liveness, self-heal, and external visibility",
            "mode": "C",
            "review_intensity": "tier3",
            "tasks": [
              {
                "id": "TASK-2.1",
                "prompt": "Mode C: Autonomous implementation.\n\nRepo-relative files to change: backend/db/file_watcher.py, backend/adapters/jobs/runtime.py, backend/config.py.\n\nPrerequisite: wave-1 (TASK-1.1) has already landed the per-tick FileWatcherSnapshot progress fields (last-tick timestamp, raw count, classified count, consecutive-ticks-without-dispatch counter) and the CCDASH_WATCHER_DISPATCH_TIMEOUT_SECONDS flag. Read the current state of backend/db/file_watcher.py before writing this task's code — do not assume exact field names.\n\nDesign constraint (verbatim from the incident brief, do not violate it): a naive 'restart if no successful sync in N minutes' watchdog thrashes every legitimately idle project. The trigger MUST be ACTIVITY WITHOUT PROGRESS — raw ticks arriving while the last successful dispatch ages past a threshold — never silence alone. Restart must go through the EXISTING in-process backoff/re-registration machinery (backend/adapters/jobs/runtime.py: the supervisor callback around lines 983-1010/1113, and the reconcile self-heal block that already calls `file_watcher_registry.dead_project_ids(expected_ids)` and re-registers, near line 1738). Never exit the process for launchd — a self-exiting worker can crash-loop.\n\nImplement:\n1. In backend/db/file_watcher.py, update `FileWatcherRegistry.dead_project_ids` (lines 481-499) to treat a project as dead when EITHER it is not running (existing behavior, keep it) OR it is running but ticking with zero/stale successful dispatch past a configurable staleness threshold (using wave-1's tick fields). Add a new config flag `CCDASH_WATCHER_STALE_AFTER_SECONDS` in backend/config.py (same pattern as CCDASH_WATCHER_SYNC_CONCURRENCY), documented default (suggest 600s = 10 minutes), and thread it into `dead_project_ids` (as a parameter with a config-sourced default, or read directly from config inside the method — prefer a parameter so the existing reconcile call site in runtime.py can pass it explicitly and tests can override it).\n2. In backend/adapters/jobs/runtime.py, update the existing reconcile self-heal call site (near line 1738, `dead = file_watcher_registry.dead_project_ids(expected_ids)`) to pass the new threshold. No new restart mechanism is needed — the existing re-registration through `file_watcher_registry.register(...)` already IS the in-process backoff path.\n3. AC5: extend `_watcher_probe_detail` (starting ~line 1354) and/or the per-project watcher registry snapshot payload so `/api/health/detail` exposes the new per-watcher progress/staleness fields (tick-without-progress counter, last successful dispatch age, staleness verdict) — follow the existing `RuntimeJobObservation` field-naming convention (checkpointAt, lastSuccessAt, staleSince, staleThresholdSeconds — see `_worker_probe_jobs` ~lines 1968-2016 for the pattern to mirror). Absent/pre-upgrade values must be an explicit `null` with a documented consumer fallback — never a silently-assumed default (resilience-by-default rule).\n\nFILE PLACEMENT — mandatory, and not a style preference:\n  - Every path you read or write is REPO-RELATIVE (docs/project_plans/..., src/...). Never an\n    absolute path, never a leading '/Users/...' or '~/...', never a '../' that escapes the repo.\n  - You may be running inside a git worktree whose root is NOT the main checkout. cwd is already\n    the correct repo root; a relative path is therefore always right and an absolute one may\n    silently write to a DIFFERENT checkout of this same repo.\n  - If you genuinely need the root, derive it at runtime: `git rev-parse --show-toplevel`. Do not\n    hardcode it, and do not reconstruct it from a path you saw in a brief or in your own context.\n  - Report the path you wrote in repo-relative form — the downstream placement guards compare\n    against relative paths and cannot reason about an absolute one.\n\nDo NOT git add/commit/push/stash.",
                "assigned_to": "python-backend-engineer",
                "effort": 5,
                "files_affected": ["backend/db/file_watcher.py", "backend/adapters/jobs/runtime.py", "backend/config.py"]
              },
              {
                "id": "TASK-2.2",
                "prompt": "Mode C: Autonomous implementation (tests).\n\nRepo-relative files to change: backend/tests/test_p3_watcher_registry.py, backend/tests/test_reconcile_freshness.py, backend/tests/test_health_detail_fields.py.\n\nContext: TASK-2.1 (same wave/phase) makes `FileWatcherRegistry.dead_project_ids` progress-aware (activity-without-progress, not mere silence, triggers dead status) and wires the reconcile self-heal call site plus /api/health/detail probe exposure. Read the current state of backend/db/file_watcher.py and backend/adapters/jobs/runtime.py before writing tests — do not assume exact field/parameter names.\n\nWrite two REQUIRED test cases for AC4 (place in test_p3_watcher_registry.py and/or test_reconcile_freshness.py, whichever already hosts dead_project_ids-style coverage):\n1. inert-but-alive: a watcher that IS ticking (raw/classified counts advancing) but has zero successful dispatch, past the configured staleness threshold — assert `dead_project_ids` flags it, and (in test_reconcile_freshness.py) that the reconcile self-heal path restarts it through the existing register()/backoff path.\n2. legitimately idle-and-quiet: a watcher with no ticks and no pending work — assert it is NOT flagged as dead.\n\nWrite one test for AC5 in backend/tests/test_health_detail_fields.py: assert `/api/health/detail`'s watcher probe payload carries the new per-watcher progress/staleness fields, and separately assert the documented null/fallback behavior when those fields are absent (e.g. a pre-upgrade snapshot shape).\n\nRun ONLY these named test files (per repo convention: a bare pytest sweep of backend/tests hangs during collection): `backend/.venv/bin/python -m pytest backend/tests/test_p3_watcher_registry.py backend/tests/test_reconcile_freshness.py backend/tests/test_health_detail_fields.py -v`.\n\nDo NOT git add/commit/push/stash.",
                "assigned_to": "python-backend-engineer",
                "effort": 3,
                "files_affected": ["backend/tests/test_p3_watcher_registry.py", "backend/tests/test_reconcile_freshness.py", "backend/tests/test_health_detail_fields.py"]
              }
            ]
          }
        ]
      }
    ]
  },
  "escalation_recommendation": "If either milestone's implementation grows beyond the estimated 8 pts during execution (e.g. dead_project_ids progress-awareness requires touching the fan-out watcher supervisor task in addition to the reconcile self-heal path), stop and re-plan wave-2 as its own Tier 2 plan rather than stretching this one — do not retrofit."
}
```

The Mac local watcher went loop-dead for ~44h after the node Postgres restart on 2026-08-13 and
nothing detected it: the loop never exited (so the existing liveness predicate never fired) while
either classification silently returned empty forever, or a dispatch hung forever on a dead pool.
When this plan lands, one hung dispatch cannot wedge a watcher forever, an inert-but-ticking
watcher is detected and restarted in-process through the existing backoff machinery, and the
staleness state is visible over HTTP without grepping a 134MB log.

## Scope boundary

**In:** `backend/db/file_watcher.py` (bounded dispatch, per-tick snapshot fields, rendered log
line, progress-aware `dead_project_ids`), `backend/adapters/jobs/runtime.py` (self-heal call site,
`/api/health/detail` watcher probe detail), `backend/config.py` (two new `CCDASH_*` flags),
matching tests under `backend/tests/`.

**Out (stated, not silently dropped):** launchd/plist changes, Docker/CI changes, any DB schema or
migration (`FileWatcherSnapshot` stays an in-memory dataclass), frontend surfacing of the new
fields, and disambiguating which of mechanism A vs B actually fired on 08-13 through 08-16 — both
are covered structurally by AC1+AC2 without needing to know which one it was.

## Rubric — what "good" looks like

The dispatch timeout and the progress-vs-activity distinction are the two load-bearing ideas; get
those right and the rest is plumbing. A reviewer should reject any design where "no successful
sync in N minutes" alone triggers a restart — that thrashes every legitimately idle project. The
correct trigger is ticks-arriving-while-last-success-ages, exactly as specified. The timeout value
and staleness threshold must be `CCDASH_*` config flags with documented defaults, not literals.
Every new snapshot/probe field follows the repo's resilience-by-default rule: absent is a contract
state with an explicit consumer fallback, never an implicit assumption.

## Named risks

- **False-positive restarts thrash idle projects.** Mitigated by requiring ticks-without-progress
  (not mere silence) before flagging — AC4b is the regression test that guards this directly.
- **A too-short dispatch timeout kills legitimately slow syncs under load.** Default should be
  generous (config-documented); this is a safety net for a *dead* pool, not a performance tuner.
- **Touching `dead_project_ids` changes behavior consumed by two call sites** (reconcile self-heal
  at `runtime.py` and the health probe) — M2 must update both consistently in one milestone rather
  than leaving one caller on the old semantics.

## References

- `backend/db/file_watcher.py:41-67` (`FileWatcherSnapshot`), `:182-280` (`_watch_loop`, the only
  place that emits succeeded/failed), `:481-499` (`dead_project_ids`)
- `backend/adapters/jobs/runtime.py:81-98` (`RuntimeJobObservation` — the pattern AC5 follows),
  `:983-1010` + `:1113` (backoff supervisor), `:1152-1153`/`:1279-1286` (per-tick retry), `:1354+`
  (`_watcher_probe_detail`), `:1738` area (reconcile self-heal call site), `:1968-2016`
  (`_worker_probe_jobs`)
- `backend/config.py:1475-1484` (existing `CCDASH_WATCHER_*` flag pattern to follow)
- Existing test homes: `backend/tests/test_file_watcher.py`, `test_p3_watcher_registry.py`,
  `test_reconcile_freshness.py`, `test_health_detail_fields.py`

## Milestones

### M1 — Per-tick progress truth in the watch loop

`_watch_loop` no longer treats "classify returned empty" and "dispatch hung forever" as
indistinguishable from healthy-idle. Every tick — regardless of whether `classified` is truthy —
writes tick-level snapshot fields (last-tick timestamp, raw count, classified count, a
consecutive-ticks-without-dispatch counter). The `sync_changed_files` call is wrapped in
`asyncio.wait_for` bounded by a new `CCDASH_WATCHER_DISPATCH_TIMEOUT_SECONDS` flag; a timeout is
recorded as a failed tick and the loop proceeds to the next `awatch` iteration. The classified-
changes log line renders raw/classified counts in the message text itself.

**AC:** AC1, AC2, AC3 (see frontmatter) — all three regression tests specified in the source
request pass.

### M2 — Progress-aware liveness, self-heal, and external visibility

`dead_project_ids` consumes M1's new tick-level fields to distinguish "ticking with no successful
dispatch past a configurable threshold" (unhealthy) from "no ticks, nothing pending" (healthy
idle) — sourced from a new `CCDASH_WATCHER_STALE_AFTER_SECONDS` flag. The reconcile self-heal call
site (already calling `dead_project_ids` and re-registering through the existing backoff path)
needs no new restart mechanism, only the updated predicate. `_watcher_probe_detail` gains the new
per-watcher fields so `/api/health/detail` exposes them, with an explicit `null`/absent fallback
documented for pre-upgrade snapshots.

**AC:** AC4, AC5 (see frontmatter).

## AC -> command -> evidence

| AC | Command | Evidence of pass |
|---|---|---|
| AC1 | `backend/.venv/bin/python -m pytest backend/tests/test_file_watcher.py -k timeout -v` | Stub `sync_changed_files` that never returns; subsequent ticks still observed (snapshot advances past the hung tick). |
| AC2 | `backend/.venv/bin/python -m pytest backend/tests/test_file_watcher.py -k progress -v` | Empty-classification tick advances new tick fields while `last_change_sync_at` stays unchanged. |
| AC3 | `backend/.venv/bin/python -m pytest backend/tests/test_file_watcher.py -k rendered -v` | Formatted log record text contains both raw and classified counts (assert on `record.getMessage()`, not `record.__dict__`). |
| AC4 | `backend/.venv/bin/python -m pytest backend/tests/test_p3_watcher_registry.py backend/tests/test_reconcile_freshness.py -k progress -v` | Two required cases: inert-but-alive past threshold IS flagged+restarted; idle-and-quiet is NOT flagged. |
| AC5 | `backend/.venv/bin/python -m pytest backend/tests/test_health_detail_fields.py -k watcher -v` | `/api/health/detail` watcher probe payload carries the new fields (or documented null fallback). |

## Sequencing (load-bearing)

M2's `dead_project_ids` progress logic and its probe exposure both read the tick-level fields M1
introduces on `FileWatcherSnapshot` — M2 cannot be written correctly before M1 lands, so the two
milestones run in sequential waves, not in parallel.

## Execution ledger

Deviations and conservative choices are logged with rationale to
`.claude/worknotes/ccdash-relay-loop-resilience/implementation-notes.md` and reviewed at each
milestone boundary. Blockers still stop: a failing test on current work, an unsatisfiable declared
artifact, exhausted recovery. Mode-D boundaries are unchanged and non-negotiable; this plan touches
none of them (no auth, payments, migrations, data deletion, secret rotation, or infra).

Execute: `/dev:execute-plan docs/project_plans/implementation_plans/harden-polish/ccdash-relay-loop-resilience-v1.md`
