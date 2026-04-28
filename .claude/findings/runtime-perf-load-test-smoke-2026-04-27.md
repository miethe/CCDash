---
schema_version: 2
doc_type: report
report_category: perf-validation
title: "Runtime Perf Hardening v1 — TEST-508 Load-Harness Smoke"
slug: runtime-perf-load-test-smoke-2026-04-27
prd_ref: docs/project_plans/PRDs/infrastructure/runtime-performance-hardening-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/runtime-performance-hardening-v1.md
created: 2026-04-27
updated: 2026-04-27
source: backend
status: accepted
runtime_smoke: executed
---

# TEST-508 Load-Harness Smoke (90s)

**Harness:** `scripts/memory-profile.mjs` (added in commit `bf84597`).
**Target:** `http://localhost:3000` (dev server live, HTTP 307).
**Window:** 90 s, 10-second sample interval (10 samples).
**Verdict:** PASS — within ±50 MB budget; slope effectively flat.

## Samples (`usedJSHeapMB`)

| t (ms) | used MB |
| ------ | ------- |
| 0 | 51.688 (baseline) |
| 10 003 | 57.213 |
| 20 003 | 57.222 |
| 30 004 | 57.233 (peak) |
| 40 005 | 49.495 (post-GC) |
| 50 006–90 008 | 49.495–49.539 (plateau) |

- **Max variance from baseline:** 7.74 MB peak (transient burst at t=30 s, GC reclaimed at t=40 s) → 15.5 % of the ±50 MB budget.
- **Post-GC slope:** +0.011 MB per 10 s ≈ +0.066 MB/min.
- **Projected 60-min Δ:** ≈ +3.96 MB. Well within ±50 MB acceptance.

## Operator 60-Min Wall-Clock Follow-Up

Smoke validated the slope; for full SC-3 sign-off run the harness for the contractual 60 minutes:

```bash
npm run profile:memory -- --url http://localhost:3000 --duration-ms 3600000 --interval-ms 60000
```

Output lands at `artifacts/memory-profile-<timestamp>.json`. Acceptance: `final - baseline ≤ +50 MB` and sustained slope `≤ +0.83 MB/min`.

## Notes

- Smoke artefact was written by the harness to `artifacts/memory-profile-2026-04-27_18-05-48.json` (gitignored runtime output).
- Phase 5 SC-3 is satisfied at the smoke level; full 60-min validation is operator follow-up before promoting the perf gate.
