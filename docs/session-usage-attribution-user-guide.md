# Session Usage Attribution User Guide

Last updated: 2026-03-10

Use usage attribution to answer which skills, agents, commands, artifacts, workflows, and features consumed workload in Claude Code sessions.

## Where it appears

- `/analytics?tab=attribution`
  - ranked attribution entities
  - calibration summary
  - per-entity event drill-down
- `/analytics?tab=workflow_intelligence`
  - attributed token, cost, coverage, and cache-share summary cards
  - per-scope attributed token metrics when attribution data is available
- `Session Inspector > Analytics`
  - session-level attribution summary for the current session only

## How to read the numbers

- `Exclusive`
  - tokens from primary attribution links only
  - this is the reconciliation-grade total
- `Supporting`
  - tokens from non-primary participation links
  - this can exceed session totals across overlapping entities
- `Attributed cost`
  - model-IO-derived cost only
  - cache workload is never shown as directly billable cost
- `Confidence`
  - rule confidence for the links that contributed to the row
  - higher is stronger evidence, not absolute truth

## Confidence interpretation

- High confidence
  - explicit signals such as direct skill invocation, linked subthread ownership, or direct command/artifact evidence
- Medium confidence
  - deterministic but indirect links such as workflow membership or bounded context windows
- Low confidence
  - heuristic participation links that are still useful for investigation but should not drive hard reconciliation decisions

## Common caveats

- Supporting totals are participation metrics. Do not add them together and treat them as a session total.
- Cache-heavy rows can look large without increasing model cost by the same amount.
- Ambiguous sessions are surfaced in calibration views instead of being forced into silent single-owner totals.
- Session totals remain authoritative for workload. Attribution is a derived analytical layer on top.

## Rollout controls

Usage attribution can be disabled without schema changes:

- `Settings > Projects > SkillMeat Integration > Usage Attribution`
  - hides attribution analytics and session attribution views for that project
- `CCDASH_SESSION_USAGE_ATTRIBUTION_ENABLED=false`
  - hard-disables attribution API surfaces globally

When disabled:

- the rest of `/analytics` still works
- workflow effectiveness still renders, but attribution-specific views are hidden or unavailable
- Session Inspector falls back to the rest of the analytics surface without attribution sections

## Recommended workflow

1. Open `/analytics?tab=attribution` to find the top exclusive consumers.
2. Inspect confidence and method mix before acting on a row.
3. Use the drill-down table to jump to the contributing sessions.
4. Open `Session Inspector > Analytics` to confirm the session-level context behind the attribution.
5. Use `/analytics?tab=workflow_intelligence` to compare yield against attributed token and cost patterns.
