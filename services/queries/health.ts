/**
 * TanStack Query hook for the health domain.
 *
 * T4-001: useHealthQuery — polls GET /api/health every 30 seconds.
 *
 * Replaces the setInterval-based `refreshAll()` fan-out that was in
 * AppRuntimeContext. The health payload is normalized via `normalizeRuntimeStatus`
 * and stored in the TQ cache so that `AppRuntimeContext` can derive
 * `runtimeStatus`, `runtimeUnreachable`, and `featureSurfaceV2Active` from it.
 *
 * refetchInterval: 30_000 — TQ manages the interval internally, respecting
 * window visibility and component lifecycle (paused when hidden by default).
 */

import { useQuery } from '@tanstack/react-query';
import { useDataClient } from '../../contexts/DataClientContext';
import { normalizeRuntimeStatus, type RuntimeStatus } from '../runtimeProfile';

// ─── Query key ────────────────────────────────────────────────────────────────

export const healthKeys = {
  all: () => ['health'] as const,
  status: () => ['health', 'status'] as const,
};

// ─── useHealthQuery ───────────────────────────────────────────────────────────

export interface UseHealthQueryOptions {
  /** Set to false to suppress the query (e.g. while retrying after teardown). */
  enabled?: boolean;
}

/**
 * Polls /api/health at a 30-second interval.
 *
 * Returns a normalized `RuntimeStatus` object. Consumers can derive
 * `runtimeUnreachable` from `isError` and `featureSurfaceV2Active` from
 * `data?.featureSurfaceV2Enabled`.
 *
 * Resilience: `data` is undefined until the first successful fetch; consumers
 * must handle null/undefined (existing pattern in AppRuntimeContext).
 */
export function useHealthQuery({ enabled = true }: UseHealthQueryOptions = {}) {
  const client = useDataClient();

  return useQuery<RuntimeStatus>({
    queryKey: healthKeys.status(),
    queryFn: async () => {
      const payload = await client.getHealth();
      return normalizeRuntimeStatus(payload);
    },
    staleTime: 25_000,
    refetchInterval: 30_000,
    retry: 3,
    enabled,
  });
}
