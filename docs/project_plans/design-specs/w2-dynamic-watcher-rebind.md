---
schema_version: 2
doc_type: design_spec
title: "D-002: W2 Dynamic Watcher Rebind — Hot-Reload Signaling Design"
status: draft
maturity: shaping
created: 2026-06-14
updated: 2026-06-14
feature_slug: ccdash-runtime-deploy-remediation
feature_version: v1
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-runtime-deploy-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-runtime-deploy-remediation-v1.md
spike_ref: .claude/worknotes/ccdash-runtime-deploy-remediation/w2-watcher-fanout-design.md
adr_refs:
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
  - docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md
audience: developers
tags:
  - watcher
  - worker-watch
  - hot-reload
  - ipc
  - dynamic-rebind
  - deferred
  - design-spec
category: backend-infrastructure
priority: low
risk_level: medium
effort_estimate: ~8–13 pts (SPIKE + implementation)
deferred_from: ccdash-runtime-deploy-remediation-v1 (P3 / T3-004 scope cut)
deferred_reason: >
  Full hot-reload signaling requires inter-process coordination between the API process
  and the worker-watch process. P3 shipped a 60-second periodic reconcile loop as the
  pragmatic in-scope solution. The sub-second push mechanism was not designed in that
  epic and is tracked here.
promotion_trigger: >
  Registry churn exceeds 1 change/hour in production (measured via watcher reconcile
  loop logs), OR an operator explicitly requests hot-reload without a service restart.
open_questions:
  - "OQ-D002-1: Should the signaling channel be per-process-pair (API → worker-watch)
    or broadcast (supporting future N-worker deployments)? Answer affects whether a
    pub/sub model or a point-to-point IPC socket is the right primitive."
  - "OQ-D002-2: If the API process crashes between writing a sentinel file and the
    watcher consuming it, how is the sentinel cleaned up? Is a PID-tagged sentinel
    with stale-sentinel GC the right answer, or does a DB-side 'pending rebind' flag
    survive crashes more reliably?"
  - "OQ-D002-3: Should the watcher-side consumer be edge-triggered (signal fires once,
    watcher re-reads registry once) or level-triggered (watcher polls the event source
    until it has ACKed all pending changes)? Level-triggered is more robust to dropped
    signals but requires idempotent ACK bookkeeping."
  - "OQ-D002-4: What is the maximum tolerable rebind latency for operators who report
    churn >1 change/hour? Is 5 seconds acceptable, or is sub-second a hard requirement
    that would mandate a Unix domain socket over a sentinel file?"
related_documents:
  - .claude/worknotes/ccdash-runtime-deploy-remediation/w2-watcher-fanout-design.md
  - docs/project_plans/implementation_plans/enhancements/ccdash-runtime-deploy-remediation-v1.md
  - docs/project_plans/design-specs/container-project-onboarding-and-watchers-v1.md
---

# D-002: W2 Dynamic Watcher Rebind — Hot-Reload Signaling Design

This document specifies the deferred sub-second registry-change signaling design for the
CCDash worker-watch process. It exists because P3 of the Runtime & Deploy Remediation epic
shipped a 60-second periodic reconcile loop as the pragmatic in-scope solution and explicitly
deferred the full hot-reload push mechanism to this spec.

---

## 1. Current State: The Reconcile-Loop Limitation

P3 (T3-004) shipped a periodic reconcile loop inside the `worker-watch` runtime profile.
On each tick the worker calls `workspace_registry.list_projects()`, diffs the result against
the active `WatcherBinding` set, and idempotently adds or removes bindings. The tick interval
is controlled by `CCDASH_WATCHER_RECONCILE_INTERVAL_SECONDS` (default **60 s**, min 10 s,
max 3600 s).

### What works

- New projects added via `ccdash project add` are picked up within the next reconcile tick
  (worst-case latency: 60 s).
- Removed or de-registered projects are shed within the same window.
- No inter-process coordination is required; the watcher owns its own polling loop.
- One bad reconcile tick (e.g., a DB read failure) logs a warning and reschedules the
  next tick without crashing the loop or any sibling project binding.

