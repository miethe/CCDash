---
schema_version: "1.0"
doc_type: implementation_plan
title: "CCDash README Build System - Comprehensive Rebuild"
description: "Rebuild Handlebars-based README system from thin data structure (5 categories, 20 items) to comprehensive content reflecting 11 feature areas from existing README"
status: draft
created: 2026-03-14
updated: 2026-03-14
feature_slug: readme-build-system
priority: low
risk_level: low
effort_estimate: "4-6 hours"
scope: Data enrichment, partial rewrites, template update, validation
prd_ref: null
plan_ref: null
related_documents:
  - docs/project_plans/implementation_plans/enhancements/readme-screenshot-capture-v1.md
team:
  - documentation-writer (all phases)
---

# Implementation Plan: CCDash README Build System - Comprehensive Rebuild

**Complexity**: Small | **Track**: Fast
**Estimated Effort**: 4-6 hours | **Timeline**: 1 day
**Scope**: Data enrichment + partial rewrites + validation

---

## Executive Summary

The current README build system at `.github/readme/` uses thin data structures that resulted in loss of rich content when auto-generation was introduced. This plan rebuilds the system to be comprehensive by:

1. Enriching `data/features.json` from 5 categories → 11 full categories matching existing README feature areas
2. Expanding `data/screenshots.json` with 6 screenshot specs + 2 GIF specs (all pending capture)
3. Rewriting/creating 8 partial files with proper detail levels and structure
4. Adding architecture partial to template
5. Validating build and link integrity

The system maintains backward compatibility with existing `build-readme.js`, `validate-links.js`, and `check-screenshots.js` scripts (no code changes required).

---

## Quick Reference Task Table

| Phase | Key Deliverables | Exit Criteria | Effort |
|-------|------------------|--------------|--------|
| 1 | `data/features.json` expanded to 11 categories with 44+ items | All items have id/name/description/highlight, no placeholders | 1.5h |
| 2 | `data/screenshots.json` expanded to 6 screenshots + 2 GIFs | All 8 assets defined with pending status, manifest valid | 0.75h |
| 3 | All 8 partials (hero, screenshots, features, quickstart, architecture, data-models, contributing, footer) | No TODO placeholders, prose matches existing README detail | 1.75h |
| 4 | `README.hbs` template updated with architecture partial | Correct 8-partial section order | 0.25h |
| 5 | Build pipeline validation (dry-run → build → validate-links → check-screenshots) | Build succeeds, links resolve, README.md ≥300 lines, no pending placeholders | 0.75h |

**Total**: ~5 hours hands-on work + validation buffer

---

## Implementation Phases

### Phase 1: Enrich data/features.json

**Duration**: 1.5 hours
**Assigned**: documentation-writer

**Objective**: Expand from 5 thin categories (20 items) to 11 comprehensive categories (44+ items) matching existing README feature areas.

**Existing Categories** (to preserve/enhance):
- dashboard-analytics (expand from 4 → 9 items)
- session-forensics (expand from 5 → 8 items)
- feature-management (expand from 4 → 8 items)
- execution (expand from 4 → 7 items)
- platform-support (keep 3 items)

**New Categories** (to create):
1. global-layout (3 items): sidebar, notifications, theme
2. project-management (3 items): switching, context, creation
3. plan-catalog (4 items): grid/list/explorer views, modal editing
4. codebase-explorer (3 items): tree, correlations, navigation
5. settings (4 items): alert rules, projects tab, integrations, pricing
6. workflow-registry (4 items): catalog, detail, identity, cross-navigation
7. agentic-intelligence (3 items): SkillMeat sync, stack extraction, operator tooling

**Structure per Item**:
```json
{
  "id": "kebab-case-id",
  "name": "Display Name",
  "description": "1-sentence benefit-focused description (no spec bullets)",
  "highlight": true/false (true for top 2-3 per category)
}
```

**Guidance**:
- Focus on **benefits and user outcomes**, not technical specs
- Use existing README prose (lines 2-351) as source material
- Highlight 2-3 top items per category maximum
- No sub-bullets (those belong in user guides)
- Keep descriptions concise (≤12 words)

**Quality Gate Exit**:
- All 11 categories defined
- 44+ total items
- Every item has id/name/description/highlight
- No TODO or placeholder text
- File validates against `data-schemas/features.schema.json`

