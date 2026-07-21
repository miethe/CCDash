---
leg_id: value
confidence: 0.78
conclusion: "The §16.2 panel set does NOT justify a top-level tab — a 4-panel 'Research / Provider Economics' tab inside the existing AnalyticsDashboard makes the cost/quality evidence loop legible, and matches the just-emerging embedded-analytics pattern."
surface_recommendation: extend_existing
mvp_panel_count: 4
---

# Value Spike — RF Run Telemetry Visualization Slice

## TL;DR

The evidence loop the operator actually wants (§5.2 "which mode/provider gives the best useful-sources-per-dollar at acceptable latency/quality?") collapses to **one economic north-star (cost per useful source) plus a quality triad (useful-rate, duplicate-rate, extraction-fail-rate), sliced by search mode, with a run-level drill table.** That is ~4 composite panels, not 11 discrete charts. It belongs as a new **tab inside `components/Analytics/AnalyticsDashboard.tsx`**, not a new top-level route.

## Critical data-availability finding (shapes everything)

The §16 `execution_event` emits **run-level aggregate metrics with a provider _list_** (`selected_providers: [exa, brave, jina]`), plus one `estimated_cost_usd`, one `duplicate_rate`, one `extraction_failure_rate`. It does **not** carry per-provider splits, source domains, extractor-per-source, report timestamps, or the claim ledger (those live in §11.2 `normalized_results`/`source_cards`, §11.4 `claim`, and SkillMeat writebacks). Consequence: several §16.2 panels as literally worded ("...by provider", "...by domain", "...by extractor", "claims stale", "promoted to SkillMeat") are **not computable from the event alone** — they need joins RF may not ship first. The honest MVP grain is **per-mode + per-run**, with provider shown as a set/frequency, not a per-provider cost attribution. (Flag for tech/risk legs: true per-provider economics requires RF to emit per-provider metric splits or CCDash to join `source_cards`.)

## Panel-value ranking (§16.2)

| # | §16.2 Panel | Evidence-loop value | In event? | Render cost | MVP? |
|---|-------------|:-------------------:|:---------:|:-----------:|:----:|
| 2 | **Cost per useful source** | **High** (north-star $) | Yes (run-level) | Low | **Yes** |
| 3 | Useful source rate (by domain) | High | Rate yes / domain **no** | Med | Partial — by **mode**, defer domain |
| 8 | Duplicate rate (by provider) | Med-High | Aggregate yes / provider **no** | Med | Partial — by **mode**, defer provider |
| 1 | Provider spend by week/month | High ("where $ goes") | Cost yes / provider split partial | Low (TrendChart exists) | **Yes** (spend trend by mode) |
| 4 | Search-mode frequency | Med (context for all others) | Yes | Low | **Yes** (folds into by-mode table) |
| 7 | Extraction failure rate (by extractor) | Med | Aggregate yes / extractor **no** | Med | Partial — aggregate only |
| 5 | Search→source-card latency | Med (budget/UX) | Yes (`latency_ms`) | Low | **Yes** (KPI + by-mode col) |
| 9 | Citation coverage (by report) | Med | Coverage yes / "by report" no | Low | Lite — aggregate/trend only |
| 6 | Search→report latency | Low-Med | **No** (no report ts) | Med | No |
| 10 | Claims unsupported/conflicted/stale | Med (output quality) | **No** (claim ledger) | Med | No — needs §11.4 |
| 11 | Reusable patterns → SkillMeat | Low (vanity for solo; charter out-of-scope) | **No** (SkillMeat) | High | No |

## Surface decision — extend, do not build a top-level tab

**Recommendation: add a `research` (label "Provider Economics") tab to `AnalyticsDashboard`'s `TAB_LABELS` (`components/Analytics/AnalyticsDashboard.tsx:56-65`) + one tab body.** Rationale:

