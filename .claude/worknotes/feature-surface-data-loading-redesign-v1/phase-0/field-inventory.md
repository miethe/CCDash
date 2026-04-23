---
type: worknotes
doc_type: worknotes
prd: feature-surface-data-loading-redesign-v1
phase: 0
task: P0-001
created: 2026-04-23
---

# Feature Surface Field Inventory

## Summary

This inventory traces every metric, count, filter value, sort key, search field, status indicator, and modal section currently rendered across six feature surfaces: `ProjectBoard.tsx` (kanban card and list card), `ProjectBoardFeatureModal` (seven tabs embedded in `ProjectBoard.tsx`), `PlanningHomePage.tsx`, `FeatureExecutionWorkbench.tsx`, `SessionInspector.tsx` (features tab), and the feature list view (which is the list-mode render path inside `ProjectBoard`). Type sources were traced from `Feature`, `FeaturePhase`, `FeatureSessionLink`, `FeatureSessionSummary`, `FeatureExecutionContext`, `FeatureExecutionAnalyticsSummary`, `FeatureSummaryItem`, `ProjectPlanningSummary`, and the locally-defined `SessionFeatureLink` interface inside `SessionInspector`. The primary hotspot is the board's per-card linked-session fetch: `loadFeatureSessionSummary` fires one `GET /api/features/{id}/linked-sessions` call per visible card and then runs `buildFeatureSessionSummary` over the full session array in-component to produce the card-level session indicator values.

---

## 1. ProjectBoard — Board Card (`FeatureCard`) and List Card (`FeatureListCard`)

Both card variants render from the same `Feature` object plus an optional `FeatureSessionSummary` loaded per card. All filtering, sorting, and session indicator fields are included.

| Surface | UI Label / Purpose | Source field (current) | Source path (type/interface) | Exact vs Derived vs Aggregate | Owning component | Notes |
|---|---|---|---|---|---|---|
| Board card | Feature ID (mono badge) | `feature.id` | `Feature.id` | Exact | `FeatureCard` | |
| Board card | Feature name headline | `feature.name` | `Feature.name` | Exact | `FeatureCard` | |
| Board card | Status badge + editable dropdown | `feature.status` | `Feature.status` | Exact | `FeatureCard` / `StatusDropdown` | |
| Board card | Planning status chips (rawStatus, effectiveStatus) | `feature.planningStatus.rawStatus`, `.effectiveStatus` | `Feature.planningStatus` → `PlanningEffectiveStatus` | Exact | `EffectiveStatusChips` | |
| Board card | Mismatch badge (isMismatch, state, reason) | `feature.planningStatus.mismatchState` | `Feature.planningStatus.mismatchState` | Exact | `MismatchBadge` | |
| Board card | Deferred caveat label | `getFeatureDeferredCount(feature) > 0` | `Feature.deferredTasks`, `Feature.phases[].deferredTasks` | Derived | `FeatureCard` | Falls back to summing phases when top-level field absent |
| Board card | Progress bar (completed / total) | `getFeatureCompletedCount(feature)`, `feature.totalTasks` | `Feature.completedTasks`, `Feature.totalTasks` | Exact + Derived | `ProgressBar` | `getFeatureCompletedCount` ensures deferred tasks count as completed |
| Board card | Progress bar deferred segment | `getFeatureDeferredCount(feature)` | `Feature.deferredTasks`, `Feature.phases[].deferredTasks` | Derived | `ProgressBar` | |
| Board card | Linked docs count + type breakdown (hover) | `feature.linkedDocs.length`, `buildLinkedDocTypeCounts(feature.linkedDocs)` | `Feature.linkedDocs[]` → `LinkedDocument` | Derived | `LinkedDocsSummaryBadge` | Requires full `linkedDocs` array on the Feature |
| Board card | Phase count | `feature.phases.length` | `Feature.phases[]` | Derived | `FeatureCard` | |
| Board card | Priority badge | `feature.priority` | `Feature.priority` | Exact | `FeatureCard` | |
| Board card | Execution readiness badge | `feature.executionReadiness` | `Feature.executionReadiness` | Exact | `FeatureCard` | |
| Board card | Document coverage summary ("Docs: n/m") | `getFeatureCoverageSummary(feature)` | `Feature.documentCoverage.present`, `.missing` | Derived | `FeatureCard` | |
| Board card | Related feature count ("links N") | `getFeatureLinkedFeatureCount(feature)` | `Feature.linkedFeatures?.length` or `Feature.relatedFeatures?.length` | Derived | `FeatureCard` | |
| Board card | Category label (footer) | `feature.category` | `Feature.category` | Exact | `FeatureCard` | |
| Board card | Primary date + label (Planned/Started/Completed) | `getFeaturePrimaryDate(feature)` | `Feature.dates`, `Feature.plannedAt`, `Feature.startedAt`, `Feature.completedAt`, `Feature.updatedAt` | Derived | `FeatureKanbanDateModule` | Selects the contextually appropriate date by status |
| Board card | Days-between display ("Nd") | `getDaysBetween(first.value, completed.value)` | `Feature.dates.*` | Derived | `FeatureKanbanDateModule` | |
| Board card | Session indicator — total linked sessions | `sessionSummary.total` | `FeatureSessionSummary.total` | **Aggregate (requires full session array)** | `FeatureSessionIndicator` | Built from `buildFeatureSessionSummary(sessions)` over full `/linked-sessions` response |
| Board card | Session indicator — main thread count | `sessionSummary.mainThreads` | `FeatureSessionSummary.mainThreads` | **Aggregate (requires full session array)** | `FeatureSessionIndicator` | |
| Board card | Session indicator — sub-thread count | `sessionSummary.subThreads` | `FeatureSessionSummary.subThreads` | **Aggregate (requires full session array)** | `FeatureSessionIndicator` | |
| Board card | Session indicator — observed workload tokens | `sessionSummary.workloadTokens` | `FeatureSessionSummary.workloadTokens` | **Aggregate (requires full session array)** | `FeatureSessionIndicator` | Calls `resolveTokenMetrics` per session with subthread awareness |
| Board card | Session indicator — cache input tokens + cache% | `sessionSummary.cacheInputTokens`, cache% derived | `FeatureSessionSummary.cacheInputTokens`, `.workloadTokens` | **Aggregate (requires full session array)** | `FeatureSessionIndicator` | |
| Board card | Session indicator — unresolved sub-thread count | `sessionSummary.unresolvedSubThreads` | `FeatureSessionSummary.unresolvedSubThreads` | **Aggregate (requires full session array)** | `FeatureSessionIndicator` | |
| Board card | Session indicator — session type breakdown (hover) | `sessionSummary.byType[]` | `FeatureSessionSummary.byType[]` | **Aggregate (requires full session array)** | `FeatureSessionIndicator` | |
| List card | Feature ID | `feature.id` | `Feature.id` | Exact | `FeatureListCard` | |
| List card | Feature name | `feature.name` | `Feature.name` | Exact | `FeatureListCard` | |
| List card | Status | `feature.status` | `Feature.status` | Exact | `FeatureListCard` | |
| List card | Planning status chips | `feature.planningStatus` | `Feature.planningStatus` | Exact | `EffectiveStatusChips` | |
| List card | Mismatch badge | `feature.planningStatus.mismatchState` | `Feature.planningStatus.mismatchState` | Exact | `MismatchBadge` | |
| List card | Category | `feature.category` | `Feature.category` | Exact | `FeatureListCard` | |
| List card | Completed / total task count | `featureCompletedTasks / feature.totalTasks` | `Feature.completedTasks`, `Feature.totalTasks` | Exact + Derived | `FeatureListCard` | |
| List card | Deferred caveat label | `hasDeferredCaveat(feature)` | `Feature.deferredTasks`, `Feature.status` | Derived | `FeatureListCard` | |
| List card | Progress bar | same as board card | same as board card | Derived | `ProgressBar` | |
| List card | Date stack (Planned/Started + Completed) | `getFeatureDateModule(feature)` | `Feature.dates`, `Feature.plannedAt`, `Feature.startedAt`, `Feature.completedAt` | Derived | `FeatureDateStack` | |
| List card | Priority | `feature.priority` | `Feature.priority` | Exact | `FeatureListCard` | |
| List card | Execution readiness | `feature.executionReadiness` | `Feature.executionReadiness` | Exact | `FeatureListCard` | |
| List card | Doc coverage summary | `getFeatureCoverageSummary(feature)` | `Feature.documentCoverage` | Derived | `FeatureListCard` | |
| List card | Related feature links count | `getFeatureLinkedFeatureCount(feature)` | `Feature.linkedFeatures`, `Feature.relatedFeatures` | Derived | `FeatureListCard` | |
| List card | Linked docs badge | `feature.linkedDocs` | `Feature.linkedDocs[]` | Derived | `LinkedDocsSummaryBadge` | |
| List card | Phase count | `feature.phases.length` | `Feature.phases[]` | Derived | `FeatureListCard` | |
| List card | Session indicator (same fields as board card) | `sessionSummary.*` | `FeatureSessionSummary.*` | **Aggregate (requires full session array)** | `FeatureSessionIndicator` | Same hotspot, same call |

