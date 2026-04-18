---
schema_version: "1.0"
doc_type: meta-plan
title: "CCDash Performance & Reliability Meta-Plan v1"
status: active
created: "2026-04-17"
updated: "2026-04-17"
owner: "@nick"
tags: [meta-plan, performance, reliability, caching, sync, memory]
waves:
  - id: 1
    title: "Default Flips + N+1 Fix (low-risk wins)"
    status: planned
    items:
      - title: "Flip query TTL default to 600s (§3.3.1)"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/runtime-performance-hardening-v1.md
      - title: "Flip deferred link rebuild default OFF (§3.2.1)"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/runtime-performance-hardening-v1.md
      - title: "Batch workflow diagnostics query (§3.3.2)"
        status: planned
        artifacts:
          spec: docs/project_plans/design-specs/runtime-performance-hardening-v1.md
  - id: 2
    title: "Frontend Memory Hardening (flagged)"
    status: planned
    items:
      - title: "Transcript windowing + pagination cap (§3.1.1–3.1.2)"
        status: planned
      - title: "Polling/EventSource teardown + request-cache TTL (§3.1.3–3.1.4)"
        status: planned
  - id: 3
    title: "Perf Observability"
    status: planned
    items:
      - title: "Metrics for cache hit rate, scan timings, link-rebuild cost (§3.4)"
        status: planned
  - id: 4
    title: "Incremental Rebuild + Scan Manifest (flagged)"
    status: planned
    items:
      - title: "Incremental link rebuild (§3.2.2)"
        status: planned
      - title: "Filesystem scan manifest cache (§3.2.3)"
        status: planned
  - id: 5
    title: "Runtime + Storage Sustain Work"
    status: planned
    items:
      - title: "Deployment Runtime Mod v1 P4 Packaging + Config Contracts"
        status: in-progress
        artifacts:
          impl: docs/project_plans/implementation_plans/refactors/deployment-runtime-modularization-v1.md
      - title: "Deployment Runtime Mod v1 P5 Observability + Hosted Guardrails"
        status: in-progress
      - title: "Deployment Runtime Mod v1 P6 Validation + Rollout"
        status: in-progress
      - title: "DB Caching Layer v1 P2 Local vs enterprise storage composition"
        status: in-progress
        artifacts:
          impl: docs/project_plans/implementation_plans/db-caching-layer-v1.md
      - title: "DB Caching Layer v1 P3 Session-storage modernization"
        status: planned
      - title: "DB Caching Layer v1 P4 Migration governance + isolation verification"
        status: planned
  - id: 6
    title: "Benchmark Validation"
    status: planned
    items:
      - title: "Run PERF-G1..G5 on reference 50k-session workspace; record in reports/"
        status: planned
      - title: "Flip §3.2.2/§3.2.3 flags to default-true after soak"
        status: planned
---

# CCDash Performance & Reliability — Meta-Plan v1

A single tracker for every in-flight or planned initiative whose primary
outcome is **runtime performance, memory behavior, cold-start latency, or
operational reliability**. Meta-plans do not own implementation — they route
to the underlying PRD/spec/plan and roll up status for cross-cutting
observability.

---

## 1. Scope

**In scope**
- Backend startup latency and sync/link-rebuild cost
- Query caching, warming, and invalidation
- Frontend tab memory, DOM cost, and live-update lifecycle
- Worker/runtime separation that impacts performance
- Observability for performance (metrics, cache hit rate, scan timings)

**Out of scope** (tracked elsewhere)
- Pure feature work with no performance outcome
- Storage governance and migration compliance (tracked by
  data-platform-modularization-v1)
- CLI/MCP surface expansion (tracked by ccdash-cli-mcp-enablement-plan)

---

## 2. Initiative Roll-Up

