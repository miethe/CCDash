---
schema_version: 2
doc_type: phase_plan
title: "Phase 11 — Launch-time profile/effort capture (fast-follow)"
status: draft
created: 2026-06-10
updated: 2026-06-10
phase: 11
phase_title: "Launch-time profile/effort capture (fast-follow)"
prd_ref: /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
feature_slug: ccdash-core-remediation
integration_owner: integration_owner
ui_touched: true
target_surfaces:
  - components/SessionInspector.tsx
  - types.ts
entry_criteria:
  - "Phase 3 complete (MCP/CLI/REST session detail green) — capture fields flow through the same detail surfaces."
  - "Phase 5 column-add pattern available as reference (dual SQLite+PG DDL + COLUMN_PARITY_DRIFT_ALLOWLIST update in the same change)."
  - "OQ-5 transport decision resolved as task T11-001 before any capture code is written (wrapper around ~/ica-claude.sh vs Claude Code SessionStart hook vs sidecar-file convention)."
exit_criteria:
  - "A session launched via ~/ica-claude.sh attributes profile=ica-delegate in the session record."
  - "Ultracode / effort tier populated when the capture sidecar supplies it; null-tolerant when absent."
  - "New columns (launcher, profile, effort_tier, model_variant) parity-clean on BOTH sqlite and postgres; COLUMN_PARITY_DRIFT_ALLOWLIST updated in the same change."
  - "Frontend fallbacks for profile/effort/launcher/model-variant render without crash when fields are absent or null (R-P2)."
  - "Runtime smoke for SessionInspector recorded against a live dev server (R-P4); not substitutable by unit-test pass."
  - "task-completion-validator sign-off."
---

# Phase 11 — Launch-time profile/effort capture (fast-follow)

## Overview

This is the ONLY path to two attributes that the diagnostic verified are **data-absent in current session JSONL logs**: the `ica-delegate` launcher profile and the Ultracode/effort tier (and, for completeness, the model variant when the launcher knows it but the log records only a bare slug). Retrospective log mining cannot recover them — they exist only at launch time. See PRD §"Launch-time capture (Phase 11)" and decisions-block §"Locked operator decisions" item 2.

The mechanism is a thin **launch-time capture** seam: a wrapper/hook around the launch path records a small sidecar (launcher, profile, effort tier, model variant) keyed to the session; the parser ingests the sidecar and promotes those values to **first-class session fields** (new dual-backend columns + parity); the frontend surfaces them with explicit missing-field fallbacks. No retrospective backfill — sessions launched before this phase legitimately carry null capture fields (a contract state, not a bug, per CLAUDE.md resilience-by-default).

**Scope boundaries (do not exceed):**
- This phase does NOT touch pricing (Phase 6), the workflow.json sidecar join (Phase 5), or the cross-project read path (Phase 0).
- The capture sidecar is a **separate convention** from the Phase 5 `workflow.json` sidecar; do not conflate them. They may share a parser module but carry distinct schemas.
- Effort tier and model variant are **best-effort**: populated only when the launcher supplies them. Absence is null, never a synthesized default.

**Column-drift hazard (high — see decisions-block Risk Hotspots):** Phases 5, 6, and 11 all add columns. The dual SQLite+PG DDL and the `COLUMN_PARITY_DRIFT_ALLOWLIST` update MUST land in the same change as the column add (T11-003). Phase 9's Bash-enabled PG seam review is the downstream hard gate; this phase ships parity-clean to make that gate pass.

**Architecture references (cite, do not re-read):** layered Router→Service→Repository and dual-backend conventions in `CLAUDE.md`; parser source-of-truth in `backend/parsers/sessions.py`; shared session-detail surfaces wired in Phase 3 (`backend/application/services/agent_queries/session_detail.py`).

## Agent Routing

