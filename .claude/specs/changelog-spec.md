---
title: CCDash CHANGELOG Spec
schema_version: 2
doc_type: spec
status: active
created: 2026-04-28
updated: 2026-04-28
owner: nick
category: infrastructure
tags: [spec, infrastructure, release, changelog, keep-a-changelog]
---

# CCDash CHANGELOG Spec

**Scope**: Rules for maintaining `CHANGELOG.md` at the repository root. This spec governs how commits are categorized into changelog sections, which commits can be skipped, how entries are formatted, and how automation scripts (`rollover-changelog.py`, `audit-coverage.py`) interact with these rules.

**Consumed by**: `release` skill and `changelog-sync` skill (both symlinked from SkillMeat). Do not modify the skill scripts; update this spec only.

---

## Keep-a-Changelog Format

**Reference**: [Keep a Changelog v1.1.0](https://keepachangelog.com/en/1.1.0/)

CCDash uses Keep-a-Changelog v1.1.0 with the following **ordered sections** under each release heading:

| Section | Purpose |
|---------|---------|
| `Added` | New features or capabilities |
| `Changed` | Changes to existing functionality |
| `Fixed` | Bug fixes |
| `Performance` | Performance improvements and optimizations (first-class section — already in use) |
| `Deprecated` | Soon-to-be-removed features |
| `Removed` | Features removed in this release |
| `Security` | Security patches and vulnerability fixes |
| `Docs` | Documentation additions and updates |

Sections are omitted entirely when empty. The `[Unreleased]` heading sits at the top and accumulates changes until a version is cut.

---

## Categorization Rules

Map Conventional Commit prefixes to changelog sections:

| Prefix | Section | Notes |
|--------|---------|-------|
| `feat` | Added | Use Changed instead when the commit modifies existing behavior without adding net-new capability |
| `feat!` | Added + Removed/Deprecated | Breaking change — add to Added and call out what was removed or deprecated |
| `fix` | Fixed | |
| `perf` | Performance | Performance improvements are user-visible behavior changes |
| `security` | Security | Includes dependency bumps addressing CVE or advisory |
| `revert` | Changed | Note what was reverted and the original commit or PR reference |
| `deprecate` | Deprecated | |
| `remove` | Removed | |
| `refactor` | **skip** | Internal restructuring, no user-visible impact |
| `test` | **skip** | Test additions and modifications |
| `docs` | **skip** | Documentation changes (unless introducing a new user-facing guide for previously undocumented feature — treat as Added) |
| `chore` | **skip** | Includes version-bump commits (`chore(release): bump version to ...`) |
| `ci` | **skip** | CI/CD configuration changes |
| `build` | **skip** | Build tooling changes (unless affecting published artifact) |
| `style` | **skip** | Code formatting, whitespace, linting |

**Breaking changes** (`!` suffix on any prefix): always warrant an entry regardless of prefix. Surface in the most relevant section with a note indicating breaking behavior.

---

## Reportable Prefixes (Audit Coverage)

These prefixes require a corresponding `[Unreleased]` entry before a release is cut. Source: `audit-coverage.py REPORTABLE_PREFIXES`.

```
feat
fix
perf
security
revert
deprecate
remove
```

**Exception**: Commits with skip-pattern prefixes (below) are exempt from coverage audit.

---

## Skip Prefixes (Exempt from Coverage Audit)

These commit characteristics mean no changelog entry is required. Source: `audit-coverage.py SKIP_PREFIXES`.

```
refactor
test
docs
chore
ci
build
style
merge
```

**Special handling for `chore(release)` commits**: All commits with subject matching `^chore\(release\):` are intrinsically skipped via the `chore` prefix. The version-bump commit itself never requires a changelog entry — the CHANGELOG.md rollover is the entry.

Additional exemptions (beyond prefix-matching):
- Merge commits (lines matching `^Merge (pull request|branch)`)
- Dependency bumps without security advisory (routine Dependabot updates)
- Internal tooling changes that do not affect CLI behavior, API contracts, or web UI
- Progress/worknotes file updates (`.claude/progress/`, `.claude/worknotes/`)
- README-only changes where no feature was added or changed

---

## Entry Format

- Entries are bullet points (`-`) under the appropriate section heading.
- Begin with a **bold short title** (noun phrase, title case) followed by an em-dash (`—`) and one sentence in past or present-perfect tense describing the change from the user's perspective.
- Reference the PR number at the end of the line where applicable: `(#123)`.
- Group tightly related sub-points under the parent entry using indented sub-bullets.
- Do not include implementation details (file names, function names) unless they are part of the public surface (CLI flags, API endpoints, config keys).
- Short SHAs in entries help `audit-coverage.py` match commits by SHA as a fallback to subject-substring matching.
- Tense: match the existing CHANGELOG.md style — past tense for fixes (`Fixed X that caused Y`), present-perfect for features (`Added X that enables Y`), nominal phrases for removals (`Removed deprecated X`).

### Examples

**Added:**
```markdown
- **Containerized deployment infrastructure** — Unified backend Dockerfile with `CCDASH_RUNTIME_PROFILE` dispatch, hardened frontend nginx image with non-root user and envsubst templating, unified `compose.yaml` with composable `local`, `enterprise`, and `postgres` profiles.
```

**Performance:**
```markdown
- **Frontend re-render reduction** — Memoized context provider values to eliminate per-poll-tick render cascades across SessionInspector, ProjectBoard, and Planning surfaces.
- **Backend N+1 elimination** — Replaced six confirmed N+1 patterns in agent_queries hot paths with batch repository fetches for feature forensics, planning session enrichment, and document detail.
```

**Fixed:**
```markdown
- **Silent error handling** — Replaced `except: pass` blocks in planning hot paths with logged warnings; partial failures no longer corrupt downstream board cards.
```

---

## `[Unreleased]` Discipline

- Every reportable commit (`feat`, `fix`, `perf`, `security`, `revert`, `deprecate`, `remove`) must have an entry in `[Unreleased]` before a tag is cut.
- `[Unreleased]` must never be absent from `CHANGELOG.md` at any point in the development cycle.
- A tag must never be cut while `[Unreleased]` is the current-version heading — `rollover-changelog.py` renames it before the tag commit.
- After `rollover-changelog.py` runs, a fresh empty `[Unreleased]` is inserted at the top, ready for the next cycle.

---

## Pre-commit Hook (Optional)

A lightweight `commit-msg` hook warns (never blocks) when a user-facing commit is made without a corresponding `[Unreleased]` CHANGELOG entry.

### Files

| File | Purpose |
|------|---------|
| `.claude/hooks/check-changelog-entry.sh` | Shell wrapper — symlink as `.git/hooks/commit-msg` |
| `.claude/hooks/check-changelog-entry.py` | Python helper with detection logic (testable in isolation) |

**Status**: Optional installation deferred to Phase 3 of `release-versioning-v1`. Hook scripts are symlinked from SkillMeat in `.claude/hooks/`.

### Behavior

1. Reads the commit subject from the commit message file (`$1` per git hook contract).
2. If the subject matches a **skip pattern** (see §Skip Prefixes) → exits 0 silently.
3. Otherwise checks `git diff --cached -- CHANGELOG.md` for an added line containing `[Unreleased]`.
4. If found → exits 0 silently (entry present).
5. If not found → prints a warning to stderr with instructions, then exits 0 (never blocks).

### Opt-out (CCDash)

```bash
CCDASH_SKIP_CHANGELOG_CHECK=1 git commit ...
```

**Note**: If `.claude/hooks/` symlinks to SkillMeat and the hook uses a generic env var name, use that instead. Update this spec and Phase 3 plan when deferred hook installation runs.

### Skip-Pattern Authority

The hook's skip-prefix list is maintained in `.claude/hooks/check-changelog-entry.py` (`SKIP_PREFIXES` set) and must stay in sync with the §Skip Prefixes table above and with `SKIP_PREFIXES` in `audit-coverage.py`. This spec table is the source of truth — update the script sets when the spec changes.

---

## Audit Gate Policy

`audit-coverage.py` is the blocking gate before version bump. It requires a `--from-tag` ref. For the **first release** (since CCDash has no git tags), use the initial commit:

```bash
FIRST_COMMIT=$(git rev-list --max-parents=0 HEAD)
python .claude/skills/changelog-sync/scripts/audit-coverage.py \
  --from-tag "$FIRST_COMMIT" \
  --to-ref HEAD \
  --changelog CHANGELOG.md
```

After the first tag is cut (`v0.2.0`), subsequent audits use the previous tag as `--from-tag`.

### Invariants

1. **Audit must exit zero before rollover.** `audit-coverage.py` must exit zero before `rollover-changelog.py` is run. When gaps are found, the skill halts, prints the full gap list, and instructs the operator to update `[Unreleased]` before re-running from the audit step.

2. **Rollover must complete before tag.** `rollover-changelog.py` must complete before `git tag` is created.

3. **`--force` requires explicit human authorization.** Agents must never pass `--force` to `audit-coverage.py` without an explicit human instruction in the current conversation.

4. **No silent bypasses.** When the audit fails, the skill halts and surfaces the gap list. It does not proceed automatically.

---

## Rollover and Release Integration

### rollover-changelog.py

Located at `.claude/skills/release/scripts/rollover-changelog.py`. Invoked as part of the version bump procedure. This script:

1. Renames the `[Unreleased]` section heading to the new version with today's date.
2. Inserts a fresh empty `[Unreleased]` heading at the top.
3. Writes a comparison link footer entry for the new version.

The script does not add or remove entries — categorization is the responsibility of the author or changelog-sync automation.

### audit-coverage.py

Located at `.claude/skills/changelog-sync/scripts/audit-coverage.py`. This script consumes the **Reportable Prefixes** and **Skip Prefixes** sections above to identify commits since the last tagged release that have no corresponding changelog entry. It outputs a coverage table and an actionable gap list so an agent or author can draft the missing entries.

Run it before cutting a release to catch gaps:

```bash
python .claude/skills/changelog-sync/scripts/audit-coverage.py \
  --from-tag v0.1.0 \
  --to-ref HEAD \
  --changelog CHANGELOG.md
```

Exit code `0` = full coverage. Non-zero = gaps present; release must be blocked (unless `--force` is explicitly authorized by a human).

---

## Acceptance Criteria for Spec Alignment

1. **REPORTABLE_PREFIXES match**: `feat`, `fix`, `perf`, `security`, `revert`, `deprecate`, `remove`
2. **SKIP_PREFIXES match**: `refactor`, `test`, `docs`, `chore`, `ci`, `build`, `style`, `merge`
3. **Sections include Performance**: `Performance` is a first-class section alongside standard Keep-a-Changelog set
4. **Entry format documented**: One line per logical change; bold title with em-dash; optional sub-bullets
5. **`[Unreleased]` discipline enforced**: Always exists; never absent; never used as current version after tag
6. **Audit gate policy documented**: Initial-commit ref for first release; previous tag for subsequent releases
7. **Skip-pattern authority clear**: This spec is the source of truth; scripts must stay in sync

---

## References

- Source of truth for reportable/skip prefixes: `.claude/skills/changelog-sync/scripts/audit-coverage.py` lines 25–45
- Release versioning PRD: `docs/project_plans/PRDs/infrastructure/release-versioning-v1.md`
- SkillMeat changelog spec: `/Users/miethe/dev/homelab/development/skillmeat/.claude/specs/changelog-spec.md`
