---
schema_version: "1.0"
doc_type: implementation_plan
title: "CCDash README - Screenshot Capture Plan (Route 2)"
status: draft
created: 2026-03-14
updated: 2026-03-14
feature_slug: readme-build-system
priority: low
risk_level: low
effort_estimate: "2-3 hours"
prd_ref: null
plan_ref: docs/project_plans/implementation_plans/enhancements/readme-build-system-v1.md
related_documents:
  - docs/project_plans/implementation_plans/enhancements/readme-build-system-v1.md
  - .github/readme/data/screenshots.json
---

# Implementation Plan: CCDash README - Screenshot Capture Plan (Route 2)

**Complexity**: Small | **Track**: Fast
**Estimated Effort**: 2-3 hours | **Timeline**: 1-2 hours capture + validation
**Scope**: Visual asset capture using Chrome MCP browser automation + validation

This plan is a **companion to [readme-build-system-v1.md](./readme-build-system-v1.md)** and covers the screenshot and GIF capture phase using Chrome MCP tools. Execute after Phase 2 (screenshots.json definition) of the main plan is complete.

---

## Quick Reference: Asset Capture Table

| Asset ID | Type | Route | Window Size | File Path | Status |
|----------|------|-------|-------------|-----------|--------|
| dashboard-hero | PNG | `/#/` | 1280×720 | docs/screenshots/dashboard-hero.png | pending |
| session-inspector-transcript | PNG | `/#/sessions` | 1280×720 | docs/screenshots/session-inspector-transcript.png | pending |
| feature-board-kanban | PNG | `/#/board` | 1280×720 | docs/screenshots/feature-board-kanban.png | pending |
| execution-workbench | PNG | `/#/execution` | 1280×720 | docs/screenshots/execution-workbench.png | pending |
| workflow-registry | PNG | `/#/workflows` | 1280×720 | docs/screenshots/workflow-registry.png | pending |
| analytics-workflow-intelligence | PNG | `/#/analytics?tab=workflow_intelligence` | 1280×720 | docs/screenshots/analytics-workflow-intelligence.png | pending |
| session-walkthrough | GIF | Multi-step sequence | 1280×720 | docs/gifs/session-walkthrough.gif | pending |
| feature-board-drill | GIF | Multi-step sequence | 1280×720 | docs/gifs/feature-board-drill.gif | pending |

---

## Executive Summary

This plan details the **visual asset capture phase** for the CCDash README rebuild. All 6 screenshots and 2 GIFs will be captured using Chrome MCP browser automation tools, ensuring consistent window sizing (1280×720), realistic populated data states, and smooth interaction sequences.

**Key Success Criteria**:
- All 8 assets captured with no loading spinners or empty states visible
- Window remains at 1280×720 throughout (no resizing between captures)
- Assets saved to correct file paths and tracked in screenshots.json
- Post-capture validation: check-screenshots.js passes, README regenerates correctly

---

## Pre-Capture Setup Checklist

Before starting any screenshot or GIF capture, complete these prerequisites:

### Development Environment
- [ ] Navigate to repo root: `/Users/miethe/dev/homelab/development/CCDash`
- [ ] Start dev server: `npm run dev`
- [ ] Wait for both frontend (Vite) and backend (uvicorn) to fully initialize
- [ ] Expected output: Frontend listens on `http://localhost:3000`, Backend on `http://localhost:8000`

### Health Verification
- [ ] Frontend loads: Navigate to `http://localhost:3000/#/` in browser → Dashboard visible
- [ ] Backend health: `curl http://localhost:8000/api/health` → Returns 200 OK with JSON
- [ ] Data populated: At least one project, one session, and one feature visible in the UI

### Data Prerequisites
CCDash reads from local filesystem. Ensure:
- [ ] Project data exists (check `CCDash/.claude/data/` or configured project path)
- [ ] Session JSONL files with agent sessions present
- [ ] Feature/task documents created and parsed
- [ ] Mock/demo data is visually interesting (multiple features, sessions with tool calls, etc.)

**Note**: If data is missing, populate via filesystem before proceeding. CCDash sync engine will pick up changes within seconds.