### What does not work

**Up-to-60-second lag.** An operator who adds a project and immediately wants to verify that
sessions are being ingested must wait up to 60 seconds before the watcher notices the new
project and begins watching its paths. In a long-running background service this is often
acceptable, but it is observable and can confuse operators who expect near-instant pickup.

**No operator-triggered refresh.** There is no CLI command or API endpoint that forces the
watcher to re-read the registry immediately. The only way to force an instant rebind today
is `docker restart worker-watch` (or equivalent), which is disruptive and resets all
in-progress per-project sync state.

**Scale concern.** If registry churn becomes frequent (>1 change/hour), every 60-second
tick does a DB read that may be a no-op most of the time. While the read is cheap, the
pattern does not scale gracefully to environments where registry changes are frequent
enough that "next tick" is meaningfully different from "right now."

---

## 2. Target State

The target state (when D-002 is promoted) is a **sub-second push notification** from the
API process to the worker-watch process whenever the project registry changes. The worker
receives the signal, re-reads the registry once, and updates its binding set within a
single event-loop iteration. The 60-second reconcile loop remains as a safety net for
signals that are dropped or for deployments that do not configure the push channel.

**Latency target**: registry change → watcher rebind in ≤ 5 seconds (signal propagation
+ one asyncio event-loop pass). Sub-second is preferred; 5 s is the acceptance bound.

**Backward-compatibility requirement**: Deployments that do not configure the hot-reload
channel continue to use the 60-second reconcile loop unmodified. The hot-reload channel
is additive, not a replacement.

---

## 3. Signaling Design Options

Three candidate approaches are evaluated below. All three assume:

- The API process and the worker-watch process are on the same host (or share a common
  volume, as in the current Compose stack).
- The signal is advisory: the receiver re-reads the full registry from the DB after
  receiving the signal rather than trusting the signal payload. This keeps the DB as
  the authoritative source (ADR-006) and avoids serialization format lock-in.

---

### Option A: Shared In-Memory Event Bus (asyncio Queue / asyncio.Event)

**Mechanism**: A shared `asyncio.Queue` or `asyncio.Event` object is passed by reference
between the API process coroutines and the watcher loop coroutines when both run in the
same process (i.e., under the `local` runtime profile where API + worker share one
Python process). The project-registry write path calls `event.set()` after a successful
`workspace_registry.upsert()`. The watcher reconcile loop `await`s the event and
re-reads the registry immediately on wake.

**Applicability**: Applies **only** when API and watcher run in the same process
(local profile or `main.py`). Does not apply to the enterprise Compose stack where
API (`api` container) and watcher (`worker-watch` container) are separate processes.

**Pros**:
- Zero IPC overhead — shared memory within one process.
- Purely asyncio primitives; no external deps.
- Sub-millisecond latency.

**Cons**:
- Does not solve the production (multi-process, multi-container) case at all.
- Requires the API write path to hold a direct reference to the watcher subsystem,
  creating a layering violation: routers/services would need to reach into runtime
  infrastructure to fire the event.
- Fragile when components are reorganized (event reference can become stale or None).

**Verdict**: Suitable as a local-profile optimization if the layering concern is
addressed via a dependency-injected `WatcherSignalBus` interface. Not sufficient as
the sole mechanism. Should be Option A of a two-track design alongside Option B or C.

---

### Option B: Filesystem Sentinel File

**Mechanism**: A sentinel file is written to a well-known path (e.g.,
`/tmp/ccdash/rebind.trigger` or a path under `CCDASH_DATA_DIR`) by the API process
after every successful project-registry write. The worker-watch process uses its
existing `watchfiles` subscription to observe changes to the sentinel file's parent
directory, or polls the file's `mtime` on each reconcile tick (a "fast-path" check
before the 60-second wall-clock check).

**Variants**:
- *Variant B1 — Sentinel file polled on reconcile tick*: The reconcile loop checks
  `mtime(sentinel)` at the start of each tick. If `mtime > last_seen_mtime`, trigger
  an immediate registry re-read and update `last_seen_mtime`. The tick timer resets.
  Worst-case latency is still 60 seconds (if the sentinel is written just after a tick
  completes), but typical latency is O(seconds) if ticks run frequently or if the
  interval is reduced.
