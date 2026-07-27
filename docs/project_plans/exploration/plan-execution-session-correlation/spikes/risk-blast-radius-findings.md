---
leg: risk-blast-radius
confidence: 0.72
deal_killer: refuted
---

# Risk / Blast-Radius Findings — Plan-Execution ↔ Session Correlation

## Summary

From the data layer, the deal-killer as stated ("no usable sub-feature signal even after
the base join is fixed") is **not** a data-layer blocker — it is a `correlation-crux`
question about signal *presence*, which this leg cannot itself confirm or refute (no session
log content was inspected here). What this leg **does** confirm is a **different, real
deal-killer-adjacent risk**: the *existing* link-derivation engine is already an
O(sessions × ref-entities) global re-derive that fires on effectively every watcher tick
(`backend/db/sync_engine.py:3690-3699`), and it commits **one SQLite transaction per link
row** (`backend/db/repositories/entity_graph.py:122-149`) with no bulk path used anywhere in
the hot loop. Naively adding phase/task/AC-level link derivation as *more instances of this
same pattern* multiplies an already-flagged performance trap by the ratio of new
hierarchy-entity count to feature count — which, per `feature_phases`/`tasks` cardinality,
is likely 10-100x, not the 3-4x the "just add more levels" framing implies.

**The mitigation is not "make the derivation cheaper" — it is "don't extend the derivation
at all."** `backend/application/services/agent_queries/session_correlation.py:317-347`
already does per-session, request-time correlation against features (and partially phases)
with **zero writes to `entity_links`** and is called from the planning board / feature-evidence
summary paths, not the sync hot path. This request-time pattern — not a new sync-engine
producer — is the low-blast-radius way to add task/AC-level correlation. If hierarchy
ingestion instead becomes a set of new `_rebuild_entity_links` producers, the blast radius is
**high** and the deal-killer risk becomes real for operational reasons (sync latency, SQLite
lock contention), independent of whether the underlying signal exists.

Schema/migration risk is **low-to-medium**: `entity_links` has no CHECK constraint on
`source_type`/`target_type` (`backend/db/sqlite_migrations.py:102-124`), so new link *types*
(`phase↔session`, `task↔session`, `ac↔session`) are additive, zero-migration. New tables
(`plan_waves`, `plan_gates`, or an `acceptance_criteria` table) **are** migration-governed and
must clear `validate_migration_governance_contract()` (`backend/db/migration_governance.py:319`)
and the `COLUMN_PARITY_DRIFT_ALLOWLIST` mechanism (`migration_governance.py:462`) per CLAUDE.md.
`feature_phases` already exists (`sqlite_migrations.py:600-611`) as a **skeleton table with no
current write path exercised by session evidence** — it is closer to reusable scaffolding than
a design-from-zero problem, which lowers migration risk for the phase level specifically.

**Sequencing verdict: this work MUST land after gap-analysis Themes 1-2.** Every hierarchy
level below "feature" inherits the feature level's evidence-surface and subagent-attribution
gaps (G-1/G-2) *and* the ingestion holes (G-3/G-4). Building phase/task/AC correlation before
sessions reliably link to features means building N new evidence pipelines on top of a base
join that is empirically 0.2% populated — the same failure shape, multiplied.

---

## Risk Register

| ID | Risk | Severity | Likelihood | Evidence | Mitigation |
|---|---|---|---|---|---|
| R-1 | Global re-derive already runs on (almost) every watcher tick; adding hierarchy levels multiplies per-tick session-evidence-loop cost by (Σ new ref-entities / feature count) | **Critical** | High (near-certain if implemented as new sync_engine producers) | `sync_engine.py:3690-3699` (scoped API still calls unscoped `_rebuild_entity_links`); `sync_engine.py:6002-6039` (full session page-load + 3 child-table reads per session, per rebuild); `sync_engine.py:6158` (per-session loop over every `feature_ref_paths` entry) | Do NOT add phase/task/AC as new `_rebuild_entity_links` producers. Extend the request-time `session_correlation.py:317` pattern (already phase-aware) instead — zero writes, computed on read. |
| R-2 | Per-link-row commit (no batching) in the hot evidence loop | **High** | High (already true today; confirmed present code) | `entity_graph.py:122-149` (`upsert` calls `self._commit()` every call); `sync_engine.py:6365` calls `link_repo.upsert` once per (feature, session) candidate inside the per-session loop; delete phase (`entity_graph.py:572-582`) also commits per entity | If any new persisted link type is added, route through `bulk_upsert` (`entity_graph.py:347,379,405` — already exists but unused by the hot loop) instead of per-row `upsert`. |
| R-3 | SQLite single-writer contention: up to `CCDASH_WATCHER_SYNC_CONCURRENCY` (default 20) concurrent per-project syncs (`config.py:1119`) each capable of triggering a global rebuild with per-row commits | **High** | Medium (already latent; new levels increase per-tick lock-hold duration, raising collision probability) | `busy_timeout=30000` is already an invariant (CLAUDE.md:162) but only bounds wait time, not contention frequency; reducing commit count (R-2) is the real lever. |
| R-4 | `feature_ref_paths`-style evidence-surface build must be repeated per new hierarchy level (phase_ref_paths, task_ref_paths, ac_ref_paths), each requiring its own alias/slug-matching pass (`sync_engine.py:5866-5941` equivalent) | **Medium** | High if built as separate producers | Same mitigation as R-1 — request-time correlation reuses one evidence pass per session, not N. |
| R-5 | Permissive confidence gate `if base_confidence <= 0: continue` (`sync_engine.py:6271-6272`) has no minimum-confidence floor; more link *types* competing over the same file-path evidence increases false-positive link volume (a session touching a phase dir could satisfy phase, task, AND ac evidence simultaneously) | **Medium** | Medium | Not a migration/perf risk but a data-quality risk: AC-level and task-level derivation from the *same* file-path signal as phase/feature will produce highly correlated, low-discriminating links unless a stricter/hierarchical confidence rule is designed (owned by correlation-crux, not this leg). |
| R-6 | New `plan_*` tables (waves/gates/ACs) must pass `validate_migration_governance_contract()` (SQLite/Postgres table-set identity) and dual DDL in the same changeset | **Medium** | Low (mechanical, well-precedented) | Follow the existing `feature_phases` pattern (`sqlite_migrations.py:600-611` / mirrored postgres_migrations.py:527+); add `COLUMN_PARITY_DRIFT_ALLOWLIST` entries only if a deliberate cross-backend difference is introduced (docstring-documented DRIFT-NNN, `migration_governance.py:459-468`). |
| R-7 | New write paths for `plan_*` tables must use `retry_on_locked` (ADR-007) and ship a direct-count assertion test, mirroring `aar_reviews`/`research_runs` precedent (`test_aar_reviews_repo.py`, `test_research_runs_migration_governance.py`) | **Low** | Low (process risk, not technical risk) | Copy the existing test pattern; both precedent test files already assert `COLUMN_PARITY_DRIFT_ALLOWLIST` has zero entries for their table, proving the parity-clean path is achievable. |
| R-8 | `LINKING_LOGIC_VERSION` bump (`config.py:70`) forces a full rebuild — walking `docs_dir`/`progress_dir` and running the (now larger) global session-evidence loop — for **every registered project** on next sync after any new-producer deploy | **Medium** | Medium (one-time per logic-version bump, but 14k-session corpus makes each occurrence expensive) | Ship new hierarchy link derivation, if it must be sync-engine-based at all, as a separately versioned/flagged rollout (mirroring `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`), not a `LINKING_LOGIC_VERSION` bump, so a bad rollout can be flag-disabled without another full-corpus rebuild. |
| R-9 | Cross-repo feature federation gap (G-5, out of scope per charter) means even a perfect hierarchy ingestion cannot roll up phases/tasks that live in a second repo's plan artifacts (the `asm-p2` case: fleet plan in `agentic_meta_dev`, engine plan in `skillmeat`) | **Medium** | Certain for any multi-repo feature | Explicitly documented as out-of-scope inherited constraint; hierarchy correlation should be scoped per-repo, same as features today, not treated as a project-spanning graph. |
| R-10 | Feature-evidence-summary "no drill-down" gap (G-9) and AAR's discard-then-refetch pattern (G-9 note) mean any new per-level DTOs risk repeating the same "computed but thrown away" mistake at the last mile | **Low** | Medium | Design-adjacent, not this leg's call — flagged for the surface-widening theme (gap-analysis Theme 4) to absorb rather than re-solving independently. |

---

## Sync Hot-Path & Link-Derivation Load

**Current baseline cost (feature↔session only), per full `_rebuild_entity_links` invocation:**
- One `session_repo.count` + paginated `list_paginated` load of **every** session in the project (`sync_engine.py:6002-6021`), `include_subagents=True`.
- For **each** session (14,399 in the probe corpus): 3 child-table reads (`get_file_updates`, `get_artifacts`, `get_logs`, `sync_engine.py:6037-6039`) plus a nested loop over **every** feature with `feature_ref_paths` entries (`sync_engine.py:6158`).
- For each accepted (feature, session) candidate: one `link_repo.upsert` call, and **each upsert is its own committed transaction** (`entity_graph.py:147-149`).
- This full-derive path is **not actually skippable**: the "scoped" `rebuild_links_for_entities` deletes scoped rows then calls `_rebuild_entity_links(project_id, operation_id=...)` with **no ID filter** (`sync_engine.py:3694-3697`) — i.e. every watcher-driven changed-`.jsonl` sync (the normal, continuous case per `sync_engine.py:4403-4407`) runs the **global** session-evidence loop, already. This is not a hypothetical introduced by this exploration — it is confirmed, present-day behavior, previously flagged as misleading in the gap-analysis's parenthetical (`sync_engine.py:3690-3697` comment claims scoping that does not happen).

**Projected marginal cost of adding phase/task/AC-level derivation, if implemented as sibling producers to the feature↔session loop:**
- Per-session cost scales with **total ref-entity count across all levels**, not level count. `feature_phases` (skeleton, `sqlite_migrations.py:600-611`) and `tasks` (`sqlite_migrations.py:517-540`, already carries `phase_id`) suggest phase/task cardinality is materially larger than feature cardinality — gap-analysis measured **12,021** `feature→task` child links already existing (§3/G-1 table) against **dozens** of features. An AC level (no table yet) would be larger still. Even a conservative 10x ref-entity multiplier turns today's already-flagged-as-a-performance-trap loop into a ~10x-slower one, run on (effectively) every incremental sync tick.
- Per-row commit amplification (R-2) compounds this: 4 hierarchy levels × candidate links per session × 14k sessions, each an individual `BEGIN`/`COMMIT`, is a qualitatively different write-durability profile than today's single-level version — this is the sharpest concrete regression risk, independent of correlation-crux's signal-quality question.

**The load-bearing mitigation is architectural, not tuning**: the request-time
`correlate_session` pipeline (`session_correlation.py:317-347`) already resolves a
per-session feature/phase binding **without touching `entity_links` or the sync hot path at
all** — it takes `links` (pre-computed, read from DB) and `features` as arguments and computes
correlation on the fly per API call. Extending this function's inputs to include tasks/ACs is
additive to a read path already proven at planning-board scale, not a multiplier on the sync
write path.

---

## DB Schema / Migration / Parity Risk

- **`entity_links` reuse is schema-free for new link types.** No CHECK constraint restricts
  `source_type`/`target_type` values (`sqlite_migrations.py:102-116`); `phase↔session`,
  `task↔session`, `ac↔session` rows are representable today with zero DDL change. The unique
  index `idx_links_upsert` (`sqlite_migrations.py:121`) already keys on
  `(source_type, source_id, target_type, target_id, link_type)`, which generalizes cleanly.
- **New hierarchy tables ARE migration-governed.** Any `plan_waves`/`plan_gates`/
  `acceptance_criteria` table must appear identically in `sqlite_migrations.py` and
  `postgres_migrations.py`'s `_TABLES`/DDL sets or `validate_migration_governance_contract()`
  raises at startup (`migration_governance.py:319-334`, table-set equality check). This is a
  hard CI-enforced gate, not a convention — low risk of silent drift, but a real gate that must
  be planned for (dual-DDL PRs, not follow-up PRs).
  `feature_phases` is a good extant template for the shape (`sqlite_migrations.py:600-611`,
  mirrored in `postgres_migrations.py:527+`).
- **Column parity allowlist is a deliberate escape hatch, not a rubber stamp.** Existing
  entries (`migration_governance.py:462-468`, e.g. `outbound_telemetry_queue.event_type`,
  `session_relationships.created_at`) are each tied to a documented `DRIFT-NNN` rationale.
  Precedent tests (`test_aar_reviews_repo.py:89-98`, `test_research_runs_migration_governance.py:115-126`)
  assert **zero** allowlist entries for their tables — i.e. the bar in this codebase is
  parity-clean-by-default; new plan_* tables should target the same zero-drift bar rather than
  planning for allowlist entries up front.
- **ADR-007 write-path discipline is mechanical but non-optional.** Any new repository method
  writing `plan_*` rows must call `retry_on_locked` (`repositories/base.py:114`, pattern already
  used by `entity_graph.py:120`) and ship a direct-count assertion test. This is process
  overhead, not architectural risk.
- **No migration risk is introduced by extending `session_correlation.py`** — it reads existing
  tables (`links`, `features`, and would additionally read `feature_phases`/`tasks`/a new AC
  table) and returns a computed DTO; it owns no schema.

---

## Blast-Radius Map

| Surface | Impact | Why |
|---|---|---|
| Sync engine hot path (`sync_engine.py:_rebuild_entity_links` / `rebuild_links_for_entities`) | **Regression risk — HIGH if new producers added; NONE if request-time pattern used** | See R-1/R-2/R-3/R-8. This is the one surface where the wrong implementation choice turns "additive feature" into "measurable latency regression on every sync." |
| Planning session board (`planning_sessions.py`, `session_correlation.py`) | **Additive-only, likely beneficiary** | Already phase-partial-aware; task/AC correlation is a natural extension of an existing read-time function signature, not a new subsystem. |
| Feature forensics / feature-evidence-summary | **Additive-only, conditional on gap-analysis fixes landing first** | Already consumes `session_correlation.py` (per G-8); benefits directly once feature↔session join is non-trivial (Theme 1). Building hierarchy correlation before that lands means it inherits G-1/G-2's near-zero base rate. |
| AAR review loop | **Additive-only if surfaced via new DTO fields; NO regression to existing `aar_reviews` rollup/triage logic** | `aar_review_enrichment.py` already fetches rich per-session bundles and discards most of it (G-9) — hierarchy data would be one more thing available to *not* discard, not a change to the deterministic triage state machine itself. |
| Analytics KPIs (`analytics_entries`) | **Additive-only, no schema coupling** | `analytics_entries`/`analytics_entity_links` (`sqlite_migrations.py:623-657`) are generic entity-tagged fact rows; a phase/task/AC entity type is just a new `entity_type` string value, no DDL change (mirrors the `entity_links` finding). |
| DB write volume / VACUUM cadence | **Regression risk — MEDIUM, conditional on producer choice** | More link rows (R-1) directly enlarge `entity_links` and increase autovacuum/VACUUM pressure; see `docs/guides/db-vacuum-runbook.md` (not re-read in depth here — out of this leg's budget, flagged as OQ-2). |

---

## Deal-Killer & Sequencing

**Deal-killer verdict from the data layer: REFUTED, conditionally.**

This leg cannot confirm or refute *signal presence* (that is `correlation-crux`'s question —
whether fix-loops/reviews/validation cycles are recoverable from session logs at all). What
this leg can state authoritatively is that **no data-layer structural barrier** prevents
building level-granular correlation:
1. `entity_links` already generalizes to new link types with zero migration (schema is not
   the blocker).
2. `feature_phases` already exists as reusable scaffolding for the phase level.
3. A proven, low-blast-radius architectural pattern (`session_correlation.py`) already does
   request-time, non-persisted, phase-aware correlation at planning-board scale — it is not a
   green-field design problem.

The risk this leg *does* surface as material is **operational, not architectural**: if the
hierarchy-ingestion leg's design instinct is "mirror the feature↔session producer for every
new level," that choice alone could functionally kill the effort on latency/lock-contention
grounds, independent of whether correlation-crux finds usable signal. **This is a design
recommendation for the hierarchy-ingestion leg to inherit, not a charter-level deal-killer.**

**Sequencing: this work MUST land after gap-analysis Themes 1-2 (G-1/G-2/G-3/G-4).**
Concretely:
- Every hierarchy level's evidence surface is a narrower version of the *same*
  `feature_ref_paths`-style catalogue-bounded matching that gap-analysis found produces 29
  links / 14,399 sessions at the feature level (G-1). Building task/AC correlation on top of
  that base means the base rate compounds downward, not up.
  `sync_engine.py:6158` iterates `feature_ref_paths.items()` per session — a task/AC
  equivalent inherits the same "catalogue must already contain the path" constraint until
  Theme 1's evidence-surface widening lands.
- Subagent sessions (G-2) are structurally unreachable from *any* level today, not just the
  feature level — the `subagent_parent_id` lineage-inheritance fix proposed in gap-analysis
  Theme 1 is a **prerequisite**, not a nice-to-have, for phase/task/AC correlation to ever see
  the ~$1,191/24-session `asm-p2` execution that motivated this exploration in the first place.
- Remote-ingested sessions (G-3) and Codex sessions (G-4) carry the same reachability holes at
  every hierarchy level as at the feature level — nothing about deeper granularity fixes an
  ingestion-time gap.

**Dependency ordering:** gap-analysis Step 0 (resolve the G-2 open question) → Theme 1 (make
sessions link: widen evidence surface, subagent lineage inheritance, slug normalization) →
Theme 2 (close ingestion holes) → **then** plan-hierarchy correlation, implemented as a
request-time extension of `session_correlation.py` rather than a new sync-engine link
producer. Attempting hierarchy correlation before Theme 1 lands is not merely
lower-value — it inherits a base rate empirically measured at 0.2%.

---

## Open Questions

- **OQ-1**: If task/AC correlation *must* eventually be persisted (e.g. for query performance
  at scale, rather than computed per-request), what is the acceptable staleness/latency
  tradeoff, and does that change the "request-time only" recommendation? Not resolved here —
  owned jointly by hierarchy-ingestion and correlation-crux.
- **OQ-2**: This leg did not re-read `docs/guides/db-vacuum-runbook.md` in depth (it appears in
  git status as locally modified, outside this leg's read set) to quantify VACUUM-cadence
  impact of a larger `entity_links` table under the request-time-only design. Flagged, not
  assessed — likely low-impact under the recommended design (no new persisted rows), higher
  impact if the hierarchy-ingestion leg instead chooses to persist correlation results.
- **OQ-3**: Actual row-count ratios (features : phases : tasks : ACs) were not verified against
  a live corpus in this session — the local SQLite cache was mid-relocation
  (`/Volumes/SKNVME/ccdash/data/ccdash_cache.db` currently reports zero tables) per the same
  caveat noted in the gap-analysis (§5). The 10-100x multiplier claim in R-1/R-4 is a structural
  inference from `tasks`/`feature_phases` schema shape and the gap-analysis's measured
  12,021 `feature→task` link count, not a directly re-measured ratio. Should be confirmed once
  the storage relocation settles.
- **OQ-4**: Whether `bulk_upsert` (`entity_graph.py:347-405`, defined but apparently unused by
  the hot session-evidence loop) was intentionally left unused for a reason not visible from
  reading alone (e.g. a correctness requirement for per-row conflict resolution ordering) was
  not confirmed with any author/commit-history check — flagged before recommending its use as
  a mitigation for R-2.

---

## Confidence Rationale

**0.72** — set in the 0.5-0.79 band because several mitigations here (using
`session_correlation.py` as the delivery pattern for new levels; using `bulk_upsert` if
persistence is required) are **recommendations grounded in reading existing code**, not
validated by writing or running anything (this leg is read-only). The risk register itself is
built entirely from direct, cited code reads (no speculative categories), which supports the
higher end of the band; it is held below 0.8 because: (a) OQ-3's row-count ratios are inferred,
not measured, on a corpus this leg could not query (relocation in flight); (b) OQ-4 (why
`bulk_upsert` exists but isn't used in the hot loop) is a real unknown that could invalidate
one specific mitigation; (c) this leg cannot independently corroborate correlation-crux's
signal-presence finding, so the "deal-killer refuted" verdict here is scoped strictly to the
data-layer/architectural dimension, not the full charter-level deal-killer.