Per decisions-block §Agent Routing (Phase 11) and §Model Routing. Primary executor **python-backend-engineer** (sonnet/adaptive); secondary **data-layer-expert** (columns/parity, sonnet/adaptive); FE work to **ui-engineer-enhanced** (sonnet/adaptive); docs to **documentation-writer** (haiku/adaptive). Phase has ≥2 owner specialties (backend parser + FE) with `files_affected` intersection on the session-detail contract → `integration_owner` required (R-P3) with an explicit seam task (T11-006). Quality gate: **task-completion-validator**, plus **runtime smoke** (R-P4) because `*.tsx` is in `files_affected`.

## Task Table

| Task ID | Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|-------------|-------|--------|
| T11-001 | Resolve capture transport (OQ-5) + sidecar schema | Decide the launch-time transport: wrapper script around `~/ica-claude.sh` vs Claude Code SessionStart hook vs sidecar-file convention. Define the capture sidecar schema (launcher, profile, effort_tier, model_variant, session correlation key) and where it is written so the parser can locate it. Record the decision inline in this phase file and as a short ADR note if it sets a lasting convention. | Transport selected with rationale; sidecar schema documented (fields + correlation key + on-disk location); decision is reversible-cost noted; no code written before this lands. | 1 pt | python-backend-engineer | sonnet | adaptive |
| T11-002 | Launch-time capture wrapper/hook | Implement the chosen transport from T11-001: a wrapper/hook on the launch path that, at session start, writes the capture sidecar with launcher, profile (e.g. `ica-delegate` when launched via `~/ica-claude.sh`), effort tier (Ultracode where the launcher exposes it), and model variant. Best-effort: omit fields the launcher cannot supply (write null/absent, never a default). Must not block or alter launch behavior on capture failure (fail-open). | See AC-11.A below. | 3 pts | python-backend-engineer | sonnet | adaptive |
| T11-003 | Dual-backend capture columns + parity | Add first-class session columns `launcher`, `profile`, `effort_tier`, `model_variant` to BOTH sqlite (`backend/db/repositories/sessions.py` schema/DDL) and postgres (`backend/db/repositories/postgres/sessions.py`) in the SAME change; update `COLUMN_PARITY_DRIFT_ALLOWLIST` in the same change; all columns nullable. Add a parity assertion test that fails if the column sets diverge between backends. Migration via `backend/db/migrations.py`. | See AC-11.B below. | 2 pts | data-layer-expert | sonnet | adaptive |
| T11-004 | Parser ingestion → first-class fields | Extend `backend/parsers/sessions.py` to locate and ingest the capture sidecar (per T11-001 correlation key) and promote launcher/profile/effort_tier/model_variant onto the session record written by the sync engine (`backend/db/sync_engine.py`). Null-tolerant: missing sidecar → all four fields null; partial sidecar → only present fields populated. Idempotent re-parse must not duplicate or clobber with stale nulls. | See AC-11.C below. | 2 pts | python-backend-engineer | sonnet | adaptive |
| T11-005 | Session-detail field exposure + FE fallbacks | Thread the four capture fields through the session-detail contract (`types.ts` + the Phase 3 detail service) so they reach `components/SessionInspector.tsx`, and render them with explicit absent/null fallbacks. No new endpoint — reuse the Phase 3 session-detail surface. | See AC-11.D below. | 2 pts | ui-engineer-enhanced | sonnet | adaptive |
| T11-006 | Seam integrity: capture → parser → detail surface | Integration-owner task. Prove the end-to-end seam: a sidecar written by T11-002 is ingested by T11-004, persisted via T11-003 columns, and surfaced via T11-005 — for the `~/ica-claude.sh` launch path specifically (profile=`ica-delegate`). Assert no field is dropped at any hand-off and that a pre-capture (null-sidecar) session renders cleanly. | See AC-11.E below. | 1 pt | integration_owner | sonnet | adaptive |
| T11-007 | Runtime smoke — SessionInspector | Start the dev server (`npm run dev`), open a captured session and a pre-capture (null-fields) session in SessionInspector; confirm profile/effort/launcher/model-variant render for the captured one and fallbacks render (no crash) for the null one. Record evidence per CLAUDE.md runtime smoke gate; if runtime unavailable, set `runtime_smoke: skipped` with reason — a clean unit-test pass is NOT a substitute (R-P4). | Browser smoke recorded for both scenarios at the target viewport; SessionInspector renders without console errors in both; evidence attached to progress file. | 1 pt | ui-engineer-enhanced | sonnet | adaptive |
| T11-008 | Phase doc + capture-convention note | Document the launch-time capture convention (transport, sidecar schema, correlation, fail-open semantics, null-field contract) for the Phase 12 CLAUDE.md rollup. Concise, usage-focused; pointer-layer for CLAUDE.md per progressive-disclosure rules. | Convention documented; ready for Phase 12 CLAUDE.md one-liner + path reference; no duplicated schema text across files. | 0.5 pts | documentation-writer | haiku | adaptive |

