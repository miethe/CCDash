## Completion Report — Phase 4 Remediation (post-T4-002 FIX-REQUIRED + T4-003 partial)

### Summary

All 9 issues from the phase-4 reviewer verdicts (T4-002 FIX-REQUIRED, T4-003 partial) were addressed
in commit `06a4826`. The fixes close four critical/high data-seam gaps that prevented branch chips,
active-session chips, and provenance panels from ever rendering from live API data. New adapter-path
unit tests (17 tests) and QueryClientProvider fixes (52 board tests now pass) provide test coverage
that was previously absent or bypassed via hand-constructed fixtures.

### Files Changed

- `services/planning.ts` — Added `WireSessionLink` interface; added `git_branch`/`git_commit_hash` to `WirePlanningAgentSessionCard`; added `linked_sessions_by_phase` to `WirePhaseContextItem`; added `SessionLink` import; added `adaptWireSessionLink`, `adaptLinkedSessionsByPhase` helpers; updated `adaptPhaseContextItem` to map `linkedSessionsByPhase`; updated `adaptPlanningAgentSessionCard` to map `gitBranch`/`gitCommitHash`
- `services/planningCommandCenter.ts` — Added `AggregateWorkItemSession`, `SessionLink` imports; added `adaptAggregateWorkItemSession` helper; added `adaptLinkedSession` helper; updated `phaseRow` to map `linkedSessions`; updated `adaptPlanningCommandCenterItem` to map `activeSessions`/`commitRefs`/`prRefs`
- `backend/application/services/agent_queries/models.py` — Added `linked_sessions: list[SessionLink]` to `PlanningCommandCenterPhaseRowDTO`; added `commit_refs`/`pr_refs`/docstrings to `PlanningCommandCenterItemDTO`
- `backend/application/services/agent_queries/planning_command_center.py` — Added `SessionLink`, `_load_phase_session_links` imports; updated `_phase_rows()` to accept optional `phase_session_map`; updated `_build_item` to accept `ports`/`project_id` and compute phase session map; updated both `_build_item` call sites to pass `ports` and `project_id`; `_build_item` now populates `commit_refs`/`pr_refs` from feature attributes
- `components/Planning/__tests__/PlanningAgentSessionBoard.test.tsx` — Added `usePlanningSessionBoardQuery` mock (isPending=true) to bypass QueryClientProvider requirement; updated 3 loading-state tests to reflect `inView` gate (T4-007)
- `services/__tests__/planningAdapterFields.test.ts` — New file: 17 adapter-path tests covering all 4 seam field groups with populated + absent-field fallback cases

### Acceptance Criteria Status

- [x] AC-NULLBRANCH-1/2 — `gitBranch` now flows from wire `git_branch` through `adaptPlanningAgentSessionCard` to `BranchChip`
- [x] AC-ACTIVE-SESSION-CHIP — `activeSessions` now mapped in `adaptPlanningCommandCenterItem`
- [x] AC-BRANCH-DIALOG — `commitRefs`/`prRefs` now mapped in `adaptPlanningCommandCenterItem`
- [x] FR-6 (AC-PHASE-SESSION-LINKS) — backend `linked_sessions` added to `PlanningCommandCenterPhaseRowDTO` and populated; FE adapter maps `linkedSessions`
- [x] PhaseContextItem `linkedSessionsByPhase` — `WirePhaseContextItem.linked_sessions_by_phase` now mapped through adapter; backend producer already populated this field
- [ ] Runtime browser smoke — T4-003 pending; requires new run after adapter fixes in 06a4826

### Validation Run

| Command | Result | Notes |
|---|---|---|
| `pnpm test services/__tests__/planningAdapterFields.test.ts` | Pass (17/17) | New adapter-path tests |
| `pnpm test services/__tests__/planningCommandCenter.test.ts` | Pass (4/4) | Existing CC service tests |
| `pnpm test services/__tests__/planning.test.ts` | Pass (via batch) | Existing planning service tests |
| `pnpm test components/Planning/__tests__/PlanningAgentSessionBoard.test.tsx` | Pass (52/52) | Was 9 failures before fix |
| `pnpm test components/Planning/CommandCenter/__tests__/commandCenterFeatureCardActiveSessions.test.tsx` | Pass (29/29) | |
| `pnpm test components/Planning/CommandCenter/__tests__/commandCenterBranchProvenanceDialog.test.tsx` | Pass (35/35) | |
| `backend/.venv/bin/python -m pytest backend/tests/test_branch_aware_planning_contract.py` | Pass (40/40) | Backend contract tests |
| `pnpm typecheck` | Pre-existing errors only | No new type errors from our changes |
| Runtime smoke | Not run | T4-003 pending; adapters fixed, smoke required |

### Deviations From Contract

- Fix 3 (AC-PHASE-SESSION-LINKS): `_load_phase_session_links` is called in `_build_item` (not `_phase_rows` directly) because `_phase_rows` is a standalone function without DB access. The ports+project_id are forwarded from the two public call sites. The result (phase_session_map) is passed to `_phase_rows` as an optional argument.
- Fix 6 (QueryClientProvider): Rather than wrap renders in `QueryClientProvider`, we mock `usePlanningSessionBoardQuery` at the hook level (matching the established pattern in `planningHomePage.smoke.test.tsx`). This is cleaner and matches project convention.

### Risks and Limitations

- Runtime smoke (T4-003) is the only remaining open item. The adapter data paths are now correct; the smoke run should verify that the UI renders branch chips, session chips, and provenance entries from a live dev server.
- `ac-coverage-report.py` returns 0 ACs for this plan because the implementation plan uses prose-section AC format (not the structured `#### AC R3.4:` block format the tool expects). This is a tooling limitation, not a coverage gap — all ACs were verified manually and via the new adapter-path tests.

### Follow-Up Recommendations

- Update the implementation plan ACs to the structured block format so `ac-coverage-report.py` can process them automatically in future phases.
- Consider adding `git_commit_hash` to the BranchChip or session card subtitle (the wire field is now flowing but only `gitBranch` is rendered in the UI).

### Memory Candidates Captured

- The `inView` gate (T4-007) in `PlanningAgentSessionBoard` uses `IntersectionObserver` which never fires in SSR (`renderToStaticMarkup`). Loading-skeleton tests must account for this: `isPending=true` does not show the skeleton until `inView=true`. Mock the hook instead of wrapping in QueryClientProvider.
- The `adaptAggregateWorkItemSession` function lives in `services/planningCommandCenter.ts` (not `multiProjectPlanningCommandCenter.ts` where the other aggregate adapters live). The command-center item adapter was missing this entirely.
