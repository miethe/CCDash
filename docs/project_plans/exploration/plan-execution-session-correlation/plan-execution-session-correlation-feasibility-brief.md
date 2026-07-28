---
schema_version: 2
doc_type: report
report_category: feasibility
title: "Plan-Execution ↔ Session Correlation & Frontmatter Enrichment — Feasibility
  Brief"
status: finalized
created: 2026-07-26
feature_slug: plan-execution-session-correlation
verdict: conditional
verdict_confidence: 0.75
exploration_charter_ref: 
  docs/project_plans/exploration/plan-execution-session-correlation/plan-execution-session-correlation-charter.md
proposed_adr_ref:
recommended_next_action: "/plan:plan-feature --tier=2 for the ingestion+enrichment
  slice (Slice 1, independent of the join); defer per-level correlation (Slice 2)
  until gap-analysis Themes 1-2 land"
related_documents:
- docs/project_plans/reports/feature-retro-linkage-gap-analysis.md
updated: '2026-07-26'
---

# Plan-Execution ↔ Session Correlation & Frontmatter Enrichment — Feasibility Brief

<!-- verdict and verdict_confidence populated. status: draft pending review. -->

---

## 1. Synopsis

CCDash's planning intelligence stops at the **feature** grain, and even there the
feature→session join is effectively dead (29 links / 14,399 sessions; a probe feature
reported **$0 / 0 tokens / 0 sessions** while $1,191 of measured spend across 24 sessions
sat one join away — `feature-retro-linkage-gap-analysis.md:19,119`). This exploration asked
whether CCDash could instead go *deeper*: ingest richer plan/workflow frontmatter, extract
the full execution hierarchy (wave→gate→phase→task→AC) as structured entities, and correlate
sessions to **every** level to derive per-level performance (validation/fix loops, reviews
used, tokens/cost). The four investigation legs converge on a **split answer**: the
**ingestion + enrichment** work is buildable now and is independent of the dead join, while
**per-level session correlation** is buildable in principle but gated on the gap-analysis
base-join remediation plus additional attribution work that today does not exist. This brief
therefore recommends a **conditional** verdict with an explicit two-slice split — one GO-NOW,
one DEFER — rather than a single go/no-go on the whole scope.

---

## 2. Investigation Summary

| Leg | Agent | Confidence | Feasibility | Conclusion |
|-----|-------|-----------|-------------|------------|
| schema-currency | search-specialist | 0.78 | feasible | `.claude/skills` is a symlink to the upstream (no deploy drift); real drift is intra-repo between the thin `schema_version: 2` artifact-tracking contract and the richer `it_schema: 1` planning contract (~45 fields CCDash never extracts). `progress.py` has a live `model`→`assigned_model` field-name bug (`schema-currency-findings.md:39`), truncates deps to `[:3]` as tags and drops multi-assignee, and `documents.content` is capped at 5,000 chars (`:45`). Enrichment is cheap and additive. |
| hierarchy-ingestion | spike-writer | 0.72 | feasible-with-constraints | phase→task already modelled (`feature_phases`+`tasks`+`parent_task_id`); wave/gate/AC are unstructured frontmatter blobs today. Full ingestion is feasible via the existing `feature_phases` child-table + delete-then-insert pattern (~3-4 new tables) at **~25 pts** ingestion-only (`hierarchy-ingestion-findings.md:252-262`). Note: the charter's "IntentTree `sync_import`" premise does **not** hold in this repo — no such path exists to reuse (`:100-111`). |
| correlation-crux | research-technical-spike | 0.78 | feasible-with-constraints | Raw signal *ingredients* exist at tool-call/log-row granularity — file-edit loops (`session_file_updates`), test fail→pass runs, review-agent invocation rows, per-tool-call usage attribution. But there is **no entity to attribute to** at wave/AC level, phase/task attribution reuses the orchestrator-only slash-command-tag mechanism that already fails for subagents, and `session_usage_attributions.entity_type` has no `task/phase/wave/AC` member (`correlation-crux-findings.md:27`). **Deal-killer NOT triggered — deferred:** signal is present, but level-granular derivation is new code gated on the base-join fix. |
| risk-blast-radius | data-layer-expert | 0.72 | refuted (data-layer) | No data-layer structural blocker: `entity_links` takes new link types with zero migration; `feature_phases` is reusable scaffolding; `session_correlation.py` already does request-time, non-persisted, phase-aware correlation off the hot path. The **real** risk is operational: the existing `_rebuild_entity_links` is an O(sessions × ref-entities) global re-derive with per-row commits (`risk-blast-radius-findings.md:56-57`); adding levels as new sync producers multiplies it 10-100x. Sequencing verdict: **MUST land after gap-analysis Themes 1-2** (`:157`). |

