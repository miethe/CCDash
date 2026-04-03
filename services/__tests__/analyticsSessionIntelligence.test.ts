import { afterEach, describe, expect, it, vi } from 'vitest';

import { analyticsService, AnalyticsApiError } from '../analytics';

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

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/analytics/session-intelligence/search?query=scope+drift&offset=0&limit=6&feature_id=feature-1&root_session_id=root-1&session_id=session-1',
    );
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

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/analytics/session-intelligence?offset=0&limit=10&feature_id=feature-1',
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/analytics/session-intelligence/detail?session_id=session-1',
    );
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
