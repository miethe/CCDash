/**
 * TanStack Query hook for the projects domain.
 *
 * T2-006: useProjectsQuery — global project list backed by GET /api/projects
 *
 * Projects are global (not scoped to a single projectId) — the key is
 * projectsKeys.list() with no projectId segment. staleTime: 300_000 since
 * the project list changes infrequently.
 *
 * Ownership boundary:
 *   - useProjectsQuery owns server-state: the list of all projects.
 *   - AppSessionContext continues to own client-state: activeProject and
 *     switchProject remain there unchanged.
 *   - refreshProjects in AppSessionContext should call
 *     queryClient.invalidateQueries({ queryKey: projectsKeys.list() }) to
 *     trigger a TQ-managed refetch rather than calling the API directly.
 *
 * The useData().projects facade reads from this hook's TQ cache via a shim
 * in DataContext.tsx so non-migrated consumers continue working unchanged.
 */

import { useQuery } from '@tanstack/react-query';
import { useDataClient } from '../../contexts/DataClientContext';
import { projectsKeys } from '../queryKeys';
import type { Project } from '../../types';
import { ensureProjectTestConfig } from '../testConfigDefaults';

// ── useProjectsQuery ───────────────────────────────────────────────────────────

export interface UseProjectsQueryOptions {
  /** Set to false to suppress the query (e.g. auth not yet resolved). */
  enabled?: boolean;
}

/**
 * Query for the global project list.
 *
 * Projects change infrequently so staleTime is set to 300 seconds. No
 * refetchInterval is needed — invalidation is triggered explicitly by
 * switchProject / addProject / updateProject flows.
 *
 * Each project's testConfig is normalised via ensureProjectTestConfig to match
 * the convention established in AppSessionContext.
 *
 * Resilience: returns `data: undefined` on first load — consumers must render
 * existing empty-state patterns (`data ?? []`).
 */
export function useProjectsQuery({
  enabled = true,
}: UseProjectsQueryOptions = {}) {
  const client = useDataClient();

  return useQuery<Project[]>({
    queryKey: projectsKeys.list(),
    queryFn: async () => {
      const data = await client.getProjects();
      return data.map(project => ({
        ...project,
        testConfig: ensureProjectTestConfig(project.testConfig),
      }));
    },
    staleTime: 300_000,
    enabled,
  });
}
