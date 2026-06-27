/**
 * TanStack Query hook for the alerts domain.
 *
 * T2-005: useAlertsQuery — list backed by GET /api/analytics/alerts
 *
 * Polling: refetchInterval: 30_000 ports the 30s interval previously driven
 * by AppRuntimeContext.tsx setInterval (POLL_INTERVAL_MS = 30_000). TQ handles
 * the interval internally, respecting window visibility and component lifecycle.
 *
 * The useData().alerts facade reads from this hook's TQ cache via a shim in
 * DataContext.tsx so non-migrated consumers continue working unchanged.
 */

import { useQuery } from '@tanstack/react-query';
import { useDataClient } from '../../contexts/DataClientContext';
import { alertsKeys } from '../queryKeys';
import type { AlertConfig } from '../../types';

// ── useAlertsQuery ─────────────────────────────────────────────────────────────

export interface UseAlertsQueryOptions {
  projectId: string | null | undefined;
  /** Set to false to suppress the query (e.g. auth not yet resolved). */
  enabled?: boolean;
}

/**
 * Query for the alert configuration list.
 *
 * Refetches every 30 seconds to keep alert state current. The interval is
 * paused automatically when the window is hidden (TQ default).
 *
 * Resilience: returns `data: undefined` on first load — consumers must render
 * existing empty-state patterns (`data ?? []`).
 */
export function useAlertsQuery({
  projectId,
  enabled = true,
}: UseAlertsQueryOptions) {
  const client = useDataClient();

  return useQuery<AlertConfig[]>({
    queryKey: alertsKeys.list(projectId ?? ''),
    queryFn: () => client.getAlerts(),
    staleTime: 30_000,
    refetchInterval: 30_000,
    enabled: !!projectId && enabled,
  });
}
