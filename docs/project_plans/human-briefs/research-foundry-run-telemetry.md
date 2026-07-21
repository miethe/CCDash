---
schema_name: ccdash_document
schema_version: 2

doc_type: human_brief
doc_subtype: "feature_brief"
root_kind: project_plans

id: "BRIEF-research-foundry-run-telemetry"
title: "Research Foundry Run Telemetry in CCDash — Human Brief"
status: draft
category: human-briefs

feature_slug: "research-foundry-run-telemetry"
feature_family: "research-foundry-run-telemetry"
feature_version: "v1"

prd_ref: "docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md"
plan_ref: "docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md"
intent_ref: ""
epic_ref: ""

related_documents:
  - docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-feasibility-brief.md
  - docs/project_plans/exploration/research-foundry-run-telemetry/research-foundry-run-telemetry-charter.md
  - .claude/worknotes/research-foundry-run-telemetry/decisions-block.md
  - docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md

owner: ""
contributors: []

audience: [humans]

priority: medium
confidence: 0.78

created: "2026-07-21"
updated: "2026-07-21"
target_release: ""

tags: [human-brief, research-foundry, telemetry, ingest, analytics]
---

# Research Foundry Run Telemetry in CCDash — Human Brief

> Living document for human orchestrators. Agents: do not load unless explicitly instructed.
> Status: draft | Updated: 2026-07-21

---

## 1. Context Pointers

- **PRD**: `docs/project_plans/PRDs/features/research-foundry-run-telemetry-v1.md`
- **Plan**: `docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md`
- **Design Specs**: None yet — 7 will be authored in Phase 4 (DF-001–DF-007, see §5)
- **SPIKEs**: None (Tier-3 SPIKE gate satisfied by the exploration bundle — 4 spikes at `docs/project_plans/exploration/research-foundry-run-telemetry/spikes/`)
- **Related Briefs**: None

---

## 2. Estimation Sanity Check

**Bottom-up total**: 31 pts / ~4–6 engineer-weeks
**Top-down anchor**: Decisions-block anchor (Opus-authored, pre-expansion) was 26 pts
**Reconciliation**: Bottom-up came in +19% over the decisions-block anchor. Trusting bottom-up per
heuristics policy — the delta is fully accounted for by two categories the anchor priced as bundled
line items rather than itemized tasks: (1) 7 separate DOC-006 deferred-spec tasks (3.5 pts) instead
of one ~1–1.5 pt "deferred specs" line, because the PRD explicitly names 7 distinct out-of-scope
panels and the Plan Generator Rules require one spec-authoring task per item; (2) explicit
reviewer/seam gate tasks — `task-completion-validator` ×4, `karen` ×2, one seam task — totaling 3.5
pts that the decisions block's phase-level anchors didn't itemize as separate line items. +19% is
within the ±30% H5 tolerance band, so no re-derivation was required, but it's worth flagging that
"3 pts for hardening" undercounts when a PRD names 7 explicit deferred panels.

**H1 (noun-counting)**: 2 new domain nouns.
- `research_runs`: full first-class entity with REST/MCP/CLI read API → ~2 pt floor.
- `rf_events`: raw append-only log, no direct CRUD API (health-tracked and rollup-derived only) → treated as the "audit/log table" exception, ~0.5 pt floor.
- H1 floor: ~2.5 pts. Actual allocated (T1-001 + T2-001 = 2+2 = 4 pts for the two DDL tasks alone, before services/endpoints) comfortably clears the floor.

**H2 (dual-implementation multiplier)**: Applied. This codebase's dual-implementation axis is
SQLite+Postgres DDL (not local/enterprise repos), and every new table ships both DDLs plus a
parity+direct-count test as a hard exit gate (T1-001/T1-002, T2-001/T2-002). The decisions block
explicitly noted this multiplier was "already absorbed" into its P1/P2 anchors — confirmed still
true after expansion.

**H3 (algorithmic flag)**: Flagged and budgeted. `entity_graph.py` correlation + D-001 dedup
(T2-006 + T2-007 = 3 pts standalone) contains "correlation"/"dedup"/"conflict"-adjacent language.
Test scenario enumerated in the plan: two runs sharing one session, session token counted once. This
is thinner than H3's "≥5 scenarios or SPIKE first" bar — **watch item**: expand the T2-007 test
matrix during execution (zero-linked-session run, multi-session run, non-UUID RF `run_id` run,
duplicate-event replay affecting the rollup) rather than shipping with only the single documented
case. The exploration bundle's risk spike already covers the SPIKE gate for the feature as a whole,
so this is a scenario-coverage watch item, not a missing-SPIKE blocker.

**H4 (bundle-vs-sum)**:

