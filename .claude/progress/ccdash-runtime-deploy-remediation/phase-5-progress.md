---
schema_version: 2
doc_type: progress
phase: 5
phase_title: Docs finalization, deferred specs, and CHANGELOG
feature_slug: ccdash-runtime-deploy-remediation
status: completed
created: 2026-06-12
updated: '2026-06-14'
overall_progress: 100
completion_estimate: null
parallelization:
  strategy: batch-parallel
  batch_1:
  - T5-001
  - T5-002
  - T5-003
  - T5-005
  - T5-006
  - T5-007
  batch_2:
  - T5-004
  - T5-008
---

# Phase 5 Progress — Docs finalization, deferred specs, and CHANGELOG

## Objective

Close out the feature: author CHANGELOG entry, deployment guide update, CLAUDE.md pointer,
two DOC-006 design specs (D-001 correlation over-count, D-002 dynamic watcher rebind),
feature guide, and advance the findings doc to `status: accepted`. Blocked by P0, P1, P3, P4.
karen end-of-feature gate required before phase is sealed.

---

## Task Table

```yaml
tasks:
  - id: T5-001
    name: "CHANGELOG [Unreleased] entry"
    status: completed
    commit_ref: bec2e56
    assigned_to: changelog-generator
    assigned_model: haiku
    model_effort: adaptive
    description: >
      Add entry under [Unreleased] per Keep A Changelog: ### Fixed for W1
      (active-project first-load) and W3 (PG migration path); ### Changed for W2
      (watcher env var demoted to optional); ### Maintenance for W4.
      Set changelog_ref: CHANGELOG.md in plan frontmatter.

  - id: T5-002
    name: "Deployment guide update"
    status: completed
    commit_ref: b17a9b5  # deployment-guide edits (watcher section, optional env, seeded-pg smoke, rollback); earlier passes 9fe62d8/79e74e5
    assigned_to: documentation-writer
    assigned_model: haiku
    model_effort: adaptive
    description: >
      Update docs/guides/containerized-deployment-quickstart.md: registry-driven
      watcher section; CCDASH_WORKER_WATCH_PROJECT_ID optional semantics;
      seeded-PG smoke command; rollback plan (addendum to T1-007).

  - id: T5-003
    name: "CLAUDE.md pointer"
    status: completed
    commit_ref: 56845d3
    assigned_to: documentation-writer
    assigned_model: haiku
    model_effort: adaptive
    description: >
      Add <=3-line entry to CLAUDE.md: watcher fan-out is registry-driven (ADR-006);
      CCDASH_WORKER_WATCH_PROJECT_ID is optional scope filter; seeded-PG smoke at
      npm run docker:hosted:smoke:seeded-pg. Progressive-disclosure rule honoured.

  - id: T5-004
    name: "Plan frontmatter close-out"
    status: completed
    commit_ref: 145fc39
    assigned_to: documentation-writer
    assigned_model: haiku
    model_effort: adaptive
    description: >
      Set status: completed in the implementation plan frontmatter; populate
      commit_refs, updated, deferred_items_spec_refs (D-001 + D-002 spec paths).
      All frontmatter fields complete per lifecycle spec.

  - id: T5-005
    name: "DOC-006: F-W6-001 design spec"
    status: completed
    commit_ref: cc08859
    assigned_to: documentation-writer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Author docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md
      (maturity: idea): describe the over-count finding, why deferred, investigation
      needed if promoted, promotion trigger. Append path to deferred_items_spec_refs.

  - id: T5-006
    name: "DOC-006: W2 dynamic rebind spec"
    status: completed
    commit_ref: d4f27fd
    assigned_to: documentation-writer
    assigned_model: sonnet
    model_effort: adaptive
    description: >
      Author docs/project_plans/design-specs/w2-dynamic-watcher-rebind.md
      (maturity: shaping): boot-time-only limitation, rebind signaling design options,
      promotion trigger. Append path to deferred_items_spec_refs.

  - id: T5-007
    name: "Findings doc finalize"
    status: completed
    commit_ref: ce62faf
    assigned_to: documentation-writer
    assigned_model: haiku
    model_effort: adaptive
    description: >
      Advance .claude/findings/ccdash-core-remediation-findings.md from draft →
      accepted; populate promoted_to with this plan's path.

  - id: T5-008
    name: "Feature guide"
    status: completed
    commit_ref: ce62faf
    assigned_to: documentation-writer
    assigned_model: haiku
    model_effort: adaptive
    description: >
      Author .claude/worknotes/ccdash-runtime-deploy-remediation/feature-guide.md
      (<=200 lines, 5 required sections: What Was Built, Architecture Overview, How to
      Test, Coverage Summary, Known Limitations). Commit before PR open.
```

---

## AC Coverage

| AC ID | Description | Verified By | Verdict |
|-------|-------------|-------------|---------|
| AC-T5-001 | `CHANGELOG.md [Unreleased]` contains W1/W3/W2/W4 entries | T5-001 | verified |
| AC-T5-005 | D-001 design spec exists at `docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md` | T5-005 | verified |
| AC-T5-006 | D-002 design spec exists at `docs/project_plans/design-specs/w2-dynamic-watcher-rebind.md` | T5-006 | verified |
| AC-T5-004 | `deferred_items_spec_refs` populated with D-001 + D-002 paths; plan `status: completed` | T5-004 | verified |
| AC-T5-007 | `.claude/findings/ccdash-core-remediation-findings.md` `status: accepted`; `promoted_to` set | T5-007 | verified |
| AC-T5-008 | Feature guide exists; all 5 sections present | T5-008 | verified |

---

## Quick Reference

**Batch dispatch hints for orchestrator:**

- **batch_1** → *Six independent tasks — fan out in parallel (all prior-phase deps satisfied at P5 entry):*
  - `Task(changelog-generator, "T5-001: CHANGELOG.md [Unreleased] — Fixed W1+W3, Changed W2, Maintenance W4")`
  - `Task(documentation-writer, "T5-002: deployment guide update — watcher section + optional env var + seeded-PG smoke + rollback plan")`
  - `Task(documentation-writer, "T5-003: CLAUDE.md <=3-line watcher fan-out pointer")`
  - `Task(documentation-writer, "T5-005: DOC-006 design spec D-001 at docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md")`
  - `Task(documentation-writer, "T5-006: DOC-006 design spec D-002 at docs/project_plans/design-specs/w2-dynamic-watcher-rebind.md")`
  - `Task(documentation-writer, "T5-007: advance .claude/findings/ccdash-core-remediation-findings.md to status: accepted; set promoted_to")`
- **batch_2** → `Task(documentation-writer, "T5-004: plan frontmatter close-out — status: completed, commit_refs, deferred_items_spec_refs")` + `Task(documentation-writer, "T5-008: feature-guide.md at .claude/worknotes/ccdash-runtime-deploy-remediation/feature-guide.md — 5 sections, <=200 lines")`

**Quality gates before phase close:**
- `CHANGELOG.md [Unreleased]` contains entry for this feature
- `deferred_items_spec_refs` populated with D-001, D-002 spec paths
- `.claude/findings/ccdash-core-remediation-findings.md` `status: accepted`
- Plan frontmatter `status: completed`
- Feature guide committed
- karen end-of-feature APPROVED

**Key files:** `CHANGELOG.md`, `CLAUDE.md`, `docs/guides/containerized-deployment-quickstart.md`, `docs/project_plans/design-specs/f-w6-001-correlation-overcounting.md`, `docs/project_plans/design-specs/w2-dynamic-watcher-rebind.md`, `.claude/worknotes/ccdash-runtime-deploy-remediation/feature-guide.md`