| # | Initiative | Kind | Status | Phase / Depth | Reference |
|---|-----------|------|--------|---------------|-----------|
| 1 | Data Platform Modularization v1 | Foundation refactor | ✅ Done | All 6 phases | [plan](../implementation_plans/refactors/data-platform-modularization-v1.md) |
| 2 | Deployment Runtime Modularization v1 | Runtime separation | 🟡 In-progress | Phases 1–3 ✅, 4–6 ⏳ | [plan](../implementation_plans/refactors/deployment-runtime-modularization-v1.md) |
| 3 | DB Caching Layer v1 | Sync + query cache | 🟡 In-progress | Phase 0–1 ✅, 2–4 ⏳ | [plan](../implementation_plans/db-caching-layer-v1.md) |
| 4 | Runtime Performance Hardening v1 | Gap fixes | 🆕 Draft | Design-spec only | [spec](../design-specs/runtime-performance-hardening-v1.md) |

Status legend: ✅ done · 🟡 in-progress · 🆕 draft · 🔴 blocked · ⏸ paused.

---

## 3. Outcome Goals

| ID | Goal | Measure | Target | Owner |
|----|------|---------|--------|-------|
| PERF-G1 | Cold-start to `/api/project-status` p95 | Reference 50k-session project, defaults applied | < 500 ms | Initiative 3 + 4 |
| PERF-G2 | Idle-hour tab memory growth | Chrome tab RSS delta over 60 min idle | < 50 MB | Initiative 4 |
| PERF-G3 | Query cache hit rate (steady-state) | Cache hits / total cached-endpoint requests | ≥ 95 % | Initiative 3 + 4 |
| PERF-G4 | Link-rebuild cost per boot | Cumulative link-rebuild wall time during startup | < 3 s on reference workspace | Initiative 4 |
| PERF-G5 | Live-update teardown correctness | Manual disconnect: no fetches within 30s of probe-down | 0 polls | Initiative 4 |

---

## 4. Phase Status per Initiative

### 4.1 Data Platform Modularization v1 — ✅ Done

| Phase | Status | Notes |
|-------|--------|-------|
| P1 Storage Profile Capability Contract | ✅ | |
| P2 Adapter Composition + UoW Split | ✅ | |
| P3 Domain Ownership + Schema Layout | ✅ | |
| P4 Identity, Membership, Audit Foundation | ✅ | |
| P5 Migration Governance + Sync Boundary Refactor | ✅ | |
| P6 Rollout, Validation, Handoff | ✅ | |

### 4.2 Deployment Runtime Modularization v1 — 🟡 Phases 1–3

| Phase | Status | Notes |
|-------|--------|-------|
| P1 Runtime Contract + Launch Surface | ✅ | |
| P2 Worker Ownership + Job Routing | ✅ | |
| P3 Health, Readiness, Degradation | ✅ | Commits a6cd153, 0f36c24, 0c050f8 |
| P4 Packaging + Configuration Contracts | ⏳ | In-progress |
| P5 Observability + Hosted Safety Guardrails | ⏳ | In-progress |
| P6 Validation, Documentation, Rollout | ⏳ | In-progress |

### 4.3 DB Caching Layer v1 — 🟡 Phase 0–1

| Phase | Status | Notes |
|-------|--------|-------|
| P0 Baseline (runtime profiles, migrations) | ✅ | |
| P1 Sync engine + TTL query cache + entity links | ✅ | Shipped; `CCDASH_QUERY_CACHE_TTL_SECONDS`, `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS` |
| P2 Local vs enterprise storage composition | ⏳ | Partial via profiles; router migration outstanding |
| P3 Session-storage modernization (canonical `session_messages`) | ⏳ | Seams exist; table design deferred |
| P4 Migration governance + shared-Postgres isolation verification | ⏳ | Partial |

### 4.4 Runtime Performance Hardening v1 — 🆕 Draft

