---
leg: hierarchy-ingestion
confidence: 0.72
feasibility: feasible-with-constraints
---

# Hierarchy Ingestion Findings — Wave→Gate→Phase→Task→AC

## Summary

CCDash can extract and store the **phase→task** layer of the execution hierarchy today (it already
does, via `feature_phases` + `tasks` + `parent_task_id`/`feature_id`/`phase_id`). It does **not**
extract or store **wave**, **gate**, or **acceptance-criteria (AC)** as first-class, queryable
entities anywhere in the parser/sync/DB stack — those exist only as unstructured frontmatter blobs
(`wave_plan`, `acceptance_criteria`) that CCDash's document parser swallows into an opaque
`docTypeFields` catch-all dict and never decomposes. Task-level **dependencies** are similarly lossy:
only the first 3 are kept, and only as free-text tags, not as edges. Building full hierarchy
ingestion is **feasible** using the existing table-family pattern (new child tables keyed to
`features`/`tasks`, dual SQLite+Postgres DDL, incremental migration) but requires ~3 new tables
(`plan_waves`, `plan_gates` optional-merge, `plan_acs`) plus a new parser module and sync-engine hook.
No blocking constraint found; the main open decision is whether gates are a distinct table or a
column on waves/phases (see OQ-2).

## Source Data Shape (what the plans/progress actually contain)

**Implementation-plan frontmatter (`wave_plan`)** — example:
`docs/project_plans/implementation_plans/enhancements/branch-aware-planning-intelligence-v2.md:74-172`

- `wave_plan.serialization_barriers: []` — file-list barrier (`:75-80`)
- `wave_plan.phases: []` — each phase has `id`, `depends_on: []`, `isolation`, `parallelizable`,
  `provider`, `model`, `effort`, `owner_skills`, `files_affected`, optional
  `integration_owner`/`ui_touched` (`:81-166`, e.g. P2 at `:100-115`)
- `wave_plan.waves: []` — array of phase-id arrays expressing the actual parallel-execution
  schedule, e.g. `[[P0],[P1],[P2,P3,P4],[P5],[P6]]` (`:168-173`) — **this is the "wave" concept**:
  a wave is a synchronization barrier across a batch of phases, distinct from the phase graph.
- Top-level `acceptance_criteria: []` (plan-wide, string+AC-id list) at `:196-199` and
  `points: 26` at `:200`.
- "Gates" are **not** a structured frontmatter key at the plan level — they appear only as prose
  ("Exit Gate (karen milestone)", "P0 exit gate") inside phase progress docs
  (`.claude/progress/branch-aware-planning-intelligence-v2/phase-2-progress.md:117-124`) and as
  `reviewer gates`/`gates P5` prose in the plan body (`branch-aware-planning-intelligence-v2.md:241,264`).
  A gate is currently a **markdown checklist + prose reference to a task ID**, not a schema object.

**Phase progress YAML (`tasks[]`)** —
`.claude/progress/branch-aware-planning-intelligence-v2/phase-2-progress.md:30-78`:
each task has `id`, `description`, `status`, `assigned_to: []`, `dependencies: []`,
`estimated_effort`, `assigned_model`, `model_effort`. Batches/critical path live in a sibling
`parallelization` block (`:79-85`: `batch_1`, `batch_2`, `critical_path`), and phase-level
`success_criteria: []` (`:87-94`, each `{id, description, status}`) is the closest thing to
phase-scoped ACs in the progress doc.

**Task-level, richly-specified ACs with `target_surfaces`/`verified_by`** live in the **PRD**, not
the plan or progress doc — `docs/project_plans/PRDs/features/system-wide-metrics-v1.md:335-402`
(AC-1..AC-6, each with `target_surfaces: []`, `propagation_contract`, `resilience`,
`visual_evidence_required`, `verified_by`). This is a materially richer AC shape than anything a
plan/progress file carries, and it is keyed by AC-id string only (`AC-1`), not by task-id — the
plan's markdown task table cites AC text inline in a `Acceptance Criteria` column
(`branch-aware-planning-intelligence-v2.md:409-413`, column header at `:407`), not a shared ID.
**So AC↔task linkage today is prose-only, split across two documents (PRD + plan), with no shared
key.**

No plan file in this repo's `docs/project_plans/implementation_plans/**` uses an explicit `gate:`
or `ac_id:` frontmatter key; the richest schema sample found is `branch-aware-planning-intelligence-v2`.
Confidence this is representative: moderate — only ~12 plans exist under `implementation_plans/`
(`ls docs/project_plans/implementation_plans/**` output) and `wave_plan` appears in this one
sampled file; a fuller inventory is the `schema-currency` sibling leg's job, not re-derived here.

