---
title: "PRD: Release Versioning v1"
schema_version: 2
doc_type: prd
status: draft
created: 2026-04-28
updated: 2026-04-28
feature_slug: release-versioning-v1
feature_version: "v1"
prd_ref: null
plan_ref: null
related_documents:
  - .claude/skills/release/SKILL.md
  - .claude/skills/release/SPEC.md
  - .claude/skills/release/workflows/release-orchestration.md
  - .claude/skills/changelog-sync/SKILL.md
  - .claude/specs/version-bump-spec.md
  - .claude/specs/changelog-spec.md
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
  related_prds: []
spike_ref: null
adr_refs: []
charter_ref: null
changelog_ref: null
test_plan_ref: null
owner: nick
contributors: []
priority: medium
risk_level: low
category: infrastructure
tags: [prd, infrastructure, release, versioning, semver, changelog]
milestone: null
changelog_required: false
commit_refs: []
pr_refs: []
files_affected:
  - .claude/specs/version-bump-spec.md
  - .claude/specs/changelog-spec.md
  - .claude/hooks/check-changelog-entry.sh
  - .claude/hooks/check-changelog-entry.py
---

# PRD: Release Versioning v1

## 1. Goal

Establish a complete, automated release versioning system for CCDash from scratch: semver tagging, Keep-a-Changelog discipline, an audit gate that blocks tagging when coverage gaps exist, and a single-command release flow driven by the symlinked `release` and `changelog-sync` skills.

The immediate deliverable is a CCDash-local configuration layer (two spec files, optional hook) that makes the symlinked SkillMeat skills work correctly against CCDash's repo structure — without modifying the shared skills.

### Non-goals

- **GitHub Releases automation**: Deferred. The `gh release create` step from the orchestration workflow is available and may be used manually, but automation (CI trigger, draft-and-publish flow) is out of v1 scope. CCDash has no CI pipeline today.
- **SDK regeneration**: CCDash exposes a FastAPI backend but has no generated OpenAPI SDK client. The SkillMeat workflow Step 2 (Regen OpenAPI) and Step 3 (Regen SDK) do not apply. This spec explicitly skips them. If an `openapi.json` export is added in a future release, this spec must be updated to include that step.
- **PyPI / npm publishing**: CCDash packages are local-first and not published to registries in v1.
- **Nightly audit reconciliation**: Requires scheduled-ops-framework-v1; deferred (mirrors SkillMeat BL-1).

---

## 2. Version Targets Inventory

CCDash currently has **4 files** containing a version string that must move in lockstep on every release. There is no Python `__init__.py` version string in the main `backend/` package or `packages/ccdash_contracts` (the contracts `__init__.py` has no `__version__` attribute). The CLI `__init__.py` is also empty.

| # | File | Field | Current value |
|---|------|-------|---------------|
| 1 | `package.json` | `"version"` | `0.1.0` |
| 2 | `pyproject.toml` | `version =` | `0.1.0` |
| 3 | `packages/ccdash_cli/pyproject.toml` | `version =` | `0.1.0` |
| 4 | `packages/ccdash_contracts/pyproject.toml` | `version =` | `0.1.0` |

The authoritative list, bump commands, and validation checklist live in `.claude/specs/version-bump-spec.md` (to be authored in Phase 1). That file is the sole source of truth for bump targets — this PRD must not be updated as targets change; update the spec file instead.

**Versioning relationship between packages**: All four targets move to the same version on every release. The CLI depends on `ccdash-contracts>=0.1.0`; keeping them in lockstep avoids dependency constraint churn. If packages diverge in the future, the spec must be updated to reflect independent tracks.

---

## 3. CHANGELOG Rules

CCDash uses Keep-a-Changelog format. The existing `CHANGELOG.md` has an `[Unreleased]` section with substantial content and uses `## [Unreleased]` as the heading — fully compatible with `rollover-changelog.py`.

### Section headings (in priority order)

`Added` | `Changed` | `Fixed` | `Performance` | `Deprecated` | `Removed` | `Security` | `Docs`

The `Performance` section is already in use in the current `[Unreleased]` block and should be treated as a first-class section alongside the standard Keep-a-Changelog set.

### `[Unreleased]` discipline

- Every user-facing commit (feat, fix, perf, security, revert, deprecate, remove) requires an entry in `[Unreleased]` before a tag is cut.
- `[Unreleased]` must never be absent from `CHANGELOG.md` at any point in the development cycle.
- A tag must never be cut while `[Unreleased]` is the current-version heading — `rollover-changelog.py` renames it before the tag commit.

### Skip prefixes (exempt from audit coverage)