**Filters applied to the feature list:**

| Surface | UI Label / Purpose | Source field (current) | Source path | Exact vs Derived | Owning component |
|---|---|---|---|---|---|
| Board filter | Text search (name, id, tags) | `f.name`, `f.id`, `f.tags[]` | `Feature.name`, `Feature.id`, `Feature.tags[]` | Exact | `ProjectBoard` (in-memory) |
| Board filter | Status filter dropdown | `getFeatureBoardStage(f)` → `feature.status` | `Feature.status` | Derived | `ProjectBoard` (in-memory) |
| Board filter | Deferred caveat filter | `hasDeferredCaveat(f)` | `Feature.status`, `Feature.deferredTasks` | Derived | `ProjectBoard` (in-memory) |
| Board filter | Category filter dropdown | `f.category` | `Feature.category` | Exact | `ProjectBoard` (in-memory) |
| Board filter | Planned from/to date range | `getFeatureDateValue(f, 'plannedAt')` | `Feature.dates.plannedAt`, `Feature.plannedAt` | Derived | `ProjectBoard` (in-memory) |
| Board filter | Started from/to date range | `getFeatureDateValue(f, 'startedAt')` | `Feature.dates.startedAt`, `Feature.startedAt` | Derived | `ProjectBoard` (in-memory) |
| Board filter | Completed from/to date range | `getFeatureDateValue(f, 'completedAt')` | `Feature.dates.completedAt`, `Feature.completedAt` | Derived | `ProjectBoard` (in-memory) |
| Board filter | Updated from/to date range | `getFeatureDateValue(f, 'updatedAt')` | `Feature.dates.updatedAt`, `Feature.updatedAt` | Derived | `ProjectBoard` (in-memory) |
| Board sort | Sort by recent (default) | `getFeatureDateValue(f, 'updatedAt')` | `Feature.dates.updatedAt`, `Feature.updatedAt` | Derived | `ProjectBoard` (in-memory) |
| Board sort | Sort by progress | `getFeatureCompletedCount(f) / f.totalTasks` | `Feature.completedTasks`, `Feature.totalTasks` | Derived | `ProjectBoard` (in-memory) |
| Board sort | Sort by task count | `f.totalTasks` | `Feature.totalTasks` | Exact | `ProjectBoard` (in-memory) |

---

## 2. ProjectBoardFeatureModal — All Tabs

The modal loads `GET /api/features/{id}` (full feature detail) and `GET /api/features/{id}/linked-sessions` (full session array) on every mount, regardless of which tab is active.

### Overview Tab