## Current Model & Reuse Assessment

**Reuse is real but partial.** The DB already models a 2-level hierarchy:

- `features` table — `backend/db/sqlite_migrations.py:546-560` (id, project_id, `parent_feature_id`,
  `data_json` catch-all).
- `feature_phases` table — `backend/db/sqlite_migrations.py:600-611` (id, `feature_id` FK, `phase`
  string, title, status, progress, total/completed task counts). Populated via wholesale
  delete-then-insert per feature sync: `backend/db/repositories/features.py:367-397`
  (`upsert_phases`, called from the feature parser's derived `phases: []` list — see
  `backend/parsers/features.py:1039-1187`, phase objects built at `:1146-1162` including
  `phaseBatches` from `_extract_phase_batches` at `:864-1020`, which already parses the
  `parallelization`/`batch_N` block into a `PlanningPhaseBatch` model, `backend/models.py:2055`).
  **This existing `_extract_phase_batches` logic is the closest current analog to wave extraction**
  — it derives ordered batches with `blockingTasks`/dependency evidence per phase, but it is scoped
  *within* one phase's progress doc, not across phases (i.e., it is NOT the same as `wave_plan.waves`,
  which barriers across phases).
- `tasks` table — `backend/db/sqlite_migrations.py:517-539` — has `parent_task_id`, `feature_id`,
  `phase_id` columns and index `idx_tasks_feature(feature_id, phase_id)` (`:538`). **This is
  already a parent/child hierarchy-capable schema** (task↔task via `parent_task_id`, task↔phase via
  `phase_id`, task↔feature via `feature_id`). It is under-used: the parser never sets
  `parent_task_id` (grep of `backend/parsers/progress.py` shows no such field on `ProjectTask`,
  `backend/models.py:1409-1424`), and dependency edges from `dependencies: []` in the YAML are
  truncated to 3 free-text tags rather than persisted rows (`backend/parsers/progress.py:196` —
  `tags=base_tags + [str(d) for d in deps[:3]] + extra_tags`).
- **No `wave`, `gate`, or `ac` concept exists anywhere** in `backend/models.py`,
  `backend/db/sqlite_migrations.py`, `backend/db/postgres_migrations.py`, or the repository layer.
  `acceptance_criteria` frontmatter is captured only as a raw list-of-strings inside
  `docTypeFields` (`backend/parsers/documents.py:79` — listed as an allowed key for `prd` doc type,
  `:73-80`), stored whole as JSON inside `documents.metadata_json`/`frontmatter_json`
  (`backend/db/sqlite_migrations.py:481,489`) — never decomposed into rows, never joined to a task.

**IntentTree `sync_import` is not present in this codebase.** Repo-wide search for
`mcp__intenttree` / `sync_import` found zero implementation hits; the only references are (a) this
charter itself (`plan-execution-session-correlation-charter.md:32,90`) and (b) an unrelated example
LAN API client (`examples/intenttree-client/`, a demo consumer of CCDash's own `/api/v1` REST
surface, not an ingestion path — `examples/intenttree-client/README.md:1-4`). `.claude/rules/
intenttree-integration.md` does not exist in this repo. **Conclusion: there is no existing
"IntentTree sync_import" ingestion path to reuse or avoid duplicating — this charter's premise that
it "already projects plan tasks[] onto a node tree" does not hold for this repository; treat that
as a stale/external assumption (flag for the schema-currency leg).** The only related PRD,
`docs/project_plans/PRDs/integrations/intenttree-session-correlation-v1.md`, is about IntentTree
*registering external sessions into CCDash* (a session-correlation write path), not about CCDash
importing IntentTree's task tree — orthogonal to this leg.

**Adjacent architectural precedent worth reusing (pattern, not storage):** the session-transcript
pipeline already builds a structured "intelligence index" out of semi-structured session content —
`TranscriptTaskRegisterItem`/`TranscriptWorkflowRegisterItem`/`TranscriptMarker`/`TranscriptPlanLink`
(`backend/models.py:200-234`) assembled into `TranscriptIntelligenceIndex`
(`backend/models.py:249-257`). This is computed request-time and **not persisted** (no DB table
found for it), but it establishes the repo's convention for turning loosely-structured source text
into typed register items with confidence scores and source-id backreferences — a reasonable
template for `plan_tasks`/`plan_acs` rows (typed, ID-linked, confidence-scored where the frontmatter
is ambiguous).

## Proposed Data-Model Shape