**Estimate total:** ~12.5 pts (decisions-block anchor: Phase 11 ~8 pts core capture mechanism + R-P3 seam + R-P4 smoke + dual-backend parity plumbing per H6 hidden-plumbing allowance).

## Structured Acceptance Criteria

#### AC-11.A: Launch-time capture wrapper records the profile sidecar (fail-open)
- target_surfaces:
    - (backend — no UI surface; non-visual AC)
- propagation_contract: >
    The wrapper/hook (transport per T11-001) writes a capture sidecar at session start carrying
    launcher, profile, effort_tier, model_variant keyed to the session correlation key. The
    `~/ica-claude.sh` launch path MUST yield profile=`ica-delegate`. Ultracode/effort tier and
    model_variant are written only when the launcher exposes them.
- resilience: >
    Capture is fail-open: if the sidecar cannot be written, launch proceeds unaffected and the
    session simply carries null capture fields downstream. No field is ever synthesized to a default;
    unknown = absent = null.
- visual_evidence_required: false
- verified_by:
    - T11-006
    - T11-002

#### AC-11.B: Capture columns are parity-clean on both backends
- target_surfaces:
    - (backend/db — non-visual AC)
- propagation_contract: >
    Columns launcher, profile, effort_tier, model_variant added to sqlite
    (backend/db/repositories/sessions.py) and postgres
    (backend/db/repositories/postgres/sessions.py) in the SAME change, all nullable, with the
    COLUMN_PARITY_DRIFT_ALLOWLIST updated in the same change.
- resilience: >
    All four columns nullable; pre-capture sessions and partial sidecars persist as NULL without
    constraint violation. A parity assertion test fails the build if the two backends' column sets
    diverge.
- visual_evidence_required: false
- verified_by:
    - T11-003

#### AC-11.C: Parser ingests capture sidecar into first-class fields (null-tolerant, idempotent)
- target_surfaces:
    - (backend/parsers + sync — non-visual AC)
- propagation_contract: >
    backend/parsers/sessions.py locates the capture sidecar by the T11-001 correlation key and
    promotes launcher/profile/effort_tier/model_variant onto the session record persisted by
    backend/db/sync_engine.py.
- resilience: >
    Missing sidecar → all four fields null; partial sidecar → only present fields populated, others
    null. Re-parse is idempotent: it must not duplicate rows nor overwrite previously-captured
    values with stale nulls when the sidecar later disappears.
- visual_evidence_required: false
- verified_by:
    - T11-004
    - T11-006

#### AC-11.D: SessionInspector surfaces capture fields with missing-field fallbacks (R-P2)
- target_surfaces:
    - components/SessionInspector.tsx
    - types.ts
- propagation_contract: >
    The four capture fields are added to the session-detail type in types.ts and threaded through
    the Phase 3 session-detail service/contract (no new endpoint) into SessionInspector.
