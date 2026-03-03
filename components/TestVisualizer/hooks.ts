import { useCallback, useEffect, useState } from 'react';

import { DomainHealthRollup, TestRun, TestVisualizerConfig } from '../../types';
import {
  getDomainHealth,
  getTestRun,
  getTestVisualizerConfig,
  listTestRuns,
  TestRunsFilter,
  TestVisualizerApiError,
} from '../../services/testVisualizer';

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
  featureDisabled: boolean;
  refresh: () => void;
}

interface UseTestRunsResult {
  runs: TestRun[];
  isLoading: boolean;
  hasMore: boolean;
  loadMore: () => void;
  refresh: () => void;
  error: Error | null;
  featureDisabled: boolean;
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
  featureDisabled: boolean;
}

interface UseTestVisualizerConfigResult {
  config: TestVisualizerConfig | null;
  isLoading: boolean;
  error: Error | null;
  refresh: () => void;
}

const isFeatureDisabledError = (err: unknown): boolean =>
  err instanceof TestVisualizerApiError && err.isFeatureDisabled;

export function useTestVisualizerConfig(projectId: string, enabled = true): UseTestVisualizerConfigResult {
  const [config, setConfig] = useState<TestVisualizerConfig | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  const refresh = useCallback(() => {
    setRefreshTick(prev => prev + 1);
  }, []);

  useEffect(() => {
    if (!projectId || !enabled) {
      setConfig(null);
      return;
    }
    let alive = true;
    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const payload = await getTestVisualizerConfig(projectId);
        if (!alive) return;
        setConfig(payload);
      } catch (err) {
        if (!alive) return;
        setError(err instanceof Error ? err : new Error('Failed to load test visualizer config'));
      } finally {
        if (alive) setIsLoading(false);
      }
    };
    void load();
    return () => {
      alive = false;
    };
  }, [enabled, projectId, refreshTick]);

  return { config, isLoading, error, refresh };
}

export function useTestStatus(projectId: string, options: UseTestStatusOptions = {}): UseTestStatusResult {
  const pollingInterval = options.pollingInterval ?? 60000;
  const enabled = options.enabled ?? true;

  const [domains, setDomains] = useState<DomainHealthRollup[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [featureDisabled, setFeatureDisabled] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  const refresh = useCallback(() => {
    setFeatureDisabled(false);
    setRefreshTick(prev => prev + 1);
  }, []);

  useEffect(() => {
    if (!projectId || !enabled || featureDisabled) {
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
        setFeatureDisabled(false);
      } catch (err) {
        if (!alive) return;
        if (isFeatureDisabledError(err)) {
          setFeatureDisabled(true);
          setDomains([]);
        }
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
  }, [enabled, featureDisabled, pollingInterval, projectId, options.since, refreshTick]);

  return { domains, isLoading, error, lastFetchedAt, featureDisabled, refresh };
}

export function useTestRuns(
  projectId: string,
  filter: Omit<TestRunsFilter, 'projectId'> = {},
  options: { enabled?: boolean; refreshToken?: number } = {},
): UseTestRunsResult {
  const enabled = options.enabled ?? true;
  const externalRefreshToken = options.refreshToken ?? 0;
  const agentSessionId = filter.agentSessionId;
  const featureId = filter.featureId;
  const domainId = filter.domainId;
  const gitSha = filter.gitSha;
  const since = filter.since;
  const limit = filter.limit;

  const [runs, setRuns] = useState<TestRun[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [featureDisabled, setFeatureDisabled] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  const refresh = useCallback(() => {
    setFeatureDisabled(false);
    setRefreshTick(prev => prev + 1);
  }, []);

  const loadRuns = useCallback(
    async (cursor?: string | null) => {
      if (!projectId || !enabled || featureDisabled) return;

      setIsLoading(true);
      setError(null);
      try {
        const payload = await listTestRuns({
          projectId,
          agentSessionId,
          featureId,
          domainId,
          gitSha,
          since,
          limit,
          cursor: cursor || undefined,
        });
        setRuns(prev => (cursor ? [...prev, ...payload.items] : payload.items));
        setNextCursor(payload.nextCursor);
        setHasMore(Boolean(payload.nextCursor));
        setFeatureDisabled(false);
      } catch (err) {
        if (isFeatureDisabledError(err)) {
          setFeatureDisabled(true);
          setRuns([]);
          setHasMore(false);
        }
        setError(err instanceof Error ? err : new Error('Failed to load test runs'));
      } finally {
        setIsLoading(false);
      }
    },
    [agentSessionId, domainId, enabled, featureDisabled, featureId, gitSha, limit, projectId, since],
  );

  useEffect(() => {
    if (!enabled) {
      setRuns([]);
      setNextCursor(null);
      setHasMore(false);
      setFeatureDisabled(false);
      return;
    }
    setRuns([]);
    setNextCursor(null);
    setHasMore(false);
    setFeatureDisabled(false);
    void loadRuns(null);
  }, [enabled, externalRefreshToken, loadRuns, refreshTick]);

  const loadMore = useCallback(() => {
    if (!nextCursor || isLoading) return;
    loadRuns(nextCursor);
  }, [isLoading, loadRuns, nextCursor]);

  return { runs, isLoading, hasMore, loadMore, refresh, error, featureDisabled };
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
  const [featureDisabled, setFeatureDisabled] = useState(false);

  useEffect(() => {
    if (!projectId || !enabled || featureDisabled) {
      setLatestRun(null);
      return;
    }

    let alive = true;

    const poll = async () => {
      try {
        if (filter.runId) {
          const detail = await getTestRun(filter.runId, projectId, { includeResults: false });
          if (!alive) return;
          setLatestRun(detail?.run ?? null);
          setLastUpdated(new Date());
          setError(null);
          setFeatureDisabled(false);
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
        setFeatureDisabled(false);
      } catch (err) {
        if (!alive) return;
        if (isFeatureDisabledError(err)) {
          setFeatureDisabled(true);
        }
        setError(err instanceof Error ? err : new Error('Failed to poll live test updates'));
      }
    };

    poll();
    const timer = window.setInterval(poll, pollingInterval);

    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [enabled, featureDisabled, filter.featureId, filter.runId, filter.sessionId, pollingInterval, projectId]);

  return {
    latestRun,
    isLive: enabled,
    lastUpdated,
    error,
    featureDisabled,
  };
}

export type {
  UseTestVisualizerConfigResult,
  UseLiveTestUpdatesOptions,
  UseLiveTestUpdatesResult,
  UseTestRunsResult,
  UseTestStatusOptions,
  UseTestStatusResult,
};
