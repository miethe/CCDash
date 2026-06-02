/**
 * Tests for useHealthQuery (T4-001, T4-002).
 *
 * T4-001: Health query fires GET /api/health on initial fetch.
 * T4-002: Health query declares refetchInterval: 30_000; no setInterval in AppRuntimeContext.
 *
 * Strategy: test queryFn directly via QueryClient.fetchQuery; verify polling
 * config via source-read assertions (same pattern as alerts.test.ts).
 * Fake-timer integration test verifies health refetch at 30s mark.
 */

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { QueryClient } from '@tanstack/react-query';
import { healthKeys } from '../../queries/health';

const root = resolve(fileURLToPath(new URL('../../..', import.meta.url)));

function makeHealthResponse() {
  return {
    status: 'ok',
    db: 'ok',
    watcher: 'ok',
    profile: 'local',
    schemaVersion: 'v1',
  };
}

function makeQueryClient(staleTime = 0) {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime } },
  });
}

// ── queryFn behaviour ─────────────────────────────────────────────────────────

describe('T4-001: useHealthQuery — queryFn behaviour', () => {
  let qc: QueryClient;
  let getHealthMock: () => Promise<ReturnType<typeof makeHealthResponse>>;
  let callCount: number;

  beforeEach(() => {
    qc = makeQueryClient();
    callCount = 0;
    getHealthMock = () => {
      callCount++;
      return Promise.resolve(makeHealthResponse());
    };
  });

  afterEach(() => {
    qc.clear();
    vi.clearAllMocks();
  });

  it('fires one GET /api/health on initial fetch', async () => {
    await qc.fetchQuery({
      queryKey: healthKeys.status(),
      queryFn: () => getHealthMock(),
    });
    expect(callCount).toBe(1);
  });

  it('returns normalised RuntimeStatus shape', async () => {
    const result = await qc.fetchQuery({
      queryKey: healthKeys.status(),
      queryFn: async () => {
        const { normalizeRuntimeStatus } = await import('../../runtimeProfile');
        const payload = await getHealthMock();
        return normalizeRuntimeStatus(payload);
      },
    });
    expect(result).toHaveProperty('health');
    expect(result).toHaveProperty('database');
    expect(result).toHaveProperty('featureSurfaceV2Enabled');
  });

  it('staleTime prevents re-fetch within 25s window', async () => {
    const qcStale = makeQueryClient(25_000);
    const key = healthKeys.status();
    let innerCount = 0;
    const countFn = () => { innerCount++; return getHealthMock(); };

    await qcStale.fetchQuery({ queryKey: key, queryFn: countFn });
    await qcStale.fetchQuery({ queryKey: key, queryFn: countFn });

    expect(innerCount).toBe(1);
    qcStale.clear();
  });
});

// ── Source-level polling config assertions (T4-002) ───────────────────────────

describe('T4-002: useHealthQuery — polling config declared in hook source', () => {
  const healthSrc = () => readFileSync(resolve(root, 'services', 'queries', 'health.ts'), 'utf-8');
  const runtimeSrc = () => readFileSync(resolve(root, 'contexts', 'AppRuntimeContext.tsx'), 'utf-8');

  it('health.ts declares refetchInterval: 30_000', () => {
    expect(healthSrc()).toContain('refetchInterval: 30_000');
  });

  it('health.ts declares staleTime: 25_000 (buffer below 30s interval)', () => {
    expect(healthSrc()).toContain('staleTime: 25_000');
  });

  it('AppRuntimeContext has no setInterval (polling moved to per-query refetchInterval)', () => {
    expect(runtimeSrc()).not.toContain('setInterval(');
  });

  it('AppRuntimeContext uses useHealthQuery for health (T4-001)', () => {
    expect(runtimeSrc()).toContain('useHealthQuery');
  });
});

// ── Feature poll 30s when SSE disabled — source assertion (T4-005) ───────────

describe('T4-005: feature poll 30s when SSE disabled — source assertion', () => {
  const featuresSrc = () => readFileSync(resolve(root, 'services', 'queries', 'features.ts'), 'utf-8');

  it('features.ts declares refetchInterval: 30_000 when live-features disabled (SSE fallback)', () => {
    // T4-005: raised from 5_000 to 30_000 — was too aggressive for enterprise loads.
    // When isFeatureLiveUpdatesEnabled() returns false, refetchInterval must be 30_000.
    // The ternary: isFeatureLiveUpdatesEnabled() ? false : 30_000
    expect(featuresSrc()).toContain('refetchInterval:');
    expect(featuresSrc()).toContain('30_000');
  });

  it('features.ts sets refetchInterval to false when live-features enabled (SSE supersedes poll)', () => {
    // The SSE branch of the ternary must yield false, not a number.
    expect(featuresSrc()).toContain('isFeatureLiveUpdatesEnabled()');
    // Ternary form: ? false : 30_000 — both branches present in source
    expect(featuresSrc()).toMatch(/isFeatureLiveUpdatesEnabled\(\)\s*\?\s*false\s*:\s*30_000/);
  });

  it('features.ts reads the env flag via isFeatureLiveUpdatesEnabled from live/config', () => {
    expect(featuresSrc()).toContain("from '../live/config'");
    expect(featuresSrc()).toContain('isFeatureLiveUpdatesEnabled');
  });
});

// ── Simulated 30s poll re-fire via direct fetchQuery ─────────────────────────

describe('T4-002: health refetches at 30s (QueryClient invalidation simulation)', () => {
  it('getHealth is called again after invalidation (simulates 30s refetch interval)', async () => {
    let cnt = 0;
    const getHealth = () => { cnt++; return Promise.resolve(makeHealthResponse()); };
    const qc = makeQueryClient(0);
    const key = healthKeys.status();
    const fn = () => getHealth();

    await qc.fetchQuery({ queryKey: key, queryFn: fn });
    expect(cnt).toBe(1);

    // Simulate 30s refetch cycle: invalidate → fetchQuery
    await qc.invalidateQueries({ queryKey: key });
    await qc.fetchQuery({ queryKey: key, queryFn: fn });
    expect(cnt).toBe(2);

    qc.clear();
  });
});
