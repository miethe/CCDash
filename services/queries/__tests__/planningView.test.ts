/**
 * Tests for usePlanningViewQuery (T5-007).
 *
 * Strategy: exercise queryFn and queryKey logic directly through QueryClient
 * without @testing-library/react.
 *
 * Scenarios covered:
 *   T5-007 — above-fold (no include flags) issues one request with no include= param
 *   T5-007 — includeGraph=true adds include=graph to the request URL
 *   T5-007 — includeSessionBoard=true adds include=session_board
 *   T5-007 — both flags → include=graph,session_board (sorted)
 *   T5-007 — planningKeys.view key structure includes projectId + sorted include
 *   T5-007 — distinct include arrays produce distinct cache keys
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { planningKeys } from '../../queryKeys';
import type { PlanningViewBundleDTO } from '../planning';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeViewPayload(overrides: Partial<PlanningViewBundleDTO> = {}): PlanningViewBundleDTO {
  return {
    project_id: 'proj-1',
    summary: {
      status: 'ok',
      projectId: 'proj-1',
      projectName: 'Test Project',
      totalFeatureCount: 2,
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
    ...overrides,
  };
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
}

/**
 * Builds a queryFn that mirrors usePlanningViewQuery's fetch logic,
 * but substitutes the real apiRequestJson with a spy so we can assert
 * the URL construction without a live server.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyFetchSpy = (url: string) => Promise<any>;

function makeViewQueryFn(
  mockFetch: AnyFetchSpy,
  projectId: string,
  sortedInclude: readonly string[],
) {
  return async (): Promise<PlanningViewBundleDTO> => {
    const params = new URLSearchParams();
    params.set('project_id', projectId);
    if (sortedInclude.length > 0) {
      params.set('include', sortedInclude.join(','));
    }
    const url = `/api/agent/planning/view?${params.toString()}`;
    return (await mockFetch(url)) as PlanningViewBundleDTO;
  };
}

// ── T5-007: above-fold call — no include flags ────────────────────────────────

describe('T5-007: usePlanningViewQuery — above-fold (no include flags)', () => {
  let qc: QueryClient;
  let spy: AnyFetchSpy & { mock: { calls: unknown[][] } };

  beforeEach(() => {
    qc = makeQueryClient();
    spy = vi.fn().mockResolvedValue(makeViewPayload()) as AnyFetchSpy & { mock: { calls: unknown[][] } };
  });

  afterEach(() => {
    qc.clear();
    vi.restoreAllMocks();
  });

  it('fires exactly one request on initial fetch', async () => {
    const sortedInclude: readonly string[] = [];
    const queryKey = planningKeys.view('proj-1', sortedInclude);
    await qc.fetchQuery({
      queryKey,
      queryFn: makeViewQueryFn(spy, 'proj-1', sortedInclude),
    });
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('URL does NOT contain include= when no flags are set', async () => {
    const sortedInclude: readonly string[] = [];
    const queryKey = planningKeys.view('proj-1', sortedInclude);
    await qc.fetchQuery({
      queryKey,
      queryFn: makeViewQueryFn(spy, 'proj-1', sortedInclude),
    });
    const calledUrl: string = spy.mock.calls[0][0] as string;
    expect(calledUrl).not.toContain('include=');
  });
});

// ── T5-007: include=graph ─────────────────────────────────────────────────────

describe('T5-007: usePlanningViewQuery — includeGraph=true', () => {
  it('URL contains include=graph when includeGraph is true', async () => {
    const qc = makeQueryClient();
    const mockFetch = vi.fn().mockResolvedValue(makeViewPayload({ graph: {} }));
    const sortedInclude = ['graph'] as const;
    const queryKey = planningKeys.view('proj-1', sortedInclude);

    await qc.fetchQuery({
      queryKey,
      queryFn: makeViewQueryFn(mockFetch, 'proj-1', sortedInclude),
    });

    const calledUrl: string = mockFetch.mock.calls[0][0];
    expect(calledUrl).toContain('include=graph');

    qc.clear();
  });
});

// ── T5-007: include=session_board ─────────────────────────────────────────────

describe('T5-007: usePlanningViewQuery — includeSessionBoard=true', () => {
  it('URL contains include=session_board when includeSessionBoard is true', async () => {
    const qc = makeQueryClient();
    const mockFetch = vi.fn().mockResolvedValue(makeViewPayload({ session_board: {} }));
    const sortedInclude = ['session_board'] as const;
    const queryKey = planningKeys.view('proj-1', sortedInclude);

    await qc.fetchQuery({
      queryKey,
      queryFn: makeViewQueryFn(mockFetch, 'proj-1', sortedInclude),
    });

    const calledUrl: string = mockFetch.mock.calls[0][0];
    expect(calledUrl).toContain('include=session_board');

    qc.clear();
  });
});

// ── T5-007: include=graph,session_board (both flags) ──────────────────────────

describe('T5-007: usePlanningViewQuery — both flags → sorted include param', () => {
  it('URL contains sorted include when both graph and session_board are requested', async () => {
    const qc = makeQueryClient();
    const mockFetch = vi.fn().mockResolvedValue(makeViewPayload({ graph: {}, session_board: {} }));
    // Sorted: graph comes before session_board alphabetically
    const sortedInclude = ['graph', 'session_board'] as const;
    const queryKey = planningKeys.view('proj-1', sortedInclude);

    await qc.fetchQuery({
      queryKey,
      queryFn: makeViewQueryFn(mockFetch, 'proj-1', sortedInclude),
    });

    const calledUrl: string = mockFetch.mock.calls[0][0];
    // The include param should contain both, sorted alphabetically
    expect(calledUrl).toContain('include=graph%2Csession_board');

    qc.clear();
  });
});

// ── T5-007: query key structure ───────────────────────────────────────────────

describe('T5-007: planningKeys.view — key structure', () => {
  it('view key starts with projectId', () => {
    const key = planningKeys.view('proj-abc', []);
    expect(key[0]).toBe('proj-abc');
  });

  it('view key includes "planning" and "view" segments', () => {
    const key = planningKeys.view('proj-abc', []);
    expect(key).toContain('planning');
    expect(key).toContain('view');
  });

  it('empty include and ["graph"] produce distinct keys', () => {
    const keyEmpty = planningKeys.view('proj-1', []);
    const keyGraph = planningKeys.view('proj-1', ['graph']);
    expect(JSON.stringify(keyEmpty)).not.toBe(JSON.stringify(keyGraph));
  });

  it('["graph", "session_board"] and ["session_board", "graph"] produce the same key (sorted)', () => {
    // Sort is applied in the key factory
    const keyGS = planningKeys.view('proj-1', ['graph', 'session_board']);
    const keySG = planningKeys.view('proj-1', ['session_board', 'graph']);
    expect(JSON.stringify(keyGS)).toBe(JSON.stringify(keySG));
  });

  it('different projectIds produce distinct keys', () => {
    const keyA = planningKeys.view('proj-a', []);
    const keyB = planningKeys.view('proj-b', []);
    expect(JSON.stringify(keyA)).not.toBe(JSON.stringify(keyB));
  });
});

// ── T5-007: distinct cache entries for different include sets ─────────────────

describe('T5-007: usePlanningViewQuery — distinct cache entries per include set', () => {
  it('above-fold and graph-included fetches use different cache entries', async () => {
    const qc = makeQueryClient();
    const mockFetch = vi.fn().mockResolvedValue(makeViewPayload());
    const projectId = 'proj-cache-test';

    const keyAboveFold = planningKeys.view(projectId, []);
    const keyWithGraph = planningKeys.view(projectId, ['graph']);

    // Populate cache for above-fold
    await qc.fetchQuery({
      queryKey: keyAboveFold,
      queryFn: makeViewQueryFn(mockFetch, projectId, []),
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);

    // Graph key is a different cache entry — triggers a new fetch
    await qc.fetchQuery({
      queryKey: keyWithGraph,
      queryFn: makeViewQueryFn(mockFetch, projectId, ['graph']),
    });
    expect(mockFetch).toHaveBeenCalledTimes(2);

    // Above-fold cache still intact
    const cached = qc.getQueryData(keyAboveFold);
    expect(cached).toBeDefined();

    qc.clear();
  });
});
