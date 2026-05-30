/**
 * TanStack Query hooks for the tasks domain.
 *
 * T2-003: useTasksQuery — offset-paginated list backed by GET /api/tasks
 *
 * Page size: 100 (replaces the removed unbounded 5000-item fetch on getTasks).
 * Paginated shape: { items: ProjectTask[], total, page, pageSize }
 *
 * The useData().tasks facade reads from this hook's TQ cache via a shim
 * in DataContext.tsx so non-migrated consumers continue working unchanged.
 */

import { useQuery } from '@tanstack/react-query';
import { useDataClient } from '../../contexts/DataClientContext';
import { tasksKeys } from '../queryKeys';
import type { ProjectTask } from '../../types';
import type { PaginatedResponse } from '../../contexts/dataContextShared';

export const TASKS_PAGE_SIZE = 100;

// ── Paginated shape ────────────────────────────────────────────────────────────

export interface TasksPage {
  items: ProjectTask[];
  total: number;
  page: number;
  pageSize: number;
}

// ── useTasksQuery ──────────────────────────────────────────────────────────────

export interface UseTasksQueryOptions {
  projectId: string | null | undefined;
  page?: number;
  /** Set to false to suppress the query (e.g. auth not yet resolved). */
  enabled?: boolean;
}

/**
 * Offset-paginated query for the task list.
 *
 * Returns `{ items, total, page, pageSize }`. Consumers read `items` for list
 * render and `total` for counts — not the raw array length.
 *
 * OpsPanel uses page=0 to get the first page; `total` from the response is
 * used for count display so the number reflects all tasks, not just page 0.
 */
export function useTasksQuery({
  projectId,
  page = 0,
  enabled = true,
}: UseTasksQueryOptions) {
  const client = useDataClient();

  return useQuery<TasksPage>({
    queryKey: tasksKeys.list(projectId ?? '', page),
    queryFn: async (): Promise<TasksPage> => {
      const offset = page * TASKS_PAGE_SIZE;
      const raw = await client.getTasksPaginated(offset, TASKS_PAGE_SIZE);
      if (Array.isArray(raw)) {
        return {
          items: raw,
          total: raw.length,
          page,
          pageSize: TASKS_PAGE_SIZE,
        };
      }
      const paginated = raw as PaginatedResponse<ProjectTask>;
      return {
        items: paginated.items ?? [],
        total: paginated.total ?? 0,
        page,
        pageSize: TASKS_PAGE_SIZE,
      };
    },
    staleTime: 30_000,
    enabled: !!projectId && enabled,
  });
}
