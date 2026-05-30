---
title: Multi-Project Command Center Operator Guide
description: Enable, configure, and operate the multi-project planning view across CCDash projects.
audience: operators, developers
tags:
  - multi-project
  - planning
  - command-center
  - operators
created: 2026-05-30
updated: 2026-05-30
category: guides
status: published
related_documents:
  - docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md
  - docs/project_plans/implementation_plans/enhancements/multi-project-planning-command-center-v1.md
  - docs/guides/multi-project-command-center-rollout.md
---

# Multi-Project Command Center Operator Guide

Last updated: 2026-05-30

This guide documents how to enable, configure, and operate the multi-project planning command center (MPCC) in CCDash. It covers the two feature flags, project display customization, the active-session board and grouping options, stale-data semantics, and troubleshooting.

---

## Overview

The Multi-Project Command Center provides a unified portfolio view of active sessions and work items across multiple CCDash projects. When enabled, the Planning Command Center (`/#/planning`) gains:

- **Portfolio mode** — see active sessions across all registered projects simultaneously
- **Project filter rail** — toggle projects on/off with live session counts and stale/error indicators
- **Consolidated active-session board** — group sessions by state, project, feature, phase, agent, or model
- **Cross-project detail actions** — open session/task details without switching the active project
- **Fallback colors and groups** — deterministic visual treatment for unconfigured projects

---

## Enabling Multi-Project Mode

The MPCC is **feature-flagged and disabled by default** for safety during the release branch.

### Backend Flag

In `backend/config.py:89`, set the environment variable:

```bash
export CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true
```

Or in a `.env` file in the backend working directory:

```
CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true
```

Default: `False`

### Frontend Flag

The frontend flag is consumed at build time via `VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED`:

```bash
export VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true
npm run build
```

Alternatively, for local development (Vite dev server), pass the flag directly:

```bash
VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true npm run dev
```

Or set it in a `.env.local` file:

```
VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true
```

Default: `false` (consuming the exported constant `MULTI_PROJECT_COMMAND_CENTER_ENABLED` in `constants.ts`)

### Verification

1. Start the dev stack (or your production server):
   ```bash
   npm run dev
   ```
2. Navigate to `/#/planning`.
3. Look for a **Portfolio / Current Project** toggle near the top of the Planning Command Center.
4. If you see the toggle and can switch between modes, both flags are enabled.

---

## Configuring Project Display Metadata

By default, all registered projects in `projects.json` appear with deterministic fallback colors and groups. You can customize the visual treatment per project via `ProjectDisplayConfig`.

### ProjectDisplayConfig Schema

In `projects.json`, add optional `displayConfig` to each project:

```json
{
  "projects": [
    {
      "id": "proj-001",
      "name": "CCDash",
      "path": "/Users/miethe/dev/ccdash",
      "displayConfig": {
        "color": "slate",
        "group": "Core Infrastructure",
        "sortOrder": 1,
        "labelOverride": "CCDash (Primary)"
      }
    },
    {
      "id": "proj-002",
      "name": "SkillMeat",
      "path": "/Users/miethe/dev/skillmeat",
      "displayConfig": {
        "color": "amber",
        "group": "AI Development",
        "sortOrder": 2
      }
    }
  ]
}
```

### Fields

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `color` | string | Deterministic (hash-based) | Color token from the design system (e.g., "slate", "amber", "cyan", "purple", "emerald"). Always accompanied by a text label; never color-only. |
| `group` | string | "Ungrouped" | Category for organizing projects in the filter rail (e.g., "Core Infrastructure", "AI Development", "Experimental"). |
| `sortOrder` | number | Alphabetical by project name | Display order in the filter rail; lower numbers appear first. |
| `labelOverride` | string | Project name | Custom display name in the filter rail and board column headers. |

### Fallback Colors (Deterministic)

Projects without explicit `displayConfig.color` receive a color deterministically based on their project ID hash. This ensures consistency across restarts and without configuration.

Supported color tokens: `slate`, `amber`, `cyan`, `purple`, `emerald`, `rose`, `indigo`, `lime`, `orange`, `pink`, `teal`, `violet`, `zinc`.

---

## Stale-Data Semantics

The active-session board reflects the most recent session state from each project's filesystem scan. However, projects are scanned asynchronously, and network delays or filesystem watchers can introduce staleness.

### Staleness Signals

The project filter rail shows per-project freshness indicators:

| Indicator | Meaning | Action |
|-----------|---------|--------|
| **✓ (green)** | Project data last updated ≤ 60 seconds ago. | Use with confidence. |
| **⚠ (yellow)** | Project data last updated 60s–5min ago. | Data is reasonable but may lag live changes. |
| **✗ (red)** | Project data last updated > 5min ago, or backend error. | Backend failed to sync this project; check logs. |

### Freshness Details