`chore` | `refactor` | `test` | `docs` | `ci` | `build` | `style` | `merge` | `version-bump`

These mirror the `SKIP_PREFIXES` set in `audit-coverage.py` and the skip-prefix list in `check-changelog-entry.sh`. The authoritative list lives in `.claude/specs/changelog-spec.md`.

### Entry format

Entries should be imperative mood, one line per logical change, optionally followed by a sub-bullet with scope context. Short SHAs in entries help `audit-coverage.py` match commits by SHA as a fallback to subject-substring matching.

---

## 4. Audit Gate Policy

`audit-coverage.py` requires a `--from-tag` ref. Because CCDash has no git tags yet, the first release audit must use the initial commit as the from-ref:

```bash
python .claude/skills/changelog-sync/scripts/audit-coverage.py \
  --from-tag "$(git rev-list --max-parents=0 HEAD)" \
  --to-ref HEAD \
  --changelog CHANGELOG.md
```

After the first tag is cut (`v0.2.0`), subsequent audits use the previous tag as `--from-tag`.

**Invariants** (mirrors SPEC.md §3):

1. `audit-coverage.py` must exit zero before `rollover-changelog.py` is run.
2. `rollover-changelog.py` must complete before `git tag` is created.
3. Agents must never pass `--force` to `audit-coverage.py` without an explicit human instruction in the current conversation.
4. When the audit fails, the skill halts, prints the full gap list, and instructs the operator to update `[Unreleased]` before re-running from Step 4. It does not proceed automatically.

---

## 5. Workflow Adaptation

The symlinked `release-orchestration.md` describes 9 steps. CCDash applies a subset:

| Step | SkillMeat description | CCDash disposition |
|------|-----------------------|--------------------|
| Step 1: Version Bump | 5 locations | **Apply** — 4 CCDash locations (see §2). Commands in `version-bump-spec.md`. |
| Step 2: Regen OpenAPI | `export_openapi_spec()` | **Skip** — no `openapi.json` in repo; no export function. Add to spec if this changes. |
| Step 3: Regen SDK | `pnpm generate-sdk` | **Skip** — no SDK client. |
| Step 4: Audit Gate | `audit-coverage.py` | **Apply** — use initial-commit ref for first release; git tag ref thereafter. |
| Step 5: Rollover | `rollover-changelog.py` | **Apply** — `--file CHANGELOG.md` (default; already correct). |
| Step 6: Skill Alignment | Advisory check on SPEC.md `aligned_app_version` | **Apply (advisory)** — check `.claude/skills/*/SPEC.md` for stale `aligned_app_version`. |
| Step 7: Git Commit | Stage known version files | **Apply** — stage the 4 version files + CHANGELOG.md only. No SDK files. |
| Step 8: Git Tag | Annotated tag + push | **Apply** — `git tag -a "v${NEW_VERSION}"` + `git push origin "v${NEW_VERSION}"`. |
| Step 9: GitHub Release | `gh release create` | **Apply (manual)** — use draft mode; publish manually. No CI automation in v1. |

### CCDash-specific Step 7 stage list

```bash
git add \
  package.json \
  pyproject.toml \
  packages/ccdash_cli/pyproject.toml \
  packages/ccdash_contracts/pyproject.toml \
  CHANGELOG.md
```

Do not use `git add -A` or `git add .`.

---

## 6. Initial Version Decision

**Recommendation: tag `v0.2.0`.**

Rationale:

- `v0.1.0` is the pre-history baseline. The repo has accumulated two substantial shipped features since the project was initialized: containerized deployment infrastructure (`infra/containerized-deployment-v1`) and runtime performance hardening. Both are documented in `CHANGELOG.md [Unreleased]`. Tagging the current state as `v0.2.0` is semantically accurate — meaningful user-facing work has shipped since `0.1.0`.
- Tagging the current tip as `v0.1.0` would require either back-dating the tag (confusing history) or pretending no changes occurred. Neither is clean.
- `v0.2.0` signals "first real release" without implying production readiness (major version zero preserves that signal per semver §4).
- The four version-target files are all at `0.1.0` and must be bumped to `0.2.0` as part of the Phase 4 validation run.

---

## 7. Local Specs to Author (Phase 1 Deliverables)

The symlinked skills reference two spec paths that do not exist locally. These must be authored before any release workflow step can run correctly.

### `.claude/specs/version-bump-spec.md`

Contents:
- CCDash-specific bump targets table (the 4 files in §2 with field names and sed/npm-version commands)
- Git tagging rules: annotated tags, `v` prefix, push to `origin`
- CHANGELOG roll-forward instructions (reference to rollover script)
- Validation checklist (version grep commands for all 4 targets)
- No SDK section (N/A for CCDash v1)
- No OpenAPI section (N/A until export is added)
- Skill SPEC.md alignment advisory (Step 6)

