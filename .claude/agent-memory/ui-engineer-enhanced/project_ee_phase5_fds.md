---
name: project_ee_phase5_fds
description: EE Phase 5 Wave 3 — FeatureDetailShell tabbed route + artifact rankings hook; key type constraints for planning types
metadata:
  type: project
---

FeatureDetailShell implemented at `components/Planning/FeatureDetailShell.tsx` for `/planning/feature/:featureId`.

**Why:** P5-006/P5-007 FE-B lane — tabbed feature detail replacing the drawer-style PlanningNodeDetail at the route level. PlanningNodeDetail remains for modal/drawer reuse.

**Key facts:**
- `FeaturePlanningContext` (types.ts:3348) does NOT have: `feature`, `description`, `currentPhase`, `tokenTelemetry`, `batches`, `blockers`, `decisions`. Use `effectiveStatus`/`rawStatus`, `totalTokens`, `phases[].batches`, `blockedBatchIds`, `ctxs`.
- `PhaseContextItem` has `phaseNumber`, `phaseTitle`, `effectiveStatus`, `rawStatus`, `batches`, `totalTasks`, `completedTasks`.
- `PlanningPhaseBatch` has `taskIds` (not `tasks`), `batchId`, `readinessState`, `assignedAgents`.
- `Chip` from PhaseZeroPrimitives is `HTMLAttributes<HTMLSpanElement>` — no `kind`/`label` props. `ArtifactChip` is the button variant with `kind`.
- `PlanningFeatureAgentLane` only accepts `featureId` and `className` — no `defaultGrouping`.
- Pre-existing vitest failures: PlanningAgentSessionBoard, PlanningFeatureAgentLane, planningHomePage tests all use `renderToStaticMarkup` which breaks in jsdom. Expected; not caused by this work.
- `analyticsKeys.artifactRankings(projectId)` already existed in queryKeys.ts — just needed the hook in `services/queries/analytics.ts`.

**How to apply:** Always check the real type shapes in types.ts before using FeaturePlanningContext fields. The context is sparse — many fields are optional or absent.