Hover over (or click) the indicator to see:
- Last sync timestamp (relative, e.g., "2 minutes ago")
- Session count at that time
- Any error message (if red)

### Forcing a Rescan

To rescan a specific project immediately:

1. Navigate to that project in single-project mode (`Current Project` toggle).
2. Open the project settings or session inspector.
3. Click **Rescan Filesystem** (if available).

Alternatively, restart the backend worker:

```bash
npm run dev:worker
```

The worker rescans all projects on startup and periodically via the configured interval (see `CCDASH_FILE_WATCHER_POLL_INTERVAL_SECONDS` in `backend/config.py`).

---

## The Active-Session Board

The consolidated active-session board displays agent sessions across all selected projects in a Kanban-style layout.

### Board States

By default, sessions are grouped by **state** (columns):

| Column | Meaning |
|--------|---------|
| **Queued** | Session waiting to start or resume. |
| **Running** | Session is currently executing. |
| **Paused** | Session paused by user or by error. |
| **Completed** | Session finished successfully. |
| **Failed** | Session ended with an error. |

### Session Cards

Each card displays:

- **Session ID** and a truncated timestamp
- **Feature ID** (if linked)
- **Phase** (if applicable)
- **Project badge** — color + label from `displayConfig`
- **Agent + Model** — which agent executed this session
- **Status badge** — sync state (✓ live, ⚠ stale, ✗ error)

### Grouping Options

Click the **Group By** dropdown to reorganize the board:

| Option | Layout | Use When |
|--------|--------|----------|
| **State** (default) | Columns: Queued, Running, Paused, Completed, Failed. Rows: cards within each state. | Overview of session progress. |
| **Project** | Columns: each project. Rows: sessions within that project across all states. | Focus on a single project's activity. |
| **Feature** | Columns: each feature ID. Rows: sessions per feature. | Track work item progress. |
| **Phase** | Columns: each phase label. Rows: sessions per phase. | Monitor phase rollout. |
| **Agent** | Columns: each agent identifier. Rows: sessions per agent. | Analyze agent workload distribution. |
| **Model** | Columns: each model used (e.g., claude-opus-4.7, claude-sonnet-4.6). Rows: sessions per model. | Track model utilization. |

### Filtering

Use the **Project Filter Rail** to toggle projects on/off. Only sessions from enabled projects appear on the board. The filter persists during your session.

---

## Cross-Project Detail Actions

When you click a session card or work item to open detail, the drawer respects the **current session context**. Specifically:

- **Detail drawer is route-local** — the `project_id` is explicitly encoded in the drawer route (e.g., `/planning/session/proj-002/sess-xyz`).
- **Active project does not switch** — opening details from Project B while Project A is active does NOT change the active project.
- **Focus returns to the originating card** — when you close the drawer, focus returns to the card you clicked (no scroll-to-top jumps).

### Example Workflow

1. You are viewing Project A (active).
2. Portfolio mode is enabled; you see sessions from Projects A, B, and C on the board.
3. You click a session from Project C.
4. The detail drawer opens with `project_id=proj-003` in its route.
5. Project A remains active in the sidebar.
6. You close the drawer.
7. Focus returns to the Project C session card you clicked.

This design prevents accidental project switches and supports cross-project review workflows.

---

## Try It: Enable and Explore

### Prerequisites

- At least two projects registered in `projects.json`.
- Both backend and frontend flags enabled (see **Enabling Multi-Project Mode** above).
- `npm run dev` running (or your production server).

### Steps

1. **Enable flags**:
   ```bash
   export CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true
   export VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true
   npm run dev
   ```

2. **Customize display config** (optional):
   - Edit `projects.json` and add `displayConfig` to each project.
   - Save.
   - Refresh the browser (hard refresh: Cmd+Shift+R or Ctrl+Shift+R).

3. **Navigate to Planning**:
   - Go to `/#/planning`.
   - Look for the **Portfolio / Current Project** toggle.

4. **Switch to Portfolio mode**:
   - Click **Portfolio**.
   - The filter rail expands; you see all projects with freshness indicators.
   - The board populates with sessions from all projects.

5. **Filter projects**:
   - Hover over a project's row in the filter rail.
   - Click the checkbox to toggle it on/off.
   - The board updates instantly.

6. **Change grouping**:
   - Click **Group By** and select a different option (e.g., "Agent").
   - The board reorganizes.

7. **Open a cross-project session detail**:
   - Click a session card from a non-active project.
   - The drawer opens; the active project remains unchanged.
   - Close the drawer; focus returns to the card.

8. **Check staleness**:
   - Wait 2–3 minutes without refreshing.
   - Hover over a project's staleness indicator to see the last sync time.
   - If it shows yellow (⚠), the data is 60–300 seconds old.

---

## Performance Caveats

The MPCC is optimized for typical multi-project setups (2–10 active projects, up to 250 concurrent sessions). Larger deployments may encounter limits:

