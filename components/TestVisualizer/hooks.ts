import { useCallback, useEffect, useState } from 'react';

import { DomainHealthRollup, TestRun } from '../../types';
import { getDomainHealth, getTestRun, listTestRuns, TestRunsFilter } from '../../services/testVisualizer';

interface UseTestStatusOptions {
  since?: string;
  pollingInterval?: number;
  enabled?: boolean;
}

interface UseTestStatusResult {
  domains: DomainHealthRollup[];
  isLoading: boolean;
  error: Error | null;
  lastFetchedAt: Date | null;
  refresh: () => void;
}

interface UseTestRunsResult {
  runs: TestRun[];
  isLoading: boolean;
  hasMore: boolean;
  loadMore: () => void;
  error: Error | null;
}

interface UseLiveTestUpdatesOptions {
  pollingInterval?: number;
  enabled?: boolean;
}

interface UseLiveTestUpdatesResult {
  latestRun: TestRun | null;
  isLive: boolean;
  lastUpdated: Date | null;
  error: Error | null;
}

export function useTestStatus(projectId: string, options: UseTestStatusOptions = {}): UseTestStatusResult {
  const pollingInterval = options.pollingInterval ?? 60000;
  const enabled = options.enabled ?? true;

  const [domains, setDomains] = useState<DomainHealthRollup[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  const refresh = useCallback(() => {
    setRefreshTick(prev => prev + 1);
  }, []);

  useEffect(() => {
    if (!projectId || !enabled) {
      setDomains([]);
      return;
    }

    let alive = true;

    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const payload = await getDomainHealth(projectId, options.since);
        if (!alive) return;
        setDomains(payload);
        setLastFetchedAt(new Date());
      } catch (err) {
        if (!alive) return;
        setError(err instanceof Error ? err : new Error('Failed to load test status'));
      } finally {
        if (alive) setIsLoading(false);
      }
    };

    load();

    const timer = window.setInterval(load, pollingInterval);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [enabled, pollingInterval, projectId, options.since, refreshTick]);

  return { domains, isLoading, error, lastFetchedAt, refresh };
}

export function useTestRuns(
  projectId: string,
  filter: Omit<TestRunsFilter, 'projectId'> = {},
): UseTestRunsResult {
  const agentSessionId = filter.agentSessionId;
  const featureId = filter.featureId;
  const gitSha = filter.gitSha;
  const since = filter.since;
  const limit = filter.limit;

  const [runs, setRuns] = useState<TestRun[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const loadRuns = useCallback(
    async (cursor?: string | null) => {
      if (!projectId) return;

      setIsLoading(true);
      setError(null);
      try {
        const payload = await listTestRuns({
          projectId,
          agentSessionId,
          featureId,
          gitSha,
          since,
          limit,
          cursor: cursor || undefined,
        });
        setRuns(prev => (cursor ? [...prev, ...payload.items] : payload.items));
        setNextCursor(payload.nextCursor);
        setHasMore(Boolean(payload.nextCursor));
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to load test runs'));
      } finally {
        setIsLoading(false);
      }
    },
    [agentSessionId, featureId, gitSha, limit, projectId, since],
  );

  useEffect(() => {
    setRuns([]);
    setNextCursor(null);
    setHasMore(false);
    void loadRuns(null);
  }, [loadRuns]);

  const loadMore = useCallback(() => {
    if (!nextCursor || isLoading) return;
    loadRuns(nextCursor);
  }, [isLoading, loadRuns, nextCursor]);

  return { runs, isLoading, hasMore, loadMore, error };
}

export function useLiveTestUpdates(
  projectId: string,
  filter: { runId?: string; featureId?: string; sessionId?: string } = {},
  options: UseLiveTestUpdatesOptions = {},
): UseLiveTestUpdatesResult {
  const pollingInterval = options.pollingInterval ?? 30000;
  const enabled = options.enabled ?? true;

  const [latestRun, setLatestRun] = useState<TestRun | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!projectId || !enabled) {
      setLatestRun(null);
      return;
    }

    let alive = true;

    const poll = async () => {
      try {
        if (filter.runId) {
          const detail = await getTestRun(filter.runId, projectId);
          if (!alive) return;
          setLatestRun(detail?.run ?? null);
          setLastUpdated(new Date());
          setError(null);
          return;
        }

        const payload = await listTestRuns({
          projectId,
          featureId: filter.featureId,
          agentSessionId: filter.sessionId,
          limit: 1,
        });

        if (!alive) return;
        setLatestRun(payload.items[0] ?? null);
        setLastUpdated(new Date());
        setError(null);
      } catch (err) {
        if (!alive) return;
        setError(err instanceof Error ? err : new Error('Failed to poll live test updates'));
      }
    };

    poll();
    const timer = window.setInterval(poll, pollingInterval);

    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [enabled, filter.featureId, filter.runId, filter.sessionId, pollingInterval, projectId]);

  return {
    latestRun,
    isLive: enabled,
    lastUpdated,
    error,
  };
}

export type {
  UseLiveTestUpdatesOptions,
  UseLiveTestUpdatesResult,
  UseTestRunsResult,
  UseTestStatusOptions,
  UseTestStatusResult,
};
