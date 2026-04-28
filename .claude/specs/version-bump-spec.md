---
title: "CCDash Version Bump Specification"
schema_version: 1
doc_type: spec
status: active
created: 2026-04-28
updated: 2026-04-28
category: infrastructure
tags: [spec, infrastructure, release, versioning, semver]
owner: nick
---

# CCDash Version Bump Spec

**Purpose**: This specification is the authoritative list of CCDash version string bump targets and the canonical procedure for updating all four files in lockstep during a release. It is consumed by the symlinked `release` skill (from SkillMeat) as the CCDash-local configuration layer. Do NOT modify the symlinked skill files — update this spec when targets or commands change.

---

## Version Targets Inventory

CCDash has **4 files** that contain a version string and must move in lockstep on every release.

| # | File | Field | Current Value | Grep Pattern |
|---|------|-------|---------------|--------------|
| 1 | `package.json` | `"version"` | `0.1.0` | `"version": "X.Y.Z"` |
| 2 | `pyproject.toml` | `version =` | `0.1.0` | `^version = "X.Y.Z"` |
| 3 | `packages/ccdash_cli/pyproject.toml` | `version =` | `0.1.0` | `^version = "X.Y.Z"` |
| 4 | `packages/ccdash_contracts/pyproject.toml` | `version =` | `0.1.0` | `^version = "X.Y.Z"` |

**Why all four**: The CLI depends on `ccdash-contracts>=0.1.0`. Keeping them in lockstep avoids dependency constraint churn. If either package is published independently in the future, this spec must be updated to reflect independent version tracks.

---

## Bump Commands (Copy-Pasteable)

**Prerequisite**: Set `NEW_VERSION` environment variable.

```bash
NEW_VERSION="0.2.0"  # Replace with actual target version
```

### Target 1: `package.json`

```bash
# Using npm version (recommended for npm ecosystem)
npm version ${NEW_VERSION} --no-git-tag-version

# OR: Using sed (if npm version is not available)
sed -i '' "s/\"version\": \"[0-9]*\.[0-9]*\.[0-9]*\"/\"version\": \"${NEW_VERSION}\"/" package.json
```

**Verification**:
```bash
grep '"version"' package.json | head -1
# Expected output: "version": "0.2.0",
```

### Target 2: `pyproject.toml` (root)

```bash
sed -i '' "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" pyproject.toml
```

**Verification**:
```bash
grep '^version = ' pyproject.toml
# Expected output: version = "0.2.0"
```

### Target 3: `packages/ccdash_cli/pyproject.toml`

```bash
sed -i '' "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" packages/ccdash_cli/pyproject.toml
```

**Verification**:
```bash
grep '^version = ' packages/ccdash_cli/pyproject.toml
# Expected output: version = "0.2.0"
```

### Target 4: `packages/ccdash_contracts/pyproject.toml`

```bash
sed -i '' "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" packages/ccdash_contracts/pyproject.toml
```

**Verification**:
```bash
grep '^version = ' packages/ccdash_contracts/pyproject.toml
# Expected output: version = "0.2.0"
```

---

## Git Tagging Rules

### Tag Format

- **Prefix**: `v` (e.g., `v0.2.0`, `v0.3.0`)
- **Type**: Annotated tags (not lightweight)
- **Message**: `Release v{version}` or a brief description

### Create Tag

```bash
NEW_VERSION="0.2.0"
git tag -a "v${NEW_VERSION}" -m "Release v${NEW_VERSION}"
```

### Push Tag to Origin

```bash
git push origin "v${NEW_VERSION}"
```

### Verify Tag

```bash
git tag --list "v*" | tail -1
# Expected output: v0.2.0 (the new tag)
```

---

## CHANGELOG Roll-Forward

**Invariant**: The `rollover-changelog.py` script (located at `.claude/skills/release/scripts/rollover-changelog.py`) must complete before the git tag is created.

The script:
1. Renames `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`
2. Inserts a fresh empty `## [Unreleased]` section above it
3. Exits with error if `[Unreleased]` is missing entirely

**Invocation**:

```bash
NEW_VERSION="0.2.0"
BUMP_DATE=$(date +%Y-%m-%d)
python .claude/skills/release/scripts/rollover-changelog.py \
  --version "${NEW_VERSION}" \
  --date "${BUMP_DATE}"
```

**Verify**:
```bash
head -20 CHANGELOG.md
# Expected: ## [Unreleased] (empty)
#           (blank lines)
#           ## [0.2.0] - 2026-04-28
```

---

## First-Release Procedure

