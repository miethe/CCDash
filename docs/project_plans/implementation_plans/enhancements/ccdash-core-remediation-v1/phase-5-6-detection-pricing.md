---
title: "Phase 5–6: Detection (log-derivable) + Pricing Correctness"
schema_version: 2
doc_type: phase_plan
status: draft
created: 2026-06-10
updated: 2026-06-10
phase: 5
phase_title: "Detection (log-derivable) + Pricing Correctness"
prd_ref: /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
feature_slug: ccdash-core-remediation
covers_phases: [5, 6]
# Phase 5 is FE+BE with a files_affected intersection on detection columns/types → R-P3 applies.
integration_owner: integration_owner
ui_touched: true
target_surfaces:
  - components/SessionInspector.tsx
  - components/Dashboard.tsx
  - types.ts
seam_tasks:
  - T5-009
entry_criteria:
  - "Phase 0 (cross-project session correctness) is green: project_id-scoped get_by_id/get_many_by_ids on both backends. Detection columns are written and read under project-safe paths."
  - "Phases 5, 7, 8 share runtime.py / sync_engine.py / config.py — sync/runtime edits are single-threaded across these phases (Risk Hotspots). Phase 5 holds exclusive ownership of parser/column edits during its execution window; no parallel agent edits the shared sync/runtime files in this window."
  - "Dev server can be brought up for runtime smoke (CLAUDE.md UI-phase gate). If runtime is unavailable, exit cannot be marked completed without explicit runtime_smoke: skipped + reason."
exit_criteria:
  - "A 1M-context session shows context_window 1M via workflow.json sidecar join (±1 min runId/taskId window)."
  - "Workflow groups root session + subagents correctly; subagent linkage survives a null/absent sidecar."
  - "Skill attribution populated where derivable from logs; absent = explicit null contract state, not error."
  - "All new detection columns present in dual DDL (SQLite + Postgres); COLUMN_PARITY_DRIFT_ALLOWLIST updated in the same change set; parity tests green on both backends."
  - "Every new optional backend field has a FE fallback UI state (R-P2): missing = contract state, not crash."
  - "_estimate_cost no longer defaults unknown slugs to Sonnet; novel claude-<family> id flagged unpriced; Fable in catalog with correct tier; pricing regression fixture green."
  - "FE renders an unpriced badge/indicator without crash when cost_estimate is null/unpriced."
  - "Runtime smoke recorded for the UI-touching surfaces (R-P4) for both phases, or runtime_smoke: skipped + reason."
  - "task-completion-validator sign-off for each phase."
---

# Phase 5–6: Detection (log-derivable) + Pricing Correctness

This file expands **Phase 5 (Detection, log-derivable)** and **Phase 6 (Pricing correctness)** of the CCDash Core Remediation v1 program. Architecture, layering, and conventions are governed by root `CLAUDE.md` and the PRD (`prd_ref`); this file does not restate them.

- Diagnostic / root cause: see PRD §Problem Statement (theme 4) and the diagnostic report referenced therein. **Do not re-derive.**
- Decisions / routing / risk: `.claude/worknotes/ccdash-core-remediation/decisions-block.md` (Phase Boundaries, Agent Routing, Model Routing, Risk Hotspots).
- AC schema for structured/multi-surface ACs: `.claude/skills/planning/references/ac-schema.md`.

## Plan Generator Rules applied

| Rule | Where it lands |
|------|----------------|
| **R-P1** (scope words → `target_surfaces`) | T5-008, T6-003 ACs expanded with `target_surfaces` lists |
| **R-P2** (new backend field → FE-handles-missing AC) | T5-008 (detection columns) and T6-003 (unpriced state) carry explicit `resilience` clauses |
| **R-P3** (≥2 owner specialties + `files_affected` intersection → `integration_owner` + ≥1 seam task) | Phase 5 frontmatter `integration_owner` + seam task **T5-009** (BE↔FE detection-field contract) |
| **R-P4** (any `*.tsx` in phase → runtime smoke task) | **T5-010** (Phase 5 smoke), **T6-005** (Phase 6 smoke) |

## Column conventions (apply to every task table)

- `Estimate` — task size (story points). Never reused for reasoning budget.
- `Model` — executor model. Per decisions block Model Routing: executors **sonnet/adaptive**; docs **haiku/adaptive**.
- `Effort` — reasoning budget (claude: `adaptive` | `extended`).
- `files_affected` — populated from decisions block / PRD key-files. Source files are **not** read during planning (context discipline).

