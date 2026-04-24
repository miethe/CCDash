import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
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
  const hasLoadedOnceRef = useRef(false);
  const refreshAllInFlightRef = useRef<Promise<void> | null>(null);
  const refreshAllRef = useRef<() => Promise<void>>(async () => undefined);
  const refreshFeaturesRef = useRef(entity.refreshFeatures);

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
          client.getHealth().then(payload => setRuntimeStatus(normalizeRuntimeStatus(payload))),
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
  }, [client, entity, featureSurfaceV2Active, isTestsRoute, session]);

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

  useEffect(() => {
    const interval = setInterval(() => {
      void refreshAllRef.current();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

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
    const interval = setInterval(() => {
      void refreshFeaturesRef.current();
    }, FEATURE_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [featureLiveEnabled, featureLiveStatus, featureSurfaceV2Active, isTestsRoute]);

  return (
    <AppRuntimeContext.Provider
      value={{
        loading,
        error,
        runtimeStatus,
        refreshAll,
        featureSurfaceV2Active,
      }}
    >
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
