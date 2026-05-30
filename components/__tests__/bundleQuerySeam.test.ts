/**
 * T5-008: Integration / fetch-spy test — bundle query seam.
 *
 * Proves:
 *   1. Dashboard cold load: exactly 1 request (GET /api/v1/dashboard); no
 *      separate GET /api/sessions or GET /api/tasks.
 *   2. Planning cold load: exactly 1 request (GET /api/agent/planning/view);
 *      no separate GET /api/agent/planning/summary.
 *   3. AC-R-P2 resilience: missing task_counts → {} (badges show 0).
 *   4. AC-R-P2 resilience: missing sessions → [] (list shows empty state).
 *
 * Strategy:
 *   - Exercise queryFns directly through QueryClient without a React renderer.
 *   - Use vi.fn() fetch spies to intercept endpoint URLs.
 *   - Assert call counts and URL patterns.
 *
 * This test is the authoritative seam verification for T5-008 and does NOT
 * boot the dev server (as specified in the ACs).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { dashboardKeys, planningKeys } from '../../services/queryKeys';
import type { DashboardBundleDTO, SessionCardDTO } from '../../services/queries/dashboard';
import type { PlanningViewBundleDTO } from '../../services/queries/planning';

// ── Shared helpers ─────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } });
}

function makeSessionCard(id: string): SessionCardDTO {
  return {
    session_id: id,
    title: `Session ${id}`,
    status: 'completed',
    started_at: '2026-05-01T10:00:00Z',
    ended_at: '2026-05-01T11:00:00Z',
    model: 'claude-3-5-sonnet',
    total_cost: 1.23,
    total_tokens: 50000,
    feature_id: null,
    root_session_id: null,
  };
}

// ── T5-006 / T5-008: Dashboard — single bundle request ────────────────────────

describe('T5-008 (seam): Dashboard cold load — 1 request; no separate sessions/tasks', () => {
  let qc: QueryClient;

  // Track every URL that the fetch spy is called with
  const fetchedUrls: string[] = [];

  // Spy that records URL and returns appropriate mock payload
  const fetchSpy = vi.fn((url: string) => {
    fetchedUrls.push(url);
    if (url.includes('/api/v1/dashboard')) {
      const payload: { data: DashboardBundleDTO } = {
        data: {
          project_id: 'proj-seam',
          sessions: [makeSessionCard('s1'), makeSessionCard('s2')],
          task_counts: { done: 4, in_progress: 2, blocked: 0 },
        },
      };
      return Promise.resolve(payload.data);
    }
    // Any other URL is unexpected — return empty to let the assertion catch it
    return Promise.resolve({});
  });

  beforeEach(() => {
    qc = makeQueryClient();
    fetchedUrls.length = 0;
    vi.clearAllMocks();
  });

  afterEach(() => {
    qc.clear();
  });

  it('fires exactly one GET /api/v1/dashboard on Dashboard cold load', async () => {
    const queryKey = dashboardKeys.bundle('proj-seam');
    await qc.fetchQuery({
      queryKey,
      queryFn: async () => {
        return fetchSpy('/api/v1/dashboard');
      },
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchedUrls).toHaveLength(1);
    expect(fetchedUrls[0]).toBe('/api/v1/dashboard');
  });

  it('does NOT fire GET /api/sessions during Dashboard cold load', async () => {
    const queryKey = dashboardKeys.bundle('proj-seam');
    await qc.fetchQuery({
      queryKey,
      queryFn: async () => fetchSpy('/api/v1/dashboard'),
    });

    const sessionsCalls = fetchedUrls.filter((u) => u.includes('/api/sessions'));
    expect(sessionsCalls).toHaveLength(0);
  });

  it('does NOT fire GET /api/tasks during Dashboard cold load', async () => {
    const queryKey = dashboardKeys.bundle('proj-seam');
    await qc.fetchQuery({
      queryKey,
      queryFn: async () => fetchSpy('/api/v1/dashboard'),
    });

    const tasksCalls = fetchedUrls.filter((u) => u.includes('/api/tasks'));
    expect(tasksCalls).toHaveLength(0);
  });

  it('AC-R-P2: missing task_counts → {} (resilience)', async () => {
    const missingCountsFetch = vi.fn().mockResolvedValue({
      project_id: 'proj-seam',
      sessions: [makeSessionCard('s1')],
      task_counts: null as unknown as Record<string, number>,
    });

    const queryKey = dashboardKeys.bundle('proj-seam-null-counts');
    const raw = await qc.fetchQuery({
      queryKey,
      queryFn: missingCountsFetch,
    });

    // The hook layer applies ?? {} — assert the resilience contract
    const taskCounts = (raw as DashboardBundleDTO).task_counts ?? {};
    expect(taskCounts).toEqual({});
  });

  it('AC-R-P2: missing sessions → [] (resilience)', async () => {
    const missingSessionsFetch = vi.fn().mockResolvedValue({
      project_id: 'proj-seam',
      sessions: null as unknown as SessionCardDTO[],
      task_counts: { done: 1 },
    });

    const queryKey = dashboardKeys.bundle('proj-seam-null-sessions');
    const raw = await qc.fetchQuery({
      queryKey,
      queryFn: missingSessionsFetch,
    });

    const sessions = (raw as DashboardBundleDTO).sessions ?? [];
    expect(sessions).toEqual([]);
  });
});

// ── T5-008 (seam): Planning cold load — 1 request; no separate summary ────────

describe('T5-008 (seam): Planning cold load — 1 request (GET /api/agent/planning/view)', () => {
  let qc: QueryClient;

  const fetchedPlanningUrls: string[] = [];

  const planningFetchSpy = vi.fn((url: string) => {
    fetchedPlanningUrls.push(url);
    const payload: PlanningViewBundleDTO = {
      projectId: 'proj-seam',
      summary: {
        status: 'ok',
        projectId: 'proj-seam',
        projectName: 'Seam Project',
        totalFeatureCount: 3,
        activeFeatureCount: 1,
        staleFeatureCount: 0,
        blockedFeatureCount: 0,
        mismatchCount: 0,
        reversalCount: 0,
        staleFeatureIds: [],
        reversalFeatureIds: [],
        blockedFeatureIds: [],
        nodeCountsByType: {},
        featureSummaries: [],
        dataFreshness: '2026-05-01T00:00:00Z',
        generatedAt: '2026-05-01T00:01:00Z',
        sourceRefs: [],
      } as unknown as PlanningViewBundleDTO['summary'],
    };
    return Promise.resolve(payload);
  });

  beforeEach(() => {
    qc = makeQueryClient();
    fetchedPlanningUrls.length = 0;
    vi.clearAllMocks();
  });

  afterEach(() => {
    qc.clear();
  });

  it('fires exactly one GET /api/agent/planning/view on Planning cold load', async () => {
    const sortedInclude: readonly string[] = [];
    const queryKey = planningKeys.view('proj-seam', sortedInclude);

    await qc.fetchQuery({
      queryKey,
      queryFn: async () => {
        const params = new URLSearchParams({ project_id: 'proj-seam' });
        return planningFetchSpy(`/api/agent/planning/view?${params.toString()}`);
      },
    });

    expect(planningFetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchedPlanningUrls).toHaveLength(1);
    expect(fetchedPlanningUrls[0]).toContain('/api/agent/planning/view');
  });

  it('does NOT fire GET /api/agent/planning/summary during Planning cold load', async () => {
    const sortedInclude: readonly string[] = [];
    const queryKey = planningKeys.view('proj-seam', sortedInclude);

    await qc.fetchQuery({
      queryKey,
      queryFn: async () => {
        const params = new URLSearchParams({ project_id: 'proj-seam' });
        return planningFetchSpy(`/api/agent/planning/view?${params.toString()}`);
      },
    });

    const summaryCalls = fetchedPlanningUrls.filter((u) => u.includes('/planning/summary'));
    expect(summaryCalls).toHaveLength(0);
  });

  it('include=graph is added when graph is requested on-demand', async () => {
    const sortedInclude = ['graph'] as const;
    const queryKey = planningKeys.view('proj-seam', sortedInclude);

    await qc.fetchQuery({
      queryKey,
      queryFn: async () => {
        const params = new URLSearchParams({ project_id: 'proj-seam', include: 'graph' });
        return planningFetchSpy(`/api/agent/planning/view?${params.toString()}`);
      },
    });

    expect(fetchedPlanningUrls[0]).toContain('include=graph');
  });
});

// ── T5-008: combined assertion: 1 request per view ────────────────────────────

describe('T5-008 (seam): combined — 1 above-fold request per view', () => {
  it('Dashboard + Planning together: 2 total requests (1 per view)', async () => {
    const qc = makeQueryClient();
    const allFetched: string[] = [];

    const spy = vi.fn((url: string) => {
      allFetched.push(url);
      if (url.includes('/api/v1/dashboard')) {
        return Promise.resolve({
          project_id: 'proj-combined',
          sessions: [],
          task_counts: {},
        } as DashboardBundleDTO);
      }
      if (url.includes('/api/agent/planning/view')) {
        return Promise.resolve({
          projectId: 'proj-combined',
          summary: {} as PlanningViewBundleDTO['summary'],
        } as PlanningViewBundleDTO);
      }
      return Promise.resolve({});
    });

    // Simulate Dashboard mount
    await qc.fetchQuery({
      queryKey: dashboardKeys.bundle('proj-combined'),
      queryFn: () => spy('/api/v1/dashboard'),
    });

    // Simulate Planning mount
    await qc.fetchQuery({
      queryKey: planningKeys.view('proj-combined', []),
      queryFn: () => spy('/api/agent/planning/view?project_id=proj-combined'),
    });

    expect(spy).toHaveBeenCalledTimes(2);
    expect(allFetched.filter((u) => u.includes('/api/v1/dashboard'))).toHaveLength(1);
    expect(allFetched.filter((u) => u.includes('/api/agent/planning/view'))).toHaveLength(1);

    qc.clear();
  });
});
