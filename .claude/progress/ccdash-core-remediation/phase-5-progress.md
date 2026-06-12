---
type: progress
schema_version: 2
doc_type: progress
prd: "ccdash-core-remediation"
feature_slug: "ccdash-core-remediation"
phase: 5
status: completed
created: 2026-06-11
updated: 2026-06-11
prd_ref: docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
commit_refs: ["2c421e6"]
pr_refs: []
owners: ["python-backend-engineer"]
contributors: ["data-layer-expert", "ui-engineer-enhanced", "integration_owner"]
overall_progress: 100
runtime_smoke: skipped
runtime_smoke_reason: >
  Isolated worktree, no dev server; FE changes are additive optional-field renders
  with explicit fallbacks (SessionInspector detection badges + Dashboard detection-
  coverage note), type-checked via `npx tsc --noEmit` (0 errors in changed files).
  Browser smoke deferred to post-merge on the epic branch (CLAUDE.md UI-phase gate).
tasks:
  - id: "T5-001"
    name: "Model bare-slug normalization"
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: []
    evidence: "test:backend/tests/test_phase5_detection_parser.py"
  - id: "T5-002"
    name: "workflow.json sidecar parser"
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: []
    evidence: "test:backend/tests/test_workflow_sidecar_parser.py"
  - id: "T5-003"
    name: "1M sidecar join (±1 min)"
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: ["T5-002"]
    evidence: "test:backend/tests/test_phase5_sidecar_join.py"
  - id: "T5-004"
    name: "Workflow + subagent linkage hardening"
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: []
    evidence: "test:backend/tests/test_phase5_sidecar_join.py::LinkageSurvivesNullSidecarTests"
  - id: "T5-005"
    name: "Skill attribution"
    status: "completed"
    assigned_to: ["python-backend-engineer"]
    dependencies: []
    evidence: "test:backend/tests/test_phase5_detection_parser.py;test:backend/tests/test_phase5_detection_columns.py"
  - id: "T5-006"
    name: "New detection columns — dual DDL"
    status: "completed"
    assigned_to: ["data-layer-expert"]
    dependencies: ["T5-001"]
    evidence: "test:backend/tests/test_phase5_detection_columns.py"
  - id: "T5-007"
    name: "COLUMN_PARITY_DRIFT_ALLOWLIST update"
    status: "completed"
    assigned_to: ["data-layer-expert"]
    dependencies: ["T5-006"]
    evidence: "test:backend/tests/test_phase5_detection_columns.py::DetectionColumnParityTests;test:backend/tests/test_migration_governance.py"
  - id: "T5-008"
    name: "FE surfacing + fallbacks"
    status: "completed"
    assigned_to: ["ui-engineer-enhanced"]
    dependencies: ["T5-006"]
    evidence: "tsc:npx tsc --noEmit (0 errors in types.ts/SessionInspector.tsx/Dashboard.tsx/dashboard.ts)"
  - id: "T5-009"
    name: "Seam: detection-field BE↔FE contract"
    status: "completed"
    assigned_to: ["integration_owner"]
    dependencies: ["T5-006", "T5-008"]
    evidence: "test:backend/tests/test_phase5_detection_columns.py::DetectionSeamContractTests"
  - id: "T5-010"
    name: "Runtime smoke (R-P4)"
    status: "completed"
    assigned_to: ["ui-engineer-enhanced"]
    dependencies: ["T5-008"]
    evidence: "runtime_smoke: skipped (see frontmatter runtime_smoke_reason); tsc clean"
  - id: "T5-011"
    name: "Phase 5 validation gate"
    status: "completed"
    assigned_to: ["task-completion-validator"]
    dependencies: ["T5-001","T5-002","T5-003","T5-004","T5-005","T5-006","T5-007","T5-008","T5-009"]
    evidence: "validator:APPROVED (Wave 3 consolidated gate, AC-5.1..5.5 MET, 97 tests green)"
parallelization:
  batch_1: ["T5-001","T5-002","T5-004","T5-005"]
  batch_2: ["T5-003","T5-006"]
  batch_3: ["T5-007","T5-008"]
  batch_4: ["T5-009","T5-010"]
  batch_5: ["T5-011"]
---

# Phase 5 — Detection (log-derivable) Progress

Executed via ICA bash delegation (Agent tool overflows on repo CLAUDE.md). Single-threaded
owner of `sync_engine.py` / `config.py` edits within Wave 3 (barrier files).

