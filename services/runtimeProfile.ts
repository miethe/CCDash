import type { RuntimeHealthResponse } from './apiClient';

export interface RuntimeStatus {
  health: string;
  database: string;
  watcher: string;
  profile: string;
  startupSync: string;
  analyticsSnapshots: string;
}

export function normalizeRuntimeStatus(health: RuntimeHealthResponse): RuntimeStatus {
  return {
    health: String(health.status || 'unknown'),
    database: String(health.db || 'unknown'),
    watcher: String(health.watcher || 'unknown'),
    profile: String(health.profile || 'local'),
    startupSync: String(health.startupSync || 'idle'),
    analyticsSnapshots: String(health.analyticsSnapshots || 'idle'),
  };
}
