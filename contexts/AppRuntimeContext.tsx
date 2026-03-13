import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { normalizeRuntimeStatus, type RuntimeStatus } from '../services/runtimeProfile';
import { useDataClient } from './DataClientContext';
import { useAppEntityData } from './AppEntityDataContext';
import { useAppSession } from './AppSessionContext';

interface AppRuntimeContextValue {
  loading: boolean;
  error: string | null;
  runtimeStatus: RuntimeStatus | null;
  refreshAll: () => Promise<void>;
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
        if (!isTestsRoute) {
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
  }, [client, entity, isTestsRoute, session]);

  useEffect(() => {
    refreshAllRef.current = refreshAll;
  }, [refreshAll]);

  useEffect(() => {
    refreshFeaturesRef.current = entity.refreshFeatures;
  }, [entity.refreshFeatures]);

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
    if (isTestsRoute) {
      return undefined;
    }
    const interval = setInterval(() => {
      void refreshFeaturesRef.current();
    }, FEATURE_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isTestsRoute]);

  return (
    <AppRuntimeContext.Provider
      value={{
        loading,
        error,
        runtimeStatus,
        refreshAll,
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