### `.claude/specs/changelog-spec.md`

Contents:
- Authoritative skip prefix list (matches `audit-coverage.py` `SKIP_PREFIXES` set exactly)
- Reportable prefix list (matches `REPORTABLE_PREFIXES`)
- CHANGELOG section headings including `Performance` as a first-class section
- Entry format convention
- `[Unreleased]` discipline rules
- Pre-commit hook behavior (skip-on-prefix logic, warn-only, `CCDASH_SKIP_CHANGELOG_CHECK` opt-out env var)

Both files must be present at `.claude/specs/` before any release skill invocation. The `audit-coverage.py` script reads the spec path for informational output only (`--spec` flag default is `.claude/specs/changelog-spec.md`); the skip/reportable lists are hardcoded in the script, so the spec is the human-readable contract, not a runtime config file.

---

## 8. Implementation Phases

### Phase 1: Author Local Specs

**Tasks**

| ID | Task | Assigned to |
|----|------|-------------|
| T1-001 | Author `.claude/specs/version-bump-spec.md` with CCDash bump targets, git tag rules, validation checklist | sonnet |
| T1-002 | Author `.claude/specs/changelog-spec.md` with skip prefixes, section headings, entry format, hook behavior | sonnet |
| T1-003 | Verify `audit-coverage.py --spec` path resolves (dry-run invocation with initial commit ref, expect parse of spec path) | sonnet |

**Exit criteria**: Both spec files exist; `python .claude/skills/changelog-sync/scripts/audit-coverage.py --from-tag $(git rev-list --max-parents=0 HEAD) --to-ref HEAD` runs to completion (exit 0 or 1 — execution success, not necessarily clean audit).

---

### Phase 2: Wire Scripts and Validate Dry-Run

**Tasks**

| ID | Task | Assigned to |
|----|------|-------------|
| T2-001 | Dry-run `rollover-changelog.py --version 0.2.0 --date <today> --dry-run` and confirm output matches current `[Unreleased]` content | sonnet |
| T2-002 | Run `audit-coverage.py` with initial-commit ref; record gap list; update `[Unreleased]` for any user-facing commits not yet represented | sonnet |
| T2-003 | Document the CCDash-adapted step sequence in `version-bump-spec.md §Release Procedure` (Steps 1, 4–9 applied; Steps 2–3 skipped) | sonnet |

**Exit criteria**: `audit-coverage.py` exits 0 (full coverage); `rollover-changelog.py --dry-run` exits 0 with expected diff.

---

### Phase 3: Optional Pre-commit Hook Install

**Tasks**

| ID | Task | Assigned to |
|----|------|-------------|
| T3-001 | Copy `.claude/hooks/check-changelog-entry.sh` and `.claude/hooks/check-changelog-entry.py` from SkillMeat if not already present (the `.claude/hooks/` dir is a symlink — confirm whether hooks exist locally or must be created) | sonnet |
| T3-002 | Replace `SKILLMEAT_SKIP_CHANGELOG_CHECK` env var name with `CCDASH_SKIP_CHANGELOG_CHECK` in hook scripts if hooks require local copies | sonnet |
| T3-003 | Install hook: `ln -s ../../.claude/hooks/check-changelog-entry.sh .git/hooks/commit-msg` | operator |
| T3-004 | Update `changelog-spec.md §Pre-commit Hook` with CCDash opt-out env var name | sonnet |

**Exit criteria**: Hook symlink exists; a test commit with a `feat:` subject and no staged CHANGELOG diff produces a warning but exits 0.

Note: Phase 3 is optional for the v1 release cut. If `.claude/hooks/` symlinks to SkillMeat and the hooks already use a generic env var, T3-002 and T3-004 may be skipped.

---

### Phase 4: Cut v0.2.0 Release (End-to-End Validation)

**Tasks**

| ID | Task | Assigned to |
|----|------|-------------|
| T4-001 | Bump all 4 version targets from `0.1.0` to `0.2.0` | sonnet |
| T4-002 | Run audit gate (Step 4); confirm exit 0 | operator |
| T4-003 | Run `rollover-changelog.py --version 0.2.0 --date <today>` | sonnet |
| T4-004 | Run Step 6 skill alignment advisory | sonnet |
| T4-005 | Stage version files + CHANGELOG.md; create release commit `chore(release): bump version to 0.2.0` | operator |
| T4-006 | Create annotated tag `v0.2.0`; push to origin | operator |
| T4-007 | Create GitHub draft release from tag; review and publish | operator |
| T4-008 | Run post-release validation checklist from `version-bump-spec.md` | sonnet |