## Guards (from plan §Contending / Unmerged Work)
- Do NOT add `source_ref`/`source_type` column or change the session upsert key (ADR-009-owned by streaming branch).
- Keep T5-003 sidecar→record join behaviorally additive and localized in `sync_engine.py`.
- Dual SQLite + Postgres DDL + `COLUMN_PARITY_DRIFT_ALLOWLIST` in the SAME change set (T5-006 + T5-007).

## Implementation notes

**Detection-field contract** (camelCase model / snake_case DB / FE):

| Concept | DB column | `AgentSession` | `types.ts` | null encoding |
|---|---|---|---|---|
| canonical bare slug | `model_slug TEXT DEFAULT ''` | `modelSlug: str=""` | `modelSlug?: string` | `""` |
| workflow id | `workflow_id TEXT` | `workflowId: Optional[str]` | `workflowId?: string\|null` | `null` |
| subagent parent | `subagent_parent_id TEXT` | `subagentParentId: Optional[str]` | `subagentParentId?: string\|null` | `null` |
| skill name | `skill_name TEXT` | `skillName: Optional[str]` | `skillName?: string\|null` | `null` |
| context window | `context_window TEXT` | `contextWindow: Optional[str]` | `contextWindow?: string\|null` | `null` (`"1M"` on match) |

- **T5-001/004/005** (parser): `_canonical_model_slug` strips `[1m]`-style variant suffixes; `model` stays untouched. `workflowId`/`subagentParentId` derived purely from log fields (family root / parent) — never from a sidecar, so linkage survives an absent sidecar (AC-5.2). `skillName` from log-derived `skillLoads` (None when none). Applied to claude_code + codex parsers.
- **T5-002** (`backend/parsers/workflow_sidecar.py`): standalone, pure, resilient (`None` on malformed/missing/partial, never raises); normalizes 1M markers to `"1M"`.
- **T5-003** (`sync_engine._join_sidecar_context_window`): localized, additive, gated by `CCDASH_SIDECAR_CONTEXT_JOIN_ENABLED` (default true). Matches on runId/taskId within ±60s of the session file mtime; sets `contextWindow` on the payload before envelope build. No match → null. Does not touch the upsert key or source/cursor boundary.
- **T5-006/007**: 5 columns added to BOTH `sessions` CREATE TABLE DDLs + `_ensure_column` ALTERs (SQLite + Postgres) + repo read/write on both backends. Columns are identical across backends → parity-clean by construction; intentionally NOT allowlisted (documented in `COLUMN_PARITY_DRIFT_ALLOWLIST`). `context_window` uses `COALESCE(excluded, existing)` so a sidecar-less re-ingest never wipes a prior 1M attribution.
- **Bug caught by tests**: the SQLite upsert VALUES placeholder count was off by one after adding columns (62 `?` vs 63 columns) — would have broken *all* SQLite session writes. Fixed to 63/63; Postgres balanced 57/57. Verified by `test_phase5_detection_columns.py` round-trip + the existing `test_session_repository_project_scope.py` / `test_session_ingest_service.py` regression suites (35 passed, 6 PG-skip).
- **T5-008** (FE): SessionInspector header gains conditional `contextWindow`/`skillName`/subagent badges (absent → not rendered). Dashboard gains a fallback-safe "Detection coverage" note derived from the bundle (omitted entirely when nothing detected). `SessionCardDTO` gained optional `context_window`/`skill_name` (forward-compatible; bundle may omit). `npx tsc --noEmit`: 0 errors in changed files (pre-existing baseline errors elsewhere unchanged).
- **Retry-safety**: detection columns are written through the EXISTING `retry_on_locked`-wrapped `upsert`/`_commit` path — no new write path, no new independent sqlite connection introduced.

## Tests added (all green; run as named files)
- `backend/tests/test_workflow_sidecar_parser.py` — 13 passed
- `backend/tests/test_phase5_detection_parser.py` — 12 passed
- `backend/tests/test_phase5_sidecar_join.py` — 8 passed (incl. linkage-survives-null, AC-5.2)
- `backend/tests/test_phase5_detection_columns.py` — 9 passed (parity AC-5.3, round-trip + seam AC-5.5)

Postgres parity is asserted statically via DDL/column-set + allowlist (no live PG in this worktree); live-PG e2e is Phase 9's hard gate.
