// AppRuntimeContext — client-state-only runtime shell (T4-001/002/006).
// useHealthQuery owns polling (30 s refetchInterval). No setInterval. No domain fetches.

import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import type { RuntimeStatus } from '../services/runtimeProfile';
import { isFeatureSurfaceV2Enabled } from '../services/featureSurfaceFlag';
import { useHealthQuery } from '../services/queries/health';
import { stopLiveConnection } from '../services/live/connectionManager';
import { isMemoryGuardEnabled } from '../lib/featureFlags';

const CONSECUTIVE_FAILURE_THRESHOLD = 3;
const TEARDOWN_BEACON_KEY = 'ccdash.pendingTeardownEvents';

interface AppRuntimeContextValue {
  loading: boolean;
  error: string | null;
  runtimeStatus: RuntimeStatus | null;
  featureSurfaceV2Active: boolean;
  runtimeUnreachable: boolean;
  retryRuntime: () => void;
  /** @deprecated No-op shim kept for DataContext compatibility (switchProject). */
  refreshAll: () => Promise<void>;
}

const AppRuntimeContext = createContext<AppRuntimeContextValue | null>(null);

export const AppRuntimeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [runtimeUnreachable, setRuntimeUnreachable] = useState(false);
  const consecutiveFailuresRef = useRef(0);
  const prevIsErrorRef = useRef(false);

  const healthQuery = useHealthQuery({ enabled: !runtimeUnreachable });
  const runtimeStatus = healthQuery.data ?? null;

  // FE-104: consecutive failure → tear down after N=3; flush OBS-402 beacon on reconnect.
  if (healthQuery.isError && !prevIsErrorRef.current) {
    prevIsErrorRef.current = true;
    if (isMemoryGuardEnabled()) {
      consecutiveFailuresRef.current += 1;
      if (consecutiveFailuresRef.current >= CONSECUTIVE_FAILURE_THRESHOLD) {
        try {
          const cur = parseInt(sessionStorage.getItem(TEARDOWN_BEACON_KEY) ?? '0', 10) || 0;
          sessionStorage.setItem(TEARDOWN_BEACON_KEY, String(Math.min(cur + 1, 100)));
        } catch { /* swallow */ }
        stopLiveConnection();
        setRuntimeUnreachable(true);
      }
    }
  } else if (!healthQuery.isError && prevIsErrorRef.current) {
    prevIsErrorRef.current = false;
    consecutiveFailuresRef.current = 0;
    try { // OBS-402: flush beacon on reconnect
      const events = parseInt(sessionStorage.getItem(TEARDOWN_BEACON_KEY) ?? '0', 10) || 0;
      if (events > 0) {
        sessionStorage.removeItem(TEARDOWN_BEACON_KEY);
        fetch('/api/observability/poll-teardown', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ events }),
        }).catch(() => { /* beacon best-effort */ });
      }
    } catch { /* swallow */ }
  }

  const retryRuntime = useCallback(() => {
    consecutiveFailuresRef.current = 0;
    setRuntimeUnreachable(false);
    void healthQuery.refetch();
  }, [healthQuery]);

  const refreshAll = useCallback(async () => { await healthQuery.refetch(); }, [healthQuery]);

  const contextValue = useMemo(() => ({
    loading: healthQuery.isLoading && !healthQuery.data,
    error: healthQuery.isError
      ? (healthQuery.error instanceof Error ? healthQuery.error.message : 'Failed to load runtime status')
      : null,
    runtimeStatus,
    featureSurfaceV2Active: isFeatureSurfaceV2Enabled(runtimeStatus),
    runtimeUnreachable,
    retryRuntime,
    refreshAll,
  }), [healthQuery.isLoading, healthQuery.data, healthQuery.isError, healthQuery.error,
    runtimeStatus, runtimeUnreachable, retryRuntime, refreshAll]);

  return (
    <AppRuntimeContext.Provider value={contextValue}>
      {children}
    </AppRuntimeContext.Provider>
  );
};

export function useAppRuntime(): AppRuntimeContextValue {
  const ctx = useContext(AppRuntimeContext);
  if (!ctx) throw new Error('useAppRuntime must be used within an AppRuntimeProvider');
  return ctx;
}
