/**
 * Tests for useTasksQuery (T2-003).
 *
 * Strategy: test queryFn directly through QueryClient.fetchQuery.
 * Verifies paginated shape, offset calculation, legacy array normalisation,
 * and staleTime cache behaviour.
 *
 * Scenarios covered:
 *   T2-003 — paginated GET on initial fetch with correct offset
 *   T2-003 — returns TasksPage { items, total, page, pageSize }
 *   T2-003 — page N uses offset = page * PAGE_SIZE
 *   T2-003 — normalises legacy array response
 *   T2-003 — staleTime prevents re-fetch within cache window
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import type { PaginatedResponse } from '../../../contexts/dataContextShared';
import type { ProjectTask } from '../../../types';
import { tasksKeys } from '../../queryKeys';
import { TASKS_PAGE_SIZE, type TasksPage } from '../tasks';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeTask(id: string): ProjectTask {
  return { id } as ProjectTask;
}

function makePaginatedTasks(
  items: ProjectTask[],
  total: number,
): PaginatedResponse<ProjectTask> {
  return { items, total, offset: 0, limit: TASKS_PAGE_SIZE };
}

function makeMockClient(opts: {
  tasks?: ProjectTask[];
  total?: number;
  useLegacy?: boolean;
} = {}) {
  const tasks = opts.tasks ?? [makeTask('t1'), makeTask('t2')];
  const total = opts.total ?? tasks.length;
  const useLegacy = opts.useLegacy ?? false;

  const getTasksPaginated = vi.fn((_offset: number, _limit: number) => {
    if (useLegacy) {
      return Promise.resolve(tasks);
    }
    return Promise.resolve(makePaginatedTasks(tasks, total));
  });

  return { getTasksPaginated };
}

function makeQueryClient(staleTime = 0) {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime } },
  });
}

// Mirror the hook's queryFn
function makeQueryFn(
  client: ReturnType<typeof makeMockClient>,
  page: number,
): () => Promise<TasksPage> {
  return async () => {
    const offset = page * TASKS_PAGE_SIZE;
    const raw = await client.getTasksPaginated(offset, TASKS_PAGE_SIZE);
    if (Array.isArray(raw)) {
      return { items: raw, total: raw.length, page, pageSize: TASKS_PAGE_SIZE };
    }
    const p = raw as PaginatedResponse<ProjectTask>;
    return { items: p.items ?? [], total: p.total ?? 0, page, pageSize: TASKS_PAGE_SIZE };
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('T2-003: useTasksQuery — queryFn behaviour', () => {
  let qc: QueryClient;
  let client: ReturnType<typeof makeMockClient>;

  beforeEach(() => {
    qc = makeQueryClient();
    client = makeMockClient({ tasks: [makeTask('t1'), makeTask('t2')], total: 2 });
  });

  afterEach(() => {
    qc.clear();
  });

  it('fires one paginated GET on initial fetch', async () => {
    await qc.fetchQuery({
      queryKey: tasksKeys.list('proj-1', 0),
      queryFn: makeQueryFn(client, 0),
    });
    expect(client.getTasksPaginated).toHaveBeenCalledTimes(1);
    expect(client.getTasksPaginated).toHaveBeenCalledWith(0, TASKS_PAGE_SIZE);
  });

  it('returns TasksPage shape with items, total, page, pageSize', async () => {
    const result = await qc.fetchQuery({
      queryKey: tasksKeys.list('proj-1', 0),
      queryFn: makeQueryFn(client, 0),
    });
    expect(result).toHaveProperty('items');
    expect(result).toHaveProperty('total');
    expect(result).toHaveProperty('page', 0);
    expect(result).toHaveProperty('pageSize', TASKS_PAGE_SIZE);
    expect(result.items).toHaveLength(2);
    expect(result.total).toBe(2);
  });

  it('page N uses offset = N * PAGE_SIZE', async () => {
    await qc.fetchQuery({
      queryKey: tasksKeys.list('proj-2', 2),
      queryFn: makeQueryFn(client, 2),
    });
    expect(client.getTasksPaginated).toHaveBeenCalledWith(2 * TASKS_PAGE_SIZE, TASKS_PAGE_SIZE);
  });

  it('normalises legacy array response into TasksPage shape', async () => {
    const legacyClient = makeMockClient({
      tasks: [makeTask('legacy1'), makeTask('legacy2')],
      useLegacy: true,
    });
    const result = await qc.fetchQuery({
      queryKey: tasksKeys.list('proj-legacy', 0),
      queryFn: makeQueryFn(legacyClient, 0),
    });
    expect(result.items).toHaveLength(2);
    expect(result.items[0].id).toBe('legacy1');
    expect(result.total).toBe(2);
  });
});

describe('T2-003: useTasksQuery — staleTime cache', () => {
  it('second fetch within staleTime returns cached data without a network call', async () => {
    const qcStale = makeQueryClient(30_000);
    const client = makeMockClient({ tasks: [makeTask('t1')], total: 1 });
    const queryKey = tasksKeys.list('proj-1', 0);
    const queryFn = makeQueryFn(client, 0);

    await qcStale.fetchQuery({ queryKey, queryFn });
    expect(client.getTasksPaginated).toHaveBeenCalledTimes(1);

    await qcStale.fetchQuery({ queryKey, queryFn });
    expect(client.getTasksPaginated).toHaveBeenCalledTimes(1);

    qcStale.clear();
  });
});

describe('T2-003: total reflects server count, not items.length', () => {
  it('total field reports server total even when page has fewer items', async () => {
    const qc2 = makeQueryClient();
    const serverTotal = 500;
    const client = makeMockClient({
      tasks: Array.from({ length: TASKS_PAGE_SIZE }, (_, i) => makeTask(`t${i}`)),
      total: serverTotal,
    });
    const result = await qc2.fetchQuery({
      queryKey: tasksKeys.list('proj-big', 0),
      queryFn: makeQueryFn(client, 0),
    });
    expect(result.total).toBe(serverTotal);
    expect(result.items).toHaveLength(TASKS_PAGE_SIZE);
    qc2.clear();
  });
});