### Window & Capture Configuration
- [ ] Open Chrome or Chrome-compatible browser
- [ ] Browser window set to **1280×720 pixels** (use DevTools or OS window manager)
- [ ] Keep window size constant for all captures (don't resize between screenshots)
- [ ] Browser DevTools closed (keeps UI clean)
- [ ] No browser extensions that may overlay UI elements

---

## Screenshot Capture Specs

### Screenshot 1: Dashboard Hero

**ID**: `dashboard-hero`
**Route**: `http://localhost:3000/#/`
**Window Size**: 1280×720
**File Path**: `docs/screenshots/dashboard-hero.png`

#### Objective
Capture the dashboard landing page showing KPI cards, cost/velocity chart, and AI insights panel with realistic populated data.

#### Required Data State
- At least 3 KPI cards visible (e.g., Sessions This Week, Agents Active, Cost This Month)
- Cost vs Velocity chart with 5+ data points
- AI Insights panel showing at least 2 insights cards
- Sidebar visible on left with project context

#### Pre-Capture Actions
1. Navigate to `http://localhost:3000/#/` (should load dashboard by default)
2. Wait 2 seconds for all charts to render
3. Scroll to ensure full viewport is visible (no scroll needed if content fits)

#### Tool Sequence
```
1. mcp__claude-in-chrome__tabs_create_mcp()
   → Get browser tab handle

2. mcp__claude-in-chrome__resize_window(tab_id, width: 1280, height: 720)
   → Set window to 1280×720

3. mcp__claude-in-chrome__navigate(tab_id, "http://localhost:3000/#/")
   → Load dashboard route

4. mcp__claude-in-chrome__wait(tab_id, ms: 2500)
   → Wait for charts to render

5. mcp__claude-in-chrome__computer_screenshot(tab_id)
   → Capture visible viewport

6. Save PNG to: docs/screenshots/dashboard-hero.png
```

#### Quality Checks
- No loading spinners visible
- All 3+ KPI cards fully rendered
- Chart data visible (not just axis labels)
- No modal dialogs open

---

### Screenshot 2: Session Inspector - Transcript Tab

**ID**: `session-inspector-transcript`
**Route**: `http://localhost:3000/#/sessions`
**Window Size**: 1280×720
**File Path**: `docs/screenshots/session-inspector-transcript.png`

#### Objective
Capture the Session Inspector showing the 3-pane transcript view with a tool call expanded, demonstrating deep-dive session analysis capability.

#### Required Data State
- At least one session in the grid (left pane) selectable
- Session detail view (right pane) shows Transcript tab active
- At least one tool call visible and expanded (showing parameters and output)
- Metadata sidebar visible showing session duration, agent info, token usage

#### Pre-Capture Actions
1. Navigate to `http://localhost:3000/#/sessions`
2. Wait 1 second for session list to load
3. Click first visible session in the grid to open detail view
4. Wait 1 second for transcript to render
5. Scroll transcript if needed to find a tool call
6. Click on a tool call row to expand it (if not already expanded)
7. Wait 1 second for expansion animation

#### Tool Sequence
```
1. mcp__claude-in-chrome__tabs_create_mcp()
   → Get browser tab handle

2. mcp__claude-in-chrome__resize_window(tab_id, width: 1280, height: 720)
   → Set window to 1280×720

3. mcp__claude-in-chrome__navigate(tab_id, "http://localhost:3000/#/sessions")
   → Load sessions route

4. mcp__claude-in-chrome__wait(tab_id, ms: 1500)
   → Wait for session grid to load

5. mcp__claude-in-chrome__click(tab_id, selector: "button[data-testid='session-row']", index: 0)
   → Click first session to open detail

6. mcp__claude-in-chrome__wait(tab_id, ms: 1500)
   → Wait for transcript tab to render

7. mcp__claude-in-chrome__click(tab_id, selector: "[data-testid='transcript-entry-tool-call']", index: 0)
   → Click first tool call to expand (if available)

8. mcp__claude-in-chrome__wait(tab_id, ms: 1000)
   → Wait for expansion animation

9. mcp__claude-in-chrome__computer_screenshot(tab_id)
   → Capture with expanded tool call visible

10. Save PNG to: docs/screenshots/session-inspector-transcript.png
```

#### Quality Checks
- Session detail view clearly shows Transcript tab
- At least one tool call expanded with parameters visible
- Metadata sidebar visible on right
- No loading spinners or skeleton loaders visible

---

### Screenshot 3: Feature Board - Kanban View

**ID**: `feature-board-kanban`
**Route**: `http://localhost:3000/#/board`
**Window Size**: 1280×720
**File Path**: `docs/screenshots/feature-board-kanban.png`

#### Objective
Capture the Feature Board in Kanban view with a feature drill-down modal open showing the Phases tab, demonstrating the full feature planning interface.

#### Required Data State
- At least 3 Kanban columns visible (e.g., Backlog, In Progress, Done)
- At least 2 feature cards visible across columns
- Feature drill-down modal open showing a feature with multiple phases
- Phases tab in modal active and expanded

#### Pre-Capture Actions
1. Navigate to `http://localhost:3000/#/board`
2. Wait 1.5 seconds for Kanban to load
3. Verify view is set to Kanban (if list view selected, click Kanban toggle)
4. Click on a feature card to open drill-down modal
5. Wait 1 second for modal to fully animate open
6. If not already on Phases tab, click the Phases tab in modal
7. Wait 0.5 seconds for tab content to render

#### Tool Sequence
```
1. mcp__claude-in-chrome__tabs_create_mcp()
   → Get browser tab handle

2. mcp__claude-in-chrome__resize_window(tab_id, width: 1280, height: 720)
   → Set window to 1280×720

3. mcp__claude-in-chrome__navigate(tab_id, "http://localhost:3000/#/board")
   → Load board route

4. mcp__claude-in-chrome__wait(tab_id, ms: 1500)
   → Wait for Kanban to load

5. mcp__claude-in-chrome__click(tab_id, selector: "[data-testid='view-toggle-kanban']")
   → Ensure Kanban view (toggle if in list view)

6. mcp__claude-in-chrome__click(tab_id, selector: "[data-testid='feature-card']", index: 0)
   → Click first feature card to open modal

7. mcp__claude-in-chrome__wait(tab_id, ms: 1000)
   → Wait for modal animation

8. mcp__claude-in-chrome__click(tab_id, selector: "[data-testid='modal-tab-phases']")
   → Click Phases tab in modal (if not already active)

9. mcp__claude-in-chrome__wait(tab_id, ms: 500)
   → Wait for tab content

10. mcp__claude-in-chrome__computer_screenshot(tab_id)
    → Capture modal with Phases tab visible

11. Save PNG to: docs/screenshots/feature-board-kanban.png
```

#### Quality Checks
- Kanban columns visible in background
- Feature drill-down modal centered and fully visible
- Phases tab active and content expanded
- No modal loading spinners visible

---

### Screenshot 4: Execution Workbench

**ID**: `execution-workbench`
**Route**: `http://localhost:3000/#/execution`
**Window Size**: 1280×720
**File Path**: `docs/screenshots/execution-workbench.png`

#### Objective
Capture the Execution Workbench showing the Recommended Stack card with confidence scores visible, and run history panel below. This demonstrates the core execution intelligence feature.

#### Required Data State
- At least one feature selectable in feature picker
- Recommended Stack card visible with 3-5 stack recommendation cards
- Confidence scores (percentages or visual indicators) visible on stack cards
- Run history panel showing at least 2 previous runs with status/duration
- No run output streaming (should show static results)

#### Pre-Capture Actions
1. Navigate to `http://localhost:3000/#/execution`
2. Wait 2 seconds for the page to fully load
3. If no feature is selected, click on first feature in the feature picker
4. Wait 2 seconds for Recommended Stack to populate
5. Scroll down slightly if needed to see Run History panel (or ensure both visible)

#### Tool Sequence
```
1. mcp__claude-in-chrome__tabs_create_mcp()
   → Get browser tab handle

2. mcp__claude-in-chrome__resize_window(tab_id, width: 1280, height: 720)
   → Set window to 1280×720

3. mcp__claude-in-chrome__navigate(tab_id, "http://localhost:3000/#/execution")
   → Load execution route

4. mcp__claude-in-chrome__wait(tab_id, ms: 2000)
   → Wait for feature picker to load

5. mcp__claude-in-chrome__click(tab_id, selector: "[data-testid='feature-picker-option']", index: 0)
   → Select first feature (triggers stack recommendation)

6. mcp__claude-in-chrome__wait(tab_id, ms: 2500)
   → Wait for Recommended Stack to populate

7. mcp__claude-in-chrome__scroll_down(tab_id, pixels: 150)
   → Scroll to ensure Run History visible in frame

8. mcp__claude-in-chrome__computer_screenshot(tab_id)
   → Capture with Recommended Stack and Run History visible

9. Save PNG to: docs/screenshots/execution-workbench.png
```

#### Quality Checks
- Recommended Stack card clearly visible with stack items
- Confidence scores visible (numeric or visual)
- Run History panel visible below (at least 2 run entries)
- No loading spinners or skeleton loaders visible

---

### Screenshot 5: Workflow Registry

**ID**: `workflow-registry`
**Route**: `http://localhost:3000/#/workflows`
**Window Size**: 1280×720
**File Path**: `docs/screenshots/workflow-registry.png`

#### Objective
Capture the Workflow Registry showing the catalog pane with workflow list and detail panel open on the right, displaying workflow metadata and effectiveness scores.

#### Required Data State
- Catalog pane on left showing at least 2 workflows with icons and names
- Detail panel on right showing full workflow details
- Effectiveness scores or metadata visible (e.g., success rate, run count)
- At least one workflow selected (highlighted in catalog, details visible in panel)

#### Pre-Capture Actions
1. Navigate to `http://localhost:3000/#/workflows`
2. Wait 2 seconds for catalog pane to load
3. If no workflow is selected, click on first workflow in catalog list
4. Wait 1 second for detail panel to populate
5. Verify both catalog and detail panel are visible (may require horizontal scroll or resize)

#### Tool Sequence
```
1. mcp__claude-in-chrome__tabs_create_mcp()
   → Get browser tab handle

2. mcp__claude-in-chrome__resize_window(tab_id, width: 1280, height: 720)
   → Set window to 1280×720

3. mcp__claude-in-chrome__navigate(tab_id, "http://localhost:3000/#/workflows")
   → Load workflows route

4. mcp__claude-in-chrome__wait(tab_id, ms: 2000)
   → Wait for catalog to load

5. mcp__claude-in-chrome__click(tab_id, selector: "[data-testid='workflow-catalog-item']", index: 0)
   → Select first workflow to open detail panel

6. mcp__claude-in-chrome__wait(tab_id, ms: 1500)
   → Wait for detail panel to populate

7. mcp__claude-in-chrome__computer_screenshot(tab_id)
   → Capture with catalog and detail panel visible

8. Save PNG to: docs/screenshots/workflow-registry.png
```

#### Quality Checks
- Catalog pane visible on left with 2+ workflows
- Detail panel visible on right with selected workflow information
- Effectiveness scores or key metrics visible in detail
- No loading spinners visible

---

### Screenshot 6: Analytics - Workflow Intelligence Tab

**ID**: `analytics-workflow-intelligence`
**Route**: `http://localhost:3000/#/analytics?tab=workflow_intelligence`
**Window Size**: 1280×720
**File Path**: `docs/screenshots/analytics-workflow-intelligence.png`

#### Objective
Capture the Analytics Dashboard on the Workflow Intelligence tab, showing workflow leaderboard with failure clustering and performance metrics.

#### Required Data State
- Analytics page loaded with tab navigation visible at top
- Workflow Intelligence tab selected/active
- Workflow leaderboard visible with 5+ workflow entries
- Performance metrics visible (e.g., success rate, failure patterns)
- At least some visual clustering or grouping indicators visible (failure clusters, patterns)

#### Pre-Capture Actions
1. Navigate to `http://localhost:3000/#/analytics?tab=workflow_intelligence`
2. Wait 2.5 seconds for analytics data to load and render
3. Verify the Workflow Intelligence tab is active (should be from URL param)
4. If tab bar shows different tab active, click Workflow Intelligence tab
5. Allow additional 1 second for tab content to fully render

#### Tool Sequence
```
1. mcp__claude-in-chrome__tabs_create_mcp()
   → Get browser tab handle

2. mcp__claude-in-chrome__resize_window(tab_id, width: 1280, height: 720)
   → Set window to 1280×720

3. mcp__claude-in-chrome__navigate(tab_id, "http://localhost:3000/#/analytics?tab=workflow_intelligence")
   → Load analytics with workflow_intelligence tab specified in URL

4. mcp__claude-in-chrome__wait(tab_id, ms: 2500)
   → Wait for analytics data to load and render

5. mcp__claude-in-chrome__click(tab_id, selector: "[data-testid='tab-workflow_intelligence']")
   → Ensure Workflow Intelligence tab is active (redundant but safe)

6. mcp__claude-in-chrome__wait(tab_id, ms: 1000)
   → Wait for tab content to stabilize

7. mcp__claude-in-chrome__scroll_down(tab_id, pixels: 100)
   → Scroll to show leaderboard in full (if needed)

8. mcp__claude-in-chrome__computer_screenshot(tab_id)
   → Capture workflow intelligence view with leaderboard visible

9. Save PNG to: docs/screenshots/analytics-workflow-intelligence.png
```

#### Quality Checks
- Analytics page layout visible
- Workflow Intelligence tab clearly marked as active
- Workflow leaderboard with 5+ entries visible
- Performance metrics visible in table/card format
- No data loading spinners or placeholders visible

---

## GIF Recording Specs

### GIF 1: Session Walkthrough

**ID**: `session-walkthrough`
**Duration**: 15-20 seconds
**File Path**: `docs/gifs/session-walkthrough.gif`
**Tool**: `mcp__claude-in-chrome__gif_creator`

#### Objective
Animated walkthrough of the session inspection workflow: opening the session list, selecting a session, browsing transcript entries, and clicking into the Forensics tab to show queue pressure analysis.

#### Story Arc
Shows how users navigate from high-level session list → detailed transcript analysis → low-level queue pressure forensics, illustrating the depth of introspection available in CCDash.

#### Step-by-Step Sequence

```
Step 1: Open Session Inspector
  Action: navigate
  Target: http://localhost:3000/#/sessions
  Hold: 1000ms (show page loading)
  Label: "Session Inspector loads"

Step 2: View Session Grid
  Action: wait
  Duration: 1500ms
  Label: "Session list populates"

Step 3: Click First Session
  Action: click
  Selector: [data-testid='session-row'] (index: 0)
  Hold: 500ms (snap)
  Label: "Opening session detail..."

Step 4: Transcript Renders
  Action: wait
  Duration: 1500ms
  Label: "Transcript tab loads"

Step 5: Scroll Through Transcript
  Action: scroll_down
  Pixels: 200
  Hold: 2000ms (show browsing)
  Label: "Browsing agent messages and tool calls"

Step 6: Click Forensics Tab
  Action: click
  Selector: [data-testid='tab-forensics']
  Hold: 500ms (snap)
  Label: "Opening Forensics..."

Step 7: Queue Pressure Visible
  Action: wait
  Duration: 1500ms
  Label: "Queue pressure and scheduling data displayed"

Step 8: Final Hold
  Action: wait
  Duration: 1000ms
  Label: (no label, final pause for screenshot)
```

#### Configuration
```json
{
  "fps": 12,
  "quality": 10,
  "showClickIndicators": true,
  "startDelay": 500,
  "endDelay": 500
}
```

#### Timing Notes
- Total duration: 9500ms + GIF rendering ≈ 15-18 seconds at 12 fps
- Click indicators help viewers follow interactive steps
- Pauses between actions allow for smooth visual transitions
- Scroll action done at moderate speed to read transcript content

#### Quality Checks
- No loading spinners frozen in frame
- Click indicators visible and helpful
- Transcript text readable (not blurry or too fast)
- Forensics tab loads and displays data before GIF ends

---

### GIF 2: Feature Board Drill

**ID**: `feature-board-drill`
**Duration**: 12-16 seconds
**File Path**: `docs/gifs/feature-board-drill.gif`
**Tool**: `mcp__claude-in-chrome__gif_creator`

#### Objective
Animated walkthrough of drilling into a feature from the Feature Board: opening board, clicking a feature card, viewing drill-down modal, and exploring the Phases tab to show feature decomposition.

#### Story Arc
Demonstrates how a single feature card expands into detailed phases and documents, showing the planning and execution structure embedded in CCDash.

#### Step-by-Step Sequence

```
Step 1: Load Feature Board
  Action: navigate
  Target: http://localhost:3000/#/board
  Hold: 1000ms (show page loading)
  Label: "Feature Board opens"

Step 2: Board Renders
  Action: wait
  Duration: 1500ms
  Label: "Kanban columns populated"

Step 3: Ensure Kanban View
  Action: click
  Selector: [data-testid='view-toggle-kanban']
  Hold: 500ms (snap)
  Label: "Switch to Kanban (if needed)"

Step 4: Click Feature Card
  Action: click
  Selector: [data-testid='feature-card'] (index: 0)
  Hold: 500ms (snap)
  Label: "Opening feature detail..."

Step 5: Modal Animates
  Action: wait
  Duration: 1000ms
  Label: "Drill-down modal slides into view"

Step 6: Click Phases Tab
  Action: click
  Selector: [data-testid='modal-tab-phases']
  Hold: 500ms (snap)
  Label: "Viewing feature phases..."

Step 7: Phase Content Loads
  Action: wait
  Duration: 1000ms
  Label: "Phase details with subtasks visible"

Step 8: Scroll Phase Content
  Action: scroll_down
  Pixels: 150
  Hold: 1500ms (show browsing)
  Label: "Exploring phase breakdown"

Step 9: Final Hold
  Action: wait
  Duration: 1000ms
  Label: (no label, final pause)
```

#### Configuration
```json
{
  "fps": 12,
  "quality": 10,
  "showClickIndicators": true,
  "startDelay": 500,
  "endDelay": 500
}
```

#### Timing Notes
- Total duration: 7500ms + GIF rendering ≈ 12-15 seconds at 12 fps
- Click indicators help show interaction points
- Modal animation timing key to showing "drilldown" experience
- Scroll shows readable phase content (not rushed)

#### Quality Checks
- Kanban board visible before feature click
- Modal animation clearly shows drill-down motion
- Phases tab content loads and displays before GIF ends
- No loading spinners frozen in frame

---

## Post-Capture Validation Steps

After all 6 screenshots and 2 GIFs are captured, execute these validation steps:

### Step 1: Verify File Existence
```bash
cd /Users/miethe/dev/homelab/development/CCDash

# Check screenshots
test -f docs/screenshots/dashboard-hero.png && echo "✓ dashboard-hero.png" || echo "✗ dashboard-hero.png"
test -f docs/screenshots/session-inspector-transcript.png && echo "✓ session-inspector-transcript.png" || echo "✗ session-inspector-transcript.png"
test -f docs/screenshots/feature-board-kanban.png && echo "✓ feature-board-kanban.png" || echo "✗ feature-board-kanban.png"
test -f docs/screenshots/execution-workbench.png && echo "✓ execution-workbench.png" || echo "✗ execution-workbench.png"
test -f docs/screenshots/workflow-registry.png && echo "✓ workflow-registry.png" || echo "✗ workflow-registry.png"
test -f docs/screenshots/analytics-workflow-intelligence.png && echo "✓ analytics-workflow-intelligence.png" || echo "✗ analytics-workflow-intelligence.png"

# Check GIFs
test -f docs/gifs/session-walkthrough.gif && echo "✓ session-walkthrough.gif" || echo "✗ session-walkthrough.gif"
test -f docs/gifs/feature-board-drill.gif && echo "✓ feature-board-drill.gif" || echo "✗ feature-board-drill.gif"
```

**Exit Criteria**: All 8 files exist (0 missing)

### Step 2: Update screenshots.json Status

After confirming all files exist, update `.github/readme/data/screenshots.json` to change status from "pending" to "captured" for each asset:

```json
{
  "screenshots": [
    {
      "id": "dashboard-hero",
      "file": "docs/screenshots/dashboard-hero.png",
      "alt": "CCDash dashboard showing KPI cards, cost vs velocity chart, and AI insights",
      "status": "captured",
      "category": "readme",
      "width": 1280,
      "height": 720
    },
    // ... (repeat for other 5 screenshots)
  ],
  "gifs": [
    {
      "id": "session-walkthrough",
      "file": "docs/gifs/session-walkthrough.gif",
      "alt": "Animated walkthrough of session inspection workflow",
      "status": "captured",
      "tool": "chrome-mcp",
      "sequence": ["open-session-list", "select-session", "browse-transcript", "open-forensics"]
    },
    // ... (repeat for feature-board-drill)
  ]
}
```

### Step 3: Run Validation Scripts

From `.github/readme/` directory:

```bash
cd /Users/miethe/dev/homelab/development/CCDash/.github/readme

# Check screenshots manifest
node scripts/check-screenshots.js
# Expected: "✓ All screenshots accounted for" or similar

# Validate links in README (after rebuild)
node scripts/validate-links.js
# Expected: "✓ All links valid" or similar
```

**Exit Criteria**: Both scripts pass with no errors

### Step 4: Regenerate README

From `.github/readme/` directory:

```bash
node scripts/build-readme.js
# Output: README.md regenerated with captured asset references
```

Verify output at `/Users/miethe/dev/homelab/development/CCDash/README.md`:
- [ ] File generated and >300 lines
- [ ] Screenshot and GIF sections render correctly with image references
- [ ] No broken markdown syntax

**Exit Criteria**: README.md exists, renders correctly, contains all asset references

---

## Quality Gates

### Asset Quality
- [ ] All 6 PNG screenshots are actual image files (not empty or corrupted)
- [ ] All 2 GIF files are valid GIF format (can be opened in image viewer)
- [ ] No loading spinners visible in any screenshot or GIF
- [ ] No empty/placeholder states visible (all show populated, real data)
- [ ] All assets at consistent 1280×720 window size

### Data Integrity
- [ ] screenshots.json validates against schema
- [ ] All 8 asset entries have status: "captured"
- [ ] File paths in manifest match actual saved locations
- [ ] No broken image references

### Documentation
- [ ] README.md regenerates without errors
- [ ] All image markdown is valid and links resolve
- [ ] Screenshot/GIF sections include descriptive captions
- [ ] Alt text is descriptive and helpful

### Validation Script Success
- [ ] `check-screenshots.js` passes (0 errors)
- [ ] `validate-links.js` passes (0 broken links)
- [ ] `build-readme.js` succeeds (README.md generated, ≥300 lines)

---

## Known Constraints & Considerations

1. **Window Size Consistency**: 1280×720 must be maintained throughout all captures. Do NOT resize between screenshots.
2. **Dev Server State**: Session/feature data must exist and be populated. If empty after startup, add mock data to filesystem before capturing.
3. **No Spinners**: All screenshots/GIFs must show fully loaded states with no loading indicators visible. Wait sufficient time (1-2.5 seconds) after navigation/interactions.
4. **GIF Continuity**: Record both GIFs in a single capture session (don't stop gif_creator between them) for consistency.
5. **Chrome MCP Tools**: Selectors used in tool sequences assume data-testid attributes. If selectors fail, fall back to CSS selectors (e.g., button.feature-card) or XPath.
6. **Timing Sensitivity**: GIF recording is timing-sensitive. If steps execute too fast (animations cut off) or too slow (GIF too long), adjust wait() durations in 500ms increments.

---

## Related Documentation

- **Main Plan**: [readme-build-system-v1.md](./readme-build-system-v1.md) — Phase 2 defines screenshot specs, Phase 5 validates assets
- **Screenshots Manifest**: `.github/readme/data/screenshots.json` — Track all asset status here
- **Build Scripts**: `.github/readme/scripts/` — Scripts that validate and use captured assets
- **Frontend Routes**: See CCDash source for all available routes and their components

---

## Timeline

| Step | Task | Duration | Owner |
|------|------|----------|-------|
| 1 | Pre-capture setup (dev server, health checks) | 10 min | MCP/Chrome |
| 2 | Capture 6 screenshots | 20 min | MCP/Chrome |
| 3 | Record 2 GIFs | 15 min | MCP/Chrome |
| 4 | Verify files exist and update screenshots.json | 5 min | Documentation |
| 5 | Run validation scripts + README rebuild | 5 min | Documentation |
| **Total** | | **55 minutes** | |

---

## Success Criteria

- [ ] All 6 screenshot PNG files exist at correct paths
- [ ] All 2 GIF files exist at correct paths
- [ ] screenshots.json updated with all status: "captured"
- [ ] `check-screenshots.js` passes (0 errors)
- [ ] `validate-links.js` passes (0 broken links)
- [ ] `build-readme.js` succeeds (README.md ≥300 lines)
- [ ] No loading spinners or empty states visible in any asset
- [ ] Window size remained 1280×720 for all captures

---

**Document Created**: 2026-03-14
**Status**: Draft - Ready for execution
**Next Step**: Begin pre-capture setup checklist, then execute screenshot captures in sequence