### Server-Side Aggregation

- The backend aggregates session data from all projects **on the main HTTP thread** during the API call.
- Each project is queried independently; fan-out is concurrent (via `asyncio.Semaphore`) with a configurable concurrency ceiling (`CCDASH_MULTI_PROJECT_AGGREGATION_CONCURRENCY`, default 5).
- For >100 projects, consider:
  - **Increasing concurrency**: `export CCDASH_MULTI_PROJECT_AGGREGATION_CONCURRENCY=10`
  - **Implementing background rollup** (see Design Spec DEF-001).

### Windowing & Pagination

- The board renders a **virtual window** of visible cards; off-screen cards are not painted.
- **Pagination is supported**: the API returns paginated results (default page size: 100 sessions).
- Boards with >250 cards use windowing; interaction is smooth.

### Refresh Interval

- The frontend polls the board every **30 seconds** in Portfolio mode.
- To reduce server load, increase `CCDASH_POLLING_INTERVAL_SECONDS` (default 30, in seconds).
- Set to 0 to disable auto-polling (manual refresh only).

### Recommended Configuration for Large Deployments

```bash
# backend/.env or .env.local
CCDASH_MULTI_PROJECT_AGGREGATION_CONCURRENCY=10
CCDASH_POLLING_INTERVAL_SECONDS=60
CCDASH_QUERY_CACHE_TTL_SECONDS=120
```

---

## Troubleshooting

### "Portfolio toggle is not visible"

**Cause:** One or both feature flags are not enabled.

**Fix:**
```bash
# Check backend flag
grep CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED backend/config.py

# Check frontend flag
grep MULTI_PROJECT_COMMAND_CENTER_ENABLED constants.ts

# Enable both and rebuild/restart
export CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true
export VITE_CCDASH_MULTI_PROJECT_COMMAND_CENTER_ENABLED=true
npm run dev
```

### "Only sessions from the active project appear on the board"

**Cause:** The `Portfolio / Current Project` toggle is in **Current Project** mode.

**Fix:** Click the toggle to switch to **Portfolio** mode.

### "Red (✗) staleness indicator for one or more projects"

**Cause:** Backend failed to sync that project, or it hasn't been synced recently (>5 min).

**Fix:**
1. Check backend logs for errors:
   ```bash
   # If running `npm run dev`, look for error traces in the backend console
   grep "ERROR" logs/ccdash.log | tail -20
   ```
2. Verify the project path is correct in `projects.json`.
3. Restart the backend worker:
   ```bash
   npm run dev:worker &
   ```
4. Manually trigger a rescan (see **Forcing a Rescan** above).

### "Board is slow to load or feels sluggish"

**Cause:** Large number of projects or sessions; aggregation is taking time.

**Fix:**
1. **Reduce visible projects** — disable unused projects in the filter rail.
2. **Increase aggregation concurrency**:
   ```bash
   export CCDASH_MULTI_PROJECT_AGGREGATION_CONCURRENCY=10
   ```
3. **Increase API cache TTL**:
   ```bash
   export CCDASH_QUERY_CACHE_TTL_SECONDS=180
   ```
4. **Check backend performance** — run the performance test:
   ```bash
   backend/.venv/bin/python -m pytest backend/tests/test_multi_project_command_center_perf.py -v
   ```

### "Session cards have no color or label"

**Cause:** Projects are using fallback colors (no `displayConfig`); this is normal.

**Fix (optional):** Customize projects in `projects.json` with explicit `displayConfig`:
```json
{
  "id": "proj-001",
  "displayConfig": {
    "color": "slate",
    "group": "Core",
    "sortOrder": 1
  }
}
```

### "Drawer opens but project_id is missing from the URL"

**Cause:** Backend or frontend is not encoding `project_id` in detail routes.

**Fix:** Verify the backend is returning `project_id` in session records:
```bash
curl -s http://localhost:8000/api/agent/planning/multi-project/session-board | jq '.sessions[0] | {id, project_id}'
```

If `project_id` is missing, check `backend/routers/agent.py` and the planning service layer.

---

## Related Documentation

- **PRD:** [`docs/project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md`](../project_plans/PRDs/enhancements/multi-project-planning-command-center-v1.md) — Feature requirements and acceptance criteria.
- **Implementation Plan:** [`docs/project_plans/implementation_plans/enhancements/multi-project-planning-command-center-v1.md`](../project_plans/implementation_plans/enhancements/multi-project-planning-command-center-v1.md) — Technical architecture and data contracts.
- **Rollout & Fallback:** [`docs/guides/multi-project-command-center-rollout.md`](./multi-project-command-center-rollout.md) — Staged rollout strategy and fallback procedures.
- **CLAUDE.md § Multi-Project Support:** [`CLAUDE.md`](../../CLAUDE.md) — Project switching and multi-project architecture overview.
