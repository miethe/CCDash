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
import { MAX_SESSIONS_IN_MEMORY } from '../../constants';

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
      // Stop fetching once we hit the memory cap even if more pages exist
      if (fetched >= MAX_SESSIONS_IN_MEMORY) return undefined;
      if (fetched >= lastPage.total) return undefined;
      return fetched;
    },
    initialPageParam: 0,
    staleTime: 30_000,
    enabled: !!projectId && enabled,
  });
}

// ── useLiveSessionsQuery ───────────────────────────────────────────────────────

/**
 * Page size for the dedicated live slice.
 *
 * Bounded well under MAX_SESSIONS_IN_MEMORY: the live slice is merged on TOP of
 * the paginated list, and including subagents roughly doubles row volume, so it
 * must stay a small fixed budget rather than a second unbounded list.
 */
export const LIVE_SESSIONS_LIMIT = Math.min(200, MAX_SESSIONS_IN_MEMORY);

/** Filters for the live slice — subagents included; they are usually the live work. */
export const LIVE_SESSION_FILTERS: SessionFilters = {
  status: 'active',
  include_subagents: true,
};

export interface UseLiveSessionsQueryOptions {
  projectId: string | null | undefined;
  /** Set to false to suppress the query. */
  enabled?: boolean;
}

/**
 * Single-page query for sessions the server still considers `active`.
 *
 * Why this exists: the paginated list is `started_at desc`, so a long-running
 * orchestrator ages off the loaded window while still running, and live
 * subagents are excluded entirely whenever `include_subagents` is not sent.
 * Neither is visible to a client-side filter over loaded pages.
 *
 * IMPORTANT: `status='active'` is NOT trustworthy on its own — the worker does
 * not reliably close sessions, so the vast majority of `active` rows are stale
 * zombies. Consumers MUST still apply the client-side freshness gate
 * (`isSessionLiveInFlight`, 10-minute window) to these items.
 */
export function useLiveSessionsQuery({
  projectId,
  enabled = true,
}: UseLiveSessionsQueryOptions) {
  const client = useDataClient();

  return useQuery({
    queryKey: sessionsKeys.list(projectId ?? '', {
      scope: 'live',
      ...LIVE_SESSION_FILTERS,
    }),
    queryFn: () => client.getSessions(LIVE_SESSION_FILTERS, {
      offset: 0,
      limit: LIVE_SESSIONS_LIMIT,
    }),
    staleTime: 15_000,
    gcTime: 300_000,
    // Keep the live rail moving without a bespoke ticker. Foreground only so a
    // hidden tab does not poll.
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
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
      // Pass the session's own projectId so the backend receives the correct
      // X-CCDash-Project-Id header for cross-project sessions. Falls back to
      // global scope when projectId is absent (single-project callers).
      return client.getSession(sessionId, projectId ?? undefined);
    },
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && !!sessionId && enabled,
  });
}