| Surface | UI Label / Purpose | Source field (current) | Source path (type/interface) | Exact vs Derived vs Aggregate | Owning component | Notes |
|---|---|---|---|---|---|---|
| Modal / Overview | Feature ID badge | `feature.id` | `Feature.id` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Overview | Status dropdown (editable) | `activeFeature.status` | `Feature.status` | Exact | `StatusDropdown` | |
| Modal / Overview | Category badge | `activeFeature.category` | `Feature.category` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Overview | Deferred badge | `featureDeferredTasks > 0` | Derived from `Feature.deferredTasks` | Derived | `ProjectBoardFeatureModal` | |
| Modal / Overview | Progress bar + percent complete | `featureCompletedTasks / activeFeature.totalTasks * 100` | `Feature.completedTasks`, `Feature.totalTasks` | Derived | `ProgressBar` | |
| Modal / Overview | Completed/total task count | `featureCompletedTasks`, `activeFeature.totalTasks` | `Feature.completedTasks`, `Feature.totalTasks` | Exact + Derived | `ProjectBoardFeatureModal` | |
| Modal / Overview | Deferred count | `featureDeferredTasks` | Derived from `Feature.deferredTasks` / phases | Derived | `ProjectBoardFeatureModal` | |
| Modal / Overview | Primary date label + value + confidence | `getFeaturePrimaryDate(activeFeature)` | `Feature.dates.*`, `Feature.plannedAt`, `Feature.startedAt`, `Feature.completedAt`, `Feature.updatedAt` | Derived | `ProjectBoardFeatureModal` | |
| Modal / Overview | Total Tasks tile | `activeFeature.totalTasks` | `Feature.totalTasks` | Exact | `FeatureMetricTile` | |
| Modal / Overview | Completed tile (done count) | `featureDoneTasks` | `Feature.completedTasks`, `Feature.deferredTasks` | Derived | `FeatureMetricTile` | |
| Modal / Overview | Phases count tile | `phases.length` | `Feature.phases[]` | Derived | `FeatureMetricTile` | |
| Modal / Overview | Documents count tile | `linkedDocs.length` | `Feature.linkedDocs[]` | Derived | `FeatureMetricTile` | |
| Modal / Overview | Priority field | `activeFeature.priority` | `Feature.priority` | Exact | `FeatureField` | |
| Modal / Overview | Risk field | `activeFeature.riskLevel` | `Feature.riskLevel` | Exact | `FeatureField` | |
| Modal / Overview | Complexity field | `activeFeature.complexity` | `Feature.complexity` | Exact | `FeatureField` | |
| Modal / Overview | Track field | `activeFeature.track` | `Feature.track` | Exact | `FeatureField` | |
| Modal / Overview | Family field | `activeFeature.featureFamily` | `Feature.featureFamily` | Exact | `FeatureField` | |
| Modal / Overview | Target release field | `activeFeature.targetRelease` | `Feature.targetRelease` | Exact | `FeatureField` | |
| Modal / Overview | Milestone field | `activeFeature.milestone` | `Feature.milestone` | Exact | `FeatureField` | |
| Modal / Overview | Execution readiness field | `activeFeature.executionReadiness` | `Feature.executionReadiness` | Exact | `FeatureField` | |
| Modal / Overview | Document coverage field | `getFeatureCoverageSummary(activeFeature)` | `Feature.documentCoverage.present`, `.missing` | Derived | `FeatureField` | |
| Modal / Overview | Blockers count (Quality Signals) | `activeFeature.qualitySignals?.blockerCount` | `Feature.qualitySignals.blockerCount` | Exact | `FeatureField` | |
| Modal / Overview | At-risk task count | `activeFeature.qualitySignals?.atRiskTaskCount` | `Feature.qualitySignals.atRiskTaskCount` | Exact | `FeatureField` | |
| Modal / Overview | Blocked-by relations count | `blockedByRelations.length` | `Feature.linkedFeatures[]` filtered by type='blocked_by' | Derived | `FeatureField` | |
| Modal / Overview | Test impact | `activeFeature.testImpact || activeFeature.qualitySignals?.testImpact` | `Feature.testImpact`, `Feature.qualitySignals.testImpact` | Exact | `FeatureField` | |
| Modal / Overview | Total related features count | `getFeatureLinkedFeatureCount(activeFeature)` | `Feature.linkedFeatures`, `Feature.relatedFeatures` | Derived | `FeatureField` | |
| Modal / Overview | Integrity signal refs | `activeFeature.qualitySignals?.integritySignalRefs[]` | `Feature.qualitySignals.integritySignalRefs` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Overview | Execution gate state label | `executionGate?.state` | `Feature.executionGate.state` | Exact | `FeatureModalSection` | |
| Modal / Overview | Execution gate ready | `executionGate?.isReady` | `Feature.executionGate.isReady` | Exact | `FeatureField` | |
| Modal / Overview | Execution gate waiting on family | `executionGate?.waitingOnFamilyPredecessor` | `Feature.executionGate.waitingOnFamilyPredecessor` | Exact | `FeatureField` | |
| Modal / Overview | Execution gate reason | `executionGate?.reason` | `Feature.executionGate.reason` | Exact | `FeatureModalSection` | |
| Modal / Overview | Next family item label | `familyPosition?.nextItemLabel || nextFamilyItem?.featureName` | `Feature.executionGate.familyPosition.nextItemLabel`, `Feature.familySummary.nextRecommendedFamilyItem` | Derived | `FeatureField` | |
| Modal / Overview | Family position label | `getFamilyPositionLabel(familyPosition)` | `Feature.familyPosition`, `Feature.executionGate.familyPosition` | Derived | `FeatureField` | |
| Modal / Overview | Sequenced items count | `familySummary?.sequencedItems ?? familyPosition?.sequencedItems` | `Feature.familySummary.sequencedItems`, `Feature.familyPosition.sequencedItems` | Exact | `FeatureField` | |
| Modal / Overview | Unsequenced items count | `familySummary?.unsequencedItems` | `Feature.familySummary.unsequencedItems` | Exact | `FeatureField` | |
| Modal / Overview | Next recommended feature ID | `familySummary?.nextRecommendedFeatureId || nextFamilyItem?.featureId` | `Feature.familySummary.nextRecommendedFeatureId` | Exact | `FeatureField` | |
| Modal / Overview | Blocking evidence items (up to 3) | `blockingEvidence[]` | `Feature.blockingFeatures[]` or `Feature.dependencyState.dependencies[]` | Exact | `FeatureModalSection` | |
| Modal / Overview | Blocker evidence count badge | `blockingEvidence.length` | same | Derived | `FeatureModalSection` | |
| Modal / Overview | Planned / Started / Completed / Updated dates + confidence | `getFeatureDateValue(activeFeature, key)` | `Feature.dates.*` + fallback scalar fields | Derived | `ProjectBoardFeatureModal` | |
| Modal / Overview | Hard dependency feature IDs | `blockedByRelations[].feature` | `Feature.linkedFeatures[]` filtered by type='blocked_by' | Derived | `FeatureModalSection` | |
| Modal / Overview | Family sequence docs (sequenceOrder) | `sequenceDocs[]` | `Feature.linkedDocs[]` filtered `typeof sequenceOrder === 'number'` | Derived | `FeatureModalSection` | |
| Modal / Overview | Linked documents list (ordered) | `orderedLinkedDocs[]` | `Feature.linkedDocs[]` | Exact | `FeatureModalSection` | |
| Modal / Overview | Related feature IDs | `activeFeature.relatedFeatures[]` | `Feature.relatedFeatures[]` | Exact | `FeatureModalSection` | |
| Modal / Overview | Tags | `activeFeature.tags[]` | `Feature.tags[]` | Exact | `FeatureModalSection` | |
| Modal / Overview | Family name (docs tab metric tile) | `familySummary?.featureFamily || activeFeature.featureFamily` | `Feature.familySummary.featureFamily`, `Feature.featureFamily` | Exact | `FeatureMetricTile` | |

