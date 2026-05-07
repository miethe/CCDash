---
schema_version: 2
doc_type: progress
title: "CCDash Claude Code Skill — Progress"
description: "Task tracker for the ccdash skill."
status: phase-5-complete
created: 2026-04-13
updated: 2026-05-06
feature_slug: ccdash-skill
prd_ref: .claude/skill-specs/ccdash-skill/prd.md
plan_ref: .claude/skill-specs/ccdash-skill/implementation-plan.md
---

# CCDash Skill — Progress

## Current Phase

**Phase 1 — MVP (Install + Status + Doctor)**

Exit criteria (from implementation plan):

- Fresh Claude Code session can walk an operator from zero-install to first `ccdash status project` via the skill.
- Server-down scenario routes through `ccdash doctor` interpretation, not raw HTTP error.

## Phase 1 Tasks

| ID | Task | Status | Owner | Notes |
|---|---|---|---|---|
| P1-01 | Author `SKILL.md` (trigger, router summary, when-not-to-use, pointers) | done | skill-creator | Focused on routing and guardrails |
| P1-02 | Author `references/cli-overview.md` | done | skill-creator | Snapshot current `ccdash --help` tree |
| P1-03 | Author `references/install-setup.md` | done | skill-creator | pipx + repo-local fallback |
| P1-04 | Author `references/command-status.md` and `references/command-doctor.md` | done | skill-creator | Include JSON field glossary |
| P1-05 | Author `references/output-modes.md` + `references/provenance.md` | done | skill-creator | Decision rules + ID/timestamp echo list |
| P1-06 | Author `recipes/unreachable-server.md` + `recipes/target-onboarding.md` | done | skill-creator | Deterministic step lists |
| P1-07 | Seed `scripts/router-table.json` with MVP intents | done | skill-creator | MVP rows: status, doctor, target, install |
| P1-08 | Seed `CHANGELOG.md` with initial skill version row | done | skill-creator | Dated entry referencing PRD |
| P1-09 | Smoke test: run skill against a live `ccdash` install end-to-end | done | nick | Covers install + status + simulated outage |

## Phase 1 Validation Checklist

- [ ] SKILL.md focused on routing and guardrails; detailed flows live in references/recipes
- [ ] All Phase 1 reference files present and cross-linked
- [ ] `scripts/router-table.json` validates as JSON and covers all MVP intents
- [ ] `ccdash doctor` appears in the fail-path for every query recipe
- [ ] Install recipe verified on a clean env (`.venv-standalone-cli/` or fresh pipx user)
- [ ] Operator smoke test passes (zero → `status project`)
- [ ] No false-fire on an unrelated coding prompt (manual check)

## Phase 2 — Full Current CLI Coverage (Done 2026-04-14)

| ID | Task | Status | Notes |
|---|---|---|---|
| P2-01 | `references/command-feature.md` | done | list/show/sessions/documents + JSON glossary |
| P2-02 | `references/command-session.md` | done | list/show/search/drilldown/family |
| P2-03 | `references/command-workflow.md` | done | failures subcommand |
| P2-04 | `references/command-report.md` | done | aar + feature, markdown default |
| P2-05 | `references/command-target.md` | done | 9 subcommands + keyring notes |
| P2-06 | `scripts/router-table.json` extensions | done | 22 intents covering full current CLI |
| P2-07 | `references/eval-scenarios.md` (10 pos / 10 neg) | done | Fixture for routing accuracy/precision checks |

## Phase 3 — Forensic Recipes (Done 2026-04-14)

| ID | Task | Status | Notes |
|---|---|---|---|
| P3-01 | `recipes/project-triage.md` | done | Branches on health signal |
| P3-02 | `recipes/feature-retrospective.md` | done | Ends with `report aar` rendered verbatim |
| P3-03 | `recipes/workflow-failure-rootcause.md` | done | Uses `session drilldown --concern` |
| P3-04 | `recipes/session-cluster-investigation.md` | done | `session family` bounded scope + drilldown |
| P3-05 | Cross-link recipes from references | done | Each command-*.md points to its recipes |

## Phase 4 — MCP-Aware Integration (Deferred)

Placeholder only. Do not execute until the MCP surface in the CLI/MCP enablement plan lands. Tasks: P4-01..P4-04 per implementation plan.

## Phase 5 — Container Project Onboarding And Watcher Binding (Done 2026-05-06)

| ID | Task | Status | Notes |
|---|---|---|---|
| P5-01 | `references/container-project-onboarding.md` | done | Covers `projects.json`, container paths, watcher env overlays, mounts, and validation |
| P5-02 | `recipes/container-project-onboarding.md` | done | Uses `backend/scripts/container_project_onboarding.py`; includes compose overlay and probe checks |
| P5-03 | `SKILL.md` trigger/runtime/do-not-say updates | done | Separates registry creation, project selection, and watcher binding |
| P5-04 | `scripts/router-table.json` intent update | done | Routes onboarding, watcher env, and healthy-empty-stack requests to the new recipe |

## Remaining

- **P1-09 smoke test** — requires a live `ccdash` install and running CCDash backend; operator-run, not part of this execution batch.
- Phase 4 (see above).

## Blockers / Open Questions

- Decide skill install location: user-global `~/.claude/skills/ccdash/` vs repo `.claude/skills/ccdash/`. Default to user-global since the skill is operator-facing and not repo-specific. Revisit if team wants it checked in.
- PRD Open Questions 1–4 (caching `target show`, MCP transport precedence, report-to-disk default, multi-project selection) stay open through Phase 1; revisit before Phase 3.

## Change Log

| Date | Change |
|---|---|
| 2026-04-13 | Initial progress tracker created alongside PRD and implementation plan. |
| 2026-04-14 | Phases 1-3 implemented in `.claude/skills/ccdash/`. Planning docs moved to `.claude/skill-specs/ccdash-skill/`. Phase 4 deferred; P1-09 smoke test still operator-pending. |
| 2026-05-06 | Phase 5 added container project onboarding and watcher-binding skill guidance grounded in the design spec, quickstart, runtime README, and helper script. |
