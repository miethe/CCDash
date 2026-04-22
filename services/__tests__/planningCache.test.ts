/**
 * P16-002: Planning browser cache + lazy-load regression coverage.
 *
 * Phase 12 shipped active-first cached loading, stale-while-revalidate,
 * bounded cache eviction, and detail-only-on-open semantics for Planning.
 * This file pins the behaviors that make the reskin feel "instant":
 *
 *   1. Warm render      — navigating back to a cached project returns the
 *                         cached summary synchronously via
 *                         getCachedProjectPlanningSummary (no fetch).
 *   2. Stale revalidate — second call returns the warm value immediately
 *                         while a background fetch upgrades freshness and
 *                         invokes onRevalidated.
 *   3. Bounded cache    — freshness buckets, payload-type map, and feature
 *                         context LRU all honor PLANNING_BROWSER_CACHE_LIMITS.
 *   4. Detail-on-open   — heavy feature-context payloads are NOT fetched
 *                         at summary load time; they only fire when the
 *                         detail accessor is called (panel/modal open).
 *
 * All tests use vi.stubGlobal('fetch', ...) and clear the cache in afterEach
 * so no cross-test bleed. Existing warm/revalidate tests in planning.test.ts
 * are complementary — this file adds the bounds + lazy-load coverage.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  PLANNING_BROWSER_CACHE_LIMITS,
  clearPlanningBrowserCache,
  getCachedProjectPlanningSummary,
  getFeaturePlanningContext,
  getPhaseOperations,
  getPlanningBrowserCacheSnapshot,
  getProjectPlanningSummary,
  prefetchFeaturePlanningContext,
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

function featureContextPayload(overrides: Record<string, unknown> = {}) {
  return {
    ...makeEnvelope(),
    feature_id: 'feat-x',
    feature_name: 'Feature X',
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

afterEach(() => {
  clearPlanningBrowserCache();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// ── Warm render ───────────────────────────────────────────────────────────────

describe('warm render (cached summary on navigation back)', () => {
  it('getCachedProjectPlanningSummary returns null before the first load', () => {
    expect(getCachedProjectPlanningSummary('proj-warm')).toBeNull();
  });

  it('exposes the warm summary synchronously after the initial fetch', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      okResponse(projectSummaryPayload({
        project_id: 'proj-warm',
        project_name: 'Warm Project',
        total_feature_count: 7,
      })),
    ));

    await getProjectPlanningSummary('proj-warm');

    const cached = getCachedProjectPlanningSummary('proj-warm');
    expect(cached).not.toBeNull();
    expect(cached?.projectName).toBe('Warm Project');
    expect(cached?.totalFeatureCount).toBe(7);
  });

  it('keys the warm cache per projectId (no cross-project bleed)', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse(projectSummaryPayload({
        project_id: 'proj-a',
        project_name: 'A',
      })))
      .mockResolvedValueOnce(okResponse(projectSummaryPayload({
        project_id: 'proj-b',
        project_name: 'B',
      })));
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-a');
    await getProjectPlanningSummary('proj-b');

    expect(getCachedProjectPlanningSummary('proj-a')?.projectName).toBe('A');
    expect(getCachedProjectPlanningSummary('proj-b')?.projectName).toBe('B');
    expect(getCachedProjectPlanningSummary('proj-unknown')).toBeNull();
  });

  it('clearPlanningBrowserCache(projectId) drops just the targeted warm entry', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse(projectSummaryPayload({ project_id: 'proj-keep', project_name: 'Keep' })))
      .mockResolvedValueOnce(okResponse(projectSummaryPayload({ project_id: 'proj-drop', project_name: 'Drop' })));
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-keep');
    await getProjectPlanningSummary('proj-drop');

    clearPlanningBrowserCache('proj-drop');

    expect(getCachedProjectPlanningSummary('proj-keep')?.projectName).toBe('Keep');
    expect(getCachedProjectPlanningSummary('proj-drop')).toBeNull();
  });
});

// ── Stale-while-revalidate ────────────────────────────────────────────────────

describe('stale-while-revalidate', () => {
  it('invokes onRevalidated with the fresh payload after background refresh', async () => {
    let resolveRevalidation: (response: Response) => void = () => {};
    const revalidation = new Promise<Response>((resolve) => {
      resolveRevalidation = resolve;
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse(projectSummaryPayload({
        project_id: 'proj-swr',
        project_name: 'SWR v1',
        data_freshness: '2026-04-16T00:00:00Z',
      })))
      .mockReturnValueOnce(revalidation);
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-swr');

    const onRevalidated = vi.fn();
    const second = await getProjectPlanningSummary('proj-swr', { onRevalidated });
    expect(second.projectName).toBe('SWR v1');
    expect(onRevalidated).not.toHaveBeenCalled();

    resolveRevalidation(okResponse(projectSummaryPayload({
      project_id: 'proj-swr',
      project_name: 'SWR v2',
      data_freshness: '2026-04-16T00:05:00Z',
    })));

    await vi.waitFor(() => {
      expect(onRevalidated).toHaveBeenCalledTimes(1);
    });
    expect(onRevalidated.mock.calls[0][0]).toMatchObject({ projectName: 'SWR v2' });
  });

  it('keeps the warm value when the background revalidation fetch rejects', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse(projectSummaryPayload({
        project_id: 'proj-err',
        project_name: 'Stable v1',
        data_freshness: '2026-04-16T00:00:00Z',
      })))
      .mockRejectedValueOnce(new Error('network down'));
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-err');
    const second = await getProjectPlanningSummary('proj-err');

    expect(second.projectName).toBe('Stable v1');
    // Cached value must still be readable after the background rejection settles.
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    expect(getCachedProjectPlanningSummary('proj-err')?.projectName).toBe('Stable v1');
  });

  it('forceRefresh bypasses the warm cache and returns the fresh payload', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse(projectSummaryPayload({
        project_id: 'proj-force',
        project_name: 'Force v1',
        data_freshness: '2026-04-16T00:00:00Z',
      })))
      .mockResolvedValueOnce(okResponse(projectSummaryPayload({
        project_id: 'proj-force',
        project_name: 'Force v2',
        data_freshness: '2026-04-16T00:10:00Z',
      })));
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-force');
    const forced = await getProjectPlanningSummary('proj-force', { forceRefresh: true });

    expect(forced.projectName).toBe('Force v2');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

// ── Bounded cache eviction ────────────────────────────────────────────────────

describe('bounded cache eviction', () => {
  it('project cache never exceeds PLANNING_BROWSER_CACHE_LIMITS.projects', async () => {
    const fetchMock = vi.fn((url: string) => {
      const projectId = new URL(url, 'http://ccdash.local').searchParams.get('project_id') || 'default';
      return Promise.resolve(okResponse(projectSummaryPayload({
        project_id: projectId,
        project_name: projectId,
      })));
    });
    vi.stubGlobal('fetch', fetchMock);

    // Load twice the limit in distinct project keys.
    const overflow = PLANNING_BROWSER_CACHE_LIMITS.projects * 2;
    for (let i = 0; i < overflow; i += 1) {
      await getProjectPlanningSummary(`proj-${i}`);
    }

    const snapshot = getPlanningBrowserCacheSnapshot();
    expect(snapshot.projectsCached).toBe(PLANNING_BROWSER_CACHE_LIMITS.projects);
    // Oldest entries must have been evicted — the very first project key is gone.
    expect(getCachedProjectPlanningSummary('proj-0')).toBeNull();
    // The most recently loaded project is retained.
    expect(getCachedProjectPlanningSummary(`proj-${overflow - 1}`)).not.toBeNull();
  });

  it('freshness buckets per project cap at PLANNING_BROWSER_CACHE_LIMITS.freshnessKeysPerProject', async () => {
    const fetchMock = vi.fn((_url: string, _init?: unknown) => {
      // Each call returns a distinct data_freshness to force a new bucket.
      const counter = fetchMock.mock.calls.length;
      return Promise.resolve(okResponse(projectSummaryPayload({
        project_id: 'proj-fresh',
        project_name: `v${counter}`,
        data_freshness: `2026-04-16T00:${String(counter).padStart(2, '0')}:00Z`,
      })));
    });
    vi.stubGlobal('fetch', fetchMock);

    // Fire forceRefresh more times than the bucket cap. Each creates a new freshness.
    const overflow = PLANNING_BROWSER_CACHE_LIMITS.freshnessKeysPerProject + 2;
    for (let i = 0; i < overflow; i += 1) {
      await getProjectPlanningSummary('proj-fresh', { forceRefresh: true });
    }

    const entry = getPlanningBrowserCacheSnapshot().entries.find(
      (e) => e.projectKey === 'proj-fresh',
    );
    expect(entry).toBeDefined();
    expect(entry!.freshnessKeys.length).toBeLessThanOrEqual(
      PLANNING_BROWSER_CACHE_LIMITS.freshnessKeysPerProject,
    );
    // Latest freshness reflects the most recent fetch.
    expect(entry!.latestFreshness).toBe(
      `2026-04-16T00:${String(overflow).padStart(2, '0')}:00Z`,
    );
  });

  it('feature context cache never exceeds PLANNING_BROWSER_CACHE_LIMITS.featureContexts', async () => {
    const fetchMock = vi.fn((url: string) => {
      // Feature id is the last path segment before any query string.
      const match = /features\/([^/?]+)/.exec(url);
      const featureId = match ? decodeURIComponent(match[1]) : 'unknown';
      return Promise.resolve(okResponse(featureContextPayload({
        feature_id: featureId,
        feature_name: featureId,
      })));
    });
    vi.stubGlobal('fetch', fetchMock);

    const overflow = PLANNING_BROWSER_CACHE_LIMITS.featureContexts + 5;
    for (let i = 0; i < overflow; i += 1) {
      await getFeaturePlanningContext(`feat-${i}`);
    }

    // The oldest feature must have been evicted → second fetch on re-access.
    fetchMock.mockClear();
    await getFeaturePlanningContext('feat-0');
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // The most recent entry must still be warm → no additional fetch.
    fetchMock.mockClear();
    await getFeaturePlanningContext(`feat-${overflow - 1}`);
    expect(fetchMock).toHaveBeenCalledTimes(0);
  });
});

// ── Detail-only-on-open ───────────────────────────────────────────────────────

describe('detail-only-on-open (heavy payloads are lazy)', () => {
  it('getProjectPlanningSummary does NOT pre-fetch feature detail endpoints', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse(projectSummaryPayload({
        project_id: 'proj-lazy',
        project_name: 'Lazy Project',
        feature_summaries: [
          {
            feature_id: 'feat-lazy-1',
            feature_name: 'Lazy 1',
            raw_status: 'in_progress',
            effective_status: 'in_progress',
            is_mismatch: false,
            mismatch_state: 'aligned',
            has_blocked_phases: false,
            phase_count: 3,
            blocked_phase_count: 0,
            node_count: 5,
          },
        ],
      })),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-lazy');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrls = fetchMock.mock.calls.map((call) => String(call[0]));
    // Summary endpoint only — no detail endpoints should be touched.
    expect(calledUrls.every((u) => u.startsWith('/api/agent/planning/summary'))).toBe(true);
    expect(calledUrls.some((u) => /\/features\//.test(u))).toBe(false);
    expect(calledUrls.some((u) => /\/phases\//.test(u))).toBe(false);
  });

  it('getFeaturePlanningContext only fires when explicitly called (panel/modal open)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse(projectSummaryPayload({
        project_id: 'proj-lazy-2',
        project_name: 'Lazy Project 2',
      })),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-lazy-2');
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Swap the mock for the feature detail fetch and invoke explicitly —
    // this simulates a panel open handler.
    fetchMock.mockResolvedValueOnce(okResponse(featureContextPayload({
      feature_id: 'feat-lazy',
      feature_name: 'Lazy Feature',
    })));

    await getFeaturePlanningContext('feat-lazy', { projectId: 'proj-lazy-2' });

    const detailCalls = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .filter((u) => /\/features\//.test(u));
    expect(detailCalls).toHaveLength(1);
    expect(detailCalls[0]).toContain('/api/agent/planning/features/feat-lazy');
  });

  it('getPhaseOperations is lazy — not invoked by summary or feature-context fetches', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse(projectSummaryPayload({
        project_id: 'proj-phase',
        project_name: 'Phase Project',
      })))
      .mockResolvedValueOnce(okResponse(featureContextPayload({
        feature_id: 'feat-phase',
        feature_name: 'Phase Feature',
      })));
    vi.stubGlobal('fetch', fetchMock);

    await getProjectPlanningSummary('proj-phase');
    await getFeaturePlanningContext('feat-phase', { projectId: 'proj-phase' });

    const phaseCalls = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .filter((u) => /\/phases\//.test(u));
    expect(phaseCalls).toHaveLength(0);

    // Explicit phase-open call now fires the request.
    fetchMock.mockResolvedValueOnce(okResponse({
      ...makeEnvelope(),
      feature_id: 'feat-phase',
      phase_number: 1,
      phase_token: 'phase_1',
      phase_title: 'Planning',
      raw_status: 'todo',
      effective_status: 'todo',
      is_ready: true,
      readiness_state: 'ready',
      phase_batches: [],
      blocked_batch_ids: [],
      tasks: [],
      dependency_resolution: {},
      progress_evidence: [],
    }));
    await getPhaseOperations('feat-phase', 1, { projectId: 'proj-phase' });

    const postOpenPhaseCalls = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .filter((u) => /\/phases\//.test(u));
    expect(postOpenPhaseCalls).toHaveLength(1);
  });

  it('prefetchFeaturePlanningContext is an optional hover-only helper (not implicit)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse(projectSummaryPayload({
        project_id: 'proj-prefetch',
        project_name: 'Prefetch Project',
      })),
    );
    vi.stubGlobal('fetch', fetchMock);

    // Summary load does NOT invoke any prefetch — guaranteed by only one fetch.
    await getProjectPlanningSummary('proj-prefetch');
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fetchMock.mockResolvedValueOnce(okResponse(featureContextPayload({
      feature_id: 'feat-prefetch',
      feature_name: 'Prefetch Feature',
    })));

    // Explicit prefetch (e.g., hover intent) then open → single fetch total.
    await prefetchFeaturePlanningContext('feat-prefetch', { projectId: 'proj-prefetch' });
    await getFeaturePlanningContext('feat-prefetch', { projectId: 'proj-prefetch' });

    const detailCalls = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .filter((u) => /\/features\//.test(u));
    expect(detailCalls).toHaveLength(1);
  });
});