---

## Phase 5 — Detection (log-derivable)

### Overview

Make log-derivable detection facts first-class and correct. Scope (decisions block Phase Boundaries / PRD FR-9, FR-10, FR-11):

1. **Model bare-slug**: normalize/store the bare model slug consistently so downstream pricing (Phase 6) and FE keys off a stable value.
2. **1M context via sidecar join**: parse `workflow.json` sidecars and join to session records on `runId`/`taskId` within a ±1 min window to attribute 1M-context (`[1m]`) sessions. This is a **join**, not a transcript heuristic.
3. **Workflow + subagent linkage hardening**: group a root session with its subagents; linkage must **survive a null/absent sidecar** (degrade, do not drop).
4. **Skill attribution**: attribute skill usage where derivable from logs; absent → explicit null.
5. **New columns**: add detection columns with **dual SQLite + Postgres DDL** and update `COLUMN_PARITY_DRIFT_ALLOWLIST` **in the same change set** (Risk Hotspots: column drift).
6. **FE surfacing + fallbacks**: surface new fields in the session detail/inspector + dashboard surfaces, each with an explicit missing-field fallback (R-P2).

This is a **FE+BE** phase with a `files_affected` intersection on the detection-field contract (`types.ts` + the response model that carries the columns) → `integration_owner` + seam task (R-P3). Sync/runtime/parser edits are single-threaded with Phases 7/8 (Risk Hotspots).

### Entry criteria

See frontmatter `entry_criteria`. Hard gates: Phase 0 green; exclusive ownership of parser/column/sync edits during this window; dev server available for smoke.

### Exit criteria

See frontmatter `exit_criteria` (1M join, workflow grouping survives null sidecar, parity-clean columns, FE fallbacks, runtime smoke, validator sign-off).

### Files affected (cited from decisions block / PRD — not read)

- `backend/parsers/sessions.py` — JSONL session parser; model bare-slug normalization, skill attribution, subagent linkage source.
- `backend/parsers/` (new) `workflow_sidecar.py` — `workflow.json` sidecar parser (new module; runId/taskId extraction).
- `backend/db/sync_engine.py` — sidecar→record join (±1 min window); writes new columns. **Shared with Phases 7/8 — single-thread.**
- `backend/db/migrations.py` — dual SQLite + Postgres DDL for new detection columns.
- `backend/db/repositories/sessions.py` + `backend/db/repositories/postgres/sessions.py` — column read/write (both backends); `COLUMN_PARITY_DRIFT_ALLOWLIST`.
- `backend/models.py` — response/DTO fields for new detection columns.
- `backend/config.py` — feature flag for sidecar join (if gated). **Shared with Phases 7/8 — single-thread.**
- `types.ts` — TS interfaces (`AgentSession` et al.) for new optional fields.
- `components/SessionInspector.tsx`, `components/Dashboard.tsx` — FE surfacing + fallback states.
- `backend/tests/` — parser, join, parity, linkage tests.

