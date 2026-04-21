import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  clearPlanningBrowserCache,
  getFeaturePlanningContext,
  getPlanningBrowserCacheSnapshot,
  getPhaseOperations,
  getProjectPlanningGraph,
  getProjectPlanningSummary,
  PLANNING_BROWSER_CACHE_LIMITS,
  prefetchFeaturePlanningContext,
} from '../planning';
import {
  featurePhaseTopic,
  featurePlanningTopic,
  projectPlanningTopic,
} from '../live/topics';

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
    data_freshness: '2026-04-16T00:00:00Z',
    generated_at: '2026-04-16T00:01:00Z',
    source_refs: ['projects.json'],
    ...overrides,
  };
}

function projectSummaryPayload(overrides: Record<string, unknown> = {}) {
  return {
    ...makeEnvelope(),
    project_id: 'proj-1',
    project_name: 'Project 1',
    total_feature_count: 0,
    active_feature_count: 0,
    stale_feature_count: 0,
    blocked_feature_count: 0,
    mismatch_count: 0,
    reversal_count: 0,
    stale_feature_ids: [],
    reversal_feature_ids: [],
    blocked_feature_ids: [],
    node_counts_by_type: {
      prd: 0,
      design_spec: 0,
      implementation_plan: 0,
      progress: 0,
      context: 0,
      tracker: 0,
      report: 0,
    },
    feature_summaries: [],
    ...overrides,
  };
}

