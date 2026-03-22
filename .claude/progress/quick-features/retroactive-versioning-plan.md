# CCDash Retroactive Versioning Plan

**Date**: 2026-03-21
**Status**: Draft
**Goal**: Establish version history for CCDash, creating a GitHub release for the current state and retroactive major version tags capturing the app's evolution.

---

## Current State

- **No git tags or releases** exist on the repository
- **304 commits**, **12 merged PRs** across ~6 weeks (Feb 8 – Mar 21, 2026)
- `package.json` version: `0.1.0` (never updated)
- No backend version strings
- Current feature branch: `refactor/ccdash-theme-system-foundation` (not yet merged)
- Head of `main`: `59c6262` (Merge PR #12, 2026-03-20)

---

## Recommended Version Map

| Version | Commit | Date | Milestone | PRs |
|---------|--------|------|-----------|-----|
| **v0.1.0** | `7c0a961` | 2026-02-11 | MVP: React frontend, FastAPI backend, session viewer, project management | Pre-PR |
| **v0.2.0** | `55dcae2` | 2026-02-17 | DB caching layer, SQLite/PostgreSQL, sync engine, session forensics | #1 |
| **v0.3.0** | `6e4e051` | 2026-02-28 | Feature execution workbench, telemetry & analytics, document schema alignment | #2–#4 |
| **v0.4.0** | `221e69d` | 2026-03-05 | Test visualizer, JUnit ingestion, test status integration | #5 |
| **v0.5.0** | `4ebcaf9` | 2026-03-12 | Agentic SDLC intelligence, session cost observability, token analytics | #6–#8 |
| **v0.6.0** | `7988d2f` | 2026-03-14 | Hexagonal architecture, runtime profiles, shell context split, workflow registry | #9–#10 |
| **v0.7.0** | `59c6262` | 2026-03-20 | SSE live updates, shared content viewer, README build system | #11–#12 |
| **v0.7.1** | TBD | TBD | Theme system foundation (current branch, pending merge) | #13 |

---

## Version Milestone Details

### v0.1.0 — MVP (2026-02-11)

Commit: `7c0a961bec81663a5521a809edf742e55570eda0`

- React + TypeScript + Vite frontend initialized
- Session analytics with advanced visualizations
- Project task structure and board view
- FastAPI backend integrated with React frontend
- Multi-project switching and creation UI
- Feature Board: document-first discovery and Kanban view
- Settings page with session/progress path config

### v0.2.0 — DB Caching & Session Forensics (2026-02-17)

Commit: `55dcae2` (Merge PR #1: feat/db-caching-layer-v1)

- SQLite caching layer with async connection, migrations, repositories
- File watcher and sync engine (filesystem to DB)
- Frontend pagination and deep linking
- PostgreSQL backend support
- Session forensics: transcripts, task data, filtering
- Force Sync UI
- Session linking heuristics and feature status tracking

### v0.3.0 — Execution, Analytics & Schema (2026-02-28)

Commit: `6e4e051` (Merge PR #4: feat/feature-execution-workbench)

- Document refactoring: nested sessions, deferred status tracking, frontmatter (#2)
- Telemetry analytics: OTel instrumentation, metrics export, analytics dashboards (#3)
- Codebase explorer and session artifact capture
- Feature execution workbench with runs, navigation, git history tab (#4)
- Entity data enhancements: feature-phase upserts, status inference

### v0.4.0 — Test Visualizer (2026-03-05)

Commit: `221e69d` (Merge PR #5: feat/test-visualizer)

- JUnit XML parser and enrichment pipeline
- SQLite/PostgreSQL test data repositories
- Test ingestion via sync engine XML watcher
- Testing page with filterable UI, core components, and hooks
- Test status integration in session inspector, execution workbench, and feature modals
- Project-scoped multi-platform test ingestion
- Phase 7 mapping resolver and integrity pipeline

### v0.5.0 — Agentic Intelligence & Observability (2026-03-12)

Commit: `4ebcaf9` (Merge PR #7: feat/agentic-sdlc-intelligence-foundation)

- Document-feature schema alignment: metadata rollups, typed relations (#6)
- Agentic SDLC intelligence: SkillMeat cache, stack observations, workflow scoring (#7)
- Session context & cost observability: token semantics, pricing catalog, block insights (#8)
- Workflow attribution: usage events, analytics APIs, rollout controls
- AI platforms catalog sync and detection

### v0.6.0 — Hexagonal Architecture & Workflows (2026-03-14)

Commit: `7988d2f` (Merge PR #10: refactor/hexagonal-foundation)

- Execution workflow refactor: workflow registry, correlation states, backlinks (#9)
- Hexagonal foundation: runtime profiles, request context, core ports (#10)
- Shell context split: AppSessionContext, AppEntityDataContext, AppRuntimeContext
- Worker and background job runtime separation
- Guardrail tests for frontend architecture

### v0.7.0 — Live Updates & Content Viewer (2026-03-20)

Commit: `59c6262` (Merge PR #12: codex/shared-content-viewer-standardization-v1-p1-p2)

- SSE live update platform: broker, streaming endpoint, frontend client (#11)
- Feature test and ops surface migration to invalidation hooks
- Shared content viewer: foundation, standardized surfaces, raw file viewer (#12)
- Document frontmatter surfacing in shared panes
- README build system with Handlebars templates

### v0.7.1 — Theme System Foundation (pending merge)

- Semantic theme contract definition
- Shared semantic UI primitives
- Status and chart semantic tokens
- Surface migrations: shell, settings, dashboard, analytics, testing, workflow, product
- Foundation guardrail tests

---

## Rationale

### Why retroactively tag?

1. **Bug bisection**: `git bisect` works better with version boundaries
2. **Changelog generation**: Clean version history for release notes
3. **GitHub Releases**: Project history documentation on the Releases page
4. **Reference point**: Team members can reference specific versions

### Why these boundaries?

Each version aligns with merged PR clusters that represent natural feature completions:

- **v0.1.0**: Pre-PR foundation — the app was usable as a basic dashboard
- **v0.2.0**: Database layer = fundamental infrastructure shift from file-only to cached DB
- **v0.3.0**: Three PRs merged in quick succession forming the execution/analytics/schema cluster
- **v0.4.0**: Test visualizer = standalone major feature with full-stack implementation
- **v0.5.0**: Three PRs forming the intelligence/observability cluster
- **v0.6.0**: Architecture refactor = structural change (hexagonal + runtime profiles)
- **v0.7.0**: Live updates + content viewer = the current main head

---

## Execution Plan

### Step 1: Create retroactive annotated tags

Run from `main` branch:

```bash
git checkout main

git tag -a v0.1.0 7c0a961 -m "v0.1.0: MVP - React frontend, FastAPI backend, session viewer, project management"
git tag -a v0.2.0 55dcae2 -m "v0.2.0: DB caching layer, SQLite/PostgreSQL, sync engine, session forensics"
git tag -a v0.3.0 6e4e051 -m "v0.3.0: Execution workbench, telemetry analytics, document schema alignment"
git tag -a v0.4.0 221e69d -m "v0.4.0: Test visualizer - JUnit ingestion, test status integration"
git tag -a v0.5.0 4ebcaf9 -m "v0.5.0: Agentic SDLC intelligence, session cost observability, token analytics"
git tag -a v0.6.0 7988d2f -m "v0.6.0: Hexagonal architecture, runtime profiles, workflow registry"
git tag -a v0.7.0 59c6262 -m "v0.7.0: SSE live updates, shared content viewer, README build system"
```

### Step 2: Push tags to remote

```bash
git push origin --tags
```

### Step 3: Create GitHub Release for current version (v0.7.0)

```bash
gh release create v0.7.0 --title "v0.7.0: Live Updates & Content Viewer" --notes "$(cat <<'EOF'
## Highlights
- SSE live update platform with broker, streaming endpoint, and frontend client
- Shared content viewer with standardized surfaces and raw file viewer
- Document frontmatter surfacing in shared panes
- README build system with Handlebars templates

**Full Changelog**: compare/v0.6.0...v0.7.0
EOF
)" --target 59c6262
```

### Step 4: Create lightweight GitHub Releases for older tags

```bash
for v in v0.1.0 v0.2.0 v0.3.0 v0.4.0 v0.5.0 v0.6.0; do
  msg=$(git tag -l --format='%(contents)' "$v")
  gh release create "$v" --title "$v" --notes "$msg" --target "$v"
done
```

### Step 5: Update version string in package.json

```bash
# After theme system merge:
npm version 0.7.1 --no-git-tag-version
# Then tag and release v0.7.1
```

### Step 6: After theme system merge, tag v0.7.1

```bash
# After merge commit exists on main:
git tag -a v0.7.1 <merge-commit> -m "v0.7.1: Theme system foundation - semantic tokens, surface migrations"
git push origin v0.7.1

gh release create v0.7.1 --title "v0.7.1: Theme System Foundation" --notes "$(cat <<'EOF'
## Highlights
- Semantic theme contract with shared UI primitives
- Status and chart semantic tokens
- Complete surface migration (shell, settings, dashboard, analytics, testing, workflow, product)
- Foundation guardrail tests

**Full Changelog**: compare/v0.7.0...v0.7.1
EOF
)"
```

---

## Post-Tagging: Going Forward

1. **Tag on every merge to main** that represents a meaningful release
2. **Use `gh release create`** for proper GitHub Releases with changelogs
3. **Keep `package.json` version in sync** when tagging
4. **Consider a release automation** via GitHub Actions on tag push