1. **The visual language already exists and is a 1:1 fit.** `AnalyticsDashboard` already renders exactly this shape: a `MetricCard` KPI strip (`:84-90`), `Surface`-wrapped panels, recharts `BarChart`/`PieChart` + `TrendChart` (`:373-381`), `EntityLinkButton` drill-through (`:92-103`), and dense tables with `formatCurrency`/`formatNumber` (`:75-82`). RF economics is conceptually the same rollup as the existing **"Models + Tools"** tab (cost/tokens by model) — here it is cost/quality **by provider-mode**. No new primitives, no new route, no new Layout nav item.
2. **The just-added components confirm the emerging pattern.** `components/SessionAnalyticsModal.tsx` (tabbed `MetricTile`/`MiniTable`) and `components/Planning/FeatureAnalyticsPanel.tsx` (embedded `SectionPanel`/`Metric`/`TokenTable`, graceful null-field fallbacks) both show the house style is **analytics as an entity-scoped embedded/modal panel that degrades gracefully on absent fields** — not a new top-level surface. RF telemetry should join that family, reusing the same resilience-by-default posture (every RF field is optional/absent-tolerant per CLAUDE.md).
3. **Volume + persona argue against a sub-app.** A solo operator on LAN runs a handful of research runs/day. A dedicated top-level "Research" route with run-list + run-detail + claim-ledger drill is premature over-architecture (YAGNI). If a run-detail surface is later warranted (priorart leg's call), it can graduate out; the analytics tab is the cheap, reversible first step.
4. **Cross-project economic rollup = analytics home.** `/analytics` is already the canonical place for cost/quality/provider rollups; RF is another dimension of the same question, not a new domain.

Do **not** put it on the Dashboard home (`components/Dashboard`) — that is project-status at-a-glance, wrong altitude for a per-run economics forensics surface.

## Minimum-lovable slice (the 4 panels)

Smallest set that makes provider cost/quality **legible and actionable**:

- **Panel A — KPI strip** (`MetricCard` row): total RF spend · **cost / useful source** · useful-source rate · duplicate rate · extraction-fail rate · p50 latency. (Folds §16.2 #2,5,7,8,9 aggregates.)
- **Panel B — Cost & quality by mode** (dense table, the evidence-loop workhorse): `mode | runs | spend | cost/useful | useful-rate | dup-rate | ext-fail | p50 latency`, sortable, with a small provider-set frequency chip row. (Folds #1,2,4,7,8 at the only honest grain.) This is the panel that answers "which mode is worth it."
- **Panel C — Spend & run-volume trend** (`TrendChart`, already in-repo): estimated cost + run count over time. (§16.2 #1,4.)
- **Panel D — Run-level drill table** (mirrors the Correlation-tab table at `:1169-1238`): `timestamp | mode | providers | cost | useful | dupes | latency | review-status`, `EntityLinkButton` to a run's session/intent when correlated. The forensic backbone + drill-through.

Everything else is a KPI tile or a table column, not its own chart. This slice is buildable from the `execution_event` alone (no source-card/claim-ledger join), so it can ship the moment events flow.

## Deferred panels (with unblock condition)

- **Per-provider** cost/useful & duplicate rate (#2,#8 by provider) — unblock when RF emits per-provider metric splits **or** CCDash joins `source_cards` (§11.2). Highest-value deferral; revisit first.
- **Useful-source rate by domain** (#3) — needs source domain on the event/card.
- **Extraction failure by extractor** (#7) — needs `source_card.extractor` join.
- **Search→report latency** (#6) — needs report/synthesis timestamp.
- **Claims unsupported/conflicted/stale** (#10) — needs §11.4 claim-ledger ingest (separate entity).
- **Patterns promoted to SkillMeat** (#11) — cross-system, charter §Out-of-Scope; skip.

## Confidence note

0.78. High confidence on **extend_existing** (route, primitives, and emerging pattern all pre-exist and fit exactly). The 0.22 gap is the per-provider granularity risk: if RF surfaces richer per-provider/per-source data cheaply, Panel B's grain upgrades and one or two deferred panels become MVP-worthy — but that is a data-contract question owned by the tech/risk legs, not a reason to change the surface decision.
