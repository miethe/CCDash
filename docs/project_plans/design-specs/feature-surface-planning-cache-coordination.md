---
schema_version: 2
doc_type: design_spec
id: feature-surface-planning-cache-coordination
title: "Feature-Surface / Planning Cache Coordination"
status: accepted
maturity: ready
created: 2026-04-23
updated: 2026-04-23
owner: Nick Miethe
tags: [cache, invalidation, feature-surface, planning, p4-011]
feature_slug: feature-surface-data-loading-redesign-v1
related_documents:
  - services/featureCacheBus.ts
  - services/featureSurfaceCache.ts
  - services/planning.ts
  - components/ProjectBoard.tsx
problem_statement: >
  Two independent browser caches coexist on the frontend. Feature writes
  (status change, phase progression, task update) must deterministically
  invalidate both or one will serve stale data silently.
open_questions: []
explored_alternatives:
  - "Option B: explicit write-through — document authoritative cache per key class and fan out at write sites manually."
---

# Feature-Surface / Planning Cache Coordination

## Context

Two browser-side caches hold feature data:

| Cache | Module | Keys | Bounded? |
|-------|--------|------|----------|
| **Feature Surface Cache** | `services/featureSurfaceCache.ts` | `projectId\|query\|page` (list) + `projectId\|sortedIds\|fields\|freshnessToken` (rollup) | Yes — 50 list + 100 rollup entries, 30 s TTL |
| **Planning Browser Cache** | `services/planning.ts` | `projectKey` → freshness bucket → payload type (summary/facets/list) | Yes — 8 projects, 3 freshness keys, 24 feature-context entries |

Prior to P4-011, feature writes (`updateFeatureStatus`, `updatePhaseStatus`, `updateTaskStatus`) only invalidated the Feature Surface Cache via `invalidateFeatureSurface()`. The Planning Browser Cache was **never invalidated** on feature writes, so planning views could display stale status counts and summaries until next navigation or hard refresh.

## Decision

**Option A — unified invalidation bus** (`services/featureCacheBus.ts`).

### Alternatives considered

**Option B (explicit write-through):** Each write site calls both `invalidateFeatureSurface()` and `clearPlanningBrowserCache()` directly. Simple to understand, but requires every future write site to import and call both helpers — easy to miss, and no enforcement mechanism.

**Option A (invalidation bus):** A tiny synchronous pub/sub module. Write sites call `publishFeatureWriteEvent(event)` once. Both caches subscribe at module init and handle their own eviction logic. New caches opt in by subscribing — no changes to existing write sites required.

### Why Option A

1. **Fewer write-site obligations.** Three write handlers in `ProjectBoard.tsx` already existed; adding a second direct import at each would have doubled the invalidation boilerplate.
2. **Decoupled extension.** A future third cache (e.g. analytics cache) subscribes to the bus without touching any write site.
3. **Single contract.** The event shape (`projectId`, `featureIds[]`, `kind`) is sufficient for both coarse (project-wide) and fine (feature-scoped) eviction strategies — each cache decides its own granularity.
4. **Cost.** The bus is ~80 lines; write-through documentation would have been comparable in size with weaker guarantees.

## Key Invariants

1. **Feature status write** → `publishFeatureWriteEvent({ projectId, featureIds: [id], kind: 'status' })` → both caches evict entries for that project.
2. **Phase progression** → same bus publish with `kind: 'phase'`.
3. **Task update** → same bus publish with `kind: 'task'`.
4. **Project switch** → the surface cache calls `invalidateFeatureSurface({ projectId })` directly (live-topic handler and project-switch handler); the planning cache is cleared separately via `clearPlanningBrowserCache(projectId)`. The bus is not used for project-switch because it is not a feature write.
5. **Sync completion** → both caches continue to handle this via their existing live-topic / periodic-revalidation paths; the bus is not involved.

## Eviction Granularity

| Cache | Bus subscriber behaviour |
|-------|--------------------------|
| Feature Surface | `invalidateFeatureSurface({ projectId, featureIds })` — fine-grained: evicts only list pages for the project + rollup entries that overlap the affected IDs. |
| Planning | `clearPlanningBrowserCache(projectId)` — coarse: evicts all entries for the project. The planning cache is freshness-keyed, so the next read triggers a fresh fetch and re-populates with correct status counts. |

The planning eviction is coarser than strictly necessary because its internal key structure (freshness bucket + payload type) does not embed feature IDs — adding feature-granular eviction would require a schema change to the planning cache that is out of scope for P4-011.

## Implementation Notes

- `services/featureCacheBus.ts` — the pub/sub module. Synchronous; no async boundary. Subscribers that throw are caught and logged so one bad subscriber cannot block the others.
- `services/featureSurfaceCache.ts` — subscribes at module-init time (bottom of file, after `invalidateFeatureSurface` is defined).
- `services/planning.ts` — subscribes at module-init time (after `clearPlanningBrowserCache` is defined).
- `components/ProjectBoard.tsx` — `handleStatusChange`, `handleFeatureStatusChange`, `handlePhaseStatusChange`, `handleTaskStatusChange` each call `publishFeatureWriteEvent(...)` after a successful API write. The existing `invalidateFeatureSurface()` call in `handleStatusChange` (board-level drag/drop) is retained for belt-and-suspenders React state reset.
- `_clearSubscribers()` / `_getSubscriberCount()` are exported from the bus for test isolation only — do not call from production code.
