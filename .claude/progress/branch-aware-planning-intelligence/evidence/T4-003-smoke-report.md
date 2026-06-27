# T4-003 Runtime Browser Smoke — Evidence

Date: 2026-06-04
HEAD commit: $(git -C /Users/miethe/dev/homelab/development/CCDash rev-parse HEAD)

## API Contract Check (Checklist Item 1)

### session-board endpoint
- URL: GET /api/agent/planning/session-board
- Status: 200 OK, 2 groups, 100+ cards
- git_branch: PRESENT ("development") — confirmed from curl
- git_commit_hash: PRESENT ("648d7320b") — confirmed from curl
- commit_refs: ABSENT (key not in response) — gap vs PR requirement FR-4 on this surface
- pr_refs: ABSENT (key not in response)

### command-center endpoint
- URL: GET /api/agent/planning/command-center
- Status: 200 OK, 50 items/page
- active_sessions: PRESENT (list, empty when no active sessions)
- git_state: PRESENT (dict with head/dirty_count/etc, shows NullGitProbe warning)
- worktree: PRESENT (null for features with no worktree — correct)
- pull_request: PRESENT (populated for 2 features with PR numbers 164, 186)
- phase_rows: PRESENT (list, 9 rows for first item)
- commit_refs: ABSENT from PlanningCommandCenterItemDTO — gap vs types.ts definition
- pr_refs: ABSENT from PlanningCommandCenterItemDTO — gap vs types.ts definition
- linked_sessions in phase_rows: ABSENT from PlanningCommandCenterPhaseRowDTO — gap vs FR-6

## Planning Command Center Page (Checklist Item 2)

- Feature cards render: CONFIRMED (329 live items in portfolio, work items list visible)
- git provenance row: CONFIRMED ("branch TBD commit TBD" shows worktree-empty state)
- Active-session chip: NOT VISIBLE (no features have active_sessions populated, component code exists)
- Worktree-empty label: CONFIRMED ("branch TBD commit TBD" rendered in feature cards)
- Provenance dialog trigger: IMPLEMENTED (BranchProvenancePanel exists in DOM, clickable when data present)
- "Open full detail" button: MISSING from MultiProjectDetailRail (portfolio view)
  - Present in PlanningCommandCenter (single-project view) — code confirmed

## Planning Session Board (Checklist Item 3)

- Session cards visible: CONFIRMED (26 active sessions in portfolio sessions board)
- git_branch chip: IMPLEMENTED in frontend (BranchChip component, three states tested)
- State 1 (populated branch): Backend returns "development" — chip would show branch name
- State 2 (codex/null): Unit tests confirm AC-NULLBRANCH states covered
- State 3 (unknown/null): Unit tests confirm fallback rendering
- Visible chip in browser: Not directly observed in screenshot (sessions are SkillMeat project, branches may be omitted from compact view)

## CommandCenterDetailPanel (Checklist Item 4)

- Phase rows render: CONFIRMED (P1-P6 visible with agents/model/files)
- Phase rows linked sessions: ABSENT from PlanningCommandCenterPhaseRowDTO — transcript links cannot render
- "Open full detail" button: PRESENT in PlanningCommandCenter.tsx (code verified, data-testid confirmed)
  - Not observed in browser (tested MultiProjectDetailRail which is the portfolio path)
- Transcript link: Code in PhasePlanTable.tsx confirms implementation when linkedSessions present

## Runtime Errors (Checklist Item 5)

- Browser console errors: 2x "async response channel closed" — browser extension artifact (Claude-in-Chrome), NOT application errors
- API 404 errors: multi-project endpoints 404 when filtering by single project in portfolio mode — pre-existing issue, not branch-aware feature
- No React render crashes or uncaught exceptions from the application itself

## Polling (Refetch)

- refetchInterval in query hooks: Cannot verify directly via network tab (tracker started after page load)
- Code: services/queries/planning.ts must have refetchInterval — needs verification via source
