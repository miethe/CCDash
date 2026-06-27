---
slug: planning-command-center-ux
status: completed
repo: CCDash
created: 2026-05-28
source: /quick-feature (invoked from citytile_pack; work belongs to CCDash)
---

# Planning Command Center — UX polish

Recently-refactored Planning Command Center (`components/Planning/CommandCenter/`). Four scoped UX fixes.

## Requirements

1. **Dynamic pane width.** Give the Command Center more horizontal width, responsive to screen size.
   Inner boxes scale in ratios so more detail shows. Today the planning canvas is hard-capped at
   `max-w-[1680px]` (`PlanningRouteLayout.tsx:195`) and BoardView forces `min-w-[1380px] grid-cols-5`
   (horizontal scroll). **Decision (assumption):** widen only the Command Center, not all planning pages.

2. **Board card status indicator** (`CommandCenterFeatureCard.tsx`). Move `StatusPill` to the very
   top-right of the card and make it smaller. Put title + feature slug in their own full-width "zone"
   (no longer sharing the row with the pill).

3. **Next Command box** (card + detail). Add a copy icon that copies the command to clipboard. Hovering
   the box opens a **code-formatted tooltip** showing the full command. Container already has
   `copyCommand` + toast; BoardView does not yet receive `onCopyCommand` — thread it through.

4. **Branch name** — copy on click (the `GitBranch` row in the card).

## Affected files (CCDash)
- `components/Planning/CommandCenter/CommandCenterFeatureCard.tsx` — card layout, status pill, next-command copy+tooltip, branch copy
- `components/Planning/CommandCenter/CommandCenterBoardView.tsx` — thread `onCopyCommand`
- `components/Planning/CommandCenter/PlanningCommandCenter.tsx` — pass `onCopyCommand` to BoardView; possibly opt into wider container
- `components/Planning/PlanningRouteLayout.tsx` and/or `PlanningHomePage.tsx` — responsive width for Command Center
- `components/Planning/CommandCenter/CommandCenterCardView.tsx` — if it shares `FeatureCard`, verify consistent result
- `components/Planning/CommandCenter/__tests__/` — update/add coverage
- Reuse: `@/components/ui/tooltip` (Radix), `StatusPill` from `../primitives`

## Quality gates
`pnpm typecheck && pnpm test && pnpm build`  (no lint script in package.json)
