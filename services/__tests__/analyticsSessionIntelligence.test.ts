import { afterEach, describe, expect, it, vi } from 'vitest';

import { analyticsService, AnalyticsApiError } from '../analytics';

// Since 265b14e every service request goes through apiClient.apiFetch, which
// normalizes init.headers into a Headers instance (adding the project-scope
// header only when a scope is selected) and defaults credentials to
// 'same-origin'. Assert on the request the wrapper actually sends — URL,
// credentials, and the real header contents — rather than the pre-wrapper
// argument shape.
function fetchCall(fetchMock: ReturnType<typeof vi.fn>, callIndex = 0) {
  const [url, init] = fetchMock.mock.calls[callIndex] as [string, RequestInit | undefined];
  return {
    url,
    init: init ?? {},
    headers: Object.fromEntries(new Headers(init?.headers).entries()),
  };
}

describe('analyticsService session intelligence helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('builds transcript search requests with scoped filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          version: 'v1',
          query: 'scope drift',
          total: 0,
          offset: 0,
          limit: 6,
          capability: {
            supported: true,
            authoritative: true,
            storageProfile: 'enterprise',
            searchMode: 'lexical',
            detail: 'ready',
          },
          items: [],
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await analyticsService.searchSessionIntelligence({
      query: 'scope drift',
      sessionId: 'session-1',
      featureId: 'feature-1',
      rootSessionId: 'root-1',
      limit: 6,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchCall(fetchMock);
    expect(call.url).toBe(
      '/api/analytics/session-intelligence/search?query=scope+drift&offset=0&limit=6&feature_id=feature-1&root_session_id=root-1&session_id=session-1',
    );
    expect(call.init.credentials).toBe('same-origin');
    expect(call.headers).toEqual({});
  });

  it('loads rollups and detail payloads from the additive intelligence routes', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            version: 'v1',
            generatedAt: '2026-04-03T00:00:00Z',
            total: 1,
            offset: 0,
            limit: 10,
            items: [],
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            version: 'v1',
            sessionId: 'session-1',
            featureId: 'feature-1',
            rootSessionId: 'root-1',
            summary: null,
            sentimentFacts: [],
            churnFacts: [],
            scopeDriftFacts: [],
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    await analyticsService.getSessionIntelligence({ featureId: 'feature-1', limit: 10 });
    await analyticsService.getSessionIntelligenceDetail('session-1');

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const rollupCall = fetchCall(fetchMock, 0);
    expect(rollupCall.url).toBe('/api/analytics/session-intelligence?offset=0&limit=10&feature_id=feature-1');
    expect(rollupCall.init.credentials).toBe('same-origin');
    expect(rollupCall.headers).toEqual({});
    const detailCall = fetchCall(fetchMock, 1);
    expect(detailCall.url).toBe('/api/analytics/session-intelligence/detail?session_id=session-1');
    expect(detailCall.init.credentials).toBe('same-origin');
    expect(detailCall.headers).toEqual({});
  });

  it('surfaces disabled-state hints from intelligence drilldown failures', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            message: 'Transcript intelligence disabled',
            error: 'feature_disabled',
            hint: 'Switch to enterprise profile.',
          },
        }),
        { status: 503, headers: { 'content-type': 'application/json' } },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      analyticsService.getSessionIntelligenceDrilldown({
        concern: 'scope_drift',
        featureId: 'feature-1',
      }),
    ).rejects.toMatchObject({
      name: 'AnalyticsApiError',
      status: 503,
      message: 'Transcript intelligence disabled',
      code: 'feature_disabled',
      hint: 'Switch to enterprise profile.',
    });
  });
});