afterEach(() => {
  clearPlanningBrowserCache();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// ── Topic helpers ─────────────────────────────────────────────────────────────

describe('planning live topic helpers', () => {
  it('projectPlanningTopic produces the correct topic string', () => {
    expect(projectPlanningTopic('proj-1')).toBe('project.proj-1.planning');
  });

  it('featurePlanningTopic produces the correct topic string', () => {
    expect(featurePlanningTopic('feat-abc')).toBe('feature.feat-abc.planning');
  });

  it('featurePhaseTopic produces the correct topic string (numeric phase)', () => {
    expect(featurePhaseTopic('feat-abc', 3)).toBe('feature.feat-abc.phase.3');
  });

  it('featurePhaseTopic produces the correct topic string (string phase)', () => {
    expect(featurePhaseTopic('feat-abc', '2')).toBe('feature.feat-abc.phase.2');
  });

  it('normalizes segment casing and trims whitespace', () => {
    expect(projectPlanningTopic(' PROJ-1 ')).toBe('project.proj-1.planning');
    expect(featurePlanningTopic(' Feat-XYZ ')).toBe('feature.feat-xyz.planning');
    expect(featurePhaseTopic(' Feat-XYZ ', 1)).toBe('feature.feat-xyz.phase.1');
  });
});

// ── getProjectPlanningSummary ─────────────────────────────────────────────────

describe('getProjectPlanningSummary', () => {
  it('calls the correct URL without projectId', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        ...makeEnvelope(),
        project_id: 'default',
        project_name: '',
        total_feature_count: 0,
        active_feature_count: 0,
        stale_feature_count: 0,
        blocked_feature_count: 0,
        mismatch_count: 0,
        reversal_count: 0,
        stale_feature_ids: [],
        reversal_feature_ids: [],
        blocked_feature_ids: [],
        node_counts_by_type: { prd: 0, design_spec: 0, implementation_plan: 0, progress: 0, context: 0, tracker: 0, report: 0 },
        feature_summaries: [],
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary();

    expect(fetchMock).toHaveBeenCalledWith('/api/agent/planning/summary');
  });

  it('appends project_id query param when provided', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        ...makeEnvelope(),
        project_id: 'my-project',
        project_name: 'My Project',
        total_feature_count: 5,
        active_feature_count: 3,
        stale_feature_count: 1,
        blocked_feature_count: 1,
        mismatch_count: 2,
        reversal_count: 0,
        stale_feature_ids: ['feat-stale'],
        reversal_feature_ids: [],
        blocked_feature_ids: ['feat-blocked'],
        node_counts_by_type: { prd: 1, design_spec: 2, implementation_plan: 3, progress: 4, context: 1, tracker: 0, report: 0 },
        feature_summaries: [],
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await getProjectPlanningSummary('my-project');

    expect(fetchMock).toHaveBeenCalledWith('/api/agent/planning/summary?project_id=my-project');
    // Verify camelCase adaptation
    expect(result.projectId).toBe('my-project');
    expect(result.projectName).toBe('My Project');
    expect(result.totalFeatureCount).toBe(5);
    expect(result.staleFeatureIds).toEqual(['feat-stale']);
    expect(result.nodeCountsByType.designSpec).toBe(2);
    expect(result.nodeCountsByType.implementationPlan).toBe(3);
  });

  it('adapts envelope fields to camelCase', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        ...makeEnvelope({ status: 'partial', source_refs: ['db', 'fs'] }),
        project_id: 'p',
        project_name: '',
        total_feature_count: 0,
        active_feature_count: 0,
        stale_feature_count: 0,
        blocked_feature_count: 0,
        mismatch_count: 0,
        reversal_count: 0,
        stale_feature_ids: [],
        reversal_feature_ids: [],
        blocked_feature_ids: [],
        node_counts_by_type: { prd: 0, design_spec: 0, implementation_plan: 0, progress: 0, context: 0, tracker: 0, report: 0 },
        feature_summaries: [],
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await getProjectPlanningSummary();

    expect(result.status).toBe('partial');
    expect(result.dataFreshness).toBe('2026-04-16T00:00:00Z');
    expect(result.generatedAt).toBe('2026-04-16T00:01:00Z');
    expect(result.sourceRefs).toEqual(['db', 'fs']);
  });

  it('throws PlanningApiError on HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 500, statusText: 'Internal Server Error' })));

    await expect(getProjectPlanningSummary()).rejects.toMatchObject({
      name: 'PlanningApiError',
      status: 500,
    });
  });

  it('returns a warm cached summary immediately while revalidation is pending', async () => {
    let resolveRevalidation: (response: Response) => void = () => {};
    const revalidation = new Promise<Response>((resolve) => {
      resolveRevalidation = resolve;
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse(projectSummaryPayload({
        project_id: 'proj-cache',
        project_name: 'Warm Project v1',
        data_freshness: '2026-04-16T00:00:00Z',
      })))
      .mockReturnValueOnce(revalidation);
    vi.stubGlobal('fetch', fetchMock);

    await expect(getProjectPlanningSummary('proj-cache')).resolves.toMatchObject({
      projectName: 'Warm Project v1',
    });
    await expect(getProjectPlanningSummary('proj-cache')).resolves.toMatchObject({
      projectName: 'Warm Project v1',
      dataFreshness: '2026-04-16T00:00:00Z',
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    resolveRevalidation(okResponse(projectSummaryPayload({
      project_id: 'proj-cache',
      project_name: 'Warm Project v2',
      data_freshness: '2026-04-16T00:05:00Z',
    })));
    await revalidation;
    await vi.waitFor(() => {
      expect(getPlanningBrowserCacheSnapshot().entries[0]?.latestFreshness).toBe('2026-04-16T00:05:00Z');
    });
  });

  it('refreshes the warm summary cache from background revalidation', async () => {
    let resolveRevalidation: (response: Response) => void = () => {};
    const revalidation = new Promise<Response>((resolve) => {
      resolveRevalidation = resolve;
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse(projectSummaryPayload({
        project_id: 'proj-refresh',
        project_name: 'Refresh Project v1',
        data_freshness: '2026-04-16T00:00:00Z',
      })))
      .mockReturnValueOnce(revalidation);
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-refresh');
    await getProjectPlanningSummary('proj-refresh');

    resolveRevalidation(okResponse(projectSummaryPayload({
      project_id: 'proj-refresh',
      project_name: 'Refresh Project v2',
      data_freshness: '2026-04-16T00:10:00Z',
    })));
    await revalidation;
    await vi.waitFor(() => {
      expect(getPlanningBrowserCacheSnapshot().entries[0]?.latestFreshness).toBe('2026-04-16T00:10:00Z');
    });

    await expect(getProjectPlanningSummary('proj-refresh')).resolves.toMatchObject({
      projectName: 'Refresh Project v2',
      dataFreshness: '2026-04-16T00:10:00Z',
    });
  });

  it('evicts oldest project summary keys when the browser cache is bounded', async () => {
    const projectLoads = new Map<string, number>();
    const fetchMock = vi.fn((url: string) => {
      const parsed = new URL(url, 'http://ccdash.local');
      const projectId = parsed.searchParams.get('project_id') || 'default';
      const loadCount = (projectLoads.get(projectId) ?? 0) + 1;
      projectLoads.set(projectId, loadCount);
      return Promise.resolve(okResponse(projectSummaryPayload({
        project_id: projectId,
        project_name: `${projectId} load ${loadCount}`,
        data_freshness: `2026-04-16T00:${String(loadCount).padStart(2, '0')}:00Z`,
      })));
    });
    vi.stubGlobal('fetch', fetchMock);

    for (let index = 0; index <= PLANNING_BROWSER_CACHE_LIMITS.projects; index += 1) {
      await getProjectPlanningSummary(`proj-${index}`);
    }

    expect(getPlanningBrowserCacheSnapshot().projectsCached).toBe(PLANNING_BROWSER_CACHE_LIMITS.projects);
    await expect(getProjectPlanningSummary('proj-0')).resolves.toMatchObject({
      projectName: 'proj-0 load 2',
    });
  });
});

// ── getProjectPlanningGraph ───────────────────────────────────────────────────

describe('getProjectPlanningGraph', () => {
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

  it('calls the correct URL without options', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(graphPayload())));

    await getProjectPlanningGraph();

    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/agent/planning/graph');
  });

  it('wires feature_id and depth query params', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(graphPayload({ feature_id: 'feat-1', node_count: 2 }))));

    const result = await getProjectPlanningGraph({ featureId: 'feat-1', depth: 2 });

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/agent/planning/graph?feature_id=feat-1&depth=2',
    );
    expect(result.featureId).toBe('feat-1');
  });

  it('throws PlanningApiError(404) when envelope signals missing feature sentinel', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(graphPayload({ status: 'error', nodes: [], feature_id: null })),
    ));

    await expect(
      getProjectPlanningGraph({ featureId: 'ghost-feature' }),
    ).rejects.toMatchObject({ name: 'PlanningApiError', status: 404 });
  });
});

