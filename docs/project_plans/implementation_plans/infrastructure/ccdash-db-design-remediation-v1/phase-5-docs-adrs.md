---
schema_version: 2
doc_type: phase_plan
title: "P5 — Docs, ADRs & Deferred Items"
status: draft
created: 2026-06-03
updated: 2026-06-03
phase: 5
phase_title: "Docs, ADRs & Deferred Items"
feature_slug: ccdash-db-design-remediation
prd_ref: docs/project_plans/PRDs/infrastructure/ccdash-db-design-remediation-v1.md
plan_ref: docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md
---

# Phase 5 — Docs, ADRs & Deferred Items (~3 pts)

**Parent Plan**: `docs/project_plans/implementation_plans/infrastructure/ccdash-db-design-remediation-v1.md`

**Dependencies**: P2, P3, P4 all verified (P5 converges everything)
**Assigned Subagent(s)**: documentation-writer (haiku)
**Model**: haiku (documentation); sonnet for design spec authoring if needed (T5-005)
**Reviewer Gates**: task-completion-validator at exit; karen end-of-feature Tier 3 review

## Entry Criteria

- P2 quality gates passed (shared helper, health fields, counter all verified)
- P3 quality gates passed (concurrency guard, column-parity, ensure_table, idempotency all verified)
- P4 quality gates passed (retention enabled, VACUUM runbook validated, live VACUUM completed)
- `deferred_items_spec_refs` in parent plan frontmatter reflects any deferred items identified during P1–P4

## Task Table

| Task ID | Task Name | Description | Acceptance Criteria | Estimate | Subagent(s) | Model | Effort | Dependencies |
|---------|-----------|-------------|---------------------|----------|-------------|-------|--------|--------------|
| T5-001 | Ratify ADR-006 | Set `status: accepted` in `docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md`. Update `decision` section to reflect ratification date (2026-06-03) and final Option B implementation as shipped in P1. | ADR-006 file has `status: accepted`; `decision` section references the P1 implementation; no substantive content change (ratification only) | 0.5 pts | documentation-writer | haiku | adaptive | P2 verified |
| T5-002 | Ratify ADR-007 | Set `status: accepted` in `docs/project_plans/adrs/adr-007-db-write-failure-surfacing-standard.md`. Update `decision` section to reference the P2 `retry_on_locked` helper, health fields, and Prometheus counter as the concrete enforcement mechanism. | ADR-007 file has `status: accepted`; `decision` references `repositories/base.py:retry_on_locked`, `/api/health/detail` fields, and `ccdash_db_write_failures_total` | 0.5 pts | documentation-writer | haiku | adaptive | P2 verified |
| T5-003 | CLAUDE.md DB-write and registry conventions | Add to `CLAUDE.md` "Key Conventions" section: (a) "Registry is DB-authoritative per ADR-006; `projects.json` is import-seed/export-only; no production code may use the JSON-backed `ProjectManager` directly"; (b) "Every new write path in `backend/db/repositories/` must use `repositories/base.py:retry_on_locked` and ship a direct-count assertion test"; (c) "Independent SQLite connections must issue `PRAGMA busy_timeout = 30000`". Keep additions to ≤3 lines per point (progressive disclosure — detail lives in ADR files). | CLAUDE.md "Key Conventions" contains all three points; each ≤3 lines; references ADR-006/007 paths | 0.5 pts | documentation-writer | haiku | adaptive | T5-001, T5-002 |
| T5-004 | After-action report (AAR) | Write `.claude/worknotes/ccdash-db-design-remediation/aar.md` summarizing: (a) what the SPIKE predicted vs what was actually found during P1–P4 execution; (b) any scope changes (expanding or contracting); (c) estimate accuracy per phase (budgeted vs actual); (d) lessons learned for future DB-layer work. | AAR file exists; covers SPIKE prediction vs reality, scope delta, per-phase estimate accuracy, lessons learned; ≤200 lines | 1 pt | documentation-writer | haiku | adaptive | P2 verified, P3 verified, P4 verified |
| T5-005 | Design specs for deferred items | For each open item in the parent plan's "Deferred Items" triage table that still lacks a target spec path, author a `design_spec` at `docs/project_plans/design-specs/[item-slug].md` with `maturity: shaping` (or `idea` if research/SPIKE still needed), set `prd_ref` to the parent PRD. Append resulting path(s) to `deferred_items_spec_refs` in the parent plan frontmatter. Items eligible at time of writing: OQ-01 (`migrations_applied` ledger schema) if not resolved during P3; OQ-02 (WAL-checkpoint strategy) if not resolved during P4. Also: any column-drift items recorded in the lazy findings doc during P3. | Each open deferred item has a corresponding design_spec with `maturity` set; `deferred_items_spec_refs` in parent plan frontmatter is populated; OR explicitly documented as N/A with rationale | 0.5 pts | documentation-writer | sonnet | adaptive | T5-001–T5-004 |
| T5-006 | Finalize findings doc | If `findings_doc_ref` in parent plan frontmatter is populated (findings doc was created during P3 column-parity work): ensure all phase findings are captured, advance status from `draft` to `accepted`, and populate `promoted_to` with the parent plan path. If `findings_doc_ref` is null, mark as N/A. | Findings doc status is `accepted` and complete, OR T5-006 is marked N/A in the progress file | 0.5 pts | documentation-writer | haiku | adaptive | T5-005 |
| T5-007 | Plan frontmatter finalization | Set `status: completed` in the parent plan frontmatter; populate `commit_refs` (from git log), `pr_refs` (from PR), `files_affected` (final list), `updated` (today's date). Set `deferred_items_spec_refs` and `findings_doc_ref` to their final values. | Parent plan frontmatter complete per the field lifecycle spec; `status: completed`; `commit_refs` and `pr_refs` populated | 0.5 pts | documentation-writer | haiku | adaptive | T5-006 |

**Phase total: ~3 pts**

## Acceptance Criteria Traceability

| AC | Task(s) | Notes |
|----|---------|-------|
| AC-010a: ADR-006 `status: accepted` | T5-001 | Ratification |
| AC-010b: ADR-007 `status: accepted` | T5-002 | Ratification |
| AC-010c: CLAUDE.md conventions documented | T5-003 | Registry + write-path conventions |

## Phase 5 Quality Gates

- [ ] T5-001 ADR-006 has `status: accepted`
- [ ] T5-002 ADR-007 has `status: accepted`; references concrete P2 implementation artifacts
- [ ] T5-003 CLAUDE.md "Key Conventions" contains registry + write-path + busy_timeout convention lines
- [ ] T5-004 AAR exists at `.claude/worknotes/ccdash-db-design-remediation/aar.md`; covers prediction vs reality
- [ ] T5-005 all open deferred items have design_specs OR are documented as N/A; `deferred_items_spec_refs` updated
- [ ] T5-006 findings doc finalized (`status: accepted`) OR marked N/A
- [ ] T5-007 parent plan frontmatter complete (`status: completed`, `commit_refs`, `pr_refs`, `files_affected`)
- [ ] task-completion-validator sign-off
- [ ] karen end-of-feature Tier 3 review clean

## Post-Feature Wrap-Up

After all P5 gates pass, open the feature PR. The PR body should include:

- Summary: registry correctness (ADR-006), DB-write reliability (ADR-007), migration integrity, storage hygiene activation
- Feature Guide: `.claude/worknotes/ccdash-db-design-remediation/feature-guide.md`
- Test plan checklist: lock-injection test, direct-count test, health-field integration test, column-parity test, idempotency test, VACUUM runbook smoke
