---
schema_version: 2
doc_type: phase_plan
title: "CCDash Core Remediation v1 — Phase 4: Live Link Freshness"
status: draft
created: 2026-06-10
updated: 2026-06-10
phase: 4
phase_title: "Live Link Freshness"
prd_ref: /Users/miethe/dev/homelab/development/CCDash/docs/project_plans/PRDs/enhancements/ccdash-core-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/enhancements/ccdash-core-remediation-v1.md
feature_slug: ccdash-core-remediation
integration_owner: null
ui_touched: false
entry_criteria:
  - "Phase 0 (cross-project session correctness) is green: get_by_id/get_many_by_ids project-scoped on both backends. (Phase 4 is independent of the 1-chain but shares the project_id invariant.)"
  - "Diagnostic verdict accepted: cross-project watchers already register for all projects and survive active-switch (decisions block, Corrected Assumptions). Phase 4 hardens link freshness, not watcher registration."
  - "CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED currently defaults False; scoped rebuild is unproven on the watcher hot path."
exit_criteria:
  - "New subagent/session JSONL written under a watched path → linked session visible within one watcher cycle (~30 s), no server restart (integration test)."
  - "Assertion test proves NO global fingerprint scan executes on the watcher hot path when incremental rebuild is enabled."
  - "Family-scoped rebuild: only the affected session family's links are recomputed on a watcher event, not the whole project graph."
  - "CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED defaults True in backend/config.py; existing suites pass with new default."
  - "task-completion-validator sign-off; causal-link proof reviewed (ultrathink-debugger)."
---

# Phase 4: Live Link Freshness

## Overview

CCDash's document-linking layer cross-references sessions, documents, features, and tasks
(`backend/document_linking.py`). Today, scoped incremental link rebuild exists but is gated off
(`CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` defaults `False`, per `CLAUDE.md` conventions and PRD
§Configuration), so new subagent JSONL activity is only linked after a full rebuild — effectively
requiring a server restart or a global fingerprint scan to surface.

This phase **proves the scoped rebuild path on the watcher hot path, then flips the default on**.
The work is hardening + a causal-link proof, not a new linking engine: the incremental dispatch
already exists. Three deliverables: (1) prove a watcher filesystem event triggers a **family-scoped**
link rebuild (only the affected session family, no global fingerprint scan); (2) flip the config
default to `True`; (3) lock the behavior with a freshness integration test and a "no global scan on
hot path" assertion test.

Architecture, layering (Router→Service→Repository), and sync/watcher mechanics are defined in
`CLAUDE.md` (Backend Structure: `db/file_watcher.py`, `db/sync_engine.py`, `document_linking.py`) —
not restated here. Per the decisions block Risk Hotspots, `sync_engine.py` is a **shared-file
collision risk** with Phases 5/7/8; Phase 4 edits to that file must be minimal and single-threaded
(no parallel agents on `sync_engine.py`). Phase 4 is otherwise independent (P0, runs in Wave 2) and
does not block the transcript critical path.

**No UI surfaces are touched** (backend/config/test only) → no runtime smoke gate applies, and R-P4
does not trigger. The freshness signal is observable only via API/integration test, not a `.tsx`.

## Entry Criteria

See frontmatter `entry_criteria`. In summary: Phase 0 project-scoping is green; the diagnostic's
corrected assumption (watchers already register all projects, survive active-switch) is accepted as
the baseline; the incremental flag is confirmed to currently default `False`.

## Exit Criteria

See frontmatter `exit_criteria`. The hard gates: freshness within one watcher cycle without restart;
proven absence of a global fingerprint scan on the hot path; family-scoped (not project-wide)
rebuild; default flipped to `True` with suites green; validator + causal-link reviewer sign-off.

## Files Affected (from decisions block key-files — not opened)

| Path | Role in this phase |
|------|--------------------|
| `backend/document_linking.py` | Family-scoped incremental link rebuild entrypoint; ensure scoped dispatch avoids global fingerprint scan |
| `backend/db/file_watcher.py` | Watcher hot path that dispatches scoped link rebuild on new/changed JSONL |
| `backend/db/sync_engine.py` | Incremental link-rebuild dispatch on partial syncs (`CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` consumer); **shared-file collision risk — minimal, single-threaded edits** |
| `backend/config.py` | `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` default flip `False` → `True` |
| `backend/tests/` | New freshness integration test + no-global-scan assertion test + family-scope unit test + config-default test |

