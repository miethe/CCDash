import type { RuntimeHealthResponse } from './apiClient';

export interface RuntimeStatus {
  health: string;
  database: string;
  watcher: string;
  profile: string;
  startupSync: string;
  analyticsSnapshots: string;
  telemetryExports: string;
  jobsEnabled: boolean | null;
  storageMode: string;
  storageProfile: string;
  storageBackend: string;
  recommendedStorageProfile: string;
  supportedStorageProfiles: string[];
  filesystemSourceOfTruth: boolean | null;
  sharedPostgresEnabled: boolean | null;
  storageIsolationMode: string;
  supportedStorageIsolationModes: string[];
  storageCanonicalStore: string;
  storageSchema: string;
  canonicalSessionStore: string;
}

function normalizeText(value: unknown, fallback: string): string {
  if (typeof value !== 'string') return fallback;
  const clean = value.trim();
  return clean || fallback;
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map(item => (typeof item === 'string' ? item.trim() : ''))
    .filter(Boolean);
}

function normalizeBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function inferJobsEnabled(profile: string): boolean | null {
  if (profile === 'local' || profile === 'worker') return true;
  if (profile === 'api' || profile === 'test') return false;
  return null;
}

export function normalizeRuntimeStatus(health: RuntimeHealthResponse): RuntimeStatus {
  const profile = normalizeText(health.profile, 'local');
  const jobsEnabled = normalizeBoolean(health.jobsEnabled) ?? inferJobsEnabled(profile);
  const telemetryExports = normalizeText(
    health.telemetryExports,
    profile === 'worker' ? 'unknown' : 'not_applicable',
  );

  return {
    health: normalizeText(health.status, 'unknown'),
    database: normalizeText(health.db, 'unknown'),
    watcher: normalizeText(health.watcher, 'unknown'),
    profile,
    startupSync: normalizeText(health.startupSync, 'idle'),
    analyticsSnapshots: normalizeText(health.analyticsSnapshots, 'idle'),
    telemetryExports,
    jobsEnabled,
    storageMode: normalizeText(health.storageMode, 'unknown'),
    storageProfile: normalizeText(health.storageProfile, 'unknown'),
    storageBackend: normalizeText(health.storageBackend, 'unknown'),
    recommendedStorageProfile: normalizeText(health.recommendedStorageProfile, 'unknown'),
    supportedStorageProfiles: normalizeStringArray(health.supportedStorageProfiles),
    filesystemSourceOfTruth: normalizeBoolean(health.filesystemSourceOfTruth),
    sharedPostgresEnabled: normalizeBoolean(health.sharedPostgresEnabled),
    storageIsolationMode: normalizeText(health.storageIsolationMode, 'unknown'),
    supportedStorageIsolationModes: normalizeStringArray(health.supportedStorageIsolationModes),
    storageCanonicalStore: normalizeText(health.storageCanonicalStore, 'unknown'),
    storageSchema: normalizeText(health.storageSchema, 'n/a'),
    canonicalSessionStore: normalizeText(health.canonicalSessionStore, 'unknown'),
  };
}
