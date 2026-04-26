/**
 * featureCardAdapters.ts — P3-005: Card Metric Mapping
 *
 * Adapts FeatureCardDTO + FeatureRollupDTO from the feature-surface v1 endpoints
 * to the shapes consumed by FeatureCard, FeatureListCard, and FeatureSessionIndicator.
 *
 * Design goals:
 * - Zero per-feature fetches — all data comes from the batch list + rollup endpoints.
 * - Card components continue to accept the existing Feature shape; the adapter
 *   synthesises a minimal Feature from FeatureCardDTO so the component tree does
 *   not need to change.
 * - Session indicator data is projected from FeatureRollupDTO; numeric fields are
 *   null-safe (DTO fields are all `| null` by spec).
 * - When rollup is not yet available (pending), session indicator receives
 *   `undefined` so the component renders its loading/neutral state.
 */

import type { FeatureCardDTO, FeatureRollupDTO, FeatureRollupBucketDTO } from '../services/featureSurface';
import type { Feature, LinkedDocument, PlanningEffectiveStatus } from '../types';

// ── FeatureSessionSummary projection ─────────────────────────────────────────
//
// This is the shape consumed by FeatureSessionIndicator (defined inline in
// ProjectBoard.tsx).  We project it from FeatureRollupDTO without importing
// the private interface — the fields must match exactly.

export interface RollupSessionSummary {
  total: number;
  mainThreads: number;
  subThreads: number;
  unresolvedSubThreads: number;
  workloadTokens: number;
  modelIOTokens: number;
  cacheInputTokens: number;
  byType: Array<{ type: string; count: number }>;
}

/**
 * Projects a FeatureRollupDTO into the RollupSessionSummary shape used by
 * FeatureSessionIndicator.  Returns `undefined` when rollup is absent (pending),
 * so the indicator renders in its neutral/loading state.
 */
export function rollupToSessionSummary(rollup: FeatureRollupDTO | undefined): RollupSessionSummary | undefined {
  if (!rollup) return undefined;

  const sessionCount = rollup.sessionCount ?? 0;
  const primarySessionCount = rollup.primarySessionCount ?? 0;
  const subthreadCount = rollup.subthreadCount ?? 0;
  const unresolvedSubthreadCount = rollup.unresolvedSubthreadCount ?? 0;
  const observedTokens = rollup.observedTokens ?? 0;
  const modelIoTokens = rollup.modelIoTokens ?? 0;
  const cacheInputTokens = rollup.cacheInputTokens ?? 0;

  // byType is derived from workflowTypes buckets when present.
  const byType: Array<{ type: string; count: number }> = (rollup.workflowTypes ?? [])
    .filter((b: FeatureRollupBucketDTO) => b.count != null && b.count > 0)
    .map((b: FeatureRollupBucketDTO) => ({ type: b.label || b.key || 'unknown', count: b.count ?? 0 }))
    .sort((a: { count: number }, b: { count: number }) => b.count - a.count)
    .slice(0, 5);

  return {
    total: sessionCount,
    mainThreads: primarySessionCount,
    subThreads: subthreadCount,
    unresolvedSubThreads: unresolvedSubthreadCount,
    workloadTokens: observedTokens,
    modelIOTokens: modelIoTokens,
    cacheInputTokens,
    byType,
  };
}

// ── FeatureCardDTO → Feature adapter ─────────────────────────────────────────
//
// Synthesises a minimal Feature from FeatureCardDTO so that FeatureCard and
// FeatureListCard — which accept Feature — can be driven from the v1 endpoint
// without breaking existing prop contracts.
//
// Fields not present in FeatureCardDTO are set to safe defaults:
//   - linkedDocs: empty array (card renders no LinkedDocsSummaryBadge)
//   - planningStatus: undefined (EffectiveStatusChips / MismatchBadge hidden)
//   - executionReadiness: undefined (badge shows 'readiness n/a')
//   - phases: empty array populated with a synthetic phase to preserve phaseCount
//   - linkedFeatures / relatedFeatures: derived from relatedFeatureCount

function bucketsToDocCoverage(coverage: FeatureCardDTO['documentCoverage']): Feature['documentCoverage'] {
  if (!coverage) return undefined;
  return {
    present: coverage.present ?? [],
    missing: coverage.missing ?? [],
    countsByType: coverage.countsByType ?? {},
    coverageScore: 0,
  };
}

function adaptPlanningStatus(raw: FeatureCardDTO['planningStatus']): PlanningEffectiveStatus | null {
  if (!raw || typeof raw !== 'object') return null;
  const rawStatus =
    typeof raw.rawStatus === 'string'
      ? raw.rawStatus
      : typeof raw.raw_status === 'string'
        ? raw.raw_status
        : '';
  const effectiveStatus =
    typeof raw.effectiveStatus === 'string'
      ? raw.effectiveStatus
      : typeof raw.effective_status === 'string'
        ? raw.effective_status
        : '';
  if (!rawStatus && !effectiveStatus) return null;

  const provenanceRaw = raw.provenance;
  const provenance = provenanceRaw && typeof provenanceRaw === 'object' && !Array.isArray(provenanceRaw)
    ? provenanceRaw as Record<string, unknown>
    : {};
  const mismatchRaw = raw.mismatchState ?? raw.mismatch_state;
  const mismatch = mismatchRaw && typeof mismatchRaw === 'object' && !Array.isArray(mismatchRaw)
    ? mismatchRaw as Record<string, unknown>
    : {};

  return {
    rawStatus,
    effectiveStatus,
    provenance: {
      source: (typeof provenance.source === 'string' ? provenance.source : 'unknown') as PlanningEffectiveStatus['provenance']['source'],
      reason: typeof provenance.reason === 'string' ? provenance.reason : '',
      evidence: Array.isArray(provenance.evidence) ? provenance.evidence as PlanningEffectiveStatus['provenance']['evidence'] : [],
    },
    mismatchState: {
      state: (typeof mismatch.state === 'string' ? mismatch.state : 'unknown') as PlanningEffectiveStatus['mismatchState']['state'],
      reason: typeof mismatch.reason === 'string' ? mismatch.reason : '',
      isMismatch: mismatch.isMismatch === true || mismatch.is_mismatch === true,
      evidence: Array.isArray(mismatch.evidence) ? mismatch.evidence as PlanningEffectiveStatus['mismatchState']['evidence'] : [],
    },
  };
}

