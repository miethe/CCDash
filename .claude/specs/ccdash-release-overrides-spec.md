---
title: "CCDash Release Workflow Overrides"
schema_version: 2
doc_type: spec
status: stable
created: 2026-04-28
updated: 2026-04-28
owner: nick
tags: [release, override, spec, infrastructure]
related_documents:
  - docs/project_plans/PRDs/infrastructure/release-versioning-v1.md
  - .claude/specs/version-bump-spec.md
  - .claude/specs/changelog-spec.md
  - .claude/skills/release/SKILL.md
  - .claude/skills/release/SPEC.md
  - .claude/skills/release/workflows/release-orchestration.md
  - .claude/skills/changelog-sync/SPEC.md
---

# CCDash Release Workflow Overrides

## Why This File Exists

The `release` skill (at `.claude/skills/release/`) and `changelog-sync` skill (at `.claude/skills/changelog-sync/`) are **symlinked from SkillMeat** and are shared, version-controlled, and read-only from CCDash's perspective.

Per CCDash project policy (CLAUDE.md), we do not edit symlinked skills in place. Instead, this file documents CCDash's adaptations to the symlinked skill's workflow without modifying the skill source.

The symlinked skill encodes SkillMeat assumptions that do not apply to CCDash (5 version-bump targets vs. 4, OpenAPI export capability, SDK client generation). This spec clarifies which workflow steps apply, which are skipped, and why — enabling agents and operators to follow the adaptation without confusion.

---

## Scope

This override covers:

- **Workflow step disposition**: which of the 9 orchestration steps apply to CCDash, which are skipped, and CCDash-specific rationale
- **Path bindings**: explicit mapping of symlinked-skill references to CCDash-local files
- **Forbidden modifications**: explicit list of changes not permitted (e.g., do not edit `.claude/skills/release/**`)
- **Drift response procedure**: what to do if SkillMeat updates the skill
- **Future update triggers**: conditions that require this file to be updated

This override does **NOT** cover:

- The audit and rollover scripts themselves — they are used as-is from the symlinked skill
- The bump-target list — that lives in `.claude/specs/version-bump-spec.md`
- CHANGELOG format and skip-prefix rules — those live in `.claude/specs/changelog-spec.md`
- CCDash-specific hook scripts — those live in `.claude/hooks/` (local, not symlinked)

---

## Workflow Step Disposition

The symlinked `release-orchestration.md` describes 9 steps. CCDash applies a subset:

| Step | SkillMeat Name | Applies? | CCDash Rationale |
|------|---|---|---|
| Step 1 | Version Bump | **Apply** | 4 CCDash targets (not 5). Bump commands in `version-bump-spec.md`. |
| Step 2 | Regen OpenAPI | **Skip** | No `openapi.json` exported in repo today. No OpenAPI export function. If CCDash adds OpenAPI export in a future release, update `version-bump-spec.md` to include Step 2 and unskip it here. |
| Step 3 | Regen SDK | **Skip** | No SDK client in repo. CCDash exposes a FastAPI backend and Python CLI, but does not generate a TypeScript/OpenAPI SDK. If an SDK is added, update `version-bump-spec.md` and unskip this step. |
| Step 4 | Audit Gate | **Apply** | Use initial-commit ref for first release (`v0.2.0`); thereafter use prior tag. Rule documented in `version-bump-spec.md §First-Release Procedure`. |
| Step 5 | Rollover CHANGELOG | **Apply** | Standard Keep-a-Changelog rollover. `--file CHANGELOG.md` (default; already correct). |
| Step 6 | Skill Alignment Check | **Apply (advisory)** | Check `.claude/skills/*/SPEC.md` for stale `aligned_app_version`. Stale skills do NOT block the release. Agents must not modify symlinked skill `SPEC.md` files; if drift is detected, raise it as a follow-up issue. See §Skill Alignment Advisory below. |
| Step 7 | Git Commit | **Apply** | Stage the 4 version files + `CHANGELOG.md` only. No SDK files. Stage list in `.claude/specs/version-bump-spec.md §Release Procedure, Staging`. |
| Step 8 | Git Tag | **Apply** | Annotated tag with `v` prefix: `git tag -a "v${NEW_VERSION}"`. Push to origin. |
| Step 9 | GitHub Release | **Apply (manual)** | Use `gh release create` with `--draft` mode. No CI automation in v1. Operator publishes manually after review. |