- resilience: >
    When any of profile / effort_tier / launcher / model_variant is absent or null, SessionInspector
    renders an explicit fallback (e.g. the row omitted or shown as a muted "Not captured" label with
    tooltip) and never crashes or renders "undefined". This is the mandatory FE-handles-missing AC for
    the Phase 11 columns (R-P2).
- visual_evidence_required: >
    Runtime smoke screenshots at desktop ≥1440px for BOTH a captured session (fields visible) and a
    pre-capture session (fallbacks visible).
- verified_by:
    - T11-007
    - T11-006

#### AC-11.E: End-to-end capture seam is unbroken for the ica-delegate path (R-P3)
- target_surfaces:
    - backend/parsers/sessions.py
    - backend/db/sync_engine.py
    - components/SessionInspector.tsx
    - types.ts
- propagation_contract: >
    A sidecar written by the wrapper (T11-002) for a `~/ica-claude.sh` launch is ingested by the
    parser (T11-004), persisted via the dual-backend columns (T11-003), and surfaced in
    SessionInspector (T11-005) as profile=`ica-delegate`, with effort_tier/model_variant populated
    when present. No field is dropped at any hand-off.
- resilience: >
    A session with no capture sidecar traverses the same path and renders cleanly with all four
    fields null/fallback. The seam test asserts both the populated and the null path.
- visual_evidence_required: >
    Covered by AC-11.D runtime smoke evidence (both scenarios).
- verified_by:
    - T11-006
    - T11-007

## files_affected

Populated from decisions-block key-files (NOT read in this planning pass):

- `backend/parsers/sessions.py` — capture-sidecar ingestion → first-class fields (T11-004)
- `backend/db/sync_engine.py` — persist captured fields on session record (T11-004)
- `backend/db/repositories/sessions.py` — sqlite capture columns + DDL (T11-003)
- `backend/db/repositories/postgres/sessions.py` — postgres capture columns + parity (T11-003)
- `backend/db/migrations.py` — migration for new columns (T11-003)
- `backend/application/services/agent_queries/session_detail.py` — expose capture fields on the Phase 3 detail contract (T11-005)
- `types.ts` — session-detail type extension for capture fields (T11-005)
- `components/SessionInspector.tsx` — surface capture fields + missing-field fallbacks (T11-005)
- launch-time wrapper/hook artifact — transport per T11-001 (e.g. wrapper around `~/ica-claude.sh` or a Claude Code SessionStart hook script); exact path fixed by T11-001 (T11-002)
- `COLUMN_PARITY_DRIFT_ALLOWLIST` (in the db parity-check module) — updated in the same change as T11-003

## Quality Gate

- **task-completion-validator** — verifies all ACs satisfied and tests green before `status: completed`.
- **Runtime smoke gate (R-P4 / CLAUDE.md)** — T11-007 must record a live SessionInspector smoke for both captured and null-field sessions. Phase 11 cannot be marked `completed` on a unit-test pass alone; if runtime is unavailable, an explicit `runtime_smoke: skipped` field + reason is required.
- **Column-parity** — T11-003 parity assertion test must be green; this phase ships parity-clean to satisfy the downstream Phase 9 Bash-enabled PG seam review.

## Dependencies & Notes

- **Upstream:** Phase 3 (session-detail surfaces) and Phase 5 (column-add + dual-DDL pattern). Per decisions-block dependency map: `3 → 11`; Phase 11 is Wave 5.
- **Downstream:** Phase 12 (CLAUDE.md conventions rollup, CHANGELOG, karen end-of-feature) consumes T11-008's capture-convention note.
- **No retrospective backfill:** sessions launched before this phase legitimately carry null capture fields — a contract state, not a defect (CLAUDE.md resilience-by-default; PRD §Non-Goals "no retrospective log mining").
- **Single-thread caution:** `sync_engine.py` is a shared-file hotspot (decisions-block Risk Hotspots). If Phase 11 executes concurrently with any residual Phase 5/7/8 sync edits, serialize the `sync_engine.py` edits — no parallel agents on that file.