### Phases Tab

| Surface | UI Label / Purpose | Source field (current) | Source path (type/interface) | Exact vs Derived vs Aggregate | Owning component | Notes |
|---|---|---|---|---|---|---|
| Modal / Phases | Phase status filter | local state against `phase.status` | `Feature.phases[].status` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Phases | Task status filter | local state against `task.status` | `Feature.phases[].tasks[].status` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Phases | Phase number + title | `phase.phase`, `phase.title` | `FeaturePhase.phase`, `FeaturePhase.title` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Phases | Phase status dot + label | `phase.status` | `FeaturePhase.status` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Phases | Phase deferred count | `phaseDeferredTasks` | `FeaturePhase.tasks[].status === 'deferred'` | Derived | `ProjectBoardFeatureModal` | |
| Modal / Phases | Phase progress bar | `phaseCompletedTasks / phaseTotalTasks` | `FeaturePhase.completedTasks`, `FeaturePhase.totalTasks`, `FeaturePhase.tasks[]` | Exact + Derived | `ProgressBar` | |
| Modal / Phases | Phase-linked session IDs (up to 3+) | `phaseSessionLinks.get(phase.phase)[]` | `FeatureSessionLink.relatedPhases[]`, full session array | **Aggregate (requires full session array)** | `ProjectBoardFeatureModal` | Built from `linkedSessions` state loaded via `/linked-sessions` |
| Modal / Phases | Phase-linked commit hashes (up to 5+) | `phaseCommitLinks.get(phase.phase)[]` | `FeatureSessionLink.sessionMetadata.commitCorrelations[].commitHash` | **Aggregate (requires full session array)** | `ProjectBoardFeatureModal` | |
| Modal / Phases | Task ID + title | `task.id`, `task.title` | `ProjectTask.id`, `ProjectTask.title` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Phases | Task status | `task.status` | `ProjectTask.status` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Phases | Task owner | `task.owner` | `ProjectTask.owner` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Phases | Task-linked session IDs | `taskSessionLinksByTaskId.get(task.id)[]` | `ProjectTask.sessionId`, `FeatureSessionLink.relatedTasks[]` | **Aggregate (requires full session array)** | `ProjectBoardFeatureModal` | |
| Modal / Phases | Task-linked commit hashes | `taskCommitLinksByTaskId.get(task.id)[]` | `FeatureSessionLink.sessionMetadata.commitCorrelations[]` | **Aggregate (requires full session array)** | `ProjectBoardFeatureModal` | |

### Documents Tab

| Surface | UI Label / Purpose | Source field (current) | Source path (type/interface) | Exact vs Derived vs Aggregate | Owning component | Notes |
|---|---|---|---|---|---|---|
| Modal / Docs | Document group count tile | `groupedDocs.length` | Derived from `Feature.linkedDocs[]` classification | Derived | `FeatureMetricTile` | |
| Modal / Docs | Linked doc total count | `linkedDocs.length` | `Feature.linkedDocs[]` | Derived | `FeatureMetricTile` | |
| Modal / Docs | Family position tile | `getFamilyPositionLabel(familyPosition)` | `Feature.familyPosition`, `Feature.executionGate.familyPosition` | Derived | `FeatureMetricTile` | |
| Modal / Docs | Execution gate tile label | `getExecutionGateLabel(executionGate?.state)` | `Feature.executionGate.state` | Exact | `FeatureMetricTile` | |
| Modal / Docs | Doc type count breakdown | `docTypeCounts[]` → `{docType, count}` | `Feature.linkedDocs[].docType` | Derived | `ProjectBoardFeatureModal` | |
| Modal / Docs | Document cards (title, filePath, docType, status, featureFamily, sequenceOrder, prdRef, blockedBy) | `doc.*` | `LinkedDocument.*` | Exact | `FeatureDocCard` | |
| Modal / Docs | Doc primary/supporting badge | `isPrimaryDoc(doc)` | `Feature.primaryDocuments.*` | Derived | `FeatureDocCard` | |

### Relations Tab

| Surface | UI Label / Purpose | Source field (current) | Source path (type/interface) | Exact vs Derived vs Aggregate | Owning component | Notes |
|---|---|---|---|---|---|---|
| Modal / Relations | Dependency evidence list | `blockingEvidence[].dependencyFeatureName/Id/Status/state/blockingReason/evidence/blockingDocumentIds` | `Feature.blockingFeatures[]` or `Feature.dependencyState.dependencies[]` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Relations | Family name, position, next item, recommended feature | `familySummary.*`, `familyPosition.*`, `nextFamilyItem.*` | `Feature.familySummary`, `Feature.familyPosition`, `Feature.executionGate.familyPosition` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Relations | Typed linked feature relations (feature, type, source, confidence, notes) | `activeFeature.linkedFeatures[]` | `Feature.linkedFeatures[]` → `LinkedFeatureRef` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Relations | Related feature IDs | `activeFeature.relatedFeatures[]` | `Feature.relatedFeatures[]` | Exact | `ProjectBoardFeatureModal` | |
| Modal / Relations | Lineage signals (lineageFamily, lineageParent, lineageChildren) | `linkedDocs[].lineageFamily/lineageParent/lineageChildren` | `LinkedDocument.lineageFamily`, `.lineageParent`, `.lineageChildren` | Exact | `ProjectBoardFeatureModal` | |

### Sessions Tab