| Track | Spec §  | Status | Owner |
|-------|---------|--------|-------|
| Frontend transcript windowing + pagination cap | §3.1.1–3.1.2 | 🆕 | TBD |
| Polling/EventSource teardown + request-cache TTL | §3.1.3–3.1.4 | 🆕 | TBD |
| Default flip: deferred rebuild off | §3.2.1 | 🆕 | TBD |
| Incremental link rebuild | §3.2.2 | 🆕 | TBD |
| Filesystem scan manifest cache | §3.2.3 | 🆕 | TBD |
| Default flip: query TTL 600s | §3.3.1 | 🆕 | TBD |
| Workflow diagnostics batching (N+1 fix) | §3.3.2 | 🆕 | TBD |
| Perf observability additions | §3.4 | 🆕 | TBD |

---

## 5. Operator-Visible Symptom Ownership

| Symptom | Owning initiative(s) | Short-term workaround |
|---------|---------------------|-----------------------|
| Browser tab grows to 2GB+ on long-running sessions | 4 | Close + reopen tab; disable `VITE_CCDASH_LIVE_SESSION_TRANSCRIPT_APPEND_ENABLED` |
| Startup feels slow; backend not immediately operational | 3 (warming) + 4 (scan cache, deferred-off default) | Set `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS=false`; run `npm run dev:worker` |
| Cache-warm misses produce cold queries every few minutes | 3 (TTL tuning) + 4 (default flip) | Set `CCDASH_QUERY_CACHE_TTL_SECONDS=600` |
| Routine re-syncs and link rebuilds on unchanged data | 3 (P2/P3) + 4 (incremental rebuild) | Keep `CCDASH_LINKING_LOGIC_VERSION=1`; ensure worker is running |
| Workflow diagnostics slow on large registries | 4 (§3.3.2) | No supported workaround; wait for batch query |

Cross-ref: the operator-facing knobs listed here are all documented in
[`docs/setup-user-guide.md`](../../setup-user-guide.md) under **Performance
Tuning Quick Start**.

---

## 6. Dependencies + Sequencing

```
data-platform-modularization-v1 (done)
        │
        ├─► deployment-runtime-modularization-v1  ──► worker runtime enables cache warming
        │
        └─► db-caching-layer-v1 ──► provides TTL cache + sync engine
                                        │
                                        └─► runtime-performance-hardening-v1
                                              consumes both; ships default flips,
                                              incremental rebuild, memory guards
```

- Initiative 4 assumes Initiative 2 Phase 3 is merged (worker readiness
  probes exist) — ✅ satisfied.
- Initiative 4 default flips must be gated on DB Caching Layer P1 — ✅
  satisfied.
- Initiative 4 incremental rebuild requires the entity-links repository from
  DB Caching Layer P1 — ✅ satisfied.

---

## 7. Review Cadence

- **Weekly**: update the Phase Status tables above; note any initiative
  moving between 🟡 / ⏸ / 🔴.
- **Per-release**: re-run the PERF-G1…G5 benchmarks on the reference
  workspace and record results in `docs/project_plans/reports/`.
- **Quarterly**: decide whether to spin a v2 meta-plan (new goals, retired
  initiatives).

---

## 8. Entry Points

- Add a new performance initiative → append to §2 and §4, then link its
  PRD/spec/plan.
- Retire an initiative → mark ✅ in §2/§4 and move to the "Completed"
  appendix of a future v2.
- Change a PERF-G target → record rationale inline; don't silently edit.

---

## 9. Recommended Execution Phasing

Sequenced across the four initiatives so the highest-leverage, lowest-risk
moves land first and so later structural changes are backed by measurement.
Each wave corresponds to the `waves:` frontmatter block and is pickable by
`plan-status` Route 8 (`Ready to Implement`).

### Wave 1 — Default flips + N+1 fix _(1–2 days, low risk)_

All prerequisites satisfied (DB Caching P1 shipped; worker readiness probes
exist). These are the cheapest wins against PERF-G1 and PERF-G3.

- **§3.3.1** — flip `CCDASH_QUERY_CACHE_TTL_SECONDS` default `60 → 600`.
  Deprecation note in `setup-user-guide.md`.
