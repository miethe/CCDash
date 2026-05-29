/**
 * TanStack Query hooks for the sessions domain.
 *
 * T1-001: useSessionsQuery — infinite-scroll list backed by GET /api/sessions
 * T1-002: useSessionDetailQuery — single-session detail backed by GET /api/sessions/:id
 *
 * Both hooks are consumed directly by migrated components. The useData() facade
 * continues to expose sessions via a thin shim that reads from the TQ cache so
 * that non-migrated consumers are unaffected.
 */

import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useDataClient } from '../../contexts/DataClientContext';
import type { SessionFilters } from '../../contexts/dataContextShared';
import { sessionsKeys } from '../queryKeys';

const SESSIONS_PAGE_SIZE = 50;

// ── useSessionsQuery ───────────────────────────────────────────────────────────

export interface UseSessionsQueryOptions {
  projectId: string | null | undefined;
  filters?: SessionFilters;
  /** Set to false to suppress the query (e.g. auth not yet resolved). */
  enabled?: boolean;
}

/**
 * Infinite-scroll query for the session list.
 *
 * Each page is a `PaginatedResponse<AgentSession>` slice. Consumers flatten
 * pages with `data?.pages.flatMap(p => p.items) ?? []`.
 */
export function useSessionsQuery({
  projectId,
  filters,
  enabled = true,
}: UseSessionsQueryOptions) {
  const client = useDataClient();

  return useInfiniteQuery({
    queryKey: sessionsKeys.list(projectId ?? '', filters as Record<string, unknown> | undefined),
    queryFn: async ({ pageParam = 0 }) => {
      return client.getSessions(filters ?? {}, {
        offset: pageParam as number,
        limit: SESSIONS_PAGE_SIZE,
      });
    },
    getNextPageParam: (lastPage, allPages) => {
      const fetched = allPages.reduce((sum, p) => sum + p.items.length, 0);
      if (fetched >= lastPage.total) return undefined;
      return fetched;
    },
    initialPageParam: 0,
    staleTime: 30_000,
    enabled: !!projectId && enabled,
  });
}

// ── useSessionDetailQuery ──────────────────────────────────────────────────────

export interface UseSessionDetailQueryOptions {
  sessionId: string | null | undefined;
  projectId: string | null | undefined;
  /** Set to false to suppress the query. */
  enabled?: boolean;
}

/**
 * Single-session detail query.
 *
 * Replaces the bespoke `sessionDetailRequestsRef` / `sessionDetailTimestampsRef`
 * Map+TTL dedup pattern that was removed from AppEntityDataContext. TanStack
 * Query deduplicates concurrent calls automatically within the staleTime window.
 */
export function useSessionDetailQuery({
  sessionId,
  projectId,
  enabled = true,
}: UseSessionDetailQueryOptions) {
  const client = useDataClient();

  return useQuery({
    queryKey: sessionsKeys.detail(projectId ?? '', sessionId ?? ''),
    queryFn: () => {
      if (!sessionId) throw new Error('sessionId is required');
      return client.getSession(sessionId);
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && !!sessionId && enabled,
  });
}