| Surface | UI Label / Purpose | Source field (current) | Source path (type/interface) | Exact vs Derived vs Aggregate | Owning component | Notes |
|---|---|---|---|---|---|---|
| Modal / Sessions | Total linked sessions tile | `linkedSessions.length` | Local state built from `/linked-sessions` | **Aggregate (requires full session array)** | `FeatureMetricTile` | |
| Modal / Sessions | Primary focus session count tile detail | `primarySessionCount` | Derived by `countThreadNodes(primarySessionRoots)` | **Aggregate (requires full session array)** | `FeatureMetricTile` | |
| Modal / Sessions | Sub-threads tile count | `linkedSessions.filter(isSubthreadSession).length` | Local state | **Aggregate (requires full session array)** | `FeatureMetricTile` | |
| Modal / Sessions | Secondary linkage count tile detail | `secondarySessionCount` | Derived from session list | **Aggregate (requires full session array)** | `FeatureMetricTile` | |
| Modal / Sessions | Observed workload tokens tile | `sum(resolveTokenMetrics(session).workloadTokens)` | `FeatureSessionLink.observedTokens`, `.modelIOTokens`, `.cacheInputTokens`, etc. | **Aggregate (requires full session array)** | `FeatureMetricTile` | Calls `resolveTokenMetrics` + `sessionHasLinkedSubthreads` for every session |
| Modal / Sessions | Primary root count detail | `linkedSessions.filter(isPrimarySession).length` | Local state | **Aggregate (requires full session array)** | `FeatureMetricTile` | |
| Modal / Sessions | Session card — sessionId, title, status | `session.sessionId`, `.title`, `.status` | `FeatureSessionLink.*` | Exact | `SessionCard` | |
| Modal / Sessions | Session card — model info (raw, displayName, provider, family, version) | `session.model*`, `session.modelsUsed[]` | `FeatureSessionLink.model*`, `.modelsUsed[]` | Exact | `SessionCard` | |
| Modal / Sessions | Session card — startedAt, endedAt, updatedAt | `session.startedAt`, `.endedAt`, `.updatedAt` | `FeatureSessionLink.*` | Exact | `SessionCard` | |
| Modal / Sessions | Session card — workload tokens | `resolveTokenMetrics(session).workloadTokens` | `FeatureSessionLink.*Tokens` | Derived | `SessionCard` headerRight | |
| Modal / Sessions | Session card — display cost | `resolveDisplayCost(session)` | `FeatureSessionLink.displayCostUsd`, `.reportedCostUsd`, `.recalculatedCostUsd`, `.totalCost` | Derived | `SessionCard` headerRight | |
| Modal / Sessions | Session card — duration | `session.durationSeconds / 60` | `FeatureSessionLink.durationSeconds` | Derived | `SessionCard` headerRight | |
| Modal / Sessions | Session card — primary commit hash | `session.gitCommitHash || session.gitCommitHashes?.[0] || session.commitHashes?.[0]` | `FeatureSessionLink.gitCommitHash`, `.gitCommitHashes`, `.commitHashes` | Derived | `SessionCard` | |
| Modal / Sessions | Session card — link confidence % | `session.confidence * 100` | `FeatureSessionLink.confidence` | Exact | `SessionCard` infoBadges | |
| Modal / Sessions | Session card — context utilization % | `session.contextUtilizationPct` | `FeatureSessionLink.contextUtilizationPct` | Exact | `SessionCard` infoBadges | |
| Modal / Sessions | Session card — link role (Primary/Related) | `isPrimarySession(session)` | `FeatureSessionLink.isPrimaryLink`, `.confidence >= 0.9` | Derived | `SessionCard` | |
| Modal / Sessions | Session card — thread label (Sub-thread/Main Thread) | `isSubthreadSession(session)` | `FeatureSessionLink.isSubthread`, `.parentSessionId`, `.sessionType` | Derived | `SessionCard` | |
| Modal / Sessions | Session card — workflow type | `session.workflowType` | `FeatureSessionLink.workflowType` | Exact | `SessionCard` | |
| Modal / Sessions | Session card — cache share % | `resolveTokenMetrics(session).cacheShare` | `FeatureSessionLink.cacheInputTokens`, `.observedTokens` | Derived | `SessionCard` | |
| Modal / Sessions | Session card — link signals | `session.linkStrategy`, `session.reasons[]` | `FeatureSessionLink.linkStrategy`, `.reasons[]` | Exact | `SessionCardDetailSection` | |
| Modal / Sessions | Session card — commands | `session.commands[]` | `FeatureSessionLink.commands[]` | Exact | `SessionCardDetailSection` | |
| Modal / Sessions | Session card — tool summary | `session.toolSummary[]` | `FeatureSessionLink.toolSummary[]` | Exact | `SessionCardDetailSection` | |
| Modal / Sessions | Session card — agent badges | `session.agentsUsed[]` | `FeatureSessionLink.agentsUsed[]` | Exact | `SessionCard` | |
| Modal / Sessions | Session card — skill badges | `session.skillsUsed[]` | `FeatureSessionLink.skillsUsed[]` | Exact | `SessionCard` | |
| Modal / Sessions | Session card — linked tasks (phase, taskId, title, status) | `phases.flatMap(p => p.tasks.filter(t => t.sessionId === session.sessionId))` | `Feature.phases[].tasks[]` cross-referenced with session | **Aggregate (requires full session array cross-referenced with full phase tasks)** | `renderSessionCard` | |
| Modal / Sessions | Core session groups (plan/execution/other) | `getCoreSessionGroupId(session)` | `FeatureSessionLink.workflowType`, `.sessionType`, `.commands[]`, `.title` | Derived | Session group rendering | Requires iterating full session array |
| Modal / Sessions | Secondary linkages count | `secondarySessionCount` | Derived | **Aggregate (requires full session array)** | `FeatureModalSection` | |

### History / Git History Tab

| Surface | UI Label / Purpose | Source field (current) | Source path (type/interface) | Exact vs Derived vs Aggregate | Owning component | Notes |
|---|---|---|---|---|---|---|
| Modal / History | Linked commits count | `gitHistoryData.commits.length` | Aggregated from `FeatureSessionLink.sessionMetadata.commitCorrelations[]` + `FeatureSessionLink.gitCommitHash*` | **Aggregate (requires full session array)** | `ProjectBoardFeatureModal` | |
| Modal / History | Linked PRs count | `gitHistoryData.pullRequests.length` | Aggregated from `FeatureSessionLink.pullRequests[]`, `session.sessionMetadata.prLinks[]` | **Aggregate (requires full session array)** | `ProjectBoardFeatureModal` | |
| Modal / History | Linked branches count | `gitHistoryData.branches.length` | Aggregated from `FeatureSessionLink.gitBranch` | **Aggregate (requires full session array)** | `ProjectBoardFeatureModal` | |
| Modal / History | Per-commit: hash, sessionIds, branches, phases, taskIds, filePaths, PRs | `gitHistoryData.commits[]` → `GitCommitAggregate` | Aggregated from `commitCorrelations[]` across all sessions | **Aggregate (requires full session array)** | `ProjectBoardFeatureModal` | Full cross-session aggregation |
| Modal / History | Per-commit: tokenInput, tokenOutput, fileCount, additions, deletions, costUsd, eventCount, toolCallCount, commandCount, artifactCount | same | same | **Aggregate (requires full session array)** | `ProjectBoardFeatureModal` | |
| Modal / History | History events timeline (feature events + doc timeline events + session start/end) | `featureHistoryEvents[]` | `Feature.timeline[]`, `Feature.linkedDocs[].timeline[]`, `FeatureSessionLink.startedAt/endedAt` | **Aggregate (requires full session array)** | `ProjectBoardFeatureModal` | Session events require full session list |