Because CCDash has no prior git tags, the first-release audit gate uses the **initial commit** as the baseline:

```bash
FIRST_COMMIT=$(git rev-list --max-parents=0 HEAD)
python .claude/skills/changelog-sync/scripts/audit-coverage.py \
  --from-tag "$FIRST_COMMIT" \
  --to-ref HEAD \
  --changelog CHANGELOG.md
```

After the first tag is cut (e.g., `v0.2.0`), subsequent releases use the previous tag:

```bash
PREVIOUS_TAG=$(git describe --tags --abbrev=0)
python .claude/skills/changelog-sync/scripts/audit-coverage.py \
  --from-tag "$PREVIOUS_TAG" \
  --to-ref HEAD \
  --changelog CHANGELOG.md
```

---

## Step-by-Step Release Procedure (CCDash Adapted)

This procedure adapts the SkillMeat release-orchestration workflow to CCDash's structure. Steps 2 and 3 (OpenAPI and SDK regen) are **skipped** — CCDash has no generated OpenAPI spec or SDK in v1.

### Step 1: Version Bump (All 4 Targets)

Execute the copy-pasteable commands above for targets 1–4 in sequence. Verify each with the grep command provided.

```bash
# Summary: All 4 files now read the new version
```

### Steps 2–3: SKIP (No OpenAPI or SDK)

**Rationale**: CCDash does not export an `openapi.json` spec and has no generated SDK in v1. If an `openapi.json` export is added in a future release, update this spec to add regeneration steps here.

### Step 4: Audit Gate (Changelog Coverage)

Run the audit to ensure all user-facing commits since the last release are covered in `[Unreleased]`:

```bash
# First release (use initial commit as baseline):
FIRST_COMMIT=$(git rev-list --max-parents=0 HEAD)
python .claude/skills/changelog-sync/scripts/audit-coverage.py \
  --from-tag "$FIRST_COMMIT" \
  --to-ref HEAD \
  --changelog CHANGELOG.md

# Subsequent releases (use previous tag):
PREVIOUS_TAG=$(git describe --tags --abbrev=0)
python .claude/skills/changelog-sync/scripts/audit-coverage.py \
  --from-tag "$PREVIOUS_TAG" \
  --to-ref HEAD \
  --changelog CHANGELOG.md
```

**If audit fails**: The script will print the gap list (commits with no CHANGELOG entry). Update `[Unreleased]` in CHANGELOG.md to add missing entries, then re-run the audit. The audit must exit 0 before proceeding.

### Step 5: Rollover CHANGELOG

Rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD` and insert a fresh empty `[Unreleased]` above it:

```bash
NEW_VERSION="0.2.0"
BUMP_DATE=$(date +%Y-%m-%d)
python .claude/skills/release/scripts/rollover-changelog.py \
  --version "${NEW_VERSION}" \
  --date "${BUMP_DATE}"
```

### Step 6: Skill Alignment Advisory

Check the symlinked skill SPEC.md files for stale `aligned_app_version` fields (advisory only — does not block the release):

```bash
NEW_VERSION="0.2.0"
echo "Skills with stale aligned_app_version:"
grep -rl "aligned_app_version:" .claude/skills/*/SPEC.md 2>/dev/null | while read f; do
  ver=$(grep "aligned_app_version:" "$f" | sed 's/.*: *//' | tr -d '"')
  if [ "$ver" != "${NEW_VERSION}" ]; then
    echo "  $f → aligned at $ver (current: ${NEW_VERSION})"
  fi
done
# Note: Symlinked files should NOT be modified. If a skill needs an aligned_app_version update,
# it is a SkillMeat repository concern, not a CCDash concern.
```

### Step 7: Git Commit (4 Version Files + CHANGELOG)

**Critical**: Use explicit file list; do NOT use `git add -A` or `git add .`.

```bash
git add \
  package.json \
  pyproject.toml \
  packages/ccdash_cli/pyproject.toml \
  packages/ccdash_contracts/pyproject.toml \
  CHANGELOG.md

git commit -m "chore(release): bump version to 0.2.0"
```

### Step 8: Git Tag

Create an annotated tag with a `v` prefix and push to origin:

```bash
NEW_VERSION="0.2.0"
git tag -a "v${NEW_VERSION}" -m "Release v${NEW_VERSION}"
git push origin "v${NEW_VERSION}"
```

### Step 9: GitHub Release (Manual, Draft Mode)

Use the GitHub CLI to create a draft release:

```bash
NEW_VERSION="0.2.0"
gh release create "v${NEW_VERSION}" \
  --title "v${NEW_VERSION}" \
  --notes "See CHANGELOG.md for details." \
  --draft
