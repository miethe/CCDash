import { useCallback } from 'react';

import { useQuery, useQueryClient } from '@tanstack/react-query';

import { DomainHealthRollup, TestRun, TestVisualizerConfig } from '../../types';
import { projectTestsTopic, useLiveInvalidation } from '../../services/live';
import {
  getDomainHealth,
  getTestRun,
  getTestVisualizerConfig,
  invalidateTestVisualizerProjectCache,
  listTestRuns,
  TestRunsFilter,
  TestVisualizerApiError,
} from '../../services/testVisualizer';

// ─── Query key factory (local to this module) ─────────────────────────────────

const testVisualizerKeys = {
  config: (projectId: string) => [projectId, 'testVisualizer', 'config'] as const,
  domainHealth: (projectId: string, since?: string) =>
    [projectId, 'testVisualizer', 'domainHealth', { since: since ?? null }] as const,
  testRuns: (
    projectId: string,
    filter: Omit<TestRunsFilter, 'projectId'>,
    refreshToken: number,
  ) =>
    [
      projectId,
      'testVisualizer',
      'testRuns',
      {
        agentSessionId: filter.agentSessionId ?? null,
        featureId: filter.featureId ?? null,
        domainId: filter.domainId ?? null,
        gitSha: filter.gitSha ?? null,
        since: filter.since ?? null,
        limit: filter.limit ?? null,
        refreshToken,
      },
    ] as const,
  liveTestUpdates: (
    projectId: string,
    filter: { runId?: string; featureId?: string; sessionId?: string },
  ) =>
    [
      projectId,
      'testVisualizer',
      'liveTestUpdates',
      {
        runId: filter.runId ?? null,
        featureId: filter.featureId ?? null,
        sessionId: filter.sessionId ?? null,
      },
    ] as const,
};

// ─── Shared helpers ───────────────────────────────────────────────────────────

const isFeatureDisabledError = (err: unknown): boolean =>
  err instanceof TestVisualizerApiError && err.isFeatureDisabled;

// ─── Exported interfaces ──────────────────────────────────────────────────────

interface UseTestStatusOptions {
  since?: string;
  pollingInterval?: number;
  enabled?: boolean;
  liveEnabled?: boolean;
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

// ─── useTestVisualizerConfig ──────────────────────────────────────────────────

export function useTestVisualizerConfig(projectId: string, enabled = true): UseTestVisualizerConfigResult {
  const queryClient = useQueryClient();
  const queryKey = testVisualizerKeys.config(projectId);

  const query = useQuery<TestVisualizerConfig | null, Error>({
    queryKey,
    queryFn: () => getTestVisualizerConfig(projectId),
    enabled: Boolean(projectId) && enabled,
    staleTime: 30_000,
  });

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey });
  }, [queryClient, queryKey]);

  return {
    config: query.data ?? null,
    isLoading: query.isLoading,
    error: query.error ?? null,
    refresh,
  };
}

// ─── useTestStatus ────────────────────────────────────────────────────────────

type DomainHealthData = {
  domains: DomainHealthRollup[];
  lastFetchedAt: Date;
};

export function useTestStatus(projectId: string, options: UseTestStatusOptions = {}): UseTestStatusResult {
  const pollingInterval = options.pollingInterval ?? 60_000;
  const enabled = options.enabled ?? true;
  const liveEnabled = Boolean(options.liveEnabled && enabled);

  const queryClient = useQueryClient();
  const queryKey = testVisualizerKeys.domainHealth(projectId, options.since);

  const query = useQuery<DomainHealthData, Error>({
    queryKey,
    queryFn: async () => {
      const payload = await getDomainHealth(projectId, options.since);
      return { domains: payload, lastFetchedAt: new Date() };
    },
    enabled: Boolean(projectId) && enabled,
    staleTime: pollingInterval * 0.9,
    // Visibility-aware: refetchIntervalInBackground defaults to false so polling
    // pauses when the tab is hidden.
    refetchInterval: pollingInterval,
    retry: (_failureCount, err) => !isFeatureDisabledError(err),
  });

  const featureDisabled = isFeatureDisabledError(query.error);

  // Live invalidation: when the live connection fires, invalidate the TQ cache
  // which triggers an immediate refetch (no manual setInterval needed).
  useLiveInvalidation({
    topics: liveEnabled && projectId ? [projectTestsTopic(projectId)] : [],
    enabled: liveEnabled && !featureDisabled,
    pauseWhenHidden: true,
    onInvalidate: () => {
      invalidateTestVisualizerProjectCache(projectId, 'live_invalidation');
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey });
  }, [queryClient, queryKey]);

  return {
    domains: query.data?.domains ?? [],
    isLoading: query.isLoading,
    error: featureDisabled ? null : (query.error ?? null),
    lastFetchedAt: query.data?.lastFetchedAt ?? null,
    featureDisabled,
    refresh,
  };
}

// ─── useTestRuns ──────────────────────────────────────────────────────────────

type TestRunsData = {
  runs: TestRun[];
  nextCursor: string | null;
  hasMore: boolean;
};