**Recommendation: new child tables under `features`, not a generic `level`+`parent_id` overlay on
`tasks`.** Rationale: `tasks` already carries live-execution semantics (status, owner, cost,
session_id) tied to *progress* docs; waves/gates/ACs are *plan-structure* metadata that should be
sourced from the *implementation-plan* file and refreshed independently of task execution state.
Conflating them into one polymorphic table risks the same "lossy squash" problem already observed
in `parse_progress_file` (phase → description string, batch → tag string, deps → truncated tags).

Proposed tables (SQLite; Postgres mirror required per CLAUDE.md dual-DDL invariant,
`CLAUDE.md:166`, and `COLUMN_PARITY_DRIFT_ALLOWLIST` at `backend/db/migration_governance.py:462`;
current schema version is 42 — `backend/db/sqlite_migrations.py:68`, `backend/db/postgres_migrations.py:46`):

```sql
-- plan_waves: one row per wave (a barrier across a set of phases), sourced from wave_plan.waves
CREATE TABLE plan_waves (
    id            TEXT PRIMARY KEY,      -- {feature_id}:wave-{n}
    feature_id    TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    plan_ref      TEXT NOT NULL,         -- source implementation-plan doc id/path
    wave_index    INTEGER NOT NULL,      -- 0-based position in wave_plan.waves
    phase_ids     TEXT NOT NULL,         -- JSON array of phase ids barriered in this wave
    status        TEXT DEFAULT 'pending' -- derived: pending/in-progress/done from member phases
);

-- plan_gates: exit/entry gates — sourced from prose ("karen milestone", "exit gate") + phase
-- success_criteria; MERGE CANDIDATE with feature_phases (see OQ-2) rather than a hard-separate table
CREATE TABLE plan_gates (
    id            TEXT PRIMARY KEY,
    feature_id    TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    phase_id      TEXT REFERENCES feature_phases(id) ON DELETE CASCADE,
    gate_type     TEXT DEFAULT 'exit',   -- exit | entry | milestone
    reviewer      TEXT DEFAULT '',       -- e.g. 'karen', 'task-completion-validator'
    status        TEXT DEFAULT 'pending',
    criteria_json TEXT DEFAULT '[]'      -- success_criteria rows: [{id, description, status}]
);

-- plan_tasks: extends existing tasks table semantics with structured dependency edges
-- (option: ADD COLUMN to existing `tasks`, not a new table — see below)
ALTER TABLE tasks ADD COLUMN wave_id TEXT REFERENCES plan_waves(id);

CREATE TABLE task_dependencies (        -- replaces the deps[:3]-as-tags lossy pattern
    task_id       TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on_id TEXT NOT NULL,        -- raw task-id token as written in frontmatter (pre-collision-id)
    PRIMARY KEY (task_id, depends_on_id)
);

-- plan_acs: the new entity type this leg is really about
CREATE TABLE plan_acs (
    id              TEXT PRIMARY KEY,   -- AC id as written, e.g. 'AC-1' / 'AC BWR-SEAM', scoped by feature
    feature_id      TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    task_id         TEXT REFERENCES tasks(id) ON DELETE SET NULL,  -- nullable: PRD ACs often predate task split
    description     TEXT DEFAULT '',
    target_surfaces TEXT DEFAULT '[]',  -- JSON array
    verified_by     TEXT DEFAULT '',
    status          TEXT DEFAULT 'pending',  -- pending | verified | failed
    source_doc_id   TEXT DEFAULT ''     -- documents.id this AC was parsed from (PRD or plan)
);
CREATE INDEX idx_plan_acs_feature ON plan_acs(feature_id);
CREATE INDEX idx_plan_waves_feature ON plan_waves(feature_id);
CREATE INDEX idx_plan_gates_feature ON plan_gates(feature_id, phase_id);
```

This follows the existing `feature_phases` precedent exactly (`backend/db/sqlite_migrations.py:600-611`):
a small child table, FK'd to `features`, delete-then-insert on each feature sync
(`backend/db/repositories/features.py:367-397` pattern). `plan_gates` is deliberately flagged as a
**merge candidate** with `feature_phases` (add `gate_status`/`gate_reviewer`/`criteria_json` columns
to `feature_phases` instead of a new table) since today's "gate" is really just an attribute of a
phase's exit condition, not an independent entity with its own lifecycle — this is OQ-2 below.

## Parser/Sync Integration Points

