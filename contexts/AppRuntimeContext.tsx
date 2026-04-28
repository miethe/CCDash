import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { normalizeRuntimeStatus, type RuntimeStatus } from '../services/runtimeProfile';
import {
  isFeatureLiveUpdatesEnabled,
  projectFeaturesTopic,
  useLiveInvalidation,
} from '../services/live';
import { isFeatureSurfaceV2Enabled } from '../services/featureSurfaceFlag';
import { useDataClient } from './DataClientContext';
import { useAppEntityData } from './AppEntityDataContext';
import { useAppSession } from './AppSessionContext';
import { stopLiveConnection } from '../services/live/connectionManager';
import { isMemoryGuardEnabled } from '../lib/featureFlags';

const CONSECUTIVE_FAILURE_THRESHOLD = 3;

interface AppRuntimeContextValue {
  loading: boolean;
  error: string | null;
  runtimeStatus: RuntimeStatus | null;
  refreshAll: () => Promise<void>;
  /**
   * G1-001: Whether the v2 feature surface is active.
   * When true, AppRuntimeContext skips the global feature refresh polling cycle
   * (refreshFeatures / 30s + 5s) so ProjectBoard's useFeatureSurface can own its
   * own surface cache independently.  Legacy consumers (SessionInspector, Dashboard)
   * that read features from AppEntityDataContext continue to receive updates via
   * refreshAll() when they call it explicitly.
   */
  featureSurfaceV2Active: boolean;
  /** FE-104: True after N=3 consecutive backend-unreachable health checks. */
  runtimeUnreachable: boolean;
  /** FE-104: Re-enable polling and reconnect EventSource after teardown. */
  retryRuntime: () => void;
}

const POLL_INTERVAL_MS = 30_000;
const FEATURE_POLL_INTERVAL_MS = 5_000;

const AppRuntimeContext = createContext<AppRuntimeContextValue | null>(null);

const isTestsHashRoute = (): boolean => (
  typeof window !== 'undefined' && window.location.hash.startsWith('#/tests')
);

