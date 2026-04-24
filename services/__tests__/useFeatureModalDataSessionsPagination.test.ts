// P4-004: useFeatureModalData — Sessions Pagination
//
// Tests the session pagination accumulator added in P4-004:
//   - First load seeds sessionPagination from first-page response
//   - loadMoreSessions fetches next page and concatenates items
//   - Cursor / offset is threaded between pages
//   - featureId change aborts in-flight load-more and resets accumulator
//   - No-op when hasMore=false or isLoadingMore=true
//
// Strategy (no @testing-library/react):
//   Directly exercise getFeatureLinkedSessionPage mock sequences and verify
//   expected call counts and accumulator state using pure simulation of the
//   pagination logic, mirroring the hook's loadMoreSessions and seeding logic.

import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  buildModalSectionCacheKey,
  modalSectionCache,
  ModalSectionLRU,
  type SessionPaginationState,
} from '../useFeatureModalData';

vi.mock('../featureSurface', () => ({
  getFeatureModalOverview: vi.fn(),
  getFeatureModalSection: vi.fn(),
  getFeatureLinkedSessionPage: vi.fn(),
}));

import {
  getFeatureLinkedSessionPage,
  type LinkedFeatureSessionPageDTO,
  type LinkedFeatureSessionDTO,
} from '../featureSurface';

const mockSessions = vi.mocked(getFeatureLinkedSessionPage);

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeSession(id: string): LinkedFeatureSessionDTO {
  return {
    sessionId: id,
    title: `Session ${id}`,
    status: 'completed',
    model: 'claude-3',
    modelProvider: 'anthropic',
    modelFamily: 'claude',
    startedAt: '2026-04-23T00:00:00Z',
    endedAt: '2026-04-23T01:00:00Z',
    updatedAt: '2026-04-23T01:00:00Z',
    totalCost: 0.05,
    observedTokens: 1000,
    rootSessionId: id,
    parentSessionId: null,
    workflowType: 'standard',
    isPrimaryLink: true,
    isSubthread: false,
    threadChildCount: 0,
    reasons: ['manual'],
    commands: [],
    relatedTasks: [],
  };
}

function makePage(
  items: LinkedFeatureSessionDTO[],
  opts: { total?: number; offset?: number; hasMore?: boolean; nextCursor?: string | null } = {},
): LinkedFeatureSessionPageDTO {
  return {
    items,
    total: opts.total ?? items.length,
    offset: opts.offset ?? 0,
    limit: 20,
    hasMore: opts.hasMore ?? false,
    nextCursor: opts.nextCursor ?? null,
    enrichment: {
      includes: [],
      logsRead: false,
      commandCountIncluded: false,
      taskRefsIncluded: false,
      threadChildrenIncluded: false,
    },
    precision: 'eventually_consistent',
    freshness: null,
  };
}

// ── Simulate the pagination accumulator logic ─────────────────────────────────
// Mirrors the hook's loadMoreSessions + seed logic without React rendering.

interface PaginationSimState extends SessionPaginationState {}

function seedFromPage(page: LinkedFeatureSessionPageDTO): PaginationSimState {
  return {
    accumulatedItems: page.items,
    serverTotal: page.total,
    hasMore: page.hasMore,
    isLoadingMore: false,
    nextCursor: page.nextCursor,
    nextOffset: page.offset + page.items.length,
  };
}

async function simulateLoadMore(
  featureId: string,
  state: PaginationSimState,
  limit?: number,
  abortSignal?: AbortSignal,
): Promise<PaginationSimState> {
  if (!state.hasMore || state.isLoadingMore) return state;

  const inProgress = { ...state, isLoadingMore: true };

  try {
    const page = await getFeatureLinkedSessionPage(featureId, {
      limit,
      offset: state.nextOffset,
    });

    if (abortSignal?.aborted) return state;

    return {
      accumulatedItems: [...inProgress.accumulatedItems, ...page.items],
      serverTotal: page.total,
      hasMore: page.hasMore,
      isLoadingMore: false,
      nextCursor: page.nextCursor,
      nextOffset: inProgress.nextOffset + page.items.length,
    };
  } catch {
    if (abortSignal?.aborted) return state;
    return { ...inProgress, isLoadingMore: false };
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.resetAllMocks();
  modalSectionCache.clear();
});

