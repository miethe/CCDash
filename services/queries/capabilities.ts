/**
 * P5-001: TanStack Query hook for runtime launch capabilities.
 *
 * Wraps getLaunchCapabilities() (services/execution.ts) with a 60-second
 * staleTime so capability flags are refreshed periodically without hammering
 * the endpoint on every component mount.
 *
 * The hook is NOT project-scoped — capabilities are global.  The
 * capabilitiesKeys.launch() key is used for stable cache identity.
 *
 * Usage:
 *   const { data: caps } = useLaunchCapabilitiesQuery();
 *   const enabled = caps?.multiProjectCommandCenterEnabled
 *     ?? MULTI_PROJECT_COMMAND_CENTER_ENABLED_DEFAULT;
 */

import { useQuery } from '@tanstack/react-query';
import { getLaunchCapabilities, type LaunchCapabilities } from '../execution';
import { capabilitiesKeys } from '../queryKeys';

export interface UseLaunchCapabilitiesQueryOptions {
  /** Set false to suppress the query (e.g. during SSR or test isolation). */
  enabled?: boolean;
}

/**
 * Global runtime capability flags from GET /api/execution/launch/capabilities.
 *
 * staleTime: 60_000 — flags change infrequently; 60 s soft-TTL is enough to
 * pick up deployments without over-fetching on every component mount.
 *
 * gcTime: 300_000 — keep the cache warm for 5 minutes after the last subscriber
 * unmounts so that navigating away and back does not issue a cold fetch.
 *
 * Returns undefined while loading so callers can apply the DEFAULT fallback:
 *   caps?.multiProjectCommandCenterEnabled ?? MULTI_PROJECT_COMMAND_CENTER_ENABLED_DEFAULT
 */
export function useLaunchCapabilitiesQuery({
  enabled = true,
}: UseLaunchCapabilitiesQueryOptions = {}) {
  return useQuery<LaunchCapabilities>({
    queryKey: capabilitiesKeys.launch(),
    queryFn: getLaunchCapabilities,
    staleTime: 60_000,
    gcTime: 300_000,
    enabled,
  });
}