1. **New parser module** `backend/parsers/wave_plan.py` (sibling to `backend/parsers/progress.py`,
   `backend/parsers/features.py`) — parses `wave_plan.{phases,waves,serialization_barriers}` and
   top-level `acceptance_criteria`/`points` out of implementation-plan frontmatter. Implementation
   plans are already parsed generically by `backend/parsers/documents.py` (frontmatter → `documents`
   row, `implementation_plan` doc-type field allowlist at `:82-95` already includes `phases` and
   `dependencies` but not `wave_plan` or `acceptance_criteria` — those currently fall through into
   the doc-type-agnostic passthrough, confirmed only as a raw dict, not decomposed).
2. **AC extraction from PRDs** needs its own small extractor for the `### AC-N:` heading + bullet
   pattern seen in `system-wide-metrics-v1.md:327-402` (or a structured-frontmatter variant if the
   PRD instead uses list-of-dict `acceptance_criteria:` — both patterns exist in this repo's PRDs;
   the `prd` doc-type allowlist already reserves `acceptance_criteria` as a key,
   `backend/parsers/documents.py:79`).
3. **Sync-engine hook**: extend `_sync_features` (`backend/db/sync_engine.py:5368` onward) — right
   after `_extract_phase_batches`/phase-list construction (`backend/parsers/features.py:1146-1187`),
   add a call to the new wave-plan parser keyed off the feature's `implementationPlanRef`
   (already resolved elsewhere in the feature parser), and a corresponding
   `FeatureRepository.upsert_waves()` / `upsert_acs()` mirroring `upsert_phases()`
   (`backend/db/repositories/features.py:367-397`).
2b. **Task-dependency fix**: in `backend/parsers/progress.py:150,196` (`deps = task_raw.get(
   "dependencies", [])` → currently truncated into tags), add a real `dependencies: list[str]`
   field to `ProjectTask` (`backend/models.py:1395-1424`) and write full rows into the new
   `task_dependencies` table via a small addition to `TaskRepository.upsert`
   (`backend/db/repositories/tasks.py:18-70`) instead of (or alongside) the tag-truncation path —
   low-risk, additive, does not change existing tag behavior.
3. **Migration**: both `backend/db/sqlite_migrations.py` and `backend/db/postgres_migrations.py`
   need the new `CREATE TABLE` blocks plus a version bump past 42
   (`backend/db/sqlite_migrations.py:68`, `backend/db/postgres_migrations.py:46`) and an idempotent
   `_ensure_column`-style migration for `tasks.wave_id`, following the exact pattern CLAUDE.md
   mandates (`CLAUDE.md:166`) — dual DDL in the same change, `COLUMN_PARITY_DRIFT_ALLOWLIST` update
   if any column is intentionally one-sided (`backend/db/migration_governance.py:462`).
4. **Repository layer**: new `WaveRepository`/extend `FeatureRepository` with `upsert_waves`,
   `upsert_gates`, `upsert_acs`, `get_waves(feature_id)`, `get_acs(feature_id, task_id=None)` —
   same shape as existing `upsert_phases`/`get_phases` (`backend/db/repositories/features.py:367-406`).
5. **API/DTO surface** (out of strict scope per the charter's "extract and store" framing, but
   required for the data to be observable): new Pydantic DTOs `PlanWave`, `PlanGate`, `PlanAC` in
   `backend/models.py`, plus router additions — not estimated in detail here since the charter
   scopes this leg to ingestion feasibility, not surface design.

## Rough Estimate + H5 Anchor

**H5 anchor candidates** (comparable past CCDash features, effort-estimate blocks cited above):

- `branch-aware-planning-intelligence-v2` — **26 pts** — new registry class + 1 migration (2
  columns + 2 indexes) + cache-key dimension + FE chip + N=3-5 profiling
  (`branch-aware-planning-intelligence-v2.md:17,200`). Comparable in *migration discipline* (dual
  DDL, ADR-gated) but simpler data shape (no new tables, just columns).
- `ccdash-db-design-remediation-v1` — **~40 pts** — closest anchor for "several new/adjusted tables
  + repo layer + dual DDL parity remediation across the DB layer"
  (`docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md:15`).
- `session-transcript-orchestration-intelligence-v1` — **20 pts across 6 phases** — closest anchor
  for "parse semi-structured source content into typed register items with confidence + backrefs"
  (`docs/project_plans/implementation_plans/enhancements/session-transcript-orchestration-intelligence-v1.md:21`),
  i.e. the *parser design* work this leg most resembles, though that feature did **not** persist to
  DB (computed per-request) — persistence adds cost this anchor doesn't carry.
- `research-foundry-run-telemetry-v1` — **31 pts** (P1 8.5 / P2 10 / P3 6.5 / P4 6) — anchor for "new
  ingestion pipeline, new DTOs, phased rollout with per-phase pts"
  (`docs/project_plans/implementation_plans/features/research-foundry-run-telemetry-v1.md:15`).

