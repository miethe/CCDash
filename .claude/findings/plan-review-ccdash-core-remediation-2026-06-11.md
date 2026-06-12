---
type: report
schema_version: 2
doc_type: report
report_category: plan-review
prd: ccdash-core-remediation
feature_slug: ccdash-core-remediation
title: "Plan Review — CCDash Core Remediation, Wave 4 (P3/P10/P9)"
status: completed
created: 2026-06-11
updated: 2026-06-11
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
scope_note: "Retrospective scoped to Wave 4 only (3 of 13 phases). Whole-plan review deferred until W5/W6 land."
commit_refs: [ca5a557, 9d5b29f]
---

# Plan Review — CCDash Core Remediation, Wave 4

> Scope: **Wave 4 only** (P3, P10, P9). The plan (13 phases / ~67 pts) is still `in-progress`;
> W1–W3 landed earlier, W5 (P11) and W6 (P12) remain. This review covers the three phases just executed.

## 1. Metrics snapshot (Wave 4)

| Metric | Estimated | Actual | Notes |
|--------|-----------|--------|-------|
| Story points (P3+P10+P9) | 18 pts (5+8+5) | ~18 pts core + a large unplanned P9 remediation tail | see §2 |
| Phases | 3 | 3 (all completed, reviewer-gated) | — |
| Phased commits | — | 4 (`9b3f52e` P3, `1db997c` P10, `c4e0237` P9, `db96365` review-fix) → squash `ca5a557` | + bookkeeping `9d5b29f` |
| Files changed | — | 31 | — |
| LOC | — | +11,199 / −91 | **inflated** — `docs/openapi/ccdash-v1.json` (generated) + 4 test files (~1,500 LOC of asserts) dominate; hand-written product delta is far smaller |
| Reviewer gates | 2 (scr + karen) | scr: CHANGES_REQUESTED→resolved; karen: PASS×3 | — |
| Live re-validation cycles | — | 5 compose boots (live3/live4/live5 + 2 fix passes) | each surfaced/cleared a distinct defect |

## 2. Variance analysis

**P3 (≈5 pts) — on estimate.** Clean read-only exposure across MCP/CLI/REST; the only failures were
two self-inflicted test-fixture bugs in the *new* parity tests, fixed same-cycle.

**P10 (≈5 pts) — on estimate.** Capability/CORS/optional-bearer/OpenAPI/example-client landed as scoped.
The one mid-flight issue (example client read `session_id` vs live `sessionId`) was a contract-drift
catch from the LAN smoke, not an estimation miss.

**P9 (≈8 pts) — large overrun, but mostly NOT an estimation failure.** The ~8 pts correctly sized the
*greenfield* P9 deliverables (parity governance, compose, `/readyz`, coalescing tests). The overrun came
from **latent pre-existing defects**: CCDash had **never successfully initialized its Postgres schema**,
so the convergence-gate phase had to *repair* five fatal PG/container bugs (immutable index, pgvector,
slots `_drain_task`, `Pool.transaction()`, worker project-binding) before it could *validate* anything —
plus an 8-item review-hardening round. This is **discovery / pre-existing-debt remediation**, not a bad
estimate.

## 3. Heuristic / cause attribution

| Cause | Classification (per plan-review taxonomy) | Feeds heuristic tuning? |
|-------|--------------------------------------------|-------------------------|
| 5 PG/container defects in P9 | **Discovery work / pre-existing debt** — the PG path was dead-on-arrival; the gate phase inherited the cost of every prior column-adding phase that was only ever tested on SQLite | No (not an estimation failure) — but see §4 |
| 8 review-hardening fixes | **Quality work that paid off** — closed a real LAN DB-exposure (HIGH) + timing/CORS/probe issues | No |
| 2 coalescing + 1 upgrade-path test failures | **Self-inflicted test-fixture bugs** in newly authored tests | No — process note in §5 |
| OpenAPI/LOC inflation | Measurement artifact (generated file) | No |

**The plan predicted this.** Its risk register already carried *"PG column drift (High)"* and *"PG seam
reviewer in edit-less mode misses PG-only bugs (High)"* with the mitigation *"Phase 9 Bash-enabled PG seam
review, edit-less prohibited."* The risk controls fired exactly as designed — the live gate + Bash-enabled
review caught what SQLite-only unit tests could not. The miss was not *whether* PG bugs existed but that
the **point estimate didn't price in remediating a never-initialized schema**.

## 4. Heuristic tuning proposal (single data point — surface, do not auto-apply)

> Candidate, N=1. Do not edit `estimation-heuristics.md` yet; revisit after W5/W6 add data points.

**Proposed heuristic:** *Convergence-gate / parity phases that validate prior phases on a backend those
phases never exercised at runtime should carry a **discovery multiplier (≈1.5–2×)** on top of their
greenfield estimate.* P9's true cost was ~8 pts greenfield + ~6–8 pts latent-defect remediation. A phase
whose job is "prove N prior phases work on backend X" inherits the unvalidated debt of all N.

## 5. Process gaps (feed dev-execution / delegation runbook, not estimation)

1. **SQLite-only validation upstream.** Phases 5/6/8 added columns validated only on SQLite; their PG cost
   deferred to P9. Recommend: any column-adding phase runs `compose_smoke.sh` against pgvector PG *in that
   phase*, not at the gate. (The plan's "dual DDL in the same change" rule needs a *live PG* check, not
   just DDL authoring.)
2. **New tests need a live run, not just authoring review.** All 3 test failures this wave were fixture
   bugs *in the new tests themselves* (constructor kwarg, FK seeding). Author-blind-against-live-backend
   tests carry their own bugs.
3. **macOS delegation idiom:** `nohup … & disown` (no `setsid` — absent on macOS); never `tail -f` a log
   you intend to truncate (inode-follow showed a stale verdict); on ICA gateway drop, verify-on-disk then
   re-delegate the *remainder* only.

## 6. Anchor update (for future estimates)

Add as an anchor: **"Postgres/container convergence gate for a project where PG was never runtime-validated"
→ budget ~8 pts greenfield + ~6–8 pts latent remediation + 1 review-hardening cycle = ~16 pts effective,
5 live boot/validate cycles."** Use this when any future plan has a "validate prior phases on a new
backend" gate.

## 7. Capture proposals (candidate memories)

- `gotcha`: *CCDash Postgres path was dead-on-arrival pre-Wave-4* — immutable-index (`captured_at::date`),
  missing pgvector image, slots `_drain_task`, `Pool.transaction()`, worker project-binding all had to be
  fixed before PG would boot. Any PG work must run the live compose smoke, not trust SQLite unit green.
- `learning`: *A "convergence gate" phase inherits the unvalidated debt of every phase it gates* — price a
  discovery multiplier, and push live-backend validation upstream into each contributing phase.
- `gotcha` (tooling): *macOS has no `setsid`; `tail -f` follows inodes* — see §5.3 for the delegation runbook.

## 8. Verdict

Wave 4 is **genuinely complete and reviewer-approved**, validated live on `pgvector/pgvector:pg15`. The
P9 overrun is **defensible discovery/remediation cost that the plan's own risk controls were designed to
absorb**, not an estimation-model failure. The one forward-looking change is process, not heuristic:
**move live-PG validation upstream** so the gate phase validates rather than repairs.