```

Review the draft release on GitHub, then manually publish. Automation is deferred to a future phase.

---

## Validation Checklist

After bumping and tagging, verify:

```bash
NEW_VERSION="0.2.0"

# 1. All 4 version files read the new version
echo "=== Checking version targets ==="
grep '"version"' package.json | head -1
grep '^version = ' pyproject.toml
grep '^version = ' packages/ccdash_cli/pyproject.toml
grep '^version = ' packages/ccdash_contracts/pyproject.toml

# 2. CHANGELOG rolled forward correctly
echo "=== Checking CHANGELOG ==="
head -10 CHANGELOG.md | grep -E "^\[Unreleased\]|^\[${NEW_VERSION}\]"
# Expected: Two section headings (Unreleased above the new version)

# 3. Git tag exists
echo "=== Checking git tag ==="
git tag --list "v*" | tail -1
# Expected: v0.2.0

# 4. Audit passes on post-tag state
echo "=== Final audit check ==="
python .claude/skills/changelog-sync/scripts/audit-coverage.py \
  --from-tag "v${NEW_VERSION}" \
  --to-ref HEAD \
  --changelog CHANGELOG.md
# Expected: exit 0 (all commits since this tag are covered)
```

---

## Changelog Spec Reference

The changelog rules (skip prefixes, section headings, entry format, and pre-commit hook behavior) are documented separately in `.claude/specs/changelog-spec.md`. That file is the authoritative contract for:

- Skip prefix list (commits exempt from audit coverage)
- Reportable prefix list (commits that must have CHANGELOG entries)
- CHANGELOG section headings (including the CCDash-specific `Performance` section)
- Entry format conventions

The `.claude/skills/changelog-sync/scripts/audit-coverage.py` script reads both this spec and the changelog spec for validation and reporting.

---

## Future-Update Notes

### If OpenAPI Export is Added

When CCDash gains an `openapi.json` export capability (future release):

1. Add a **Step 2 (Regen OpenAPI)** section here with the export command
2. Add a **Step 3 (Regen SDK)** section here with the `pnpm generate-sdk` command (if an SDK is generated)
3. Update the list of bump targets in the Inventory table above

### If Packages Diverge

If `ccdash-cli` or `ccdash-contracts` are published independently to registries:

1. Update this spec to document separate version tracks (e.g., CLI tracks main version, contracts track independently)
2. Update the Inventory table to show which files bump together and which are independent
3. Update the release procedure to show separate bump sequences

---

## Example: Bumping to v0.2.0

```bash
#!/bin/bash
set -e

NEW_VERSION="0.2.0"
BUMP_DATE=$(date +%Y-%m-%d)

echo "Bumping CCDash version to ${NEW_VERSION}..."

# Step 1: Bump all 4 targets
npm version ${NEW_VERSION} --no-git-tag-version
sed -i '' "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" pyproject.toml
sed -i '' "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" packages/ccdash_cli/pyproject.toml
sed -i '' "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" packages/ccdash_contracts/pyproject.toml

echo "✓ Version targets bumped"

# Step 4: Audit gate
FIRST_COMMIT=$(git rev-list --max-parents=0 HEAD)
python .claude/skills/changelog-sync/scripts/audit-coverage.py \
  --from-tag "$FIRST_COMMIT" \
  --to-ref HEAD \
  --changelog CHANGELOG.md

echo "✓ Audit passed"

# Step 5: Rollover CHANGELOG
python .claude/skills/release/scripts/rollover-changelog.py \
  --version "${NEW_VERSION}" \
  --date "${BUMP_DATE}"

echo "✓ CHANGELOG rolled forward"

# Step 7: Commit
git add package.json pyproject.toml packages/ccdash_cli/pyproject.toml packages/ccdash_contracts/pyproject.toml CHANGELOG.md
git commit -m "chore(release): bump version to ${NEW_VERSION}"

echo "✓ Commit created"

# Step 8: Tag
git tag -a "v${NEW_VERSION}" -m "Release v${NEW_VERSION}"
git push origin "v${NEW_VERSION}"

echo "✓ Tag created and pushed"
echo "Release v${NEW_VERSION} ready for GitHub Release (Step 9)"
```

---

## References

- **PRD**: `/docs/project_plans/PRDs/infrastructure/release-versioning-v1.md`
- **Release Skill**: `.claude/skills/release/` (symlinked from SkillMeat)
- **Changelog Spec**: `.claude/specs/changelog-spec.md`
- **CHANGELOG**: `CHANGELOG.md`