**Estimate for hierarchy ingestion alone (extract + store, no correlation, no FE):**

| Component | Pts | Basis |
|---|---|---|
| Migration: `plan_waves`, `plan_gates`, `plan_acs`, `task_dependencies`, `tasks.wave_id` (dual DDL + parity check) | 5 | vs. branch-aware v2's 2-column/2-index migration priced at ~2pt of its 26 |
| `wave_plan` frontmatter parser (new module) | 3 | doc-type allowlist extension is trivial; wave/phase graph parsing has real edge cases (missing waves array, phase-id mismatches) |
| PRD-AC extraction (prose heading pattern + list-of-dict fallback) | 5 | two source shapes observed in-repo; heading-pattern regex is fragile — H4/H5 risk premium |
| Sync-engine hook + repository methods (`upsert_waves/gates/acs`, dependency-edge write) | 5 | mirrors existing `upsert_phases` (~409 LOC repo file) at roughly 1/3 the surface |
| Task-dependency de-truncation fix (`ProjectTask.dependencies`, table write) | 2 | small, additive, isolated to `progress.py` + `tasks.py` |
| Tests (migration parity, parser fixtures from real plan files, sync round-trip) | 5 | CLAUDE.md-mandated dual-DDL test discipline; ~20% of comparable anchors' pts is test-only |
| **Total** | **~25 pts** | mid-point between branch-aware v2 (26, columns-only) and research-foundry (31, new-pipeline) — reasonable given this leg adds 4 new tables but reuses the `feature_phases` sync pattern almost verbatim |

This does **not** include: FE surfaces to display the hierarchy, session-correlation joins (sibling
leg), or gate-merge-vs-split rework if OQ-2 resolves toward "gates are their own entity" (would add
~3-5 pts for the extra table + repo methods already partially priced above as a hedge).

## Open Questions (OQ-*)

- **OQ-1**: Is `wave_plan` frontmatter present broadly enough across real plans to justify a
  dedicated parser, or is `branch-aware-planning-intelligence-v2` an outlier? Only one plan was
  sampled here (~10K-token budget); the `schema-currency` sibling leg should confirm prevalence
  across all ~12 files in `docs/project_plans/implementation_plans/**` before committing to this
  scope.
- **OQ-2**: Should `plan_gates` be a standalone table or columns added to the existing
  `feature_phases` table? Current evidence shows gates are always phase-scoped exit conditions
  (`success_criteria` + prose "exit gate" + reviewer name), never independent of a phase in any
  sampled file — leaning toward **merge into `feature_phases`** (cheaper, ~3-5pt savings), but not
  confirmed against a plan with a genuinely cross-phase/wave-level gate.
- **OQ-3**: AC↔task linkage is currently prose-only and split across two documents (PRD `AC-N`
  headings vs. plan markdown-table `Acceptance Criteria` column citing the same AC by free text,
  `branch-aware-planning-intelligence-v2.md:409` vs `system-wide-metrics-v1.md:335`). Building
  `plan_acs.task_id` reliably may require fuzzy matching or an authoring-convention change (add an
  `ac_ref:` column to the plan's task table) — not purely a parsing problem.
- **OQ-4**: `task_dependencies.depends_on_id` stores the raw frontmatter task-id token, but the
  actual `tasks.id` primary key is collision-hardened via `_task_storage_id(raw_task_id,
  source_file)` (`backend/db/sync_engine.py:276-289`). Cross-phase dependencies (a task in P2
  depending on a task in P1, different source files) will need a resolution step at write time,
  not just a raw FK — small but real complexity not fully priced above.

## Confidence Rationale

0.72 (feasible-with-constraints band). Supporting: integration points are concretely enumerated
against real file:line locations, the existing `feature_phases`/`tasks` schema provides a proven,
directly-reusable pattern (delete-then-insert child table keyed to `features`), and two solid H5
anchors (`ccdash-db-design-remediation-v1` ~40pts, `session-transcript-orchestration-intelligence-v1`
20pts) bound the estimate. Held below 0.8 because: (1) only one `wave_plan`-bearing plan was sampled
against a ~10K-token budget, so prevalence/schema-stability across the corpus is unconfirmed (OQ-1);
(2) the gate entity design (OQ-2) and AC↔task linkage mechanism (OQ-3) are genuine open design
decisions, not just parsing gaps — the AC problem in particular may require an authoring-convention
change upstream (skill/schema), which is outside this leg's and possibly this exploration's control.
