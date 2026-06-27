/**
 * TanStack Query hook for the system-wide active-agent count.
 *
 * T4-006-2: replaces the manual setInterval/pollRef loop in SystemMetricsChip.
 *
 * refetchInterval: 30_000 ms — TQ manages the interval internally.
 * refetchIntervalInBackground defaults to false so polling pauses automatically
 * when the tab is hidden (visibility-aware, no manual visibilitychange listener).
 *
 * Resilience contracts (R-P2):
 * - total missing/null  → null (chip renders em-dash)
 * - per_project missing → [] (chip renders "breakdown unavailable")
 * - status missing      → null (no partial badge)
 * - fetch failure       → isError=true; last known total preserved by consumer ref
 */

import { useQuery } from '@tanstack/react-query';
import { apiRequestJson } from '../apiClient';
import type { SystemActiveCount } from '../../types';

/** Polling interval in ms — matches the backend cache TTL (Cache-Control: max-age=30). */
export const SYSTEM_METRICS_POLL_MS = 30_000;

// ─── Query key ────────────────────────────────────────────────────────────────
// System metrics are global (not scoped to a single project).

export const systemMetricsKeys = {
  all: () => ['system-metrics'] as const,
  activeCount: () => ['system-metrics', 'active-count'] as const,
};

// ─── useSystemMetricsQuery ────────────────────────────────────────────────────

export interface UseSystemMetricsQueryOptions {
  /** Set to false to suppress the query (e.g. during testing). */
  enabled?: boolean;
}

/**
 * Polls GET /api/agent/system/active-count every 30 s.
 *
 * Returns the raw TanStack Query result so callers can access `data`,
 * `isLoading`, `isError`, and `dataUpdatedAt` directly.
 *
 * Visibility-aware: refetchIntervalInBackground is left at the TQ default
 * (false) so the interval is automatically paused when the tab is hidden.
 */
export function useSystemMetricsQuery(
  { enabled = true }: UseSystemMetricsQueryOptions = {},
) {
  return useQuery<SystemActiveCount>({
    queryKey: systemMetricsKeys.activeCount(),
    queryFn: () => apiRequestJson<SystemActiveCount>('/api/agent/system/active-count'),
    staleTime: SYSTEM_METRICS_POLL_MS - 5_000, // keep fresh across refetches
    refetchInterval: SYSTEM_METRICS_POLL_MS,
    // refetchIntervalInBackground: default false — pauses when tab is hidden
    retry: 2,
    enabled,
  });
}