- *Variant B2 — Sentinel file watched via watchfiles*: The watcher adds the sentinel
  file's parent directory to its `watchfiles` subscription. A write to the sentinel
  fires an `awatch` event on the watcher side, which immediately triggers a registry
  re-read outside the normal reconcile tick. Worst-case latency is < 1 second.

**Sentinel file content**: An empty file, or a JSON payload containing
`{"written_at": "<iso8601>", "written_by_pid": <pid>}`. Content is advisory and
not parsed for registry data — the watcher always re-reads from the DB.

**Pros**:
- Works across process boundaries including separate containers that share a volume
  (all current Compose profiles mount a shared `data/` volume).
- No new infrastructure dependency.
- Transparent to operators — they can touch the sentinel file manually to force a
  rebind without a code path.
- Variant B2 achieves sub-second latency using the watcher's existing `watchfiles`
  loop — no additional polling is required.

**Cons**:
- Filesystem dependency: if the shared volume is unavailable, the signal is dropped.
  The reconcile loop is the fallback in this case (acceptable).
- Stale sentinel files survive process crashes. A stale sentinel (written by a
  previous API process that crashed) may trigger a spurious rebind on the next
  watcher startup. Spurious resyncs are idempotent and harmless.
- Containers that do not share a volume (e.g., API and watcher on separate hosts)
  cannot use this mechanism — the 60-second reconcile loop is the only option there.
- Variant B1 does not improve worst-case latency; Variant B2 is preferred.

**Verdict**: Recommended for the initial D-002 implementation (Variant B2). It is the
simplest multi-process mechanism consistent with the existing Compose volume topology,
requires no new infrastructure, and achieves sub-second latency. A fallback to the
reconcile loop handles all sentinel-unavailable cases without operator intervention.

---

### Option C: Inter-Process Socket (Unix Domain Socket or Named Pipe)

**Mechanism**: The watcher process opens a Unix domain socket listener at a well-known
path (e.g., `{CCDASH_DATA_DIR}/rebind.sock`). The API process connects to the socket
after each project-registry write and sends a minimal payload (`{"op": "rebind"}`).
The watcher receives the message, triggers a registry re-read, and ACKs with
`{"status": "accepted"}`. Connection is short-lived (connect → send → receive ACK →
close).

**Pros**:
- Bidirectional: the API can receive a confirmation that the watcher processed the
  signal (the 60-second reconcile loop provides no such confirmation).
- Sub-millisecond to sub-second latency (local socket, no filesystem I/O beyond
  the socket descriptor).
- Explicit ACK enables the API to surface "watcher rebind confirmed" in the health
  endpoint or in the `ccdash project add` CLI output.
- Clean abstraction: the watcher exposes a control-plane interface that can later be
  extended (e.g., `{"op": "reload-config"}`, `{"op": "status"}`).

**Cons**:
- Socket file must be cleaned up on process exit. A stale socket file from a crashed
  watcher will cause the API's connect attempt to fail (ECONNREFUSED) — the API must
  handle this gracefully (treat as "watcher not available; sentinel fallback").
- Adds a new operational concern: socket path must be writable by both processes;
  SELinux / AppArmor profiles may need updating in hardened deployments.
- More complex to implement than the sentinel file: the watcher needs an asyncio
  socket server task; the API needs a short-lived asyncio client connection.
- Does not work across separate hosts (same limitation as Option B).

**Verdict**: The cleanest long-term architecture, especially if a watcher control-plane
interface (health, force-rebind, status) becomes a desired operator feature. Complexity
is justified only after Option B has been shipped and operators request the ACK feedback
loop or explicit control-plane tooling. Recommend as **Phase 2 of D-002 promotion**,
not the initial implementation.

---

## 4. Recommended Approach

### Short term (D-002 initial promotion)

Implement **Option B, Variant B2**: sentinel file watched via `watchfiles`.