// ── getFeaturePlanningContext ─────────────────────────────────────────────────

describe('getFeaturePlanningContext', () => {
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

  it('calls the correct URL for a feature', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(contextPayload())));

    await getFeaturePlanningContext('feat-1');

    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/agent/planning/features/feat-1');
  });

  it('encodes special characters in featureId', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(contextPayload({ feature_id: 'feat/special' }))));

    await getFeaturePlanningContext('feat/special');

    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/agent/planning/features/feat%2Fspecial');
  });

  it('adapts snake_case fields to camelCase', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(contextPayload({
        feature_name: 'Alpha Feature',
        effective_status: 'blocked',
        mismatch_state: 'blocked',
        blocked_batch_ids: ['batch-1'],
        linked_artifact_refs: ['docs/prd.md'],
      })),
    ));

    const result = await getFeaturePlanningContext('feat-1');

    expect(result.featureName).toBe('Alpha Feature');
    expect(result.effectiveStatus).toBe('blocked');
    expect(result.mismatchState).toBe('blocked');
    expect(result.blockedBatchIds).toEqual(['batch-1']);
    expect(result.linkedArtifactRefs).toEqual(['docs/prd.md']);
  });

  it('throws PlanningApiError(404) on 404 HTTP status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Feature not found.' }), {
        status: 404,
        headers: { 'content-type': 'application/json' },
      }),
    ));

    await expect(getFeaturePlanningContext('missing-feat')).rejects.toMatchObject({
      name: 'PlanningApiError',
      status: 404,
    });
  });

  it('throws PlanningApiError(404) for status=error + empty feature_name sentinel', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(contextPayload({ status: 'error', feature_name: '' })),
    ));

    await expect(getFeaturePlanningContext('ghost')).rejects.toMatchObject({
      name: 'PlanningApiError',
      status: 404,
      envelopeStatus: 'error',
    });
  });

  it('appends project_id when provided', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(contextPayload())));

    await getFeaturePlanningContext('feat-1', { projectId: 'proj-42' });

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/agent/planning/features/feat-1?project_id=proj-42',
    );
  });

  it('reuses a hovered prefetch for the subsequent open', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(contextPayload())));

    await prefetchFeaturePlanningContext('feat-1', { projectId: 'proj-42' });
    const result = await getFeaturePlanningContext('feat-1', { projectId: 'proj-42' });

    expect(result.featureId).toBe('feat-1');
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
  });

  it('deduplicates in-flight feature context requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(contextPayload())));

    await Promise.all([
      getFeaturePlanningContext('feat-1', { projectId: 'proj-42' }),
      prefetchFeaturePlanningContext('feat-1', { projectId: 'proj-42' }),
    ]);

    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
  });
});

// ── getPhaseOperations ────────────────────────────────────────────────────────

describe('getPhaseOperations', () => {
  function phasePayload(overrides: Record<string, unknown> = {}) {
    return {
      ...makeEnvelope(),
      feature_id: 'feat-1',
      phase_number: 2,
      phase_token: 'phase_2',
      phase_title: 'Implementation',
      raw_status: 'in_progress',
      effective_status: 'in_progress',
      is_ready: false,
      readiness_state: 'blocked',
      phase_batches: [],
      blocked_batch_ids: ['batch-A'],
      tasks: [],
      dependency_resolution: { cleared: false },
      progress_evidence: [],
      ...overrides,
    };
  }

  it('calls the correct URL for a phase', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(phasePayload())));

    await getPhaseOperations('feat-1', 2);

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/agent/planning/features/feat-1/phases/2',
    );
  });

  it('adapts snake_case phase fields to camelCase', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(phasePayload({
        tasks: [
          { task_id: 't-1', title: 'Write tests', status: 'todo', assignees: ['agent-1'], blockers: [], batch_id: 'batch-A' },
        ],
        is_ready: true,
        readiness_state: 'ready',
      })),
    ));

    const result = await getPhaseOperations('feat-1', 2);

    expect(result.isReady).toBe(true);
    expect(result.readinessState).toBe('ready');
    expect(result.tasks[0].taskId).toBe('t-1');
    expect(result.tasks[0].assignees).toEqual(['agent-1']);
    expect(result.blockedBatchIds).toEqual(['batch-A']);
  });

  it('throws PlanningApiError(404) for status=error + empty phase_token sentinel', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(phasePayload({ status: 'error', phase_token: '' })),
    ));

    await expect(getPhaseOperations('feat-1', 99)).rejects.toMatchObject({
      name: 'PlanningApiError',
      status: 404,
    });
  });

  it('appends project_id when provided', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse(phasePayload())));

    await getPhaseOperations('feat-1', 2, { projectId: 'proj-x' });

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/agent/planning/features/feat-1/phases/2?project_id=proj-x',
    );
  });
});