- **§3.2.1** — flip `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS` default
  `true → false`; worker now owns rebuilds.
- **§3.3.2** — replace the per-workflow diagnostics query with a batched
  fetch; straight code change gated only by unit/integration tests.

**Gate to Wave 2**: benchmarks + smoke on reference workspace show cold-start
p95 improvement and no regression in cache hit rate.

### Wave 2 — Frontend memory hardening _(behind flag, parallelizable with Wave 3)_

Targets PERF-G2 and PERF-G5. Can run in parallel with Wave 3 since it touches
a different surface.

- **§3.1.1–3.1.2** — transcript windowing + pagination cap, behind
  `VITE_CCDASH_MEMORY_GUARD_ENABLED=true` by default on new tabs.
- **§3.1.3–3.1.4** — polling/EventSource teardown when probe-down; request-
  cache TTL for idle tabs.

**Gate to Wave 4**: 60-min idle tab memory delta < 50 MB on reference
workspace; no polls within 30s of probe-down (manual disconnect test).

### Wave 3 — Perf observability _(prerequisite for Wave 4 measurement)_

Ship the metrics in **§3.4** (cache hit rate, scan timings, link-rebuild
cost, deferred-rebuild duration). Without this, Wave 4's soak cannot be
evaluated against PERF-G3/G4.

### Wave 4 — Incremental rebuild + scan manifest _(flagged, needs Wave 3 telemetry)_

Targets PERF-G4 directly.

- **§3.2.2** — incremental link rebuild via `EntityLinksRepository`
  scope resolver, behind `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED=false`.
- **§3.2.3** — filesystem scan manifest cache, same flag.

**Soak**: one minor-version window with flag on in a dev profile; flip to
`true` default in Wave 6 after PERF-G4 < 3 s is sustained.

### Wave 5 — Runtime + storage sustain work _(parallel, unblocks hosted/enterprise)_

Runs throughout Waves 1–4 on a separate track; required for parity with
hosted/enterprise but not blocking local perf wins.

- **Initiative 2** (Deployment Runtime Mod v1): complete P4 Packaging +
  Config Contracts, P5 Observability + Hosted Guardrails, P6 Validation +
  Rollout.
- **Initiative 3** (DB Caching Layer v1): complete P2 (router migration to
  storage profiles), then P3 (`session_messages` canonicalization), then P4
  (migration governance + shared-Postgres isolation verification).

**Sequencing note**: Initiative 3 P3 depends on Initiative 2 P4 landing so
that session-storage tables can be owned by the correct runtime profile.

### Wave 6 — Benchmark validation + default-on flip

- Re-run PERF-G1…G5 on the reference 50k-session workspace; record results
  in `docs/project_plans/reports/`.
- Flip Wave 4 flags to default-on after soak.
- Close initiative 4; decide whether to spin a v2 meta-plan per §7.

### Sequencing summary

```
Wave 1 ─┐
        ├─► Wave 3 ─► Wave 4 ─┐
Wave 2 ─┘                     ├─► Wave 6
          Wave 5 (parallel) ──┘
```

---

## Appendix A — Referenced Knobs

All performance-relevant env vars are listed in
[`docs/setup-user-guide.md`](../../setup-user-guide.md) §Full Configuration
Reference. The subset that directly backs this meta-plan:

- `CCDASH_QUERY_CACHE_TTL_SECONDS`
- `CCDASH_QUERY_CACHE_REFRESH_INTERVAL_SECONDS`
- `CCDASH_STARTUP_SYNC_LIGHT_MODE`
- `CCDASH_STARTUP_DEFERRED_REBUILD_LINKS`
- `CCDASH_STARTUP_DEFERRED_REBUILD_DELAY_SECONDS`
- `CCDASH_LINKING_LOGIC_VERSION`
- `CCDASH_SQLITE_BUSY_TIMEOUT_MS`
- `VITE_CCDASH_LIVE_SESSION_TRANSCRIPT_APPEND_ENABLED`