**Summary**: Apply: 1, 4, 5, 6, 7, 8, 9; Apply manual: 9; Advisory: 6; Skip: 2, 3

---

## Path Bindings

Every path referenced by the symlinked skill, with whether it is local-CCDash, symlinked, or shared:

| Path | Status | Notes |
|------|--------|-------|
| `.claude/specs/version-bump-spec.md` | **Local CCDash** | Defines 4 CCDash-specific bump targets. Authored in release-versioning-v1 Phase 1. |
| `.claude/specs/changelog-spec.md` | **Local CCDash** | Defines skip-prefixes matching `audit-coverage.py` `SKIP_PREFIXES`, `Performance` section, entry format, `[Unreleased]` discipline. Authored in release-versioning-v1 Phase 1. |
| `CHANGELOG.md` | **Local CCDash** | Tracked file. Keep-a-Changelog format with `[Unreleased]` section. Owned by developers; rollovers handled by script. |
| `.claude/hooks/` | **Local CCDash** | Symlink status unclear (may be symlink to SkillMeat or local). Scripts `check-changelog-entry.sh` and `check-changelog-entry.py` used via optional `commit-msg` hook. If hooks are symlinked from SkillMeat, no local modification needed. If local copies required, see Phase 3 in PRD. |
| `.claude/hooks/check-changelog-entry.sh` | **TBD** | Hook script for commit-msg gate. If local, replace env var `SKILLMEAT_SKIP_CHANGELOG_CHECK` with `CCDASH_SKIP_CHANGELOG_CHECK`. |
| `.claude/hooks/check-changelog-entry.py` | **TBD** | Python helper for hook. If local, adjust env var names. |
| `.claude/skills/release/SKILL.md` | **Symlinked (SkillMeat)** | Read-only. Do NOT edit. Route table and invocation guidance. |
| `.claude/skills/release/SPEC.md` | **Symlinked (SkillMeat)** | Read-only. Do NOT edit. Capability contract and invariants. May reference SkillMeat-specific paths (e.g., `skillmeat/api/openapi.json`); CCDash overrides in this file. |
| `.claude/skills/release/workflows/release-orchestration.md` | **Symlinked (SkillMeat)** | Read-only. Do NOT edit. Contains 9-step workflow. Steps 2–3 are skipped in CCDash; all others apply with CCDash-specific adaptations documented here. |
| `.claude/skills/release/scripts/rollover-changelog.py` | **Symlinked (SkillMeat)** | Used as-is. Invoked with `--file CHANGELOG.md --version X.Y.Z --date YYYY-MM-DD`. |
| `.claude/skills/release/scripts/audit-coverage.py` | **Symlinked (SkillMeat)** | Used as-is. For first release, invoked with `--from-tag $(git rev-list --max-parents=0 HEAD)`. Thereafter, `--from-tag <prior-tag>`. |
| `.claude/skills/changelog-sync/SPEC.md` | **Symlinked (SkillMeat)** | Read-only. Do NOT edit. Audit gate policy and invariants. |
| `package.json` | **Local CCDash** | Version string at `"version"` field. Bumped in Step 1. |
| `pyproject.toml` | **Local CCDash** | Version string at `version = ` field. Bumped in Step 1. |
| `packages/ccdash_cli/pyproject.toml` | **Local CCDash** | CLI package version. Bumped in Step 1. |
| `packages/ccdash_contracts/pyproject.toml` | **Local CCDash** | Contracts package version. Bumped in Step 1. |

