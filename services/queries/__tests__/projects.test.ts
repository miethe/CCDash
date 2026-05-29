/**
 * Tests for useProjectsQuery (T2-006).
 *
 * Strategy: test queryFn directly through QueryClient.fetchQuery.
 * Verifies project list fetch, testConfig normalisation, and staleTime cache
 * behaviour.
 *
 * Scenarios covered:
 *   T2-006 — getProjects called on initial fetch
 *   T2-006 — returns Project[] with normalised testConfig
 *   T2-006 — staleTime (300s) prevents re-fetch within cache window
 *   T2-006 — invalidateQueries(projectsKeys.list()) marks data stale
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import type { Project } from '../../../types';
import { projectsKeys } from '../../queryKeys';
import { ensureProjectTestConfig } from '../../testConfigDefaults';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeProject(id: string): Project {
  return { id, name: `Project ${id}` } as Project;
}

function makeMockClient(projects: Project[] = [makeProject('p1'), makeProject('p2')]) {
  return {
    getProjects: vi.fn(() => Promise.resolve(projects)),
  };
}

function makeQueryClient(staleTime = 0) {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime } },
  });
}

// Mirror the hook's queryFn (normalises testConfig)
function makeQueryFn(client: ReturnType<typeof makeMockClient>) {
  return async () => {
    const data = await client.getProjects();
    return data.map((project: Project) => ({
      ...project,
      testConfig: ensureProjectTestConfig(project.testConfig),
    }));
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('T2-006: useProjectsQuery — queryFn behaviour', () => {
  let qc: QueryClient;
  let client: ReturnType<typeof makeMockClient>;

  beforeEach(() => {
    qc = makeQueryClient();
    client = makeMockClient([makeProject('p1'), makeProject('p2')]);
  });

  afterEach(() => {
    qc.clear();
  });

  it('fires one GET on initial fetch', async () => {
    await qc.fetchQuery({
      queryKey: projectsKeys.list(),
      queryFn: makeQueryFn(client),
    });
    expect(client.getProjects).toHaveBeenCalledTimes(1);
  });

  it('returns an array of Project items', async () => {
    const result = await qc.fetchQuery({
      queryKey: projectsKeys.list(),
      queryFn: makeQueryFn(client),
    });
    expect(Array.isArray(result)).toBe(true);
    expect(result).toHaveLength(2);
    expect(result[0].id).toBe('p1');
    expect(result[1].id).toBe('p2');
  });

  it('normalises testConfig on each project via ensureProjectTestConfig', async () => {
    const rawProject: Project = { id: 'raw', name: 'Raw' } as Project;
    const rawClient = makeMockClient([rawProject]);

    const result = await qc.fetchQuery({
      queryKey: projectsKeys.list(),
      queryFn: makeQueryFn(rawClient),
    });

    expect(result[0]).toHaveProperty('testConfig');
    // ensureProjectTestConfig always returns a defined object
    expect(result[0].testConfig).toBeDefined();
  });
});

describe('T2-006: useProjectsQuery — staleTime (300s) cache', () => {
  it('second fetch within 300s staleTime returns cached data without a network call', async () => {
    const qcStale = makeQueryClient(300_000);
    const client = makeMockClient([makeProject('p1')]);
    const queryKey = projectsKeys.list();
    const queryFn = makeQueryFn(client);

    await qcStale.fetchQuery({ queryKey, queryFn });
    expect(client.getProjects).toHaveBeenCalledTimes(1);

    await qcStale.fetchQuery({ queryKey, queryFn });
    expect(client.getProjects).toHaveBeenCalledTimes(1);

    qcStale.clear();
  });
});

describe('T2-006: useProjectsQuery — invalidateQueries triggers re-fetch', () => {
  it('invalidateQueries(projectsKeys.list()) marks data stale so next fetch refetches', async () => {
    const qcInvalidate = makeQueryClient(300_000);
    const client = makeMockClient([makeProject('p1')]);
    const queryKey = projectsKeys.list();
    const queryFn = makeQueryFn(client);

    // Prime the cache
    await qcInvalidate.fetchQuery({ queryKey, queryFn });
    expect(client.getProjects).toHaveBeenCalledTimes(1);

    // Invalidate — marks data stale
    await qcInvalidate.invalidateQueries({ queryKey: projectsKeys.list() });

    // Next fetchQuery on stale data triggers a fresh network call
    await qcInvalidate.fetchQuery({ queryKey, queryFn });
    expect(client.getProjects).toHaveBeenCalledTimes(2);

    qcInvalidate.clear();
  });
});