### Task table

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| T5-001 | Model bare-slug normalization | Normalize and persist the bare model slug from session logs to a stable canonical value consumed by pricing (Phase 6) and FE. | Bare slug parsed consistently; `[1m]`/variant suffixes handled per T5-003 join (slug itself stays bare); unit test pins canonical form for known + variant slugs. | 1 | python-backend-engineer | sonnet | adaptive |
| T5-002 | workflow.json sidecar parser | New `backend/parsers/workflow_sidecar.py` extracting `runId`/`taskId`/context-window/workflow metadata from `workflow.json` sidecars. | Parser returns structured sidecar record incl. runId, taskId, context_window; tolerates malformed/partial sidecar (returns None, logs at debug, no raise); unit test on valid + malformed + missing fixtures. | 2 | python-backend-engineer | sonnet | adaptive |
| T5-003 | 1M sidecar join (±1 min) | In `sync_engine.py`, join sidecar records to session records on runId/taskId within a ±1 min window; set `context_window` (e.g. `1M`) on matched sessions. | See **AC-5.1** below. | 2 | python-backend-engineer | sonnet | adaptive |
| T5-004 | Workflow + subagent linkage hardening | Group root session + subagents; populate `workflow_id` / `subagent_parent_id`; linkage must survive a null/absent sidecar (derive from log fields when sidecar absent). | See **AC-5.2** below. | 2 | python-backend-engineer | sonnet | adaptive |
| T5-005 | Skill attribution | Attribute `skill_name` where derivable from logs; absent → explicit null (not empty-string sentinel). | Skill attributed for fixture session that invokes a skill; absent for one that does not; null is round-tripped through repo→model→types as `null`; unit test. | 1 | python-backend-engineer | sonnet | adaptive |
| T5-006 | New detection columns — dual DDL | Add `workflow_id`, `subagent_parent_id`, `skill_name`, `context_window` (+ any T5-001 canonical-slug column) via dual SQLite + Postgres DDL in `migrations.py`; wire repo read/write on both backends. | See **AC-5.3** below. | 2 | data-layer-expert | sonnet | adaptive |
| T5-007 | COLUMN_PARITY_DRIFT_ALLOWLIST update | Update `COLUMN_PARITY_DRIFT_ALLOWLIST` in the **same change set** as T5-006; add/extend a parity test asserting SQLite and Postgres column sets match (allowlist-aware). | Parity test green on both backends; allowlist diff is committed with the migration (not post-hoc); intentional divergences (if any) are listed in allowlist with rationale comment. | 1 | data-layer-expert | sonnet | adaptive |
| T5-008 | FE surfacing + fallbacks | Add new optional fields to `types.ts`; surface in SessionInspector and Dashboard with explicit missing-field fallback states. | See **AC-5.4** below. | 2 | ui-engineer-enhanced | sonnet | adaptive |
| T5-009 | **Seam**: detection-field BE↔FE contract | Pin the contract for the new detection fields across the BE response model (`models.py`) and FE `types.ts`: names, optionality, null encoding. Add a contract assertion test (response-shape pin) and confirm FE types match. | See **AC-5.5** below. | 1 | integration_owner | sonnet | adaptive |
| T5-010 | **Runtime smoke** (R-P4) | Bring up dev server; in a browser, open SessionInspector for (a) a 1M session, (b) a session with subagents, (c) a session missing all new fields; confirm fields render and fallbacks render without crash. | Smoke recorded against `target_surfaces`; if runtime unavailable, record `runtime_smoke: skipped` + reason in progress (CLAUDE.md gate). | 1 | ui-engineer-enhanced | sonnet | adaptive |
| T5-011 | Phase 5 validation gate | task-completion-validator over AC-5.1…AC-5.5 + exit criteria; confirm parity tests and linkage-survives-null tests green. | Validator sign-off recorded; no exit criterion outstanding. | 1 | task-completion-validator | sonnet | adaptive |

### Phase 5 structured ACs

#### AC-5.1: 1M context is attributed via sidecar join
- propagation_contract: >
    `sync_engine.py` joins each `workflow.json` sidecar record (T5-002) to session
    records on matching `runId`/`taskId` where the sidecar mtime/timestamp falls within
    ±1 min of the session; on match it writes `context_window` (e.g. `1M`) to the
    session row (T5-006 column).
- resilience: >
    If no sidecar matches within the window, `context_window` is left null; the session
    is still ingested and grouped. No raise, no Sonnet-style silent default.
- visual_evidence_required: >
    Covered indirectly by T5-010 smoke (1M badge visible in SessionInspector); backend
    proof is the join unit/integration test, not a screenshot.
- verified_by:
    - T5-011
    - T5-010

#### AC-5.2: Workflow grouping survives a null sidecar
- propagation_contract: >
    Root session and its subagents are grouped via `workflow_id` / `subagent_parent_id`
    derived from log fields; when the sidecar is absent the grouping falls back to
    log-derived linkage and still produces a coherent workflow group.
- resilience: >
    Absent/null sidecar → subagent linkage still resolves from logs; a subagent never
    becomes orphaned or mis-parented because the sidecar was missing. Integration test
    asserts grouping identical (modulo context_window) with and without the sidecar.
- visual_evidence_required: false
- verified_by:
    - T5-011

#### AC-5.3: New detection columns are parity-clean on both backends
- propagation_contract: >
    `migrations.py` adds the columns with dual SQLite + Postgres DDL; both repositories
    read/write them; `COLUMN_PARITY_DRIFT_ALLOWLIST` is updated in the same change set.
- resilience: >
    Existing rows predating the columns read as null through repo→model; no migration
    backfill required for correctness (null is a valid contract state).
- visual_evidence_required: false
- verified_by:
    - T5-007
    - T5-011