### Test Status Tab

| Surface | UI Label / Purpose | Source field (current) | Source path (type/interface) | Exact vs Derived vs Aggregate | Owning component | Notes |
|---|---|---|---|---|---|---|
| Modal / Test Status | Test health data | `featureTestHealth` | `FeatureTestHealth` from `getFeatureHealth(projectId, {featureId})` | Exact | `FeatureModalTestStatus` | Separate API call, not from feature or session endpoints |

---

## 3. PlanningHomePage (`components/Planning/PlanningHomePage.tsx`)

The planning home page renders from `ProjectPlanningSummary` (the lightweight summary query) plus a `FeatureSummaryItem[]` list. It does not directly call the feature or linked-sessions endpoints. The full `Feature` object is only needed when the user opens the embedded `ProjectBoardFeatureModal`.

| Surface | UI Label / Purpose | Source field (current) | Source path (type/interface) | Exact vs Derived vs Aggregate | Owning component | Notes |
|---|---|---|---|---|---|---|
| Planning Home | Project name | `summary.projectName` | `ProjectPlanningSummary.projectName` | Exact | `HeroHeader` | |
| Planning Home | Total feature count | `summary.totalFeatureCount` | `ProjectPlanningSummary.totalFeatureCount` | Exact | `HeroHeader` / panels | |
| Planning Home | Active feature count | `summary.activeFeatureCount` | `ProjectPlanningSummary.activeFeatureCount` | Exact | `HeroHeader` | |
| Planning Home | Stale feature count | `summary.staleFeatureCount` | `ProjectPlanningSummary.staleFeatureCount` | Exact | Panels | |
| Planning Home | Blocked feature count | `summary.blockedFeatureCount` | `ProjectPlanningSummary.blockedFeatureCount` | Exact | Panels | |
| Planning Home | Mismatch count | `summary.mismatchCount` | `ProjectPlanningSummary.mismatchCount` | Exact | Panels | |
| Planning Home | Reversal count | `summary.reversalCount` | `ProjectPlanningSummary.reversalCount` | Exact | Panels | |
| Planning Home | Node counts by type (context, tracker, progress, prd, etc.) | `summary.nodeCountsByType.*` | `ProjectPlanningSummary.nodeCountsByType` → `PlanningNodeCountsByType` | Exact | `HeroHeader` / `deriveCorpusStats` | |
| Planning Home | Ctx/phase ratio (derived heuristic) | `ctxCount / phaseCount` | Computed from `nodeCountsByType.context`, `nodeCountsByType.progress` | Derived | `deriveCorpusStats` | Marked TODO to replace with `ctxPerPhase` from backend |
| Planning Home | Tokens-saved heuristic % | Math computation | Derived from `ctxCount / phaseCount` | Derived | `deriveCorpusStats` | Placeholder heuristic |
| Planning Home | Spark history data (12-point curve) | Synthesized | Derived from `summary.totalFeatureCount`, `summary.activeFeatureCount` | Derived | `AnimatedSpark` | Placeholder; real backend history not yet wired |
| Planning Home | Status counts (shaping/planned/active/blocked/review/completed/deferred/staleOrMismatched) | `summary.statusCounts` | `ProjectPlanningSummary.statusCounts` → `PlanningStatusCounts` | Exact | Panels | Optional field, must have FE fallback |
| Planning Home | Backend ctx/phase (ratio, contextCount, phaseCount) | `summary.ctxPerPhase` | `ProjectPlanningSummary.ctxPerPhase` → `PlanningCtxPerPhase` | Exact | Panels | Optional; `source` field governs display |
| Planning Home | Token telemetry (totalTokens, byModelFamily) | `summary.tokenTelemetry` | `ProjectPlanningSummary.tokenTelemetry` → `PlanningTokenTelemetry` | Exact | Panels | Optional |
| Planning Home | Feature row — featureName, featureId | `item.featureName`, `item.featureId` | `FeatureSummaryItem.featureName`, `.featureId` | Exact | `PlanningFeatureRow` | |
| Planning Home | Feature row — rawStatus, effectiveStatus, isMismatch, mismatchState | `item.rawStatus`, `.effectiveStatus`, `.isMismatch`, `.mismatchState` | `FeatureSummaryItem.*` | Exact | `PlanningFeatureRow` | |
| Planning Home | Feature row — phaseCount | `item.phaseCount` | `FeatureSummaryItem.phaseCount` | Exact | `PlanningFeatureRow` | |
| Planning Home | Feature row — hasBlockedPhases, blockedPhaseCount | `item.hasBlockedPhases`, `item.blockedPhaseCount` | `FeatureSummaryItem.hasBlockedPhases`, `.blockedPhaseCount` | Exact | `PlanningFeatureRow` | |
| Planning Home | Signal/bucket filter | `featureMatchesBucket(item, bucket)`, `featureMatchesSignal(item, signal)` | `FeatureSummaryItem.*` | Derived | `PlanningHomePage` | |

---

## 4. FeatureExecutionWorkbench (`components/FeatureExecutionWorkbench.tsx`)

Loads `FeatureExecutionContext` via `getFeatureExecutionContext(featureId)` which bundles `Feature`, `LinkedDocument[]`, `FeatureExecutionSessionLink[]`, and `FeatureExecutionAnalyticsSummary` in a single call. Sessions are the full list for the feature.