Implementation sketch:

1. Define `CCDASH_WATCHER_REBIND_SENTINEL_PATH` (default:
   `{CCDASH_DATA_DIR}/rebind.trigger`). Document in `backend/config.py`.
2. In the project-registry write path (`workspace_registry.upsert()` /
   `workspace_registry.delete()`), call a side-channel helper
   `_write_rebind_sentinel(path)` after a successful DB commit. The helper writes
   the sentinel with a timestamp payload. The helper is fail-open: any I/O error is
   logged at WARN, not raised (write failure must not abort the registry mutation).
3. In the `worker-watch` runtime startup, add the sentinel file's parent directory
   to the `watchfiles` subscription. On a change event matching the sentinel filename,
   call `_trigger_reconcile_immediately()` outside the normal tick timer.
4. The 60-second reconcile loop remains unchanged as a safety net.
5. A new config var `CCDASH_WATCHER_REBIND_SIGNAL_ENABLED` (default **false** on
   initial rollout; promote to **true** as default after one release cycle confirms
   stability).

### Medium term (if confirmed required)

If operators confirm the ACK feedback loop is needed (e.g., `ccdash project add` should
report "watcher confirmed rebind") or if a watcher control-plane is desired for
operational tooling (force-rebind, status), promote to **Option C** (Unix domain
socket) as a follow-on epic.

### Never-needed paths

Option A (shared asyncio event bus) should only be wired for the `local` runtime profile
as a micro-optimization if profiling shows the reconcile-loop latency matters there.
It is not a substitute for B or C in production.

---

## 5. Promotion Trigger

D-002 is promoted from deferred to planned when **either** of the following conditions
is met:

1. **Registry churn threshold**: watcher reconcile-loop logs (field `reconcile_new_count`
   or `reconcile_removed_count` on the structured log line emitted after each tick) show
   an average of more than **1 binding change per hour** over a 7-day window in any
   operator-reported production deployment.

2. **Operator request**: an operator explicitly opens an issue or feature request stating
   that the 60-second rebind lag is causing operational friction and requesting hot-reload
   without a service restart.

Neither condition has been observed at the time of this spec's authoring (2026-06-14).
The 60-second reconcile loop shipped in P3 is sufficient for all known current deployments.

---

## 6. Effort Estimate (if Promoted)

| Phase | Work | Estimate |
|-------|------|----------|
| SPIKE | Resolve OQ-D002-1 through OQ-D002-4; confirm Variant B2 vs Option C | 2 pt |
| BE — sentinel write path | `_write_rebind_sentinel()` helper in write path; config var | 1.5 pt |
| BE — watcher subscription extension | Add sentinel directory to watchfiles; `_trigger_reconcile_immediately()` | 2 pt |
| BE — config + docs | `CCDASH_WATCHER_REBIND_SENTINEL_PATH`, `CCDASH_WATCHER_REBIND_SIGNAL_ENABLED`; operator guide update | 1 pt |
| Tests | Unit: sentinel written after registry upsert; watcher fires immediate reconcile on sentinel change; fail-open behavior on I/O error | 2 pt |
| Smoke | `docker:livewatch:up`; `ccdash project add` second project; observe watcher picks up in <5 s | 0.5 pt |
| **Total** | | **~9–13 pt** |

Option C (Unix domain socket) adds an estimated 4–6 pt on top of the Option B
implementation (socket server/client setup, ACK protocol, stale-socket GC).

---

## 7. Non-Goals of this Spec

- Multi-host deployments (API and watcher on separate machines): the 60-second
  reconcile loop remains the only mechanism; no networking layer is designed here.
- N-watcher horizontal scaling (D-003): each watcher instance would independently
  read the sentinel or socket; coordination between watchers is a D-003 concern.
- Watcher restart / crash recovery signaling: the reconcile loop handles this already
  by re-reading the registry on each tick after a restart.
- Frontend visibility of "rebind in progress": the per-project health map
  (`/api/health/detail` `watcher.projects`) already surfaces state transitions;
  no new FE surface is required.
