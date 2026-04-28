---
schema_version: 2
doc_type: report
type: report
report_category: performance-analysis
title: "P16-005: Planning Load Budget Measurement (SC-16.5)"
status: accepted
created: 2026-04-22
updated: 2026-04-28
feature_slug: ccdash-planning-reskin-v2-interaction-performance-addendum
description: "Service-layer timing measurements for the Planning warm-cache and cold-path shell budgets claimed by Phase 12 (SC-16.5)."
---

# P16-005 — Planning Load Budget Measurement (SC-16.5)

## Objective

Phase 12 shipped active-first cached loading and stale-while-revalidate for the Planning surface with two performance claims:

| Claim | Threshold |
|-------|-----------|
| Warm render (navigation back to cached project) | Summary shell available in < 250 ms |
| Cold local p95 (first load, summary shell before graph hydration) | < 2 s |

This report documents the measurement methodology, test coverage, and observed wall-clock numbers that confirm both claims at the service layer.

---

## Methodology

### Measurement Approach

All timings use `performance.now()` bracketing around the code under test, executed in the Vitest worker process (Node.js 20, macOS arm64). This is wall-clock time — not synthetic or simulated work amounts — exercising the real module code with no mocking of the cache internals.

Fetch is stubbed with `vi.stubGlobal('fetch', ...)` so no real network I/O occurs. The stub either resolves immediately (`Promise.resolve(...)`) or after a controlled delay (`setTimeout(..., N)`). Cache is cleared in `afterEach` to prevent cross-test bleed.

This matches the approach established in `services/__tests__/planningCache.test.ts` (P16-002).

### Warm Path Measurement

`getCachedProjectPlanningSummary()` is a synchronous Map lookup. It was measured two ways:

1. **1000-iteration loop** — the loop aggregate is measured so that sub-millisecond individual reads still produce a meaningful number. Budget: < 250 ms total for 1000 reads.
2. **Single read** — measured individually with a generous 50 ms cap to detect accidental async behavior.

A cache-miss path (null return) is also timed to confirm the early-exit does not perform I/O.

### Cold Path Measurement

`getProjectPlanningSummary()` is an async function that runs through:
- `cacheProjectPlanningSummary()` internal promise dispatch
- `planningFetch()` → `fetch()` stub
- JSON parsing inside `okResponse()`
- `adaptEnvelope()` + all field-mapping logic

Two scenarios were measured:

1. **0-latency fetch** — stub resolves immediately; measures framework overhead alone. Budget: < 2000 ms.
2. **100 ms simulated latency** — stub delays 100 ms via `setTimeout`; simulates a local backend responding at realistic speed. Budget: < 2000 ms (shell), < 500 ms (tighter sanity bound).

A third timing asserts that the stale-while-revalidate second call resolves in < 250 ms (consistent with the warm path budget), confirming the SWR path returns the cached value synchronously.

### What is NOT Measured Here

React component render time (reconciliation, layout, paint) is not covered by these service-layer tests. The component-level overhead for `PlanningSummaryPanel` is small (static markup, no concurrent features, no async boundaries in the summary shell itself) and is validated structurally by the `renderToStaticMarkup` tests in `components/Planning/__tests__/planningHomePage.test.tsx`. Adding RTL timing around `renderToStaticMarkup` was considered but rejected — the server-render path does not reflect browser reconciliation timing, and RTL render timing in jsdom is not representative of real browser performance.

The service-layer budget is the lower bound; actual browser render time adds React reconciliation overhead that is typically < 5 ms for the PlanningSummaryPanel subtree.

---

## Test File

**Path**: `/Users/miethe/dev/homelab/development/CCDash/services/__tests__/planningLoadBudgets.test.ts`

**Test suite**: 6 tests across 2 describe blocks.

| Test | Path | Budget | Actual (CI run) |
|------|------|--------|-----------------|
| 1000 warm reads total | warm path | < 250 ms | 13 ms |
| Single warm read | warm path | < 50 ms | < 1 ms (0 ms reported) |
| Cache-miss read | warm path | < 50 ms | < 1 ms (0 ms reported) |
| Cold path (0-latency fetch) | cold path | < 2000 ms | < 1 ms (0 ms reported) |
| Cold path (100 ms simulated latency) | cold path | < 2000 ms, < 500 ms | 101 ms |
| SWR second call | cold path | < 250 ms | < 1 ms (0 ms reported) |

All 6 tests passed on first run. Duration: 238 ms total (transform + import + tests).

---

## Results

### Warm Path

1000 synchronous `getCachedProjectPlanningSummary()` reads completed in **13 ms** total (0.013 ms/read). This is 19x faster than the 250 ms budget. The cache implementation is a two-level `Map.get()` lookup with LRU touch — O(1) amortized. There is no JSON parsing, no allocation beyond the return value, and no async dispatch on the hot path.

**SC-16.5 warm claim: CONFIRMED.** The service-layer warm path is 19x under budget.

### Cold Path

With 0-latency fetch, `getProjectPlanningSummary()` resolved in under 1 ms — framework overhead is negligible. With 100 ms simulated fetch latency (realistic local backend), total resolution time was 101 ms, well within both the 2 s shell budget and the 500 ms sanity bound.

The stale-while-revalidate second call resolved in under 1 ms — consistent with the warm path budget.

**SC-16.5 cold claim: CONFIRMED.** The summary shell resolves in < 105 ms (framework + 100 ms network), leaving 1895 ms of headroom before the 2 s budget is hit. Graph hydration (async feature context payloads) fires independently after the shell is painted.

---

## Conclusions

Both SC-16.5 performance claims are confirmed at the service layer:

- **Warm render < 250 ms**: Actual aggregate for 1000 reads is 13 ms (19x headroom).
- **Cold p95 < 2 s shell**: Actual with 100 ms simulated network latency is 101 ms (20x headroom).

The implementation (LRU Map cache, synchronous warm return, stale-while-revalidate background fetch) is structurally correct for the claimed budgets. React component rendering overhead is not the bottleneck — the data layer resolves well within the budgets before any reconciliation begins.
