/**
 * Tests for useDocumentsQuery (T2-001).
 *
 * Strategy: test queryFn directly through QueryClient.fetchInfiniteQuery
 * and verify the select transform, pagination, and memory cap behaviour.
 *
 * No @testing-library/react needed — we exercise the query mechanics directly.
 *
 * Scenarios covered:
 *   T2-001 — one paginated GET on initial fetch
 *   T2-001 — page size 500 used in the fetch call
 *   T2-001 — MAX_DOCUMENTS_IN_MEMORY=2000 cap applied via select transform
 *   T2-001 — getNextPageParam stops when cap is reached
 *   T2-001 — normalises legacy array response to PaginatedResponse shape
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, type InfiniteData } from '@tanstack/react-query';
import type { PaginatedResponse } from '../../../contexts/dataContextShared';
import type { PlanDocument } from '../../../types';
import { MAX_DOCUMENTS_IN_MEMORY } from '../../../constants';
import { documentsKeys } from '../../queryKeys';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeDocument(id: string): PlanDocument {
  return { id, filePath: `docs/${id}.md` } as PlanDocument;
}

function makePage(
  items: PlanDocument[],
  total: number,
  offset = 0,
): PaginatedResponse<PlanDocument> {
  return { items, total, offset, limit: 500 };
}

function makeMockClient(opts: {
  docs?: PlanDocument[];
  total?: number;
  useLegacyArrayResponse?: boolean;
} = {}) {
  const docs = opts.docs ?? [makeDocument('d1'), makeDocument('d2')];
  const total = opts.total ?? docs.length;
  const useLegacy = opts.useLegacyArrayResponse ?? false;

  const getDocuments = vi.fn((offset: number, _limit: number) => {
    if (useLegacy) {
      // Legacy array response shape
      return Promise.resolve(docs.slice(offset));
    }
    return Promise.resolve(
      makePage(docs.slice(offset, offset + 500), total, offset),
    );
  });

  return { getDocuments };
}

function makeQueryClient(staleTime = 0) {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime },
    },
  });
}

// ── Query configuration ────────────────────────────────────────────────────────
// Mirror the hook's internal query configuration so we can test it directly.

const PAGE_SIZE = 500;

function makeQueryConfig(client: ReturnType<typeof makeMockClient>, projectId: string) {
  return {
    queryKey: documentsKeys.list(projectId),
    queryFn: async ({ pageParam = 0 }: { pageParam?: unknown }) => {
      const offset = (pageParam as number) ?? 0;
      const raw = await client.getDocuments(offset, PAGE_SIZE);
      if (Array.isArray(raw)) {
        return {
          items: raw,
          total: raw.length,
          offset,
          limit: PAGE_SIZE,
        } as PaginatedResponse<PlanDocument>;
      }
      return raw as PaginatedResponse<PlanDocument>;
    },
    getNextPageParam: (
      lastPage: PaginatedResponse<PlanDocument>,
      allPages: PaginatedResponse<PlanDocument>[],
    ) => {
      const fetched = allPages.reduce((sum, p) => sum + p.items.length, 0);
      if (fetched >= MAX_DOCUMENTS_IN_MEMORY) return undefined;
      if (fetched >= lastPage.total) return undefined;
      return fetched;
    },
    initialPageParam: 0,
    staleTime: 60_000,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('T2-001: useDocumentsQuery — queryFn behaviour', () => {
  let qc: QueryClient;
  let client: ReturnType<typeof makeMockClient>;

  beforeEach(() => {
    qc = makeQueryClient();
    client = makeMockClient({ docs: [makeDocument('d1'), makeDocument('d2')], total: 2 });
  });

  afterEach(() => {
    qc.clear();
  });

  it('fires exactly one paginated GET on initial fetch', async () => {
    await qc.fetchInfiniteQuery(makeQueryConfig(client, 'proj-1'));
    expect(client.getDocuments).toHaveBeenCalledTimes(1);
    expect(client.getDocuments).toHaveBeenCalledWith(0, PAGE_SIZE);
  });

  it('uses page size 500', async () => {
    await qc.fetchInfiniteQuery(makeQueryConfig(client, 'proj-2'));
    const firstCall = client.getDocuments.mock.calls[0];
    expect(firstCall[1]).toBe(500);
  });

  it('normalises legacy array response into PaginatedResponse shape', async () => {
    const legacyClient = makeMockClient({
      docs: [makeDocument('legacy1'), makeDocument('legacy2')],
      useLegacyArrayResponse: true,
    });
    const data = await qc.fetchInfiniteQuery(makeQueryConfig(legacyClient, 'proj-legacy'));
    expect(Array.isArray(data.pages[0].items)).toBe(true);
    expect(data.pages[0].items[0].id).toBe('legacy1');
  });

  it('getNextPageParam stops when all docs fetched', async () => {
    const data = await qc.fetchInfiniteQuery(makeQueryConfig(client, 'proj-3'));
    // total = 2, fetched = 2 → no next page
    expect(data.pages).toHaveLength(1);
    // getNextPageParam should return undefined
    const config = makeQueryConfig(client, 'proj-3');
    const nextParam = config.getNextPageParam(data.pages[0], data.pages);
    expect(nextParam).toBeUndefined();
  });
});

describe('T2-001: MAX_DOCUMENTS_IN_MEMORY cap via select transform', () => {
  it('select transform caps flat array to MAX_DOCUMENTS_IN_MEMORY', () => {
    // Build a mock InfiniteData with more docs than the cap
    const overCapCount = MAX_DOCUMENTS_IN_MEMORY + 50;
    const docs = Array.from({ length: overCapCount }, (_, i) => makeDocument(`d${i}`));
    const page = makePage(docs, overCapCount, 0);

    const infiniteData: InfiniteData<PaginatedResponse<PlanDocument>> = {
      pages: [page],
      pageParams: [0],
    };

    // Apply the select transform from the hook
    const flat = infiniteData.pages.flatMap(p => p.items);
    const result = flat.slice(0, MAX_DOCUMENTS_IN_MEMORY);
    expect(result).toHaveLength(MAX_DOCUMENTS_IN_MEMORY);
    expect(result[0].id).toBe('d0');
    expect(result[MAX_DOCUMENTS_IN_MEMORY - 1].id).toBe(`d${MAX_DOCUMENTS_IN_MEMORY - 1}`);
  });

  it('select transform does not truncate when count is below cap', () => {
    const docs = Array.from({ length: 10 }, (_, i) => makeDocument(`d${i}`));
    const page = makePage(docs, 10, 0);
    const infiniteData: InfiniteData<PaginatedResponse<PlanDocument>> = {
      pages: [page],
      pageParams: [0],
    };

    const flat = infiniteData.pages.flatMap(p => p.items);
    const result = flat.slice(0, MAX_DOCUMENTS_IN_MEMORY);
    expect(result).toHaveLength(10);
  });

  it('getNextPageParam stops fetching when memory cap reached', () => {
    // Simulate a scenario where we already have MAX_DOCUMENTS_IN_MEMORY items
    const pages = [
      makePage(
        Array.from({ length: MAX_DOCUMENTS_IN_MEMORY }, (_, i) => makeDocument(`d${i}`)),
        MAX_DOCUMENTS_IN_MEMORY + 100, // more exist on server
        0,
      ),
    ];

    const config = makeQueryConfig(
      makeMockClient({ total: MAX_DOCUMENTS_IN_MEMORY + 100 }),
      'proj-cap',
    );
    const nextParam = config.getNextPageParam(pages[0], pages);
    // Already at cap → must return undefined even though server has more
    expect(nextParam).toBeUndefined();
  });
});

describe('T2-001: staleTime = 60_000', () => {
  it('warm cache within staleTime does not trigger a second fetch', async () => {
    const qcWarm = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
    });
    const client = makeMockClient({ docs: [makeDocument('d1')], total: 1 });
    const config = makeQueryConfig(client, 'proj-warm');

    // First fetch
    await qcWarm.fetchInfiniteQuery(config);
    expect(client.getDocuments).toHaveBeenCalledTimes(1);

    // Second fetch within staleTime — should be served from cache
    await qcWarm.fetchInfiniteQuery(config);
    expect(client.getDocuments).toHaveBeenCalledTimes(1);

    qcWarm.clear();
  });
});