---

## First-Release Exception

CCDash has no git tags yet. The first release audit (`audit-coverage.py`) must use the initial commit as the `--from-tag` ref:

```bash
FIRST_COMMIT=$(git rev-list --max-parents=0 HEAD)
python .claude/skills/changelog-sync/scripts/audit-coverage.py \
  --from-tag "$FIRST_COMMIT" \
  --to-ref HEAD \
  --changelog CHANGELOG.md
```

After the first tag is cut (`v0.2.0` per PRD §6), subsequent audits use the prior tag as `--from-tag`:

```bash
PRIOR_TAG=$(git describe --tags --abbrev=0)
python .claude/skills/changelog-sync/scripts/audit-coverage.py \
  --from-tag "$PRIOR_TAG" \
  --to-ref HEAD \
  --changelog CHANGELOG.md
```

This pattern is documented in `version-bump-spec.md §First-Release Procedure` for agents to reference during release execution.

---

## Skill Alignment Advisory

Step 6 (advisory) checks whether symlinked skills' `aligned_app_version` fields are behind the release version. **Stale skills do NOT block the release.**

**Constraint**: Agents must NOT modify symlinked skill `SPEC.md` files (e.g., `.claude/skills/release/SPEC.md`). If drift is detected:

1. **Log the drift**: note in the release notes which skills are stale.
2. **Raise a follow-up issue**: create a GitHub issue or `.claude/worknotes/` entry documenting the skill-update backlog.
3. **Do not patch in place**: if a symlinked skill requires an update, create a CCDash-local copy (non-symlinked) and replace the symlink. This is deferred until drift is substantial enough to warrant local maintenance.

Example:
```bash
# Detect stale skill (advisory, does not block release)
echo "Skills with stale aligned_app_version:"
grep -rl "aligned_app_version:" .claude/skills/*/SPEC.md 2>/dev/null | while read f; do
  ver=$(grep "aligned_app_version:" "$f" | sed 's/.*: *//' | tr -d '"')
  if [ "$ver" != "${NEW_VERSION}" ]; then
    echo "  $f → aligned at $ver (current: ${NEW_VERSION})"
  fi
done
```

If output shows stale skills, document and continue — the release is not blocked.

---

## Forbidden Modifications

**DO NOT:**

1. **Edit `.claude/skills/release/**` or `.claude/skills/changelog-sync/**`** — these are symlinked from SkillMeat. Any changes must be made upstream in SkillMeat or as a local copy (deferred until drift is observed).

2. **Pass `--force` to `audit-coverage.py` without explicit human authorization** — the audit gate is a safety mechanism. Bypassing it requires a human decision documented in the conversation.

3. **Use `git add -A` or `git add .` during release commits** — Stage only the 4 version files + `CHANGELOG.md`. Use the explicit staging command from `version-bump-spec.md §Release Procedure`.

4. **Skip Step 4 (audit gate) or reorder steps** — the workflow is linear and non-optional. Steps 2–3 are skipped (not applied), but the sequence 1, 4, 5, 6, 7, 8, 9 must be followed in order.

5. **Modify hook scripts in place without understanding symlink status** — `.claude/hooks/` may be symlinked from SkillMeat. Only create local copies if hooks require CCDash-specific env var names (e.g., `CCDASH_SKIP_CHANGELOG_CHECK` instead of `SKILLMEAT_SKIP_CHANGELOG_CHECK`).

---

## Drift Response Procedure

If SkillMeat updates the symlinked `release` or `changelog-sync` skill (e.g., adds a new step, renames a path, changes the script interface), the procedure is:

1. **Identify the delta**: compare the updated skill against this override spec.

2. **Document the drift**: add a dated note to this file in a new `§Observed Drift` section (see example below):
   ```
   ### Drift Entry — 2026-05-15
   SkillMeat updated `release-orchestration.md` to add a Step 2.5 ("Regen Config").
   Action: Updated this spec §Workflow Step Disposition to reflect new step.
   No code changes required.
   ```

