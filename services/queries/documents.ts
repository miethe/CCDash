/**
 * TanStack Query hooks for the documents domain.
 *
 * T2-001: useDocumentsQuery — infinite-scroll list backed by GET /api/documents
 *
 * Page size: 500 (matches existing AppEntityDataContext page size).
 * Memory cap: MAX_DOCUMENTS_IN_MEMORY=2000 applied via TQ `select` transform
 * so the cache holds raw pages but components see only the capped array.
 *
 * The useData().documents facade reads from this hook's TQ cache via a shim
 * in DataContext.tsx so non-migrated consumers continue working unchanged.
 */

import { useInfiniteQuery } from '@tanstack/react-query';
import { useDataClient } from '../../contexts/DataClientContext';
import { MAX_DOCUMENTS_IN_MEMORY, DOCUMENTS_PAGE_SIZE } from '../../constants';
import { documentsKeys } from '../queryKeys';
import type { PlanDocument } from '../../types';
import type { PaginatedResponse } from '../../contexts/dataContextShared';
import type { InfiniteData } from '@tanstack/react-query';

// ── useDocumentsQuery ──────────────────────────────────────────────────────────

export interface UseDocumentsQueryOptions {
  projectId: string | null | undefined;
  /** Set to false to suppress the query (e.g. auth not yet resolved). */
  enabled?: boolean;
}

/**
 * Infinite-scroll query for the document list.
 *
 * Each page is fetched with offset/limit via GET /api/documents.
 * The `select` transform caps the visible flat list to MAX_DOCUMENTS_IN_MEMORY
 * documents while keeping raw pages in cache (needed for correct pagination).
 *
 * Consumers flatten pages with `data?.pages.flatMap(p => p.items) ?? []`,
 * but prefer `useDocuments()` which returns the capped flat array directly.
 */
export function useDocumentsQuery({
  projectId,
  enabled = true,
}: UseDocumentsQueryOptions) {
  const client = useDataClient();

  return useInfiniteQuery({
    queryKey: documentsKeys.list(projectId ?? ''),
    queryFn: async ({ pageParam = 0 }) => {
      const offset = pageParam as number;
      const raw = await client.getDocuments(offset, DOCUMENTS_PAGE_SIZE);
      // Normalise legacy array response to PaginatedResponse shape
      if (Array.isArray(raw)) {
        return {
          items: raw,
          total: raw.length,
          offset,
          limit: DOCUMENTS_PAGE_SIZE,
        } as PaginatedResponse<PlanDocument>;
      }
      return raw as PaginatedResponse<PlanDocument>;
    },
    getNextPageParam: (lastPage, allPages) => {
      const fetched = allPages.reduce((sum, p) => sum + p.items.length, 0);
      // Stop fetching once we hit the memory cap even if more pages exist
      if (fetched >= MAX_DOCUMENTS_IN_MEMORY) return undefined;
      if (fetched >= lastPage.total) return undefined;
      return fetched;
    },
    initialPageParam: 0,
    staleTime: 60_000,
    select: (data: InfiniteData<PaginatedResponse<PlanDocument>>) => {
      // Apply MAX_DOCUMENTS_IN_MEMORY cap via select so the component sees
      // a bounded flat array while raw pages remain in the TQ cache.
      const flat = data.pages.flatMap(p => p.items);
      return flat.slice(0, MAX_DOCUMENTS_IN_MEMORY);
    },
    enabled: !!projectId && enabled,
  });
}