| Capability Area | Independent Estimate | Notes |
|------------------|----------------------|-------|
| Ingest transport + `rf_events` | 8.5 pts | Reuses ADR-008 stack; dual-DDL + idempotency |
| Run entity + intelligence + correlation | 10 pts | Algorithmic risk hotspot; dedup + karen gate |
| Analytics visualization tab | 6.5 pts | Seam task + runtime smoke required |
| Hardening + docs + deferred specs | 6 pts | 7 itemized DOC-006 tasks, not bundled |
| **Σ** | **31 pts** | Plan total equals Σ exactly — no compression applied |

**H5 (anchor reference)**: Directional anchors, not a single recovered SP figure — this plan didn't
pull an exact actual-cost number from a prior AAR (would have cost a full plan-read to recover, and
none of `collections`/`deployment-sets`/`bundles`-style anchors from the general heuristics doc are
CCDash features). Directional anchors used per-phase instead: P1 → the ADR-008/009/014/015 remote
session ingest stack (`ingest_cursors` v36 precedent — same transport shape, one new raw table); P2
→ existing `agent_queries` services (`system_metrics.py`, `artifact_intelligence.py`) plus
`links.py` correlation; P3 → existing `AnalyticsDashboard.tsx` tab patterns (MetricCard strip +
recharts + drill table). If a future retrospective recovers this feature's actual cost, it becomes
the first same-shape CCDash anchor (ingest + entity + viz) for the next similar feature.

**H6 (plumbing budget)**: Folded into per-task descriptions rather than a separate plan-level line
item (each ingest/service/router task description explicitly includes DTOs, OpenAPI, feature-flag
gating, and OTEL spans in scope) — consistent with H6's "prefer estimating it once… over scattering
0.1-pt fragments" guidance, applied here as "embed in the owning task" instead. Reviewer/seam gate
overhead alone (T1-008, T2-008, T2-009, T3-000, T3-007, T4-011, T4-012 = 7 tasks × 0.5 pt = 3.5 pts)
is ~11% of the 31-pt total — a reasonable proxy for the plumbing band without double-counting.

**H7 (huge-file touch)**: Does not apply. `components/Analytics/AnalyticsDashboard.tsx` is
1,244 lines pre-feature (per PRD §8 Internal Dependencies) — under the 2K-line threshold. No 2×
multiplier required for Phase 3 tasks.

**Bottom-up total**: 31 pts
**Top-down intuition**: 26 pts (decisions-block anchor)
**Locked estimate**: 31 pts (bottom-up wins per estimation-heuristics.md policy; no downward
adjustment applied — the delta is fully justified, not padding)

---

## 3. Wave & Orchestration Notes

**Critical path**: Strictly sequential — P1 → P2 → P3 → P4. Each phase's output is the next
phase's typed contract (ingest contract → run entity → visualization → hardening); there is no
inter-phase parallelism in the wave plan.

**Parallel opportunities**:
- Intra-P1: schema/migration work (`data-layer-expert`) and endpoint scaffolding
  (`python-backend-engineer`) proceed concurrently under file-ownership split until the migration lands.
- Intra-P4: the 7 DOC-006 deferred specs and the operator guide/CHANGELOG can start in parallel once
  P3's MVP scope is locked — no shared files between them.

**Merge order**: No branch-stacking complexity expected — single feature branch, phase-by-phase
commits, PR at the end per the Wrap-Up step in the parent plan.

**Cross-feature coupling**: None blocking. This feature is fully additive and does not require
RF's own transport change to land (RF's `emit_ccdash_event()` → HTTP POST wiring is a
research-foundry-repo deliverable tracked separately, per PRD §8). The only soft coupling is that
until RF's side lands, the `ingest_sources[]` `rf` entry will show as stale/disconnected in
production — this is a valid, tested, first-class state, not a blocker.

---

## 4. Open Questions Ledger

| ID | Source | Question | Status | Resolved By |
|----|--------|----------|--------|-------------|
| OQ-1 | Decisions block §7 | One table (`rf_events`) or two (raw + rollup)? | resolved | D6 — two tables, locked in PRD |
| OQ-2 | Decisions block §7 | Feature-flag name + default? | resolved | `CCDASH_RF_TELEMETRY_ENABLED`, default `true`, fail-open (FR-13) |
| OQ-3 | Decisions block §7 | Expose run intelligence via MCP/CLI now or defer? | resolved | Include now (FR-11); T2-005 |
| OQ-4 | Decisions block §7 | Per-provider split via `source_cards` join now or defer? | resolved | Defer (D7); deferred item DF-001 |
| OQ-5 | PRD §13 / plan frontmatter | Resolve `intent_id` via IntentTree API or store opaque? | resolved | Opaque display-only for v1; deferred item DF-007 |

All five open questions from the decisions block and PRD were resolved before the implementation
plan was authored — none remain open heading into Phase 1.

---

## 5. Deferred Items Rationale

All 7 items map 1:1 to PRD §12 and each has a dedicated DOC-006 task in Phase 4 (see plan's
Deferred Items triage table for the full mapping to task IDs and spec paths).

- **DF-001 (per-provider cost/quality splits)**: Deferred because RF's §16 event carries only a
  provider list, not per-provider splits. Promote when RF ships per-provider metrics in a future
  schema version, or CCDash ingests `source_cards` as a second entity.