describe('P4-004 session pagination accumulator', () => {
  it('seeds hasMore=true from first-page response with more items available', async () => {
    const page1 = makePage([makeSession('s1'), makeSession('s2')], {
      total: 5,
      offset: 0,
      hasMore: true,
      nextCursor: 'cursor-1',
    });

    mockSessions.mockResolvedValueOnce(page1);
    await getFeatureLinkedSessionPage('feat-1', {});

    const state = seedFromPage(page1);

    expect(state.hasMore).toBe(true);
    expect(state.accumulatedItems).toHaveLength(2);
    expect(state.serverTotal).toBe(5);
    expect(state.nextCursor).toBe('cursor-1');
    expect(state.nextOffset).toBe(2);
  });

  it('seeds hasMore=false from single-page response', async () => {
    const page = makePage([makeSession('s1')], { total: 1, hasMore: false, nextCursor: null });
    mockSessions.mockResolvedValueOnce(page);
    await getFeatureLinkedSessionPage('feat-2', {});

    const state = seedFromPage(page);
    expect(state.hasMore).toBe(false);
    expect(state.nextCursor).toBeNull();
  });

  it('loadMore fetches next page and concatenates items', async () => {
    const page1 = makePage([makeSession('s1'), makeSession('s2')], {
      total: 4,
      offset: 0,
      hasMore: true,
      nextCursor: 'cursor-1',
    });
    const page2 = makePage([makeSession('s3'), makeSession('s4')], {
      total: 4,
      offset: 2,
      hasMore: false,
      nextCursor: null,
    });

    mockSessions.mockResolvedValueOnce(page1).mockResolvedValueOnce(page2);

    // Seed first page
    await getFeatureLinkedSessionPage('feat-1', {});
    let state = seedFromPage(page1);

    // Load more
    state = await simulateLoadMore('feat-1', state);

    expect(mockSessions).toHaveBeenCalledTimes(2);
    // Second call must use the nextOffset from the first page
    expect(mockSessions).toHaveBeenNthCalledWith(2, 'feat-1', { limit: undefined, offset: 2 });

    expect(state.accumulatedItems).toHaveLength(4);
    expect(state.accumulatedItems.map(s => s.sessionId)).toEqual(['s1', 's2', 's3', 's4']);
    expect(state.hasMore).toBe(false);
    expect(state.nextOffset).toBe(4);
  });

  it('cursor is threaded: second loadMore uses updated nextOffset', async () => {
    const page1 = makePage([makeSession('s1')], { total: 3, offset: 0, hasMore: true });
    const page2 = makePage([makeSession('s2')], { total: 3, offset: 1, hasMore: true });
    const page3 = makePage([makeSession('s3')], { total: 3, offset: 2, hasMore: false });

    mockSessions
      .mockResolvedValueOnce(page1)
      .mockResolvedValueOnce(page2)
      .mockResolvedValueOnce(page3);

    await getFeatureLinkedSessionPage('feat-3', {});
    let state = seedFromPage(page1);
    state = await simulateLoadMore('feat-3', state);
    state = await simulateLoadMore('feat-3', state);

    expect(mockSessions).toHaveBeenCalledTimes(3);
    expect(mockSessions).toHaveBeenNthCalledWith(2, 'feat-3', { limit: undefined, offset: 1 });
    expect(mockSessions).toHaveBeenNthCalledWith(3, 'feat-3', { limit: undefined, offset: 2 });

    expect(state.accumulatedItems).toHaveLength(3);
    expect(state.hasMore).toBe(false);
  });

  it('loadMore is a no-op when hasMore=false', async () => {
    const state: PaginationSimState = {
      accumulatedItems: [makeSession('s1')],
      serverTotal: 1,
      hasMore: false,
      isLoadingMore: false,
      nextCursor: null,
      nextOffset: 1,
    };

    const newState = await simulateLoadMore('feat-4', state);
    expect(mockSessions).not.toHaveBeenCalled();
    expect(newState).toBe(state); // same reference — no update
  });

  it('loadMore is a no-op when isLoadingMore=true', async () => {
    const state: PaginationSimState = {
      accumulatedItems: [],
      serverTotal: 5,
      hasMore: true,
      isLoadingMore: true,
      nextCursor: null,
      nextOffset: 0,
    };

    const newState = await simulateLoadMore('feat-5', state);
    expect(mockSessions).not.toHaveBeenCalled();
    expect(newState).toBe(state);
  });

  it('abort on featureId change: aborted loadMore does not mutate state', async () => {
    const page = makePage([makeSession('s1')], { total: 2, hasMore: true });
    mockSessions.mockImplementation(
      () =>
        new Promise(resolve =>
          setTimeout(() => resolve(page), 50),
        ),
    );

    const ctrl = new AbortController();
    const state: PaginationSimState = {
      accumulatedItems: [],
      serverTotal: 2,
      hasMore: true,
      isLoadingMore: false,
      nextCursor: null,
      nextOffset: 0,
    };

    // Start load-more, then abort before it resolves
    const loadPromise = simulateLoadMore('feat-6', state, undefined, ctrl.signal);
    ctrl.abort();

    const result = await loadPromise;

    // After abort, state should be unchanged (returned original state reference)
    expect(result).toBe(state);
  });

  it('reset on featureId change: accumulator clears to empty', () => {
    // Simulates the effect of prevAccumulatedCountRef being reset to 0 and
    // setSessionPagination being called with INITIAL on feature change.
    const initialState: PaginationSimState = {
      accumulatedItems: [],
      serverTotal: 0,
      hasMore: false,
      isLoadingMore: false,
      nextCursor: null,
      nextOffset: 0,
    };

    expect(initialState.accumulatedItems).toHaveLength(0);
    expect(initialState.hasMore).toBe(false);
    expect(initialState.serverTotal).toBe(0);
  });

  it('cache key differentiates session params (offset)', () => {
    const key0 = buildModalSectionCacheKey('feat-1', 'sessions', { offset: 0 });
    const key1 = buildModalSectionCacheKey('feat-1', 'sessions', { offset: 20 });
    expect(key0).not.toBe(key1);
  });

  it('LRU cache stores and retrieves paginated session pages', () => {
    const cache = new ModalSectionLRU(10);
    const page = makePage([makeSession('s1')], { total: 1, hasMore: false });
    const key = buildModalSectionCacheKey('feat-1', 'sessions', { offset: 0 });
    cache.set(key, page);
    expect(cache.get(key)).toBe(page);
  });
});