#### AC-5.4: FE surfaces new detection fields with explicit fallbacks (R-P1, R-P2)
- target_surfaces:
    - components/SessionInspector.tsx
    - components/Dashboard.tsx
    - types.ts
- propagation_contract: >
    New optional fields are added to `AgentSession` (and related) in `types.ts`,
    flow through the existing apiClient/query path, and are read by SessionInspector
    (detail) and Dashboard (list/summary) components.
- resilience: >
    Missing `context_window` → no 1M badge (not a placeholder error). Missing
    `workflow_id`/`subagent_parent_id` → session renders standalone (no broken group
    affordance). Missing `skill_name` → skill chip omitted, not rendered as "null".
    Each absence is a contract state, never a thrown error or visible "undefined".
- visual_evidence_required: >
    Before/after screenshots of SessionInspector at desktop ≥1440px for a 1M session
    and a session missing all new fields.
- verified_by:
    - T5-010
    - T5-011

#### AC-5.5: Detection-field BE↔FE seam contract is pinned (R-P3)
- target_surfaces:
    - backend/models.py
    - types.ts
- propagation_contract: >
    Field names, optionality, and null encoding for `workflow_id`,
    `subagent_parent_id`, `skill_name`, `context_window` (+ canonical slug) are
    identical between the BE response model and FE `types.ts`. A response-shape pin
    test asserts the BE envelope; FE types are confirmed to match.
- resilience: >
    All new fields are optional/nullable on both sides; the contract test asserts that
    omitting any field is a valid response (not a 500, not a FE parse error).
- visual_evidence_required: false
- verified_by:
    - T5-011

### Phase 5 quality gate

- [ ] task-completion-validator sign-off (T5-011) over AC-5.1…AC-5.5 + exit criteria.
- [ ] Parity test (T5-007) green on SQLite and Postgres; allowlist committed with migration.
- [ ] Linkage-survives-null-sidecar integration test green (AC-5.2).
- [ ] Runtime smoke recorded (T5-010) or `runtime_smoke: skipped` + reason (CLAUDE.md UI-phase gate).

---

## Phase 6 — Pricing correctness

### Overview

Stop silently mispricing unknown models. Scope (decisions block Phase Boundaries / PRD FR-12, FR-13):

1. **No Sonnet-default for unknown**: `_estimate_cost` must not fall back to Sonnet pricing for an unrecognized slug.
2. **Explicit unpriced state**: an unknown `claude-<family>` slug returns an explicit `unpriced` status (distinct from `$0` and from a real price).
3. **Fable in catalog**: add Fable to the pricing catalog with the correct tier so Fable sessions price correctly (today they are silently Sonnet-mispriced — not $0).
4. **FE unpriced badge**: render an explicit unpriced indicator when `cost_estimate` is null/unpriced, without crashing.

Phase 6 consumes the canonical bare slug from Phase 5 (T5-001) but is otherwise independent (Wave 2). It touches one FE surface (`*.tsx`) → R-P4 runtime smoke applies.

### Entry criteria

- Phase 5 T5-001 (canonical bare slug) available, OR an interim agreement that Phase 6 keys off the existing slug field. Pricing logic must key off the same slug FE/Phase 5 surface.
- Dev server available for the unpriced-badge runtime smoke (or `runtime_smoke: skipped` + reason).

### Exit criteria

See frontmatter `exit_criteria` lines for pricing: no Sonnet-default; novel slug → unpriced; Fable catalog-correct; FE unpriced badge renders without crash; regression fixture green; validator sign-off.

### Files affected (cited from decisions block / PRD — not read)

- pricing catalog module (`pricing_catalog`) and `_estimate_cost` — location per decisions block (cost-estimation layer; do not read). Add generic family / explicit-unpriced handling + Fable entry.
- `backend/models.py` — cost-estimate DTO field carries `unpriced` status / nullable `cost_estimate`.
- `types.ts` — FE cost type allows unpriced/null.
- `components/SessionInspector.tsx`, `components/Dashboard.tsx` — unpriced badge.
- `backend/tests/` — pricing regression fixture (unknown slug, Fable, known slug).

