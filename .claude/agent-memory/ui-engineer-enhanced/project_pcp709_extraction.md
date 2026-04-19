---
name: PCP-709 Planning Primitives Extraction
description: Five planning primitives extracted from CCDash to @miethe/ui 0.3.0 in PCP-709
type: project
---

Five CCDash planning primitives extracted to `@miethe/ui` v0.3.0 on 2026-04-17 (PCP-709):

- StatusChip + variants.ts
- EffectiveStatusChips (with inlined PlanningStatusProvenance types)
- MismatchBadge (lucide-react AlertTriangle)
- BatchReadinessPill (with inlined PlanningPhaseBatchReadinessState)
- PlanningNodeTypeIcon (with inlined PlanningNodeType union)

Destination: `/Users/miethe/dev/homelab/development/skillmeat/skillmeat/web/packages/ui/src/primitives/`

**Why:** PCP-709 extraction task; these primitives used in 2+ CCDash features and have stable APIs.

**How to apply:** Tests for @miethe/ui must be run from the web workspace root (`skillmeat/web/`), not from the package directory — Jest is configured at the monorepo web level, not per-package. Package build is run from the package directory (`npm run build`).