## Task Table

| Task ID | Name | Description | Acceptance Criteria | Estimate | Assigned Subagent(s) | Model | Effort |
|---------|------|-------------|---------------------|----------|----------------------|-------|--------|
| T4-001 | Trace scoped-rebuild causal path | Trace the existing incremental link-rebuild dispatch from `file_watcher.py` watcher event → `sync_engine.py` partial-sync handler → `document_linking.py` rebuild, with `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED=True`. Produce a written causal-link proof (in the progress file, not a standalone doc) identifying the exact dispatch seam and confirming no full-fingerprint scan is on that path. No code change. | AC-T4-001 (below) | 1 pt | ultrathink-debugger | sonnet | high |
| T4-002 | Family-scoped rebuild on watcher event | Ensure a single watcher filesystem event recomputes links for ONLY the affected session family (anchor-derived family per Phase 0 project-scoping), not the whole project graph. Scope the rebuild call in `document_linking.py` to the family; ensure `sync_engine.py` partial-sync dispatch passes family scope, not a project-wide trigger. Minimal edits to `sync_engine.py` (shared-file collision risk). | AC-T4-002 (below) | 1 pt | data-layer-expert | sonnet | adaptive |
| T4-003 | No global fingerprint scan on hot path | Verify (and, if the trace in T4-001 shows otherwise, fix) that the watcher hot path with incremental rebuild enabled does NOT trigger a global fingerprint/full-scan. Guard the scoped path so the global scan remains restart/full-sync-only. | AC-T4-003 (below) | 0.5 pt | data-layer-expert | sonnet | adaptive |
| T4-004 | Flip CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED default to True | Change the default in `backend/config.py` from `False` to `True`. Update `.env.example` and the `CLAUDE.md` flag note if it states the default (decisions block: "Incremental link rebuild ... default false"). Confirm env override still disables it. | AC-T4-004 (below) | 0.5 pt | data-layer-expert | sonnet | adaptive |
| T4-005 | Freshness integration test | New `backend/tests/` test: write a new subagent/session JSONL under a watched path, advance one watcher cycle, assert the linked session is queryable WITHOUT a server restart and within the cycle window (~30 s; use the test's deterministic watcher tick, not wall-clock sleep). | AC-T4-005 (below) | 0.5 pt | data-layer-expert | sonnet | adaptive |
| T4-006 | No-global-scan assertion test | New `backend/tests/` test that asserts, on a single watcher event with incremental rebuild enabled, the global fingerprint scan function is NOT invoked (spy/patch on the global-scan call site) and only the family-scoped rebuild runs. Also assert default-on via config import. | AC-T4-006 (below) | 0.5 pt | data-layer-expert | sonnet | adaptive |
| T4-007 | Update flag docs note | Update the `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` line in `CLAUDE.md` conventions to reflect the new `True` default and the proven scoped path. Docs-only; coordinate with Phase 12 to avoid CHANGELOG double-entry (Phase 12 owns CHANGELOG). | AC-T4-007 (below) | 0.25 pt | documentation-writer | haiku | adaptive |

**Total Phase 4 estimate**: ~3 pts (matches decisions block + PRD §Phase Summary).

## Acceptance Criteria (structured)

#### AC-T4-001: Causal-link proof for scoped rebuild dispatch
- propagation_contract: >
    Written proof traces watcher event (`backend/db/file_watcher.py`) → partial-sync handler
    (`backend/db/sync_engine.py`, gated by `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED`) →
    family-scoped rebuild (`backend/document_linking.py`). Proof names the exact dispatch
    function/seam and explicitly states whether any global fingerprint scan sits on that path.
- resilience: >
    If the trace finds the dispatch path absent or routing through the global scan, T4-001 records
    that as the finding and scopes T4-002/T4-003 fixes accordingly; the phase does not flip the
    default (T4-004) until the scoped path is proven.
- visual_evidence_required: false
- verified_by:
    - T4-006

#### AC-T4-002: Watcher event triggers family-scoped rebuild only
- propagation_contract: >
    A single watched-path JSONL write causes link recomputation for exactly the affected session
    family (anchor-derived `project_id` per Phase 0), invoked once via the partial-sync dispatch in
    `sync_engine.py`; the project-wide link graph is not rebuilt.
- resilience: >
    If the new JSONL cannot be resolved to a family (orphan/anchor-missing), the rebuild degrades to
    a no-op for that event and logs a deferred-link count (no silent drop, no fallback to global
    scan); the session is picked up on the next full sync.
- visual_evidence_required: false
- verified_by:
    - T4-005
    - T4-006

#### AC-T4-003: No global fingerprint scan on watcher hot path
- propagation_contract: >
    With `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED=True`, the watcher hot path never invokes the
    global fingerprint/full-scan routine; the global scan remains reachable only via explicit full
    sync or restart.
- resilience: >
    If incremental rebuild is disabled via env override, behavior falls back to the prior
    full/global path (unchanged), preserving the escape hatch.
- visual_evidence_required: false
- verified_by:
    - T4-006

#### AC-T4-004: Config default flipped to True with override intact
- propagation_contract: >
    `backend/config.py` reads `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` defaulting to `True`;
    `.env.example` reflects the new default; setting the env var to `false`/`0` still disables
    incremental rebuild.
- resilience: >
    Absent env var → `True` (new default); malformed value falls back to the documented default
    parsing in `config.py` (no crash on import).
- visual_evidence_required: false
- verified_by:
    - T4-006

#### AC-T4-005: New JSONL linked within one watcher cycle, no restart
- propagation_contract: >
    Integration test writes a new subagent/session JSONL under a watched path, drives one
    deterministic watcher tick, and asserts the linked session is queryable via the repository/query
    layer without restarting the runtime, within the cycle window (~30 s).
- resilience: >
    Test uses the watcher's deterministic tick/flush hook rather than wall-clock sleep; if the
    watcher cannot be driven deterministically in-test, the test fails loudly (no time-based flake).
- visual_evidence_required: false
- verified_by:
    - T4-005

#### AC-T4-006: No-global-scan + default-on assertion test green
- propagation_contract: >
    Test spies/patches the global-scan call site, fires one watcher event with incremental rebuild
    enabled, and asserts the global scan is not called while the family-scoped rebuild is called
    exactly once; a separate assertion imports `config` and confirms the default is `True`.
- resilience: >
    Test is backend-agnostic where the linking path is shared; if any path is SQLite-only vs
    Postgres-only, the assertion is parameterized or explicitly scoped with a recorded reason.
- visual_evidence_required: false
- verified_by:
    - T4-006

#### AC-T4-007: Flag documentation reflects new default
- propagation_contract: >
    `CLAUDE.md` `CCDASH_INCREMENTAL_LINK_REBUILD_ENABLED` line states default `True` and the proven
    scoped (family) rebuild path; CHANGELOG entry is deferred to Phase 12 (no duplicate entry here).
- resilience: false
- visual_evidence_required: false
- verified_by:
    - T4-006

## Quality Gate

**Phase 4 quality gates (all must pass before `status: completed`):**

- **task-completion-validator** — verifies every AC met, all Phase 4 tests green, default flipped,
  no regressions in existing link/sync suites.
- **ultrathink-debugger (causal-link proof)** — per decisions block Agent Routing (Phase 4 reviewer);
  signs off that the scoped-rebuild causal path is correct and the no-global-scan invariant holds on
  the hot path. (This is the special gate for Phase 4 noted in the decisions block.)
- **No runtime smoke gate**: Phase 4 touches no `*.tsx` / UI surface, so the `CLAUDE.md` runtime
  smoke gate and Plan Generator Rule R-P4 do not apply. Freshness is proven by integration/assertion
  tests (T4-005/T4-006), which are the substitute of record for this backend-only phase.
- **Shared-file discipline**: `sync_engine.py` edits are single-threaded with respect to Phases 5/7/8
  (Risk Hotspots); no parallel agents on `sync_engine.py` during Phase 4 execution.

## Notes & Cross-References

- PRD acceptance checklist: see PRD §"Live link freshness (Phase 4)" (3 items) and FR-8.
- Decisions block: Phase Boundaries (Phase 4 row), Agent Routing (data-layer-expert primary;
  ultrathink-debugger + task-completion-validator), Risk Hotspots (incremental-rebuild perf regression;
  shared sync-file collisions), Dependency Map (Phase 4 independent, Wave 2).
- Backend layering, watcher/sync mechanics, and the flag's role: `CLAUDE.md` (do not restate).
- Progress file: `.claude/progress/ccdash-core-remediation/phase-4-progress.md` (created at execution time).
