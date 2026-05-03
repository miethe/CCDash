/**
 * Tests for URL encoding in apiClient write paths (G2-001/G2-002).
 *
 * Verifies that updateFeatureStatus, updatePhaseStatus, and updateTaskStatus
 * percent-encode RFC 3986 § 2.2 reserved characters in path-segment IDs before
 * issuing fetch requests.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TaskStatus } from '../../types';
import { ApiError, apiFetch, createApiClient } from '../apiClient';

// ── Helpers ────────────────────────────────────────────────────────────────────

function stubFetch(responseBody: unknown = {}, status = 200): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(responseBody), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    ),
  );
}

function calledUrl(): string {
  const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls;
  if (calls.length === 0) throw new Error('fetch was not called');
  return calls[0][0] as string;
}

function calledInit(): RequestInit {
  const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls;
  if (calls.length === 0) throw new Error('fetch was not called');
  return (calls[0][1] ?? {}) as RequestInit;
}

// ── Suite ──────────────────────────────────────────────────────────────────────

describe('apiClient — URL encoding on write paths (RFC 3986 § 2.2)', () => {
  let client: ReturnType<typeof createApiClient>;

  beforeEach(() => {
    client = createApiClient();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // ── updateFeatureStatus ──────────────────────────────────────────────────────

  describe('updateFeatureStatus', () => {
    it('encodes # in featureId (%23)', async () => {
      stubFetch({ id: 'FEAT#1', status: 'active' });
      await client.updateFeatureStatus('FEAT#1', 'active');
      expect(calledUrl()).toBe('/api/features/FEAT%231/status');
    });

    it('encodes ? in featureId (%3F)', async () => {
      stubFetch({ id: 'FEAT?X', status: 'active' });
      await client.updateFeatureStatus('FEAT?X', 'active');
      expect(calledUrl()).toBe('/api/features/FEAT%3FX/status');
    });

    it('encodes space in featureId (%20)', async () => {
      stubFetch({ id: 'MY FEAT', status: 'active' });
      await client.updateFeatureStatus('MY FEAT', 'active');
      expect(calledUrl()).toBe('/api/features/MY%20FEAT/status');
    });
  });

  // ── updatePhaseStatus ────────────────────────────────────────────────────────

  describe('updatePhaseStatus', () => {
    it('encodes & in phaseId (%26)', async () => {
      stubFetch({});
      await client.updatePhaseStatus('FEAT-1', 'phase&2', 'done');
      expect(calledUrl()).toBe('/api/features/FEAT-1/phases/phase%262/status');
    });

    it('encodes % in featureId (%25)', async () => {
      stubFetch({});
      await client.updatePhaseStatus('FEAT%20X', 'phase-1', 'in-progress');
      // The literal % must itself be encoded; the resulting featureId segment is FEAT%2520X
      expect(calledUrl()).toBe('/api/features/FEAT%2520X/phases/phase-1/status');
    });

    it('encodes + in phaseId (%2B)', async () => {
      stubFetch({});
      await client.updatePhaseStatus('FEAT-2', 'phase+alpha', 'todo');
      expect(calledUrl()).toBe('/api/features/FEAT-2/phases/phase%2Balpha/status');
    });
  });

  // ── updateTaskStatus ─────────────────────────────────────────────────────────

  describe('updateTaskStatus', () => {
    it('encodes # in taskId (%23)', async () => {
      stubFetch({});
      await client.updateTaskStatus('FEAT-1', 'phase-1', 'task#3', 'done');
      expect(calledUrl()).toBe('/api/features/FEAT-1/phases/phase-1/tasks/task%233/status');
    });

    it('encodes space, &, and + together across all three IDs', async () => {
      stubFetch({});
      await client.updateTaskStatus('F A', 'p&1', 't+2', 'in-progress');
      expect(calledUrl()).toBe('/api/features/F%20A/phases/p%261/tasks/t%2B2/status');
    });
  });

  // ── Plain IDs are unaffected ─────────────────────────────────────────────────

  describe('plain IDs (no reserved chars)', () => {
    it('leaves alphanumeric IDs unchanged in updateFeatureStatus', async () => {
      stubFetch({ id: 'FEAT-123', status: 'active' });
      await client.updateFeatureStatus('FEAT-123', 'active');
      expect(calledUrl()).toBe('/api/features/FEAT-123/status');
    });

    it('leaves alphanumeric IDs unchanged in updatePhaseStatus', async () => {
      stubFetch({});
      await client.updatePhaseStatus('FEAT-1', 'phase-2', 'done');
      expect(calledUrl()).toBe('/api/features/FEAT-1/phases/phase-2/status');
    });

    it('leaves alphanumeric IDs unchanged in updateTaskStatus', async () => {
      const status: TaskStatus = 'done';
      stubFetch({});
      await client.updateTaskStatus('FEAT-1', 'phase-1', 'T1-001', status);
      expect(calledUrl()).toBe('/api/features/FEAT-1/phases/phase-1/tasks/T1-001/status');
    });
  });
});

describe('apiClient — auth/session foundation', () => {
  let client: ReturnType<typeof createApiClient>;

  beforeEach(() => {
    client = createApiClient();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends same-origin credentials for cookie-backed auth requests', async () => {
    stubFetch({
      authenticated: false,
      subject: null,
      displayName: null,
      groups: [],
      scopes: [],
      memberships: [],
      provider: 'oidc',
      authMode: 'anonymous',
      localMode: false,
    });

    await client.getAuthSession();

    expect(calledUrl()).toBe('/api/auth/session');
    expect(calledInit().credentials).toBe('same-origin');
  });

  it('defaults all shared transport calls to same-origin credentials', async () => {
    stubFetch({ ok: true });

    await apiFetch('/api/execution/runs');

    expect(calledUrl()).toBe('/api/execution/runs');
    expect(calledInit().credentials).toBe('same-origin');
  });

  it('preserves an explicit shared transport credentials override', async () => {
    stubFetch({ ok: true });

    await apiFetch('/api/health', { credentials: 'omit' });

    expect(calledUrl()).toBe('/api/health');
    expect(calledInit().credentials).toBe('omit');
  });

  it('exposes login helper with JSON mode and encoded redirect target', async () => {
    stubFetch({ authorizationUrl: 'https://issuer.example.test/authorize' });

    await client.login({ redirectTo: '/dashboard?tab=auth' });

    expect(calledUrl()).toBe('/api/auth/login/start?redirect=false&redirectTo=%2Fdashboard%3Ftab%3Dauth');
    expect(calledInit().credentials).toBe('same-origin');
  });

  it('exposes logout helper as a POST request', async () => {
    stubFetch({ ok: true });

    await client.logout();

    expect(calledUrl()).toBe('/api/auth/logout');
    expect(calledInit().method).toBe('POST');
    expect(calledInit().credentials).toBe('same-origin');
  });

  it('classifies 401 responses as unauthenticated and carries response detail', async () => {
    stubFetch({ detail: { error: 'unauthorized', code: 'principal_unauthenticated' } }, 401);

    await expect(client.getProjects()).rejects.toMatchObject({
      status: 401,
      url: '/api/projects',
      authClassification: 'unauthenticated',
      detail: { error: 'unauthorized', code: 'principal_unauthenticated' },
    } satisfies Partial<ApiError>);
  });

  it('classifies 403 responses as unauthorized and carries response detail', async () => {
    stubFetch({ detail: { error: 'forbidden', code: 'permission_not_granted' } }, 403);

    await expect(client.getProjects()).rejects.toMatchObject({
      status: 403,
      url: '/api/projects',
      authClassification: 'unauthorized',
      detail: { error: 'forbidden', code: 'permission_not_granted' },
    } satisfies Partial<ApiError>);
  });
});