| Surface | UI Label / Purpose | Source field (current) | Source path (type/interface) | Exact vs Derived vs Aggregate | Owning component | Notes |
|---|---|---|---|---|---|---|
| Workbench | Session count tile | `context.analytics.sessionCount` | `FeatureExecutionAnalyticsSummary.sessionCount` | Exact | Workbench overview | Pre-aggregated in backend |
| Workbench | Primary session count detail | `context.analytics.primarySessionCount` | `FeatureExecutionAnalyticsSummary.primarySessionCount` | Exact | Workbench overview | Pre-aggregated |
| Workbench | Execution workload tokens | `executionWorkload.workloadTokens` | Derived from `context.sessions[]` via `resolveTokenMetrics` | **Aggregate (requires full session array)** | Workbench overview | Sums `workloadTokens` across all linked sessions |
| Workbench | Total session cost | `context.analytics.totalSessionCost` | `FeatureExecutionAnalyticsSummary.totalSessionCost` | Exact | Workbench overview | Pre-aggregated |
| Workbench | Artifact event count | `context.analytics.artifactEventCount` | `FeatureExecutionAnalyticsSummary.artifactEventCount` | Exact | Workbench overview | Pre-aggregated |
| Workbench | Command event count | `context.analytics.commandEventCount` | `FeatureExecutionAnalyticsSummary.commandEventCount` | Exact | Workbench overview | Pre-aggregated |
| Workbench | Last event at | `context.analytics.lastEventAt` | `FeatureExecutionAnalyticsSummary.lastEventAt` | Exact | Workbench overview | |
| Workbench | Model count | `context.analytics.modelCount` | `FeatureExecutionAnalyticsSummary.modelCount` | Exact | Workbench overview | |
| Workbench | Feature metadata (name, status, priority, riskLevel, complexity, executionReadiness, tags, family, etc.) | `context.feature.*` | `Feature.*` | Exact | Workbench overview | |
| Workbench | Phase list, task list (same fields as modal phases tab) | `context.feature.phases[]` | `Feature.phases[]`, `FeaturePhase.*`, `ProjectTask.*` | Exact | Workbench phases section | |
| Workbench | Session cards (sessionId, model, cost, tokens, duration, commit, confidence, workflow, agentsUsed, skillsUsed, commands) | `context.sessions[]` | `FeatureExecutionSessionLink.*` | Exact + Derived | Workbench sessions section | Full session array from context endpoint |
| Workbench | Per-session workload tokens in cards | `resolveTokenMetrics(session, {hasLinkedSubthreads: …}).workloadTokens` | `FeatureExecutionSessionLink.*Tokens` | **Aggregate (requires full session array for subthread check)** | Workbench sessions | |
| Workbench | Linked documents | `context.documents[]` | `FeatureExecutionContext.documents[]` → `LinkedDocument` | Exact | Workbench docs section | |
| Workbench | Execution recommendation (command, confidence, explanation, evidence) | `context.recommendations.*` | `FeatureExecutionContext.recommendations` → `ExecutionRecommendation` | Exact | Workbench recommendations | |
| Workbench | Execution gate state, reason, isReady | `context.executionGate.*` | `FeatureExecutionContext.executionGate` → `ExecutionGateState` | Exact | Workbench gate section | |
| Workbench | Family summary and position | `context.familySummary.*`, `context.familyPosition.*` | `FeatureExecutionContext.familySummary`, `.familyPosition` | Exact | Workbench family section | |
| Workbench | Recommended stack (workflow, components, scores) | `context.recommendedStack.*` | `FeatureExecutionContext.recommendedStack` → `RecommendedStack` | Exact | Workbench stack section | |
| Workbench | Execution warnings | `context.warnings[]` | `FeatureExecutionContext.warnings[]` | Exact | Workbench warning section | |

---

## 5. SessionInspector — Features Tab (`components/SessionInspector.tsx`)