---

### Phase 2: Enrich data/screenshots.json

**Duration**: 0.75 hours
**Assigned**: documentation-writer

> **Screenshot Capture Plan**: For the detailed browser automation capture workflow (Chrome MCP sequences, timing, data requirements, GIF recording specs), see the companion plan:
> [`readme-screenshot-capture-v1.md`](./readme-screenshot-capture-v1.md)

**Objective**: Define 6 screenshot captures + 2 GIF specs (all status: "pending" since assets not yet captured).

**Screenshots to Define** (at 1280×720 desktop preset):

| ID | Route | Description | Category |
|---|---|---|---|
| dashboard-hero | `/` | KPI cards + cost/velocity chart + AI insights panel | readme |
| session-inspector-transcript | `/sessions` | 3-pane transcript with tool call expanded | readme |
| feature-board-kanban | `/board` | Kanban columns + drill-down modal open | readme |
| execution-workbench | `/execution` | Recommended stack card + run output streaming | features |
| workflow-registry | `/workflows` | Catalog pane + detail panel with effectiveness scores | features |
| analytics-workflow-intelligence | `/analytics?tab=workflow_intelligence` | Workflow leaderboard with failure clustering | features |

**GIFs to Define**:

| ID | Description | Sequence |
|---|---|---|
| session-walkthrough | Open session list → select session → browse transcript → click forensics tab | 4 steps |
| feature-board-drill | Click feature in board → open modal → browse phases → view documents tab | 3 steps |

**Structure**: Mirrors existing schema with added fields for GIFs
```json
{
  "id": "screenshot-id",
  "file": "docs/screenshots/[id].png or docs/gifs/[id].gif",
  "alt": "Descriptive alt text",
  "status": "pending",
  "category": "readme|features",
  "width": 1280,
  "height": 720,
  "notes": "Capture context"
}
```

**Quality Gate Exit**:
- 6 screenshots defined
- 2 GIFs defined
- All fields populated (id, file, alt, status, category, width, height, notes)
- All status: "pending"
- File validates against `data-schemas/screenshots.schema.json`

---

### Phase 3: Rewrite All Partials

**Duration**: 1.75 hours
**Assigned**: documentation-writer

**Objective**: Rewrite/create 8 partial files with proper detail levels and structure. Each partial should feel complete on its own while fitting into the larger README.

#### 3.1: hero.md

**Content**:
- Tight value prop (≤15 words)
- 2-3 sentence intro expanding on philosophy
- Badge placeholder row (badges not yet defined)
- 5 top capabilities as benefit-focused bullets
- "Get Started" anchor link to quickstart

**Source**: README lines 1-16 + philosophy from lines 6-10

---

#### 3.2: screenshots.md

**Content**:
- Section header with brief intro
- For each screenshot: image markdown + descriptive caption tied to screenshots.json data
- Pending asset placeholder with note that assets are being captured
- Alt text and category grouping

**Structure**:
```markdown
## Screenshots

[Brief intro]

### [Screenshot category/title]

![alt text](file)

**[Descriptive caption tied to features]**

---
```

**Source**: New section derived from README feature areas

---

#### 3.3: features.md

**Content**:
- 11 categories from enriched `data/features.json`
- Benefit-focused bullets per item
- Top 2-3 items bolded as highlights
- No sub-bullets or spec details (user guides are for that)
- Clean visual hierarchy

**Template Pattern**:
```markdown
### Category Name

- **Highlighted Item**: One-sentence benefit
- Regular Item: One-sentence benefit
- Another Item: One-sentence benefit
```

**Source**: Enriched features.json data

---

#### 3.4: quickstart.md

**Content**:
- Prerequisites: Node 20+, Python 3.10+
- 3-step install (npm install → npm run setup → npm run dev)
- All 8 npm scripts in a table with descriptions
- All CCDASH_* env vars grouped by function:
  - Feature gates (CCDASH_*_ENABLED)
  - Startup tuning (CCDASH_STARTUP_*)
  - Database (CCDASH_DB_BACKEND, CCDASH_DATABASE_URL)
  - Integrations (GEMINI_API_KEY, etc)
  - Development (CCDASH_API_PROXY_TARGET)