export function useTestRuns(
  projectId: string,
  filter: Omit<TestRunsFilter, 'projectId'> = {},
  options: { enabled?: boolean; refreshToken?: number; liveEnabled?: boolean } = {},
): UseTestRunsResult {
  const enabled = options.enabled ?? true;
  const externalRefreshToken = options.refreshToken ?? 0;
  const liveEnabled = Boolean(options.liveEnabled && enabled);

  const queryClient = useQueryClient();
  const queryKey = testVisualizerKeys.testRuns(projectId, filter, externalRefreshToken);

  const query = useQuery<TestRunsData, Error>({
    queryKey,
    queryFn: async () => {
      const payload = await listTestRuns({
        projectId,
        agentSessionId: filter.agentSessionId,
        featureId: filter.featureId,
        domainId: filter.domainId,
        gitSha: filter.gitSha,
        since: filter.since,
        limit: filter.limit,
        cursor: undefined,
      });
      return {
        runs: payload.items,
        nextCursor: payload.nextCursor,
        hasMore: Boolean(payload.nextCursor),
      };
    },
    enabled: Boolean(projectId) && enabled,
    staleTime: 25_000,
    // When live is enabled the live connection drives invalidation; fall back to
    // 30-second polling only when live is disabled (mirrors the original
    // setInterval fallback path).
    // Visibility-aware: refetchIntervalInBackground defaults to false.
    refetchInterval: liveEnabled ? false : 30_000,
    retry: (_failureCount, err) => !isFeatureDisabledError(err),
  });

  const featureDisabled = isFeatureDisabledError(query.error);

  useLiveInvalidation({
    topics: liveEnabled && projectId ? [projectTestsTopic(projectId)] : [],
    enabled: liveEnabled && !featureDisabled,
    pauseWhenHidden: true,
    onInvalidate: () => {
      invalidateTestVisualizerProjectCache(projectId, 'live_invalidation');
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey });
  }, [queryClient, queryKey]);

  // loadMore appends the next cursor page directly into the cached result so
  // consumers get an accumulated list without a full reset.
  const loadMore = useCallback(() => {
    const cached = queryClient.getQueryData<TestRunsData>(queryKey);
    if (!cached?.nextCursor || query.isFetching) return;
    const cursor = cached.nextCursor;
    void (async () => {
      const payload = await listTestRuns({
        projectId,
        agentSessionId: filter.agentSessionId,
        featureId: filter.featureId,
        domainId: filter.domainId,
        gitSha: filter.gitSha,
        since: filter.since,
        limit: filter.limit,
        cursor,
      });
      queryClient.setQueryData<TestRunsData>(queryKey, prev => {
        if (!prev) return prev;
        return {
          ...prev,
          runs: [...prev.runs, ...payload.items],
          nextCursor: payload.nextCursor,
          hasMore: Boolean(payload.nextCursor),
        };
      });
    })();
  }, [
    queryClient,
    queryKey,
    query.isFetching,
    projectId,
    filter.agentSessionId,
    filter.featureId,
    filter.domainId,
    filter.gitSha,
    filter.since,
    filter.limit,
  ]);

  return {
    runs: query.data?.runs ?? [],
    isLoading: query.isLoading,
    hasMore: query.data?.hasMore ?? false,
    loadMore,
    refresh,
    error: featureDisabled ? null : (query.error ?? null),
    featureDisabled,
  };
}

// ─── useLiveTestUpdates ───────────────────────────────────────────────────────

type LiveUpdatesData = {
  latestRun: TestRun | null;
  lastUpdated: Date;
};

export function useLiveTestUpdates(
  projectId: string,
  filter: { runId?: string; featureId?: string; sessionId?: string } = {},
  options: UseLiveTestUpdatesOptions = {},
): UseLiveTestUpdatesResult {
  const pollingInterval = options.pollingInterval ?? 30_000;
  const enabled = options.enabled ?? true;

  const queryClient = useQueryClient();
  const queryKey = testVisualizerKeys.liveTestUpdates(projectId, filter);

  const query = useQuery<LiveUpdatesData, Error>({
    queryKey,
    queryFn: async () => {
      if (filter.runId) {
        const detail = await getTestRun(filter.runId, projectId, { includeResults: false });
        return { latestRun: detail?.run ?? null, lastUpdated: new Date() };
      }
      const payload = await listTestRuns({
        projectId,
        featureId: filter.featureId,
        agentSessionId: filter.sessionId,
        limit: 1,
      });
      return { latestRun: payload.items[0] ?? null, lastUpdated: new Date() };
    },
    enabled: Boolean(projectId) && enabled,
    staleTime: pollingInterval * 0.9,
    // Visibility-aware: refetchIntervalInBackground defaults to false so polling
    // pauses when the tab is hidden.
    refetchInterval: pollingInterval,
    retry: (_failureCount, err) => !isFeatureDisabledError(err),
  });

  const featureDisabled = isFeatureDisabledError(query.error);

  const liveStatus = useLiveInvalidation({
    topics: enabled && projectId ? [projectTestsTopic(projectId)] : [],
    enabled: enabled && !featureDisabled,
    pauseWhenHidden: true,
    onInvalidate: () => {
      invalidateTestVisualizerProjectCache(projectId, 'live_invalidation');
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  return {
    latestRun: query.data?.latestRun ?? null,
    isLive: enabled && !['backoff', 'closed'].includes(liveStatus),
    lastUpdated: query.data?.lastUpdated ?? null,
    error: featureDisabled ? null : (query.error ?? null),
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
