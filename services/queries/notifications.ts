/**
 * TanStack Query hook for the notifications domain.
 *
 * T2-005: useNotificationsQuery — list backed by GET /api/analytics/notifications
 *
 * Polling: refetchInterval: 30_000 ports the 30s interval previously driven
 * by AppRuntimeContext.tsx setInterval (POLL_INTERVAL_MS = 30_000). TQ handles
 * the interval internally, respecting window visibility and component lifecycle.
 *
 * The useData().notifications facade reads from this hook's TQ cache via a shim
 * in DataContext.tsx so non-migrated consumers continue working unchanged.
 */

import { useQuery } from '@tanstack/react-query';
import { useDataClient } from '../../contexts/DataClientContext';
import { notificationsKeys } from '../queryKeys';
import type { Notification } from '../../types';

// ── useNotificationsQuery ──────────────────────────────────────────────────────

export interface UseNotificationsQueryOptions {
  projectId: string | null | undefined;
  /** Set to false to suppress the query (e.g. auth not yet resolved). */
  enabled?: boolean;
}

/**
 * Query for the notification list.
 *
 * Refetches every 30 seconds to surface new notifications promptly. The
 * interval is paused automatically when the window is hidden (TQ default).
 *
 * Resilience: returns `data: undefined` on first load — consumers must render
 * existing empty-state patterns (`data ?? []`).
 */
export function useNotificationsQuery({
  projectId,
  enabled = true,
}: UseNotificationsQueryOptions) {
  const client = useDataClient();

  return useQuery<Notification[]>({
    queryKey: notificationsKeys.list(projectId ?? ''),
    queryFn: () => client.getNotifications(),
    staleTime: 30_000,
    refetchInterval: 30_000,
    enabled: !!projectId && enabled,
  });
}