export const AppRuntimeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const client = useDataClient();
  const session = useAppSession();
  const entity = useAppEntityData();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [isTestsRoute, setIsTestsRoute] = useState<boolean>(isTestsHashRoute);
  const [runtimeUnreachable, setRuntimeUnreachable] = useState(false);
  const hasLoadedOnceRef = useRef(false);
  const refreshAllInFlightRef = useRef<Promise<void> | null>(null);
  const refreshAllRef = useRef<() => Promise<void>>(async () => undefined);
  const refreshFeaturesRef = useRef(entity.refreshFeatures);
  // FE-104: consecutive failure counter for the health-check path
  const consecutiveFailuresRef = useRef(0);
  // FE-104: refs to the two poll intervals so teardown can clear them
  const healthPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const featurePollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // FE-104: flag to gate whether polling is currently active
  const pollingActiveRef = useRef(true);

  // G1-001: Derive v2 flag from current runtimeStatus.  When v2 is active the
  // global feature polling cycle is suppressed — ProjectBoard manages its own
  // surface cache via useFeatureSurface + useLiveInvalidation.
  // refreshFeatures() itself remains available on AppEntityDataContext for any
  // legacy consumer (SessionInspector, Dashboard) that calls it explicitly.
  const featureSurfaceV2Active = isFeatureSurfaceV2Enabled(runtimeStatus);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onHashChange = () => setIsTestsRoute(isTestsHashRoute());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  /** OBS-402: sessionStorage key used to accumulate teardown events across
   *  backend-unreachable periods.  Flushed as a beacon on next successful
   *  reconnect via POST /api/observability/poll-teardown. */
  const TEARDOWN_BEACON_KEY = 'ccdash.pendingTeardownEvents';

  /** OBS-402: Persist one more teardown event in sessionStorage so it can be
   *  beaconed on the next successful reconnect. */
  const recordTeardownToStorage = useCallback(() => {
    try {
      const raw = sessionStorage.getItem(TEARDOWN_BEACON_KEY);
      const current = parseInt(raw ?? '0', 10) || 0;
      // Cap at 100 to match the backend's clamp contract.
      const next = Math.min(current + 1, 100);
      sessionStorage.setItem(TEARDOWN_BEACON_KEY, String(next));
    } catch {
      // sessionStorage may be unavailable in some environments — swallow silently.
    }
  }, []);

  /** FE-104: Tear down both poll intervals and the live EventSource. */
  const teardownPolling = useCallback(() => {
    if (healthPollRef.current !== null) {
      clearInterval(healthPollRef.current);
      healthPollRef.current = null;
    }
    if (featurePollRef.current !== null) {
      clearInterval(featurePollRef.current);
      featurePollRef.current = null;
    }
    stopLiveConnection();
    pollingActiveRef.current = false;
    // OBS-402: Persist the teardown event so it can be beaconed on reconnect.
    recordTeardownToStorage();
    setRuntimeUnreachable(true);
  }, [recordTeardownToStorage]);

  const refreshAll = useCallback(async () => {
    if (refreshAllInFlightRef.current) {
      return refreshAllInFlightRef.current;
    }
    const isInitialLoad = !hasLoadedOnceRef.current;
    if (isInitialLoad) {
      setLoading(true);
    }
    setError(null);

    const task = (async () => {
      try {
        const tasksToRun: Promise<unknown>[] = [
          entity.refreshSessions(),
          entity.refreshDocuments(),
          entity.refreshTasks(),
          entity.refreshAlerts(),
          entity.refreshNotifications(),
          session.refreshProjects(),
          client.getHealth().then(payload => {
            // FE-104: successful health response resets the failure counter
            consecutiveFailuresRef.current = 0;
            setRuntimeStatus(normalizeRuntimeStatus(payload));
            // OBS-402: Flush any accumulated teardown beacon on successful
            // reconnect.  Fire-and-forget; errors are swallowed so a beacon
            // failure never disrupts the UI reconnect flow.
            try {
              const raw = sessionStorage.getItem('ccdash.pendingTeardownEvents');
              const events = parseInt(raw ?? '0', 10) || 0;
              if (events > 0) {
                sessionStorage.removeItem('ccdash.pendingTeardownEvents');
                fetch('/api/observability/poll-teardown', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ events }),
                }).catch(() => { /* beacon best-effort only */ });
              }
            } catch {
              // sessionStorage unavailable — skip beacon silently.
            }
          }),
        ];
        // G1-001: Skip legacy feature refresh when v2 surface is active.
        // ProjectBoard drives its own surface cache; legacy consumers still get
        // feature data from refreshAll when explicitly triggered.
        if (!isTestsRoute && !featureSurfaceV2Active) {
          tasksToRun.push(entity.refreshFeatures());
        }
        await Promise.all(tasksToRun);
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : 'Failed to load data';
        setError(message);
        // FE-104 / FE-106: only count failures and trigger teardown when memory guard is enabled.
        // When disabled → polling continues indefinitely (original behavior); banner never shows.
        if (isMemoryGuardEnabled()) {
          consecutiveFailuresRef.current += 1;
          if (consecutiveFailuresRef.current >= CONSECUTIVE_FAILURE_THRESHOLD) {
            teardownPolling();
          }
        }
      } finally {
        if (isInitialLoad) {
          setLoading(false);
          hasLoadedOnceRef.current = true;
        }
      }
    })();

    refreshAllInFlightRef.current = task;
    try {
      await task;
    } finally {
      if (refreshAllInFlightRef.current === task) {
        refreshAllInFlightRef.current = null;
      }
    }
  }, [client, entity, featureSurfaceV2Active, isTestsRoute, session, teardownPolling]);

  useEffect(() => {
    refreshAllRef.current = refreshAll;
  }, [refreshAll]);

  useEffect(() => {
    refreshFeaturesRef.current = entity.refreshFeatures;
  }, [entity.refreshFeatures]);

  // G1-001: When v2 surface is active, disable the global feature live
  // subscription here — ProjectBoard subscribes to feature topics independently
  // via its own useLiveInvalidation → useFeatureSurface.invalidate() chain.
  const featureLiveEnabled = Boolean(
    !isTestsRoute
    && !featureSurfaceV2Active
    && session.activeProject?.id
    && isFeatureLiveUpdatesEnabled(),
  );
  const featureLiveStatus = useLiveInvalidation({
    topics: featureLiveEnabled && session.activeProject?.id ? [projectFeaturesTopic(session.activeProject.id)] : [],
    enabled: featureLiveEnabled,
    pauseWhenHidden: true,
    onInvalidate: () => refreshFeaturesRef.current(),
  });

  useEffect(() => {
    void refreshAllRef.current();
  }, []);

  // FE-104: Health poll — store interval ref so teardown can clear it
  useEffect(() => {
    const id = setInterval(() => {
      if (!pollingActiveRef.current) return;
      void refreshAllRef.current();
    }, POLL_INTERVAL_MS);
    healthPollRef.current = id;
    return () => {
      clearInterval(id);
      if (healthPollRef.current === id) {
        healthPollRef.current = null;
      }
    };
  }, []);

  // FE-104: Feature poll — store interval ref so teardown can clear it
  useEffect(() => {
    // G1-001: When v2 surface is active, skip the legacy 5s feature polling
    // fallback.  ProjectBoard handles invalidation via useLiveInvalidation wired
    // directly into its useFeatureSurface hook (G1-002).
    if (isTestsRoute || featureSurfaceV2Active) {
      return undefined;
    }
    if (featureLiveEnabled && !['backoff', 'closed'].includes(featureLiveStatus)) {
      return undefined;
    }
    const id = setInterval(() => {
      if (!pollingActiveRef.current) return;
      void refreshFeaturesRef.current();
    }, FEATURE_POLL_INTERVAL_MS);
    featurePollRef.current = id;
    return () => {
      clearInterval(id);
      if (featurePollRef.current === id) {
        featurePollRef.current = null;
      }
    };
  }, [featureLiveEnabled, featureLiveStatus, featureSurfaceV2Active, isTestsRoute]);

  /** FE-104: Re-enable polling and reconnect after the backend comes back. */
  const retryRuntime = useCallback(() => {
    consecutiveFailuresRef.current = 0;
    pollingActiveRef.current = true;
    setRuntimeUnreachable(false);
    void refreshAllRef.current();
  }, []);

  const contextValue = useMemo(() => ({
    loading,
    error,
    runtimeStatus,
    refreshAll,
    featureSurfaceV2Active,
    runtimeUnreachable,
    retryRuntime,
  }), [loading, error, runtimeStatus, refreshAll, featureSurfaceV2Active, runtimeUnreachable, retryRuntime]);

  return (
    <AppRuntimeContext.Provider value={contextValue}>
      {children}
    </AppRuntimeContext.Provider>
  );
};

export function useAppRuntime(): AppRuntimeContextValue {
  const ctx = useContext(AppRuntimeContext);
  if (!ctx) {
    throw new Error('useAppRuntime must be used within an AppRuntimeProvider');
  }
  return ctx;
}
