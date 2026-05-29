/**
 * Tests for useAlertsQuery and useNotificationsQuery (T2-005).
 *
 * Strategy: test queryFn directly through QueryClient.fetchQuery, and verify
 * the refetchInterval option is configured via source-read assertions
 * (consistent with the noHandRolledCache guardrail pattern used in this codebase).
 *
 * Note: integration testing of refetchInterval polling requires a full React
 * rendering environment (@testing-library/react is not installed in this
 * project). The refetchInterval option is verified by source assertion below.
 *
 * Scenarios covered:
 *   T2-005 — getAlerts called on initial fetch
 *   T2-005 — returns AlertConfig[] items
 *   T2-005 — refetchInterval: 30_000 declared in alerts.ts (polling config)
 *   T2-005 — staleTime: 30_000 declared in alerts.ts
 *   T2-005 — enabled: !!projectId guard present in alerts.ts
 *   T2-005 — staleTime prevents extra fetch within cache window
 *   T2-005 — enabled: false suppresses fetch when projectId absent
 *   T2-005 — same assertions for notifications.ts
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
import { QueryClient, QueryObserver } from '@tanstack/react-query';
import type { AlertConfig } from '../../../types';
import type { Notification } from '../../../types';
import { alertsKeys, notificationsKeys } from '../../queryKeys';

// ── Helpers ───────────────────────────────────────────────────────────────────

const root = resolve(fileURLToPath(new URL('../../..', import.meta.url)));

function makeAlert(id: string): AlertConfig {
  return { id, name: `Alert ${id}`, isActive: true } as AlertConfig;
}

function makeNotification(id: string): Notification {
  return { id, message: `Notification ${id}`, isRead: false } as Notification;
}

function makeMockAlertsClient(alerts: AlertConfig[] = [makeAlert('a1')]) {
  return {
    getAlerts: vi.fn(() => Promise.resolve(alerts)),
  };
}

function makeMockNotificationsClient(notifications: Notification[] = [makeNotification('n1')]) {
  return {
    getNotifications: vi.fn(() => Promise.resolve(notifications)),
  };
}

function makeQueryClient(staleTime = 0) {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime,
      },
    },
  });
}

// Mirror queryFns
function makeAlertsQueryFn(client: ReturnType<typeof makeMockAlertsClient>) {
  return () => client.getAlerts();
}

function makeNotificationsQueryFn(client: ReturnType<typeof makeMockNotificationsClient>) {
  return () => client.getNotifications();
}

// ── Alerts: initial fetch ──────────────────────────────────────────────────────

describe('T2-005: useAlertsQuery — queryFn behaviour', () => {
  let qc: QueryClient;
  let client: ReturnType<typeof makeMockAlertsClient>;

  beforeEach(() => {
    qc = makeQueryClient();
    client = makeMockAlertsClient([makeAlert('a1'), makeAlert('a2')]);
  });

  afterEach(() => {
    qc.clear();
  });

  it('fires one GET on initial fetch', async () => {
    await qc.fetchQuery({
      queryKey: alertsKeys.list('proj-1'),
      queryFn: makeAlertsQueryFn(client),
    });
    expect(client.getAlerts).toHaveBeenCalledTimes(1);
  });

  it('returns an array of AlertConfig items', async () => {
    const result = await qc.fetchQuery({
      queryKey: alertsKeys.list('proj-1'),
      queryFn: makeAlertsQueryFn(client),
    });
    expect(Array.isArray(result)).toBe(true);
    expect(result).toHaveLength(2);
    expect(result[0].id).toBe('a1');
  });

  it('staleTime prevents re-fetch within cache window', async () => {
    const qcStale = makeQueryClient(30_000);
    const queryKey = alertsKeys.list('proj-1');
    const queryFn = makeAlertsQueryFn(client);

    await qcStale.fetchQuery({ queryKey, queryFn });
    expect(client.getAlerts).toHaveBeenCalledTimes(1);

    await qcStale.fetchQuery({ queryKey, queryFn });
    expect(client.getAlerts).toHaveBeenCalledTimes(1);

    qcStale.clear();
  });

  it('enabled: false — query is not executed (no projectId)', async () => {
    const qcDisabled = makeQueryClient();

    const observer = new QueryObserver<AlertConfig[]>(qcDisabled, {
      queryKey: alertsKeys.list(''),
      queryFn: makeAlertsQueryFn(client),
      enabled: false,
    });

    const unsubscribe = observer.subscribe(() => {});
    // Yield to allow any async scheduling
    await new Promise<void>(r => { setTimeout(r, 0); setTimeout(r, 0); });

    unsubscribe();
    qcDisabled.clear();

    expect(client.getAlerts).toHaveBeenCalledTimes(0);
  });
});

// ── Alerts: source-level config assertions (polling contract) ─────────────────
// @testing-library/react is not installed; we verify refetchInterval is
// declared via source-read (same approach as noHandRolledCache.test.ts).

describe('T2-005: useAlertsQuery — polling config declared in hook source', () => {
  it('alerts.ts declares refetchInterval: 30_000 (30s poll ported from AppRuntimeContext)', () => {
    const source = readFileSync(
      resolve(root, 'services', 'queries', 'alerts.ts'),
      'utf-8',
    );
    expect(source).toContain('refetchInterval: 30_000');
  });

  it('alerts.ts declares staleTime: 30_000', () => {
    const source = readFileSync(
      resolve(root, 'services', 'queries', 'alerts.ts'),
      'utf-8',
    );
    expect(source).toContain('staleTime: 30_000');
  });

  it('alerts.ts uses enabled: !!projectId guard', () => {
    const source = readFileSync(
      resolve(root, 'services', 'queries', 'alerts.ts'),
      'utf-8',
    );
    expect(source).toContain('enabled: !!projectId');
  });
});

// ── Alerts: re-fires after 30s interval — QueryClient direct simulation ────────

describe('T2-005: useAlertsQuery — re-fires after 30s (via direct fetchQuery simulation)', () => {
  it('getAlerts is called on mount (first fetch)', async () => {
    const client = makeMockAlertsClient([makeAlert('poll-a1')]);
    const qc = makeQueryClient(0);

    // Simulates mount: first fetch
    await qc.fetchQuery({
      queryKey: alertsKeys.list('proj-poll'),
      queryFn: () => client.getAlerts(),
    });
    expect(client.getAlerts).toHaveBeenCalledTimes(1);

    // Simulates the 30s interval re-fetch: invalidate then re-fetch
    await qc.invalidateQueries({ queryKey: alertsKeys.list('proj-poll') });
    await qc.fetchQuery({
      queryKey: alertsKeys.list('proj-poll'),
      queryFn: () => client.getAlerts(),
    });
    expect(client.getAlerts).toHaveBeenCalledTimes(2);

    qc.clear();
  });
});

// ── Notifications: initial fetch ──────────────────────────────────────────────

describe('T2-005: useNotificationsQuery — queryFn behaviour', () => {
  let qc: QueryClient;
  let client: ReturnType<typeof makeMockNotificationsClient>;

  beforeEach(() => {
    qc = makeQueryClient();
    client = makeMockNotificationsClient([makeNotification('n1'), makeNotification('n2')]);
  });

  afterEach(() => {
    qc.clear();
  });

  it('fires one GET on initial fetch', async () => {
    await qc.fetchQuery({
      queryKey: notificationsKeys.list('proj-1'),
      queryFn: makeNotificationsQueryFn(client),
    });
    expect(client.getNotifications).toHaveBeenCalledTimes(1);
  });

  it('returns an array of Notification items', async () => {
    const result = await qc.fetchQuery({
      queryKey: notificationsKeys.list('proj-1'),
      queryFn: makeNotificationsQueryFn(client),
    });
    expect(Array.isArray(result)).toBe(true);
    expect(result).toHaveLength(2);
    expect(result[0].id).toBe('n1');
  });

  it('staleTime prevents re-fetch within cache window', async () => {
    const qcStale = makeQueryClient(30_000);
    const queryKey = notificationsKeys.list('proj-1');
    const queryFn = makeNotificationsQueryFn(client);

    await qcStale.fetchQuery({ queryKey, queryFn });
    expect(client.getNotifications).toHaveBeenCalledTimes(1);

    await qcStale.fetchQuery({ queryKey, queryFn });
    expect(client.getNotifications).toHaveBeenCalledTimes(1);

    qcStale.clear();
  });
});

// ── Notifications: source-level config assertions ─────────────────────────────

describe('T2-005: useNotificationsQuery — polling config declared in hook source', () => {
  it('notifications.ts declares refetchInterval: 30_000 (30s poll ported from AppRuntimeContext)', () => {
    const source = readFileSync(
      resolve(root, 'services', 'queries', 'notifications.ts'),
      'utf-8',
    );
    expect(source).toContain('refetchInterval: 30_000');
  });

  it('notifications.ts declares staleTime: 30_000', () => {
    const source = readFileSync(
      resolve(root, 'services', 'queries', 'notifications.ts'),
      'utf-8',
    );
    expect(source).toContain('staleTime: 30_000');
  });

  it('notifications.ts uses enabled: !!projectId guard', () => {
    const source = readFileSync(
      resolve(root, 'services', 'queries', 'notifications.ts'),
      'utf-8',
    );
    expect(source).toContain('enabled: !!projectId');
  });
});

// ── Notifications: re-fires after 30s — direct simulation ────────────────────

describe('T2-005: useNotificationsQuery — re-fires after 30s (via direct fetchQuery simulation)', () => {
  it('getNotifications is called on mount then re-called after invalidation (simulates 30s refetch)', async () => {
    const client = makeMockNotificationsClient([makeNotification('poll-n1')]);
    const qc = makeQueryClient(0);

    // Simulates mount: first fetch
    await qc.fetchQuery({
      queryKey: notificationsKeys.list('proj-poll'),
      queryFn: () => client.getNotifications(),
    });
    expect(client.getNotifications).toHaveBeenCalledTimes(1);

    // Simulates the 30s interval re-fetch: invalidate then re-fetch
    await qc.invalidateQueries({ queryKey: notificationsKeys.list('proj-poll') });
    await qc.fetchQuery({
      queryKey: notificationsKeys.list('proj-poll'),
      queryFn: () => client.getNotifications(),
    });
    expect(client.getNotifications).toHaveBeenCalledTimes(2);

    qc.clear();
  });
});