- Runtime profile note (local/api/worker)
- Link to detailed guides

**Source**: README lines 280-332 (complete coverage of all env vars)

---

#### 3.5: architecture.md (NEW)

**Content**:
- Brief architecture overview for developers
- Frontend/backend split (React 19 + FastAPI)
- Port configuration (3000/8000)
- Data flow diagram in text form: parsers → sync → DB → repos → routers → frontend
- Key directories with 1-line descriptions:
  - frontend/ (root, App.tsx, services, contexts)
  - backend/ (main.py, routers, services, db, models)
  - .github/readme/ (build system, templates, data)
- Key data flow: session JSONL → parser → sync_engine → repositories → API → UI
- Brief note on CLAUDE.md as source of truth

**Source**: CLAUDE.md architecture section + README lines 20-28 (tech stack)

---

#### 3.6: data-models.md

**Content**:
- Condense from current 3 detailed models to 1 paragraph each:
  - **Feature**: Primary unit of delivery aggregating docs and tasks
  - **AgentSession**: Atomic unit of work with logs, impact history, artifacts
  - **ProjectTask**: Specific implementation unit with status and cost
  - **PlanDocument**: Markdown docs with typed metadata and frontmatter
- Remove raw field lists (users should check code/types.ts for that)
- Focus on purpose and relationships

**Source**: README lines 244-277

---

#### 3.7: contributing.md

**Content**:
- Development setup (use quickstart section)
- Backend test commands with proper syntax:
  - `backend/.venv/bin/python -m pytest backend/tests/ -v`
  - Single test pattern
  - Matching pattern
- Link to CLAUDE.md for full development guidelines
- Link to existing architecture/ADRs
- Code review expectations
- Documentation requirements for new features

**Source**: CLAUDE.md + README test notes

---

#### 3.8: footer.md

**Content**:
- Full documentation table with all 10 linked guides (from README lines 341-350):
  1. setup-user-guide.md
  2. testing-user-guide.md
  3. execution-workbench-user-guide.md
  4. agentic-sdlc-intelligence-user-guide.md
  5. session-usage-attribution-user-guide.md
  6. agentic-sdlc-intelligence-developer-reference.md
  7. session-usage-attribution-developer-reference.md
  8. sync-observability-and-audit.md
  9. codebase-explorer-developer-reference.md
  10. execution-workbench-developer-reference.md
- Version badge from version.json (v0.1.0)
- License note
- Contributing callout

**Quality Gate Exit**:
- All 8 partials written (no stub files)
- No TODO or placeholder text
- Prose detail level matches existing README
- Each partial is self-contained but fits larger README structure
- Screenshots, features, quickstart partials pull from enriched data files

---

### Phase 4: Update Template README.hbs

**Duration**: 0.25 hours
**Assigned**: documentation-writer

**Objective**: Update template to include architecture partial and ensure correct section order.

**Changes**:
```diff
  {{> hero}}

  {{> screenshots}}

  {{> features}}

  {{> quickstart}}
+
+ {{> architecture}}

  {{> data-models}}

+ {{> footer}}
+
  {{> contributing}}
-
- {{> footer}}
```

**Rationale**:
- Architecture comes after quickstart (devs read setup first, then understand structure)
- Footer moved to end (canonical position)
- Contributing before footer (editorial flow)

**Quality Gate Exit**:
- All 8 partials included
- Correct order: hero → screenshots → features → quickstart → architecture → data-models → footer → contributing
- File validates Handlebars syntax

---

### Phase 5: Build + Validate

**Duration**: 0.75 hours
**Assigned**: documentation-writer

**Objective**: Execute build pipeline, verify integrity, and fix any issues.

**Steps**:

1. **Dry-Run Preview**
   ```bash
   cd /Users/miethe/dev/homelab/development/CCDash/.github/readme
   node scripts/build-readme.js --dry-run
   ```
   - Check output for no placeholder text
   - Verify all sections rendered
   - Count lines (should be >400 for comprehensive README)

2. **Generate README.md**
   ```bash
   node scripts/build-readme.js
   ```
   - Output written to `/Users/miethe/dev/homelab/development/CCDash/README.md`
   - Verify file exists and is >300 lines

