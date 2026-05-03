/**
 * PCP-602: Extended planning service tests.
 *
 * Extends planning.test.ts without duplicating existing cases.
 * Additional coverage:
 *   1. getProjectPlanningSummary — feature_summaries adaptation (isMismatch, hasBlockedPhases).
 *   2. getProjectPlanningGraph — 5xx HTTP error throws PlanningApiError.
 *   3. getProjectPlanningGraph — partial envelope status is preserved.
 *   4. getProjectPlanningGraph — project_id query param is wired.
 *   5. getProjectPlanningGraph — adapts node/edge counts from wire.
 *   6. getFeaturePlanningContext — 5xx HTTP error throws PlanningApiError.
 *   7. getFeaturePlanningContext — phases array is correctly adapted.
 *   8. getPhaseOperations — 5xx HTTP error throws PlanningApiError.
 *   9. getPhaseOperations — empty progress_evidence yields empty array.
 *  10. getPhaseOperations — dependency_resolution passthrough.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  getFeaturePlanningContext,
  getPhaseOperations,
  getProjectPlanningGraph,
  getProjectPlanningSummary,
} from '../planning';

// ── Helpers ───────────────────────────────────────────────────────────────────

function okResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function makeEnvelope(overrides: Partial<{
  status: string;
  data_freshness: string;
  generated_at: string;
  source_refs: string[];
}> = {}) {
  return {
    status: 'ok',
    data_freshness: '2026-04-17T00:00:00Z',
    generated_at: '2026-04-17T00:01:00Z',
    source_refs: ['projects.json'],
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// ── getProjectPlanningSummary (extended) ──────────────────────────────────────

describe('getProjectPlanningSummary (extended)', () => {
  it('adapts feature_summaries isMismatch and hasBlockedPhases fields', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse({
        ...makeEnvelope(),
        project_id: 'proj-x',
        project_name: 'X',
        total_feature_count: 1,
        active_feature_count: 1,
        stale_feature_count: 0,
        blocked_feature_count: 0,
        mismatch_count: 1,
        reversal_count: 0,
        stale_feature_ids: [],
        reversal_feature_ids: [],
        blocked_feature_ids: [],
        node_counts_by_type: {
          prd: 0, design_spec: 0, implementation_plan: 0,
          progress: 0, context: 0, tracker: 0, report: 0,
        },
        feature_summaries: [
          {
            feature_id: 'feat-m',
            feature_name: 'Mismatch Feature',
            raw_status: 'in-progress',
            effective_status: 'done',
            is_mismatch: true,
            mismatch_state: 'mismatched',
            has_blocked_phases: false,
            phase_count: 2,
            blocked_phase_count: 0,
            node_count: 4,
          },
          {
            feature_id: 'feat-b',
            feature_name: 'Blocked Feature',
            raw_status: 'in-progress',
            effective_status: 'blocked',
            is_mismatch: false,
            mismatch_state: 'aligned',
            has_blocked_phases: true,
            phase_count: 3,
            blocked_phase_count: 1,
            node_count: 2,
          },
        ],
      }),
    ));

    const result = await getProjectPlanningSummary('proj-x');

    expect(result.featureSummaries).toHaveLength(2);
    const mismatchFeat = result.featureSummaries[0];
    expect(mismatchFeat.isMismatch).toBe(true);
    expect(mismatchFeat.mismatchState).toBe('mismatched');
    expect(mismatchFeat.rawStatus).toBe('in-progress');
    expect(mismatchFeat.effectiveStatus).toBe('done');
    expect(mismatchFeat.phaseCount).toBe(2);

    const blockedFeat = result.featureSummaries[1];
    expect(blockedFeat.hasBlockedPhases).toBe(true);
    expect(blockedFeat.blockedPhaseCount).toBe(1);
    expect(blockedFeat.isMismatch).toBe(false);
  });

  it('adapts feature_summaries with missing optional fields gracefully', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse({
        ...makeEnvelope(),
        project_id: 'proj-y',
        project_name: '',
        total_feature_count: 1,
        active_feature_count: 0,
        stale_feature_count: 0,
        blocked_feature_count: 0,
        mismatch_count: 0,
        reversal_count: 0,
        stale_feature_ids: [],
        reversal_feature_ids: [],
        blocked_feature_ids: [],
        node_counts_by_type: { prd: 0, design_spec: 0, implementation_plan: 0, progress: 0, context: 0, tracker: 0, report: 0 },
        feature_summaries: [
          {
            // minimal: no is_mismatch, no has_blocked_phases, no mismatch_state
            feature_id: 'feat-min',
            feature_name: 'Minimal',
            raw_status: 'todo',
            effective_status: 'todo',
          },
        ],
      }),
    ));

    const result = await getProjectPlanningSummary();
    const feat = result.featureSummaries[0];
    expect(feat.featureId).toBe('feat-min');
    expect(feat.isMismatch).toBe(false);
    expect(feat.hasBlockedPhases).toBe(false);
    expect(feat.mismatchState).toBe('unknown');
    expect(feat.phaseCount).toBe(0);
    expect(feat.nodeCount).toBe(0);
  });
});

// ── getProjectPlanningGraph (extended) ────────────────────────────────────────

describe('getProjectPlanningGraph (extended)', () => {
  function graphPayload(overrides: Record<string, unknown> = {}) {
    return {
      ...makeEnvelope(),
      project_id: 'proj-1',
      feature_id: null,
      depth: null,
      nodes: [],
      edges: [],
      phase_batches: [],
      node_count: 0,
      edge_count: 0,
      ...overrides,
    };
  }

  it('throws PlanningApiError on 5xx HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('', { status: 503, statusText: 'Service Unavailable' }),
    ));

    await expect(getProjectPlanningGraph()).rejects.toMatchObject({
      name: 'PlanningApiError',
      status: 503,
    });
  });

  it('throws PlanningApiError on 404 HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('', { status: 404, statusText: 'Not Found' }),
    ));

    await expect(getProjectPlanningGraph({ featureId: 'missing' })).rejects.toMatchObject({
      name: 'PlanningApiError',
      status: 404,
    });
  });

  it('preserves partial envelope status in returned object', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(graphPayload({ ...makeEnvelope({ status: 'partial' }) })),
    ));

    const result = await getProjectPlanningGraph();
    expect(result.status).toBe('partial');
  });

  it('wires project_id query param when projectId option is supplied', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse(graphPayload()));
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningGraph({ projectId: 'proj-abc' });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/agent/planning/graph?project_id=proj-abc',
      { credentials: 'same-origin' },
    );
  });

  it('adapts node_count and edge_count from wire shape', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(graphPayload({ node_count: 12, edge_count: 7 })),
    ));

    const result = await getProjectPlanningGraph();
    expect(result.nodeCount).toBe(12);
    expect(result.edgeCount).toBe(7);
  });

  it('returns phaseBatches from phase_batches wire array', async () => {
    const fakeBatch = { batch_id: 'b-1', feature_slug: 'feat-1', readiness_state: 'ready' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(graphPayload({ phase_batches: [fakeBatch], node_count: 1 })),
    ));

    const result = await getProjectPlanningGraph();
    expect(result.phaseBatches).toHaveLength(1);
  });
});

// ── getFeaturePlanningContext (extended) ──────────────────────────────────────

describe('getFeaturePlanningContext (extended)', () => {
  function contextPayload(overrides: Record<string, unknown> = {}) {
    return {
      ...makeEnvelope(),
      feature_id: 'feat-1',
      feature_name: 'My Feature',
      raw_status: 'in_progress',
      effective_status: 'in_progress',
      mismatch_state: 'aligned',
      planning_status: {},
      graph: { nodes: [], edges: [], phase_batches: [] },
      phases: [],
      blocked_batch_ids: [],
      linked_artifact_refs: [],
      ...overrides,
    };
  }

  it('throws PlanningApiError on 5xx HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('', { status: 502, statusText: 'Bad Gateway' }),
    ));

    await expect(getFeaturePlanningContext('feat-1')).rejects.toMatchObject({
      name: 'PlanningApiError',
      status: 502,
    });
  });

  it('adapts phases array with per-phase fields', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(contextPayload({
        phases: [
          {
            phase_id: 'ph-1',
            phase_token: 'PHASE-1',
            phase_title: 'Phase 1: Init',
            raw_status: 'done',
            effective_status: 'done',
            is_mismatch: false,
            mismatch_state: 'aligned',
            planning_status: {},
            batches: [],
            blocked_batch_ids: [],
            total_tasks: 5,
            completed_tasks: 5,
            deferred_tasks: 0,
          },
        ],
      })),
    ));

    const result = await getFeaturePlanningContext('feat-1', { forceRefresh: true });

    expect(result.phases).toHaveLength(1);
    const phase = result.phases[0];
    expect(phase.phaseId).toBe('ph-1');
    expect(phase.phaseToken).toBe('PHASE-1');
    expect(phase.phaseTitle).toBe('Phase 1: Init');
    expect(phase.rawStatus).toBe('done');
    expect(phase.effectiveStatus).toBe('done');
    expect(phase.isMismatch).toBe(false);
    expect(phase.totalTasks).toBe(5);
    expect(phase.completedTasks).toBe(5);
    expect(phase.deferredTasks).toBe(0);
  });

  it('adapts phases with blocked_batch_ids per phase', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(contextPayload({
        phases: [
          {
            phase_id: 'ph-2',
            phase_token: 'PHASE-2',
            phase_title: 'Phase 2: Build',
            raw_status: 'blocked',
            effective_status: 'blocked',
            is_mismatch: false,
            mismatch_state: 'aligned',
            planning_status: {},
            batches: [],
            blocked_batch_ids: ['batch-A', 'batch-B'],
            total_tasks: 8,
            completed_tasks: 2,
            deferred_tasks: 1,
          },
        ],
      })),
    ));

    const result = await getFeaturePlanningContext('feat-1', { forceRefresh: true });
    const phase = result.phases[0];
    expect(phase.blockedBatchIds).toEqual(['batch-A', 'batch-B']);
    expect(phase.deferredTasks).toBe(1);
  });
});

// ── getPhaseOperations (extended) ─────────────────────────────────────────────

describe('getPhaseOperations (extended)', () => {
  function phasePayload(overrides: Record<string, unknown> = {}) {
    return {
      ...makeEnvelope(),
      feature_id: 'feat-1',
      phase_number: 1,
      phase_token: 'PHASE-1',
      phase_title: 'Phase 1',
      raw_status: 'in_progress',
      effective_status: 'in_progress',
      is_ready: false,
      readiness_state: 'blocked',
      phase_batches: [],
      blocked_batch_ids: [],
      tasks: [],
      dependency_resolution: {},
      progress_evidence: [],
      ...overrides,
    };
  }

  it('throws PlanningApiError on 5xx HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('', { status: 500, statusText: 'Internal Server Error' }),
    ));

    await expect(getPhaseOperations('feat-1', 1)).rejects.toMatchObject({
      name: 'PlanningApiError',
      status: 500,
    });
  });

  it('returns empty progressEvidence array when wire field is empty', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(phasePayload({ progress_evidence: [] })),
    ));

    const result = await getPhaseOperations('feat-1', 1);
    expect(result.progressEvidence).toEqual([]);
  });

  it('passes through dependency_resolution dict as-is', async () => {
    const depRes = { blockers: 2, readyDependencies: 5, strategy: 'parallel' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(phasePayload({ dependency_resolution: depRes })),
    ));

    const result = await getPhaseOperations('feat-1', 1);
    expect(result.dependencyResolution).toMatchObject(depRes);
  });

  it('adapts task list with all fields', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(phasePayload({
        tasks: [
          {
            task_id: 'TASK-2.1',
            title: 'Write unit tests',
            status: 'todo',
            assignees: ['agent-beta', 'agent-gamma'],
            blockers: ['TASK-1.5'],
            batch_id: 'batch-02',
          },
        ],
      })),
    ));

    const result = await getPhaseOperations('feat-1', 1);
    expect(result.tasks).toHaveLength(1);
    const task = result.tasks[0];
    expect(task.taskId).toBe('TASK-2.1');
    expect(task.title).toBe('Write unit tests');
    expect(task.status).toBe('todo');
    expect(task.assignees).toEqual(['agent-beta', 'agent-gamma']);
    expect(task.blockers).toEqual(['TASK-1.5']);
    expect(task.batchId).toBe('batch-02');
  });

  it('adapts is_ready=true to isReady=true and readiness_state=ready', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(phasePayload({ is_ready: true, readiness_state: 'ready' })),
    ));

    const result = await getPhaseOperations('feat-1', 1);
    expect(result.isReady).toBe(true);
    expect(result.readinessState).toBe('ready');
  });

  it('returns empty blockedBatchIds when wire field is absent', async () => {
    // Simulate missing field (defaults to empty)
    const payload = phasePayload({ blocked_batch_ids: undefined });
    delete (payload as Record<string, unknown>).blocked_batch_ids;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(payload)));

    const result = await getPhaseOperations('feat-1', 1);
    expect(result.blockedBatchIds).toEqual([]);
  });
});