/**
 * Converts a FeatureCardDTO to a minimal Feature suitable for card rendering.
 *
 * The resulting object covers all fields read by FeatureCard / FeatureListCard
 * and their helper functions:
 *   getFeatureDeferredCount, getFeatureCompletedCount, hasDeferredCaveat,
 *   getFeatureCoverageSummary, getFeatureLinkedFeatureCount,
 *   getFeatureDateValue, getFeaturePrimaryDate, getFeatureDateModule.
 *
 * Fields that require the full Feature (planningStatus, executionGate, etc.)
 * are omitted; the card components handle undefined gracefully.
 */
export function cardDTOToFeature(card: FeatureCardDTO): Feature {
  // Synthesise relatedFeatures as an array of the appropriate length so
  // getFeatureLinkedFeatureCount() returns the right number.
  const relatedFeatures: string[] = card.relatedFeatureCount > 0
    ? Array.from({ length: card.relatedFeatureCount }, (_, i) => `__placeholder_${i}`)
    : [];

  // Synthesise a phases array so the card's "N phases" badge is correct.
  // Each entry is a minimal FeaturePhase with only the fields the card reads.
  const phases = card.phaseCount > 0
    ? Array.from({ length: card.phaseCount }, (_, i) => ({
        phase: `phase-${i + 1}`,
        id: `phase-${i + 1}`,
        status: 'unknown',
        totalTasks: 0,
        completedTasks: 0,
        deferredTasks: 0,
        tasks: [],
        progress: 0,
      }))
    : [];

  return {
    id: card.id,
    name: card.name,
    status: card.status,
    totalTasks: card.totalTasks ?? 0,
    completedTasks: card.completedTasks ?? 0,
    deferredTasks: card.deferredTasks ?? 0,
    category: card.category ?? '',
    tags: card.tags ?? [],
    summary: card.summary ?? '',
    description: card.descriptionPreview || card.summary || undefined,
    priority: card.priority || undefined,
    riskLevel: card.riskLevel || undefined,
    complexity: card.complexity || undefined,
    executionReadiness: card.executionReadiness || undefined,
    testImpact: card.testImpact || card.qualitySignals?.testImpact || undefined,
    updatedAt: card.updatedAt ?? '',
    plannedAt: card.plannedAt || undefined,
    startedAt: card.startedAt || undefined,
    completedAt: card.completedAt || undefined,
    documentCoverage: bucketsToDocCoverage(card.documentCoverage),
    linkedDocs: [] as LinkedDocument[],
    relatedFeatures,
    phases: phases as Feature['phases'],
    planningStatus: adaptPlanningStatus(card.planningStatus),
    linkedFeatures: undefined,
    familyPosition: undefined,
    familySummary: undefined,
    executionGate: undefined,
    blockingFeatures: undefined,
    primaryDocuments: undefined,
    qualitySignals: card.qualitySignals
      ? {
          blockerCount: card.qualitySignals.blockerCount ?? 0,
          atRiskTaskCount: card.qualitySignals.atRiskTaskCount ?? 0,
          integritySignalRefs: card.qualitySignals.integritySignalRefs ?? [],
          reportFindingsBySeverity: {},
          testImpact: card.testImpact || card.qualitySignals.testImpact || '',
          hasBlockingSignals: card.qualitySignals.hasBlockingSignals ?? false,
        }
      : undefined,
    dependencyState: card.dependencyState
      ? {
          state: (card.dependencyState.state || 'unblocked') as Feature['dependencyState']['state'],
          dependencyCount: (card.dependencyState.blockedByCount ?? 0) + (card.dependencyState.readyDependencyCount ?? 0),
          resolvedDependencyCount: card.dependencyState.readyDependencyCount ?? 0,
          blockedDependencyCount: card.dependencyState.blockedByCount ?? 0,
          unknownDependencyCount: 0,
          blockingFeatureIds: [],
          blockingDocumentIds: [],
          firstBlockingDependencyId: '',
          blockingReason: card.dependencyState.blockingReason ?? '',
          completionEvidence: [],
          dependencies: [],
        }
      : undefined,
    dates: undefined,
    timeline: undefined,
  };
}

/**
 * Returns the card-stage string used to bucket features into board columns.
 * Mirrors the logic in getFeatureBoardStage (defined locally in ProjectBoard).
 */
export function cardDTOBoardStage(card: FeatureCardDTO): string {
  if (card.status === 'deferred') return 'done';
  return card.status;
}

/**
 * Returns the linked-doc count from rollup if available, falling back to zero.
 * Used for the linked-doc badge count in partial-render (rollup pending) state.
 */
export function rollupLinkedDocCount(rollup: FeatureRollupDTO | undefined): number {
  return rollup?.linkedDocCount ?? 0;
}
