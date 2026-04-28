---
schema_version: 2
doc_type: implementation_plan
title: CCDash Release Versioning v1 — Implementation Plan
status: in-progress
created: 2026-04-28
updated: '2026-04-28'
feature_slug: release-versioning
feature_version: v1
prd_ref: /docs/project_plans/PRDs/infrastructure/release-versioning-v1.md
plan_ref: null
scope: Adopt semver tagging, Keep-a-Changelog discipline, audit-gated release flow modeled on the symlinked SkillMeat release skill — without modifying the skill itself.
effort_estimate: 8 story points
architecture_summary: CCDash-local spec layer at .claude/specs/ overrides SkillMeat skill assumptions (4 bump targets, no SDK, no openapi.json). Audit gate (audit-coverage.py) blocks tagging. Rollover script renames [Unreleased] to versioned heading.
related_documents:
- docs/project_plans/PRDs/infrastructure/release-versioning-v1.md
- .claude/specs/version-bump-spec.md
- .claude/specs/changelog-spec.md
- .claude/specs/ccdash-release-overrides-spec.md
- .claude/skills/release/SKILL.md
- .claude/skills/changelog-sync/SKILL.md
- CHANGELOG.md
references:
  user_docs: []
  context:
  - package.json
  - pyproject.toml
  - packages/ccdash_cli/pyproject.toml
  - packages/ccdash_contracts/pyproject.toml
  specs:
  - .claude/specs/version-bump-spec.md
  - .claude/specs/changelog-spec.md
  - .claude/specs/ccdash-release-overrides-spec.md
  related_prds: []
spike_ref: null
adr_refs: []
findings_doc_ref: null
changelog_required: true
owner: nick
contributors: []
priority: medium
risk_level: low
category: infrastructure
tags: [release, versioning, semver, changelog, infrastructure]
milestone: null
commit_refs: []
pr_refs: []
files_affected:
- .claude/specs/version-bump-spec.md
- .claude/specs/changelog-spec.md
- .claude/specs/ccdash-release-overrides-spec.md
- CHANGELOG.md
- package.json
- pyproject.toml
- packages/ccdash_cli/pyproject.toml
- packages/ccdash_contracts/pyproject.toml
---

# Implementation Plan: Release Versioning v1

## Overview

Stand up CCDash's first formal versioned release process. Source-of-truth specs live at `.claude/specs/` (CCDash-local). The `release` and `changelog-sync` skills are symlinked from SkillMeat and are read-only from CCDash's perspective per project policy — adaptations are documented in a CCDash-local override spec rather than skill edits.

## Phases

### Phase 1: Author CCDash-local specs (DONE)

Three CCDash-local specs authored; the symlinked skills now have the `.claude/specs/*` paths they reference.

| ID | Task | Status |
|----|------|--------|
| T1-001 | Author `.claude/specs/version-bump-spec.md` | completed |
| T1-002 | Author `.claude/specs/changelog-spec.md` | completed |
| T1-003 | Author `.claude/specs/ccdash-release-overrides-spec.md` (CCDash-specific deltas vs SkillMeat skill) | completed |

**Exit criteria** (met): All three spec files exist; audit-coverage.py runs to completion against initial-commit ref.

### Phase 2: Audit + dry-run validation (IN PROGRESS)

| ID | Task | Status |
|----|------|--------|
| T2-001 | Clean duplicate `### Fixed` and orphan bullets in CHANGELOG `[Unreleased]` (PRD R4) | completed |
| T2-002 | Backfill `[Unreleased]` to cover gaps from work landed before `[Unreleased]` was created (Planning Reskin v2 phases 0-7, addendum, feature-surface remediation, landing page, etc.) | in_progress |
| T2-003 | Run `audit-coverage.py` against `3782d3d^..HEAD` (the commit just before `[Unreleased]` was introduced); confirm exit 0 | in_progress |
| T2-004 | Run `rollover-changelog.py --dry-run --version 0.2.0`; confirm exit 0 with expected diff | pending |

**Exit criteria**: audit-coverage.py exits 0; rollover dry-run exits 0.

### Phase 3: Optional pre-commit hook (DEFERRED)

Skipped for v1. The `.claude/hooks/` directory is local CCDash; the symlinked skill provides hook scripts under SkillMeat's tree. Installing the warn-only `commit-msg` hook is deferred until after `v0.2.0` ships and the workflow is observed in practice.

### Phase 4: Cut v0.2.0 release

| ID | Task | Status |
|----|------|--------|
| T4-001 | Bump `package.json`, `pyproject.toml`, `packages/ccdash_cli/pyproject.toml`, `packages/ccdash_contracts/pyproject.toml` from `0.1.0` to `0.2.0` | pending |
| T4-002 | Re-run audit gate; confirm exit 0 | pending |
| T4-003 | Run `rollover-changelog.py --version 0.2.0 --date 2026-04-28` (live, non-dry-run) | pending |
| T4-004 | Skill alignment advisory check (read-only — do NOT modify symlinked skill files) | pending |
| T4-005 | Stage version files + CHANGELOG.md only (explicit list, no `git add -A`); commit `chore(release): bump version to 0.2.0` | pending |
| T4-006 | Create annotated tag `v0.2.0`; push to origin | pending |
| T4-007 | Create GitHub release from tag (manual draft → publish) | pending |
| T4-008 | Post-release validation: grep all 4 version files for `0.2.0`; confirm `git tag` lists `v0.2.0`; confirm `[Unreleased]` is now empty above `[0.2.0]` heading | pending |

**Exit criteria**: `git tag` shows `v0.2.0`; all 4 version targets read `0.2.0`; `CHANGELOG.md` has `## [0.2.0] - 2026-04-28` with empty `[Unreleased]` above.

## Acceptance Criteria

See PRD §9 (AC-1 through AC-9). All target surfaces:
- `.claude/specs/version-bump-spec.md` (AC-1, AC-5)
- `.claude/specs/changelog-spec.md` (AC-2)
- `.claude/skills/changelog-sync/scripts/audit-coverage.py` execution (AC-3, AC-8, AC-9)
- `.claude/skills/release/scripts/rollover-changelog.py` execution (AC-4)
- `package.json`, `pyproject.toml`, `packages/ccdash_cli/pyproject.toml`, `packages/ccdash_contracts/pyproject.toml` (AC-5)
- `CHANGELOG.md` (AC-6)
- git repository (AC-7)

## Out of Scope

- GitHub Releases automation (manual draft only)
- PyPI / npm publishing
- SDK regeneration (no SDK exists)
- `openapi.json` export step
- Nightly audit reconciliation