### Task table

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| T6-001 | Remove Sonnet-default; add unpriced state | In `_estimate_cost`, replace the unknown-slug Sonnet fallback with an explicit `unpriced` status; nullable `cost_estimate`. Pricing catalog gains a generic-family / explicit-unpriced path. | See **AC-6.1** below. | 1 | python-backend-engineer | sonnet | adaptive |
| T6-002 | Add Fable to catalog | Add Fable to the pricing catalog with the correct input/output tier so Fable sessions price correctly (not Sonnet-mispriced, not $0). | Fable slug resolves to its own catalog tier; cost computed from Fable rates; regression fixture asserts Fable cost != Sonnet cost and != null. | 1 | python-backend-engineer | sonnet | adaptive |
| T6-003 | FE unpriced badge + fallback | Extend `types.ts` cost type for unpriced/null; render an explicit unpriced indicator in SessionInspector + Dashboard; no crash when `cost_estimate` is null. | See **AC-6.2** below. | 1 | ui-engineer-enhanced | sonnet | adaptive |
| T6-004 | Pricing regression fixture | Fixture covering: known slug (real price), Fable (Fable tier), novel `claude-<family>` (unpriced status, not Sonnet). Assert no Sonnet-default leakage. | See **AC-6.1 verified_by**; fixture green; explicit assertion that novel slug status == `unpriced` and price is null. | 1 | python-backend-engineer | sonnet | adaptive |
| T6-005 | **Runtime smoke** (R-P4) | Dev server up; open SessionInspector for (a) priced session, (b) Fable session, (c) novel/unknown-slug session; confirm unpriced badge renders for (c), correct cost for (a)/(b), no crash. | Smoke recorded against `target_surfaces`; if runtime unavailable, `runtime_smoke: skipped` + reason. | 0.5 | ui-engineer-enhanced | sonnet | adaptive |
| T6-006 | Phase 6 validation gate | task-completion-validator over AC-6.1/AC-6.2 + exit criteria; confirm regression fixture + smoke. | Validator sign-off; no exit criterion outstanding. | 0.5 | task-completion-validator | sonnet | adaptive |

### Phase 6 structured ACs

#### AC-6.1: Unknown slug → explicit unpriced, never Sonnet default
- propagation_contract: >
    `_estimate_cost` resolves the slug against the pricing catalog; an unrecognized
    `claude-<family>` (or any unknown) slug returns status `unpriced` with a null
    `cost_estimate`, surfaced through `models.py` to the API envelope.
- resilience: >
    `unpriced` is distinct from `$0` and from a real price. A future novel model id
    never silently inherits Sonnet (or any) rates; the regression fixture pins this.
- visual_evidence_required: false
- verified_by:
    - T6-004
    - T6-006

#### AC-6.2: FE renders unpriced state without crash (R-P1, R-P2)
- target_surfaces:
    - components/SessionInspector.tsx
    - components/Dashboard.tsx
    - types.ts
- propagation_contract: >
    `types.ts` cost type admits `unpriced`/null; SessionInspector and Dashboard read
    the cost field via the existing query path and branch on the unpriced status.
- resilience: >
    `cost_estimate: null` / status `unpriced` → an explicit "Unpriced" badge/indicator
    renders (with tooltip explaining the model is not in the pricing catalog); the
    component never renders `NaN`, `$null`, or throws.
- visual_evidence_required: >
    Screenshot of SessionInspector showing the unpriced badge for a novel-slug session
    at desktop ≥1440px.
- verified_by:
    - T6-005
    - T6-006

### Phase 6 quality gate

- [ ] task-completion-validator sign-off (T6-006) over AC-6.1/AC-6.2 + exit criteria.
- [ ] Pricing regression fixture (T6-004) green: known/Fable/novel slug behave correctly; no Sonnet-default leakage.
- [ ] Runtime smoke recorded (T6-005) or `runtime_smoke: skipped` + reason.

---

## Cross-phase notes

- **Shared-file discipline**: `sync_engine.py`, `runtime.py`, `config.py` are shared with Phases 7/8. Phase 5 must hold exclusive edit ownership during its window; no parallel agent edits these in the same wave (Risk Hotspots).
- **Column drift**: every column-adding task (T5-006) ships its `COLUMN_PARITY_DRIFT_ALLOWLIST` update (T5-007) in the same change set; Phase 9 performs the Bash-enabled Postgres seam review as the hard gate.
- **Resilience-by-default**: each new optional backend field (Phase 5 columns, Phase 6 unpriced) has a paired FE-handles-missing AC (R-P2): AC-5.4, AC-6.2.
- **Slug coupling**: Phase 6 pricing keys off the canonical bare slug from T5-001; keep the slug field name identical across both phases to avoid a hidden seam.