3. **Validate Links**
   ```bash
   node scripts/validate-links.js
   ```
   - All relative links (e.g., `docs/setup-user-guide.md`) resolve
   - Fix any broken internal links
   - External links checked

4. **Check Screenshots Manifest**
   ```bash
   node scripts/check-screenshots.js
   ```
   - Manifest validates against schema
   - All pending assets cataloged
   - File references are consistent

**Expected Outputs**:
- Generated README.md in repo root (≥300 lines)
- All validation scripts pass
- No placeholder text (e.g., "TODO", "[pending]")
- Build log shows 11 categories, 44+ features, 8 screenshots + GIFs

**Quality Gate Exit**:
- `node scripts/build-readme.js` succeeds
- `node scripts/validate-links.js` succeeds (0 broken links)
- `node scripts/check-screenshots.js` succeeds
- Generated README.md ≥300 lines
- All content from existing README preserved and enriched
- Data files validate against schemas

---

## Quality Gates Summary

### Phase 1 Exit (data/features.json)
- [ ] 11 categories defined (with new ones added)
- [ ] 44+ items total
- [ ] Every item has id, name, description (≤12 words), highlight (boolean)
- [ ] No duplicate IDs across categories
- [ ] No TODO or placeholder text
- [ ] Validates against features.schema.json

