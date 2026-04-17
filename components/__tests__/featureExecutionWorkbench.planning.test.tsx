/**
 * PCP-401: Planning context integration in FeatureExecutionWorkbench.
 *
 * Strategy: the workbench has deep react-router, live-connection, and async
 * loading dependencies that make full DOM rendering fragile. Per the task spec,
 * we test:
 *   (a) the exported `computeActivePhase` helper (now in lib/planningHelpers)
 *       directly — no React rendering needed.
 *   (b) The Planning Control Plane primitives (EffectiveStatusChips,
 *       MismatchBadge, BatchReadinessPill, LineageRow) rendered with
 *       synthesized FeaturePlanningContext fixtures to assert the section would
 *       produce the correct markup.
 *
 * This avoids pulling in the full workbench component tree (which has
 * transitive imports that break without a bundler alias pass).
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { computeActivePhase } from '../../lib/planningHelpers';
import type { PhaseContextItem, PlanningPhaseBatch, FeaturePlanningContext } from '../../types';
import {
  BatchReadinessPill,
  EffectiveStatusChips,
  MismatchBadge,
  LineageRow,
} from '@/components/shared/PlanningMetadata';

// ── Fixtures ──────────────────────────────────────────────────────────────────

const makePhase = (overrides: Partial<PhaseContextItem>): PhaseContextItem => ({
  phaseId: 'phase-1',
  phaseToken: 'PHASE-1',
  phaseTitle: 'Implementation',
  rawStatus: 'in-progress',
  effectiveStatus: 'in_progress',
  isMismatch: false,
  mismatchState: 'aligned',
  planningStatus: {},
  batches: [],
  blockedBatchIds: [],
  totalTasks: 5,
  completedTasks: 2,
  deferredTasks: 0,
  ...overrides,
});

const makeReadyBatch = (overrides: Partial<PlanningPhaseBatch> = {}): PlanningPhaseBatch => ({
  featureSlug: 'feat-1',
  phase: 'PHASE-1',
  batchId: 'batch-001',
  taskIds: ['TASK-1.1', 'TASK-1.2'],
  assignedAgents: ['agent-alpha'],
  fileScopeHints: ['src/feature/index.ts'],
  readinessState: 'ready',
  readiness: {
    state: 'ready',
    reason: 'All dependencies resolved',
    blockingNodeIds: [],
    blockingTaskIds: [],
    evidence: [],
    isReady: true,
  },
  ...overrides,
});

const makePlanningContext = (
  overrides: Partial<FeaturePlanningContext> = {},
): FeaturePlanningContext => ({
  status: 'ok',
  dataFreshness: '2026-04-17T00:00:00Z',
  generatedAt: '2026-04-17T00:00:00Z',
  sourceRefs: [],
  featureId: 'feat-1',
  featureName: 'Auth Revamp',
  rawStatus: 'in-progress',
  effectiveStatus: 'in_progress',
  mismatchState: 'mismatched',
  planningStatus: {
    rawStatus: 'in-progress',
    effectiveStatus: 'in_progress',
    provenance: { source: 'derived', reason: 'Phase evidence', evidence: [] },
    mismatchState: {
      state: 'mismatched',
      reason: 'Progress doc says done but tracker is in-progress',
      isMismatch: true,
      evidence: [
        { id: 'ev-1', label: 'progress.md:done', detail: '', sourceType: 'doc', sourceId: 'doc-1', sourcePath: 'progress.md' },
      ],
    },
  },
  graph: {
    nodes: [
      {
        id: 'node-1',
        type: 'implementation_plan',
        path: 'docs/plans/impl.md',
        title: 'Auth Implementation Plan',
        featureSlug: 'feat-1',
        rawStatus: 'in-progress',
        effectiveStatus: 'in_progress',
        mismatchState: { state: 'aligned', reason: '', isMismatch: false, evidence: [] },
        updatedAt: '2026-04-15T10:00:00Z',
      },
    ],
    edges: [],
    phaseBatches: [],
  },
  phases: [
    makePhase({
      effectiveStatus: 'in_progress',
      batches: [makeReadyBatch()],
    }),
  ],
  blockedBatchIds: [],
  linkedArtifactRefs: [],
  ...overrides,
});

// ── Tests: computeActivePhase ────────────────────────────────────────────────

describe('computeActivePhase', () => {
  it('returns null when phases array is empty', () => {
    expect(computeActivePhase([])).toBeNull();
  });

  it('picks the first in_progress phase', () => {
    const phases = [
      makePhase({ phaseId: 'p1', effectiveStatus: 'done' }),
      makePhase({ phaseId: 'p2', effectiveStatus: 'in_progress', phaseTitle: 'Phase 2' }),
      makePhase({ phaseId: 'p3', effectiveStatus: 'todo' }),
    ];
    expect(computeActivePhase(phases)?.phaseId).toBe('p2');
  });

  it('picks the first "active" phase when none are in_progress', () => {
    const phases = [
      makePhase({ phaseId: 'p1', effectiveStatus: 'done' }),
      makePhase({ phaseId: 'p2', effectiveStatus: 'active' }),
    ];
    expect(computeActivePhase(phases)?.phaseId).toBe('p2');
  });

  it('falls back to first non-completed phase when no in_progress/active', () => {
    const phases = [
      makePhase({ phaseId: 'p1', effectiveStatus: 'done' }),
      makePhase({ phaseId: 'p2', effectiveStatus: 'deferred' }),
      makePhase({ phaseId: 'p3', effectiveStatus: 'todo' }),
    ];
    expect(computeActivePhase(phases)?.phaseId).toBe('p3');
  });

  it('falls back to phases[0] when all phases are completed', () => {
    const phases = [
      makePhase({ phaseId: 'p1', effectiveStatus: 'done' }),
      makePhase({ phaseId: 'p2', effectiveStatus: 'deferred' }),
    ];
    expect(computeActivePhase(phases)?.phaseId).toBe('p1');
  });

  it('treats in_progress (underscore) as active', () => {
    const phases = [
      makePhase({ phaseId: 'p1', effectiveStatus: 'done' }),
      makePhase({ phaseId: 'p2', effectiveStatus: 'in_progress' }),
    ];
    expect(computeActivePhase(phases)?.phaseId).toBe('p2');
  });
});

// ── Tests: Planning Control Plane primitives with synthesized data ────────────

describe('Planning Control Plane section rendering (primitive-level)', () => {
  const ctx = makePlanningContext();
  const activePhase = ctx.phases[0];
  const actionableBatch = activePhase.batches[0];

  it('renders the feature name and id', () => {
    const html = renderToStaticMarkup(
      <div>
        <span>{ctx.featureName}</span>
        <span>{ctx.featureId}</span>
      </div>,
    );
    expect(html).toContain('Auth Revamp');
    expect(html).toContain('feat-1');
  });

  it('renders EffectiveStatusChips with raw and effective status', () => {
    const html = renderToStaticMarkup(
      <EffectiveStatusChips
        rawStatus={ctx.rawStatus}
        effectiveStatus={ctx.effectiveStatus}
        isMismatch={ctx.mismatchState !== 'aligned' && ctx.mismatchState !== 'unknown'}
      />,
    );
    expect(html).toContain('raw: in-progress');
    expect(html).toContain('eff: in_progress');
  });

  it('renders the MismatchBadge when isMismatch is true', () => {
    const html = renderToStaticMarkup(
      <MismatchBadge
        state={ctx.mismatchState}
        reason="Progress doc says done but tracker is in-progress"
        evidenceLabels={['progress.md:done']}
        compact={false}
      />,
    );
    expect(html).toContain('Status mismatch detected');
    expect(html).toContain('Progress doc says done but tracker is in-progress');
    expect(html).toContain('progress.md:done');
  });

  it('renders the active phase title', () => {
    const html = renderToStaticMarkup(
      <div>
        <span>{activePhase.phaseTitle}</span>
        <EffectiveStatusChips
          rawStatus={activePhase.rawStatus}
          effectiveStatus={activePhase.effectiveStatus}
          isMismatch={activePhase.isMismatch}
        />
        <span>{activePhase.completedTasks}/{activePhase.totalTasks} tasks</span>
      </div>,
    );
    expect(html).toContain('Implementation');
    expect(html).toContain('raw: in-progress');
    expect(html).toContain('2/5 tasks');
  });

  it('renders the actionable batch id with readiness pill', () => {
    const html = renderToStaticMarkup(
      <div>
        <span>{actionableBatch.batchId}</span>
        <BatchReadinessPill
          readinessState={actionableBatch.readinessState}
          blockingNodeIds={actionableBatch.readiness?.blockingNodeIds}
          blockingTaskIds={actionableBatch.readiness?.blockingTaskIds}
        />
      </div>,
    );
    expect(html).toContain('batch-001');
    expect(html).toContain('ready');
    expect(html).not.toContain('Blocking nodes');
  });

  it('renders the lineage node via LineageRow', () => {
    const node = ctx.graph.nodes[0];
    const html = renderToStaticMarkup(<LineageRow node={node} />);
    expect(html).toContain('Auth Implementation Plan');
    expect(html).toContain('docs/plans/impl.md');
  });
});