All four legs report confidence ≥ 0.70; no leg reports hard infeasibility; the deal-killer is
explicitly refuted/deferred (not triggered) by both the correlation-crux and risk legs.

---

## 3. Cost Estimate

The scope cleaves into two slices with sharply different sizing certainty. **H5 anchors** are
drawn from the hierarchy-ingestion leg (`hierarchy-ingestion-findings.md:234-250`).

### Slice 1 — Hierarchy ingestion + frontmatter/schema enrichment (GO-ABLE NOW)

**Rough estimate**: **~20–30 story points** (Tier 2/3 equivalent), centred on the
hierarchy leg's **~25 pt** ingestion-only bottom-up (`hierarchy-ingestion-findings.md:262`).

**Comparable past features (H5)**:
- `session-transcript-orchestration-intelligence-v1` (~20 pts) — closest analog for *parsing
  semi-structured source into typed register items with confidence + backrefs*
  (`hierarchy-ingestion-findings.md:244`).
- `research-foundry-run-telemetry-v1` (~31 pts) — anchor for *new ingestion pipeline + new DTOs
  + phased rollout* (`:249`).
- `ccdash-db-design-remediation-v1` (~40 pts) — upper bound for *several new tables + repo layer
  + dual-DDL parity* (`:242`).

**Major cost drivers** (from the hierarchy leg's component table, `:254-262`):
- Migration for `plan_waves` / `plan_gates` / `plan_acs` / `task_dependencies` + `tasks.wave_id`,
  dual SQLite+Postgres DDL + parity check (~5 pts).
- `wave_plan` frontmatter parser as a new module (~3 pts).
- PRD-AC extraction from prose headings + list-of-dict fallback — fragile regex, H4/H5 risk
  premium (~5 pts).
- Sync-engine hook + `upsert_waves/gates/acs` repository methods mirroring `upsert_phases` (~5 pts).
- Tests: migration parity, real-plan fixtures, sync round-trip (~5 pts).

**Cheap enrichment wins folded in** (schema-currency leg, low-cost/high-confidence):
- 1-line `model`→`assigned_model` field-name bug fix (`schema-currency-findings.md:56`).
- Task de-truncation: real `dependencies` edges + full `assigned_to` (`:57`, folded into the
  `task_dependencies` write above).
- Lift/replace the 5,000-char `documents.content` truncation so long plans' AC sections survive
  ingestion (`:59`).
- Promote `wave_plan`/`tier`/`points`/`scores` into the doc-type field allowlist and project
  `tier`/`points` onto `features` (`:60`).

Excludes FE surfaces to display the hierarchy and any session-correlation joins (those are Slice 2).

### Slice 2 — Per-level session correlation + performance signals (DEFER)

**Rough estimate**: **not independently sizable today** — directionally **~25–40+ pts of net-new
work, ON TOP OF gap-analysis Themes 1-2** (a separate prerequisite effort, not counted here).
No H5 anchor bounds this cleanly because it composes several subsystems that do not exist:
- A new usage-attribution producer to add `task`/`phase`/`wave`/`AC` `entity_type` members
  (`correlation-crux-findings.md:27,50`).
- Loop/retry derivation code (file-edit repeats, test fail→pass, tool error→retry) — zero exists
  today (`:22-24`).
- A reviewer-type-agent taxonomy so "reviews used" becomes a count, not a presence flag — the
  shipped `agentsUsed` badge dedupes the count away by design (`:25,51`).
- Widening lineage inheritance from feature-only to feature+phase+task so subagent signal is
  reachable (`:44-45`).

Given the risk leg's mandate to build correlation as a **request-time extension of
`session_correlation.py`** rather than new sync producers (`risk-blast-radius-findings.md:81-87`),
much of the cost is derivation/aggregation logic, not schema. Size this properly only *after*
Themes 1-2 land and the correlation-crux OQs (retry linkage, usage-attribution liveness) are
empirically resolved.

---

## 4. Value Statement

**Primary beneficiaries**: operators and developers running feature retros / AARs; the
planning session board and feature-evidence-summary surfaces.

**Evidence of demand**:
- The **$1,191 invisible-spend probe** (`feature-retro-linkage-gap-analysis.md:19,64-74`): a real
  feature (`asm-p2`) whose 24-session / 388.7M-token / $1,191.38 execution the AAR reports as
  "insufficient execution evidence" — *"the retro is not evidence-limited, it is join-limited"*
  (`:101`). Desirability is established; the charter explicitly skipped a value leg for this reason
  (`plan-execution-session-correlation-charter.md:128`).
- No sub-feature plan-hierarchy correlation exists **at all** today — wave/gate/AC are not entities
  and phase/task attribution is orchestrator-only (`correlation-crux-findings.md:18-21`).

**What each slice unlocks**:
- **Slice 1 alone** delivers standalone value *even with the join still dead*: structured
  wave→gate→phase→task→AC tables make plan structure queryable (parallelism, gate/reviewer
  posture, AC→file `target_surfaces`/`verified_by` coverage), and the enrichment fixes recover
  `assigned_model` (a plan-vs-actual model-drift signal against the session's real `model_slug`,
  `schema-currency-findings.md:57`) and real dependency edges. This is useful the day it ships.
- **Slice 2** is what turns the recovered join into **per-level forensics**: which phase burned
  the fix loops, how many review passes a task took, tokens/cost per wave. High value — but it
  is contingent, not immediate.

**Counterfactual**: If neither slice is built, retros stay feature-grained *and* join-broken —
$1,191-class executions remain invisible and plan structure stays trapped in opaque frontmatter
blobs. If only Slice 2 is attempted first, it inherits a base rate empirically measured at 0.2%
and builds N new evidence pipelines on a join that does not yet fire
(`risk-blast-radius-findings.md:178-179`).

---

## 5. Risks & Blast Radius

Drawn from the risk-blast-radius leg's register (`risk-blast-radius-findings.md:54-65`).

| Risk | Category | Severity | Mitigation |
|------|----------|----------|------------|
| Global re-derive hot path: `_rebuild_entity_links` runs O(sessions × ref-entities) on nearly every watcher tick (`sync_engine.py:3690-3699`); adding phase/task/AC as new sync producers multiplies per-tick cost 10-100x (`risk-blast-radius-findings.md:56,78`) | technical/operational | **H** (Critical if built as new producers) | Do NOT add levels as `_rebuild_entity_links` producers. Extend the request-time `session_correlation.py:317` pattern — zero writes, computed on read (`:81-87`). |
| Per-link-row commit amplification: `entity_graph.upsert` commits one transaction per link row in the hot loop (`entity_graph.py:122-149`); 4 levels × candidates × 14k sessions is a qualitatively worse write profile (`risk-blast-radius-findings.md:57,79`) | technical | **H** | If any persisted link type is added, route through the existing-but-unused `bulk_upsert` (`entity_graph.py:347`) — pending OQ-4 (why it's unused). |
| Dual-DDL parity: new `plan_*` tables are migration-governed and must clear `validate_migration_governance_contract()` + `COLUMN_PARITY_DRIFT_ALLOWLIST` (`migration_governance.py:319,462`) — CLAUDE.md dual-DDL invariant | technical | **M** | Follow `feature_phases` precedent (`sqlite_migrations.py:600-611` + Postgres mirror); target zero-drift; ship direct-count + parity tests per `aar_reviews`/`research_runs` precedent (`risk-blast-radius-findings.md:61-62,110`). |
| SQLite single-writer contention under `CCDASH_WATCHER_SYNC_CONCURRENCY` (default 20) concurrent syncs, each capable of a global rebuild with per-row commits (`config.py:1119`) | operational | **H** | Reduce commit count (bulk path); prefer request-time correlation so no new hot-path writes are added (`risk-blast-radius-findings.md:58`). |
| Link write-amplification / low-discrimination: permissive `if base_confidence <= 0: continue` gate (`sync_engine.py:6271`) means AC/task/phase derivation off the *same* file-path evidence yields highly correlated, low-value links (`risk-blast-radius-findings.md:60`) | technical (data quality) | **M** | Hierarchical/stricter confidence rule (owned by correlation-crux design, not ingestion). |
| `LINKING_LOGIC_VERSION` bump forces a full-corpus rebuild for every project (`config.py:70`), expensive at 14k sessions (`risk-blast-radius-findings.md:63`) | operational | **M** | Ship any new correlation behind a separate flag (mirror `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`), not a logic-version bump, so a bad rollout is flag-disabled. |
| Cross-repo feature federation (G-5) means even perfect ingestion can't roll up phases/tasks living in a second repo's artifacts (the `asm-p2` fleet/engine split) (`risk-blast-radius-findings.md:64`) | organizational | **M** | Documented out-of-scope inherited constraint; scope hierarchy correlation per-repo, same as features today. |
| Sequencing dependency: Slice 2 built before gap-analysis Themes 1-2 inherits the 0.2% base rate and subagent-unreachability at every level (`risk-blast-radius-findings.md:157-179`) | organizational | **H** | Gate Slice 2 on Step 0 → Theme 1 → Theme 2 explicitly (see Verdict). |

The risk leg's headline: the wrong implementation choice (mirroring the feature↔session producer
per level) turns "additive feature" into "measurable latency regression on every sync,"
independent of whether the signal exists (`risk-blast-radius-findings.md:151-155`).

---

## 6. Architectural Implications

**No proposed ADR is drafted now — deliberately.** The load-bearing architectural decision is
verdict-dependent: it only needs resolving *if we build*, and its inputs (row-count ratios, base-join
liveness, usage-attribution liveness) are open empirical questions the exploration could not settle
read-only. Per the exploration anti-pattern guard, the reasoning is carried here rather than
committed to an ADR file that presumes a build. `proposed_adr_ref` is `null`.

**Decision 1 — Data-model shape for the hierarchy (Slice 1).** Two candidates surfaced:

- **(A) New child tables under `features`** — `plan_waves`, `plan_gates`, `plan_acs`,
  `task_dependencies`, plus a `tasks.wave_id` column — following the existing `feature_phases`
  delete-then-insert precedent (`hierarchy-ingestion-findings.md:123-183`).
- **(B) Extend `tasks` with a generic `level` + `parent_id` polymorphic overlay.**

The hierarchy leg recommends **(A)**, because `tasks` already carries live-execution semantics
(status, owner, cost, `session_id`) sourced from *progress* docs, whereas waves/gates/ACs are
*plan-structure* metadata sourced from the *implementation-plan* file and must refresh
independently of task execution state. A polymorphic squash risks the same lossy behaviour already
observed in `parse_progress_file` (phase→string, batch→tag, deps→truncated tags)
(`hierarchy-ingestion-findings.md:125-131`). This decision is **not final** — it is contingent on
OQ-1/OQ-2 (is `wave_plan` prevalent enough to justify a dedicated parser; should `plan_gates` merge
into `feature_phases` since gates are always phase-scoped exit conditions today,
`:270-279`) and on OQ-4 from correlation-crux (are wave/AC first-class entities or virtual
groupings over `tasks`/`feature_phases`, `correlation-crux-findings.md:70`).

**Decision 2 — Correlation delivery mechanism (Slice 2).** The risk leg is unambiguous:
**request-time extension of `session_correlation.py`, not new sync-engine link producers**
(`risk-blast-radius-findings.md:81-87,146-149`). This keeps `entity_links` schema-free (new link
types need zero migration) and off the O(sessions × ref-entities) hot path. Open: if per-level
correlation *must* be persisted for query performance at scale, the staleness/latency tradeoff and
`bulk_upsert` routing must be re-decided (risk OQ-1/OQ-4, `:185,201`).

**Layers touched (Slice 1)**: `backend/parsers/` (new `wave_plan.py` + AC extractor + `progress.py`
fix), `backend/db/{sqlite,postgres}_migrations.py`, `backend/db/repositories/features.py`
(new `upsert_*`), `backend/db/sync_engine.py` (`_sync_features` hook), `backend/models.py` (new DTOs).
No structural change to the sync architecture itself — it reuses the `feature_phases` shape verbatim.

**Layers touched (Slice 2)**: `session_correlation.py` (input widening),
`session_usage_attribution.py` (new plan-level attribution producer), new derivation/aggregation
helpers, and a config-driven reviewer-agent taxonomy (mirroring `session_mappings.py`).

**Decision 3 — IntentTree as the import path (RESOLVED 2026-07-26): NO.** The
`hierarchy-ingestion` leg dismissed IntentTree `sync_import` reuse in one line; that dismissal was
re-investigated as a focused follow-on spike. Full evidence:
`spikes/intenttree-import-path/intenttree-import-path-findings.md` (verdict **no-go**, confidence
0.85). **This does not change the verdict or the plan below** — Slice 1 stays file-based and GO,
Slice 2 stays DEFER. Summary of what was settled, so it is not re-explored:

- **CCDash must NOT consume IntentTree's node tree for Slice 1** — *not* because the importer is
  weak. `sync_import` is genuinely capable: it unions `tasks[]` with `wave_plan.phases[].tasks`,
  emits `depends_on`/`blocks` edges, captures validation commands and doc refs, and can even project
  ACs as `step` nodes under `--ac-as-steps`. The rejection rests on the *deployed reality* and the
  architecture: the live `aos-ccdash` tree is 271 nodes from **3** plans (vs 132 implementation plans
  on disk), frozen since **2026-06-24** with no automatic refresh, using 2 of 18 node types. There is
  no `wave`/`gate` node type — gate criteria survive only as unqueryable `meta` keys. Its
  `acceptance_criteria` is not per-node: 246 nodes share **4 distinct lists** because DI-152 container
  inheritance (on by default) copies phase/feature AC onto every task lacking its own, so a consumer
  **cannot distinguish authored from inherited AC** and any per-task AC join would be silently wrong.
  Container-level bindings carry `source_fingerprint: null`, so phase-set drift is undetectable — the
  import dropped `ccdash-core-remediation` Phase 1 and Phase 4 and never flagged it. Consuming this
  would be derived-reading-derived (AOS constraint #2), adding a runtime dependency on a LAN service,
  for a hierarchy CCDash already parses from the same files.
- **`intenttree-session-correlation-v1` is CONDITIONAL, not rejected** *(revised 2026-07-28; an
  earlier revision of this entry said "must NOT be revived" — that was wrong, see the findings §8).*
  IntentTree does link only **one** session per run (`AgentRun.ccdash_session_id` is a single scalar
  column, no `parent_run_id`, no child registration). **But that does not block per-level
  attribution**, because CCDash already derives the orchestrator→subagent family graph from log
  fields alone (`parser.py:4491-4502`) and it is fully populated: `workflow_id` on **16,658/16,658**
  sessions, `subagent_parent_id` on **3,956/3,956** subagent sessions, 100% family coherence across
  ~770 multi-session families. One `node_id` on the orchestrator propagates across the family and
  reaches every subagent. The mechanism works; the blockers are **adoption + a small build**:
  IntentTree has never dispatched (0 ccdash-bound runs, 0 `claude_code`-harness runs, 0 external-link
  rows), CCDash needs an IntentTree HTTP client (DF-007's unblock condition), and the D2
  never-a-join-key boundary must be deliberately overturned. Leave the PRD at `status: draft` — it is
  premature, not wrong. **New hard design question**: family-level propagation over-attributes when
  one session spans multiple nodes (same class as deferred D-001 over-count); a run-boundary
  attribution rule is required before this ships.
- **`node_id` resolution is unsolved and constraint-bound.** The PRD stores `node_id` in an opaque
  `metadata_json` blob with no column, no schema, and no read path. Resolving it is the same problem
  class as `rf-intenttree-intent-id-resolution` (DF-007, deferred), whose unblock condition — an
  IntentTree HTTP client plus a resilience contract in `backend/config.py` — CCDash still lacks. That
  spec's **D2 boundary** (these ids must never become an `entity_graph`/`aos_correlation` join key)
  directly collides with what Slice-2 per-level attribution would require.
- **~~Carried forward — `aos_trace_uuid`~~ RETRACTED 2026-07-28.** An earlier revision named
  `aos_trace_uuid` (IntentTree migration `0036`) as the key unlock for subagent grouping and routed
  it to the AOS launchpad. **That is unnecessary** — CCDash's log-derived `workflow_id` /
  `subagent_parent_id` lineage already solves grouping with no dispatcher cooperation, and it is
  100% populated today. `aos_trace_uuid` retains value only for *cross-harness* multi-hop work
  (e.g. Codex↔Claude handoffs spanning separate session families), which is out of scope here.
- **Slice 1 stays file-based regardless.** Architecture B only ever covers IntentTree-*dispatched*
  runs; the 16,658-session historical corpus and all ad-hoc work require the file path. The
  recommended end-state is therefore the **hybrid**: file-based Slice 1 as canonical, IntentTree
  correlation as additive enrichment for future dispatched work.

---

## 7. Verdict

**Verdict**: **conditional**
**Confidence**: **0.75**

**Rationale**: All four legs report confidence ≥ 0.70 and none reports hard infeasibility; the
deal-killer ("no usable per-level session signal even after the base-join fix") is **not triggered**
— correlation-crux confirms the raw ingredients (loop counts, review counts, tokens/cost) exist at
tool-call/log-row granularity (`correlation-crux-findings.md:22-25`), and the risk leg refutes any
data-layer structural blocker (`risk-blast-radius-findings.md:138-149`). This maps to the charter's
**conditional** criterion: *"Hierarchy ingestion + schema enrichment feasible, but per-level
correlation depends on a named precondition (gap-analysis Step 0 / Themes 1–2 landing first)"*
(`plan-execution-session-correlation-charter.md:58-61`). The scope splits into two slices with
different verdicts, and this must be made explicit:

- **SLICE 1 — Hierarchy ingestion + frontmatter/schema enrichment: GO (now).** Extracting
  wave→gate→phase→task→AC into structured tables, ingesting the richer `it_schema: 1` fields the
  parsers drop, and fixing `progress.py`'s field-name/lossiness bugs + the 5,000-char body
  truncation is **feasible today and fully independent of the dead session→feature join** — it is
  sourced from plan/PRD frontmatter and bodies, not from session correlation. It reuses the proven
  `feature_phases` child-table pattern (`hierarchy-ingestion-findings.md:185-190`) at ~20–30 pts and
  delivers standalone query value immediately. **This is the recommended first move.**

- **SLICE 2 — Per-level session correlation + performance signals: DEFER (conditional).** Feasible
  in principle but gated on **(a)** the gap-analysis base-join fix (Themes 1-2: subagent lineage
  inheritance + slug normalization + widened evidence surface) **AND (b)** additional attribution
  work the base-join fix does *not* deliver: task/wave/AC levels have no entity to attribute to, and
  phase-attribution reuses the orchestrator-only slash-command-tag mechanism that fails for subagents
  (`correlation-crux-findings.md:12,44-52`). The deal-killer is **deferred, not triggered** —
  the signal exists; the plumbing to attribute it per-level does not. Building this before Themes 1-2
  inherits the 0.2% base rate (`risk-blast-radius-findings.md:178-179`).

**Named precondition for Slice 2**: gap-analysis **Step 0** (resolve the G-2 slug-vs-catalogue open
question) → **Theme 1** (make sessions link: widen evidence surface, subagent lineage inheritance,
slug normalization) → **Theme 2** (close ingestion holes), all in
`feature-retro-linkage-gap-analysis.md:344-354`.

---

## 8. Recommended Next Action

**Run `/plan:plan-feature --tier=2 --charter=docs/project_plans/exploration/plan-execution-session-correlation/plan-execution-session-correlation-charter.md`
scoped to Slice 1 only** (hierarchy ingestion + frontmatter/schema enrichment), which is independent
of the join and can proceed immediately. During planning, resolve hierarchy-ingestion OQ-1/OQ-2
(wave_plan prevalence; gate merge-vs-split) and lock Decision 1 (new `plan_*` tables vs. polymorphic
`tasks` overlay) — that data-model choice is deferred with the build, per §6.

**Defer Slice 2** (per-level correlation + performance signals) with an explicit gate:
`defer-until: gap-analysis Themes 1-2 land AND correlation-crux OQ-1/OQ-5 (retry linkage,
usage-attribution liveness) are empirically resolved`. Re-size Slice 2 at that point using a live
corpus, since its cost is dominated by net-new derivation subsystems that cannot be anchored today.

---

## 9. Citations

- Exploration charter: `docs/project_plans/exploration/plan-execution-session-correlation/plan-execution-session-correlation-charter.md`
- schema-currency leg SPIKE: `docs/project_plans/exploration/plan-execution-session-correlation/spikes/schema-currency-findings.md` (conf 0.78)
- hierarchy-ingestion leg SPIKE: `docs/project_plans/exploration/plan-execution-session-correlation/spikes/hierarchy-ingestion-findings.md` (conf 0.72)
- correlation-crux leg SPIKE: `docs/project_plans/exploration/plan-execution-session-correlation/spikes/correlation-crux-findings.md` (conf 0.78)
- risk-blast-radius leg SPIKE: `docs/project_plans/exploration/plan-execution-session-correlation/spikes/risk-blast-radius-findings.md` (conf 0.72)
- Prior art (join mechanics + remediation themes, not re-derived): `docs/project_plans/reports/feature-retro-linkage-gap-analysis.md`