**Exit criteria**: `git tag` lists `v0.2.0`; all 4 version targets read `0.2.0`; `CHANGELOG.md` has `[0.2.0]` section with date and empty `[Unreleased]` above it.

---

## 9. Acceptance Criteria

| # | Criterion | Target surfaces |
|---|-----------|----------------|
| AC-1 | `.claude/specs/version-bump-spec.md` exists with all 4 CCDash bump targets, CCDash-adapted release procedure (Steps 2–3 skipped), and validation checklist | `.claude/specs/version-bump-spec.md` |
| AC-2 | `.claude/specs/changelog-spec.md` exists with skip prefixes matching `audit-coverage.py` `SKIP_PREFIXES`, `Performance` section recognized, and pre-commit hook opt-out env var documented | `.claude/specs/changelog-spec.md` |
| AC-3 | `audit-coverage.py` runs to completion (exit 0 or 1) using initial-commit as `--from-tag` | `.claude/skills/changelog-sync/scripts/audit-coverage.py` |
| AC-4 | `rollover-changelog.py --dry-run` exits 0 and prints expected diff for v0.2.0 rollover | `.claude/skills/release/scripts/rollover-changelog.py`, `CHANGELOG.md` |
| AC-5 | All 4 version-target files read `0.2.0` after the release bump | `package.json`, `pyproject.toml`, `packages/ccdash_cli/pyproject.toml`, `packages/ccdash_contracts/pyproject.toml` |
| AC-6 | `CHANGELOG.md` contains `## [0.2.0]` with a date, and `## [Unreleased]` above it is empty | `CHANGELOG.md` |
| AC-7 | `git tag` lists `v0.2.0`; no other version tags exist | git repository |
| AC-8 | Audit gate (`audit-coverage.py`) is never bypassed with `--force` during the v0.2.0 release run | release procedure log |
| AC-9 | A second audit run after the release commit exits 0 (CHANGELOG fully covers all commits since initial commit) | post-release validation |

---

## 10. Risks and Mitigations

### R1: Symlinked skill drift if SkillMeat updates spec paths

**Risk**: The symlinked `release` skill (`SKILL.md`, `SPEC.md`, `release-orchestration.md`) references `skillmeat/`-specific paths (e.g., `skillmeat/__init__.py`, `skillmeat/web/package.json`) in its orchestration workflow. If SkillMeat updates those paths, the workflow becomes stale relative to CCDash.

**Mitigation**: The CCDash-local `version-bump-spec.md` encodes the CCDash-specific bump targets and step procedure. When executing a release, agents read `version-bump-spec.md` for the actual commands — not the SkillMeat-specific sed examples in `release-orchestration.md`. The workflow doc serves as structural guidance; the spec file is the executable contract.

If SkillMeat renames or restructures the skill, create a CCDash-local skill override at `.claude/skills/release/` (non-symlinked copy with CCDash spec paths) and remove the symlink. This override is deliberately deferred until drift is observed.

### R2: No prior git tags — audit requires initial-commit ref

**Risk**: `audit-coverage.py --from-tag` requires a valid git ref. With no tags, agents may not know to substitute the initial commit SHA.

**Mitigation**: Document the initial-commit pattern in `version-bump-spec.md §First-Release Procedure`:
```bash
FIRST_COMMIT=$(git rev-list --max-parents=0 HEAD)
python .claude/skills/changelog-sync/scripts/audit-coverage.py \
  --from-tag "$FIRST_COMMIT" --to-ref HEAD
```
After `v0.2.0` is tagged, subsequent releases use the previous tag normally.

### R3: `ccdash-contracts` version coupling

**Risk**: If `packages/ccdash_contracts` is ever published separately (e.g., for external integrations), its version track must diverge from the monorepo version. Moving it back to lockstep would require breaking changes to the spec.

**Mitigation**: Document in `version-bump-spec.md` that contracts and CLI are bumped in lockstep only while they remain private/local. If either is published, the spec must be updated to describe independent tracks before the next release.

### R4: Existing `[Unreleased]` section has mixed formatting

**Risk**: The current `[Unreleased]` block contains a duplicated entry block at the bottom (lines 49–52 of CHANGELOG.md) that is plain text without section headings, which `audit-coverage.py` subject-matching may not detect correctly.

**Mitigation**: Clean up the duplicate/raw entry block before running the audit gate in Phase 2 (T2-002). This is a one-time editorial fix to bring the CHANGELOG into canonical Keep-a-Changelog format; it is not a schema change.