### Phase 2 Exit (data/screenshots.json)
- [ ] 6 screenshots defined
- [ ] 2 GIFs defined
- [ ] All fields populated: id, file, alt, status, category, width, height, notes
- [ ] All status: "pending" (capture deferred)
- [ ] File paths follow docs/screenshots/* and docs/gifs/* pattern
- [ ] Validates against screenshots.schema.json

### Phase 3 Exit (All 8 Partials)
- [ ] hero.md: value prop + philosophy + 5 capabilities
- [ ] screenshots.md: image references + captions + pending note
- [ ] features.md: all 11 categories with benefit-focused items
- [ ] quickstart.md: prerequisites + install + scripts table + env vars grouped + runtime note
- [ ] architecture.md: overview + tech stack + data flow + key directories
- [ ] data-models.md: 1 paragraph per model (no field lists)
- [ ] contributing.md: test commands + CLAUDE.md link + expectations
- [ ] footer.md: 10-doc table + version badge + license
- [ ] All files valid Markdown
- [ ] No TODO or placeholder text
- [ ] Total prose detail ≥ existing README level

### Phase 4 Exit (README.hbs)
- [ ] All 8 partials included
- [ ] Correct section order (hero → screenshots → features → quickstart → architecture → data-models → footer → contributing)
- [ ] Valid Handlebars syntax

### Phase 5 Exit (Validation)
- [ ] `npm run build-readme` (or `node scripts/build-readme.js`) succeeds
- [ ] Generated README.md ≥300 lines
- [ ] `node scripts/validate-links.js` passes (0 broken links)
- [ ] `node scripts/check-screenshots.js` passes (manifest valid)
- [ ] No placeholder or TODO text in generated README
- [ ] All 11 feature categories visible in output
- [ ] All env vars from existing README included in quickstart section

---

## Key Constraints

1. **No code changes**: build-readme.js, validate-links.js, check-screenshots.js remain untouched
2. **No backend/frontend code changes**: This is data and documentation only
3. **No new JSON files**: Work within features.json, screenshots.json, version.json
4. **All existing env vars included**: Every CCDASH_* variable from README must appear in quickstart.md
5. **All 10 doc links preserved**: Every guide referenced in existing README footer appears in new footer.md
6. **Backward compatibility**: Generated README structure matches/exceeds original content richness

---

## Dependencies & Assumptions

**Dependencies**:
- Node.js 18+ available in dev environment (for `node scripts/build-readme.js`)
- Handlebars templating engine (already installed via `.github/readme/package.json`)
- Existing data schema validation (data-schemas/*.schema.json)

**Assumptions**:
- Screenshots are not yet captured (all status: "pending" is acceptable for v1.0)
- GIF specs can be recorded as metadata without actual capture
- Existing README at repo root is comprehensive and accurate
- CLAUDE.md reflects current architecture
- No breaking changes to build script during implementation

---

## Success Metrics

1. **Completeness**: 11 feature categories, 44+ items, 6 screenshots + 2 GIFs all defined
2. **Data Integrity**: 100% validation pass (schemas + links + manifest)
3. **Content Quality**: Generated README ≥300 lines, no placeholder text, all env vars included
4. **Backward Compatibility**: Generated README includes all content from existing README plus enrichments
5. **Build Success**: All scripts execute with exit code 0

---

## Implementation Notes

### Reference Materials
- Existing README: `/Users/miethe/dev/homelab/development/CCDash/README.md` (lines 1-351)
- CLAUDE.md: `/Users/miethe/dev/homelab/development/CCDash/CLAUDE.md`
- Current features.json: `.github/readme/data/features.json` (5 categories, 20 items)
- Current screenshots.json: `.github/readme/data/screenshots.json` (4 screenshots, 1 GIF)

### File Locations
- Build system: `/Users/miethe/dev/homelab/development/CCDash/.github/readme/`
- Partials: `.github/readme/partials/*.md`
- Data files: `.github/readme/data/*.json`
- Template: `.github/readme/templates/README.hbs`
- Output: `/Users/miethe/dev/homelab/development/CCDash/README.md`

### Commands Reference
```bash
# From .github/readme/ directory:
npm install                    # Install handlebars deps (if needed)
node scripts/build-readme.js --dry-run   # Preview output
node scripts/build-readme.js             # Generate README.md
node scripts/validate-links.js           # Check links
node scripts/check-screenshots.js        # Validate manifest

# From repo root:
npm run build:readme           # If npm script exists
```

---

## Risk Assessment

**Risk**: Low overall. This is data and documentation work with no code changes.

**Specific Risks & Mitigations**:

1. **Risk**: Missing env var coverage in quickstart.md
   - **Mitigation**: Cross-check against existing README lines 308-326 systematically
   - **Owner**: documentation-writer, Phase 3.4

2. **Risk**: Partial rewrites don't match existing README prose detail level
   - **Mitigation**: Use existing README as source material throughout Phase 3
   - **Owner**: documentation-writer, Phase 3

3. **Risk**: Screenshot IDs or paths don't align with capture conventions
   - **Mitigation**: Define IDs and paths in Phase 2 per team convention (pending review if needed)
   - **Owner**: documentation-writer, Phase 2

4. **Risk**: Build script validation fails due to JSON schema changes
   - **Mitigation**: Validate each JSON file against existing schemas before build
   - **Owner**: documentation-writer, Phase 5

5. **Risk**: Generated README is shorter than existing (losing content)
   - **Mitigation**: Dry-run preview in Phase 5.1, adjust partial content if needed
   - **Owner**: documentation-writer, Phase 5

---

## Timeline & Effort Breakdown

| Phase | Task | Effort | Owner |
|-------|------|--------|-------|
| 1 | Expand data/features.json to 11 categories | 1.5h | documentation-writer |
| 2 | Define 6 screenshots + 2 GIFs in data/screenshots.json | 0.75h | documentation-writer |
| 3.1 | Rewrite hero.md | 0.2h | documentation-writer |
| 3.2 | Create screenshots.md | 0.2h | documentation-writer |
| 3.3 | Rewrite features.md | 0.3h | documentation-writer |
| 3.4 | Rewrite quickstart.md with full env var coverage | 0.4h | documentation-writer |
| 3.5 | Create architecture.md (new partial) | 0.25h | documentation-writer |
| 3.6 | Rewrite data-models.md (condense) | 0.15h | documentation-writer |
| 3.7 | Create contributing.md | 0.15h | documentation-writer |
| 3.8 | Create footer.md with 10-doc table | 0.2h | documentation-writer |
| 4 | Update README.hbs template | 0.25h | documentation-writer |
| 5 | Build validation + fixes | 0.75h | documentation-writer |
| **Total** | | **~5 hours** | |

---

## Related Documentation

- **Existing README**: Source of truth for all 11 feature areas and env vars
- **CLAUDE.md**: Architecture reference and development conventions
- **data-schemas/**: JSON validation schemas (features.schema.json, screenshots.schema.json)
- **scripts/**: Build and validation tools (no changes required)

---

## Sign-Off

**Document Created**: 2026-03-14
**Status**: Draft - Ready for implementation
**Next Step**: Assign to documentation-writer and begin Phase 1