The features tab renders `SessionFeatureLink[]` (lightweight, from the session's own link metadata), and lazily fetches `GET /api/features/{id}/linked-sessions` only when the user expands "Related Main-Thread Sessions" for a specific feature link.

| Surface | UI Label / Purpose | Source field (current) | Source path (type/interface) | Exact vs Derived vs Aggregate | Owning component | Notes |
|---|---|---|---|---|---|---|
| SessionInspector / Features | Feature name + ID | `feature.featureName`, `feature.featureId` | `SessionFeatureLink.featureName`, `.featureId` | Exact | `SessionFeaturesView` | |
| SessionInspector / Features | Link confidence % | `feature.confidence * 100` | `SessionFeatureLink.confidence` | Exact | `SessionFeaturesView` | |
| SessionInspector / Features | Primary/Related link badge | `feature.isPrimaryLink` | `SessionFeatureLink.isPrimaryLink` | Exact | `SessionFeaturesView` | |
| SessionInspector / Features | Feature status | `feature.featureStatus` | `SessionFeatureLink.featureStatus` | Exact | `SessionFeaturesView` | |
| SessionInspector / Features | Feature category | `feature.featureCategory` | `SessionFeatureLink.featureCategory` | Exact | `SessionFeaturesView` | |
| SessionInspector / Features | Link strategy | `feature.linkStrategy` | `SessionFeatureLink.linkStrategy` | Exact | `SessionFeaturesView` | |
| SessionInspector / Features | Link reasons | `feature.reasons[]` | `SessionFeatureLink.reasons[]` | Exact | `SessionFeaturesView` | |
| SessionInspector / Features | Feature progress bar (completed/total) | `feature.completedTasks / feature.totalTasks` | `SessionFeatureLink.completedTasks`, `.totalTasks` | Exact | `SessionFeaturesView` | |
| SessionInspector / Features | Related main-thread sessions list (lazy loaded on expand) | Fetched from `/api/features/{id}/linked-sessions` | `FeatureExecutionSessionLink.*` | **Aggregate (requires full session array, lazy)** | `SessionFeaturesView` | Only fires on user expand; shows sessionId, title, startedAt, cost, workflowType |
| SessionInspector / Features | Task hierarchy (phase + tasks matched to session tool artifacts) | `taskHierarchy[]` | `Feature.phases[].tasks[]` (from `linkedFeatureDetailsById`) cross-referenced with `taskArtifacts[]` | **Aggregate (requires full feature detail with phase tasks)** | `SessionFeaturesView` | Loaded lazily via feature detail fetch |
| SessionInspector / Features | Primary feature link panel (in transcript header) | `primaryFeatureLink.featureId/Name`, `.confidence`, `.linkStrategy` | `SessionFeatureLink.*` passed as prop | Exact | `SessionTranscriptPanel` | |

---

## 6. Cross-Cutting: Metrics That Currently Require Full Session Log Arrays

The following metrics are computed today by loading the full `/api/features/{id}/linked-sessions` response (an unbounded array of `FeatureSessionLink` objects) in the frontend and then iterating every element. Each one is a blocking hotspot or a lazy hotspot.

| Surface | Field | Why It Is Expensive Today |
|---|---|---|
| Board card / List card (FeatureSessionIndicator) | `total`, `mainThreads`, `subThreads`, `unresolvedSubThreads` | `buildFeatureSessionSummary` iterates every session; fires per-card on board load |
| Board card / List card (FeatureSessionIndicator) | `workloadTokens` (observed workload) | `resolveTokenMetrics(session, {hasLinkedSubthreads: sessionHasLinkedSubthreads(session.sessionId, sessions)})` runs per-session and requires the full array to check for linked subthreads |
| Board card / List card (FeatureSessionIndicator) | `modelIOTokens`, `cacheInputTokens`, cache% | Same per-session `resolveTokenMetrics` pass; requires full array |
| Board card / List card (FeatureSessionIndicator) | `byType[]` (session type breakdown) | Requires iterating all sessions to bucket by workflow/sessionType label |
| Modal / Sessions tab | Total, sub-thread, primary, secondary counts | `linkedSessions.length`, `linkedSessions.filter(isSubthreadSession)`, `primarySessionRoots` etc. all iterate full array loaded on modal mount |
| Modal / Sessions tab | Observed workload tokens tile | `linkedSessions.reduce(sum + resolveTokenMetrics(...))` — iterates full array with subthread awareness |
| Modal / Sessions tab | Primary session count detail | `countThreadNodes(primarySessionRoots)` — requires building the full session forest |
| Modal / Sessions tab | Session type grouping (plan/execution/other) | `getCoreSessionGroupId` runs classification heuristics per session over entire array |
| Modal / Sessions tab | Session card — linked tasks annotation | `phases.flatMap(p => p.tasks.filter(t => t.sessionId === session.sessionId))` — cross-join of full session list with full phase task list |
| Modal / Phases tab | Phase-linked session IDs | `phaseSessionLinks` map built by iterating all linked sessions and their `relatedPhases[]` |
| Modal / Phases tab | Task-linked session IDs | `taskSessionLinksByTaskId` map built from full session list's `relatedTasks[]` |
| Modal / Phases tab | Phase-linked commit hashes | `phaseCommitLinks` built by accumulating `commitCorrelations[]` across all sessions |
| Modal / Phases tab | Task-linked commit hashes | `taskCommitLinksByTaskId` built from commit correlation data across all sessions |
| Modal / History tab | Linked commits count, PR count, branch count | `gitHistoryData` built by iterating all sessions' `commitCorrelations[]`, `pullRequests[]`, `gitBranch` |
| Modal / History tab | Per-commit aggregates (tokenInput/Output, fileCount, additions, deletions, costUsd, event/tool/command/artifact counts) | Accumulated across all sessions' `sessionMetadata.commitCorrelations[]` |
| Modal / History tab | Session start/end events in history timeline | `featureHistoryEvents` iterates `linkedSessions[]` for every session's `startedAt` and `endedAt` |
| Workbench | Execution workload tokens | `context.sessions.reduce(sum + resolveTokenMetrics(...))` requires full session array with subthread check |
| Workbench | Per-session workload tokens in session cards | `resolveTokenMetrics(session, {hasLinkedSubthreads: sessionHasLinkedSubthreads(session.sessionId, context.sessions)})` — O(n) subthread check per session card |
| SessionInspector / Features | Related main-thread sessions (lazy) | Fires `GET /api/features/{id}/linked-sessions` on expand, filters non-subthread sessions client-side |

Total flagged metrics requiring full session arrays: **18 distinct metric groups** (all bullet rows above).

---

## 4. Open Questions / Gaps

1. **Filter completeness**: All active filters (status, category, date ranges, text search, sort) are applied entirely in-memory on the frontend after loading the full feature list. The board currently has no server-side filtering or pagination. Phase 1 must decide which filters become query parameters and which remain client-side for the initial window.

2. **`unresolvedSubThreads` signal**: This metric is computed by checking whether a subthread's `parentSessionId` / `rootSessionId` appears in the same session set. It is only meaningful when the full session array is present. The rollup DTO must decide whether to carry this field or drop it.

3. **`byType[]` breakdown on card indicator**: Five buckets (by workflow label) are shown in the card hover tooltip. The rollup DTO must either pre-aggregate these buckets server-side or drop this granularity from card rendering.

4. **`sessionHasLinkedSubthreads` O(n) cross-check**: Called once per session during token metric resolution. When the full session array is present it is O(n²) overall. The rollup endpoint must either encode a `hasLinkedSubthreads` flag per session or provide a pre-computed per-feature subthread map.

5. **`FeatureExecutionWorkbench` duplicate vs `ProjectBoardFeatureModal`**: The workbench uses `FeatureExecutionContext` (backend-assembled DTO with pre-computed analytics) while the modal rolls up its own analytics from the full session array. They render overlapping but not identical fields. Phase 2 must decide whether to unify these on a single rollup endpoint.

6. **LinkedDocument fields on cards**: Both card variants load `feature.linkedDocs[]` in their Feature object (which comes from the main feature list endpoint, not a separate call). If `linkedDocs` is stripped from the list DTO for performance, `LinkedDocsSummaryBadge` on cards will break. This must be an explicit decision in Phase 2.

7. **`getFeatureCoverageSummary` on cards**: Requires `Feature.documentCoverage.present[]` and `.missing[]` arrays. These must remain in the list DTO or be replaced by a scalar coverage score.

8. **History tab session-start/end events**: The feature timeline events section mixes `Feature.timeline[]`, `LinkedDocument.timeline[]`, and session start/end events derived from the full session list. The last group cannot be produced cheaply without either a pre-computed event list endpoint or carrying session boundary timestamps in a lightweight rollup.

9. **Test status tab**: Uses a completely independent API call (`getFeatureHealth`) and does not depend on the linked-sessions endpoint. No changes required for this tab in the redesign.

10. **`FeatureTokenRollup` in planning graph**: `ProjectPlanningGraph.featureTokenRollups` is already a server-side rollup. It should be reviewed as a potential basis for card-level token metrics to avoid duplicating aggregation logic.