3. **Update this spec** if the drift affects CCDash:
   - New step? Add a row to the disposition table.
   - Renamed path? Update the Path Bindings table.
   - Script interface change? Document in the FFX that invokes the script.

4. **Only as a last resort**: if the drift is substantial and patching this spec is insufficient, replace the symlinked skill with a local copy:
   ```bash
   rm -rf .claude/skills/release
   cp -r /path/to/skillmeat/.claude/skills/release .claude/skills/release
   # Then edit the local copy for CCDash-specific paths
   ```
   When a skill is copied locally, update `CLAUDE.md` `.claude/` directory inventory to reflect the change from "symlink to SkillMeat" to "local override."

---

## Future Update Triggers

This spec must be updated when any of the following occur:

| Trigger | Update Location | Action |
|---------|-----------------|--------|
| CCDash adds `openapi.json` export | §Workflow Step Disposition, Step 2 row | Unskip Step 2. Update `version-bump-spec.md` to add export command and validation. Update Path Bindings if a new export script is added. |
| CCDash adds a generated SDK client | §Workflow Step Disposition, Step 3 row | Unskip Step 3. Update `version-bump-spec.md` with SDK regeneration command. Update Path Bindings for new generated-file paths. |
| CI/CD is added to the project | §Workflow Step Disposition, Step 9 row | Change Step 9 from "Apply (manual)" to "Apply". Update `version-bump-spec.md §Release Procedure` with CI trigger instructions. |
| `ccdash-contracts` is published independently | §Workflow Step Disposition, Step 1 row; Path Bindings | Document independent version tracks in `version-bump-spec.md`. Update CCDash-specific version-bump logic. |
| SkillMeat renames a symlinked-skill path | §Path Bindings | Record the old and new paths. Update all references in `version-bump-spec.md` and `.claude/specs/changelog-spec.md`. |
| SkillMeat adds a new required workflow step | §Workflow Step Disposition | Add a new row. Assess whether it applies to CCDash or should be skipped. |
| `.claude/hooks/` is confirmed to be a local copy | §Path Bindings | Update hook script rows from "TBD" to "Local CCDash" or "Symlinked (SkillMeat)" as appropriate. |

---

## Cross-Links

- **CCDash Release Versioning PRD**: `docs/project_plans/PRDs/infrastructure/release-versioning-v1.md` — executive summary, non-goals, version targets inventory, and phase breakdown
- **Version Bump Spec**: `.claude/specs/version-bump-spec.md` — authoritative bump targets, commands, validation checklist, first-release procedure
- **Changelog Spec**: `.claude/specs/changelog-spec.md` — skip-prefixes, section headings, entry format, pre-commit hook behavior
- **Symlinked Release Skill**: `.claude/skills/release/SKILL.md` (read-only) — overview and quick-start routing
- **Symlinked Release Spec**: `.claude/skills/release/SPEC.md` (read-only) — capability matrix and invariants
- **Symlinked Release Workflow**: `.claude/skills/release/workflows/release-orchestration.md` (read-only) — 9-step orchestration with SkillMeat-specific paths and examples

---

## Summary

| Aspect | Status |
|--------|--------|
| Symlinked skills status | Read-only. Do not edit. Override via this file. |
| CCDash version targets | 4 files (package.json, pyproject.toml, CLI, contracts). Defined in `version-bump-spec.md`. |
| Workflow steps applied | 1, 4, 5, 6, 7, 8, 9. Skipped: 2, 3 (OpenAPI export and SDK regen not applicable). |
| Audit gate behavior | Blocks tagging on coverage gaps. First release uses initial-commit ref; thereafter uses prior tag. |
| Drift response | Document in this file. Only copy skill locally if drift is substantial. |
| Forbidden actions | Do not edit symlinked skills. Do not pass `--force` without human authorization. Do not use `git add -A` during release commits. |