- **DF-002 (useful-source rate by domain)**: Deferred — domain lives on `source_card.url`, not the
  event. Same `source_cards` join unblocks this alongside DF-001.
- **DF-003 (extraction failure rate by extractor)**: Deferred — extractor identity lives on
  `source_card.extractor`. Same `source_cards` join unblocks this.
- **DF-004 (search→report latency)**: Deferred — no report/synthesis timestamp exists on the
  event. Promote when RF adds one to a future schema version.
- **DF-005 (claim-ledger panel)**: Deferred — requires ingesting RF's claim ledger (§11.4) as a
  distinct entity, out of this PRD's scope entirely. Promote via a follow-up feature.
- **DF-006 (SkillMeat-promotion panel)**: Deferred — cross-system (SkillMeat writeback tracking),
  explicitly excluded from the exploration charter. Promote via a follow-up feature reading
  `search_run.writebacks.skillmeat_candidate_ids`.
- **DF-007 (IntentTree `intent_id` resolution)**: Deferred — would require a live IntentTree API
  call; opaque-string display is sufficient operator legibility for v1. Promote once IntentTree API
  access is wired for CCDash's backend.

---

## 6. Risk Narrative

- **D-001 dedup reproduction (P2, high severity)**: This is the single highest-consequence risk in
  the plan. The run↔session join is structurally identical to the deferred D-001 over-count bug —
  if the dedup discipline (`DISTINCT`/`GROUP BY`-before-sum) is skipped or the regression test is
  treated as a formality, this bug reappears at a second layer with the same blast radius. Watch
  T2-006/T2-007 closely; this is why `karen`'s milestone review sits at the P2 exit gate rather than
  only at feature end.
- **Correlation-key mismatch (P2, medium severity)**: The temptation to "just make it work" by
  loosening `UUID_RE`/`AOS_URN_RE` to accept RF's slugs must be resisted — that would corrupt the
  AOS sidecar-URN graph for every existing session, a much larger blast radius than this feature's
  own scope. D2's boundary (zero `aos_correlation.py` changes) is non-negotiable.
- **Per-provider data gap (P3/P4, medium severity)**: Not really a risk so much as a legibility
  trap — if the tab's copy or panel titles imply per-provider granularity that isn't actually there,
  users will draw wrong conclusions from a real chart showing the wrong grain. Watch panel copy
  during T3-004 for accidental "by provider" framing on what is actually per-mode data.
- **RF transport not yet live (P1, medium severity, accepted)**: This is a known and accepted
  condition, not a live risk to mitigate — the plan is explicitly designed to be complete and
  useful with zero live RF traffic.

---

## 7. What to Watch For

- **T2-007's test matrix is thin.** Only one dedup scenario is spelled out in the task table
  (two runs, one shared session). During execution, push for at least: zero-linked-session run,
  multi-session run, non-UUID RF `run_id` minting a fresh UUID, and duplicate-event replay effect
  on the rollup. If the executing agent ships with just the one scenario, that's a signal to send it
  back before `karen`'s T2-008 review, not after.
- **DOC-006 specs risk being rubber-stamped.** Seven 0.5-pt tasks in one phase is an easy place for
  an agent to produce seven near-identical boilerplate specs. Spot-check at least 2–3 of the 7 for
  genuine unblock-condition specificity (not just restated PRD prose).
- **Watch the P2→P3 seam (T3-000) actually happens before panel work starts**, not retroactively.
  The seam task exists precisely because backend and frontend own disjoint files with no natural
  compile-time check tying them together — a silent contract drift here would only surface as a
  runtime bug in the tab, likely caught late.
- **`ingest_sources[]` `rf` entry will show stale/disconnected in real usage** until RF's own
  transport change lands — this is expected and should not be treated as a CCDash-side bug during
  post-ship validation.

---

## 8. Expected Success Behaviors

- [ ] POSTing the same seeded `ccdash_event` fixture twice via `/api/v1/ingest/rf-events` produces
      exactly one `rf_events` row (verify with a direct DB count, not just "the test passed").
- [ ] With two seeded `research_runs` rows correlated to the same session, any rollup that reports a
      combined session token/cost figure shows the session's own total once — not doubled.
- [ ] Opening `/analytics` → "Provider Economics" tab with zero seeded runs shows an explicit
      "No research runs recorded yet" message in all 4 panels — not blank space, not `$0.00`.
- [ ] Seeding a handful of runs with some optional fields present and some absent renders "—" for
      the absent ones, never `$0.00`/`NaN`/`0%`.
- [ ] `GET /api/v1/capabilities` includes `research-runs:*` and existing API consumers don't error
      on the new string.

---

## 9. Running Log

- [2026-07-21] Brief created alongside the implementation plan expansion from the Opus decisions
  block. Estimation delta (+19% vs. decisions-block anchor) reconciled in §2 — locked at 31 pts,
  bottom-up.
