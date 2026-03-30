import { describe, expect, it } from 'vitest';
import type { RuntimeHealthResponse } from '../apiClient';
import { normalizeRuntimeStatus } from '../runtimeProfile';

function buildHealthPayload(overrides: Partial<RuntimeHealthResponse> = {}): RuntimeHealthResponse {
  return {
    status: 'ok',
    db: 'connected',
    watcher: 'running',
    profile: 'api',
    startupSync: 'idle',
    analyticsSnapshots: 'idle',
    ...overrides,
  };
}

describe('normalizeRuntimeStatus', () => {
  it('normalizes expanded runtime and storage capability fields', () => {
    const normalized = normalizeRuntimeStatus(
      buildHealthPayload({
        profile: 'worker',
        telemetryExports: 'running',
        jobsEnabled: true,
        storageMode: 'shared-enterprise',
        storageProfile: 'enterprise',
        storageBackend: 'postgres',
        recommendedStorageProfile: 'enterprise',
        supportedStorageProfiles: ['enterprise'],
        filesystemSourceOfTruth: false,
        sharedPostgresEnabled: true,
        storageIsolationMode: 'schema',
        supportedStorageIsolationModes: ['schema', 'tenant'],
        storageCanonicalStore: 'postgres_shared_instance',
        storageSchema: 'ccdash_app',
        canonicalSessionStore: 'postgres',
      }),
    );

    expect(normalized.health).toBe('ok');
    expect(normalized.database).toBe('connected');
    expect(normalized.watcher).toBe('running');
    expect(normalized.profile).toBe('worker');
    expect(normalized.telemetryExports).toBe('running');
    expect(normalized.jobsEnabled).toBe(true);
    expect(normalized.storageMode).toBe('shared-enterprise');
    expect(normalized.storageCanonicalStore).toBe('postgres_shared_instance');
    expect(normalized.supportedStorageIsolationModes).toEqual(['schema', 'tenant']);
  });

  it('infers jobs capability from runtime profile when not supplied', () => {
    const apiStatus = normalizeRuntimeStatus(
      buildHealthPayload({
        profile: 'api',
        jobsEnabled: undefined,
      }),
    );
    const workerStatus = normalizeRuntimeStatus(
      buildHealthPayload({
        profile: 'worker',
        jobsEnabled: undefined,
      }),
    );

    expect(apiStatus.jobsEnabled).toBe(false);
    expect(apiStatus.telemetryExports).toBe('not_applicable');
    expect(workerStatus.jobsEnabled).toBe(true);
    expect(workerStatus.telemetryExports).toBe('unknown');
  });

  it('uses safe defaults for missing optional storage fields', () => {
    const normalized = normalizeRuntimeStatus(
      buildHealthPayload({
        profile: 'local',
        storageMode: undefined,
        storageProfile: undefined,
        storageBackend: undefined,
        supportedStorageProfiles: undefined,
        filesystemSourceOfTruth: undefined,
        sharedPostgresEnabled: undefined,
        supportedStorageIsolationModes: undefined,
      }),
    );

    expect(normalized.storageMode).toBe('unknown');
    expect(normalized.storageProfile).toBe('unknown');
    expect(normalized.storageBackend).toBe('unknown');
    expect(normalized.supportedStorageProfiles).toEqual([]);
    expect(normalized.filesystemSourceOfTruth).toBeNull();
    expect(normalized.sharedPostgresEnabled).toBeNull();
    expect(normalized.supportedStorageIsolationModes).toEqual([]);
  });
});
